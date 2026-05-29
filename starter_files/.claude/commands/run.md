Show the last Strava run as a table.

**STEP 1** — run the script:
```
python scripts/run.py
```
Optional: `python scripts/run.py <activity_id>` for a specific run.

The script fetches everything from Strava itself (auto-refresh of access token, data goes straight into Python — not through Claude's context), computes elevation per km, and prints a ready-to-paste markdown table with auto-flags and markers:
- 🔥 fastest km
- 🐢 slowest km
- 💓 HR peak
- 📉 form dip (cadence)
- ⛰️ climb +Xm
- ⏸️ stop ~Xmin

Auth is shared with the strava-mcp server via `~/.config/strava-mcp/config.json` (so MCP keeps working transparently; refresh tokens stay in sync).

**STEP 2** — paste the script output 1:1 and make EXACTLY two changes:

1. **Add the Type** in the header — replace `<DOPISZ na podstawie planu>` (or its English equivalent) with: `Easy` / `Tempo` / `Intervals` / `Race` based on pace, HR, and context from `plan_current.md`. Use the user's language from `profile.md`.

2. **Replace markers** (🔥 / 🐢 / 💓 / 📉 / ⛰️ / ⏸️) in the comment column with short coaching observations (6–8 words). The marker just tells you WHERE to comment.

**Leave other km empty** — empty cell. Do not invent comments for steady-state km. Most easy-run km are "steady rhythm" — writing that 30 times is wasted output.

**Comment guidelines:**
A coaching observation, not wordplay. Write what's happening: pace + HR + elevation.
- HR rising, pace holding → "heart working, legs holding"
- Fast km after descent → "descent cashed in"
- Slower km on climb → "hill took its toll"
- Late acceleration → "engine firing"
- Fastest → "all in"
Max 6–8 words. Direct, observational tone.

No text before the table.

**STEP 3** — RACE SUMMARY (only for Race type; skip for Easy/Tempo/Intervals):

Before writing, load `fitness.md` and `races.md` (if not already read).

Write a `## 📋 Race analysis` section:

**✅ What went very well** — minimum 4 specific observations from lap/split data.

**🔧 What to consider** — minimum 3 specific points referencing upcoming races or the training plan. Name a specific km, HR, or pace. End with one sentence tying it to the season.

**STEP 4** — UPDATE CONTEXT FILES (only for Race; execute after STEP 3):

Calculate VDOT from result time and distance. Compare with `fitness.md`.

**If new T-pace is faster by >5s/km:**

1. Update `fitness.md` (Edit): VDOT + date + all zones (E/M/T/I/R) + threshold history + Race Predictors
2. If new PB — update `profile.md` in the `## PB` section
3. Display:
```
📝 Updated:
- fitness.md: VDOT [old] → [new], T-pace [old] → [new]
- profile.md: PB HM [old] → [new]  ← only if PB
```

**If difference ≤5s/km:**
`ℹ️ Form confirmed, threshold unchanged (difference <5s/km — below update threshold).`
