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
  - points_per_page: 1000  ← CRITICAL: forces 1 page instead of 10

**STEP 3** — build `scripts/run_data.json` via Write tool with this exact shape:
```json
{
  "details_text": "<entire text response from get-activity-details, as a single JSON string>",
  "laps": [<the Complete Lap Data array from get-activity-laps>],
  "streams_data": {"distance":[...], "altitude":[...]}  ← the "data" field from streams
}
```

**STEP 4** — run the script:
```
python scripts/run_table.py scripts/run_data.json
```
The script auto-deletes the input file after reading. Output is a ready-to-paste markdown table with:
- Header (Distance / Avg pace / Time / Avg HR / Elevation)
- Full km-by-km table with auto-bold (fastest, slowest, HR peak, cadence dip)
- Auto-markers in the comment column: 🔥 fastest, 🐢 slowest, 💓 HR peak, 📉 form dip, ⛰️ climb +Xm, ⏸️ stop ~Xmin

**STEP 5** — show the script output and replace markers with coaching comments:

1. **Show output 1:1** — the full markdown table.
2. **Add the Type row** in the header: `| 🏷️ Type | Easy / Tempo / Intervals / Race |` — pick based on pace, HR, and context from `plan_current.md`.
3. **Replace markers** (🔥 / 🐢 / 💓 / 📉 / ⛰️ / ⏸️) in the comment column with short coaching observations (6–8 words). The marker only tells you WHERE to comment, not what to write.
4. **Leave other km empty** — do not invent comments for steady-state km. Most easy-run km are "steady rhythm" — writing that 30 times is wasted output.

**Comment guidelines — IMPORTANT:**
A COACHING OBSERVATION — not wordplay or empty metaphor. Write what is actually happening in that km based on pace + HR + elevation.
- HR rising, pace holding → "heart working, legs holding"
- Fast km after descent → "descent cashed in"
- Slower km on climb → "hill took its toll"
- Late acceleration → "engine firing"
- Fastest km → "all in"
Do NOT write wordplay, empty metaphors, or excessive exclamation marks.
Max 6–8 words. Tone: direct, observational, like talking to the runner right after the finish line.

No text before the table (a brief note after is fine).

**STEP 6** — RACE SUMMARY (only for Race type; skip for Easy/Tempo/Intervals):

Before writing, load `fitness.md` and `races.md` (if not already read this session).

Write a `## 📋 Race analysis` section with two parts:

**✅ What went very well** — minimum 4 specific observations backed by lap/split data.

**🔧 What to consider** — minimum 3 specific points referencing upcoming races or the training plan. Name a specific km, HR, or pace. End with one sentence tying it to the season.

**STEP 7** — UPDATE CONTEXT FILES (only for Race; execute after STEP 6):

Calculate VDOT from result time and distance. Compare with current VDOT from `fitness.md`.

**If new T-pace is faster by >5s/km than current in `fitness.md`:**

1. Update `fitness.md` via **Edit** — replace:
   - Line with VDOT and update date
   - All zones: E-pace, M-pace, T-pace, I-pace, R-pace
   - Add entry to threshold history section
   - Update Race Predictors if section exists

2. If result is a new PB for that distance — update `profile.md` via **Edit** in the `## PB` section.

3. After editing, display:
```
📝 Updated:
- fitness.md: VDOT [old] → [new], T-pace [old] → [new]
- profile.md: PB HM [old] → [new]  ← only if PB
```

**If T-pace difference ≤5s/km** — write one line:
`ℹ️ Form confirmed, threshold unchanged (difference <5s/km — below update threshold).`
