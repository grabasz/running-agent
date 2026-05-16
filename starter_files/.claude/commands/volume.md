Update volume_log.md with weekly mileage from Strava. Execute EXACTLY in this order:

**STEP 1 — get today's date:**
Fetch current date from `weather:weather_forecast` (→ `current.time`).
Calculate the date 91 days ago (13 weeks) as startDate in YYYY-MM-DD format.

**STEP 2 — fetch activities:**
`strava:get-all-activities`:
- startDate: [date from step 1]
- activityTypes: ["Run"]
- maxActivities: 300
- perPage: 200

**STEP 3 — save array to temp file:**
Extract the activities array from the response.
Write it as `scripts/activities_tmp.json` using the Write tool.
Format: raw JSON array `[{...}, {...}]` — no headers or wrappers.

**STEP 4 — run the script:**
```
python scripts/weekly_volume.py scripts/activities_tmp.json
```

**STEP 5 — delete temp file:**
Delete `scripts/activities_tmp.json`.

**STEP 6 — display result:**
Read `volume_log.md` and display the table.
State how many weeks were saved and what the weekly average is.
