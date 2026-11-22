"""Warstwa DB planera — jedyne miejsce, które dotyka `conn` (DIP: conn z zewnątrz).

Działa na sqlite3 (local/testy) i libsql adapterze (Turso) przez aiosql z db/api.py.
"""
from __future__ import annotations
import json
from datetime import date, timedelta

import api  # type: ignore

from planner.macro import WeekTarget, monday

DEFAULT_VDOT = 45.0
HISTORY_WEEKS = 16


def load_context(conn, user_id: int, today: date) -> dict:
    """Wszystko, czego planer potrzebuje o userze — jednym wywołaniem."""
    since = (monday(today) - timedelta(weeks=HISTORY_WEEKS)).isoformat()
    actual = {r["week_start"]: float(r["km"] or 0)
              for r in api.macro.actual_weekly_km(conn, user_id=user_id, since=since)}
    vrows = list(api.vdot.history(conn, user_id=user_id, limit=1))
    prof = api.users.profile(conn, user_id=user_id)
    prefs = {}
    if prof and prof["preferences"]:
        try:
            prefs = json.loads(prof["preferences"])
        except (ValueError, TypeError):
            prefs = {}  # uszkodzony JSON w profilu → domyślne dni, plan i tak się zbuduje
    last = api.macro.last_race_before(conn, user_id=user_id, before=today.isoformat())
    return {
        "vdot": float(vrows[0]["vdot"]) if vrows else DEFAULT_VDOT,
        "vdot_date": vrows[0]["date"] if vrows else None,
        "actual_km": actual,
        "completed_weeks_km": _completed_weeks(actual, today),
        "max_pain_7d": int(api.macro.max_pain_since(
            conn, user_id=user_id, since=(today - timedelta(days=7)).isoformat())["max_pain"] or 0),
        "prefs": prefs,
        "safety_max_km": prof["safety_max_km_week"] if prof else None,
        "last_race": (date.fromisoformat(last["date"]), float(last["distance_km"])) if last else None,
        "goal": _row(api.macro.goal_active(conn, user_id=user_id)),
    }


def _completed_weeks(actual: dict[str, float], today: date, n: int = 4) -> list[float]:
    """Km z n ostatnich ZAKOŃCZONYCH tygodni (brak biegów = 0, nie pomijamy)."""
    this_monday = monday(today)
    return [actual.get((this_monday - timedelta(weeks=k)).isoformat(), 0.0) for k in range(n, 0, -1)]


def _row(r) -> dict | None:
    return {k: r[k] for k in r.keys()} if r else None


def reference_weeks(conn, user_id: int, goal_id: int) -> list[dict]:
    out = []
    for r in api.macro.weeks_for_goal(conn, user_id=user_id, goal_id=goal_id):
        d = _row(r)
        d["quality"] = json.loads(d.pop("quality_json") or "[]")
        out.append(d)
    return out


def save_goal(conn, user_id: int, goal: dict, weeks: list[WeekTarget]) -> int:
    """Archiwizuje poprzedni aktywny cel, zapisuje nowy + snapshot makroplanu."""
    api.macro.goal_archive_active(conn, user_id=user_id)
    goal_id = api.macro.goal_add(conn, user_id=user_id, **goal)
    for w in weeks:
        api.macro.week_add(
            conn, user_id=user_id, goal_id=goal_id, week_start=w.week_start.isoformat(),
            phase=w.phase, week_in_phase=w.week_in_phase, is_deload=int(w.is_deload),
            is_race_week=int(w.is_race_week), target_km=w.target_km, long_km=w.long_km,
            quality_json=json.dumps(w.quality))
    return goal_id


def write_week(conn, user_id: int, week_start: date, days: list[dict]) -> dict:
    """Zastępuje zaplanowane (status planned) biegi tygodnia wygenerowanymi dniami.

    Nie rusza: siłowni/mobility, wykonanych/zmodyfikowanych/pominiętych wpisów.
    Dzień, na który już jest nie-planned trening tego samego typu → pomijany.
    """
    ws = week_start.isoformat()
    api.macro.delete_components_of_planned_runs(conn, user_id=user_id, week_start=ws)
    api.macro.delete_planned_runs_in_week(conn, user_id=user_id, week_start=ws)
    taken = {(r["date"], r["type_key"]) for r in api.planned.week_plan(conn, user_id=user_id, week_start=ws)}
    status_id = api.planned.status_by_key(conn, key="planned")["id"]
    inserted, skipped = 0, []
    for d in days:
        if (d["date"], d["type_key"]) in taken:
            skipped.append(d["date"])
            continue
        type_row = api.planned.type_by_key(conn, key=d["type_key"])
        api.planned.add(conn, user_id=user_id, date=d["date"], week_start=ws,
                        type_id=type_row["id"], status_id=status_id, title=d["title"],
                        target_distance_km=d["target_distance_km"], target_duration_min=None,
                        target_pace_sec_per_km=d["target_pace_sec_per_km"], target_hr_max=None,
                        notes=f"{d['notes']} | auto-planner", weather_temp_c=None, weather_note=None)
        inserted += 1
    return {"inserted": inserted, "skipped_dates": skipped}
