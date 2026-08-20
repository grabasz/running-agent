"""Wszystkie cached queries dashboardu.

Zgodnie z CODING_STANDARDS: cache osobno od render, user_id ZAWSZE parametr,
zero hardkodow user_id. Kazda funkcja zwraca list[dict] / DataFrame /
dict — nigdy connection ani cursor.

Query TTL:
  15s — bieżący tydzień (edycja statusów, chcemy szybko odświeżyć)
  30s — plan / body_state / notes / goals / tasks
  60s — trendy dlugoterminowe (weekly volume, runs, gym, races, VDOT, exercises, artifacts)
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

import api  # type: ignore

try:
    from crypto import maybe_decrypt as _maybe_decrypt
except ImportError:  # crypto module opcjonalny — fallback zwraca plaintext bez zmian
    def _maybe_decrypt(v, _user_id):
        return v


def _decrypt_fields(rows, user_id, fields):
    """Deszyfruj wskazane pola in-place na liscie dictow. Zwraca ta sama liste."""
    for r in rows:
        for f in fields:
            if f in r:
                r[f] = _maybe_decrypt(r[f], user_id)
    return rows


# ============================================
# Plan (planned_workouts + components)
# ============================================

@st.cache_data(ttl=30)
def q_today(user_id: int):
    with api.connect() as conn:
        return [dict(r) for r in api.planned.today(conn, user_id=user_id)]


@st.cache_data(ttl=30)
def q_upcoming(user_id: int, days=7):
    with api.connect() as conn:
        return [dict(r) for r in api.planned.upcoming(conn, user_id=user_id, days=f"+{days} days", limit=7)]


@st.cache_data(ttl=15)
def q_current_week_with_components(user_id: int):
    """Zwraca plany bieżącego tygodnia z komponentami zgroupowanymi per planned_id.

    Auto-migruje brakujące komponenty (splituje `title` po ` + `) — bez tego
    UI ma tylko caption "brak komponentów" zamiast selectboxów statusu.
    """
    from migrate_components import split_title  # type: ignore

    with api.connect() as conn:
        week = [dict(r) for r in api.planned.current_week(conn, user_id=user_id)]
        # 1) Auto-generate components for planned_workouts that have none yet
        for p in week:
            existing = list(api.planned.components_for(conn, planned_workout_id=p["id"]))
            if existing:
                continue
            parts = split_title(p.get("title") or "")
            if not parts:
                continue
            for idx, label in enumerate(parts):
                conn.execute("""
                    INSERT INTO planned_workout_components
                        (planned_workout_id, order_idx, label, status_id)
                    VALUES (?, ?, ?, ?)
                """, (p["id"], idx, label, p.get("status_id") or 1))
            conn.commit()
        # 2) Re-fetch fresh components
        by_planned: dict[int, list[dict]] = {}
        for p in week:
            comps = [dict(c) for c in api.planned.components_for(conn, planned_workout_id=p["id"])]
            by_planned[p["id"]] = comps
    # 3) Decrypt user-private text field
    _decrypt_fields(week, user_id, ["actual_notes"])
    return week, by_planned


# ============================================
# Trendy dlugoterminowe — runs, gym, weekly volume
# ============================================

@st.cache_data(ttl=60)
def q_weekly_volume(user_id: int, weeks=12):
    with api.connect() as conn:
        rows = [dict(r) for r in api.weekly_volume.recent(conn, user_id=user_id, weeks=weeks)]
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def q_runs_recent(user_id: int, limit=30):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.runs.recent(conn, user_id=user_id, limit=limit)])


@st.cache_data(ttl=60)
def q_runs_with_dynamics(user_id: int, since="-90 days"):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.runs.recent_with_dynamics(conn, user_id=user_id, since=since)])


@st.cache_data(ttl=60)
def q_gym_sessions(user_id: int, limit=20):
    with api.connect() as conn:
        return [dict(r) for r in api.gym.sessions_recent(conn, user_id=user_id, limit=limit)]


@st.cache_data(ttl=60)
def q_exercise_progression(user_id: int, exercise, limit=30):
    with api.connect() as conn:
        return pd.DataFrame([
            dict(r) for r in api.gym.exercise_progression(conn, user_id=user_id, exercise=exercise, limit=limit)
        ])


@st.cache_data(ttl=60)
def q_top_exercises(user_id: int, since="2026-01-01"):
    with api.connect() as conn:
        return pd.DataFrame([
            dict(r) for r in api.gym.top_exercises_by_volume(conn, user_id=user_id, since=since)
        ])


# ============================================
# Wyscigi + VDOT
# ============================================

@st.cache_data(ttl=60)
def q_races_upcoming(user_id: int):
    with api.connect() as conn:
        return [dict(r) for r in api.races.upcoming(conn, user_id=user_id)]


@st.cache_data(ttl=60)
def q_races_history(user_id: int):
    with api.connect() as conn:
        return [dict(r) for r in api.races.history(conn, user_id=user_id)]


@st.cache_data(ttl=60)
def q_vdot_history(user_id: int, limit=10):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.vdot.history(conn, user_id=user_id, limit=limit)])


# ============================================
# Body state / tasks / goals / notes (Rozkminy)
# ============================================

@st.cache_data(ttl=30)
def q_body_state(user_id: int, since="-14 days"):
    with api.connect() as conn:
        rows = [dict(r) for r in api.body.state_recent(conn, user_id=user_id, since=since)]
    return _decrypt_fields(rows, user_id, ["notes"])


@st.cache_data(ttl=30)
def q_tasks_all(user_id: int):
    with api.connect() as conn:
        rows = [dict(r) for r in api.tasks.list_all(conn, user_id=user_id)]
    return _decrypt_fields(rows, user_id, ["title", "description"])


@st.cache_data(ttl=30)
def q_goals_week(user_id: int, week_start):
    with api.connect() as conn:
        return {r["category"]: dict(r) for r in api.goals.for_week(conn, user_id=user_id, week_start=week_start)}


@st.cache_data(ttl=30)
def q_notes_recent(user_id: int, limit=30):
    with api.connect() as conn:
        rows = [dict(r) for r in api.notes.recent(conn, user_id=user_id, limit=limit)]
    return _decrypt_fields(rows, user_id, ["content"])


# ============================================
# Rutyna + katalog cwiczen
# ============================================

@st.cache_data(ttl=60)
def q_active_routine(user_id: int):
    """Zwraca aktualnie obowiazujaca rutyne (dzis wpada w [active_from, active_to])."""
    from datetime import datetime
    today = datetime.now().date().isoformat()
    with api.connect() as conn:
        r = conn.execute("""
            SELECT id, name, focus, total_time_min, active_from, active_to, notes
              FROM routines
             WHERE user_id = ?
               AND active_from <= ?
               AND (active_to IS NULL OR active_to >= ?)
             ORDER BY active_from DESC
             LIMIT 1
        """, (user_id, today, today)).fetchone()
        return dict(r) if r else None


@st.cache_data(ttl=60)
def q_routine_exercises(routine_id: int):
    with api.connect() as conn:
        rows = conn.execute("""
            SELECT re.position, re.duration_or_reps, re.notes AS re_notes,
                   e.id AS exercise_id, e.key, e.name, e.category, e.tool,
                   e.description_md, e.youtube_url
              FROM routine_exercises re
              JOIN exercises e ON re.exercise_id = e.id
             WHERE re.routine_id = ?
             ORDER BY re.position
        """, (routine_id,)).fetchall()
        return [dict(r) for r in rows]


@st.cache_data(ttl=60)
def q_all_routines(user_id: int):
    with api.connect() as conn:
        rows = conn.execute("""
            SELECT id, name, focus, total_time_min, active_from, active_to, notes
              FROM routines WHERE user_id = ?
             ORDER BY active_from DESC
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]


@st.cache_data(ttl=60)
def q_all_exercises():
    """Katalog cwiczen — nie filtruje po user_id (katalog jest wspolny)."""
    with api.connect() as conn:
        rows = conn.execute("""
            SELECT id, key, name, name_en, category, tool, description_md, youtube_url, updated_at
              FROM exercises
             ORDER BY category, name
        """).fetchall()
        return [dict(r) for r in rows]


# ============================================
# Artefakty sesji
# ============================================

@st.cache_data(ttl=60, show_spinner=False)
def q_artifacts(user_id: int, include_archived: bool = False):
    with api.connect() as conn:
        where = "user_id = ?"
        params: list = [user_id]
        if not include_archived:
            where += " AND archived = 0"
        rows = conn.execute(
            f"SELECT id, date, category, title, summary, content_md, source, archived, created_at "
            f"FROM session_artifacts WHERE {where} ORDER BY date DESC, id DESC",
            params
        ).fetchall()
        result = [dict(r) for r in rows]
    return _decrypt_fields(result, user_id, ["title", "summary", "content_md"])
