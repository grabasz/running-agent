"""Thin Turso (libsql) wrapper for the Telegram bot.

Bot pisze BEZPOSREDNIO do Turso — brak lokalnego SQLite. To upraszcza deploy
(stateless container, brak volume mount na Fly.io).

Zwracamy dict-y (rows), nie sqlite3.Row — libsql zwraca tuple, konwertujemy
przez description. Uzywamy positional `?` placeholders + tuple params.

Wzorzec retry: jesli Hrana stream padnie miedzy handlerami (bot idle > 5 min),
przy nastepnym execute() dostaniemy stream-not-found. `_retry` zamyka polaczenie
i otwiera swieze — max 3 proby.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import libsql

from config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN


def _is_stream_err(e: BaseException) -> bool:
    m = str(e)
    return "stream not found" in m or "stream expired" in m or "STREAM_EXPIRED" in m


class TursoDB:
    """Wrapper z auto-reconnect na Hrana stream expiry.

    Nie trzymaj instancji miedzy handlerami dluzej niz ~1 min — kazdy handler
    tworzy swoja instancje przez `with TursoDB() as db: ...`. Dziesiatki
    polaczen na godzine to zero problem dla Turso free tier.
    """

    def __init__(self) -> None:
        self.conn = libsql.connect(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _reconnect(self):
        self.close()
        self.conn = libsql.connect(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)

    def _execute(self, sql: str, params: tuple = ()):
        for attempt in range(3):
            try:
                return self.conn.execute(sql, params)
            except ValueError as e:
                if _is_stream_err(e) and attempt < 2:
                    self._reconnect()
                    continue
                raise

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.fetchall(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        cur = self._execute(sql, params)
        self.conn.commit()
        return cur.lastrowid if cur.lastrowid else 0


# ============================================================
# Date helpers
# ============================================================

def today_iso() -> str:
    return date.today().isoformat()


def tomorrow_iso() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def monday_of(d: date | None = None) -> str:
    d = d or date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


# ============================================================
# PLANNED WORKOUTS
# ============================================================

_PLANNED_SELECT = """
SELECT p.id, p.date, p.week_start, p.title, p.notes,
       p.target_distance_km, p.target_duration_min,
       p.target_pace_sec_per_km, p.target_hr_max,
       p.weather_temp_c, p.weather_note,
       p.actual_run_id, p.actual_session_id, p.actual_notes,
       t.key AS type_key, t.display_pl AS type_display,
       t.category AS type_category, t.icon AS type_icon,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses s ON s.id = p.status_id
"""


def planned_today(db: TursoDB) -> list[dict]:
    return db.fetchall(_PLANNED_SELECT + " WHERE p.date = ? ORDER BY p.id", (today_iso(),))


def planned_for_date(db: TursoDB, d: str) -> list[dict]:
    return db.fetchall(_PLANNED_SELECT + " WHERE p.date = ? ORDER BY p.id", (d,))


def planned_week(db: TursoDB, week_start: str | None = None) -> list[dict]:
    ws = week_start or monday_of()
    return db.fetchall(
        _PLANNED_SELECT + " WHERE p.week_start = ? ORDER BY p.date, p.id",
        (ws,),
    )


def planned_add(
    db: TursoDB,
    *,
    date: str,
    week_start: str,
    type_key: str,
    title: str,
    target_distance_km: float | None = None,
    target_pace_sec_per_km: int | None = None,
    target_hr_max: int | None = None,
    notes: str | None = None,
) -> int:
    tid = db.fetchone("SELECT id FROM workout_types WHERE key = ?", (type_key,))
    if not tid:
        raise ValueError(f"Nieznany typ workoutu: {type_key}")
    return db.execute(
        """
        INSERT INTO planned_workouts
            (date, week_start, type_id, status_id, title, target_distance_km,
             target_pace_sec_per_km, target_hr_max, notes)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
        """,
        (date, week_start, tid["id"], title, target_distance_km,
         target_pace_sec_per_km, target_hr_max, notes),
    )


def week_has_plan(db: TursoDB, week_start: str) -> bool:
    row = db.fetchone(
        "SELECT COUNT(*) AS n FROM planned_workouts WHERE week_start = ?",
        (week_start,),
    )
    return bool(row and row["n"] > 0)


# ============================================================
# RUNS + GYM
# ============================================================

def last_run(db: TursoDB) -> dict | None:
    return db.fetchone(
        """
        SELECT id, date, start_time, name, distance_km, moving_sec,
               pace_sec_per_km, hr_avg, hr_max, cadence_avg,
               ground_contact_ms, gct_balance_left_pct, vertical_oscillation_cm,
               stride_length_cm, elevation_gain_m, training_effect_aerobic,
               training_load, type, notes, source
          FROM runs
         ORDER BY date DESC, id DESC
         LIMIT 1
        """
    )


def last_gym(db: TursoDB) -> dict | None:
    return db.fetchone(
        """
        SELECT id, date, duration_min, hr_avg, hr_max, calories, context, notes
          FROM gym_sessions
         ORDER BY date DESC, id DESC
         LIMIT 1
        """
    )


def gym_sets(db: TursoDB, session_id: int) -> list[dict]:
    return db.fetchall(
        """
        SELECT exercise, set_num, reps, duration_sec, weight_kg,
               weight_per_side, rpe, notes
          FROM gym_sets
         WHERE session_id = ?
         ORDER BY id
        """,
        (session_id,),
    )


# ============================================================
# TASKS / GOALS / NOTES  (Faza 17)
# ============================================================

VALID_TASK_CATEGORIES = {"sport", "praca", "dom", "relacje", "zdrowie", "inne"}
VALID_NOTE_CATEGORIES = {"insight", "decision", "reminder", "idea"}


def add_note(
    db: TursoDB,
    *,
    category: str,
    content: str,
    related_task_id: int | None = None,
    related_run_id: int | None = None,
    related_session_id: int | None = None,
    source: str = "telegram",
) -> int:
    if category not in VALID_NOTE_CATEGORIES:
        raise ValueError(
            f"Kategoria {category!r} nie jest jedna z: {sorted(VALID_NOTE_CATEGORIES)}"
        )
    return db.execute(
        """
        INSERT INTO notes (date, category, content, related_task_id,
                           related_run_id, related_session_id, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (today_iso(), category, content, related_task_id,
         related_run_id, related_session_id, source),
    )


def recent_notes(db: TursoDB, limit: int = 10, category: str | None = None) -> list[dict]:
    if category:
        return db.fetchall(
            """
            SELECT id, date, category, content, source
              FROM notes WHERE category = ?
             ORDER BY date DESC, id DESC LIMIT ?
            """,
            (category, limit),
        )
    return db.fetchall(
        """
        SELECT id, date, category, content, source
          FROM notes ORDER BY date DESC, id DESC LIMIT ?
        """,
        (limit,),
    )


def add_task(
    db: TursoDB,
    *,
    category: str,
    title: str,
    parent_id: int | None = None,
    description: str | None = None,
    success_criteria: str | None = None,
    due_date: str | None = None,
    priority: str | None = None,
) -> int:
    if category not in VALID_TASK_CATEGORIES:
        raise ValueError(
            f"Kategoria {category!r} nie jest jedna z: {sorted(VALID_TASK_CATEGORIES)}"
        )
    return db.execute(
        """
        INSERT INTO tasks (parent_id, category, title, description,
                           success_criteria, due_date, priority, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (parent_id, category, title, description, success_criteria,
         due_date, priority),
    )


def tasks_open(db: TursoDB, category: str | None = None) -> list[dict]:
    if category:
        return db.fetchall(
            """
            SELECT id, parent_id, category, title, description,
                   due_date, priority, status
              FROM tasks
             WHERE status = 'open' AND category = ?
             ORDER BY (due_date IS NULL), due_date, id
            """,
            (category,),
        )
    return db.fetchall(
        """
        SELECT id, parent_id, category, title, description,
               due_date, priority, status
          FROM tasks
         WHERE status = 'open'
         ORDER BY category, (due_date IS NULL), due_date, id
        """
    )


def task_by_id(db: TursoDB, task_id: int) -> dict | None:
    return db.fetchone(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    )


def task_mark_done(db: TursoDB, task_id: int) -> None:
    db.execute(
        """
        UPDATE tasks SET status = 'done',
                         done_at = datetime('now'),
                         updated_at = datetime('now')
         WHERE id = ?
        """,
        (task_id,),
    )


def task_reopen(db: TursoDB, task_id: int) -> None:
    db.execute(
        """
        UPDATE tasks SET status = 'open',
                         done_at = NULL,
                         updated_at = datetime('now')
         WHERE id = ?
        """,
        (task_id,),
    )


def upsert_goal(db: TursoDB, *, week_start: str, category: str, goal: str) -> None:
    if category not in VALID_TASK_CATEGORIES:
        raise ValueError(
            f"Kategoria {category!r} nie jest jedna z: {sorted(VALID_TASK_CATEGORIES)}"
        )
    db.execute(
        """
        INSERT INTO weekly_goals (week_start, category, goal, status)
        VALUES (?, ?, ?, 'open')
        ON CONFLICT(week_start, category) DO UPDATE SET
            goal = excluded.goal,
            status = excluded.status,
            updated_at = datetime('now')
        """,
        (week_start, category, goal),
    )


def week_goals(db: TursoDB, week_start: str | None = None) -> list[dict]:
    ws = week_start or monday_of()
    return db.fetchall(
        """
        SELECT id, week_start, category, goal, status
          FROM weekly_goals
         WHERE week_start = ?
         ORDER BY category
        """,
        (ws,),
    )


# ============================================================
# BODY STATE
# ============================================================

def log_body(
    db: TursoDB,
    *,
    location: str,
    pain_0_10: int | None = None,
    doms: bool = False,
    notes: str | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO body_state (date, location, pain_0_10, doms, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date, location) DO UPDATE SET
            pain_0_10 = excluded.pain_0_10,
            doms = excluded.doms,
            notes = excluded.notes
        """,
        (today_iso(), location, pain_0_10, 1 if doms else 0, notes),
    )
