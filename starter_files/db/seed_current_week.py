"""Example: seed planned_workouts for a single week.

This is a template — edit `WEEK_START` and `PLAN` to reflect your own week,
then run:  python db/seed_current_week.py

It is idempotent: existing rows for the same week_start are deleted before
the new plan is inserted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import api  # type: ignore


WEEK_START = "2026-01-06"  # Monday — change to your target week

# Each entry: (date, type_key, title, target_distance_km, target_pace_sec/km,
#              target_hr_max, weather_temp, weather_note, notes)
# type_key must exist in workout_types (see schema.sql seed rows).
PLAN = [
    ("2026-01-06", "easy",       "Easy 6 km @ conversational pace",
     6.0, 390, 145, None, None, "Warm up 10min, then steady."),
    ("2026-01-07", "tempo",      "Tempo — 2km warm + 4km @ T + 2km cool",
     8.0, 265, 165, None, None, "T pace = comfortably hard, not race pace."),
    ("2026-01-08", "easy",       "Easy 5 km + 4x100m strides",
     5.0, 390, 145, None, None, "Strides = form work, not sprints."),
    ("2026-01-09", "strength_a", "Strength A (lower body + core)",
     None, None, None, None, None, "Squat / RDL / plank progression."),
    ("2026-01-10", "rest",       "REST + mobility 30min",
     None, None, None, None, None, "Foam roll, hips, IT band."),
    ("2026-01-11", "long",       "Long run 14 km — steady effort",
     14.0, 380, 152, None, None, "Fuel + hydrate. Last 20% slightly faster if legs OK."),
    ("2026-01-12", "easy",       "Easy 5 km recovery (or REST if fatigued)",
     5.0, 400, 140, None, None, "Listen to the body."),
]


def seed():
    with api.connect() as conn:
        # Look up type IDs once
        type_ids = {row["key"]: row["id"] for row in api.planned.list_types(conn)}

        # Clear existing rows for this week (idempotent re-runs)
        api.planned.delete_week(conn, week_start=WEEK_START)

        for date, type_key, title, dist, pace, hr_max, temp, weather_note, notes in PLAN:
            type_id = type_ids.get(type_key)
            if not type_id:
                print(f"  ! unknown type: {type_key}", file=sys.stderr)
                continue
            api.planned.add(conn,
                date=date,
                week_start=WEEK_START,
                type_id=type_id,
                status_id=1,  # planned
                title=title,
                target_distance_km=dist,
                target_duration_min=None,
                target_pace_sec_per_km=pace,
                target_hr_max=hr_max,
                notes=notes,
                weather_temp_c=temp,
                weather_note=weather_note,
            )

        rows = list(api.planned.week_plan(conn, week_start=WEEK_START))
        print(f"[seed] week {WEEK_START}: {len(rows)} planned workouts")
        for r in rows:
            dist = f"{r['target_distance_km']}km" if r['target_distance_km'] else "—"
            print(f"  {r['date']}  {r['type_icon']} {r['type_display']:14} {r['status_icon']} {dist:8} {r['title'][:55]}")


if __name__ == "__main__":
    seed()
