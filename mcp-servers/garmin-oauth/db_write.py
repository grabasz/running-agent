"""DB write tools (Turso).

Planning writes (planned_workouts + components + delete/clear), plus mobile-friendly
writes (body_state, notes, tasks, exercises).

NEW in this split: `db-add-exercise` — lets Bartek dodawać nowe ćwiczenia do katalogu
exercises z telefona przez Claude iOS Custom Connector.
"""
from __future__ import annotations
from db_common import (
    _tq, _tx, _dumps, _wrap_401, _monday, USER_ID,
    _ALLOWED_NOTE_CATEGORIES, _ALLOWED_TASK_CATEGORIES, _ALLOWED_TASK_PRIORITIES,
    _ALLOWED_EXERCISE_CATEGORIES,
)


def register_db_write_tools(mcp) -> None:
    """Register all DB write tools on the given FastMCP instance."""

    # =========================================================================
    # Planning writes
    # =========================================================================

    @mcp.tool(
        name="db-plan-workout",
        description="""Add a planned workout to the training plan.

Args:
  date: YYYY-MM-DD. Must be today or future (past dates rejected).
  type_key: one of workout_types keys (call db-workout-types to list). Common: easy, tempo, interval, long, strength_a, rest.
  title: short human description, e.g. "Easy 6K @6:15 z Kubą".
  target_distance_km: optional.
  target_pace_sec_per_km: optional (e.g. 375 = 6:15/km).
  target_duration_min: optional.
  target_hr_max: optional (HR cap).
  notes: optional context (e.g. "spotkanie grupowe, plany zależne od pogody").

Returns the new planned_workout id on success.
Errors if a workout of the same type already exists for that date (UNIQUE constraint)."""
    )
    @_wrap_401
    def db_plan_workout(
        date: str,
        type_key: str,
        title: str,
        target_distance_km: float | None = None,
        target_pace_sec_per_km: int | None = None,
        target_duration_min: int | None = None,
        target_hr_max: int | None = None,
        notes: str | None = None,
    ) -> str:
        from datetime import date as _d
        today = _d.today().isoformat()
        if date < today:
            return _dumps({"status": "error", "message": f"Cannot plan in the past (date={date}, today={today})"})
        tk = _tq("SELECT id FROM workout_types WHERE key = ?", (type_key,))
        if not tk:
            return _dumps({"status": "error", "message": f"Unknown type_key '{type_key}'. Use db-workout-types to list valid keys."})
        week_start = _monday(date)
        result = _tx("""
            INSERT INTO planned_workouts
                (date, week_start, type_id, status_id, title, target_distance_km,
                 target_duration_min, target_pace_sec_per_km, target_hr_max, notes, user_id)
            VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        """, (date, week_start, tk[0]["id"], title, target_distance_km,
              target_duration_min, target_pace_sec_per_km, target_hr_max, notes, USER_ID))
        return _dumps({"status": "ok", "planned_workout_id": result["lastrowid"], "date": date, "type_key": type_key, "user_id": USER_ID})

    @mcp.tool(
        name="db-plan-component",
        description="Add a sub-component (checkbox item) to an existing planned workout. Use to split a monolithic entry into checkable parts (e.g. 'REST' + 'Foam roll 10min' + 'Mobility 15min')."
    )
    @_wrap_401
    def db_plan_component(planned_workout_id: int, order_idx: int, label: str) -> str:
        parent = _tq("SELECT id FROM planned_workouts WHERE id = ? AND user_id = ?", (planned_workout_id, USER_ID))
        if not parent:
            return _dumps({"status": "error", "message": f"No planned_workout with id={planned_workout_id} for user_id={USER_ID}"})
        result = _tx("""
            INSERT INTO planned_workout_components (planned_workout_id, order_idx, label, status_id)
            VALUES (?, ?, ?, 1)
        """, (planned_workout_id, order_idx, label))
        return _dumps({"status": "ok", "component_id": result["lastrowid"]})

    @mcp.tool(
        name="db-delete-planned-workout",
        description="Delete a planned workout by id. Refuses if status is 'done' (protects logged workouts). Cascades to components."
    )
    @_wrap_401
    def db_delete_planned_workout(planned_workout_id: int) -> str:
        row = _tq("""
            SELECT p.id, p.date, p.title, s.key AS status_key
              FROM planned_workouts p JOIN workout_statuses s ON s.id = p.status_id
             WHERE p.id = ? AND p.user_id = ?
        """, (planned_workout_id, USER_ID))
        if not row:
            return _dumps({"status": "error", "message": f"No planned_workout with id={planned_workout_id} for user_id={USER_ID}"})
        if row[0]["status_key"] == "done":
            return _dumps({"status": "error", "message": "Refusing to delete a 'done' workout — mark as 'skipped' instead if needed"})
        _tx("DELETE FROM planned_workout_components WHERE planned_workout_id = ?", (planned_workout_id,))
        _tx("DELETE FROM planned_workouts WHERE id = ? AND user_id = ?", (planned_workout_id, USER_ID))
        return _dumps({"status": "ok", "deleted": row[0]})

    @mcp.tool(
        name="db-clear-week",
        description="Delete ALL planned workouts for a given week_start (Monday YYYY-MM-DD). Refuses if any workout that week has status 'done'. Use before regenerating a week's plan."
    )
    @_wrap_401
    def db_clear_week(week_start: str) -> str:
        done = _tq("""
            SELECT COUNT(*) AS n FROM planned_workouts p
              JOIN workout_statuses s ON s.id = p.status_id
             WHERE p.week_start = ? AND p.user_id = ? AND s.key = 'done'
        """, (week_start, USER_ID))
        if done and done[0]["n"] > 0:
            return _dumps({"status": "error", "message": f"Refusing — {done[0]['n']} workouts in week {week_start} are marked 'done'"})
        _tx("""DELETE FROM planned_workout_components WHERE planned_workout_id IN
               (SELECT id FROM planned_workouts WHERE week_start = ? AND user_id = ?)""", (week_start, USER_ID))
        result = _tx("DELETE FROM planned_workouts WHERE week_start = ? AND user_id = ?", (week_start, USER_ID))
        return _dumps({"status": "ok", "week_start": week_start, "deleted_workouts": result["rowcount"]})

    # =========================================================================
    # Mobile-friendly writes (body_state, notes, tasks, exercises)
    # =========================================================================

    @mcp.tool(
        name="db-log-body-state",
        description="""Log a body-state entry (pain / DOMS at a specific location). UPSERT on (date, location).

Args:
  location: free text describing where — use existing patterns when possible
            (e.g. "kolano_prawe", "kolano_lewe", "lydka_prawa", "posladek_prawy", "plecy", "krzyz",
             "przywodziciel_prawy", "piriformis_prawy", "glute_prawy"). Snake_case, Polish body-parts.
  pain_0_10: integer 0-10 (0 = fine, 3 = discomfort, 5 = noticeable pain, 8+ = severe).
  notes: optional free text — what triggered it, when, what helps.
  date: optional YYYY-MM-DD, defaults to today.
  doms: optional bool (True = delayed-onset muscle soreness from prior workout), default False.

Perfect for mobile: "boli mnie kolano prawe 4/10 po biegu" → db-log-body-state(location="kolano_prawe", pain_0_10=4, notes="po biegu")."""
    )
    @_wrap_401
    def db_log_body_state(
        location: str,
        pain_0_10: int,
        notes: str | None = None,
        date: str | None = None,
        doms: bool = False,
    ) -> str:
        from datetime import date as _d
        d = date or _d.today().isoformat()
        if not isinstance(pain_0_10, int) or not (0 <= pain_0_10 <= 10):
            return _dumps({"status": "error", "message": f"pain_0_10 must be int 0-10, got {pain_0_10!r}"})
        loc = (location or "").strip()
        if not loc:
            return _dumps({"status": "error", "message": "location is required (e.g. 'kolano_prawe')"})
        _tx("""
            INSERT INTO body_state (user_id, date, location, pain_0_10, doms, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, location) DO UPDATE SET
                pain_0_10 = excluded.pain_0_10,
                doms = excluded.doms,
                notes = excluded.notes
        """, (USER_ID, d, loc, int(pain_0_10), 1 if doms else 0, notes))
        return _dumps({
            "ok": True, "date": d, "location": loc, "pain_0_10": int(pain_0_10),
            "doms": bool(doms), "note": notes, "user_id": USER_ID,
        })

    @mcp.tool(
        name="db-add-note",
        description="""Add a note to the notes stream (insight/decision/reminder/idea/observation).

Args:
  category: one of insight | decision | reminder | idea | observation.
  content: free text — the note body.
  date: optional YYYY-MM-DD, defaults to today.
  related_run_id: optional int — link to a runs.id (e.g. an insight about a specific run).
  related_task_id: optional int — link to a tasks.id (e.g. a decision that closes a task).

Perfect for mobile: "zapisz insight: po rolowaniu stopy klekanie znika" → db-add-note(category="insight", content="Po rolowaniu stopy prawej klekanie znika")."""
    )
    @_wrap_401
    def db_add_note(
        category: str,
        content: str,
        date: str | None = None,
        related_run_id: int | None = None,
        related_task_id: int | None = None,
    ) -> str:
        from datetime import date as _d
        d = date or _d.today().isoformat()
        cat = (category or "").strip().lower()
        if cat not in _ALLOWED_NOTE_CATEGORIES:
            return _dumps({"status": "error",
                           "message": f"category must be one of {list(_ALLOWED_NOTE_CATEGORIES)}, got {category!r}"})
        txt = (content or "").strip()
        if not txt:
            return _dumps({"status": "error", "message": "content is required"})
        result = _tx("""
            INSERT INTO notes (user_id, date, category, content, related_task_id,
                               related_run_id, related_session_id, source)
            VALUES (?, ?, ?, ?, ?, ?, NULL, 'mcp_mobile')
        """, (USER_ID, d, cat, txt, related_task_id, related_run_id))
        return _dumps({
            "ok": True, "id": result["lastrowid"], "date": d, "category": cat,
            "content_preview": txt[:80] + ("…" if len(txt) > 80 else ""),
            "user_id": USER_ID,
        })

    @mcp.tool(
        name="db-add-task",
        description="""Add a task to the Rozkminy (tasks) list.

Args:
  category: one of sport | praca | dom | relacje | zdrowie | inne.
  title: short imperative — "Umów fizjo", "Kupić rolki", "Zadzwonić do Kuby".
  priority: one of low | medium | high (default medium).
  due_date: optional YYYY-MM-DD.
  description: optional longer context.

Perfect for mobile: "dodaj task: umow fizjo pilnie" → db-add-task(category="zdrowie", title="Umow fizjo", priority="high")."""
    )
    @_wrap_401
    def db_add_task(
        category: str,
        title: str,
        priority: str = "medium",
        due_date: str | None = None,
        description: str | None = None,
    ) -> str:
        cat = (category or "").strip().lower()
        if cat not in _ALLOWED_TASK_CATEGORIES:
            return _dumps({"status": "error",
                           "message": f"category must be one of {list(_ALLOWED_TASK_CATEGORIES)}, got {category!r}"})
        prio = (priority or "medium").strip().lower()
        if prio not in _ALLOWED_TASK_PRIORITIES:
            return _dumps({"status": "error",
                           "message": f"priority must be one of {list(_ALLOWED_TASK_PRIORITIES)}, got {priority!r}"})
        ttl = (title or "").strip()
        if not ttl:
            return _dumps({"status": "error", "message": "title is required"})
        result = _tx("""
            INSERT INTO tasks (user_id, category, title, description, due_date, status, priority, created_at)
            VALUES (?, ?, ?, ?, ?, 'todo', ?, datetime('now'))
        """, (USER_ID, cat, ttl, description, due_date, prio))
        return _dumps({
            "ok": True, "id": result["lastrowid"], "category": cat, "title": ttl,
            "priority": prio, "due_date": due_date, "user_id": USER_ID,
        })

    @mcp.tool(
        name="db-add-exercise",
        description="""Add a new exercise to the exercises catalog (used by routines).

Args:
  key: unique slug snake_case (e.g. "monster_walks", "hip_bridge_single_leg"). Required.
  name: Polish name (e.g. "Chody potworkowe"). Required.
  category: one of "rolowanie" | "aktywacja" | "stretch" | "wzmocnienie" | "kardio". Required.
  tool: what user needs (e.g. "Guma mini-band", "Mata", "BW", "Hantle"). Required.
  description_md: markdown body — dostarczaj sekcje "Po co", "Jak", "Sprawdź" (co user ma czuć). Required.
  name_en: English name (e.g. "Monster Walks"). Optional but recommended.
  youtube_url: YouTube video link. Optional (Bartek doda później w dashboardzie).

Perfect for mobile: "dodaj cwiczenie monster walks - lateral steps z guma mini-band na kostkach"."""
    )
    @_wrap_401
    def db_add_exercise(
        key: str,
        name: str,
        category: str,
        tool: str,
        description_md: str,
        name_en: str | None = None,
        youtube_url: str | None = None,
    ) -> str:
        k = (key or "").strip().lower()
        n = (name or "").strip()
        cat = (category or "").strip().lower()
        t = (tool or "").strip()
        desc = (description_md or "").strip()
        if not k or not n or not cat or not t or not desc:
            return _dumps({"status": "error",
                           "message": "key, name, category, tool, description_md are required"})
        if cat not in _ALLOWED_EXERCISE_CATEGORIES:
            return _dumps({"status": "error",
                           "message": f"category must be one of {list(_ALLOWED_EXERCISE_CATEGORIES)}, got {category!r}"})
        try:
            result = _tx("""
                INSERT INTO exercises (key, name, name_en, category, tool, description_md, youtube_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (k, n, name_en, cat, t, desc, youtube_url))
            return _dumps({
                "ok": True, "id": result["lastrowid"], "key": k, "name": n,
                "name_en": name_en, "category": cat, "tool": t,
                "youtube_url": youtube_url,
            })
        except Exception as e:
            if "UNIQUE" in str(e):
                return _dumps({"status": "error", "message": f"exercise key '{k}' already exists"})
            return _dumps({"status": "error", "message": f"{type(e).__name__}: {e}"})
