Update volume_log.md with weekly running mileage from Strava.

**STEP 1** — run the script:
```
python scripts/volume.py
```

The script pulls 13 weeks of activities directly from the Strava API (shared auth with strava-mcp via `~/.config/strava-mcp/config.json` — refresh tokens get written back so MCP stays in sync), aggregates by Monday-anchored week, and overwrites `volume_log.md`. Columns: km, elevation gain (real values, not zeros!), time, run count, longest run, trend (recovery/peak).

Script output is one line: `Zapisano N tygodni → volume_log.md (avg X km/tydzień)`.

**STEP 2** — show the result:
Read `volume_log.md` and display the table. Add 1-2 sentences of commentary: weekly average, peak week, any trend.
