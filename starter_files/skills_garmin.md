# SKILLS GARMIN — JSON workout spec (load only when generating Garmin JSON)

Reference: `garmin_workouts/templates/REFERENCE_real_garmin_export.json`
Workout name: `YYYY.MM.DD WorkoutName_Pace_Distance`
File name: `YYYY.MM.DD_Type_Pace.json`

## Required fields on every ExecutableStepDTO
Missing any = 500 error.
```
type | stepOrder | stepType | childStepId | description | endCondition | endConditionValue
preferredEndConditionUnit | endConditionCompare | targetType | targetValueOne | targetValueTwo
targetValueUnit | zoneNumber | secondaryTargetType | secondaryTargetValueOne | secondaryTargetValueTwo
secondaryTargetValueUnit | secondaryZoneNumber | endConditionZone | strokeType | equipmentType
category | exerciseName | workoutProvider | providerExerciseSourceId | weightValue=-1 | weightUnit
```

## Step types
| ID | Key | Use |
|----|-----|-----|
| 1 | warmup | Warmup (use TWICE: time then lap.button) |
| 2 | cooldown | Cooldown (lap.button) |
| 3 | interval | Main effort / group segment |
| 4 | recovery | Rest between reps |
| 6 | repeat | RepeatGroupDTO only |

## End conditions
| ID | Key | endConditionValue | endConditionCompare | preferredEndConditionUnit |
|----|-----|-------------------|---------------------|--------------------------|
| 1 | lap.button | 0 | "gt" | {unitId:2,unitKey:"kilometer",factor:100000} |
| 2 | time | seconds | "gt" | {unitId:2,...} |
| 3 | distance | meters | "gt" | {unitId:2,...} |
| 7 | iterations | count | null | null |

EXCEPTION — cooldown lap.button: `endConditionCompare=""` and `preferredEndConditionUnit=null`.

## Target types
| ID | Key | When |
|----|-----|------|
| 1 | no.target | targetValueOne/Two = null |
| 6 | pace.zone | values in m/s |

`targetValueOne` = faster limit (higher m/s = lower pace, e.g. 6:00 = 2.778)
`targetValueTwo` = slower limit (lower m/s = higher pace, e.g. 6:20 = 2.632)
Always: targetValueOne > targetValueTwo.

## Pace → m/s (1000 / pace_seconds)
```
4:00=4.167 | 4:10=4.000 | 4:14=3.937 | 4:18=3.876 | 4:30=3.704
4:44=3.521 | 4:50=3.448 | 5:00=3.333 | 5:10=3.226 | 5:20=3.125
5:26=3.067 | 5:30=3.030 | 5:50=2.857 | 6:00=2.778 | 6:10=2.703
6:20=2.632 | 6:30=2.564 | 6:40=2.500 | 7:00=2.381
```

## RepeatGroupDTO
```json
{
  "type": "RepeatGroupDTO",
  "stepOrder": 3,
  "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
  "childStepId": 1,
  "numberOfIterations": 4,
  "workoutSteps": [...all inner steps have childStepId: 1...],
  "endConditionValue": 4,
  "preferredEndConditionUnit": null,
  "endConditionCompare": null,
  "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": false},
  "skipLastRestStep": false,
  "smartRepeat": false
}
```

## Special characters — CRITICAL
Chrome extension misreads UTF-8 as Latin-1 → file MUST be ASCII-only.
NEVER use Cyrillic — "a" must be ASCII U+0061, NOT Cyrillic U+0430.

Special character escape codes (use literally in Python strings; `ensure_ascii=True` will handle the rest):
```
ś=ś | ó=ó | ą=ą | ę=ę | ć=ć | ł=ł | ń=ń | ź=ź | ż=ż
```

## ⚠️ Saving the file — ALWAYS Python, NEVER Write/filesystem tools
`mcp__filesystem__write_file` and the `Write` tool output UTF-8 → literal special chars → Chrome importer breaks.

Template (PowerShell) — copy-paste, only change `workout = {...}` and file name:
```powershell
$py = @'
import sys
sys.path.insert(0, r"[YOUR_RUNNING_FOLDER]\garmin_workouts")
from make_garmin import save_workout

workout = {
    # ... your workout dict here ...
}

save_workout(workout, "YYYY.MM.DD_Type_Pace.json")
'@
$py | Out-File "$env:TEMP\gw.py" -Encoding utf8; python "$env:TEMP\gw.py"
```

## Pre-save checklist
- [ ] All required fields present in every ExecutableStepDTO
- [ ] `targetValueOne` = faster limit (higher m/s, np. 6:00 = 2.778), `targetValueTwo` = slower limit (np. 6:20 = 2.632)
- [ ] Warmup = 2 steps (time-based + lap.button)
- [ ] Cooldown = lap.button with endConditionCompare="" and preferredEndConditionUnit=null
- [ ] Special chars as normal Python strings (ensure_ascii=True in make_garmin.py handles escaping)
- [ ] Saved via `make_garmin.save_workout()`, not via Write tool
- [ ] File name: YYYY.MM.DD_Type_Pace.json

## Garmin Chrome importer
https://chromewebstore.google.com/detail/odgdfpclpfmmemajpmgfipfdfmjgihac

## Elevation per km (when streams fetched)
```python
def elevation_per_km(dist, alt):
    total_km = int(dist[-1] // 1000) + 1
    for km in range(1, total_km + 1):
        km_start, km_end = (km - 1) * 1000, km * 1000
        up = down = 0.0
        for i in range(1, len(dist)):
            if dist[i-1] >= km_start and dist[i] <= km_end:
                d = alt[i] - alt[i-1]
                if d > 0: up += d
                elif d < 0: down += abs(d)
        if up > 0 or down > 0:
            print(f"km {km}: +{up:.1f}m / -{down:.1f}m")
```
