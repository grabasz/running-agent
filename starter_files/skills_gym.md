# skills_gym.md — Garmin Strength Workout Generator

## When to load
Load this file only when the user asks to generate a **strength/gym workout JSON** for Garmin Connect.
Do NOT load for running workout generation — use `skills_garmin.md` for that.

---

## What this file does
Generates Garmin Connect strength workout JSON files that can be imported via the Garmin Workout Importer Chrome extension.

**Import path:** Garmin Connect → Create Workout (Running) → switch to Strength Training → import JSON
Or use the Chrome extension on https://connect.garmin.com/modern/workout/create/running

---

## JSON skeleton

```json
{
  "workoutId": 0,
  "ownerId": 0,
  "workoutName": "YYYY.MM.DD Strength",
  "description": null,
  "sportType": {
    "sportTypeId": 5,
    "sportTypeKey": "strength_training",
    "displayOrder": 5
  },
  "subSportType": null,
  "estimatedDurationInSecs": 0,
  "estimatedDistanceInMeters": 0,
  "workoutSegments": [
    {
      "segmentOrder": 1,
      "sportType": {
        "sportTypeId": 5,
        "sportTypeKey": "strength_training",
        "displayOrder": 5
      },
      "workoutSteps": []
    }
  ],
  "poolLength": null,
  "poolLengthUnit": null,
  "shared": false
}
```

All exercises go inside `workoutSteps` array. StepIds and stepOrders are sequential integers starting at 1.

---

## Step types

### Warmup step (cardio or single activation exercise)
```json
{
  "type": "ExecutableStepDTO",
  "stepId": 1,
  "stepOrder": 1,
  "stepType": { "stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1 },
  "childStepId": null,
  "description": "treadmill",
  "endCondition": { "conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": true },
  "endConditionValue": 10,
  "targetType": { "workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1 },
  "targetValueOne": null, "targetValueTwo": null, "targetValueUnit": null,
  "zoneNumber": null,
  "secondaryTargetType": null, "secondaryTargetValueOne": null, "secondaryTargetValueTwo": null,
  "secondaryTargetValueUnit": null, "secondaryZoneNumber": null, "endConditionZone": null,
  "strokeType": { "strokeTypeId": 0, "strokeTypeKey": null, "displayOrder": 0 },
  "equipmentType": { "equipmentTypeId": 0, "equipmentTypeKey": null, "displayOrder": 0 },
  "category": "CARDIO",
  "exerciseName": "",
  "workoutProvider": null, "providerExerciseSourceId": null,
  "weightValue": null, "weightUnit": null
}
```

For a **timed warmup exercise** (e.g. 40s plank): use `"conditionTypeId": 2, "conditionTypeKey": "time"` and `"endConditionValue": 40` (seconds).

### Rest step (between sets or between exercise groups)
```json
{
  "type": "ExecutableStepDTO",
  "stepId": 2,
  "stepOrder": 2,
  "stepType": { "stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5 },
  "childStepId": null,
  "description": null,
  "endCondition": { "conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": true },
  "endConditionValue": 10,
  "targetType": { "workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1 },
  "targetValueOne": null, "targetValueTwo": null, "targetValueUnit": null,
  "zoneNumber": null,
  "secondaryTargetType": null, "secondaryTargetValueOne": null, "secondaryTargetValueTwo": null,
  "secondaryTargetValueUnit": null, "secondaryZoneNumber": null, "endConditionZone": null,
  "strokeType": { "strokeTypeId": 0, "strokeTypeKey": null, "displayOrder": 0 },
  "equipmentType": { "equipmentTypeId": 0, "equipmentTypeKey": null, "displayOrder": 0 },
  "category": null, "exerciseName": null,
  "workoutProvider": null, "providerExerciseSourceId": null,
  "weightValue": null, "weightUnit": null
}
```

### Exercise set (reps-based, inside RepeatGroup)
```json
{
  "type": "ExecutableStepDTO",
  "stepId": 8,
  "stepOrder": 8,
  "stepType": { "stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3 },
  "childStepId": 1,
  "description": null,
  "endCondition": { "conditionTypeId": 10, "conditionTypeKey": "reps", "displayOrder": 10, "displayable": true },
  "endConditionValue": 10,
  "targetType": { "workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1 },
  "targetValueOne": null, "targetValueTwo": null, "targetValueUnit": null,
  "zoneNumber": null,
  "secondaryTargetType": null, "secondaryTargetValueOne": null, "secondaryTargetValueTwo": null,
  "secondaryTargetValueUnit": null, "secondaryZoneNumber": null, "endConditionZone": null,
  "strokeType": { "strokeTypeId": 0, "strokeTypeKey": null, "displayOrder": 0 },
  "equipmentType": { "equipmentTypeId": 0, "equipmentTypeKey": null, "displayOrder": 0 },
  "category": "SQUAT",
  "exerciseName": "GOBLET_SQUAT",
  "workoutProvider": null, "providerExerciseSourceId": null,
  "weightValue": 24,
  "weightUnit": { "unitId": 8, "unitKey": "kilogram", "factor": 1000 }
}
```

For **bodyweight** (no weight): `"weightValue": null, "weightUnit": null`

For **time-based** exercise (e.g. 45s plank): `"conditionTypeId": 2, "conditionTypeKey": "time"` and `"endConditionValue": 45`

### RepeatGroup (3 sets of one exercise)
`childStepId` increments per exercise group (1, 2, 3, …). All steps inside the group share the same `childStepId`.

```json
{
  "type": "RepeatGroupDTO",
  "stepId": 7,
  "stepOrder": 7,
  "stepType": { "stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6 },
  "childStepId": 1,
  "numberOfIterations": 3,
  "workoutSteps": [
    { /* exercise step with childStepId: 1 */ },
    { /* rest step with childStepId: 1 */ }
  ],
  "endConditionValue": 3,
  "endCondition": { "conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": false },
  "skipLastRestStep": true,
  "smartRepeat": false
}
```

Set `"skipLastRestStep": true` to skip the rest after the final set (user rests before moving to the next exercise block).
Set `"skipLastRestStep": false` if you want the rest to run after every set including the last.

---

## Typical workout structure

```
warmup steps (cardio + activation exercises)
rest step
RepeatGroup (exercise A, 3×N reps + rest)    ← childStepId: 1
rest step  (between exercise groups)
RepeatGroup (exercise B, 3×N reps + rest)    ← childStepId: 2
rest step
RepeatGroup (exercise C, 3×N reps + rest)    ← childStepId: 3
...
standalone timed exercise (e.g. plank hold at end)
```

---

## Exercise lookup table

Format: **Description** → `"category": "X", "exerciseName": "Y"`

### Legs / lower body
| Exercise | category | exerciseName |
|----------|----------|--------------|
| Goblet squat | `SQUAT` | `GOBLET_SQUAT` |
| Barbell back squat | `SQUAT` | `BARBELL_BACK_SQUAT` |
| Dumbbell squat | `SQUAT` | `DUMBBELL_SQUAT` |
| Overhead squat | `SQUAT` | `OVERHEAD_SQUAT` |
| Bulgarian split squat (barbell) | `LUNGE` | `BARBELL_BULGARIAN_SPLIT_SQUAT` |
| Bulgarian split squat (dumbbell) | `LUNGE` | `DUMBBELL_BULGARIAN_SPLIT_SQUAT` |
| Walking lunge with dumbbells overhead | `LUNGE` | `DUMBBELL_OVERHEAD_WALKING_LUNGE` |
| Reverse lunge with dumbbells | `LUNGE` | `DUMBBELL_REVERSE_LUNGE` |
| Side lunge | `LUNGE` | `SIDE_LUNGE` |
| Romanian deadlift (RDL) | `DEADLIFT` | `ROMANIAN_DEADLIFT` |
| Single-leg RDL with dumbbells | `DEADLIFT` | `SINGLE_LEG_ROMANIAN_DEADLIFT_WITH_DUMBBELL` |
| Barbell deadlift | `DEADLIFT` | `BARBELL_DEADLIFT` |
| Dumbbell straight-leg deadlift | `DEADLIFT` | `DUMBBELL_STRAIGHT_LEG_DEADLIFT` |
| Calf raise (standing) | `CALF_RAISE` | `STANDING_CALF_RAISE` |
| Single-leg calf raise | `CALF_RAISE` | `SINGLE_LEG_STANDING_CALF_RAISE` |
| Step up (dumbbell) | `SQUAT` | `DUMBBELL_STEP_UP` |
| Box jump | `JUMP` | `BOX_JUMP` |

### Hips / glutes / stability
| Exercise | category | exerciseName |
|----------|----------|--------------|
| Hip thrust (barbell) | `HIP_RAISE` | `BARBELL_HIP_THRUST_WITH_BENCH` |
| Single-leg hip raise | `HIP_RAISE` | `SINGLE_LEG_HIP_RAISE` |
| Glute bridge | `HIP_RAISE` | `HIP_RAISE` |
| Kettlebell swing | `HIP_RAISE` | `KETTLEBELL_SWING` |
| Dead bug | `HIP_STABILITY` | `DEAD_BUG` |
| Side-lying leg raise | `HIP_STABILITY` | `SIDE_LYING_LEG_RAISE` |
| Clamshell | `HIP_RAISE` | `CLAMS` |
| Quadruped hip extension | `HIP_STABILITY` | `QUADRUPED_HIP_EXTENSION` |
| Standing hip abduction | `HIP_STABILITY` | `STANDING_HIP_ABDUCTION` |

### Pull / back
| Exercise | category | exerciseName |
|----------|----------|--------------|
| Pull-up | `PULL_UP` | `PULL_UP` |
| Chin-up | `PULL_UP` | `CHIN_UP` |
| Barbell row | `ROW` | `BARBELL_ROW` |
| Dumbbell row | `ROW` | `DUMBBELL_ROW` |
| Face pull | `ROW` | `FACE_PULL` |
| Seated cable row | `ROW` | `SEATED_CABLE_ROW` |
| Inverted row / Australian row | `ROW` | `BARBELL_ROW` |
| Hanging leg raise | `LEG_RAISE` | `HANGING_LEG_RAISE` |
| Hanging knee raise | `LEG_RAISE` | `HANGING_KNEE_RAISE` |

### Push / chest / shoulders
| Exercise | category | exerciseName |
|----------|----------|--------------|
| Dumbbell bench press | `BENCH_PRESS` | `DUMBBELL_BENCH_PRESS` |
| Barbell bench press | `BENCH_PRESS` | `BARBELL_BENCH_PRESS` |
| Incline dumbbell bench press | `BENCH_PRESS` | `INCLINE_DUMBBELL_BENCH_PRESS` |
| Push-up | `PUSH_UP` | `PUSH_UP` |
| Overhead dumbbell press | `SHOULDER_PRESS` | `OVERHEAD_DUMBBELL_PRESS` |
| Barbell overhead press | `SHOULDER_PRESS` | `BARBELL_SHOULDER_PRESS` |
| Lateral raise standing (L-raise) | `SHOULDER_STABILITY` | `STANDING_L_RAISE` |
| Dumbbell front raise | `SHOULDER_PRESS` | `DUMBBELL_FRONT_RAISE` |

### Core / plank
| Exercise | category | exerciseName |
|----------|----------|--------------|
| Plank (standard) | `PLANK` | `PLANK` |
| Side plank | `PLANK` | `SIDE_PLANK` |
| Two-point plank (1 arm 1 leg) | `PLANK` | `TWO_POINT_PLANK` |
| Plank with arm raise | `PLANK` | `PLANK_WITH_ARM_RAISE` |
| Mountain climber | `PLANK` | `MOUNTAIN_CLIMBER` |
| Dead bug | `HIP_STABILITY` | `DEAD_BUG` |
| L-sit | `CORE` | `L_SIT` |
| Bicycle crunch | `CORE` | `BICYCLE` |
| Jackknife (Swiss ball) | `CORE` | `SWISS_BALL_JACKKNIFE` |
| Russian twist | `CORE` | `RUSSIAN_TWIST` |
| Leg raise (lying) | `LEG_RAISE` | `LYING_STRAIGHT_LEG_RAISE` |

### Arms
| Exercise | category | exerciseName |
|----------|----------|--------------|
| Dumbbell biceps curl | `CURL` | `DUMBBELL_BICEPS_CURL` |
| Barbell biceps curl | `CURL` | `BARBELL_BICEPS_CURL` |
| Hammer curl | `CURL` | `DUMBBELL_HAMMER_CURL` |
| Generic curl (any) | `CURL` | `""` (empty string) |

---

## Cardio / machine warmup
For treadmill, bike, or unspecified cardio: use `"category": "CARDIO", "exerciseName": ""` with `"conditionTypeId": 1, "conditionTypeKey": "lap.button"` (user presses lap when done).

---

## Rules
- `stepId` and `stepOrder` are the same sequential integer for each step (1, 2, 3, …) across the entire workout.
- `childStepId` inside a RepeatGroup: assign a group index (1, 2, 3, …) — all steps in the same group share the same value.
- Rest between sets (inside RepeatGroup): `endCondition: "lap.button"`. User presses lap when ready.
- Rest between exercise blocks (outside RepeatGroup): also `"lap.button"` rest step.
- Weight in kg → `"weightValue": N, "weightUnit": {"unitId": 8, "unitKey": "kilogram", "factor": 1000}`.
- Bodyweight exercise → `"weightValue": null, "weightUnit": null`.
- Time-based step → `"conditionTypeId": 2, "conditionTypeKey": "time"`, value in seconds.
- Reps-based step → `"conditionTypeId": 10, "conditionTypeKey": "reps"`, value = rep count.
- Do NOT use Polish characters in `workoutName` or `description` — Chrome importer breaks on non-ASCII.

---

## Save pattern

```python
import json, os, pathlib

workout = { ... }  # dict built from the skeleton above

folder = pathlib.Path(os.path.expandvars(r"%USERPROFILE%\Documents\running\garmin_workouts\gym"))
folder.mkdir(parents=True, exist_ok=True)
filename = folder / "YYYY.MM.DD_Strength_NAME.json"

with open(filename, "w", encoding="utf-8") as f:
    json.dump(workout, f, ensure_ascii=True, indent=2)

print(f"Saved: {filename}")
```

Use `ensure_ascii=True` — Garmin Connect importer requires plain ASCII. Special characters will be escaped automatically.

---

## Reference files (local, git-ignored)

| File | Purpose |
|------|---------|
| `garmin_workouts/gym/WorkoutsPL.txt` | Full exercise list: `CATEGORY_EXERCISENAME=Polish description` |
| `garmin_workouts/gym/ExercisesToEquipment.json` | Exercise → equipment mapping |
| `garmin_workouts/gym/2026.05.18_Siła_TEMPLATE.json` | Real export — use as structure reference |

If an exercise is not in the lookup table above, search `WorkoutsPL.txt` using the Polish name to find the `CATEGORY_EXERCISENAME` key, then split on `_` to get `category` and `exerciseName`.

---

## Quick generation checklist

1. Ask the user: exercises, sets×reps, weights (or bodyweight), rest preference (lap button = flexible, or fixed seconds)
2. Build warmup section (cardio + 1–2 activation exercises)
3. Build one RepeatGroup per exercise (3 sets default, adjust if user specifies)
4. Add rest step between groups
5. Name the file `YYYY.MM.DD_Strength_FOCUS.json` (ASCII only)
6. Save to `garmin_workouts/gym/` using the save pattern above
7. Tell user: open Garmin Connect → Create Workout → change sport to Strength → use Chrome extension to import
