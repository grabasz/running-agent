#!/usr/bin/env python3
"""
weekly_volume.py — weekly mileage from Strava JSON

Usage:
    python scripts/weekly_volume.py [file.json]
    python scripts/weekly_volume.py          # reads stdin

Output: volume_log.md in project root (overwrites).

Input format: JSON array of Strava activities (fields: sport_type/type,
start_date_local, distance [m], moving_time [s], total_elevation_gain [m]).
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun"}


def week_monday(dt: datetime) -> str:
    return (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")


def hm(seconds: int) -> str:
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}h"


def main() -> None:
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            activities = json.load(f)
    else:
        activities = json.load(sys.stdin)

    weeks: dict = defaultdict(
        lambda: {"km": 0.0, "elev": 0.0, "time_s": 0, "runs": 0, "long_km": 0.0}
    )

    for a in activities:
        sport = a.get("sport_type") or a.get("type", "")
        if sport not in RUNNING_TYPES:
            continue

        raw = a.get("start_date_local") or a.get("start_date", "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", ""))
        except ValueError:
            continue

        w = week_monday(dt)
        km = (a.get("distance") or 0) / 1000
        weeks[w]["km"] += km
        weeks[w]["elev"] += a.get("total_elevation_gain") or 0
        weeks[w]["time_s"] += a.get("moving_time") or 0
        weeks[w]["runs"] += 1
        if km > weeks[w]["long_km"]:
            weeks[w]["long_km"] = km

    if not weeks:
        print("No running activities found in data.")
        sys.exit(0)

    # Average excluding the worst week (recovery/illness pulls it down)
    all_km = sorted(d["km"] for d in weeks.values())
    avg = sum(all_km[1:]) / len(all_km[1:]) if len(all_km) > 1 else all_km[0]

    lines = [
        "# Volume Log — weekly mileage",
        f"*Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} "
        f"| Average (excl. worst week): **{avg:.1f} km/week***",
        "",
        "| Week (Mon)    |    km  |   elev |  time  | runs  | longest    |  trend  |",
        "|---------------|--------|--------|--------|-------|------------|---------|",
    ]

    for w in sorted(weeks):
        d = weeks[w]
        km = d["km"]
        if km < avg * 0.75:
            trend = "↓ recovery"
        elif km > avg * 1.12:
            trend = "↑ peak"
        else:
            trend = ""
        lines.append(
            f"| {w} | {km:>6.1f} | +{d['elev']:>5.0f}m | {hm(d['time_s'])} "
            f"| {d['runs']:>5} | {d['long_km']:>8.1f}km | {trend:<7} |"
        )

    total = sum(d["km"] for d in weeks.values())
    lines += [
        "",
        f"*Weeks: {len(weeks)} | Total in period: {total:.0f} km*",
    ]

    out = Path(__file__).parent.parent / "volume_log.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {len(weeks)} weeks → {out.name}  (avg {avg:.1f} km/week)")


if __name__ == "__main__":
    main()
