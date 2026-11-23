"""Makroplan tools (Turso) — db-macro-now, db-macro-adherence.

Tabele z migracji 011/012 (training_goals, macro_plan_weeks, plan_rules,
pace_targets, plan_revisions). Jedno wywołanie zamiast szukania makro w notatkach.
"""
from __future__ import annotations
import json
from datetime import date, timedelta

from db_common import _tq, _dumps, _wrap_401, _monday, USER_ID


def _weeks(goal_id: int) -> list[dict]:
    rows = _tq("""SELECT week_start, phase, is_deload, is_race_week, target_km, long_km,
                         long_structure, key_session, notes, quality_json
                    FROM macro_plan_weeks WHERE goal_id = ? AND user_id = ? ORDER BY week_start""",
               (goal_id, USER_ID))
    for r in rows:
        r["quality"] = json.loads(r.pop("quality_json") or "[]")
    return rows


def _goal(status: str = "active") -> dict | None:
    rows = _tq("""SELECT id, name, race_date, distance_km, target_time_sec, start_date, peak_km,
                         source, methodology, notes
                    FROM training_goals WHERE user_id = ? AND status = ? ORDER BY id DESC LIMIT 1""",
               (USER_ID, status))
    return rows[0] if rows else None


def _fmt(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def register_db_macro_tools(mcp) -> None:

    @mcp.tool(name="db-macro-now", description=(
        "Aktywny makroplan: cel, bieżący i następny tydzień (km, long z strukturą, akcenty, faza, deload), "
        "reguły ważne dziś (bany/capy/gate'y), tempa docelowe i ostatnie zmiany planu. "
        "WYWOŁAJ NAJPIERW przy planowaniu tygodnia. on_date: YYYY-MM-DD (default dziś)."))
    @_wrap_401
    def db_macro_now(on_date: str | None = None) -> str:
        today = on_date or date.today().isoformat()
        goal = _goal()
        if not goal:
            return _dumps({"status": "no_active_macro_plan"})
        weeks = _weeks(goal["id"])
        ws = _monday(today)
        idx = next((i for i, w in enumerate(weeks) if w["week_start"] == ws), None)
        rules = _tq("""SELECT rule_type, subject, value, valid_from, valid_to, reason FROM plan_rules
                        WHERE goal_id = ? AND user_id = ?
                          AND (valid_from IS NULL OR valid_from <= ?) AND (valid_to IS NULL OR valid_to >= ?)
                        ORDER BY rule_type, subject""", (goal["id"], USER_ID, today, today))
        paces = _tq("""SELECT p.zone, p.min_sec, p.max_sec, p.valid_from, p.source FROM pace_targets p
                        WHERE p.goal_id = ? AND p.user_id = ? AND p.valid_from <= ?
                          AND p.valid_from = (SELECT MAX(q.valid_from) FROM pace_targets q
                                               WHERE q.goal_id = p.goal_id AND q.zone = p.zone AND q.valid_from <= ?)
                        ORDER BY p.zone""", (goal["id"], USER_ID, today, today))
        for p in paces:
            p["range"] = f"{_fmt(p['min_sec'])}-{_fmt(p['max_sec'])}/km"
        revs = _tq("""SELECT created_at, event_type, reason FROM plan_revisions
                       WHERE goal_id = ? AND user_id = ? ORDER BY created_at DESC, id DESC LIMIT 5""",
                   (goal["id"], USER_ID))
        return _dumps({
            "goal": goal, "week_no": idx + 1 if idx is not None else None, "weeks_total": len(weeks),
            "this_week": weeks[idx] if idx is not None else None,
            "next_week": weeks[idx + 1] if idx is not None and idx + 1 < len(weeks) else None,
            "rules": rules, "paces": paces, "revisions": revs,
        })

    @mcp.tool(name="db-macro-adherence", description=(
        "Plan vs wykonanie dla ostatnich N zakończonych tygodni aktywnego makroplanu: km planowane vs "
        "realne (z runs), najdłuższy bieg vs planowany long. Porównuje też plan porównawczy (shadow, "
        "deterministyczny) jeśli istnieje."))
    @_wrap_401
    def db_macro_adherence(weeks: int = 4) -> str:
        goal = _goal()
        if not goal:
            return _dumps({"status": "no_active_macro_plan"})
        shadow = _goal("shadow")
        det = {w["week_start"]: w["target_km"] for w in _weeks(shadow["id"])} if shadow else {}
        this_monday = _monday()
        plan = [w for w in _weeks(goal["id"]) if w["week_start"] < this_monday][-max(1, min(weeks, 26)):]
        out = []
        for w in plan:
            end = (date.fromisoformat(w["week_start"]) + timedelta(days=6)).isoformat()
            act = _tq("""SELECT ROUND(COALESCE(SUM(distance_km),0),1) AS km,
                                ROUND(COALESCE(MAX(distance_km),0),1) AS longest, COUNT(*) AS runs
                           FROM runs WHERE user_id = ? AND date BETWEEN ? AND ?""",
                      (USER_ID, w["week_start"], end))[0]
            out.append({"week_start": w["week_start"], "planned_km": w["target_km"],
                        "deterministic_km": det.get(w["week_start"]), "actual_km": act["km"],
                        "ratio": round(act["km"] / w["target_km"], 2) if w["target_km"] else None,
                        "planned_long_km": w["long_km"], "longest_run_km": act["longest"],
                        "runs": act["runs"]})
        planned = sum(r["planned_km"] for r in out)
        return _dumps({"goal": goal["name"], "weeks": out,
                       "overall_ratio": round(sum(r["actual_km"] for r in out) / planned, 2) if planned else None})
