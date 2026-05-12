#!/usr/bin/env python3
"""
Garmin Connect workout JSON generator.
Outputs JSON with proper \\uXXXX escapes so Chrome importer reads Polish chars correctly.

Usage:
  python garmin_gen.py easy        2026.05.07 6:30 20
  python garmin_gen.py easy_strides 2026.05.06 6:30 20 --strides 4
  python garmin_gen.py shakeout    2026.05.09 6:30 15 --strides 4 --race-pace 4:40
  python garmin_gen.py intervals   2026.05.13 6:30 --int-pace 4:44 --int-dist 1000 --reps 4 --rec 90
  python garmin_gen.py tempo       2026.05.14 6:30 --t-pace 4:55 --t-duration 20
  python garmin_gen.py race_hm     2026.05.10 --p1 4:40 --p2 4:38 --p3 4:30
  python garmin_gen.py fix-encoding garmin_workouts/upcoming/some.json   # fix broken UTF-8
"""

import json, argparse, os, sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "garmin_workouts" / "upcoming"

# ---------- pace helpers ----------

def pace_ms(pace_str: str) -> float:
    """'M:SS' or 'MM:SS' -> m/s"""
    parts = pace_str.split(":")
    secs = int(parts[0]) * 60 + int(parts[1])
    return round(1000 / secs, 7)

def pace_range(target: str, delta: int = 10):
    """Returns (faster_ms, slower_ms) with ±delta seconds around target."""
    parts = target.split(":")
    secs = int(parts[0]) * 60 + int(parts[1])
    faster = round(1000 / max(1, secs - delta), 7)
    slower = round(1000 / (secs + delta), 7)
    return faster, slower

# ---------- shared step fragments ----------

def _unit_km():
    return {"unitId": 2, "unitKey": "kilometer", "factor": 100000}

def _unit_kg():
    return {"unitId": 8, "unitKey": "kilogram", "factor": 1000}

def _stroke():
    return {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}

def _equip():
    return {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}

def _base_fields(child_id=None):
    return dict(
        childStepId=child_id,
        endConditionZone=None,
        secondaryTargetType=None, secondaryTargetValueOne=None,
        secondaryTargetValueTwo=None, secondaryTargetValueUnit=None,
        secondaryZoneNumber=None, zoneNumber=None, targetValueUnit=None,
        strokeType=_stroke(), equipmentType=_equip(),
        category=None, exerciseName=None, workoutProvider=None,
        providerExerciseSourceId=None, weightValue=-1, weightUnit=_unit_kg(),
    )

def _target_pace(faster_ms, slower_ms):
    return dict(
        targetType={"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6},
        targetValueOne=faster_ms, targetValueTwo=slower_ms,
    )

def _target_none():
    return dict(
        targetType={"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
        targetValueOne=None, targetValueTwo=None,
    )

def _step_type(id_, key):
    return {"stepTypeId": id_, "stepTypeKey": key, "displayOrder": id_}

# ---------- step builders ----------

def step_warmup_time(order, duration_secs, pace, desc):
    f, s = pace_range(pace)
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": _step_type(1, "warmup"), "description": desc,
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
            "endConditionValue": duration_secs, "preferredEndConditionUnit": _unit_km(), "endConditionCompare": "gt",
            **_target_pace(f, s), **_base_fields()}

def step_warmup_lap(order, desc):
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": _step_type(1, "warmup"), "description": desc,
            "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True},
            "endConditionValue": 0, "preferredEndConditionUnit": _unit_km(), "endConditionCompare": "gt",
            **_target_none(), **_base_fields()}

def step_interval_time(order, duration_secs, pace, desc, child_id=None):
    f, s = pace_range(pace)
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": _step_type(3, "interval"), "description": desc,
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
            "endConditionValue": duration_secs, "preferredEndConditionUnit": _unit_km(), "endConditionCompare": "gt",
            **_target_pace(f, s), **_base_fields(child_id)}

def step_interval_dist(order, dist_m, pace, desc, child_id=None):
    f, s = pace_range(pace)
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": _step_type(3, "interval"), "description": desc,
            "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True},
            "endConditionValue": dist_m, "preferredEndConditionUnit": _unit_km(), "endConditionCompare": "gt",
            **_target_pace(f, s), **_base_fields(child_id)}

def step_interval_dist_no_target(order, dist_m, desc, child_id=None):
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": _step_type(3, "interval"), "description": desc,
            "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True},
            "endConditionValue": dist_m, "preferredEndConditionUnit": _unit_km(), "endConditionCompare": "gt",
            **_target_none(), **_base_fields(child_id)}

def step_recovery(order, duration_secs, desc, child_id=1):
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": _step_type(4, "recovery"), "description": desc,
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
            "endConditionValue": duration_secs, "preferredEndConditionUnit": None, "endConditionCompare": "",
            **_target_none(), **_base_fields(child_id)}

def step_cooldown(order, pace, desc):
    f, s = pace_range(pace)
    return {"type": "ExecutableStepDTO", "stepOrder": order,
            "stepType": _step_type(2, "cooldown"), "description": desc,
            "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True},
            "endConditionValue": 0, "preferredEndConditionUnit": None, "endConditionCompare": "",
            **_target_pace(f, s), **_base_fields()}

def repeat_group(order, n_iters, inner_steps, skip_last=True):
    return {"type": "RepeatGroupDTO", "stepOrder": order,
            "stepType": _step_type(6, "repeat"), "childStepId": 1,
            "numberOfIterations": n_iters, "workoutSteps": inner_steps,
            "endConditionValue": n_iters, "preferredEndConditionUnit": None, "endConditionCompare": None,
            "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
            "skipLastRestStep": skip_last, "smartRepeat": False}

# ---------- workout assembler ----------

def make_workout(name, desc, steps):
    sport = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}
    return {"workoutName": name, "description": desc, "sportType": sport,
            "subSportType": None, "estimatedDurationInSecs": 0, "estimatedDistanceInMeters": None,
            "workoutSegments": [{"segmentOrder": 1, "sportType": sport,
                                  "poolLengthUnit": None, "poolLength": None, "workoutSteps": steps}],
            "poolLength": None, "poolLengthUnit": None, "locale": None,
            "workoutProvider": None, "workoutSourceId": None, "shared": False}

def save(workout, filename):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        # ensure_ascii=True converts Polish chars to \uXXXX — required by Chrome importer
        json.dump(workout, f, ensure_ascii=True, separators=(",", ":"))
    print(f"Saved: {path}")

# ---------- workout type builders ----------

def build_easy(date, pace, duration_min, name_suffix=""):
    mins = int(duration_min)
    label = f"{date} Easy_{name_suffix}@{pace.replace(':', '-')}" if name_suffix else f"{date} Easy_@{pace.replace(':', '-')}"
    steps = [
        step_warmup_time(1, 300, pace, f"Rozgrzewka 5 min @{pace}/km."),
        step_interval_time(2, mins * 60, pace, f"Easy {mins} min @{pace}/km. HR max 145 bpm."),
        step_cooldown(3, pace, "Cooldown do domu. Naciśnij LAP po dotarciu."),
    ]
    w = make_workout(label, f"Easy {mins} min @{pace}/km.", steps)
    save(w, f"{date}_Easy_@{pace.replace(':', '-')}.json")

def build_easy_strides(date, pace, duration_min, strides=5):
    mins = int(duration_min)
    label = f"{date} Easy+Strides_@{pace.replace(':', '-')}"
    inner = [
        step_interval_dist_no_target(4, 100, "100m stride — kontrolowane przyspieszenie, nie sprint.", child_id=1),
        step_recovery(5, 60, "Pełna przerwa — trucht/marsz 60 sek.", child_id=1),
    ]
    steps = [
        step_warmup_time(1, 300, pace, f"Rozgrzewka 5 min @{pace}/km."),
        step_interval_time(2, mins * 60, pace, f"Easy {mins} min @{pace}/km. HR max 145 bpm."),
        repeat_group(3, strides, inner),
        step_cooldown(6, pace, "Cooldown do domu. Naciśnij LAP po dotarciu."),
    ]
    w = make_workout(label, f"Easy {mins} min + {strides}×100m strides.", steps)
    save(w, f"{date}_Easy+Strides_@{pace.replace(':', '-')}.json")

def build_shakeout(date, pace, duration_min, strides=4, race_pace="4:40"):
    mins = int(duration_min)
    label = f"{date} Shakeout_@{race_pace.replace(':', '-')}"
    inner = [
        step_interval_dist_no_target(4, 100, "100m stride — luźno, kontrolowanie. Nie sprint.", child_id=1),
        step_recovery(5, 60, "Trucht/marsz 60 sek.", child_id=1),
    ]
    steps = [
        step_warmup_time(1, 180, pace, f"Rozgrzewka 3 min @{pace}/km. Rozprostuj nogi."),
        step_interval_time(2, mins * 60, pace, f"Easy {mins} min @{pace}/km. Spokojnie."),
        repeat_group(3, strides, inner),
        step_interval_time(6, 60, race_pace, f"1 min @{race_pace}/km — przypomnienie race pace. Krótko."),
        step_cooldown(7, pace, "Cooldown. Naciśnij LAP. Hydratacja, węgle, sen."),
    ]
    w = make_workout(label, f"Shakeout: easy {mins} min + {strides}×strides + 1×1min @{race_pace}.", steps)
    save(w, f"{date}_Shakeout_@{race_pace.replace(':', '-')}.json")

def build_intervals(date, easy_pace, int_pace, int_dist, reps, rec_secs=90):
    label = f"{date} Intervals_{reps}x{int_dist}m_@{int_pace.replace(':', '-')}"
    inner = [
        step_interval_dist(4, int_dist, int_pace, f"{int_dist}m @{int_pace}/km. Kontrolowane, równe splity.", child_id=1),
        step_recovery(5, rec_secs, f"Przerwa {rec_secs} sek trucht.", child_id=1),
    ]
    steps = [
        step_warmup_time(1, 600, easy_pace, f"Rozgrzewka 10 min @{easy_pace}/km."),
        step_warmup_lap(2, "Gotowy do interwałów? Naciśnij LAP."),
        repeat_group(3, reps, inner),
        step_cooldown(6, easy_pace, "Cooldown do domu. Naciśnij LAP."),
    ]
    w = make_workout(label, f"{reps}×{int_dist}m @{int_pace}/km, przerwa {rec_secs}s.", steps)
    save(w, f"{date}_Intervals_{reps}x{int_dist}m_@{int_pace.replace(':', '-')}.json")

def build_tempo(date, easy_pace, t_pace, t_duration_min):
    mins = int(t_duration_min)
    label = f"{date} Tempo_{mins}min_@{t_pace.replace(':', '-')}"
    steps = [
        step_warmup_time(1, 600, easy_pace, f"Rozgrzewka 10 min @{easy_pace}/km."),
        step_warmup_lap(2, "Gotowy? Naciśnij LAP."),
        step_interval_time(3, mins * 60, t_pace, f"Tempo {mins} min @{t_pace}/km. Comfortably hard — możesz mówić urywane zdania."),
        step_cooldown(4, easy_pace, "Cooldown do domu. Naciśnij LAP."),
    ]
    w = make_workout(label, f"Tempo ciągłe {mins} min @{t_pace}/km.", steps)
    save(w, f"{date}_Tempo_{mins}min_@{t_pace.replace(':', '-')}.json")

def build_race_hm(date, p1, p2, p3):
    label = f"{date} RACE_HM_21km"
    steps = [
        step_warmup_time(1, 900, "6:30", "Rozgrzewka 15 min @6:30/km + dynamika. 4 strides na koniec."),
        step_warmup_lap(2, "Stój na linii startu — LAP przy strzale."),
        step_interval_dist(3, 5000,  p1, f"0–5km @{p1}/km. KONTROLA. Nie daj się ponieść tłumowi."),
        step_interval_dist(4, 10000, p2, f"5–15km @{p2}/km. RYTM. Żel/woda na każdym punkcie."),
        step_interval_dist(5, 6097,  p3, f"15–21,1km @{p3}/km. PUSH! Wszystko co masz."),
        step_cooldown(6, "6:30", "META! Marsz/trucht. Naciśnij LAP. Hydratacja."),
    ]
    w = make_workout(label, f"Półmaraton. Strategia: {p1} / {p2} / push {p3}.", steps)
    save(w, f"{date}_RACE_HM_21km.json")

def fix_encoding(path_str):
    """Re-encode existing JSON file: replace raw Polish chars with \\uXXXX."""
    p = Path(path_str)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, separators=(",", ":"))
    print(f"Fixed encoding: {p}")

# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description="Garmin workout JSON generator")
    parser.add_argument("type", choices=["easy", "easy_strides", "shakeout", "intervals", "tempo", "race_hm", "fix-encoding"])
    parser.add_argument("date_or_path", nargs="?", help="YYYY.MM.DD or file path for fix-encoding")
    parser.add_argument("pace", nargs="?", help="Easy/main pace M:SS")
    parser.add_argument("duration", nargs="?", type=int, help="Duration in minutes (easy section)")
    parser.add_argument("--strides",     type=int,   default=5,     help="Number of strides (default 5)")
    parser.add_argument("--race-pace",   default="4:40",            help="Race pace for shakeout/strides")
    parser.add_argument("--int-pace",    default="4:44",            help="Interval pace")
    parser.add_argument("--int-dist",    type=int,   default=1000,  help="Interval distance in m")
    parser.add_argument("--reps",        type=int,   default=4,     help="Number of repetitions")
    parser.add_argument("--rec",         type=int,   default=90,    help="Recovery seconds")
    parser.add_argument("--t-pace",      default="4:55",            help="Tempo pace")
    parser.add_argument("--t-duration",  type=int,   default=20,    help="Tempo duration in minutes")
    parser.add_argument("--p1",          default="4:40",            help="HM segment 1 pace (0–5km)")
    parser.add_argument("--p2",          default="4:38",            help="HM segment 2 pace (5–15km)")
    parser.add_argument("--p3",          default="4:30",            help="HM segment 3 pace (15–21km)")
    args = parser.parse_args()

    t = args.type
    if t == "fix-encoding":
        fix_encoding(args.date_or_path)
    elif t == "easy":
        build_easy(args.date_or_path, args.pace, args.duration)
    elif t == "easy_strides":
        build_easy_strides(args.date_or_path, args.pace, args.duration, args.strides)
    elif t == "shakeout":
        build_shakeout(args.date_or_path, args.pace, args.duration, args.strides, args.race_pace)
    elif t == "intervals":
        build_intervals(args.date_or_path, args.pace or "6:20", args.int_pace, args.int_dist, args.reps, args.rec)
    elif t == "tempo":
        build_tempo(args.date_or_path, args.pace or "6:20", args.t_pace, args.t_duration)
    elif t == "race_hm":
        build_race_hm(args.date_or_path, args.p1, args.p2, args.p3)

if __name__ == "__main__":
    main()
