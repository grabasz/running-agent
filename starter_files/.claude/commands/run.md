Show the latest run as a table and **save it to DB**.

**Garmin primary** (with running dynamics: GCT, vertical oscillation, stride length, training effect, VO₂max). **Strava fallback** when the Garmin token has expired.

**Output language:** Polish (user is Polish, per CLAUDE.md).

---

## STEP 1 — Fetch the run

### 1A. Try Garmin (preferred — has running dynamics)

0. **Pre-flight:** invoke `/garmin-refresh` (silent path if session OK — ~1s; auto-refresh cookies via open Playwright if 401 — ~5s). Only falls back to interactive login when the browser session itself is dead.
0b. **Cache check:** `python -m db.cli garmin-cache --format=json` — exit code 0 = cache hit (age <10 min), pick the newest `running` activity by `startTimeLocal` from cached list. Skip STEP 1 entirely. Exit 2 = miss → continue.
1. `mcp__garmin__list-activities` with `limit: 10` — **also write the result to cache** afterwards: save array to `db/_tmp_activities.json` then `python -m db.cli garmin-cache --write --stdin-file=db/_tmp_activities.json`. That way `/gym` or `/analyze` in the same conversation reuse the fetch.
2. **Find the first element** where `activityType.typeKey == "running"` (skip e_bike, swim, strength). Remember its `activityId`.
3. `mcp__garmin__get-activity-splits` with the `activityId` from step 2.
4. Build the JSON bundle: `{"activity": <element from list-activities>, "splits": <response from get-activity-splits>}`
5. **Save** the bundle to `db/_tmp_garmin.json` (Write tool)
6. **Run**: `python scripts/garmin_save.py db/_tmp_garmin.json`
7. The script writes to DB (`runs` + `run_laps` with running dynamics) and prints a ready-to-paste markdown table — **paste the output 1:1** below.

**If `mcp__garmin__list-activities` returns 401 / "session expired"** → jump to **1B**.

### 1B. Strava fallback (when Garmin isn't available)

```
python scripts/run.py
```
Optionally: `python scripts/run.py <activity_id>` for a specific run.

The script auto-saves to DB (`source='strava'`, without running dynamics) and prints a markdown table.

---

## STEP 2 — Paste the table + adjust two things

**Paste the script output 1:1** (it already includes `🏷️ Typ` from auto-classification in the header — correct it if wrong). Then:

1. **Verify the Typ** in the header (auto-classification can miss) — `Easy` / `Tempo` / `Interwały` / `Wyścig` / `Long` / `Recovery` / `Shakeout`. If you change it → `UPDATE runs SET type='...' WHERE id=<run_id>`.

2. **Replace the markers** (🔥 / 🐢 / 💓 / 📉 / ⛰️ / ⏸️ / ⚖️) in the comment column with short coach observations (6-8 words). The marker only signals WHERE to comment.

**Leave the remaining kms without a comment.** Don't invent comments for average kms.

### Auto-markers
- 🔥 fastest / 🐢 slowest
- 💓 HR peak
- 📉 form dip (lowest cadence)
- ⛰️ climb +Xm
- ⏸️ stop ~Xmin (Strava only — Garmin doesn't detect pauses)
- **⚖️ L/R asymmetry** (when GCT balance deviates >0.7% from 50%) — **NEW for Garmin**

### Comment guidelines
A comment is an observation, not a joke. Pace + HR + climb + (for Garmin) dynamics.
- HR climbs, pace holds → "serce pracuje, nogi stoją"
- Fast km after a downhill → "zjazd skasowany z głową"
- Slower km on a climb → "podbieg wziął swoje"
- L/R asymmetry growing → "prawa noga przejmuje pod zmęczeniem"
- Shorter GCT + longer stride → "forma elite-like po pauzie"
- Max 6-8 words, coach tone, concrete.

No text before the table.

---

## STEP 3 — SUMMARY (races only)

For `Easy` / `Tempo` / `Interwały` / `Long` / `Recovery` / `Shakeout` — **skip**.

Load `fitness.md` and `races.md` (if not in context). Write `## 📋 Analiza wyścigu`:

**✅ Co poszło bardzo dobrze** — at least 4 observations backed by laps/splits data.

**🔧 Co warto rozważyć** — at least 3 points referencing upcoming starts. Specific km, HR, pace. Close with one sentence tying the analysis to the season.

---

## STEP 4 — FILE UPDATES (races only, after STEP 3)

Compute VDOT from time and distance. Compare with `fitness.md`.

**If the new T-pace is >5s/km faster:**

1. Update `fitness.md` (Edit): VDOT + date + all zones + Historia progu + Race Predictors
2. If PB — update `profile.md` in the `## PB` section
3. Plus in DB (SQL inline — no CLI wrapper yet): `INSERT INTO vdot_history` and `UPDATE races SET actual_time_sec=..., is_pb=1`
4. Print:
```
📝 Zaktualizowano:
- fitness.md: VDOT [stary] → [nowy], T-pace [stary] → [nowy]
- profile.md: PB HM [stary] → [nowy]  ← tylko jeśli PB
- DB: vdot_history +1, races UPDATE PB
```

**If the difference is ≤5s/km:**
`ℹ️ Forma potwierdzona, próg bez zmian (różnica <5s/km — poniżej progu aktualizacji).`

---

## STEP 5 — Cleanup (optional)

After use, delete `db/_tmp_garmin.json` (Bash: `rm db/_tmp_garmin.json` or Filesystem MCP).

---

## STEP 6 — Push to Turso (MANDATORY, at the end)

Always after a DB write — no user prompt:

```
python db/sync.py push --after=run
```

The `--after=run` preset pushes only touched tables (runs, run_laps, planned_workouts, planned_workout_components) — ~1-2s instead of ~5-8s for full sync.

At the end print briefly: `☁️ Turso: OK` (or the error + note that local changes remain for retry).

Same applies to `mark_status` on `planned_workouts` (auto-link from a saved run / status update). Goal: mobile / dashboard stay current without reminders.

### ⚠️ Bugfix: notes/tasks/weekly_goals require a SECOND push

**The `run` preset does NOT include `notes`, `tasks`, `weekly_goals`** — those are in the `life` preset. Historical bug (2026-07-14): notes written from the /run analysis got stuck in local SQLite because only `--after=run` was pushed. Dashboard (which reads from Turso replica) showed nothing.

**Rule:** if during this /run flow you also wrote to `notes` (e.g. saved insights linked to `run_id` via `api.notes.add()`), or touched `tasks` / `weekly_goals`, run a **second push right after the run one**:

```
python db/sync.py push --after=life
```

Both pushes are safe to run back-to-back (~1-2s each). Signal both in the final line: `☁️ Turso: OK (run + life)`. If only run was touched, keep the original single push and print `☁️ Turso: OK`.

---

## STEP 7 — Print timing summary (end of every /run)

Right before finishing the response, run:
```
python -m db.cli perf-recent --minutes=5 --label=run
```

Print the resulting `⏱️` line as the very last line of the response so the user sees how much backend time this skill cost.
