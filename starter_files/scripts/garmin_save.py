"""Map Garmin Connect activity DTOs → DB rows (runs + run_laps).

Usage:
    1. From Claude Code (after fetching via mcp__garmin__*):
       - Claude collects activity (list-activities or get-activity) + splits (get-activity-splits)
       - Calls: save_run(activity_dto, splits_dto)
    2. From command line (for tests):
       python scripts/garmin_save.py <bundle.json>
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))
import api  # type: ignore


def _ms_per_m_to_sec_per_km(avg_speed_mps: float | None) -> int | None:
    """Garmin gives averageSpeed in m/s. 1000 / m/s = sec/km."""
    if not avg_speed_mps or avg_speed_mps <= 0:
        return None
    return int(round(1000 / avg_speed_mps))


def _classify_run_type(activity: dict) -> str:
    """Heuristic classification of run type from Garmin metrics."""
    name = (activity.get("activityName") or "").lower()
    if "race" in name or "wyscig" in name or "hm" in name or "maraton" in name:
        return "Race"
    if "shakeout" in name:
        return "Shakeout"
    dist = activity.get("distance", 0) / 1000  # m -> km
    hr_avg = activity.get("averageHR") or 0
    avg_speed = activity.get("averageSpeed") or 0  # m/s
    pace = 1000 / avg_speed if avg_speed > 0 else 0  # sec/km

    if dist >= 14:
        return "Long"
    if pace < 270 and hr_avg > 165:  # < 4:30/km + wysokie HR
        return "Interval"
    if 270 <= pace < 320 and hr_avg > 160:  # 4:30-5:20 + HR powyzej T
        return "Tempo"
    if hr_avg < 145:
        return "Easy"
    return "Easy"  # default


def save_run(activity: dict, splits: dict | None = None, run_type: str | None = None) -> int:
    """Save Garmin run to DB. Returns run_id.

    Args:
        activity: single element from list-activities or get-activity-details (activitySummary)
        splits: response from get-activity-splits (contains lapDTOs); optional
        run_type: override auto-classification (Easy/Tempo/Interval/Race/Long/Recovery/Shakeout)
    """
    aid = activity["activityId"]
    dist_km = (activity.get("distance") or 0) / 1000

    # 0. Deduplication: if a Strava-sourced run for same date+distance (±0.1km) exists,
    # we'll UPSERT into THAT row (keep strava_id, fill Garmin-only columns) instead of creating a new row.
    # Implemented below: after building the data dict, we either UPSERT by garmin_activity_id (normal path)
    # or UPDATE the existing Strava row to enrich it with Garmin data.
    moving_sec = int(activity.get("movingDuration") or 0)
    elapsed_sec = int(activity.get("elapsedDuration") or activity.get("duration") or 0)
    avg_speed = activity.get("averageSpeed") or 0
    pace = _ms_per_m_to_sec_per_km(avg_speed)

    # ISO date from startTimeLocal
    start_local = activity.get("startTimeLocal", "")
    date = start_local.split(" ")[0] if start_local else ""

    typ = run_type or _classify_run_type(activity)

    with api.connect() as conn:
        # 0. Deduplication: if a Strava-sourced run for same date+distance (±0.1km) exists
        # and has no garmin_activity_id yet, hijack it: set garmin_activity_id+source='garmin'
        # so the UPSERT below targets that row and enriches it with Garmin-only columns
        # (running dynamics, training effect, body battery, etc.) — keeping the strava_id intact.
        existing = api.runs.find_by_date_and_distance(conn,
            date=date, distance_km=dist_km, tolerance=0.1)
        if existing and existing["source"] == "strava" and not existing["garmin_activity_id"]:
            conn.execute(
                "UPDATE runs SET garmin_activity_id = ?, source = 'garmin' WHERE id = ?",
                (aid, existing["id"])
            )
            print(f"[garmin_save] dedup: merging Garmin data into existing Strava run_id={existing['id']}", file=sys.stderr)

        # 1. UPSERT runs
        run_id = api.runs.run_upsert_garmin(conn,
            garmin_activity_id=aid,
            date=date,
            name=activity.get("activityName"),
            distance_km=dist_km,
            duration_sec=elapsed_sec,
            moving_sec=moving_sec,
            pace_sec_per_km=pace,
            hr_avg=int(activity["averageHR"]) if activity.get("averageHR") else None,
            hr_max=int(activity["maxHR"]) if activity.get("maxHR") else None,
            cadence_avg=int(activity["averageRunningCadenceInStepsPerMinute"])
                        if activity.get("averageRunningCadenceInStepsPerMinute") else None,
            power_avg=activity.get("avgPower"),
            power_max=activity.get("maxPower"),
            power_norm=activity.get("normPower"),
            elevation_gain_m=int(activity.get("elevationGain") or 0),
            elevation_loss_m=int(activity.get("elevationLoss") or 0),
            vertical_oscillation_cm=activity.get("avgVerticalOscillation"),
            ground_contact_ms=int(activity["avgGroundContactTime"])
                              if activity.get("avgGroundContactTime") else None,
            gct_balance_left_pct=activity.get("avgGroundContactBalance"),
            stride_length_cm=activity.get("avgStrideLength"),
            vertical_ratio_pct=activity.get("avgVerticalRatio"),
            training_effect_aerobic=activity.get("aerobicTrainingEffect"),
            training_effect_anaerobic=activity.get("anaerobicTrainingEffect"),
            training_load=activity.get("activityTrainingLoad"),
            recovery_time_hours=None,  # not in activity summary, only via get-training-readiness
            body_battery_start=None,
            body_battery_end=None,
            vo2max_at_activity=activity.get("vO2MaxValue"),
            hr_time_z1_sec=int(activity.get("hrTimeInZone_1") or 0),
            hr_time_z2_sec=int(activity.get("hrTimeInZone_2") or 0),
            hr_time_z3_sec=int(activity.get("hrTimeInZone_3") or 0),
            hr_time_z4_sec=int(activity.get("hrTimeInZone_4") or 0),
            hr_time_z5_sec=int(activity.get("hrTimeInZone_5") or 0),
            type=typ,
            notes=None,
            raw_json=json.dumps(activity, ensure_ascii=False),
        )

        # SQLite ON CONFLICT DO UPDATE doesn't return lastrowid on update path.
        # Look up id via garmin_activity_id.
        row = conn.execute("SELECT id FROM runs WHERE garmin_activity_id = ?", (aid,)).fetchone()
        run_id = row["id"]

        # 2. Laps (if splits provided)
        if splits and splits.get("lapDTOs"):
            api.runs.delete_laps_for_run(conn, run_id=run_id)
            for lap in splits["lapDTOs"]:
                lap_speed = lap.get("averageSpeed") or 0
                lap_pace = _ms_per_m_to_sec_per_km(lap_speed)
                api.runs.lap_add(conn,
                    run_id=run_id,
                    lap_num=lap["lapIndex"],
                    distance_km=(lap.get("distance") or 0) / 1000,
                    duration_sec=int(lap.get("duration") or 0),
                    pace_sec_per_km=lap_pace,
                    hr_avg=int(lap["averageHR"]) if lap.get("averageHR") else None,
                    hr_max=int(lap["maxHR"]) if lap.get("maxHR") else None,
                    cadence_avg=int(lap["averageRunCadence"]) if lap.get("averageRunCadence") else None,
                    power_avg=int(lap["averagePower"]) if lap.get("averagePower") else None,
                    elev_up_m=int(lap.get("elevationGain") or 0),
                    elev_down_m=int(lap.get("elevationLoss") or 0),
                    vertical_oscillation_cm=lap.get("verticalOscillation"),
                    ground_contact_ms=int(lap["groundContactTime"]) if lap.get("groundContactTime") else None,
                    gct_balance_left_pct=lap.get("groundContactBalanceLeft"),
                    stride_length_cm=lap.get("strideLength"),
                    vertical_ratio_pct=lap.get("verticalRatio"),
                )

    # Auto-link to planned workout for the same date (if any)
    with api.connect() as conn:
        match = api.planned.auto_link_run_for_date(conn, date=date)
        if match:
            api.planned.link_actual_run(conn, id=match["id"], run_id=run_id)

    return run_id


# ============================================
# Render — prints markdown table from DB
# ============================================

PL_WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


def _fmt_pace(sec_per_km: int | None) -> str:
    if not sec_per_km:
        return "—"
    m, s = divmod(int(sec_per_km), 60)
    return f"{m}:{s:02d}"


def _fmt_duration(sec: int | None) -> str:
    if not sec:
        return "—"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def render_run_table(run_id: int) -> str:
    """Build markdown table for one run from DB (Garmin with running dynamics)."""
    import sqlite3
    sys.path.insert(0, str(ROOT / "db"))
    import api  # type: ignore

    with api.connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return f"Run {run_id} nie istnieje w DB"
        laps = list(api.runs.laps_for_run(conn, run_id=run_id))

    # Header
    from datetime import datetime
    date = datetime.fromisoformat(row["date"])
    weekday = PL_WEEKDAYS[date.weekday()]
    date_str = date.strftime("%d.%m.%Y")

    out = []
    out.append(f"🏃 {row['name']} — {weekday} {date_str}")
    out.append("")
    out.append(f"| 📏 Dystans | {row['distance_km']:.2f} km |")
    out.append(f"| ⚡ Tempo śr. | {_fmt_pace(row['pace_sec_per_km'])}/km |")
    out.append(f"| ⏱️ Czas | {_fmt_duration(row['moving_sec'])} moving / {_fmt_duration(row['duration_sec'])} łącznie |")
    out.append(f"| 💓 HR śr. / max | {row['hr_avg']} / {row['hr_max']} bpm |")
    out.append(f"| 🦵 GCT śr. | {row['ground_contact_ms']} ms |")
    out.append(f"| ⚖️ GCT bal L% | {row['gct_balance_left_pct']:.2f} |")
    out.append(f"| ↕️ VO / stride | {row['vertical_oscillation_cm']} cm / {row['stride_length_cm']} cm |")
    out.append(f"| 📈 Wznos. | +{row['elevation_gain_m']}m / -{row['elevation_loss_m']}m |")
    te_a = row['training_effect_aerobic'] or 0
    te_an = row['training_effect_anaerobic'] or 0
    out.append(f"| 🩺 Training Effect | aerobic {te_a:.1f} / anaerobic {te_an:.1f} |")
    out.append(f"| 🫁 VO₂max | {row['vo2max_at_activity']} |")
    out.append(f"| 🏷️ Typ | {row['type']} |")
    out.append("")

    # Marker calculation (fastest / slowest / HR peak / cadence min / climb)
    real_laps = [l for l in laps if (l["distance_km"] or 0) >= 0.95]
    if real_laps:
        paces = [l["pace_sec_per_km"] for l in real_laps]
        fastest_i = paces.index(min(paces))
        slowest_i = paces.index(max(paces))
        hrs = [l["hr_avg"] or 0 for l in real_laps]
        hr_peak_i = hrs.index(max(hrs))
        cads = [l["cadence_avg"] or 999 for l in real_laps]
        cad_min_i = cads.index(min(cads))
        # GCT asymmetry
        balances = [(abs((l["gct_balance_left_pct"] or 50) - 50), i) for i, l in enumerate(real_laps)]
        max_asym = max(balances) if balances else (0, None)
        asym_i = max_asym[1] if max_asym[0] > 0.7 else None
    else:
        fastest_i = slowest_i = hr_peak_i = cad_min_i = asym_i = None

    # Table
    out.append("| km | tempo | HR | kad | moc | wzn. | GCT | L% | stride | komentarz |")
    out.append("|----|-------|-----|-----|-----|------|-----|-----|--------|-----------|")
    for i, lap in enumerate(laps):
        km = lap["lap_num"]
        dist_km = lap["distance_km"] or 0
        is_real = dist_km >= 0.95
        km_label = f"{km}" if is_real else f"{km}*"
        pace = _fmt_pace(lap["pace_sec_per_km"])
        hr = lap["hr_avg"] or 0
        cad = lap["cadence_avg"] or 0
        watts = lap["power_avg"] or 0
        up = lap["elev_up_m"] or 0
        down = lap["elev_down_m"] or 0
        gct = lap["ground_contact_ms"] or 0
        bal = lap["gct_balance_left_pct"]
        stride = lap["stride_length_cm"] or 0

        # Markers (only for real_laps)
        real_idx = real_laps.index(lap) if is_real and lap in real_laps else None
        markers = []
        if real_idx == fastest_i: markers.append("🔥 najszybszy")
        if real_idx == slowest_i: markers.append("🐢 najwolniejszy")
        if real_idx == hr_peak_i: markers.append("💓 HR peak")
        if real_idx == cad_min_i: markers.append("📉 dołek formy")
        if real_idx == asym_i: markers.append(f"⚖️ asymetria L/R")
        if up > 20: markers.append(f"⛰️ podbieg +{up}m")

        pace_s = f"**{pace}**" if real_idx in (fastest_i, slowest_i) else pace
        hr_s = f"**{hr}**" if real_idx == hr_peak_i else str(hr)
        cad_s = f"**{cad}**" if real_idx == cad_min_i else str(cad)
        bal_s = f"**{bal:.2f}**" if real_idx == asym_i and bal else (f"{bal:.2f}" if bal else "—")

        out.append(
            f"| {km_label} | {pace_s} | {hr_s} | {cad_s} | {watts}W | "
            f"+{up}m/-{down}m | {gct} | {bal_s} | {stride:.1f} | {' · '.join(markers)} |"
        )

    return "\n".join(out)


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python garmin_save.py <bundle.json>", file=sys.stderr)
        print("  bundle.json format: {\"activity\": {...}, \"splits\": {...}, \"type\": \"Long\"}", file=sys.stderr)
        print("  Lub legacy: python garmin_save.py <activity.json> <splits.json> [type]", file=sys.stderr)
        sys.exit(1)

    # Mode 1: bundle JSON (one file)
    p1 = Path(sys.argv[1])
    data = json.loads(p1.read_text(encoding="utf-8"))

    if "activity" in data:
        activity = data["activity"]
        splits = data.get("splits")
        run_type = data.get("type")
    else:
        # Mode 2: legacy - separate files
        activity = data if not isinstance(data, list) else data[0]
        splits_path = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
        splits = json.loads(splits_path.read_text(encoding="utf-8")) if splits_path else None
        run_type = sys.argv[3] if len(sys.argv) > 3 else None

    if isinstance(activity, list):
        activity = activity[0]

    run_id = save_run(activity, splits, run_type)
    print(f"<!-- saved run_id={run_id} (source=garmin, activityId={activity.get('activityId')}) -->", file=sys.stderr)
    print(render_run_table(run_id))
