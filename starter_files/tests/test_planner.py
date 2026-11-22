"""Testy deterministycznego planera (planner/*) — czysta logika, zero DB."""
from __future__ import annotations
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from planner import methodology as M  # noqa: E402
from planner.macro import MacroInput, allocate_phases, build_macrocycle, recovery_weeks_needed  # noqa: E402
from planner.paces import race_time, vdot_from_time, training_paces, pace_range  # noqa: E402
from planner.week import render_week, apply_safety  # noqa: E402
from planner.progress import goal_progress, adherence, replan_advice, baseline_from_actual  # noqa: E402

HM = 21.0975
MON = date(2026, 11, 23)


def _hm_input(**kw) -> MacroInput:
    base = dict(start=MON, baseline_km=40.0, vdot=55, race_date=date(2027, 4, 18),
                distance_km=HM, runs_per_week=5)
    base.update(kw)
    return MacroInput(**base)


# ---------- paces ----------

def test_vdot_roundtrip():
    v = vdot_from_time(HM * 1000, 5700)
    assert abs(race_time(v, HM * 1000) - 5700) <= 2


def test_project_scale_matches_fitness_md():
    # fitness.md: VDOT 55 → HM ≈ 1:33:43 (±5 s)
    assert abs(race_time(55, HM * 1000) - 5623) <= 5


def test_pace_range_rule_spreads():
    p = training_paces(55)
    for kind in ("E", "L"):
        lo, hi = pace_range(kind, p)
        assert hi - lo >= 20
    for kind in ("T", "I"):
        lo, hi = pace_range(kind, p)
        assert hi - lo == 10


# ---------- macro ----------

@pytest.mark.parametrize("n", range(1, 30))
def test_allocate_phases_sums_and_order(n):
    seq = allocate_phases(n)
    assert len(seq) == n
    order = [M.PHASE_BASE, M.PHASE_EARLY, M.PHASE_LATE]
    assert [order.index(p) for p in seq] == sorted(order.index(p) for p in seq)


def test_macro_is_deterministic():
    assert [w.to_dict() for w in build_macrocycle(_hm_input())] == \
           [w.to_dict() for w in build_macrocycle(_hm_input())]


def test_macro_ends_with_race_week_and_taper():
    weeks = build_macrocycle(_hm_input())
    assert weeks[-1].is_race_week and weeks[-1].week_start == date(2027, 4, 12)
    assert [w.phase for w in weeks[-2:]] == [M.PHASE_TAPER, M.PHASE_TAPER]
    assert weeks[-1].target_km - HM < weeks[-3].target_km * 0.5     # km treningowe w tyg. startu


def test_macro_progression_respects_step_and_deload():
    weeks = [w for w in build_macrocycle(_hm_input()) if w.phase not in (M.PHASE_TAPER,)]
    loads = [w.target_km for w in weeks if not w.is_deload]
    for a, b in zip(loads, loads[1:]):
        assert b <= a * 1.10 + 0.1        # max +10% między kolejnymi tygodniami obciążenia
    assert any(w.is_deload for w in weeks)
    assert max(loads) <= M.by_distance(M.DEFAULT_PEAK_KM, HM)


def test_safety_cap_limits_peak():
    weeks = build_macrocycle(_hm_input(baseline_km=25, safety_max_km=30))
    assert max(w.target_km for w in weeks if not w.is_race_week) <= 30   # start poza capem


def test_quality_caps():
    for w in build_macrocycle(_hm_input(baseline_km=60, peak_km=80)):
        for q in w.quality:
            if q["kind"] in M.QUALITY_CAPS:
                pct, cap = M.QUALITY_CAPS[q["kind"]]
                assert q["km"] <= min(pct * w.target_km, cap) + 0.05


def test_recovery_after_race():
    # HM 7 dni roztrenowania; start makro 2 dni po starcie → 1 tydzień recovery
    assert recovery_weeks_needed(MON, (date(2026, 11, 21), HM)) == 1
    weeks = build_macrocycle(_hm_input(last_race=(date(2026, 11, 21), HM)))
    assert weeks[0].phase == M.PHASE_RECOVERY and weeks[0].quality == []


def test_maintenance_without_goal():
    weeks = build_macrocycle(MacroInput(start=MON, baseline_km=30, vdot=50, horizon_weeks=8))
    assert len(weeks) == 8 and {w.phase for w in weeks} == {M.PHASE_MAINTENANCE}


# ---------- week ----------

def test_render_week_sums_to_target_and_keeps_rules():
    w = next(w for w in build_macrocycle(_hm_input(baseline_km=50)) if w.phase == M.PHASE_LATE)
    days = render_week(w, 55, {"group_days": [["Mon", "easy"], ["Wed", "easy"]]})
    total = sum(d["target_distance_km"] for d in days)
    assert abs(total - w.target_km) <= 2.5
    dows = {date.fromisoformat(d["date"]).weekday(): d for d in days}
    assert dows[6]["type_key"] == "long"
    assert dows[0]["type_key"] == "easy"               # dzień grupowy = easy
    assert all("Tempo:" in d["notes"] for d in days)


def test_race_week_single_shakeout():
    weeks = build_macrocycle(_hm_input())
    days = render_week(weeks[-1], 55, race_date=date(2027, 4, 18), race_km=HM)
    assert sum(d["type_key"] == "shakeout" for d in days) == 1
    assert days[-1]["type_key"] == "race"


def test_safety_layer():
    w = next(w for w in build_macrocycle(_hm_input()) if w.phase == M.PHASE_LATE)
    easy, msg = apply_safety(w, 6)
    assert easy.quality == [] and easy.target_km < w.target_km and msg
    down, _ = apply_safety(w, 3)
    assert "I" not in {q["kind"] for q in down.quality}


# ---------- progress ----------

def test_goal_progress_statuses():
    g = goal_progress(55, HM, 5700, date(2027, 4, 18), MON)
    assert g["status"] == "achieved"                   # 55 → 1:33:43 < 1:35
    g = goal_progress(50, HM, 5400, date(2026, 12, 7), MON)
    assert g["status"] == "unrealistic"


def test_adherence_and_advice():
    ref = [{"week_start": "2026-11-02", "target_km": 40, "phase": "base"},
           {"week_start": "2026-11-09", "target_km": 40, "phase": "base"},
           {"week_start": "2026-11-16", "target_km": 40, "phase": "base"}]
    adh = adherence(ref, {"2026-11-02": 30.0, "2026-11-09": 28.0}, MON)
    assert adh["overall_ratio"] == round(58 / 120, 2)
    assert any("baseline" in t for t in replan_advice(adh, 0))
    assert baseline_from_actual([30, 28, 0, 40]) == 24.5
