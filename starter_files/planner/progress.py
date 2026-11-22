"""Progres do celu + adaptacja planu do wykonania (planned vs actual).

Idea reaktywności: makroplan "referencyjny" zapisany w DB służy do mierzenia
adherence; plan "na dziś" generujemy zawsze od nowa z realnego baseline'u
(build_macrocycle jest deterministyczny), więc odchylenia propagują się same.
"""
from __future__ import annotations
from datetime import date

from planner import methodology as M
from planner.paces import vdot_from_time, race_time

STATUS_LABELS = {
    "achieved": "✅ Cel w zasięgu już teraz",
    "realistic": "🟢 Realny",
    "ambitious": "🟡 Ambitny",
    "unrealistic": "🔴 Mało realny w tym terminie",
    "past": "⏹️ Termin minął",
}


def goal_progress(current_vdot: float, distance_km: float, target_time_sec: int | None,
                  race_date: date | None, today: date) -> dict:
    """Ile VDOT brakuje do celu i czy realnie da się to dowieźć do startu."""
    dist_m = distance_km * 1000
    out = {"current_vdot": current_vdot,
           "predicted_now_sec": race_time(current_vdot, dist_m),
           "weeks_left": max((race_date - today).days / 7, 0) if race_date else None}
    if not target_time_sec:
        return out
    goal_vdot = vdot_from_time(dist_m, target_time_sec)
    gap = goal_vdot - current_vdot
    weeks = out["weeks_left"] or 0
    need = gap / weeks if weeks > 0 else float("inf")
    if gap <= 0:
        status = "achieved"
    elif weeks <= 0:
        status = "past"
    elif need <= M.VDOT_GAIN_PER_WEEK_REALISTIC:
        status = "realistic"
    elif need <= M.VDOT_GAIN_PER_WEEK_AMBITIOUS:
        status = "ambitious"
    else:
        status = "unrealistic"
    expected = current_vdot + min(gap, M.VDOT_GAIN_PER_WEEK_REALISTIC * weeks) if gap > 0 else current_vdot
    out.update({
        "goal_vdot": round(goal_vdot, 1), "vdot_gap": round(gap, 1),
        "vdot_needed_per_week": round(need, 2) if weeks > 0 else None,
        "status": status, "status_label": STATUS_LABELS[status],
        "expected_vdot_at_race": round(expected, 1),
        "predicted_at_race_sec": race_time(expected, dist_m),
    })
    return out


def adherence(reference: list[dict], actual_km: dict[str, float], today: date) -> dict:
    """Porównanie referencyjnego makroplanu z realnymi km dla zakończonych tygodni.

    reference: [{"week_start": "YYYY-MM-DD", "target_km": float, ...}]
    actual_km: {"YYYY-MM-DD" (poniedziałek): km}
    """
    rows = []
    for w in reference:
        ws = date.fromisoformat(w["week_start"])
        if ws > today:
            continue
        done = (today - ws).days >= 7
        act = round(actual_km.get(w["week_start"], 0.0), 1)
        ratio = act / w["target_km"] if w["target_km"] else None
        rows.append({"week_start": w["week_start"], "phase": w.get("phase"),
                     "planned_km": w["target_km"], "actual_km": act,
                     "ratio": round(ratio, 2) if ratio is not None else None, "complete": done})
    closed = [r for r in rows if r["complete"]]
    planned = sum(r["planned_km"] for r in closed)
    total = round(sum(r["actual_km"] for r in closed) / planned, 2) if planned else None
    return {"weeks": rows, "overall_ratio": total}


def baseline_from_actual(actual_last_weeks: list[float]) -> float:
    """Baseline do replanu: średnia ostatnich (max 4) zakończonych tygodni."""
    recent = actual_last_weeks[-4:]
    return round(sum(recent) / len(recent), 1) if recent else M.MIN_WEEK_KM


def replan_advice(adh: dict, max_pain: int) -> list[str]:
    """Tekstowe wskazówki co zmienić — deterministyczne progi z methodology."""
    tips = []
    closed = [r for r in adh["weeks"] if r["complete"] and r["ratio"] is not None]
    last2 = closed[-2:]
    if len(last2) == 2 and all(r["ratio"] < M.ADHERENCE_LOW for r in last2):
        tips.append("2 tygodnie <80% planu → replan od realnego baseline'u (bez podnoszenia objętości).")
    if last2 and last2[-1]["ratio"] > M.ADHERENCE_HIGH:
        tips.append("Ostatni tydzień >115% planu → nie dokładaj; trzymaj poziom, ryzyko przeciążenia.")
    if max_pain >= M.PAIN_EASY_ONLY:
        tips.append(f"Ból {max_pain}/10 → najbliższy tydzień tylko easy (safety layer).")
    elif max_pain >= M.PAIN_DOWNGRADE:
        tips.append(f"Ból {max_pain}/10 → intensywność obniżona o stopień.")
    if not tips:
        tips.append("Wykonanie zgodne z planem — kontynuuj.")
    return tips
