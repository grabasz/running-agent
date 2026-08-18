"""DB read tools (Turso).

Read-only queries against Turso for plan / VDOT / history / body state / notes.
Modularized from server.py — behavior identical.
"""
from __future__ import annotations
from db_common import (
    _tq, _dumps, _wrap_401, _monday, USER_ID,
    _ALLOWED_NOTE_CATEGORIES,
)


def register_db_read_tools(mcp) -> None:
    """Register all DB read tools on the given FastMCP instance."""

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

    @mcp.tool(
        name="db-get-notes",
        description="""Fetch recent notes from the stream (insight/decision/reminder/idea/observation).

Args:
  limit: max notes to return (default 15, max 50).
  category: optional filter — one of insight/decision/reminder/idea/observation.
  since_days: only notes newer than N days (default 30, max 365).

Returns: {count, notes: [{id, date, category, content, source, related_run_id, related_task_id, created_at}]} sorted newest-first.

Perfect for mobile: "co ostatnio zapisalem" / "pokaz ostatnie decyzje" / "insights z ostatniego tygodnia"."""
    )
    def db_get_notes(
        limit: int = 15,
        category: str | None = None,
        since_days: int = 30,
    ) -> str:
        limit = max(1, min(int(limit), 50))
        since_days = max(1, min(int(since_days), 365))
        since = f"-{since_days} days"
        sql = ("SELECT id, date, category, content, source, related_run_id, "
               "related_task_id, created_at FROM notes "
               "WHERE user_id = ? AND date >= date('now', ?)")
        params: list = [USER_ID, since]
        if category:
            cat = category.strip().lower()
            if cat not in _ALLOWED_NOTE_CATEGORIES:
                return _dumps({"status": "error",
                               "message": f"category must be one of {list(_ALLOWED_NOTE_CATEGORIES)}, got {category!r}"})
            sql += " AND category = ?"
            params.append(cat)
        sql += " ORDER BY date DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = _tq(sql, tuple(params))
        return _dumps({"count": len(rows), "notes": rows, "user_id": USER_ID})
