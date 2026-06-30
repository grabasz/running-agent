"""Seed planned_workouts table with the current week's plan (29.06–05.07).

This was previously in plan_current.md as the '📆 BIEŻĄCY TYDZIEŃ' table.
After running this, that markdown section can be removed — DB is the source of truth.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import api  # type: ignore


WEEK_START = "2026-06-29"  # Monday

# Each entry: (date, type_key, title, target_distance_km, target_pace_sec/km, target_hr_max, weather_temp, weather_note, notes)
PLAN = [
    ("2026-06-29", "rest",       "REST + foam roll + Codzienny Beton",                   None, None, None, 39, "upal 39C",
     "Kuba Piech odpuszczony (kolano + upal)"),
    ("2026-06-30", "easy",       "Easy 5-6 km @6:10 RANO (5-6:00), plasko",              5.5,  370,  145,  35, "upal 35C",
     "Krotko ze wzgledu na upal"),
    ("2026-07-01", "strength_b", "Silownia B (upper + core + prehab block)",             None, None, None, 34, "burza 84%",
     "Bez biegu - upal + burza popoludniowa"),
    ("2026-07-02", "easy",       "Easy 8 km @6:00 + 4x strides 100m",                    8.0,  360,  145,  25, "ochlodzenie",
     "Pierwszy chlod - wykorzystaj"),
    ("2026-07-03", "strength_a", "Silownia A z prehab (BSS @BW, RDL 40kg utrzymaj)",     None, None, None, 23, None,
     "Monitor kolano"),
    ("2026-07-04", "long",       "Long 14 km @6:00-6:15, plasko",                        14.0, 370,  150,  24, None,
     "Pierwszy long Fazy 1"),
    ("2026-07-05", "rest",       "REST + foam roll + mobility",                          None, None, None, 24, None,
     "Regeneracja przed Tydz 2"),
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
