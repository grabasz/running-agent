"""Map Garmin strength_training activity → DB (gym_sessions + gym_sets).
Also regenerate gym_log.md from last N sessions in DB.

Garmin gives AGGREGATED data per exercise (summarizedExerciseSets):
- reps: TOTAL across all sets
- volume: total kg (grams × reps × weight)
- maxWeight: in grams
- duration: in ms (TOTAL across sets)
- sets: number of sets

No per-set granular data (12+12+12 treated as "3 sets of ~12 reps each").
Heuristic: reps_per_set = total_reps / sets (rounded).

Usage:
    1. From Claude (after fetching via mcp__garmin__list-activities + get-activity):
       save_strength(activity_dto) → session_id
    2. CLI: python silownia_save.py <activity.json>
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "db"))
import api  # type: ignore


# Mapping Garmin (category, subCategory) → display name (PL, as in gym_log.md)
# Names match the project convention (BSS, RDL etc).
EXERCISE_MAP = {
    ("CORE", "DEAD_BUG"):                              "Dead bug",
    ("CORE", "BIRD_DOG"):                              "Bird dog",
    ("CORE", None):                                    "Cwiczenia na tulow",
    ("PLANK", "PLANK"):                                "Plank",
    ("PLANK", "SIDE_PLANK"):                           "Deska boczna",
    ("PLANK", "SIDE_PLANK_LEG_LIFT"):                  "Deska boczna z uniesieniem nogi",
    ("SQUAT", "GOBLET_SQUAT"):                         "Goblet squat",
    ("SQUAT", "BACK_SQUAT"):                           "Przysiad ze sztanga",
    ("LUNGE", "DUMBBELL_BULGARIAN_SPLIT_SQUAT"):       "BSS",
    ("LUNGE", "BARBELL_BULGARIAN_SPLIT_SQUAT"):        "BSS sztanga",
    ("LUNGE", "DUMBBELL_LUNGE"):                       "Wykrok hantle",
    ("DEADLIFT", "ROMANIAN_DEADLIFT"):                 "RDL",
    ("DEADLIFT", "BARBELL_DEADLIFT"):                  "Martwy ciag sztanga",
    ("CALF_RAISE", "STANDING_CALF_RAISE"):             "Wspiecia lydek stojac",
    ("CALF_RAISE", "SINGLE_LEG_STANDING_CALF_RAISE"):  "Wspiecia lydek jednonoz",
    ("ROW", "BARBELL_ROW"):                            "Wioslowanie sztanga",
    ("ROW", "DUMBBELL_ROW"):                           "Wioslowanie hantle",
    ("ROW", "FACE_PULL"):                              "Przyciaganie do twarzy",
    ("BENCH_PRESS", "DUMBBELL_BENCH_PRESS"):           "Wyciskanie hantli na lawce",
    ("BENCH_PRESS", "BARBELL_BENCH_PRESS"):            "Wyciskanie sztangi na lawce",
    ("CURL", "DUMBBELL_BICEPS_CURL"):                  "Uginanie ramion hantle",
    ("CURL", None):                                    "Uginanie ramion",
    ("SHOULDER_PRESS", "OVERHEAD_DUMBBELL_PRESS"):     "OHP hantle",
    ("SHOULDER_STABILITY", "STANDING_L_RAISE"):        "L-raise",
    ("PULL_UP", "PULL_UP"):                            "Podciaganie",
    ("PUSH_UP", "PUSH_UP"):                            "Pompki",
    ("CARDIO", None):                                  "Kardio",
    ("CARDIO", ""):                                    "Kardio",
    ("UNKNOWN", None):                                 "Nieznane cwiczenie",
}


def map_exercise(category: str, sub_category: str | None) -> str:
    """Map Garmin (category, subCategory) → display name."""
    if sub_category == "":
        sub_category = None
    name = EXERCISE_MAP.get((category, sub_category))
    if name:
        return name
    # Fallback: subCategory if present, else category
    if sub_category:
        return sub_category.replace("_", " ").title()
    return category.replace("_", " ").title()


def save_strength(activity: dict, context: str | None = None, notes: str | None = None) -> int:
    """Save Garmin strength session to DB. Returns session_id.

    Args:
        activity: element from list-activities with `summarizedExerciseSets` (or get-activity)
        context: extra context (e.g. "Silownia A + Prehab pod kolano")
        notes: extra notes
    """
    # Date from startTimeLocal
    start_local = activity.get("startTimeLocal", "")
    date = start_local.split(" ")[0] if start_local else ""

    # Duration in minutes (Garmin gives seconds)
    duration_min = int(round((activity.get("duration") or 0) / 60))

    # Auto-context from activity name if not provided
    if not context:
        context = activity.get("activityName") or "Strength training"

    with api.connect() as conn:
        # Does this session already exist? Match by date + duration_min (±2 min tolerance)
        existing = conn.execute(
            "SELECT id FROM gym_sessions WHERE date = ? AND ABS(COALESCE(duration_min, 0) - ?) <= 2 LIMIT 1",
            (date, duration_min)
        ).fetchone()

        if existing:
            session_id = existing["id"]
            # Remove old sets — we'll rebuild from Garmin
            conn.execute("DELETE FROM gym_sets WHERE session_id = ?", (session_id,))
            # Update session metadata
            conn.execute(
                """UPDATE gym_sessions SET duration_min = ?, hr_avg = ?, hr_max = ?,
                       calories = ?, context = ?, notes = ? WHERE id = ?""",
                (duration_min,
                 int(activity["averageHR"]) if activity.get("averageHR") else None,
                 int(activity["maxHR"]) if activity.get("maxHR") else None,
                 int(activity.get("calories") or 0) or None,
                 context, notes, session_id)
            )
        else:
            session_id = api.gym.session_add(conn,
                date=date,
                duration_min=duration_min,
                hr_avg=int(activity["averageHR"]) if activity.get("averageHR") else None,
                hr_max=int(activity["maxHR"]) if activity.get("maxHR") else None,
                calories=int(activity.get("calories") or 0) or None,
                context=context,
                notes=notes,
            )

        # Sets from summarizedExerciseSets
        groups = activity.get("summarizedExerciseSets") or []
        for group in groups:
            category = group.get("category", "UNKNOWN")
            sub_cat = group.get("subCategory")
            exercise_name = map_exercise(category, sub_cat)

            n_sets = max(int(group.get("sets") or 1), 1)
            total_reps = int(group.get("reps") or 0)
            total_dur_ms = float(group.get("duration") or 0)
            max_weight_g = float(group.get("maxWeight") or 0)
            weight_kg = max_weight_g / 1000 if max_weight_g > 0 else None

            # Per-set heuristics (Garmin gives only aggregate)
            reps_per_set = total_reps // n_sets if total_reps > 0 else None
            dur_per_set_sec = int(total_dur_ms / n_sets / 1000) if total_dur_ms > 0 else None

            # Time-based exercises (plank, side plank): reps=0, duration matters
            is_time_based = total_reps == 0 and dur_per_set_sec and dur_per_set_sec > 0

            for set_num in range(1, n_sets + 1):
                api.gym.set_add(conn,
                    session_id=session_id,
                    exercise=exercise_name,
                    set_num=set_num,
                    reps=reps_per_set if not is_time_based else None,
                    duration_sec=dur_per_set_sec if is_time_based else None,
                    weight_kg=weight_kg,
                    weight_per_side=0,  # Garmin doesn't distinguish per-side
                    rest_sec=None,
                    rpe=None,
                    notes=None,
                )

        # Auto-link to planned workout for the same date (if any strength workout planned)
        match = api.planned.auto_link_session_for_date(conn, date=date)
        if match:
            api.planned.link_actual_session(conn, id=match["id"], session_id=session_id)

    return session_id


# ============================================
# Render gym_log.md from DB
# ============================================

def _fmt_weight(w: float | None, per_side: int) -> str:
    if w is None or w == 0:
        return "BW"
    side = "/strona" if per_side else ""
    return f"{w:g} kg{side}"


def render_gym_log(limit: int = 5) -> str:
    """Build markdown for last N sessions + current max-weight summary."""
    out = []
    out.append("# Gym Log — baza treningowa")
    out.append("")
    out.append(f"*Auto-generated {datetime.now():%Y-%m-%d %H:%M} — edytuj przez Claude/skrypt, nie ręcznie*")
    out.append("")

    with api.connect() as conn:
        sessions = list(api.gym.sessions_recent(conn, limit=limit))

        for s in sessions:
            out.append("---")
            out.append("")
            out.append(f"## {s['date']} — {s['context'] or 'Strength'}")
            out.append("")
            meta_parts = []
            if s["duration_min"]: meta_parts.append(f"**Czas:** {s['duration_min']} min")
            if s["hr_avg"]: meta_parts.append(f"HR śr {s['hr_avg']}")
            if s["hr_max"]: meta_parts.append(f"HR max {s['hr_max']}")
            if s["calories"]: meta_parts.append(f"{s['calories']} kcal")
            if meta_parts:
                out.append(" | ".join(meta_parts))
                out.append("")
            if s["notes"]:
                out.append(f"_Notatka:_ {s['notes']}")
                out.append("")

            # Group sets per exercise
            sets = list(api.gym.sets_for_session(conn, session_id=s["id"]))
            by_ex: dict[str, list] = {}
            for st in sets:
                by_ex.setdefault(st["exercise"], []).append(st)

            if by_ex:
                out.append("| Ćwiczenie | Serie | Powt. / Czas | Ciężar | Uwagi |")
                out.append("|-----------|-------|--------------|--------|-------|")
                for ex_name, ex_sets in by_ex.items():
                    n = len(ex_sets)
                    reps_repr = []
                    dur_repr = []
                    weights = []
                    notes_concat = []
                    for st in ex_sets:
                        if st["reps"]: reps_repr.append(str(st["reps"]))
                        if st["duration_sec"]: dur_repr.append(f"{st['duration_sec']}s")
                        if st["weight_kg"]: weights.append(_fmt_weight(st["weight_kg"], st["weight_per_side"]))
                        if st["notes"]: notes_concat.append(st["notes"])

                    if reps_repr:
                        rd = "+".join(reps_repr)
                    elif dur_repr:
                        rd = "/".join(dur_repr)
                    else:
                        rd = "—"
                    w = weights[0] if weights else "BW"
                    notes = "; ".join(set(notes_concat))[:80] if notes_concat else ""
                    out.append(f"| {ex_name} | {n} | {rd} | {w} | {notes} |")
                out.append("")

        # Current max-weight summary — top exercises in last 3 months
        out.append("---")
        out.append("")
        out.append("## Wzorzec aktualnych możliwości (ostatnie 90 dni)")
        out.append("")
        rows = conn.execute(
            """SELECT gs.exercise,
                      MAX(gs.weight_kg) AS max_w,
                      MAX(s.date) AS last_date,
                      MAX(gs.reps) AS top_reps
                 FROM gym_sets gs
                 JOIN gym_sessions s ON s.id = gs.session_id
                WHERE s.date >= date('now', '-90 days')
                  AND gs.weight_kg IS NOT NULL AND gs.weight_kg > 0
                GROUP BY gs.exercise
                ORDER BY max_w DESC"""
        ).fetchall()
        if rows:
            out.append("| Ćwiczenie | Max ciężar | Ostatnio | Top reps |")
            out.append("|-----------|------------|----------|----------|")
            for r in rows:
                out.append(f"| {r['exercise']} | {r['max_w']:g} kg | {r['last_date']} | {r['top_reps']} |")
        else:
            out.append("_Brak danych — dodaj sesje silowni._")

    return "\n".join(out) + "\n"


def update_gym_log_file(limit: int = 5):
    """Overwrite garmin_workouts/gym/gym_log.md with the current DB render."""
    path = ROOT / "garmin_workouts" / "gym" / "gym_log.md"
    path.write_text(render_gym_log(limit=limit), encoding="utf-8")
    return path


# ============================================
# CLI
# ============================================

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage:", file=sys.stderr)
        print("  python silownia_save.py <activity.json> [context]   # zapisz sesje + regen gym_log.md", file=sys.stderr)
        print("  python silownia_save.py --render-only [limit]       # tylko regen gym_log.md z DB", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--render-only":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        path = update_gym_log_file(limit=limit)
        print(f"<!-- regenerated {path} from DB (last {limit} sessions) -->", file=sys.stderr)
        print(render_gym_log(limit=limit))
        sys.exit(0)

    p1 = Path(sys.argv[1])
    data = json.loads(p1.read_text(encoding="utf-8"))
    activity = data[0] if isinstance(data, list) else data
    context = sys.argv[2] if len(sys.argv) > 2 else None

    session_id = save_strength(activity, context=context)
    print(f"<!-- saved session_id={session_id} (activityId={activity.get('activityId')}) -->", file=sys.stderr)

    # Regenerate gym_log.md
    path = update_gym_log_file(limit=5)
    print(f"<!-- regenerated {path.name} -->", file=sys.stderr)

    # Print rendered markdown
    print(render_gym_log(limit=5))
