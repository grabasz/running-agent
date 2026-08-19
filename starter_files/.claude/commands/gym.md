Fetch the latest strength session from Garmin, **save it to DB**, and regenerate `gym_log.md`.

**Output language:** Polish (user is Polish, per CLAUDE.md).

---

## STEP 1 — Fetch the session

### 1A. Garmin (preferred)

0. **Pre-flight:** invoke `/garmin-refresh` (silent path if session OK — ~1s; auto-refresh cookies via open Playwright if 401 — ~5s).
0b. **Cache check:** `python -m db.cli garmin-cache --format=json` — exit 0 = pick newest `strength_training` from cached list, skip STEP 1. Exit 2 = miss → continue.
1. `mcp__garmin__list-activities` with `limit: 10` — after use, write to cache: `python -m db.cli garmin-cache --write --stdin-file=db/_tmp_activities.json`.
2. Find the first element where `activityType.typeKey == "strength_training"`. Keep the **whole object** (including `summarizedExerciseSets`).
3. Save that object as JSON to `db/_tmp_silownia.json` (Write tool).
4. Run: `python scripts/silownia_save.py db/_tmp_silownia.json "<context>"` where `<context>` is a short session label (e.g. `"Silownia A + Prehab"`, `"Powrot po przerwie"`). If unsure → omit the argument.
5. The script:
   - INSERT/UPDATE into `gym_sessions` + `gym_sets` (per-set heuristic: total_reps / n_sets)
   - Regenerates `garmin_workouts/gym/gym_log.md` (last 5 sessions + Wzorzec aktualnych możliwości)
   - Prints ready-to-paste markdown — **paste the output 1:1**

**If Garmin returns 401 / fails** → go to **1B**.

### 1B. Manual entry (fallback)

No manual script — ask the user to paste the log from Garmin Connect (like the 27.06.2026 session). Build the activity JSON with `summarizedExerciseSets` by hand and run as in 1A.

---

## STEP 2 — Coach's notes

If the user mentions subjective sensations (knee, back, technique, energy) — log to `body_state`:

```
python -m db.cli log-body --date=YYYY-MM-DD --location=kolano_prawe --pain=N --notes="..."
```

Or update `notes` on specific sets:

```sql
UPDATE gym_sets SET notes = 'plan @BW, wzial 2x8kg, kontrolowal'
 WHERE session_id = <id> AND exercise = 'BSS' AND set_num = 1;
```

After such edits, run **`python scripts/silownia_save.py --render-only`** to regenerate `gym_log.md` with the new notes.

---

## STEP 3 — Progression analysis (optional, when the user asks)

The "Wzorzec aktualnych możliwości" section lives at the end of `gym_log.md`. Plus quick queries:

```
python -m db.cli exercise-prog --exercise=RDL --limit=20
```

For `top_exercises_by_volume` (not yet in CLI), inline:
```python
import sys; sys.path.insert(0, "db"); import api
with api.connect() as conn:
    for r in api.gym.top_exercises_by_volume(conn, since='2026-01-01'):
        print(dict(r))
```

---

## STEP 4 — Cleanup

```
rm db/_tmp_silownia.json
```

---

## STEP 5 — Writes go direct to Turso (since 2026-08-19, PR #40)

`api.connect()` uses libsql direct → Turso (auto-loads `db/.env`). Every write
(`api.gym.session_add`, `api.gym.set_add`, `mark_status`, `api.notes.add`, etc.)
lands in Turso instantly. **No `sync.py push` needed.**

Print `☁️ Turso: OK` at the end if writes completed successfully.

**DO NOT call** `python db/sync.py push` — sync.py is deprecated for daily flow
after the 19.08 incident. It stays only for manual backup / disaster recovery.

---

## ⚠️ Known limitations of Garmin's summarized API

- `summarizedExerciseSets` gives **per-exercise totals**, not per-set. The script divides `total_reps / n_sets` (e.g. BSS 52 reps / 3 = 17 per set, though it was actually 16+16+20).
- Some exercises without `subCategory` (e.g. CORE without DEAD_BUG) end up with a generic name ("Cwiczenia na tulow"). The user can `UPDATE` it by hand.
- Garmin returns `volume`, `duration`, `maxWeight` in grams / milliseconds — the script converts to kg / sec.
- Full per-set granularity (12+12+12 vs 36 total) would need a fetch through `get-workout` with `workoutId` — TODO for later.

---

## STEP 6 — Print timing summary

At the end:
```
python -m db.cli perf-recent --minutes=5 --label=gym
```
