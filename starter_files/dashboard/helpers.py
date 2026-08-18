"""Pure helpers — formatery i race predictor Daniels & Gilbert.

Zero zaleznosci od Streamlit / DB. Testowalne bezposrednio pytestem.
"""
from __future__ import annotations
import math
from datetime import datetime, timedelta

from dashboard.constants import VDOT_CAL_OFFSET


def fmt_pace(sec) -> str:
    """Sekundy/km -> 'M:SS/km'. Zwraca '—' dla None/0."""
    if not sec or sec <= 0:
        return "—"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}/km"


def fmt_time(sec) -> str:
    """Sekundy -> 'H:MM:SS' lub 'M:SS'. Zwraca '—' dla None/0."""
    if not sec or sec <= 0:
        return "—"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def monday_iso(d=None) -> str:
    """Poniedzialek tygodnia dla podanej daty (default: dzis) jako YYYY-MM-DD."""
    d = d or datetime.now().date()
    return (d - timedelta(days=d.weekday())).isoformat()


def daniels_race_time(vdot: float, distance_m: float) -> int:
    """Predicted race time (sec) for a project-scale VDOT — Daniels & Gilbert equations.

    Solves for T where VO2(velocity) / %VO2max(T) == canonical vdot (bisection).
    """
    vdot = vdot - VDOT_CAL_OFFSET

    def pct_vo2max(t_min):
        return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)

    def vo2(v_m_per_min):
        return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min ** 2

    lo, hi = 4.0, 420.0  # minutes
    for _ in range(60):
        mid = (lo + hi) / 2
        if vo2(distance_m / mid) / pct_vo2max(mid) > vdot:
            lo = mid  # running too fast for this vdot -> need more time
        else:
            hi = mid
    return int(round((lo + hi) / 2 * 60))
