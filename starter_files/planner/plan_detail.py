"""Reguły, tempa docelowe i historia zmian makroplanu + widok "makro na dziś".

Odpowiednik db-macro-now z notatki #41: jedno wywołanie zamiast szukania notatek.
"""
from __future__ import annotations
import json
from datetime import date

import api  # type: ignore

from planner.macro import monday


def add_rules(conn, user_id: int, goal_id: int, rules: list[dict]) -> None:
    for r in rules:
        api.macro.rule_add(conn, user_id=user_id, goal_id=goal_id, rule_type=r["rule_type"],
                           subject=r["subject"], value=r.get("value"), valid_from=r.get("valid_from"),
                           valid_to=r.get("valid_to"), reason=r.get("reason"))


def add_paces(conn, user_id: int, goal_id: int, paces: list[dict]) -> None:
    for p in paces:
        api.macro.pace_add(conn, user_id=user_id, goal_id=goal_id, zone=p["zone"],
                           min_sec=p["min_sec"], max_sec=p["max_sec"],
                           valid_from=p["valid_from"], source=p.get("source"))


def add_revision(conn, user_id: int, goal_id: int, event_type: str, reason: str,
                 diff: dict | None = None, accepted: bool = True) -> None:
    api.macro.revision_add(conn, user_id=user_id, goal_id=goal_id, event_type=event_type,
                           reason=reason, diff_json=json.dumps(diff or {}, ensure_ascii=False),
                           accepted=int(accepted))


def _rows(it) -> list[dict]:
    return [{k: r[k] for k in r.keys()} for r in it]


def macro_now(conn, user_id: int, today: date) -> dict | None:
    """Aktywny plan: tydzień bieżący + następny, reguły ważne dziś, tempa, ostatnie zmiany."""
    goal = api.macro.goal_active(conn, user_id=user_id)
    if not goal:
        return None
    gid = goal["id"]
    weeks = _rows(api.macro.weeks_for_goal(conn, user_id=user_id, goal_id=gid))
    for w in weeks:
        w["quality"] = json.loads(w.pop("quality_json") or "[]")
    ws = monday(today).isoformat()
    idx = next((i for i, w in enumerate(weeks) if w["week_start"] == ws), None)
    return {
        "goal": {k: goal[k] for k in goal.keys()},
        "this_week": weeks[idx] if idx is not None else None,
        "next_week": weeks[idx + 1] if idx is not None and idx + 1 < len(weeks) else None,
        "week_no": (idx + 1) if idx is not None else None,
        "weeks_total": len(weeks),
        "rules": _rows(api.macro.rules_active_on(conn, user_id=user_id, goal_id=gid,
                                                 on_date=today.isoformat())),
        "paces": _rows(api.macro.paces_on(conn, user_id=user_id, goal_id=gid,
                                          on_date=today.isoformat())),
        "revisions": _rows(api.macro.revisions_for_goal(conn, user_id=user_id, goal_id=gid))[:5],
    }
