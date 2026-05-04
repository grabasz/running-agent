# SKILLS — Claude Running Agent behavior rules

## 📅 Training plan phases (Jack Daniels)

```
Phase I   — BASE:           Easy + Strides, volume building
Phase II  — EARLY QUALITY:  R-pace + T/M
Phase III — LATE QUALITY:   I-pace + T
Phase IV  — FINAL + TAPER:  T + M inserts + volume reduction
```

**Taper (half marathon) — last 10 days:**
```
Day -10: last medium-long or tempo
Day  -9: easy
Day  -8: REST
Day  -7: last short quality session (e.g. 3x1km T-pace)
Days -6 to -3: easy or REST
Day  -2: REST or 20min very easy
Day  -1: SHAKEOUT (the only one!) 15-20min + 4x strides
Day   0: RACE
```
**SHAKEOUT = ONE, the day before the race.** Not 2, not 3.
If traveling: do the shakeout at the race venue.

---

## 🌤️ Weather and date
Tool: `weather:weather_forecast` (Open-Meteo MCP, native Celsius)
Parameters: latitude, longitude, temperature_unit=celsius, timezone=local
Data source for current date: `current.time` from weather response — reliable
Output format:
```
🌤️ [City] — [Day] [Date]
| | Temp | Rain | Wind |
| 🌡️ Now  | X°C | Ymm | Z km/h |
| ☀️ Tomorrow | min–max°C | P% | W km/h |
```
Icons: 0-1=☀️ 2-3=🌤️ 51-67=🌧️ 71-77=❄️ 80-82=🌦️ 95+=⚡
Effect on training: >20°C=+5-8bpm HR+hydration | <5°C=layer up | wind>20kmh=affects pace
NEVER show °F — always convert if needed: (F-32)×5/9

---

## 📅 Dates and days of week
ALWAYS verify via timeanddate.com or current.time from weather
Before any plan: check 3 control dates out loud (first, last, one middle)
Before JSON: state date+weekday and confirm before saving

---

## 📊 Training plans (Jack Daniels + 80/20)
Weekly structure: 2x Easy + 1x Quality accent (rotate!) + 1x Long Run
Plan table: `Date|Day|Phase|Type|Workout steps|Distance|Group alternative|Notes`
Every 3-4 weeks: recovery week (volume -20-30%, no hard accents)

Quality accent rotation: Intervals(I) | Threshold/Cruise(T) | Reps+Strides(R) | Hills | Continuous Tempo | Fartlek | LongRun+M inserts

VDOT zones (update after every race result):
| Zone | Type | Purpose |
|------|------|---------|
| E | Easy | Aerobic base, recovery |
| M | Marathon pace | Running economy |
| T | Threshold | Lactate clearance |
| I | Intervals | VO2max |
| R | Repetitions | Speed, economy |

Calculate VDOT: https://runsmartproject.com/calculator/

---

## 🏃 Garmin workout structure (ALWAYS use this)
```
1. WU part 1 — TIME based (e.g. 10min @6:30/km) — auto ends
2. WU part 2 — LAP BUTTON — athlete decides when ready
3. MAIN WORKOUT (intervals / tempo / group run)
4. COOLDOWN — LAP BUTTON — press on arrival home
```
Group run warmup: use lap.button warmup step as "run to meeting point, press LAP on arrival"

---

## 💾 JSON for Garmin Connect

Reference file: `garmin_workouts/templates/REFERENCE_real_garmin_export.json`
Workout name: `YYYY.MM.DD WorkoutName_Pace_Distance`
File name: `YYYY.MM.DD_Type_Pace.json`

**Every ExecutableStepDTO MUST have ALL these fields (missing any = 500 error):**
type | stepOrder | stepType | childStepId | description | endCondition | endConditionValue
preferredEndConditionUnit | endConditionCompare | targetType | targetValueOne | targetValueTwo
targetValueUnit | zoneNumber | secondaryTargetType | secondaryTargetValueOne | secondaryTargetValueTwo
secondaryTargetValueUnit | secondaryZoneNumber | endConditionZone | strokeType | equipmentType
category | exerciseName | workoutProvider | providerExerciseSourceId | weightValue=-1 | weightUnit

**Step types:**
| ID | Key | Use |
|----|-----|-----|
| 1 | warmup | Warmup (use TWICE: time then lap.button) |
| 2 | cooldown | Cooldown (lap.button) |
| 3 | interval | Main effort / group segment |
| 4 | recovery | Rest between reps |
| 6 | repeat | RepeatGroupDTO only |

**End conditions:**
| ID | Key | endConditionValue | endConditionCompare | preferredEndConditionUnit |
|----|-----|-------------------|---------------------|--------------------------|
| 1 | lap.button | 0 | "gt" | {unitId:2,unitKey:"kilometer",factor:100000} |
| 2 | time | seconds (e.g.600) | "gt" | {unitId:2,...} |
| 3 | distance | meters (e.g.1000) | "gt" | {unitId:2,...} |
| 7 | iterations | count | null | null |
EXCEPTION — cooldown lap.button: endConditionCompare="" and preferredEndConditionUnit=null

**Target types:**
| ID | Key | When to use |
|----|-----|-------------|
| 1 | no.target | No target — set targetValueOne/Two to null |
| 6 | pace.zone | Pace zone — values in m/s |

targetValueOne > targetValueTwo (slower limit > faster limit, both in m/s)

**Pace → m/s conversion (1000 / pace_in_seconds):**
```
4:00=4.167 | 4:10=4.000 | 4:14=3.937 | 4:18=3.876 | 4:30=3.704
4:44=3.521 | 4:50=3.448 | 5:00=3.333 | 5:10=3.226 | 5:20=3.125
5:26=3.067 | 5:30=3.030 | 5:50=2.857 | 6:00=2.778 | 6:10=2.703
6:20=2.632 | 6:30=2.564 | 6:40=2.500 | 7:00=2.381
```

**RepeatGroupDTO structure:**
```json
{
  "type": "RepeatGroupDTO",
  "stepOrder": 3,
  "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
  "childStepId": 1,
  "numberOfIterations": 4,
  "workoutSteps": [...all steps inside have childStepId: 1...],
  "endConditionValue": 4,
  "preferredEndConditionUnit": null,
  "endConditionCompare": null,
  "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": false},
  "skipLastRestStep": false,
  "smartRepeat": false
}
```

**Special characters — CRITICAL:**
Chrome extension doesn't send correct charset → Garmin misreads UTF-8 as Latin-1.
Solution: use unicode escape sequences in description strings.
Polish chars: ś=\u015b | ó=\u00f3 | ą=\u0105 | ę=\u0119 | ć=\u0107 | ł=\u0142 | ń=\u0144 | ź=\u017a | ż=\u017c
NEVER use Cyrillic — "a" in "interwal" must be ASCII U+0061, NOT Cyrillic U+0430

**Pre-save checklist:**
- [ ] All fields present in every ExecutableStepDTO
- [ ] targetValueOne > targetValueTwo (m/s)
- [ ] Warmup = 2 steps (time-based + lap.button)
- [ ] Cooldown = lap.button with endConditionCompare="" and preferredEndConditionUnit=null
- [ ] Special characters as \uXXXX unicode escapes
- [ ] No Cyrillic characters anywhere
- [ ] File name: YYYY.MM.DD_Type_Pace.json

**Garmin Connect import extension (Chrome):**
https://chromewebstore.google.com/detail/odgdfpclpfmmemajpmgfipfdfmjgihac

---

## 🦉 Strava activity analysis
1. FIRST: `strava:get-activity-details` — description contains race times, gear, feelings
2. THEN: fetch laps + streams (HR, pace, power, altitude)
3. Report elevation per km: `km X: +Ym / -Zm`
4. Strava cadence = one-sided (single leg) → multiply ×2 for real cadence
5. After threshold/intervals/race → update forma.md with new threshold data

---

## 🦃 Lactate threshold tracking
After every T/I workout or race: evaluate pace at stable HR = threshold
Entry format: `DATE: X:XX/km @ Y bpm (VDOT~Z) — context`
If threshold shifts >5sec/km from current T-pace → update VDOT and zones in forma.md

---

## 📂 Which file to read when
- `profil.md` — who the user is, running groups, MCP tools (read once per session)
- `forma.md` — VDOT, zones, predictors, threshold history (read when analyzing or planning)
- `wyscigy.md` — race calendar, strategies, logistics (read when discussing races)
- `plan_aktualny.md` — current plan (read for today's/tomorrow's workout questions)
- `skills.md` — this file (read when generating JSON or building training plans)
- `garmin_workouts/templates/` — Garmin JSON reference
