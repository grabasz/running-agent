"""Testy pure helpers z `dashboard.helpers`.

Po refaktorze (dashboard/ package) mozemy importowac bezposrednio zamiast
kopiowac SQL. To sciezka docelowa dla kolejnych testow — kazda query po
extraction ma tu pare testow.
"""
from __future__ import annotations
import pytest

from dashboard.helpers import fmt_pace, fmt_time, monday_iso, daniels_race_time


# ============================================
# fmt_pace — sekundy/km -> "M:SS/km"
# ============================================

@pytest.mark.parametrize("sec,expected", [
    (390, "6:30/km"),
    (300, "5:00/km"),
    (0, "—"),
    (None, "—"),
    (-5, "—"),
    (60, "1:00/km"),
    (65, "1:05/km"),
])
def test_fmt_pace(sec, expected):
    assert fmt_pace(sec) == expected


# ============================================
# fmt_time — sekundy -> "H:MM:SS" lub "M:SS"
# ============================================

@pytest.mark.parametrize("sec,expected", [
    (3661, "1:01:01"),  # >1h -> HH:MM:SS
    (7200, "2:00:00"),
    (300, "5:00"),      # <1h -> M:SS
    (65, "1:05"),
    (0, "—"),
    (None, "—"),
])
def test_fmt_time(sec, expected):
    assert fmt_time(sec) == expected


# ============================================
# monday_iso — dowolna data -> pon. tygodnia
# ============================================

def test_monday_iso_from_friday():
    from datetime import date
    # Pt 2026-08-14 -> pon 2026-08-10
    assert monday_iso(date(2026, 8, 14)) == "2026-08-10"


def test_monday_iso_from_monday():
    from datetime import date
    # Pon 2026-08-24 -> ta sama data
    assert monday_iso(date(2026, 8, 24)) == "2026-08-24"


def test_monday_iso_from_sunday():
    from datetime import date
    # Nd 2026-08-23 -> pon 2026-08-17
    assert monday_iso(date(2026, 8, 23)) == "2026-08-17"


# ============================================
# daniels_race_time — bisection VO2max solver
# ============================================

def test_daniels_5km_at_vdot55():
    """Fitness.md pinuje VDOT 55 -> 5km ~20:18. Tolerancja ±30s (VDOT calibration offset)."""
    t = daniels_race_time(55, 5000)
    assert 1188 <= t <= 1248, f"Expected ~1218s (20:18), got {t}"


def test_daniels_hm_at_vdot55():
    """Fitness.md pinuje VDOT 55 -> HM ~1:33:43. Tolerancja ±60s."""
    t = daniels_race_time(55, 21097.5)
    assert 5563 <= t <= 5683, f"Expected ~5623s (1:33:43), got {t}"


def test_daniels_marathon_at_vdot55():
    """Fitness.md pinuje VDOT 55 -> M ~3:15:28. Tolerancja ±60s."""
    t = daniels_race_time(55, 42195)
    assert 11668 <= t <= 11788, f"Expected ~11728s (3:15:28), got {t}"


def test_daniels_higher_vdot_gives_faster_time():
    """Sanity: wyzszy VDOT -> szybszy czas HM."""
    t_55 = daniels_race_time(55, 21097.5)
    t_60 = daniels_race_time(60, 21097.5)
    assert t_60 < t_55, "Wyzszy VDOT musi dac szybszy czas"
