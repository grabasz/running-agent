# SKILLS ACTIVITY — Strava activity analysis

> Load when: last run, splits, laps, streams, HR, pace, race result.
> For "show last run" → always read `.claude/commands/bieg.md` first.

## Analysis depth (conditional)
1. ALWAYS first: `strava:get-activity-details`
2. Decide by activity type:
   - **Walk / Ride / Hike** → stop, no further calls.
   - **Run easy < 5km / shakeout** → + laps.
   - **Run quality / race / long** → + laps + streams (`format: compact`, `resolution: low`).
3. Strava cadence = one-side → **×2** before displaying (e.g. Strava 87 → 174 spm).
4. Elevation per km only when streams fetched → `python elev_per_km.py`.
5. After T/I/race → check if threshold shifted >5s/km from T-pace in `fitness.md` → update.

## Threshold tracking
Entry format in `fitness.md`: `DATE: X:XX/km @ Y bpm (VDOT~Z) — context`
Shift >5s/km vs current T-pace → recompute VDOT + all zones + Race Predictors.

## Display format — use EXACTLY this layout, no deviations
Output labels in the user's language from `profile.md → Preferred language`.

Single run:
```
🏃 [Activity name] — [Weekday] [DD.MM.YYYY]
| 📏 Distance  | X.XX km                          |
| ⚡ Avg pace  | X:XX/km                          |
| ⏱️ Time      | HH:MM:SS                         |
| 💓 Avg HR    | XXX bpm                          |
| 📈 Elevation | +Xm                              |
| 🏷️ Type      | Easy / Tempo / Intervals / Race  |
```

Laps — every km separately, never group:
```
| km | pace  | HR  | elev      |
|----|-------|-----|-----------|
|  1 | X:XX  | XXX | +Xm / -Xm |
```

- Elevation per km = from altitude stream (`+Xm / -Xm`), NOT from lap's `total_elevation_gain`.
- If streams not fetched → show total `+Xm` in header only, no elevation column.
- Weekly summary: horizontal table, one row per activity.
