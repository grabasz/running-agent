"""Mikrocykl: WeekTarget → konkretne dni (format zgodny z MCP db-plan-week-bulk).

Reguły: long w dniu long_day, jakość (Q) w quality_days (nie dzień przed longiem,
nie w dni grupowe), reszta km równo na easy. Tempa wg PACE RANGE RULE.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import date, timedelta

from planner import methodology as M
from planner.macro import WeekTarget
from planner.paces import training_paces, pace_range, pace_note

# Kolejność dokładania dni biegowych ponad long + Q + grupowe (pt, pn, śr, sb).
FILL_ORDER = [4, 0, 2, 5, 1, 3]
DEFAULT_QUALITY_DAYS = [1, 3]
DEFAULT_LONG_DAY = 6
DOW = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
TYPE_KEY = {"E": "easy", "S": "easy", "L": "long", "T": "tempo", "M": "tempo",
            "I": "interval", "R": "interval", "RECOVERY": "recovery",
            "RACE": "race", "SHAKEOUT": "shakeout"}
REP_KM = {"T": 1.6, "I": 1.0, "R": 0.4}
REP_REST = {"T": "1 min trucht", "I": "2-3 min trucht", "R": "pełna przerwa (marsz/trucht 400 m)"}


def _r(km: float) -> float:
    return round(km * 2) / 2


def apply_safety(week: WeekTarget, max_pain: int) -> tuple[WeekTarget, list[str]]:
    """Ból z body_state (max z 7 dni) → cięcie objętości i degradacja intensywności."""
    if max_pain >= M.PAIN_EASY_ONLY:
        return (replace(week, target_km=round(week.target_km * M.PAIN_EASY_FACTOR, 1),
                        long_km=round(week.long_km * M.PAIN_EASY_FACTOR, 1), quality=[]),
                [f"Ból {max_pain}/10 w ostatnich 7 dniach → tylko easy, objętość ×{M.PAIN_EASY_FACTOR}"])
    if max_pain >= M.PAIN_DOWNGRADE:
        q = [{**x, "kind": M.DOWNGRADE[x["kind"]]} for x in week.quality]
        return (replace(week, target_km=round(week.target_km * M.PAIN_DOWNGRADE_FACTOR, 1), quality=q),
                [f"Ból {max_pain}/10 → intensywność obniżona (I→T, R→strides, T→M), objętość ×{M.PAIN_DOWNGRADE_FACTOR}"])
    return week, []


def _prefs_days(prefs: dict, runs_per_week: int) -> tuple[list[int], list[int], int, set[int]]:
    """Dni biegowe: jawne run_days z profilu, albo long + Q + grupowe, dopełnione FILL_ORDER."""
    long_day = prefs.get("long_day", DEFAULT_LONG_DAY)
    group = {DOW[d] for d, _ in prefs.get("group_days", []) if d in DOW}
    q_days = [d for d in prefs.get("quality_days", DEFAULT_QUALITY_DAYS)
              if d != long_day and d not in group and (d + 1) % 7 != long_day]
    if prefs.get("run_days"):
        run_days = set(prefs["run_days"]) | {long_day}
        q_days = [d for d in q_days if d in run_days]
    else:
        n = max(2, min(7, runs_per_week))
        run_days = {long_day} | group | set(q_days[:max(n - 1 - len(group), 0)])
        for d in FILL_ORDER:
            if len(run_days) >= n:
                break
            run_days.add(d)
        q_days = [d for d in q_days if d in run_days]
    return sorted(run_days), q_days, long_day, group


def _quality_day(ws: date, dow: int, q: dict, paces: dict) -> dict:
    kind, work = q["kind"], q["km"]
    lo, hi = pace_range(kind, paces)
    if kind == "M":
        desc = f"{work:g} km ciągłe @M"
    else:
        reps = max(2, round(work / REP_KM[kind]))
        desc = f"{reps}× {REP_KM[kind]:g} km @{kind}, {REP_REST[kind]}"
    return {"date": (ws + timedelta(days=dow)).isoformat(), "kind": kind,
            "type_key": TYPE_KEY[kind], "title": f"{kind}: {desc}",
            "target_distance_km": _r(work + M.WARMUP_COOLDOWN_KM),
            "target_pace_sec_per_km": (lo + hi) // 2,
            "notes": f"{pace_note(lo, hi)} | WU 2 km + CD 2 km E"}


def _easy_day(ws: date, dow: int, km: float, paces: dict, kind: str = "E", extra: str = "") -> dict:
    lo, hi = pace_range(kind, paces)
    label = {"E": "Easy", "L": "Long", "S": "Easy + przebieżki", "RECOVERY": "Recovery"}[kind]
    return {"date": (ws + timedelta(days=dow)).isoformat(), "kind": kind,
            "type_key": TYPE_KEY[kind], "title": f"{label} {km:g} km{extra}",
            "target_distance_km": km, "target_pace_sec_per_km": (lo + hi) // 2,
            "notes": pace_note(lo, hi) + (" | 6-8× 20 s przebieżki" if kind == "S" else "")}


def _race_week(week: WeekTarget, race_date: date, race_km: float, run_days: list[int],
               paces: dict) -> list[dict]:
    ws, rd = week.week_start, race_date.weekday()
    lo, hi = pace_range("E", paces)
    days = [{"date": race_date.isoformat(), "kind": "RACE", "type_key": "race",
             "title": f"START {race_km:g} km", "target_distance_km": race_km,
             "target_pace_sec_per_km": None, "notes": "Strategia: patrz races.strategy"}]
    if rd >= 1:
        days.append({"date": (race_date - timedelta(days=1)).isoformat(), "kind": "SHAKEOUT",
                     "type_key": "shakeout", "title": "Shakeout 3 km + 4 przebieżki",
                     "target_distance_km": 3.0, "target_pace_sec_per_km": (lo + hi) // 2,
                     "notes": pace_note(lo, hi)})
    easy = [d for d in run_days if d < rd - 1]
    left = max(week.target_km - race_km - 3.0, 0)
    for i, d in enumerate(easy):
        km = _r(left / len(easy))
        if km >= M.MIN_EASY_RUN_KM:
            days.append(_easy_day(ws, d, km, paces, "S" if i == len(easy) - 1 else "E"))
    return sorted(days, key=lambda x: x["date"])


def render_week(week: WeekTarget, vdot: float, prefs: dict | None = None, runs_per_week: int = 5,
                race_date: date | None = None, race_km: float | None = None) -> list[dict]:
    prefs = prefs or {}
    paces = training_paces(vdot)
    run_days, q_days, long_day, _group = _prefs_days(prefs, runs_per_week)
    if week.is_race_week and race_date:
        return _race_week(week, race_date, race_km or 21.1, run_days, paces)
    ws = week.week_start
    days: list[dict] = []
    real_q = [q for q in week.quality if q["kind"] != "S"]
    strides = any(q["kind"] == "S" for q in week.quality)
    for q, dow in zip(real_q, q_days):
        days.append(_quality_day(ws, dow, q, paces))
    used = {date.fromisoformat(d["date"]).weekday() for d in days}
    long_km = _r(week.long_km)
    if week.phase != M.PHASE_RECOVERY:
        days.append(_easy_day(ws, long_day, long_km, paces, "L"))
        used.add(long_day)
    easy_days = [d for d in run_days if d not in used]
    left = week.target_km - sum(d["target_distance_km"] for d in days)
    while easy_days and left / len(easy_days) < M.MIN_EASY_RUN_KM:
        easy_days.pop()  # za mało km na tyle dni → mniej biegów, nie krótsze śmieciowe
    kind = "RECOVERY" if week.phase == M.PHASE_RECOVERY else "E"
    for i, dow in enumerate(easy_days):
        k = "S" if strides and i == len(easy_days) // 2 else kind
        days.append(_easy_day(ws, dow, _r(left / len(easy_days)), paces, k))
    return sorted(days, key=lambda x: x["date"])
