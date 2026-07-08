"""Map Strava API responses (details + laps) -> DB (runs + run_laps).

Garmin-only columns (running dynamics, training_effect, body_battery) stay NULL.
Strava gives basic metrics (distance, time, HR, cadence, power, elevation).

Usage: imported from `run.py` after fetching data, or standalone from JSON files.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))
import api  # type: ignore


def _classify_run_type(details: dict) -> str:
    """Heuristic run classification from Strava metrics."""
    name = (details.get("name") or "").lower()
    if "race" in name or "wyscig" in name or "hm" in name or "maraton" in name or "5km" in name:
        return "Race"
    if "shakeout" in name:
        return "Shakeout"
    dist = (details.get("distance") or 0) / 1000
    hr_avg = details.get("average_heartrate") or 0
    moving = details.get("moving_time") or 0
    pace = moving / dist if dist > 0 else 0  # sec/km

    if dist >= 14:
        return "Long"
    if pace < 270 and hr_avg > 165:
        return "Interval"
    if 270 <= pace < 320 and hr_avg > 160:
        return "Tempo"
    return "Easy"


def _elev_per_km(distance: list[float], altitude: list[float]) -> dict[int, tuple[float, float]]:
    """Return dict {km: (up_m, down_m)}."""
    if not distance:
        return {}
    total_km = int(distance[-1] / 1000) + 1
    out = {}
    for km in range(1, total_km + 1):
        start, end = (km - 1) * 1000, km * 1000
        up = down = 0.0
        prev = None
        for i, d in enumerate(distance):
            if start <= d <= end:
                if prev is not None:
                    diff = altitude[i] - altitude[prev]
                    if diff > 0: up += diff
                    elif diff < 0: down += abs(diff)
                prev = i
        out[km] = (up, down)
    return out


def save_strava_run(
    details: dict,
    laps: list[dict] | None = None,
    streams: dict | None = None,
    run_type: str | None = None,
) -> int:
    """Save Strava run to DB. Returns run_id."""
    sid = details["id"]
    dist_km = (details.get("distance") or 0) / 1000
    moving_sec = int(details.get("moving_time") or 0)
    elapsed_sec = int(details.get("elapsed_time") or 0)
    pace = int(round(moving_sec / dist_km)) if dist_km > 0 else None

    # Date + time-of-day from start_date_local ("YYYY-MM-DDTHH:MM:SSZ" — Z is misleading, it's LOCAL time)
    start_local = details.get("start_date_local", "")
    parts = start_local.split("T", 1) if start_local else []
    date = parts[0] if parts else ""
    start_time = parts[1].rstrip("Z") if len(parts) > 1 else None

    typ = run_type or _classify_run_type(details)

    # Elev loss from streams (Strava details has only total_elevation_gain without loss)
    elev_loss = None
    if streams and streams.get("distance") and streams.get("altitude"):
        elev_map = _elev_per_km(streams["distance"], streams["altitude"])
        elev_loss = int(sum(d for _, d in elev_map.values()))

    with api.connect() as conn:
        # 0. Deduplication: check if a Garmin-sourced run for the same date+distance (±0.1km) exists.
        # If yes, just link strava_id to it and skip INSERT (Garmin data is richer — keep that record).
        existing = api.runs.find_by_date_and_distance(conn,
            date=date, distance_km=dist_km, tolerance=0.1)
        if existing and existing["source"] == "garmin" and not existing["strava_id"]:
            api.runs.link_strava_to_garmin(conn, run_id=existing["id"], strava_id=sid)
            print(f"[strava_save] dedup: linked strava_id={sid} to existing Garmin run_id={existing['id']}", file=sys.stderr)
            run_id = existing["id"]
            # Skip lap re-insert (Garmin laps are richer)
            match = api.planned.auto_link_run_for_date(conn, date=date)
            if match:
                api.planned.link_actual_run(conn, id=match["id"], run_id=run_id)
            return run_id

        # 1. UPSERT runs
        api.runs.run_upsert_strava(conn,
            strava_id=sid,
            date=date,
            start_time=start_time,
            name=details.get("name"),
            distance_km=dist_km,
            duration_sec=elapsed_sec,
            moving_sec=moving_sec,
            pace_sec_per_km=pace,
            hr_avg=int(details["average_heartrate"]) if details.get("average_heartrate") else None,
            hr_max=int(details["max_heartrate"]) if details.get("max_heartrate") else None,
            cadence_avg=int(round((details.get("average_cadence") or 0) * 2)) if details.get("average_cadence") else None,
            power_avg=int(details["average_watts"]) if details.get("average_watts") else None,
            elevation_gain_m=int(details.get("total_elevation_gain") or 0),
            elevation_loss_m=elev_loss,
            type=typ,
            notes=None,
            raw_json=json.dumps(details, ensure_ascii=False),
        )
        run_id = conn.execute("SELECT id FROM runs WHERE strava_id = ?", (sid,)).fetchone()["id"]

        # 2. Laps
        if laps:
            api.runs.delete_laps_for_run(conn, run_id=run_id)
            elev_per = _elev_per_km(streams["distance"], streams["altitude"]) if streams else {}
            for i, lap in enumerate(laps):
                if (lap.get("distance") or 0) < 200:
                    continue
                lap_dist_m = lap.get("distance") or 0
                lap_moving = lap.get("moving_time") or 0
                lap_pace = int(round(lap_moving / (lap_dist_m / 1000))) if lap_dist_m > 0 else None
                km_num = i + 1
                up, down = elev_per.get(km_num, (0, 0))
                api.runs.lap_add(conn,
                    run_id=run_id,
                    lap_num=km_num,
                    distance_km=lap_dist_m / 1000,
                    duration_sec=int(lap.get("elapsed_time") or 0),
                    pace_sec_per_km=lap_pace,
                    hr_avg=int(lap["average_heartrate"]) if lap.get("average_heartrate") else None,
                    hr_max=int(lap["max_heartrate"]) if lap.get("max_heartrate") else None,
                    cadence_avg=int(round((lap.get("average_cadence") or 0) * 2)) if lap.get("average_cadence") else None,
                    power_avg=int(lap["average_watts"]) if lap.get("average_watts") else None,
                    elev_up_m=int(round(up)),
                    elev_down_m=int(round(down)),
                    # Strava has no running dynamics
                    vertical_oscillation_cm=None,
                    ground_contact_ms=None,
                    gct_balance_left_pct=None,
                    stride_length_cm=None,
                    vertical_ratio_pct=None,
                )

        # Auto-link to planned workout for the same date (if any)
        match = api.planned.auto_link_run_for_date(conn, date=date)
        if match:
            api.planned.link_actual_run(conn, id=match["id"], run_id=run_id)

    return run_id
