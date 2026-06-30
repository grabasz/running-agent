"""Batch-import last N days of Strava runs into the DB.

Useful to seed `runs` + `run_laps` historically without using /run one-by-one.

Usage:
    python scripts/strava_import_recent.py            # default 14 days
    python scripts/strava_import_recent.py 30         # last 30 days
"""
from __future__ import annotations
import sys
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import truststore
truststore.inject_into_ssl()
import requests  # noqa: E402

# Reuse run.py helpers
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from run import get_access_token, api_get, fetch_streams, STRAVA_API  # type: ignore
from strava_save import save_strava_run  # type: ignore


RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
SESSION = requests.Session()


def list_recent_runs(token: str, days: int) -> list[dict]:
    """List Run activities from the last `days` days."""
    after_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    activities = api_get(token, "/athlete/activities", {"after": after_ts, "per_page": 100})
    runs = [a for a in activities if (a.get("sport_type") or a.get("type", "")) in RUN_TYPES]
    return runs


def import_run(token: str, aid: int) -> dict:
    """Fetch full data for one activity and save to DB. Returns brief info."""
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_det = ex.submit(api_get, token, f"/activities/{aid}")
        f_laps = ex.submit(api_get, token, f"/activities/{aid}/laps")
        f_streams = ex.submit(fetch_streams, token, aid)
        details = f_det.result()
        laps = f_laps.result()
        streams = f_streams.result()

    run_id = save_strava_run(details, laps, streams)
    return {
        "run_id": run_id,
        "date": details.get("start_date_local", "")[:10],
        "name": details.get("name", ""),
        "distance_km": (details.get("distance") or 0) / 1000,
    }


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    print(f"[strava] fetching runs from last {days} days...")

    token = get_access_token()
    runs = list_recent_runs(token, days)
    print(f"[strava] found {len(runs)} runs\n")

    for i, a in enumerate(runs, 1):
        aid = a["id"]
        try:
            info = import_run(token, aid)
            print(f"  [{i}/{len(runs)}] run_id={info['run_id']:3} {info['date']} {info['distance_km']:5.2f}km {info['name'][:50]}")
        except Exception as e:
            print(f"  [{i}/{len(runs)}] FAIL aid={aid}: {e}")
        time.sleep(0.4)  # polite rate-limit ~150 req/15min Strava limit

    print(f"\n[done] imported {len(runs)} runs to DB.runs")


if __name__ == "__main__":
    main()
