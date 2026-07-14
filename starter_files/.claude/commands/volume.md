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

**STEP 4 — Push to Turso (MANDATORY)**

After DB write, no prompt:
```
python db/sync.py push --after=volume
```
Print `☁️ Turso: OK` (or the error).

### ⚠️ Bugfix: notes/tasks/weekly_goals require a SECOND push

**The `volume` preset does NOT include `notes`, `tasks`, `weekly_goals`** — those are in the `life` preset. Historical bug (2026-07-14 on `/run`): insights written from analysis got stuck in local SQLite because only `--after=volume` was pushed. Dashboard (which reads from Turso replica) showed nothing.

**Rule:** if during this /volume flow you also wrote to `notes` (e.g. saved an insight about a volume trend via `api.notes.add()`), or touched `tasks` / `weekly_goals`, run a **second push right after the volume one**:

```
python db/sync.py push --after=life
```

Both pushes are safe to run back-to-back (~1-2s each). Signal both in the final line: `☁️ Turso: OK (volume + life)`. If only volume was touched, keep the original single push and print `☁️ Turso: OK`.

**STEP 5** — timing:
```
python -m db.cli perf-recent --minutes=3 --label=volume
```
