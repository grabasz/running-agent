#!/usr/bin/env python3
"""
run.py — Strava run analysis end-to-end.

Fetches the latest Run from Strava, computes elevation per km from streams,
and prints a ready-to-paste markdown table to stdout.

Auth: reads from ~/.config/strava-mcp/config.json (shared with strava-mcp server).
Auto-refreshes access token if expired and writes back to the same config —
so MCP server picks up the refreshed token transparently.

Optional CLI arg: activity ID (otherwise picks latest Run).
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# Use the OS certificate store (Windows/macOS) for HTTPS verification.
# Avoids the "unable to get local issuer certificate" pitfall on miniconda
# Windows installs where Python ships with a stale/missing CA bundle.
import truststore
truststore.inject_into_ssl()

import requests  # noqa: E402  (must follow truststore.inject)

STRAVA_API = "https://www.strava.com/api/v3"
OAUTH_URL = "https://www.strava.com/oauth/token"
CONFIG_PATH = Path.home() / ".config" / "strava-mcp" / "config.json"

SESSION = requests.Session()

PL_WEEKDAYS = [
    "poniedziałek", "wtorek", "środa", "czwartek",
    "piątek", "sobota", "niedziela",
]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_access_token():
    cfg = load_config()
    # Refresh if expired or within 5 minutes of expiring
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


def api_get(token, path, params=None):
    r = SESSION.get(
        f"{STRAVA_API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def find_last_run(token):
    activities = api_get(token, "/athlete/activities", {"per_page": 10})
    for a in activities:
        if a.get("type") == "Run" or a.get("sport_type") == "Run":
            return a["id"]
    raise RuntimeError("No Run activity in last 10 activities")


def fetch_streams(token, aid):
    data = api_get(token, f"/activities/{aid}/streams", {
        "keys": "distance,altitude",
        "key_by_type": "true",
    })
    return {
        "distance": data["distance"]["data"],
        "altitude": data["altitude"]["data"],
    }


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


def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


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


def build_table(details, laps, streams):
    elev = elev_per_km(streams["distance"], streams["altitude"])
    real_laps = [lap for lap in laps if lap.get("distance", 0) >= 200]

    # Highlights
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
        if lap["elapsed_time"] - lap["moving_time"] > 60:
            continue
        valid.append((i, paces_s[i]))

    fastest_i = min(valid, key=lambda x: x[1])[0] if valid else None
    slowest_i = max(valid, key=lambda x: x[1])[0] if valid else None

    hrs = [round(lap.get("average_heartrate") or 0) for lap in real_laps]
    hr_peak_i = hrs.index(max(hrs)) if hrs and max(hrs) > 0 else None

    cads_pairs = [(i, c) for i, c in enumerate(
        lap.get("average_cadence") or 0 for lap in real_laps
    ) if c > 0]
    cad_min_i = min(cads_pairs, key=lambda x: x[1])[0] if cads_pairs else None

    # Date/weekday
    date = datetime.fromisoformat(details["start_date_local"].replace("Z", ""))
    weekday_pl = PL_WEEKDAYS[date.weekday()]
    date_str = date.strftime("%d.%m.%Y")

    out = []
    out.append(f"🏃 {details['name']} — {weekday_pl} {date_str}")
    out.append("")
    out.append(f"| 📏 Dystans   | {details['distance']/1000:.2f} km |")
    pace = parse_pace(details["moving_time"], details["distance"])
    out.append(f"| ⚡ Tempo śr. | {pace}/km |")
    moving = format_duration(details["moving_time"])
    elapsed = format_duration(details["elapsed_time"])
    out.append(f"| ⏱️ Czas      | {moving} moving / {elapsed} łącznie |")
    out.append(f"| 💓 HR śr.    | {round(details.get('average_heartrate') or 0)} bpm |")
    out.append(f"| 📈 Wznos.    | +{int(details.get('total_elevation_gain') or 0)}m łącznie |")
    out.append("| 🏷️ Typ       | <DOPISZ na podstawie planu> |")
    out.append("")

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

    return "\n".join(out)


def main():
    token = get_access_token()

    if len(sys.argv) > 1:
        aid = int(sys.argv[1])
    else:
        aid = find_last_run(token)

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_det = ex.submit(api_get, token, f"/activities/{aid}")
        f_laps = ex.submit(api_get, token, f"/activities/{aid}/laps")
        f_streams = ex.submit(fetch_streams, token, aid)
        details = f_det.result()
        laps = f_laps.result()
        streams = f_streams.result()

    print(build_table(details, laps, streams))

    # Save to DB (errors -> stderr to keep stdout clean for Claude)
    try:
        from strava_save import save_strava_run
        run_id = save_strava_run(details, laps, streams)
        print(f"\n<!-- saved to DB: run_id={run_id} (source=strava) -->", file=sys.stderr)
    except Exception as e:
        print(f"\n<!-- DB save failed: {e} -->", file=sys.stderr)


if __name__ == "__main__":
    main()
