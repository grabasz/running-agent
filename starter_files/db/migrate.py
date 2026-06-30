"""One-shot migrator: parse existing .md files and load into SQLite.

Run once after init_db.py:
    python db/migrate.py
    python db/migrate.py --reset   # clean slate

Context markdowns (plan_current, fitness, profile, groups) remain hand-edited.
Only STRUCTURED LOGS get migrated:
  - volume_log.md  -> weekly_volume
  - races.md       -> races (+ result fill-in from plan_current.md)
  - gym_log.md     -> gym_sessions + gym_sets (hardcoded — free-form format)
  - fitness.md     -> vdot_history
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

from init_db import init  # type: ignore
import api  # type: ignore

ROOT = Path(__file__).parent.parent

# ============================================
# Helpers
# ============================================

def parse_pace_to_sec(s: str) -> int | None:
    m = re.search(r"(\d+):(\d{2})", s)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None

def parse_time_to_sec(s: str) -> int | None:
    s = s.strip()
    parts = s.split(":")
    if len(parts) == 3:
        h, m, sec = parts
        return int(h) * 3600 + int(m) * 60 + int(sec)
    if len(parts) == 2:
        a, b = int(parts[0]), int(parts[1])
        if a <= 6 and b <= 59:  # h:mm for HM/marathon
            return a * 3600 + b * 60
        return a * 60 + b       # mm:ss for short races
    return None

def parse_duration_hm_to_sec(s: str) -> int | None:
    m = re.search(r"(\d+):(\d{2})", s)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 if m else None


# ============================================
# Migration: volume_log.md -> weekly_volume
# ============================================

def migrate_volume(conn):
    f = ROOT / "volume_log.md"
    count = 0
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(
            r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([\d.]+)\s*\|\s*\+\s*(\d+)m\s*\|\s*(\d+:\d+)h\s*\|\s*(\d+)\s*\|\s*([\d.]+)km\s*\|\s*([^|]*)\s*\|",
            line
        )
        if not m:
            continue
        week_start, dist, elev, dur_hm, n, longest, trend = m.groups()
        trend = trend.strip() or None
        if trend:
            if "peak" in trend: trend = "peak"
            elif "recovery" in trend: trend = "recovery"
            else: trend = None
        api.weekly_volume.upsert(conn,
            week_start=week_start, distance_km=float(dist), elevation_gain_m=int(elev),
            duration_sec=parse_duration_hm_to_sec(dur_hm) or 0,
            num_runs=int(n), longest_km=float(longest), trend=trend)
        count += 1
    print(f"[volume] migrated {count} weeks")


# ============================================
# Migration: races.md -> races
# ============================================

def migrate_races(conn):
    f = ROOT / "races.md"
    lines = f.read_text(encoding="utf-8").splitlines()
    count = 0

    DIST = {
        "HM": 21.0975, "Polmaraton": 21.0975, "Półmaraton": 21.0975,
        "Maraton": 42.195, "Cracovia Marathon": 42.195,
        "5km": 5.0, "Most Dębnicki": 5.0,
    }
    def guess_distance(name: str) -> float:
        for k, v in DIST.items():
            if k.lower() in name.lower():
                return v
        return 21.0975

    in_calendar = in_history = False
    for line in lines:
        if line.startswith("# KALENDARZ") or "kalendarz" in line.lower()[:30]:
            in_calendar, in_history = True, False
            continue
        if "historia start" in line.lower():
            in_calendar, in_history = False, True
            continue
        if not (in_calendar or in_history):
            continue

        if in_calendar:
            m = re.match(
                r"\|\s*\**(\d{1,2}\.\d{1,2})\**\s*\|\s*\w+\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|",
                line)
            if not m: continue
            date_str, name, target, strategy = m.groups()
            day, month = date_str.split(".")
            iso_date = f"2026-{int(month):02d}-{int(day):02d}"
            target_sec = None
            tm = re.search(r"sub\s*(\d):(\d{2})", target)
            if tm:
                target_sec = int(tm.group(1)) * 3600 + int(tm.group(2)) * 60
            api.races.add(conn,
                date=iso_date, name=name.strip(), distance_km=guess_distance(name),
                target_time_sec=target_sec, actual_time_sec=None, is_pb=0,
                place_overall=None, place_category=None, conditions_temp_c=None,
                strategy=strategy.strip() or None, notes=None)
            count += 1

        elif in_history:
            m = re.match(r"\|\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
            if not m: continue
            date_str, name, time_str = m.groups()
            d, mo, y = date_str.split(".")
            iso_date = f"{y}-{int(mo):02d}-{int(d):02d}"
            api.races.add(conn,
                date=iso_date, name=name.strip(), distance_km=guess_distance(name),
                target_time_sec=None, actual_time_sec=parse_time_to_sec(time_str.split()[0]),
                is_pb=0, place_overall=None, place_category=None,
                conditions_temp_c=None, strategy=None, notes=None)
            count += 1

    print(f"[races] migrated {count} entries")


def migrate_race_results(conn):
    """Fill in actual times for 3 HMs of 2026 (data from plan_current.md)."""
    RESULTS = [
        ("2026-05-10", parse_time_to_sec("1:39:37"), "PB, HR sr 166, mocna koncowka 4:17 km 21"),
        ("2026-06-06", parse_time_to_sec("1:59:53"), "Fun run, neg split, plan A wykonany"),
        ("2026-06-14", parse_time_to_sec("1:39:48"), "CNS fatigue: HR sr 173, koncowka -38s vs Bialystok"),
    ]
    for iso_date, sec, note in RESULTS:
        api.races.update_result(conn, date=iso_date, actual_time_sec=sec, notes=note)
    # Recompute PBs after inserting actuals
    api.races.recompute_pbs(conn)
    api.races.flag_pbs(conn)
    print(f"[race_results] updated {len(RESULTS)} actuals + recomputed PBs")


# ============================================
# Migration: fitness.md -> vdot_history
# ============================================

def migrate_vdot(conn):
    f = ROOT / "fitness.md"
    text = f.read_text(encoding="utf-8")
    count = 0
    for m in re.finditer(
        r"-\s*(\d{1,2}\.\d{1,2}\.\d{4}):\s*T-pace\s*~?(\d+:\d{2})/km.*?\(VDOT\s*~?(\d+)(?:-\d+)?\)\s*[—\-]?\s*(.*)",
        text
    ):
        date_str, t_pace, vdot, source = m.groups()
        d, mo, y = date_str.split(".")
        iso_date = f"{y}-{int(mo):02d}-{int(d):02d}"
        api.vdot.add(conn,
            date=iso_date, vdot=int(vdot),
            t_pace_sec=parse_pace_to_sec(t_pace),
            source=source.strip() or None, notes=None)
        count += 1
    print(f"[vdot] migrated {count} entries")


# ============================================
# Migration: gym_log.md -> gym_sessions + gym_sets (HARDCODED)
# ============================================

def migrate_gym(conn):
    # Session 1: 2026-05-18 — return after break
    s1 = api.gym.session_add(conn,
        date="2026-05-18", duration_min=63, hr_avg=126, hr_max=164, calories=477,
        context="Powrot po przerwie",
        notes="Ciezary konserwatywne — test mozliwosci.")
    SETS_1 = [
        ("Wioslowanie sztanga", 1, 10, 40, False, None, None),
        ("Wioslowanie sztanga", 2, 10, 40, False, None, None),
        ("Wioslowanie sztanga", 3, 11, 40, False, None, "ostatnia z nawiazka"),
        ("Wyciskanie hantli na lawce", 1, 10, 20, False, None, "rozgrzewka"),
        ("Wyciskanie hantli na lawce", 2, 10, 25, False, None, None),
        ("Wyciskanie hantli na lawce", 3, 10, 25, False, None, None),
        ("Przyciaganie do twarzy", 1, 10, 10, False, None, None),
        ("Przyciaganie do twarzy", 2, 10, 10, False, None, None),
        ("Przyciaganie do twarzy", 3, 10, 10, False, None, None),
        ("L-raise", 1, 10, 10, False, None, None),
        ("L-raise", 2, 10, 10, False, None, None),
        ("L-raise", 3, 10, 10, False, None, None),
        ("Uginanie ramion", 1, 10, 24, False, None, None),
        ("Uginanie ramion", 2, 6, 24, False, None, "zmeczenie"),
        ("Uginanie ramion", 3, 4, 25, False, None, "biceps wykonczony"),
    ]
    for ex, sn, reps, wt, ps, dur, n in SETS_1:
        api.gym.set_add(conn, session_id=s1, exercise=ex, set_num=sn,
            reps=reps, duration_sec=dur, weight_kg=wt, weight_per_side=int(ps),
            rest_sec=None, rpe=None, notes=n)

    # Session 2: 2026-06-27 — Silownia A + Prehab (knee-modified)
    s2 = api.gym.session_add(conn,
        date="2026-06-27", duration_min=90, hr_avg=None, hr_max=None, calories=None,
        context="Silownia A + Prehab pod kolano (valgus od Grodziska)",
        notes="Plan zalecal BSS @bodyweight, RDL lekko. Wzial ciezsze niz w planie ale kontrolowal. Bez bolu po sesji.")
    SETS_2 = [
        ("Goblet squat", 1, 12, 16, False, None, None),
        ("Goblet squat", 2, 12, 16, False, None, None),
        ("Goblet squat", 3, 12, 16, False, None, "+20% volume vs plan (10), forma OK"),
        ("BSS", 1, 16, 8, True, None, "plan @BW, wzial 2x8kg, kolano kontrolowal swiadomie"),
        ("BSS", 2, 16, 8, True, None, None),
        ("BSS", 3, 20, 8, True, None, "20 reps = zagapienie ze stoperem"),
        ("RDL", 1, 8, 40, False, None, "plan 22kg, wzial 40"),
        ("RDL", 2, 8, 40, False, None, "czuje semimembranosus prawej nogi"),
        ("RDL", 3, 10, 40, False, None, "kolano klikne po treningu = ustawilo sie"),
        ("Wspiecia lydek stojac", 1, 15, 20, False, None, "plan BW obunoz, wzial +20kg, lydka prawa OK"),
        ("Wspiecia lydek stojac", 2, 15, 20, False, None, None),
        ("Wspiecia lydek stojac", 3, 15, 20, False, None, None),
        ("Deska boczna", 1, None, None, False, 52, "izometryczne zamiast reps"),
        ("Deska boczna", 2, None, None, False, 82, None),
        ("Deska boczna", 3, None, None, False, 74, None),
        ("Plank", 1, None, None, False, 45, None),
        ("Plank", 2, None, None, False, 45, None),
        ("Plank", 3, None, None, False, 45, None),
        ("Dead bug", 1, 16, None, False, None, "8/strona"),
        ("Dead bug", 2, 16, None, False, None, None),
        ("Dead bug", 3, 4, None, False, None, "trzecia seria zmeczenie"),
    ]
    for ex, sn, reps, wt, ps, dur, n in SETS_2:
        api.gym.set_add(conn, session_id=s2, exercise=ex, set_num=sn,
            reps=reps, duration_sec=dur, weight_kg=wt, weight_per_side=int(ps),
            rest_sec=None, rpe=None, notes=n)

    print(f"[gym] migrated 2 sessions ({len(SETS_1) + len(SETS_2)} sets)")


# ============================================
# Migration: body_state seed for 2026-06-28
# ============================================

def migrate_body_state(conn):
    SEEDS = [
        ("2026-06-28", "posladki",     None, 1, "zakwasy po Silowni A 27.06 — glute medius/max pracowaly"),
        ("2026-06-28", "kolano_prawe", 2, 0,    "boli tylko przy przyklekaniu (pressure-based), chodzenie OK"),
        ("2026-06-28", "lydka_prawa",  0, 0,    None),
        ("2026-06-28", "krzyz",        0, 0,    "po RDL 40kg + meble dzien wczesniej — bez objawow"),
    ]
    for date, loc, pain, doms, note in SEEDS:
        api.body.state_log(conn, date=date, location=loc, pain_0_10=pain, doms=doms, notes=note)
    print(f"[body_state] seeded {len(SEEDS)} entries")


# ============================================
# Main
# ============================================

if __name__ == "__main__":
    reset = "--reset" in sys.argv
    init(reset=reset)
    print(f"\n--- Migrating {'(reset)' if reset else '(append)'} ---\n")
    with api.connect() as conn:
        migrate_volume(conn)
        migrate_races(conn)
        migrate_vdot(conn)
        migrate_race_results(conn)
        migrate_gym(conn)
        migrate_body_state(conn)
    print("\n--- Stats ---")
    for table, n in api.stats_summary().items():
        print(f"  {table:20} {n}")
