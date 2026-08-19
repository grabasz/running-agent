Update `volume_log.md` with weekly mileage from Strava **and save to DB** (`weekly_volume`).

**Output language:** Polish (user is Polish, per CLAUDE.md).

**STEP 1** — run the script:
```
python scripts/volume.py
```

The script:
1. Fetches 13 weeks of activities from the Strava API (shared auth with strava-mcp)
2. Aggregates weekly (Monday-anchored)
3. Overwrites `volume_log.md` (km, elev, time, run count, longest, trend)
4. **Upserts to `db.weekly_volume`** (stderr: `<!-- saved N weeks to DB.weekly_volume -->`)

Stdout is one line: `Zapisano N tygodni → volume_log.md (avg X km/tydzień)`.

**STEP 2** — display the result:
Read `volume_log.md` and show the table to the user. Add 1-2 sentences of context: weekly average, peak week, any trend (peak/recovery).

**STEP 3 (optional)** — historical questions go straight to the DB, no re-fetch:
```python
import sys; sys.path.insert(0, "db"); import api
with api.connect() as conn:
    rows = list(api.weekly_volume.recent(conn, weeks=14))
    # or: api.weekly_volume.avg_last_n_weeks(conn, weeks=4)
```

**STEP 4 — Writes go direct to Turso (since 2026-08-19, PR #40)**

`api.connect()` uses libsql direct → Turso (auto-loads `db/.env`). Every write
(`api.weekly_volume.upsert`, `api.notes.add`, etc.) lands in Turso instantly.
**No `sync.py push` needed.**

Print `☁️ Turso: OK` at the end if writes completed successfully.

**DO NOT call** `python db/sync.py push` — sync.py is deprecated for daily flow
after the 19.08 incident. It stays only for manual backup / disaster recovery.

**STEP 5** — timing:
```
python -m db.cli perf-recent --minutes=3 --label=volume
```
