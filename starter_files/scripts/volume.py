#!/usr/bin/env python3
"""
volume.py — weekly running volume from Strava → volume_log.md.

Fetches the last 13 weeks of activities directly from Strava, aggregates by
week (Monday-anchored), and writes the result to `../volume_log.md`.

Auth: shared with strava-mcp via `~/.config/strava-mcp/config.json`
(refresh tokens get written back so MCP stays in sync).
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Use the OS certificate store. Avoids the broken CA bundle path that
# miniconda ships with on Windows.
import truststore
truststore.inject_into_ssl()

import requests  # noqa: E402

STRAVA_API = "https://www.strava.com/api/v3"
OAUTH_URL = "https://www.strava.com/oauth/token"
CONFIG_PATH = Path.home() / ".config" / "strava-mcp" / "config.json"

RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun"}

SESSION = requests.Session()


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_access_token():
    cfg = load_config()
    if cfg["expiresAt"] - time.time() < 300:
        r = SESSION.post(OAUTH_URL, data={
            "client_id": cfg["clientId"],
            "client_secret": cfg["clientSecret"],
            "refresh_token": cfg["refreshToken"],
            "grant_type": "refresh_token",
        }, timeout=15)
        r.raise_for_status()
        new = r.json()
        cfg["accessToken"] = new["access_token"]
        cfg["refreshToken"] = new["refresh_token"]
        cfg["expiresAt"] = new["expires_at"]
        save_config(cfg)
    return cfg["accessToken"]


def fetch_activities_since(token, after_ts):
    activities = []
    page = 1
    while True:
        r = SESSION.get(
            f"{STRAVA_API}/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"after": after_ts, "per_page": 200, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < 200:
            break
        page += 1
    return activities


def week_monday(dt):
    return (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")


def hm(seconds):
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}h"


def main():
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=91)).timestamp())

    token = get_access_token()
    activities = fetch_activities_since(token, since_ts)

    weeks = defaultdict(
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
        print("Brak aktywności biegowych w okresie.")
        sys.exit(0)

    # Average ignoring the worst week (recovery/illness skew it down)
    all_km = sorted(d["km"] for d in weeks.values())
    avg = sum(all_km[1:]) / len(all_km[1:]) if len(all_km) > 1 else all_km[0]

    lines = [
        "# Volume Log — tygodniowy kilometraż",
        f"*Aktualizacja: {datetime.now().strftime('%Y-%m-%d %H:%M')} "
        f"| Średnia (bez najsłabszego tygodnia): **{avg:.1f} km/tydzień***",
        "",
        "| Tydzień (pon) |    km  |   wzn. |  czas  | biegi | najdłuższy |  trend  |",
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
        f"*Tygodni: {len(weeks)} | Łącznie w okresie: {total:.0f} km*",
    ]

    out_path = Path(__file__).parent.parent / "volume_log.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Zapisano {len(weeks)} tygodni → {out_path.name}  (avg {avg:.1f} km/tydzień)")


if __name__ == "__main__":
    main()
