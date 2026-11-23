"""Dawki tygodnia: długość longa i sesje jakościowe (metodyka → liczby)."""
from __future__ import annotations

from planner import methodology as M


def long_km(target_km: float, distance_km: float, long_pace_sec: int,
             cap_km: float | None = None) -> float:
    marathon = distance_km > 22.0
    if marathon:
        pct, max_min = M.LONG_PCT_MARATHON, M.LONG_MAX_MIN_MARATHON
    else:
        pct = M.LONG_PCT_LOW_VOLUME if target_km < M.LOW_VOLUME_KM else M.LONG_PCT
        max_min = M.LONG_MAX_MIN
    cap_time = max_min * 60 / long_pace_sec
    cap_dist = M.by_distance(M.LONG_MAX_KM, distance_km)
    if cap_km:
        cap_dist = min(cap_dist, cap_km)
    return round(min(target_km * pct, cap_time, cap_dist), 1)


def quality(phase: str, family: str, target_km: float, deload: bool, race_week: bool) -> list[dict]:
    if race_week:
        return []
    kinds = M.QUALITY_BY_PHASE[phase][family]
    if deload or phase == M.PHASE_TAPER:
        kinds = kinds[:1]
    out = []
    for kind in kinds:
        if kind == "S":
            out.append({"kind": "S", "km": 0.0})
            continue
        pct_cap, km_cap = M.QUALITY_CAPS[kind]
        km = min(M.QUALITY_SHARE[kind] * target_km, pct_cap * target_km, km_cap)
        out.append({"kind": kind, "km": round(km, 1)})
    return out
