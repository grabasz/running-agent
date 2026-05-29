Show the last Strava run as a table. Execute EXACTLY these steps in order:

**STEP 1** — get list:
`strava:get-recent-activities` (perPage: 5) → find the last activity of type Run (ignore Walk/Ride/Hike).

**STEP 2 — details + laps + streams IN PARALLEL** (all use the ID from step 1, fire simultaneously in one message):
- `strava:get-activity-details` for the ID from step 1
- `strava:get-activity-laps` for the ID from step 1
- `strava:get-activity-streams` with parameters:
  - streamTypes: ["distance", "altitude"]
  - format: "compact"
  - resolution: "medium"  ← ~1000 points, ~27 pts/km accuracy even on a marathon
  - points_per_page: 1000  ← CRITICAL: forces 1 page instead of 10 (16KB response fits in single chunk)

**STEP 3** — calculate elevation per km:
From the streams response take the `data` field (contains `{"distance":[...],"altitude":[...]}`).
Save the **entire `data` field as JSON** to `scripts/streams_tmp.json` via the Write tool.
Run:
```
python elev_per_km.py scripts/streams_tmp.json
```
After using the output, delete `scripts/streams_tmp.json` (Bash `del` or PowerShell `Remove-Item`).
Use the output as elevation per km values.

(Rationale: passing 1000 points via bash CLI args fails on Windows due to ~8KB arg limit. Reading from a file path bypasses this entirely and keeps full resolution.)

**STEP 4** — OUTPUT. Copy this format EXACTLY (replace values in brackets).
Output labels in the user's language from profile.md. No text before the table.

🏃 [activity name] — [weekday] [DD.MM.YYYY]
| 📏 Distance  | [X.XX km]                         |
| ⚡ Avg pace  | [X:XX/km]                         |
| ⏱️ Time      | [HH:MM:SS]                        |
| 💓 Avg HR    | [XXX bpm]                         |
| 📈 Elevation | [+Xm total]                       |
| 🏷️ Type      | [Easy / Tempo / Intervals / Race] |

Cadence from laps (`average_cadence`) is one-side — ALWAYS multiply ×2 before displaying (e.g. Strava 87.5 → show 175 spm).
Power (`average_watts`) from laps, no conversion.

| km | pace  | HR  | cad  | pwr   | elev       | comment                     |
|----|-------|-----|------|-------|-----------|-----------------------------|
| 1  | X:XX  | XXX | XXX  | XXX W | +Xm / -Xm | [comment — see guidelines]  |
[...every km separately, never group...]

**Per-km comment guidelines — IMPORTANT:**
A COACHING OBSERVATION — not wordplay or empty metaphor.
Write what is actually happening in that km based on pace + HR + elevation.
- HR rising, pace holding → "heart working, legs holding" / "HR climbing, pace defending"
- Fast km after descent → "descent cashed in" / "gravity contributed"
- Slower km on climb → "hill took its toll" / "pace drops, HR rises"
- Unexplained dip → "brief energy dip" / "one-off low"
- Late acceleration → "race mode on" / "engine firing"
- Consistent series → "textbook rhythm" / "like clockwork"
- Fastest km → "peak of the day" / "all in"
Do NOT write wordplay, empty metaphors, or excessive exclamation marks.
Max 6–8 words. Tone: direct, observational, like talking to the runner right after the finish line.

**STEP 5** — RACE SUMMARY (only for Race type; skip for Easy/Tempo/Intervals):

Before writing, load `fitness.md` and `races.md` (if not already read this session).

Write a `## 📋 Race analysis` section with two parts:

**✅ What went very well** — minimum 4 specific observations backed by lap/split data. Factual but energetic. Don't state the obvious.

**🔧 What to consider** — minimum 3 specific points referencing upcoming races or the training plan. Name a specific km, HR, or pace. End with one sentence tying it to the season.

**STEP 6** — UPDATE CONTEXT FILES (only for Race; execute after STEP 5):

Calculate VDOT from result time and distance. Compare with current VDOT from `fitness.md`.

**If new T-pace is faster by >5s/km than current in `fitness.md`:**

1. Update `fitness.md` via **Edit** — replace:
   - Line with VDOT and update date
   - All zones: E-pace, M-pace, T-pace, I-pace, R-pace
   - Add entry to threshold history section (new line at end)
   - Update Race Predictors if section exists

2. If result is a new PB for that distance — update `profile.md` via **Edit**:
   - Replace the relevant line in the `## PB` section

3. After editing, display:
```
📝 Updated:
- fitness.md: VDOT [old] → [new], T-pace [old] → [new]
- profile.md: PB HM [old] → [new]  ← only if PB
```

**If T-pace difference ≤5s/km** — do not edit, write one line:
`ℹ️ Form confirmed, threshold unchanged (difference <5s/km — below update threshold).`
