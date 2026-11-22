"""Tempa treningowe Danielsa + predyktor czasu i odwrotność (VDOT potrzebny do celu).

Czyste funkcje — zero DB. Skala VDOT = skala projektu (fitness.md).
Tabela temp = ta sama co w MCP `db-get-training-paces` (osobny deploy na Fly,
dlatego kopia, nie import).
"""
from __future__ import annotations
import math

from planner.methodology import VDOT_CAL_OFFSET

PACES_TABLE = {
    30: {"E_min": 480, "E_max": 540, "M": 420, "T": 385, "I": 355, "R": 320},
    35: {"E_min": 435, "E_max": 495, "M": 385, "T": 355, "I": 325, "R": 290},
    40: {"E_min": 405, "E_max": 465, "M": 355, "T": 325, "I": 300, "R": 265},
    45: {"E_min": 380, "E_max": 440, "M": 330, "T": 305, "I": 280, "R": 245},
    50: {"E_min": 360, "E_max": 420, "M": 315, "T": 285, "I": 260, "R": 230},
    55: {"E_min": 340, "E_max": 400, "M": 295, "T": 270, "I": 245, "R": 215},
    60: {"E_min": 325, "E_max": 385, "M": 280, "T": 255, "I": 230, "R": 205},
    65: {"E_min": 310, "E_max": 370, "M": 265, "T": 240, "I": 220, "R": 195},
}

# PACE RANGE RULE (MCP): easy/long ≥20 s/km rozstępu, T/I wąsko 10 s/km.
NARROW_SPREAD = 10
WIDE_SPREAD = 20
EASY_SPREAD = 30


def training_paces(vdot: float) -> dict[str, int]:
    """Tempa (s/km) dla VDOT — interpolacja liniowa w tabeli, clamp 30..65."""
    v = max(30.0, min(65.0, float(vdot)))
    lo = int(v // 5) * 5
    hi = min(65, lo + 5)
    if lo == hi:
        return dict(PACES_TABLE[lo])
    a = (v - lo) / (hi - lo)
    p_lo, p_hi = PACES_TABLE[lo], PACES_TABLE[hi]
    return {k: round(p_lo[k] + a * (p_hi[k] - p_lo[k])) for k in p_lo}


def pace_range(kind: str, paces: dict[str, int]) -> tuple[int, int]:
    """(min, max) s/km dla rodzaju biegu. min = szybsze tempo."""
    if kind in ("E", "S"):  # środek tabelowego E, rozstęp 30 s (PACE RANGE RULE 20-40)
        lo = paces["E_min"] + 15
        return lo, lo + EASY_SPREAD
    if kind == "L":  # long: środkowa część E
        lo = (paces["E_min"] + paces["E_max"]) // 2 - 10
        return lo, lo + 25
    if kind == "RECOVERY":
        return paces["E_max"], paces["E_max"] + 30
    if kind == "M":
        return paces["M"] - 5, paces["M"] + 15
    center = paces[kind]
    return center - NARROW_SPREAD // 2, center + NARROW_SPREAD // 2


def fmt_pace(sec: int) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def pace_note(lo: int, hi: int) -> str:
    """Format wymagany przez PACE RANGE RULE: `Tempo: M:SS-M:SS/km`."""
    return f"Tempo: {fmt_pace(lo)}-{fmt_pace(hi)}/km"


# ============================================
# Daniels & Gilbert — predyktor czasu i odwrotność
# ============================================

def _pct_vo2max(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def _vo2(v_m_per_min: float) -> float:
    return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min ** 2


def vdot_from_time(distance_m: float, time_sec: float) -> float:
    """VDOT (skala projektu) z wyniku na dystansie."""
    t_min = time_sec / 60.0
    return _vo2(distance_m / t_min) / _pct_vo2max(t_min) + VDOT_CAL_OFFSET


def race_time(vdot: float, distance_m: float) -> int:
    """Przewidywany czas (s) dla VDOT (skala projektu) — bisekcja."""
    target = vdot - VDOT_CAL_OFFSET
    lo, hi = 4.0, 420.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _vo2(distance_m / mid) / _pct_vo2max(mid) > target:
            lo = mid
        else:
            hi = mid
    return int(round((lo + hi) / 2 * 60))
