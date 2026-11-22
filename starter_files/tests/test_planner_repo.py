"""Testy warstwy DB planera (planner/repo.py + db/queries/macro.sql) na SQLite in-memory."""
from __future__ import annotations
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "db"))

import pytest  # noqa: E402

from planner import repo, build_macrocycle, render_week, MacroInput  # noqa: E402


@pytest.fixture
def tmp_conn():
    """schema.sql + migracja 011. Nie używamy conftest.tmp_conn: odpalanie 008 na
    już-finalnej schemie zostawia FK components → _planned_workouts_old."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
    conn.executescript((ROOT / "db" / "migrations" / "011_training_goals_macro.sql").read_text(encoding="utf-8"))
    yield conn
    conn.close()

TODAY = date(2026, 11, 25)   # środa
MON = date(2026, 11, 23)


def _seed(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        INSERT INTO runs (user_id, date, distance_km) VALUES
            (1, '2026-11-17', 10), (1, '2026-11-22', 15.5), (1, '2026-11-10', 8),
            (2, '2026-11-17', 99);
        INSERT INTO vdot_history (user_id, date, vdot) VALUES (1, '2026-05-10', 55);
        INSERT INTO body_state (user_id, date, location, pain_0_10) VALUES (1, '2026-11-21', 'kolano', 4);
    """)


def test_load_context(tmp_conn):
    _seed(tmp_conn)
    ctx = repo.load_context(tmp_conn, 1, TODAY)
    assert ctx["vdot"] == 55
    assert ctx["actual_km"]["2026-11-16"] == 25.5          # user 2 nie przecieka
    assert ctx["completed_weeks_km"] == [0.0, 0.0, 8.0, 25.5]
    assert ctx["max_pain_7d"] == 4
    assert ctx["prefs"]["group_days"]                        # z seeda users (schema)


def test_save_goal_and_reference(tmp_conn):
    weeks = build_macrocycle(MacroInput(start=MON, baseline_km=30, vdot=55,
                                        race_date=date(2027, 3, 21), distance_km=21.0975))
    goal = dict(race_id=None, name="HM test", race_date="2027-03-21", distance_km=21.0975,
                target_time_sec=5700, start_date=MON.isoformat(), baseline_km=30,
                peak_km=None, runs_per_week=5)
    gid = repo.save_goal(tmp_conn, 1, goal, weeks)
    gid2 = repo.save_goal(tmp_conn, 1, {**goal, "name": "HM v2"}, weeks)
    active = repo.load_context(tmp_conn, 1, TODAY)["goal"]
    assert active["id"] == gid2 != gid
    ref = repo.reference_weeks(tmp_conn, 1, gid2)
    assert len(ref) == len(weeks) and isinstance(ref[0]["quality"], list)


def test_write_week_keeps_gym_and_done(tmp_conn):
    tmp_conn.executescript("""
        INSERT INTO planned_workouts (user_id, date, week_start, type_id, status_id, title)
        VALUES (1, '2026-11-24', '2026-11-23', 8, 1, 'Siłownia A'),
               (1, '2026-11-23', '2026-11-23', 1, 2, 'Easy wykonany'),
               (1, '2026-11-26', '2026-11-23', 1, 1, 'Stary easy do nadpisania');
    """)
    week = build_macrocycle(MacroInput(start=MON, baseline_km=40, vdot=55, horizon_weeks=1))[0]
    days = render_week(week, 55, {"run_days": [0, 1, 3, 4, 6]})
    res = repo.write_week(tmp_conn, 1, MON, days)
    rows = tmp_conn.execute(
        "SELECT title FROM planned_workouts WHERE user_id=1 ORDER BY date").fetchall()
    titles = [r["title"] for r in rows]
    assert "Siłownia A" in titles and "Easy wykonany" in titles
    assert "Stary easy do nadpisania" not in titles
    assert "2026-11-23" in res["skipped_dates"]              # nie dubluj wykonanego easy
    assert res["inserted"] == len(days) - 1
