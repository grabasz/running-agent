#!/usr/bin/env python3
"""
run_table.py — generate markdown table for a Strava run.

Input: single JSON file with three fields:
  details_text: raw string from strava:get-activity-details response
  laps: complete laps array from strava:get-activity-laps "Complete Lap Data"
  streams_data: "data" field from strava:get-activity-streams response
                ({"distance":[...],"altitude":[...]})

Prints the full table to stdout, ready to paste into the user's response.
After reading, DELETES the input file automatically (no manual cleanup needed).
"""

import json
import os
import re
import sys
from datetime import datetime

PL_WEEKDAYS = [
    "poniedziałek", "wtorek", "środa", "czwartek",
    "piątek", "sobota", "niedziela",
]


def parse_pace(moving_s, distance_m):
    if distance_m <= 0:
        return "—"
    pace_s_per_km = moving_s / (distance_m / 1000.0)
    m = int(pace_s_per_km // 60)
    s = int(round(pace_s_per_km - m * 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"


def parse_details(text):
    out = {}
    m = re.search(r"\*\*(.+?)\*\*", text)
    out["name"] = m.group(1) if m else "—"
    m = re.search(r"Date:\s*(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        out["date"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.search(r"Moving Time:\s*(\S+?),\s*Elapsed Time:\s*(\S+)", text)
    if m:
        out["moving_str"] = m.group(1)
        out["elapsed_str"] = m.group(2)
    m = re.search(r"Distance:\s*([\d.]+)\s*km", text)
    if m:
        out["distance_km"] = float(m.group(1))
    m = re.search(r"Pace:\s*([\d:]+)\s*/km", text)
    if m:
        out["pace"] = m.group(1)
    m = re.search(r"Avg Heart Rate:\s*([\d.]+)\s*bpm", text)
    if m:
        out["avg_hr"] = round(float(m.group(1)))
    m = re.search(r"Elevation Gain:\s*([\d.]+)\s*m", text)
    if m:
        out["elev_gain"] = int(round(float(m.group(1))))
    return out


def elev_per_km(distance, altitude):
    n = len(distance)
    if n == 0:
        return {}
    total_km = int(distance[-1] / 1000) + 1
    out = {}
    for km in range(1, total_km + 1):
        km_start = (km - 1) * 1000
        km_end = km * 1000
        up = 0.0
        down = 0.0
        prev_idx = None
        for i in range(n):
            if km_start <= distance[i] <= km_end:
                if prev_idx is not None:
                    diff = altitude[i] - altitude[prev_idx]
                    if diff > 0:
                        up += diff
                    elif diff < 0:
                        down += abs(diff)
                prev_idx = i
        out[km] = (up, down)
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: run_table.py <run_data.json>", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    with open(input_file, encoding="utf-8") as f:
        data = json.load(f)

    det = parse_details(data["details_text"])
    streams = data["streams_data"]
    elev = elev_per_km(streams["distance"], streams["altitude"])

    # Filter laps: drop markers and tiny segments (warm-up start, resume markers, final crumb)
    real_laps = [lap for lap in data["laps"] if lap.get("distance", 0) >= 200]

    weekday_idx = datetime.fromisoformat(det["date"]).weekday()
    weekday_pl = PL_WEEKDAYS[weekday_idx]
    date_pl = datetime.fromisoformat(det["date"]).strftime("%d.%m.%Y")

    out = []
    out.append(f"🏃 {det['name']} — {weekday_pl} {date_pl}")
    out.append("")
    out.append(f"| 📏 Dystans   | {det['distance_km']:.2f} km |")
    out.append(f"| ⚡ Tempo śr. | {det.get('pace', '—')}/km |")
    moving = det.get("moving_str", "—")
    elapsed = det.get("elapsed_str", "—")
    out.append(f"| ⏱️ Czas      | {moving} moving / {elapsed} łącznie |")
    out.append(f"| 💓 HR śr.    | {det.get('avg_hr', '—')} bpm |")
    out.append(f"| 📈 Wznos.    | +{det.get('elev_gain', 0)}m łącznie |")
    out.append("")

    # Per-lap metrics for highlights
    paces_s = []
    for lap in real_laps:
        if lap["distance"] >= 950:
            paces_s.append(lap["moving_time"] / (lap["distance"] / 1000.0))
        else:
            paces_s.append(None)

    valid = []
    for i, lap in enumerate(real_laps):
        if paces_s[i] is None:
            continue
        # Exclude laps with significant stops (would skew "slowest" detection)
        if lap["elapsed_time"] - lap["moving_time"] > 60:
            continue
        valid.append((i, paces_s[i]))

    fastest_i = min(valid, key=lambda x: x[1])[0] if valid else None
    slowest_i = max(valid, key=lambda x: x[1])[0] if valid else None

    hrs = [round(lap.get("average_heartrate") or 0) for lap in real_laps]
    hr_peak_i = hrs.index(max(hrs)) if hrs and max(hrs) > 0 else None

    cads = [(lap.get("average_cadence") or 0) for lap in real_laps]
    valid_cads = [(i, c) for i, c in enumerate(cads) if c > 0]
    cad_min_i = min(valid_cads, key=lambda x: x[1])[0] if valid_cads else None

    out.append("| km | tempo | HR  | kad | moc | wzn. | komentarz |")
    out.append("|----|-------|-----|-----|-----|------|-----------|")

    for i, lap in enumerate(real_laps):
        km_num = i + 1
        dist_m = lap["distance"]
        moving_s = lap["moving_time"]
        elapsed_s = lap["elapsed_time"]
        avg_hr = round(lap.get("average_heartrate") or 0)
        cad = round((lap.get("average_cadence") or 0) * 2)
        watts = round(lap.get("average_watts") or 0)

        pace = parse_pace(moving_s, dist_m)
        up, down = elev.get(km_num, (0, 0))
        elev_str = f"+{up:.0f}m / -{down:.0f}m"

        pace_str = f"**{pace}**" if i in (fastest_i, slowest_i) else pace
        hr_str = f"**{avg_hr}**" if i == hr_peak_i else str(avg_hr)
        cad_str = f"**{cad}**" if i == cad_min_i else str(cad)

        markers = []
        stop_min = (elapsed_s - moving_s) / 60.0
        if stop_min > 2:
            markers.append(f"⏸️ stop ~{int(round(stop_min))}min")
        if i == fastest_i:
            markers.append("🔥 najszybszy")
        if i == slowest_i:
            markers.append("🐢 najwolniejszy")
        if i == hr_peak_i:
            markers.append("💓 HR peak")
        if i == cad_min_i:
            markers.append("📉 dołek formy")
        if up > 20:
            markers.append(f"⛰️ podbieg +{up:.0f}m")

        comment = " · ".join(markers)
        km_label = f"{km_num}" if dist_m >= 950 else f"{km_num}*"

        out.append(
            f"| {km_label} | {pace_str} | {hr_str} | {cad_str} | "
            f"{watts}W | {elev_str} | {comment} |"
        )

    print("\n".join(out))

    # Auto-cleanup the temp input file (so /run doesn't leave artifacts)
    try:
        os.remove(input_file)
    except OSError:
        pass


if __name__ == "__main__":
    main()
