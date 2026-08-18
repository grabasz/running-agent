"""Callbacks — form submits, on_change handlers.

Zgodnie z CODING_STANDARDS: callbacks osobno od render code. Kazdy callback:
  1. Modyfikuje DB (INSERT/UPDATE)
  2. Invaliduje cache (queries jak `q_*.clear()`)
  3. Push do Turso (best-effort, nie przerywa UI)
"""
from __future__ import annotations
from pathlib import Path
import streamlit as st

import api  # type: ignore

from dashboard import queries


ROOT = Path(__file__).resolve().parent.parent


# ============================================
# planned_workouts + components (Przeglad)
# ============================================

def _apply_component_status(component_id: int, planned_id: int, status_key: str, notes: str | None) -> None:
    """Callback: update komponentu, sync parent, push do Turso, unieważnij cache."""
    with api.connect() as conn:
        api.planned.mark_component_status(
            conn, id=component_id, status_key=status_key, actual_notes=notes or None
        )
        api.planned.sync_parent_status_from_components(conn, planned_workout_id=planned_id)
        conn.commit()
    queries.q_current_week_with_components.clear()
    queries.q_today.clear()
    try:
        from sync import push as _push  # type: ignore
        _push(verbose=False)
    except Exception as e:
        st.warning(f"Push do Turso nieudany: {e}")


def _apply_planned_status(planned_id: int, status_key: str, notes: str | None) -> None:
    """Callback: update parent planned_workout (fallback gdy brak komponentów)."""
    with api.connect() as conn:
        api.planned.mark_status(
            conn, id=planned_id, status_key=status_key, actual_notes=notes or None
        )
        conn.commit()
    queries.q_current_week_with_components.clear()
    queries.q_today.clear()
    try:
        from sync import push as _push  # type: ignore
        _push(verbose=False)
    except Exception as e:
        st.warning(f"Push do Turso nieudany: {e}")


# ============================================
# Rozkminy — goals + tasks + notes
# ============================================

def _invalidate_life_cache():
    """Wyczysc cache queries uzywanych w page_life po write."""
    queries.q_tasks_all.clear()
    queries.q_goals_week.clear()
    queries.q_notes_recent.clear()


def _push_life_to_turso():
    """Best-effort push tabel Rozkmin."""
    try:
        from sync import push as _push  # type: ignore
        _push(verbose=False, tables=["tasks", "weekly_goals", "notes"],
              skip_empty=False)
    except Exception as e:
        st.warning(f"Push do Turso: {e}")


def _cb_goal_upsert(week_start: str, category: str, key: str):
    val = (st.session_state.get(key) or "").strip()
    if not val:
        return
    with api.connect() as conn:
        api.goals.upsert(conn, week_start=week_start, category=category,
                         goal=val, status=None)
    _invalidate_life_cache()
    _push_life_to_turso()


def _cb_goal_toggle(goal_id: int, current_status: str):
    with api.connect() as conn:
        if current_status == "open":
            api.goals.mark_done(conn, id=goal_id)
        else:
            api.goals.reopen(conn, id=goal_id)
    _invalidate_life_cache()
    _push_life_to_turso()


def _cb_task_toggle(task_id: int, current_status: str):
    with api.connect() as conn:
        if current_status == "open":
            api.tasks.mark_done(conn, id=task_id)
        else:
            api.tasks.reopen(conn, id=task_id)
    _invalidate_life_cache()
    _push_life_to_turso()


def _cb_task_delete(task_id: int):
    with api.connect() as conn:
        api.tasks.delete(conn, id=task_id)
    _invalidate_life_cache()
    _push_life_to_turso()


def _cb_note_delete(note_id: int):
    with api.connect() as conn:
        api.notes.delete(conn, id=note_id)
    _invalidate_life_cache()
    _push_life_to_turso()


# ============================================
# Cwiczenia — edycja YouTube URL + name_en
# ============================================

def _apply_exercise_edit(ex_id: int, url: str, name_en: str):
    with api.connect() as conn:
        conn.execute(
            "UPDATE exercises SET youtube_url=?, name_en=?, updated_at=datetime('now') WHERE id=?",
            (url.strip() or None, name_en.strip() or None, ex_id),
        )
        conn.commit()
    st.cache_data.clear()


# ============================================
# Artefakty — best-effort Turso push
# ============================================

def _push_artifacts_to_turso():
    """Best-effort push po zmianach (add/archive)."""
    try:
        import subprocess, sys as _sys
        subprocess.Popen(
            [_sys.executable, str(ROOT / "db" / "sync.py"), "push"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
