"""Garmin Connect MCP server (OAuth-based).

Uses python-garminconnect (which wraps garth) for long-lived OAuth tokens.
OAuth1 lives ~1 year, OAuth2 access token 24h with silent refresh.
No browser/Playwright in the hot path.

Tool names match @etweisberg/garmin-connect-mcp 1:1 so existing skills work
without modification.

Setup (one-time):
    python setup_credentials.py       # save email+password to Windows Credential Manager
    python test_login.py              # first login with MFA, saves OAuth tokens

Tokens live in ~/.garminconnect/. If OAuth1 expires (~1 year), rerun test_login.py.
"""
from __future__ import annotations
import base64
import functools
import inspect
import json
import os
import secrets
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

# Use Windows Certificate Store (via truststore) instead of bundled certifi.
# On Windows the certifi bundle lacks some Cloudflare intermediates that Garmin uses
# — connectapi.garmin.com returns SSL cert-verify errors under requests, even though
# raw ssl.create_default_context() succeeds. truststore fixes that by routing all
# SSL through the OS trust store. Must be injected BEFORE requests/urllib3 import.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass

from mcp.server.fastmcp import FastMCP

try:
    from garminconnect import Garmin, GarminConnectAuthenticationError
except ImportError:
    print("Missing garminconnect. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

TOKEN_DIR = os.environ.get("TOKEN_DIR") or str(Path.home() / ".garminconnect")

# Multi-tenant: which DB user this MCP instance operates on.
# Default 1 (Bartek) for backward compat with existing deploys / local dev.
# Set USER_ID=2 for Matiego's Fly deploy, etc.
USER_ID = int(os.environ.get("USER_ID", "1"))


def _seed_tokens_from_env() -> None:
    """First-boot bootstrap for cloud deploy.

    If TOKEN_DIR has no garmin_tokens.json but env var GARMIN_TOKENS_JSON is set,
    write it to disk once. After that OAuth2 refresh writes update the volume
    normally, so this only runs on a fresh machine/volume.
    """
    tokens_path = Path(TOKEN_DIR) / "garmin_tokens.json"
    if tokens_path.exists():
        return
    seed = os.environ.get("GARMIN_TOKENS_JSON")
    if not seed:
        return
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    tokens_path.write_text(seed, encoding="utf-8")
    print(f"[seed] wrote {tokens_path} from GARMIN_TOKENS_JSON env", file=sys.stderr)

mcp = FastMCP(
    "personal-training",
    instructions="""Personal training assistant MCP for Bartek — runner (VDOT ~55, target sub-1:35 HM Gniezno 20.09).
Two domains: GARMIN (device + external service) and DB (Turso — source of truth for training plan + history).

DECISION RULES:
- "co ma zaplanowane / plan tygodnia / na jutro"   → DB: db-planned-for-date, db-week-plan
- "ostatni bieg / splity / jak poszło"             → GARMIN: get-last-run (server-side filter — DO NOT use list-activities + client filter)
- "aktualny VDOT / tempa treningowe"               → DB: db-current-vdot
- "trend formy / ostatnie tygodnie"                → DB: db-recent-runs, db-weekly-volume, db-recent-gym
- "kolano / body state / DOMS" (READ)              → DB: db-body-state
- "boli / czuję dyskomfort / lekki ból" (WRITE)    → DB: db-log-body-state (mobile-friendly UPSERT: location + pain_0_10 + notes)
- "zapisz notatkę / insight / decyzja / pomysł"    → DB: db-add-note (category: insight/decision/reminder/idea/observation)
- "dodaj zadanie / TODO / muszę zrobić"            → DB: db-add-task (category: sport/praca/dom/relacje/zdrowie/inne, priority: low/medium/high)
- "PB w dystansie / historia startów"              → DB: db-race-pbs
- "sen / HRV / body battery / training readiness"  → GARMIN: get-sleep, get-hrv, get-body-battery, get-training-readiness

PLANNING NEXT WEEK (workflow):
1. Assess: db-current-vdot + db-recent-runs(days=14) + db-body-state(days=14) + db-weekly-volume(weeks=4)
2. Read allowed types: db-workout-types
3. For each day: db-plan-workout(date, type_key, title, target_distance_km, target_pace_sec_per_km, notes)
4. To reset a week first: db-clear-week(week_start)  — refuses if any status='done'
5. DO NOT call create-workout / schedule-workout unless user EXPLICITLY wants the workout on the Garmin device
   (planning DB entry ≠ pushing workout to watch). Ask before pushing.

CREATING GARMIN WORKOUT FROM PLAN:
1. db-planned-for-date(date) — read what to build
2. Construct workout JSON per Garmin schema (running or strength)
3. create-workout(workout=...) → schedule-workout(workoutId, date=...)

INVARIANTS:
- DB planned_workouts = plan (source of truth). Garmin workouts = pushed-to-device (subset).
- Garmin activities = what was actually done (immutable).
- Never delete a planned_workout with status='done' — db-delete-planned-workout refuses this.
- Dates always YYYY-MM-DD. week_start = Monday (ISO).
- Paces: sec/km (e.g. 6:15/km = 375). VDOT 55 → E 6:00-6:30, M 5:20-5:30, T 4:55-5:05.
"""
)

_client: Garmin | None = None


def _get_client() -> Garmin:
    """Lazy singleton — loads OAuth tokens once, refreshes OAuth2 silently on expiry."""
    global _client
    if _client is None:
        c = Garmin()
        c.login(TOKEN_DIR)
        _client = c
    return _client


def _reset_client() -> None:
    global _client
    _client = None


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _wrap_401(fn):
    """Decorator: on 401 reset client + retry once. Preserves signature for FastMCP."""
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "unauthor" in msg:
                _reset_client()
                try:
                    return fn(*args, **kwargs)
                except Exception as e2:
                    return _dumps({
                        "status": "error",
                        "message": f"{type(e2).__name__}: {e2}",
                        "fix": "Run: python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\test_login.py",
                    })
            return _dumps({"status": "error", "message": f"{type(e).__name__}: {e}"})
    inner.__signature__ = inspect.signature(fn)
    return inner


# ============================================================================
# Session / auth
# ============================================================================

@mcp.tool(name="check-session", description="Check if the saved Garmin OAuth session is still valid.")
@_wrap_401
def check_session() -> str:
    c = _get_client()
    summary = c.get_user_summary(date.today().isoformat())
    return _dumps({
        "status": "ok",
        "date": date.today().isoformat(),
        "steps": summary.get("totalSteps"),
        "resting_hr": summary.get("restingHeartRate"),
    })


@mcp.tool(name="garmin-login", description="Instructions for OAuth setup (one-time).")
def garmin_login() -> str:
    return (
        "Garmin OAuth setup (one-time):\n"
        "  1. python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\setup_credentials.py\n"
        "  2. python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\test_login.py\n"
        "OAuth1 lives ~1 year. Verify with check-session."
    )


# ============================================================================
# Profile
# ============================================================================

@mcp.tool(name="get-user-profile", description="Get user profile + settings.")
@_wrap_401
def get_user_profile() -> str:
    c = _get_client()
    return _dumps({
        "profile": c.get_user_profile(),
        "settings": c.get_userprofile_settings(),
    })


# ============================================================================
# Activities
# ============================================================================

@mcp.tool(name="list-activities", description="List Garmin activities, paginated. Optional activityType filter (e.g. 'running', 'strength_training', 'cycling') — server-side, much faster than filtering the full list.")
@_wrap_401
def list_activities(limit: int = 20, start: int = 0, activityType: str | None = None) -> str:
    c = _get_client()
    return _dumps(c.get_activities(start, limit, activityType))


@mcp.tool(name="get-last-run", description="Get the most recent running activity (server-side type filter — use this instead of get-last-activity when you specifically need a run).")
@_wrap_401
def get_last_run() -> str:
    c = _get_client()
    runs = c.get_activities(0, 1, "running")
    if not runs:
        return _dumps({"status": "no_runs_found"})
    return _dumps(runs[0])


@mcp.tool(name="get-activity", description="Get full activity summary.")
@_wrap_401
def get_activity(activityId: str) -> str:
    c = _get_client()
    return _dumps(c.get_activity(activityId))


@mcp.tool(name="get-activity-splits", description="Get lap/split data (includes GCT balance, cadence).")
@_wrap_401
def get_activity_splits(activityId: str) -> str:
    c = _get_client()
    return _dumps(c.get_activity_splits(activityId))


@mcp.tool(name="get-activity-details", description="Time-series metrics (HR, cadence, elevation).")
@_wrap_401
def get_activity_details(activityId: str, maxChartSize: int = 2000) -> str:
    c = _get_client()
    return _dumps(c.get_activity_details(activityId, maxChartSize))


@mcp.tool(name="get-activity-hr-zones", description="Heart rate time-in-zone breakdown for an activity.")
@_wrap_401
def get_activity_hr_zones(activityId: str) -> str:
    c = _get_client()
    return _dumps(c.get_activity_hr_in_timezones(activityId))


@mcp.tool(name="get-activity-weather", description="Weather conditions during an activity.")
@_wrap_401
def get_activity_weather(activityId: str) -> str:
    c = _get_client()
    return _dumps(c.get_activity_weather(activityId))


@mcp.tool(name="get-activity-split-summaries", description="Split summaries (running walk splits, climb splits, etc.)")
@_wrap_401
def get_activity_split_summaries(activityId: str) -> str:
    c = _get_client()
    return _dumps(c.get_activity_split_summaries(activityId))


@mcp.tool(name="get-last-activity", description="Get the most recent activity summary.")
@_wrap_401
def get_last_activity() -> str:
    c = _get_client()
    return _dumps(c.get_last_activity())


@mcp.tool(name="download-fit", description="Download activity as FIT. Returns base64 bytes and a suggested filename.")
@_wrap_401
def download_fit(activityId: str) -> str:
    c = _get_client()
    data = c.download_activity(activityId, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
    return _dumps({
        "activityId": activityId,
        "filename": f"activity_{activityId}.fit",
        "data_base64": base64.b64encode(data).decode("ascii"),
        "size_bytes": len(data),
    })


# ============================================================================
# Daily wellness
# ============================================================================

@mcp.tool(name="get-daily-summary", description="Daily summary: steps, calories, distance, intensity, floors.")
@_wrap_401
def get_daily_summary(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_stats(dateStr))


@mcp.tool(name="get-daily-heart-rate", description="HR timeline for a date.")
@_wrap_401
def get_daily_heart_rate(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_heart_rates(dateStr))


@mcp.tool(name="get-daily-stress", description="Stress level throughout the day.")
@_wrap_401
def get_daily_stress(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_stress_data(dateStr))


@mcp.tool(name="get-daily-intensity-minutes", description="Intensity minutes earned for a date.")
@_wrap_401
def get_daily_intensity_minutes(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_intensity_minutes_data(dateStr))


@mcp.tool(name="get-daily-respiration", description="Respiration rate for a date.")
@_wrap_401
def get_daily_respiration(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_respiration_data(dateStr))


# ============================================================================
# Body / recovery
# ============================================================================

@mcp.tool(name="get-sleep", description="Sleep data (score, stages, HRV) for a date.")
@_wrap_401
def get_sleep(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_sleep_data(dateStr))


@mcp.tool(name="get-body-battery", description="Body battery charged/drained values for a date range.")
@_wrap_401
def get_body_battery(startDate: str, endDate: str | None = None) -> str:
    c = _get_client()
    return _dumps(c.get_body_battery(startDate, endDate))


@mcp.tool(name="get-hrv", description="Heart rate variability (HRV) data for a date.")
@_wrap_401
def get_hrv(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_hrv_data(dateStr))


@mcp.tool(name="get-weight", description="Weight measurements over a date range.")
@_wrap_401
def get_weight(startDate: str, endDate: str) -> str:
    c = _get_client()
    return _dumps(c.get_weigh_ins(startDate, endDate))


@mcp.tool(name="get-hydration", description="Daily hydration for a date.")
@_wrap_401
def get_hydration(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_hydration_data(dateStr))


# ============================================================================
# Performance
# ============================================================================

@mcp.tool(name="get-vo2max", description="VO2 Max / fitness level estimate for a date.")
@_wrap_401
def get_vo2max(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_max_metrics(dateStr))


@mcp.tool(name="get-training-readiness", description="Training readiness score for a date.")
@_wrap_401
def get_training_readiness(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_training_readiness(dateStr))


@mcp.tool(name="get-training-status", description="Training status (productive, maintaining, detraining) for a date.")
@_wrap_401
def get_training_status(dateStr: str) -> str:
    c = _get_client()
    return _dumps(c.get_training_status(dateStr))


@mcp.tool(name="get-personal-records", description="All personal records with history.")
@_wrap_401
def get_personal_records() -> str:
    c = _get_client()
    return _dumps(c.get_personal_record())


@mcp.tool(name="get-fitness-stats", description="Aggregated fitness stats by activity type over a date range.")
@_wrap_401
def get_fitness_stats(startDate: str, endDate: str, metric: str = "distance", groupByActivities: bool = True) -> str:
    c = _get_client()
    return _dumps(c.get_progress_summary_between_dates(startDate, endDate, metric, groupByActivities))


# ============================================================================
# Goals & badges
# ============================================================================

@mcp.tool(name="get-goals", description="Active goals (status: active/completed/past).")
@_wrap_401
def get_goals(status: str = "active", start: int = 0, limit: int = 30) -> str:
    c = _get_client()
    return _dumps(c.get_goals(status, start, limit))


@mcp.tool(name="get-badges", description="Earned badges.")
@_wrap_401
def get_badges() -> str:
    c = _get_client()
    return _dumps(c.get_earned_badges())


# ============================================================================
# Workouts
# ============================================================================

@mcp.tool(name="list-workouts", description="List saved workouts (paginated).")
@_wrap_401
def list_workouts(start: int = 0, limit: int = 100) -> str:
    c = _get_client()
    return _dumps(c.get_workouts(start, limit))


@mcp.tool(name="get-workout", description="Get a single workout by ID with full step details.")
@_wrap_401
def get_workout(workoutId: str) -> str:
    c = _get_client()
    return _dumps(c.get_workout_by_id(workoutId))


@mcp.tool(name="download-workout-fit", description="Download workout as FIT bytes (base64).")
@_wrap_401
def download_workout_fit(workoutId: str) -> str:
    c = _get_client()
    data = c.download_workout(workoutId)
    return _dumps({
        "workoutId": workoutId,
        "filename": f"workout_{workoutId}.fit",
        "data_base64": base64.b64encode(data).decode("ascii"),
        "size_bytes": len(data),
    })


@mcp.tool(name="create-workout", description="Upload a workout from JSON. Argument workout: dict or JSON string.")
@_wrap_401
def create_workout(workout: Any) -> str:
    c = _get_client()
    if isinstance(workout, str):
        try:
            workout = json.loads(workout)
        except Exception:
            pass
    return _dumps(c.upload_workout(workout))


@mcp.tool(name="schedule-workout", description="Schedule an existing workout to a date (YYYY-MM-DD).")
@_wrap_401
def schedule_workout(workoutId: str, date: str) -> str:
    c = _get_client()
    return _dumps(c.schedule_workout(workoutId, date))


@mcp.tool(name="delete-workout", description="Delete a workout from Garmin.")
@_wrap_401
def delete_workout(workoutId: str) -> str:
    c = _get_client()
    return _dumps(c.delete_workout(workoutId))


@mcp.tool(name="unschedule-workout", description="Remove a scheduled workout from the calendar.")
@_wrap_401
def unschedule_workout(workoutId: str) -> str:
    c = _get_client()
    return _dumps(c.unschedule_workout(workoutId))


# ============================================================================
# Turso DB tools — remote read + limited planning writes.
# Reads: plan, VDOT, history, body state, weekly volume.
# Writes: only planned_workouts (+ components + delete). No touching actuals.
# ============================================================================

_turso_conn = None


def _turso():
    """Lazy libsql connection to Turso. Re-created on failure."""
    global _turso_conn
    if _turso_conn is None:
        import libsql
        url = os.environ.get("TURSO_DATABASE_URL")
        token = os.environ.get("TURSO_AUTH_TOKEN")
        if not url or not token:
            raise RuntimeError("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN not set")
        _turso_conn = libsql.connect(url, auth_token=token)
    return _turso_conn


def _tq(sql: str, params=None):
    """Turso query returning list[dict]. Params can be tuple (?) or dict (:name)."""
    cur = _turso().execute(sql, params or ())
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _tx(sql: str, params=None) -> dict:
    """Turso write. Returns {'rowcount': N, 'lastrowid': X}."""
    conn = _turso()
    cur = conn.execute(sql, params or ())
    conn.commit()
    return {"rowcount": cur.rowcount, "lastrowid": cur.lastrowid}


def _monday(d: str | None = None) -> str:
    """Get Monday-anchored week_start for a given date (or today)."""
    from datetime import date as _d, timedelta
    day = _d.fromisoformat(d) if d else _d.today()
    return (day - timedelta(days=day.weekday())).isoformat()


# ---------------------------------------------------------------------------
# READ tools
# ---------------------------------------------------------------------------

@mcp.tool(name="db-current-vdot", description="Get the current (latest) VDOT + threshold pace. Use for computing Jack Daniels training paces.")
@_wrap_401
def db_current_vdot() -> str:
    rows = _tq("SELECT date, vdot, t_pace_sec, source, notes FROM vdot_history WHERE user_id = ? ORDER BY date DESC LIMIT 1", (USER_ID,))
    return _dumps(rows[0] if rows else {"status": "no_vdot_recorded"})


@mcp.tool(name="db-week-plan", description="Planned workouts for a week (Monday-anchored). Defaults to current week if week_start omitted (YYYY-MM-DD Monday date).")
@_wrap_401
def db_week_plan(week_start: str | None = None) -> str:
    ws = week_start or _monday()
    rows = _tq("""
        SELECT p.id, p.date, p.week_start, p.title, p.target_distance_km,
               p.target_duration_min, p.target_pace_sec_per_km, p.target_hr_max, p.notes,
               p.weather_temp_c, p.weather_note,
               t.key AS type_key, t.display_pl AS type_display, t.category AS type_category,
               s.key AS status_key, s.display_pl AS status_display,
               p.actual_run_id, p.actual_session_id, p.actual_notes
          FROM planned_workouts p
          JOIN workout_types t ON t.id = p.type_id
          JOIN workout_statuses s ON s.id = p.status_id
         WHERE p.week_start = ? AND p.user_id = ?
         ORDER BY p.date, p.id
    """, (ws, USER_ID))
    return _dumps({"week_start": ws, "workouts": rows})


@mcp.tool(name="db-planned-for-date", description="Planned workouts for a specific date (YYYY-MM-DD). Empty list if nothing scheduled.")
@_wrap_401
def db_planned_for_date(date: str) -> str:
    rows = _tq("""
        SELECT p.id, p.date, p.title, p.target_distance_km, p.target_pace_sec_per_km, p.notes,
               t.key AS type_key, t.display_pl AS type_display, t.category AS type_category,
               s.key AS status_key
          FROM planned_workouts p
          JOIN workout_types t ON t.id = p.type_id
          JOIN workout_statuses s ON s.id = p.status_id
         WHERE p.date = ? AND p.user_id = ?
         ORDER BY p.id
    """, (date, USER_ID))
    return _dumps(rows)


@mcp.tool(name="db-plan-components", description="All sub-components of a planned workout (per-item breakdown of a monolithic entry like 'REST + foam + mobility').")
@_wrap_401
def db_plan_components(planned_workout_id: int) -> str:
    rows = _tq("""
        SELECT c.id, c.order_idx, c.label, c.actual_notes,
               s.key AS status_key, s.display_pl AS status_display
          FROM planned_workout_components c
          JOIN workout_statuses s ON s.id = c.status_id
          JOIN planned_workouts p ON p.id = c.planned_workout_id
         WHERE c.planned_workout_id = ? AND p.user_id = ?
         ORDER BY c.order_idx, c.id
    """, (planned_workout_id, USER_ID))
    return _dumps(rows)


@mcp.tool(name="db-recent-runs", description="Recent runs with running dynamics (Garmin data). Default last 14 days.")
@_wrap_401
def db_recent_runs(days: int = 14) -> str:
    rows = _tq(f"""
        SELECT id, date, name, distance_km, moving_sec, pace_sec_per_km,
               hr_avg, hr_max, cadence_avg, elevation_gain_m,
               vertical_oscillation_cm, ground_contact_ms, gct_balance_left_pct,
               stride_length_cm, vertical_ratio_pct,
               training_effect_aerobic, training_load, type, notes
          FROM runs
         WHERE date >= date('now', '-{int(days)} days') AND user_id = ?
         ORDER BY date DESC, id DESC
    """, (USER_ID,))
    return _dumps(rows)


@mcp.tool(name="db-recent-gym", description="Recent strength sessions with set-level details. Default last 14 days.")
@_wrap_401
def db_recent_gym(days: int = 14) -> str:
    sessions = _tq(f"""
        SELECT id, date, duration_min, hr_avg, hr_max, context, notes
          FROM gym_sessions
         WHERE date >= date('now', '-{int(days)} days') AND user_id = ?
         ORDER BY date DESC
    """, (USER_ID,))
    for s in sessions:
        s["sets"] = _tq("""
            SELECT exercise, set_num, reps, duration_sec, weight_kg, weight_per_side, rpe, notes
              FROM gym_sets WHERE session_id = ? ORDER BY exercise, set_num
        """, (s["id"],))
    return _dumps(sessions)


@mcp.tool(name="db-body-state", description="Body state entries (knee, calf, back pain, DOMS). Default last 14 days.")
@_wrap_401
def db_body_state(days: int = 14) -> str:
    rows = _tq(f"""
        SELECT date, location, pain_0_10, doms, notes
          FROM body_state
         WHERE date >= date('now', '-{int(days)} days') AND user_id = ?
         ORDER BY date DESC, location
    """, (USER_ID,))
    return _dumps(rows)


@mcp.tool(name="db-weekly-volume", description="Weekly mileage history. Default last 6 weeks.")
@_wrap_401
def db_weekly_volume(weeks: int = 6) -> str:
    rows = _tq(f"""
        SELECT week_start, distance_km, elevation_gain_m, duration_sec, num_runs, longest_km, trend
          FROM weekly_volume
         WHERE user_id = ?
         ORDER BY week_start DESC LIMIT {int(weeks)}
    """, (USER_ID,))
    return _dumps(rows)


@mcp.tool(name="db-race-pbs", description="All races with times and PBs. Useful for planning race strategy.")
@_wrap_401
def db_race_pbs() -> str:
    rows = _tq("""
        SELECT date, name, distance_km, target_time_sec, actual_time_sec, is_pb,
               place_overall, strategy, notes
          FROM races
         WHERE user_id = ?
         ORDER BY date DESC
    """, (USER_ID,))
    return _dumps(rows)


@mcp.tool(name="db-workout-types", description="List of allowed workout type keys (easy, tempo, interval, long, recovery, shakeout, race, strength_a, strength_b, mobility, rest, cross, kickboxing). Use with db-plan-workout.")
@_wrap_401
def db_workout_types() -> str:
    rows = _tq("SELECT key, display_pl, category, icon FROM workout_types ORDER BY sort_order")
    return _dumps(rows)


# ---------------------------------------------------------------------------
# WRITE tools — planning only
# ---------------------------------------------------------------------------

@mcp.tool(
    name="db-plan-workout",
    description="""Add a planned workout to the training plan.

Args:
  date: YYYY-MM-DD. Must be today or future (past dates rejected).
  type_key: one of workout_types keys (call db-workout-types to list). Common: easy, tempo, interval, long, strength_a, rest.
  title: short human description, e.g. "Easy 6K @6:15 z Kubą".
  target_distance_km: optional.
  target_pace_sec_per_km: optional (e.g. 375 = 6:15/km).
  target_duration_min: optional.
  target_hr_max: optional (HR cap).
  notes: optional context (e.g. "spotkanie grupowe, plany zależne od pogody").

Returns the new planned_workout id on success.
Errors if a workout of the same type already exists for that date (UNIQUE constraint)."""
)
@_wrap_401
def db_plan_workout(
    date: str,
    type_key: str,
    title: str,
    target_distance_km: float | None = None,
    target_pace_sec_per_km: int | None = None,
    target_duration_min: int | None = None,
    target_hr_max: int | None = None,
    notes: str | None = None,
) -> str:
    from datetime import date as _d
    today = _d.today().isoformat()
    if date < today:
        return _dumps({"status": "error", "message": f"Cannot plan in the past (date={date}, today={today})"})
    tk = _tq("SELECT id FROM workout_types WHERE key = ?", (type_key,))
    if not tk:
        return _dumps({"status": "error", "message": f"Unknown type_key '{type_key}'. Use db-workout-types to list valid keys."})
    week_start = _monday(date)
    result = _tx("""
        INSERT INTO planned_workouts
            (date, week_start, type_id, status_id, title, target_distance_km,
             target_duration_min, target_pace_sec_per_km, target_hr_max, notes, user_id)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
    """, (date, week_start, tk[0]["id"], title, target_distance_km,
          target_duration_min, target_pace_sec_per_km, target_hr_max, notes, USER_ID))
    return _dumps({"status": "ok", "planned_workout_id": result["lastrowid"], "date": date, "type_key": type_key, "user_id": USER_ID})


@mcp.tool(
    name="db-plan-component",
    description="Add a sub-component (checkbox item) to an existing planned workout. Use to split a monolithic entry into checkable parts (e.g. 'REST' + 'Foam roll 10min' + 'Mobility 15min')."
)
@_wrap_401
def db_plan_component(planned_workout_id: int, order_idx: int, label: str) -> str:
    parent = _tq("SELECT id FROM planned_workouts WHERE id = ? AND user_id = ?", (planned_workout_id, USER_ID))
    if not parent:
        return _dumps({"status": "error", "message": f"No planned_workout with id={planned_workout_id} for user_id={USER_ID}"})
    result = _tx("""
        INSERT INTO planned_workout_components (planned_workout_id, order_idx, label, status_id)
        VALUES (?, ?, ?, 1)
    """, (planned_workout_id, order_idx, label))
    return _dumps({"status": "ok", "component_id": result["lastrowid"]})


@mcp.tool(
    name="db-delete-planned-workout",
    description="Delete a planned workout by id. Refuses if status is 'done' (protects logged workouts). Cascades to components."
)
@_wrap_401
def db_delete_planned_workout(planned_workout_id: int) -> str:
    row = _tq("""
        SELECT p.id, p.date, p.title, s.key AS status_key
          FROM planned_workouts p JOIN workout_statuses s ON s.id = p.status_id
         WHERE p.id = ? AND p.user_id = ?
    """, (planned_workout_id, USER_ID))
    if not row:
        return _dumps({"status": "error", "message": f"No planned_workout with id={planned_workout_id} for user_id={USER_ID}"})
    if row[0]["status_key"] == "done":
        return _dumps({"status": "error", "message": "Refusing to delete a 'done' workout — mark as 'skipped' instead if needed"})
    _tx("DELETE FROM planned_workout_components WHERE planned_workout_id = ?", (planned_workout_id,))
    _tx("DELETE FROM planned_workouts WHERE id = ? AND user_id = ?", (planned_workout_id, USER_ID))
    return _dumps({"status": "ok", "deleted": row[0]})


@mcp.tool(
    name="db-clear-week",
    description="Delete ALL planned workouts for a given week_start (Monday YYYY-MM-DD). Refuses if any workout that week has status 'done'. Use before regenerating a week's plan."
)
@_wrap_401
def db_clear_week(week_start: str) -> str:
    done = _tq("""
        SELECT COUNT(*) AS n FROM planned_workouts p
          JOIN workout_statuses s ON s.id = p.status_id
         WHERE p.week_start = ? AND p.user_id = ? AND s.key = 'done'
    """, (week_start, USER_ID))
    if done and done[0]["n"] > 0:
        return _dumps({"status": "error", "message": f"Refusing — {done[0]['n']} workouts in week {week_start} are marked 'done'"})
    _tx("""DELETE FROM planned_workout_components WHERE planned_workout_id IN
           (SELECT id FROM planned_workouts WHERE week_start = ? AND user_id = ?)""", (week_start, USER_ID))
    result = _tx("DELETE FROM planned_workouts WHERE week_start = ? AND user_id = ?", (week_start, USER_ID))
    return _dumps({"status": "ok", "week_start": week_start, "deleted_workouts": result["rowcount"]})


# ---------------------------------------------------------------------------
# WRITE tools — mobile-friendly (body_state, notes, tasks)
# ---------------------------------------------------------------------------

_ALLOWED_NOTE_CATEGORIES = ("insight", "decision", "reminder", "idea", "observation")
_ALLOWED_TASK_CATEGORIES = ("sport", "praca", "dom", "relacje", "zdrowie", "inne")
_ALLOWED_TASK_PRIORITIES = ("low", "medium", "high")


@mcp.tool(
    name="db-log-body-state",
    description="""Log a body-state entry (pain / DOMS at a specific location). UPSERT on (date, location).

Args:
  location: free text describing where — use existing patterns when possible
            (e.g. "kolano_prawe", "kolano_lewe", "lydka_prawa", "posladek_prawy", "plecy", "krzyz",
             "przywodziciel_prawy", "piriformis_prawy", "glute_prawy"). Snake_case, Polish body-parts.
  pain_0_10: integer 0-10 (0 = fine, 3 = discomfort, 5 = noticeable pain, 8+ = severe).
  notes: optional free text — what triggered it, when, what helps.
  date: optional YYYY-MM-DD, defaults to today.
  doms: optional bool (True = delayed-onset muscle soreness from prior workout), default False.

Perfect for mobile: "boli mnie kolano prawe 4/10 po biegu" → db-log-body-state(location="kolano_prawe", pain_0_10=4, notes="po biegu")."""
)
@_wrap_401
def db_log_body_state(
    location: str,
    pain_0_10: int,
    notes: str | None = None,
    date: str | None = None,
    doms: bool = False,
) -> str:
    from datetime import date as _d
    d = date or _d.today().isoformat()
    if not isinstance(pain_0_10, int) or not (0 <= pain_0_10 <= 10):
        return _dumps({"status": "error", "message": f"pain_0_10 must be int 0-10, got {pain_0_10!r}"})
    loc = (location or "").strip()
    if not loc:
        return _dumps({"status": "error", "message": "location is required (e.g. 'kolano_prawe')"})
    _tx("""
        INSERT INTO body_state (user_id, date, location, pain_0_10, doms, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, location) DO UPDATE SET
            pain_0_10 = excluded.pain_0_10,
            doms = excluded.doms,
            notes = excluded.notes
    """, (USER_ID, d, loc, int(pain_0_10), 1 if doms else 0, notes))
    return _dumps({
        "ok": True, "date": d, "location": loc, "pain_0_10": int(pain_0_10),
        "doms": bool(doms), "note": notes, "user_id": USER_ID,
    })


@mcp.tool(
    name="db-add-note",
    description="""Add a note to the notes stream (insight/decision/reminder/idea/observation).

Args:
  category: one of insight | decision | reminder | idea | observation.
  content: free text — the note body.
  date: optional YYYY-MM-DD, defaults to today.
  related_run_id: optional int — link to a runs.id (e.g. an insight about a specific run).
  related_task_id: optional int — link to a tasks.id (e.g. a decision that closes a task).

Perfect for mobile: "zapisz insight: po rolowaniu stopy klekanie znika" → db-add-note(category="insight", content="Po rolowaniu stopy prawej klekanie znika")."""
)
@_wrap_401
def db_add_note(
    category: str,
    content: str,
    date: str | None = None,
    related_run_id: int | None = None,
    related_task_id: int | None = None,
) -> str:
    from datetime import date as _d
    d = date or _d.today().isoformat()
    cat = (category or "").strip().lower()
    if cat not in _ALLOWED_NOTE_CATEGORIES:
        return _dumps({"status": "error",
                       "message": f"category must be one of {list(_ALLOWED_NOTE_CATEGORIES)}, got {category!r}"})
    txt = (content or "").strip()
    if not txt:
        return _dumps({"status": "error", "message": "content is required"})
    result = _tx("""
        INSERT INTO notes (user_id, date, category, content, related_task_id,
                           related_run_id, related_session_id, source)
        VALUES (?, ?, ?, ?, ?, ?, NULL, 'mcp_mobile')
    """, (USER_ID, d, cat, txt, related_task_id, related_run_id))
    return _dumps({
        "ok": True, "id": result["lastrowid"], "date": d, "category": cat,
        "content_preview": txt[:80] + ("…" if len(txt) > 80 else ""),
        "user_id": USER_ID,
    })


@mcp.tool(
    name="db-add-task",
    description="""Add a task to the Rozkminy (tasks) list.

Args:
  category: one of sport | praca | dom | relacje | zdrowie | inne.
  title: short imperative — "Umów fizjo", "Kupić rolki", "Zadzwonić do Kuby".
  priority: one of low | medium | high (default medium).
  due_date: optional YYYY-MM-DD.
  description: optional longer context.

Perfect for mobile: "dodaj task: umow fizjo pilnie" → db-add-task(category="zdrowie", title="Umow fizjo", priority="high")."""
)
@_wrap_401
def db_add_task(
    category: str,
    title: str,
    priority: str = "medium",
    due_date: str | None = None,
    description: str | None = None,
) -> str:
    cat = (category or "").strip().lower()
    if cat not in _ALLOWED_TASK_CATEGORIES:
        return _dumps({"status": "error",
                       "message": f"category must be one of {list(_ALLOWED_TASK_CATEGORIES)}, got {category!r}"})
    prio = (priority or "medium").strip().lower()
    if prio not in _ALLOWED_TASK_PRIORITIES:
        return _dumps({"status": "error",
                       "message": f"priority must be one of {list(_ALLOWED_TASK_PRIORITIES)}, got {priority!r}"})
    ttl = (title or "").strip()
    if not ttl:
        return _dumps({"status": "error", "message": "title is required"})
    result = _tx("""
        INSERT INTO tasks (user_id, category, title, description, due_date, status, priority, created_at)
        VALUES (?, ?, ?, ?, ?, 'todo', ?, datetime('now'))
    """, (USER_ID, cat, ttl, description, due_date, prio))
    return _dumps({
        "ok": True, "id": result["lastrowid"], "category": cat, "title": ttl,
        "priority": prio, "due_date": due_date, "user_id": USER_ID,
    })


# ============================================================================
# OAuth 2.1 provider (HTTP mode only) — needed for Claude Custom Connectors.
# Single-user auto-approve: no consent screen, DCR allowed, state on disk.
# ============================================================================

class _OAuthState:
    """Persistent OAuth state (clients + tokens) on disk.

    Access tokens are short-lived (1h) — surviving restarts is nice-to-have.
    Refresh tokens + registered clients MUST survive so Claude does not have
    to re-register after every machine sleep/restart on Fly.
    """

    def __init__(self, path: Path):
        self.path = path
        self.clients: dict[str, Any] = {}
        self.auth_codes: dict[str, Any] = {}
        self.access_tokens: dict[str, Any] = {}
        self.refresh_tokens: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        from mcp.shared.auth import OAuthClientInformationFull
        from mcp.server.auth.provider import AccessToken, RefreshToken
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[oauth] failed to load state: {e}", file=sys.stderr)
            return
        for cid, c in data.get("clients", {}).items():
            self.clients[cid] = OAuthClientInformationFull.model_validate(c)
        for tok, at in data.get("access_tokens", {}).items():
            self.access_tokens[tok] = AccessToken.model_validate(at)
        for tok, rt in data.get("refresh_tokens", {}).items():
            self.refresh_tokens[tok] = RefreshToken.model_validate(rt)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "clients": {k: v.model_dump(mode="json") for k, v in self.clients.items()},
            "access_tokens": {k: v.model_dump(mode="json") for k, v in self.access_tokens.items()},
            "refresh_tokens": {k: v.model_dump(mode="json") for k, v in self.refresh_tokens.items()},
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
        tmp.replace(self.path)


def _lenient_claude_client(client_info):
    """Return a client instance that accepts any redirect_uri under known MCP hosts.

    We pre-register the client with a placeholder redirect_uris entry (pydantic
    won't accept empty), then swap in this subclass when the SDK loads it —
    Claude/ChatGPT actual callback URLs vary per org / per connector and are
    not documented up-front. Unknown hosts fall through to parent which enforces
    the list.
    """
    from mcp.shared.auth import OAuthClientInformationFull

    ALLOWED_PREFIXES = (
        "https://claude.ai/",
        "https://claude.com/",
        "https://chatgpt.com/",
        "https://chat.openai.com/",
    )

    class _LenientClient(OAuthClientInformationFull):
        def validate_redirect_uri(self, redirect_uri):
            if redirect_uri is not None:
                s = str(redirect_uri).lower()
                if any(s.startswith(p) for p in ALLOWED_PREFIXES):
                    return redirect_uri
            return super().validate_redirect_uri(redirect_uri)

    return _LenientClient(**client_info.model_dump())


class SimpleOAuthProvider:
    """Single-user OAuth 2.1 provider with auto-approve.

    - Dynamic Client Registration disabled — clients must be pre-registered
      via OAUTH_CLIENT_ID + OAUTH_CLIENT_SECRET env (see _run_http).
    - `authorize` auto-issues an auth code without a consent screen — this
      server is personal, only the owner will ever hit it, and the client
      secret at /token is the real security boundary.
    - Access token 1h TTL; refresh token long-lived.
    """

    def __init__(self, state: _OAuthState):
        self.state = state

    async def get_client(self, client_id: str):
        c = self.state.clients.get(client_id)
        if c is None:
            return None
        return _lenient_claude_client(c)

    async def register_client(self, client_info) -> None:
        self.state.clients[client_info.client_id] = client_info
        self.state.save()

    async def authorize(self, client, params) -> str:
        from mcp.server.auth.provider import AuthorizationCode, construct_redirect_uri
        code = "ac_" + secrets.token_urlsafe(32)
        self.state.auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject="owner",
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client, authorization_code: str):
        ac = self.state.auth_codes.get(authorization_code)
        if ac and ac.expires_at > time.time() and ac.client_id == client.client_id:
            return ac
        return None

    async def exchange_authorization_code(self, client, ac):
        self.state.auth_codes.pop(ac.code, None)
        return self._issue(client.client_id, ac.scopes, ac.resource)

    async def load_refresh_token(self, client, refresh_token: str):
        rt = self.state.refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(self, client, rt, scopes):
        self.state.refresh_tokens.pop(rt.token, None)
        return self._issue(client.client_id, scopes or rt.scopes, None)

    async def load_access_token(self, token: str):
        at = self.state.access_tokens.get(token)
        if at and (at.expires_at is None or at.expires_at > time.time()):
            return at
        return None

    async def revoke_token(self, token) -> None:
        from mcp.server.auth.provider import AccessToken, RefreshToken
        if isinstance(token, AccessToken):
            self.state.access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self.state.refresh_tokens.pop(token.token, None)
        self.state.save()

    def _issue(self, client_id: str, scopes: list[str], resource):
        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthToken
        at_tok = "at_" + secrets.token_urlsafe(32)
        rt_tok = "rt_" + secrets.token_urlsafe(32)
        now = int(time.time())
        self.state.access_tokens[at_tok] = AccessToken(
            token=at_tok, client_id=client_id, scopes=scopes,
            expires_at=now + 3600, resource=resource,
        )
        self.state.refresh_tokens[rt_tok] = RefreshToken(
            token=rt_tok, client_id=client_id, scopes=scopes,
        )
        self.state.save()
        return OAuthToken(
            access_token=at_tok, token_type="Bearer", expires_in=3600,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=rt_tok,
        )


def _run_http(host: str, port: int) -> None:
    """Serve MCP over streamable-http with OAuth 2.1 (for Claude Custom Connectors)."""
    try:
        import uvicorn
        from starlette.responses import JSONResponse
        from pydantic import AnyHttpUrl
        from mcp.server.transport_security import TransportSecuritySettings
        from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
        from mcp.server.auth.provider import ProviderTokenVerifier
    except ImportError as e:
        print(f"HTTP mode requires extra deps: {e}", file=sys.stderr)
        sys.exit(1)

    fly_app = os.environ.get("FLY_APP_NAME", "garmin-mcp-grabb")
    fly_host = f"{fly_app}.fly.dev"
    issuer_url = os.environ.get("OAUTH_ISSUER_URL", f"https://{fly_host}")

    mcp.settings.transport_security = TransportSecuritySettings(
        allowed_hosts=[fly_host, "127.0.0.1:*", "localhost:*"],
        allowed_origins=[f"https://{fly_host}", "http://127.0.0.1:*", "http://localhost:*"],
    )

    oauth_client_id = os.environ.get("OAUTH_CLIENT_ID", "claude-connector")
    oauth_client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
    if not oauth_client_secret:
        print("HTTP mode requires OAUTH_CLIENT_SECRET (set via `flyctl secrets set`)",
              file=sys.stderr)
        sys.exit(1)

    # Optional second client (e.g. ChatGPT connector) for isolation from Claude.
    extra_clients = []
    for suffix in ("_2", "_3"):
        cid = os.environ.get(f"OAUTH_CLIENT_ID{suffix}")
        csec = os.environ.get(f"OAUTH_CLIENT_SECRET{suffix}")
        if cid and csec:
            extra_clients.append((cid, csec, f"Connector{suffix}"))

    state_path = Path(os.environ.get("OAUTH_STATE_PATH") or (Path(TOKEN_DIR).parent / "oauth-state.json"))
    state = _OAuthState(state_path)

    # Pre-register the allowed clients. Purge any others (leftover DCR
    # registrations from before this security tightening).
    from mcp.shared.auth import OAuthClientInformationFull
    allowed_cids = {oauth_client_id, *(c[0] for c in extra_clients)}
    stale = [cid for cid in state.clients if cid not in allowed_cids]
    for cid in stale:
        print(f"[oauth] purging stale client {cid}", file=sys.stderr)
        state.clients.pop(cid)

    def _upsert(cid, csec, name, redirect_placeholder):
        existing = state.clients.get(cid)
        if existing is None or existing.client_secret != csec:
            state.clients[cid] = OAuthClientInformationFull(
                client_id=cid,
                client_secret=csec,
                redirect_uris=[AnyHttpUrl(redirect_placeholder)],
                token_endpoint_auth_method="client_secret_post",
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope="mcp",
                client_name=name,
            )

    _upsert(oauth_client_id, oauth_client_secret,
            "Claude Custom Connector", "https://claude.ai/api/mcp/auth_callback")
    for cid, csec, _name in extra_clients:
        # Placeholder redirect only for pydantic validation; real URI is
        # accepted by _lenient_claude_client via prefix allowlist.
        _upsert(cid, csec, cid, "https://chatgpt.com/connector/oauth/placeholder")
    state.save()

    provider = SimpleOAuthProvider(state)

    mcp.settings.auth = AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        resource_server_url=AnyHttpUrl(issuer_url),
        client_registration_options=None,
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=[],
    )
    mcp._auth_server_provider = provider
    mcp._token_verifier = ProviderTokenVerifier(provider)

    app = mcp.streamable_http_app()

    async def health(_request):
        return JSONResponse({"status": "ok", "user_id": USER_ID})
    app.router.add_route("/health", health, methods=["GET"])

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Garmin Connect MCP server (OAuth)")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                        help="stdio for local Claude Code, http for remote/mobile")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    _seed_tokens_from_env()

    print(f"[startup] USER_ID={USER_ID}, TOKEN_DIR={TOKEN_DIR}, transport={args.transport}", file=sys.stderr)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # AUTH_TOKEN legacy env is ignored — HTTP mode now uses OAuth 2.1
        # (see SimpleOAuthProvider). Kept read here only for backwards debug.
        _ = os.environ.get("AUTH_TOKEN")
        _run_http(args.host, args.port)
