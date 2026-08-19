"""Callbacks — form submits, on_change handlers.

Zgodnie z CODING_STANDARDS: callbacks osobno od render code. Kazdy callback:
  1. Modyfikuje DB (INSERT/UPDATE) — w cloud mode zapis IDZIE BEZPOSREDNIO do Turso
     (bo api.connect() zwraca libsql conn). W local mode zapis do sqlite.
  2. Invaliduje cache (queries jak `q_*.clear()`)

2026-08-19 refactor: usuniete _push_life_to_turso / _push_artifacts_to_turso —
niepotrzebne, api.connect() od razu pisze do Turso w cloud mode.
"""
from __future__ import annotations
import streamlit as st

import api  # type: ignore

from dashboard import queries


# ============================================
# planned_workouts + components (Przeglad)
# ============================================

def _apply_component_status(component_id: int, planned_id: int, status_key: str, notes: str | None) -> None:
    """Callback: update komponentu, sync parent, uniewaznij cache."""
    with api.connect() as conn:
        api.planned.mark_component_status(
            conn, id=component_id, status_key=status_key, actual_notes=notes or None
        )
        api.planned.sync_parent_status_from_components(conn, planned_workout_id=planned_id)
    queries.q_current_week_with_components.clear()
    queries.q_today.clear()


def _apply_planned_status(planned_id: int, status_key: str, notes: str | None) -> None:
    """Callback: update parent planned_workout (fallback gdy brak komponentów)."""
    with api.connect() as conn:
        api.planned.mark_status(
            conn, id=planned_id, status_key=status_key, actual_notes=notes or None
        )
    queries.q_current_week_with_components.clear()
    queries.q_today.clear()


# ============================================
# Rozkminy — goals + tasks + notes
# ============================================

def _invalidate_life_cache():
    """Wyczysc cache queries uzywanych w page_life po write."""
    queries.q_tasks_all.clear()
    queries.q_goals_week.clear()
    queries.q_notes_recent.clear()


def _cb_goal_upsert(week_start: str, category: str, key: str):
    val = (st.session_state.get(key) or "").strip()
    if not val:
        return
    with api.connect() as conn:
        api.goals.upsert(conn, week_start=week_start, category=category,
                         goal=val, status=None)
    _invalidate_life_cache()


def _cb_goal_toggle(goal_id: int, current_status: str):
    with api.connect() as conn:
        if current_status == "open":
            api.goals.mark_done(conn, id=goal_id)
        else:
            api.goals.reopen(conn, id=goal_id)
    _invalidate_life_cache()


def _cb_task_toggle(task_id: int, current_status: str):
    with api.connect() as conn:
        if current_status == "open":
            api.tasks.mark_done(conn, id=task_id)
        else:
            api.tasks.reopen(conn, id=task_id)
    _invalidate_life_cache()


def _cb_task_delete(task_id: int):
    with api.connect() as conn:
        api.tasks.delete(conn, id=task_id)
    _invalidate_life_cache()


def _cb_note_delete(note_id: int):
    with api.connect() as conn:
        api.notes.delete(conn, id=note_id)
    _invalidate_life_cache()


# ============================================
# Legacy no-op shims (2026-08-19 refactor)
# ============================================
# W nowej architekturze api.connect() zapisuje BEZPOSREDNIO do Turso w cloud mode,
# wiec explicit push jest niepotrzebny. Shim zostaje zeby pages/artifacts.py i
# pages/life.py nie wymagaly zmian.

def _push_life_to_turso():
    """No-op — zapis do Turso odbywa sie inline w api.connect() w cloud mode."""
    return None


def _push_artifacts_to_turso():
    """No-op — zapis do Turso odbywa sie inline w api.connect() w cloud mode."""
    return None


# ============================================
# Cwiczenia — edycja YouTube URL + name_en
# ============================================

def _apply_exercise_edit(ex_id: int, url: str, name_en: str):
    with api.connect() as conn:
        conn.execute(
            "UPDATE exercises SET youtube_url=?, name_en=?, updated_at=datetime('now') WHERE id=?",
            (url.strip() or None, name_en.strip() or None, ex_id),
        )
    st.cache_data.clear()
