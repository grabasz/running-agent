"""Zapis makroplanu Cracovia 2027: plan panelu AI (active) + deterministyczny (shadow).

Użycie:  python scripts/seed_macro_cracovia.py [--user-id 1] [--dry-run]
Ponowne uruchomienie archiwizuje poprzednie wersje (status active/shadow) i zapisuje od nowa.
"""
from __future__ import annotations
import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "db"))

import api  # noqa: E402
from planner import repo, plan_detail  # noqa: E402
from planner.macro import MacroInput, build_macrocycle  # noqa: E402
from planner.events import TuneUp  # noqa: E402
from planner.seeds import cracovia_2027_panel as S  # noqa: E402

KIND_PATTERNS = [("race", r"START"), ("T", r"\bT\b"), ("I", r"\bI\b"), ("MLR", r"MLR"), ("M", r"@M")]


def _quality(key: str, long_structure: str) -> list[dict]:
    text = f"{key} {long_structure}"
    return [{"kind": k, "km": 0.0} for k, pat in KIND_PATTERNS if re.search(pat, text)]


def ai_weeks() -> list[dict]:
    out, seen = [], {}
    for ws, phase, km, deload, long_km, ls, key, notes in S.W:
        seen[phase] = seen.get(phase, 0) + 1
        out.append({"week_start": ws, "phase": phase, "week_in_phase": seen[phase],
                    "is_deload": bool(deload), "is_race_week": ws == "2027-04-12",
                    "target_km": km, "long_km": long_km, "long_structure": ls,
                    "key_session": key, "notes": notes, "quality": _quality(key, ls)})
    return out


def deterministic_input() -> MacroInput:
    """Te same fakty i reguły, które dostał panel AI — uczciwe porównanie."""
    return MacroInput(
        start=date(2026, 11, 23), baseline_km=S.GOAL["baseline_km"], vdot=52.0,
        race_date=date(2027, 4, 18), distance_km=42.195, peak_km=68, progression="weekly",
        tune_ups=(TuneUp(date(2026, 12, 31), 10.0, "B"), TuneUp(date(2027, 3, 7), 21.0975, "B")),
        quality_caps=((date(2026, 12, 31), 1),), kind_bans=(("R", date(2027, 2, 1), "S"),),
        long_start_km=18.5, long_step_km=3, long_cap_km=33, forced_deloads=(date(2026, 12, 21),))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ai, det = ai_weeks(), build_macrocycle(deterministic_input())
    print(f"AI: {len(ai)} tyg., {sum(w['target_km'] for w in ai)} km | "
          f"DET: {len(det)} tyg., {round(sum(w.target_km for w in det))} km")
    if a.dry_run:
        return
    with api.connect() as conn:
        gid = repo.save_goal(conn, a.user_id, dict(S.GOAL), ai)
        plan_detail.add_rules(conn, a.user_id, gid, [
            dict(zip(("rule_type", "subject", "value", "valid_from", "valid_to", "reason"), r))
            for r in S.RULES])
        plan_detail.add_paces(conn, a.user_id, gid, [
            dict(zip(("zone", "min_sec", "max_sec", "valid_from", "source"), p)) for p in S.PACES])
        plan_detail.add_revision(conn, a.user_id, gid, "created",
                                 "Panel AI 2 trenerów (Pfitzinger × Magness), 2 rundy; Lago HM 07.03")
        sid = repo.save_goal(conn, a.user_id, {**S.GOAL, "status": "shadow", "source": "deterministic",
                                               "methodology": "planner v2 (weekly, reguły usera)"}, det)
        conn.commit()
    print(f"active goal_id={gid}, shadow goal_id={sid}")


if __name__ == "__main__":
    main()
