# skills_gym.md — Garmin Strength Workout Generator

## When to load
Load this file **only when the user asks to generate a strength/gym workout JSON** for Garmin Connect.
Do NOT load for running workout generation — use `skills_garmin.md` for that.

---

## Source of truth: `garmin_workouts/templates/Exercises.json`

Garmin provides an official library of **47 categories and ~1500 exercises** at `garmin_workouts/templates/Exercises.json` (format: `{"categories": {CAT_NAME: {"exercises": {EX_NAME: {...}}}}}`).

**ALWAYS parse this file** before writing any `category` or `exerciseName`. Importer rejects file with `{message: "Invalid category", error: "BadRequestException"}` if values don't match.

```python
import json
with open(r"C:\Users\grabb\Documents\running\garmin_workouts\templates\Exercises.json") as f:
    data = json.load(f)
for cat_name, cat_data in data["categories"].items():
    for ex_name in cat_data["exercises"].keys():
        if "CLAM" in ex_name:
            print(f"{cat_name} / {ex_name}")
# -> BANDED_EXERCISES / CLAM_SHELLS
```

### The 47 valid categories
BANDED_EXERCISES, BATTLE_ROPE, BENCH_PRESS, BIKE_OUTDOOR, CALF_RAISE, CARDIO, CARRY, CHOP, CORE, CRUNCH, CURL, DEADLIFT, ELLIPTICAL, FLOOR_CLIMB, FLYE, HIP_RAISE, HIP_STABILITY, HIP_SWING, HYPEREXTENSION, INDOOR_BIKE, LADDER, LATERAL_RAISE, LEG_CURL, LEG_RAISE, LUNGE, OLYMPIC_LIFT, PLANK, PLYO, PULL_UP, PUSH_UP, ROW, RUN, RUN_INDOOR, SANDBAG, SHOULDER_PRESS, SHOULDER_STABILITY, SHRUG, SIT_UP, SLED, SLEDGE_HAMMER, SQUAT, STAIR_STEPPER, SUSPENSION, TIRE, TOTAL_BODY, TRICEPS_EXTENSION, WARM_UP.

### Common pitfalls (verified empirically)
- Exact spelling matters: `CLAM_SHELLS` (with S and `_`), not `CLAMSHELL`. `DEAD_BUG` (with `_`), not `DEADBUG` (which also exists, but in BANDED_EXERCISES).
- Same exercise can exist in multiple categories — pick by context.
- **Bird dog is NOT in the library**. Leave `exerciseName=""` (category alone is enough, full instruction goes in `description`).
- Categories that were **wrongly guessed and rejected**: ~~HIP~~, ~~HIPS~~, ~~CHEST~~. Use HIP_STABILITY, HIP_RAISE, HIP_SWING, BENCH_PRESS instead.

### Standard mappings (prehab/runner-focused)
| Exercise (PL) | category | exerciseName |
|---------------|----------|--------------|
| Clamshells z gumą | BANDED_EXERCISES | CLAM_SHELLS |
| Side-lying leg raise z gumą | HIP_STABILITY | BAND_SIDE_LYING_LEG_RAISE |
| Monster walks / lateral band walks | HIP_STABILITY | LATERAL_WALKS_WITH_BAND_AT_ANKLES |
| Single-leg glute bridge | HIP_RAISE | BRIDGE_WITH_LEG_EXTENSION |
| Bird dog | HIP_STABILITY | "" (not in library) |
| Dead bug | HIP_STABILITY | DEAD_BUG |
| Plank | PLANK | PLANK |
| Side plank | PLANK | SIDE_PLANK |
| Pompki | PUSH_UP | PUSH_UP |
| Goblet squat | SQUAT | GOBLET_SQUAT |
| BSS (Bulgarian split squat) | LUNGE | DUMBBELL_BULGARIAN_SPLIT_SQUAT |
| RDL (Romanian deadlift) | DEADLIFT | ROMANIAN_DEADLIFT |
| Wspięcia łydek stojąc | CALF_RAISE | STANDING_CALF_RAISE |
| Warmup cardio | CARDIO | "" |

For any exercise NOT in this table — parse `Exercises.json` and find exact name.

---

## JSON top-level

```python
"sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
"estimatedDistanceInMeters": 0   # NOT null — Garmin requires 0 for strength
```

---

## Step types

| ID | Key | Use |
|----|-----|-----|
| 1 | warmup | Warmup (cardio + dynamic stretch, lap.button) |
| 3 | interval | Main exercise step (reps or time-based) |
| 5 | rest | Between sets and between exercise blocks (lap.button) |
| 6 | repeat | RepeatGroupDTO for N sets of one exercise |

---

## End conditions

| ID | Key | endConditionValue | endConditionCompare | preferredEndConditionUnit |
|----|-----|-------------------|---------------------|---------------------------|
| 1 | lap.button | 10 | null | null |
| 2 | time | seconds | null | null |
| 10 | reps | rep count | null | null |

For **reps-based** exercise: `conditionTypeId: 10, conditionTypeKey: "reps"`, value = rep count.
For **time-based** (plank, side plank): `conditionTypeId: 2, conditionTypeKey: "time"`, value in seconds.

---

## Pattern: each exercise = RepeatGroup[exercise + rest]

To do N sets of one exercise, wrap `[exercise, rest]` in `RepeatGroupDTO` with `numberOfIterations=N` and `skipLastRestStep=True` (skip rest after last set — outer rest between exercises kicks in).

**NEVER use `RepeatGroupDTO` with `numberOfIterations=1`** — Garmin rejects the file. A single exercise = plain `ExecutableStepDTO` (with rest after if needed). Combine warmup mobility (leg swings + hip circles + cat-cow) into **ONE** warmup CARDIO step with all movements in description.

### Rest between exercise blocks
After each Repeat (= after each exercise), insert `rest(order, None)` with `childStepId=None`. This is an **outer rest**, not inside any Repeat. Without it, importer may reject the file.

### Two-sided exercises (per-side) — CRITICAL

Ćwiczenia wykonywane na **jedną stronę na raz** (side plank, side plank + leg lift, BSS, single-leg RDL, clam shells, dead bug per side, bird dog, single-arm row, itd.) — **muszą mieć parzystą liczbę serii**, żeby każda strona dostała tyle samo pracy.

**Zła konfiguracja (verified empirically 03.07.2026):**
- Side plank + leg lift 3 serie po 20s → seria 1 prawa, seria 2 lewa, seria 3 prawa → **prawa 2×, lewa 1×**.
- Jeśli asymetria dodatnio-koreluje ze słabszą stroną (prawa słabsza + prawa 2×) — user robi więcej pracy na słabszej stronie, co daje mylące dane diagnostyczne i przeciąża tę stronę.

**Poprawna konfiguracja:**

Opcja A — parzysta liczba serii (3 → 4 lub 6):
```
Side plank + leg lift: 4 serie po 20s (prawa/lewa/prawa/lewa = 2×2)
```

Opcja B — 1 seria = obie strony w kolejności (opisz w `description`):
```
Side plank + leg lift: 3 serie. Każda seria = 20s prawa + 20s lewa
z ~5s przejściem. Duration step = 45s.
description: "Set N: 20s prawa noga → obrót → 20s lewa noga. Kontrola technika."
```

Opcja C — RepeatGroup dwustronny (osobne stepy L/R z rest 30s między):
```
RepeatGroup iters=N, workoutSteps=[side_plank_R, rest(30s), side_plank_L, rest(60s_end_of_set)]
```

**Domyślnie stosuj opcję A** — najczytelniej dla usera na zegarku, każdy step w timeline reprezentuje jedną stronę. W `description` **jasno pisz którą stronę robi w tym stepie** (np. "Set 1: PRAWA noga uniesiona", "Set 2: LEWA noga uniesiona").

Ta reguła dotyczy WSZYSTKICH ćwiczeń per-side (BSS, single-leg RDL, single-arm, side plank, itd.) chociaż dla BSS/single-arm często robi się "seria = obie strony" i nie ma tego problemu — kluczowe jest **żeby licznik serii i sposób wykonania były zgodne w description**.

---

## description per exercise — CRITICAL

In `description` of every ExecutableStepDTO, write the full execution instruction (form cues, breathing, modifications). User reads this **on the watch** during the workout — it's a substitute for a coach. ~150-250 ASCII characters, no decorations.

### Weight signaling — 3 places must agree

If the exercise is meant to be **bodyweight** (no load):
- `exerciseName`: do NOT use prefix `DUMBBELL_`/`BARBELL_`/`KETTLEBELL_` (suggests equipment). Pick a neutral name from the library (e.g. `BULGARIAN_SPLIT_SQUAT` not `DUMBBELL_BULGARIAN_SPLIT_SQUAT`), or leave `exerciseName=""`.
- `weightValue: 0`
- **First line of `description`** MUST say: `WAGA: BEZ OBCIAZENIA` (or `WAGA: 22kg LEKKO (powod)` if reduced weight). Don't hide weight info inside a sentence — user scrolls the description on the watch and reads the start.

Rules:
- `weightValue: 0` + `WAGA: BEZ OBCIAZENIA` first line — bodyweight due to injury/movement learning
- `weightValue: X` + `WAGA: Xkg LEKKO (reason)` first line — reduced weight from specific reason (back fatigue, post-incident)
- `weightValue: X` (no annotation) — normal working weight

If the plan modifies an exercise for injury — conflict between name (DUMBBELL_X), `weightValue` (0), and description ("@bodyweight" hidden in mid-sentence) = user will take the weight. Verified empirically 27.06.2026.

---

## Workout structure (typical)

1. **Warmup** (CARDIO, lap.button) — rower/treadmill + dynamic stretch
2. **CNS prep / pre-plyo** (optional) — pogo hops, A-skips. BEFORE main strength because requires fresh CNS.
3. **Main strength** (equipment, fresh CNS) — multi-joint big lifts (squat, BSS, RDL)
4. **Accessory** (single-joint, isolation) — calf raise, side plank with leg lift
5. **Core finisher** — plank, dead bug, bird dog
6. Between blocks: outer `rest(order, None)` with `childStepId=None`

---

## Helper functions (DRY)

Strength workouts have a LOT of repetitive boilerplate (each exercise = 25 lines of ExecutableStepDTO). Define at the start:

```python
def ex(order, child, category, name, reps, weight, desc):
    # full ExecutableStepDTO reps-based
def ex_time(order, child, category, name, secs, desc):
    # same but time-based (for plank etc)
def rest(order, child):
    # rest step lap.button
def repeat(order, child, iters, steps):
    # RepeatGroupDTO with skipLastRestStep=True
```

Reference implementations: `templates/Codzienny_Beton.json`, `2026.06.27_Silownia_A_Prehab.json`.

---

## Naming convention

- **Recurring workout** (daily routine): name **without date** (e.g. "Codzienny Beton"), file `Name_Routine.json`
- **One-off workout**: standard `YYYY.MM.DD_Type_Detail.json`

---

## Save pattern (Python)

```python
import json, os, pathlib

workout = { ... }  # dict built from the structure above

folder = pathlib.Path(os.path.expandvars(r"%USERPROFILE%\Documents\running\garmin_workouts\upcoming"))
folder.mkdir(parents=True, exist_ok=True)
filename = folder / "YYYY.MM.DD_Strength_NAME.json"

with open(filename, "w", encoding="utf-8") as f:
    json.dump(workout, f, ensure_ascii=True, indent=2)

print(f"Saved: {filename}")
```

Use `ensure_ascii=True` — Garmin Connect importer requires plain ASCII. Special characters will be escaped automatically. **NEVER use Cyrillic** — Chrome importer reads UTF-8 as Latin-1 and breaks on certain bytes.

For workouts cykliczne save also via `make_garmin.save_workout()` from `garmin_workouts/make_garmin.py` (handles the ASCII encoding).

---

## Reference files

| File | Purpose |
|------|---------|
| `garmin_workouts/templates/Exercises.json` | **Source of truth** — 47 categories, ~1500 exercises |
| `garmin_workouts/templates/REFERENCE_real_garmin_export.json` | Real Garmin export — structure reference |
| `garmin_workouts/upcoming/2026.06.27_Silownia_A_Prehab.json` | Latest working strength example |
| `garmin_workouts/upcoming/Codzienny_Beton.json` | Daily routine (no date in name) |

---

## Garmin Chrome importer

https://chromewebstore.google.com/detail/odgdfpclpfmmemajpmgfipfdfmjgihac

Import path: Garmin Connect → Create Workout (Running) → switch to Strength Training → import JSON.

---

## Pre-save checklist

- [ ] `sportTypeId=5`, `estimatedDistanceInMeters=0`
- [ ] Every `category` is from the 47-list above (verified)
- [ ] Every `exerciseName` exists in `Exercises.json` OR is `""`
- [ ] Reps-based exercise: `conditionTypeId=10`
- [ ] Time-based exercise: `conditionTypeId=2`
- [ ] Each exercise wrapped in `RepeatGroupDTO` with `numberOfIterations >= 2`
- [ ] `skipLastRestStep=True` in every RepeatGroup
- [ ] Outer `rest(order, None)` after each Repeat
- [ ] **Two-sided exercise (side plank, single-leg, BSS): parzysta liczba serii LUB jawnie w description "seria = prawa + lewa"** (verified 03.07.2026)
- [ ] If bodyweight: `weightValue=0` + neutral `exerciseName` + `WAGA: BEZ OBCIAZENIA` first line of description
- [ ] No Cyrillic chars anywhere
- [ ] Saved via `make_garmin.save_workout()` or direct write with `ensure_ascii=True`
- [ ] Filename: recurring → `Name_Routine.json`; one-off → `YYYY.MM.DD_Type_Detail.json`
