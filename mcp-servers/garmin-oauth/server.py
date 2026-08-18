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

Module split (Task #57):
    db_common.py   — shared utils (Garmin client, Turso _tq/_tx, _wrap_401, _dumps, _monday)
    garmin.py      — Garmin API tools (activities, wellness, workouts, ...)
    db_read.py     — DB read tools (plan, VDOT, history, body-state, notes)
    db_write.py    — DB write tools (plan-workout, log-body-state, add-note, add-task, add-exercise)
    auth.py        — OAuth 2.1 provider + HTTP transport (Claude Custom Connectors)
    server.py      — this file: FastMCP init + registration + main()
"""
from __future__ import annotations
import os
import sys

from mcp.server.fastmcp import FastMCP

# Importing db_common runs its truststore init + garminconnect import check
# BEFORE any HTTP-related dependency loads urllib3. Keep this order.
from db_common import USER_ID, TOKEN_DIR, _seed_tokens_from_env
from garmin import register_garmin_tools
from db_read import register_db_read_tools
from db_write import register_db_write_tools


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
- "co zapisałem / ostatnie notatki / pokaż insights" → DB: db-get-notes (read stream, filter po category / since_days / limit)
- "dodaj zadanie / TODO / muszę zrobić"            → DB: db-add-task (category: sport/praca/dom/relacje/zdrowie/inne, priority: low/medium/high)
- "dodaj ćwiczenie / nowe ćwiczenie / zapisz ćwiczenie X" → DB: db-add-exercise (category: rolowanie/aktywacja/stretch/wzmocnienie/kardio)
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

# Register tools from modules onto the FastMCP instance.
register_garmin_tools(mcp)
register_db_read_tools(mcp)
register_db_write_tools(mcp)


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
        # (see auth.SimpleOAuthProvider). Kept read here only for backwards debug.
        _ = os.environ.get("AUTH_TOKEN")
        from auth import run_http
        run_http(mcp, args.host, args.port)
