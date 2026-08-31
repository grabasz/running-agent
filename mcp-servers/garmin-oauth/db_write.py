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

try:
    from crypto import maybe_encrypt as _enc
except ImportError:
    def _enc(v, _uid):
        return v


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
        _enc_notes = _enc(notes, USER_ID)
        _tx("""
            INSERT INTO body_state (user_id, date, location, pain_0_10, doms, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, location) DO UPDATE SET
                pain_0_10 = excluded.pain_0_10,
                doms = excluded.doms,
                notes = excluded.notes
        """, (USER_ID, d, loc, int(pain_0_10), 1 if doms else 0, _enc_notes))
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
        """, (USER_ID, d, cat, _enc(txt, USER_ID), related_task_id, related_run_id))
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
        """, (USER_ID, cat, _enc(ttl, USER_ID), _enc(description, USER_ID), due_date, prio))
        return _dumps({
            "ok": True, "id": result["lastrowid"], "category": cat, "title": ttl,
            "priority": prio, "due_date": due_date, "user_id": USER_ID,
        })

    # =========================================================================
    # Plan closing loop + editing (Faza 19 CRUD toolset)
    # =========================================================================

    @mcp.tool(
        name="db-log-run-actual",
        description="""Zamknij pętlę planu — powiąż wykonany trening z planned_workout i dopisz actual_notes.

Args:
  planned_workout_id: id z db-week-plan / db-planned-for-date. Alt: (date, type_key)
    zamiast id — jednoznaczne, jeśli tego dnia więcej niż jeden plan tego typu = błąd 'ambiguous'.
  actual_notes: co user chce zapisać po treningu (jak się czuło, kolano, warunki).
  garmin_activity_id: opcjonalnie — jeśli chcesz zlinkować do runs.garmin_activity_id.
  strava_activity_id: opcjonalnie — jeśli chcesz zlinkować do runs.strava_id.
  status: 'done' (default) | 'modified' | 'skipped'.
  date + type_key: alternatywa dla planned_workout_id.

Perfect for mobile po biegu: db-log-run-actual(planned_workout_id=112, actual_notes="14km, blok 4km @4:38, HR max 190")."""
    )
    @_wrap_401
    def db_log_run_actual(
        planned_workout_id: int | None = None,
        actual_notes: str | None = None,
        garmin_activity_id: int | None = None,
        strava_activity_id: int | None = None,
        status: str = "done",
        date: str | None = None,
        type_key: str | None = None,
    ) -> str:
        if status not in ("done", "modified", "skipped"):
            return _dumps({"status": "error", "message": f"status must be done|modified|skipped, got {status!r}"})
        if planned_workout_id is None:
            if not (date and type_key):
                return _dumps({"status": "error", "message": "provide planned_workout_id OR (date + type_key)"})
            rows = _tq("""
                SELECT p.id FROM planned_workouts p
                  JOIN workout_types t ON t.id = p.type_id
                 WHERE p.date = ? AND t.key = ? AND p.user_id = ?
            """, (date, type_key, USER_ID))
            if not rows:
                return _dumps({"status": "error", "message": f"no plan for date={date} type_key={type_key}"})
            if len(rows) > 1:
                return _dumps({"status": "error", "message": f"ambiguous — {len(rows)} plans for date={date} type_key={type_key}, use planned_workout_id"})
            planned_workout_id = rows[0]["id"]
        parent = _tq("SELECT id FROM planned_workouts WHERE id = ? AND user_id = ?", (planned_workout_id, USER_ID))
        if not parent:
            return _dumps({"status": "error", "message": f"no planned_workout id={planned_workout_id} for user_id={USER_ID}"})
        actual_run_id = None
        if garmin_activity_id:
            r = _tq("SELECT id FROM runs WHERE garmin_activity_id = ? AND user_id = ?", (garmin_activity_id, USER_ID))
            actual_run_id = r[0]["id"] if r else None
        elif strava_activity_id:
            r = _tq("SELECT id FROM runs WHERE strava_id = ? AND user_id = ?", (strava_activity_id, USER_ID))
            actual_run_id = r[0]["id"] if r else None
        enc_notes = _enc(actual_notes, USER_ID) if actual_notes else None
        _tx("""
            UPDATE planned_workouts
               SET status_id = (SELECT id FROM workout_statuses WHERE key = ?),
                   actual_notes = COALESCE(?, actual_notes),
                   actual_run_id = COALESCE(?, actual_run_id),
                   updated_at = datetime('now')
             WHERE id = ? AND user_id = ?
        """, (status, enc_notes, actual_run_id, planned_workout_id, USER_ID))
        return _dumps({
            "ok": True,
            "planned_workout_id": planned_workout_id,
            "status": status,
            "actual_run_id": actual_run_id,
            "actual_notes_saved": bool(actual_notes),
            "linked_from": ("garmin" if garmin_activity_id else "strava" if strava_activity_id else None),
            "user_id": USER_ID,
        })

    @mcp.tool(
        name="db-plan-week-bulk",
        description="""Zaplanuj cały tydzień jednym wywołaniem (do 7 dni w 1 callu — dla mobile ekonomii tokenów).

Args:
  week_start: YYYY-MM-DD (musi być poniedziałek).
  days: lista dictów. Każdy dict: {date, type_key, title,
        target_distance_km?, target_pace_sec_per_km?, target_hr_max?, target_duration_min?, notes?}
  replace: bool (default False). Jeśli True — najpierw db-clear-week (odmawia jeśli którykolwiek status='done').

Zwraca: {inserted, ids, week_start}.
Przy błędzie w środku pętli zwraca {status: partial_error, inserted_so_far: [...ids...]}.

PACE RANGE RULE: notes powinny zawierać "Tempo: M:SS-M:SS/km" z rozstępem min 20s/km (patrz server instructions).

Perfect for planning: user mówi 'zaplanuj mi tydzień 07-13.09' → 1 call zamiast 7."""
    )
    @_wrap_401
    def db_plan_week_bulk(
        week_start: str,
        days: list,
        replace: bool = False,
    ) -> str:
        if not isinstance(days, list) or not days:
            return _dumps({"status": "error", "message": "days must be a non-empty list of dicts"})
        from datetime import date as _d
        try:
            wsd = _d.fromisoformat(week_start)
            if wsd.weekday() != 0:
                return _dumps({"status": "error", "message": f"week_start must be Monday, got {wsd.strftime('%A')}"})
        except ValueError:
            return _dumps({"status": "error", "message": f"invalid week_start date: {week_start!r}"})
        type_cache: dict = {}
        prepared = []
        for i, d in enumerate(days):
            if not isinstance(d, dict):
                return _dumps({"status": "error", "message": f"days[{i}] must be dict, got {type(d).__name__}"})
            for key in ("date", "type_key", "title"):
                if not d.get(key):
                    return _dumps({"status": "error", "message": f"days[{i}]: missing required field {key!r}"})
            tk = d["type_key"]
            if tk not in type_cache:
                tt = _tq("SELECT id FROM workout_types WHERE key = ?", (tk,))
                if not tt:
                    return _dumps({"status": "error", "message": f"days[{i}]: unknown type_key {tk!r}"})
                type_cache[tk] = tt[0]["id"]
            prepared.append({
                "date": d["date"],
                "week_start": _monday(d["date"]),
                "type_id": type_cache[tk],
                "title": d["title"],
                "target_distance_km": d.get("target_distance_km"),
                "target_duration_min": d.get("target_duration_min"),
                "target_pace_sec_per_km": d.get("target_pace_sec_per_km"),
                "target_hr_max": d.get("target_hr_max"),
                "notes": d.get("notes"),
            })
        if replace:
            done = _tq("""
                SELECT COUNT(*) AS n FROM planned_workouts p
                  JOIN workout_statuses s ON s.id = p.status_id
                 WHERE p.week_start = ? AND p.user_id = ? AND s.key = 'done'
            """, (week_start, USER_ID))
            if done and done[0]["n"] > 0:
                return _dumps({"status": "error", "message": f"replace refused — {done[0]['n']} workouts in week {week_start} are 'done'"})
            _tx("""DELETE FROM planned_workout_components WHERE planned_workout_id IN
                   (SELECT id FROM planned_workouts WHERE week_start = ? AND user_id = ?)""", (week_start, USER_ID))
            _tx("DELETE FROM planned_workouts WHERE week_start = ? AND user_id = ?", (week_start, USER_ID))
        ids = []
        for p in prepared:
            try:
                result = _tx("""
                    INSERT INTO planned_workouts
                        (date, week_start, type_id, status_id, title, target_distance_km,
                         target_duration_min, target_pace_sec_per_km, target_hr_max, notes, user_id)
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                """, (p["date"], p["week_start"], p["type_id"], p["title"],
                      p["target_distance_km"], p["target_duration_min"],
                      p["target_pace_sec_per_km"], p["target_hr_max"],
                      p["notes"], USER_ID))
                ids.append(result["lastrowid"])
            except Exception as e:
                return _dumps({
                    "status": "partial_error",
                    "message": f"insert failed at days[{len(ids)}] ({p['date']} {p['title'][:40]}): {type(e).__name__}: {e}",
                    "inserted_so_far": ids,
                })
        return _dumps({"ok": True, "inserted": len(ids), "ids": ids, "week_start": week_start, "user_id": USER_ID})

    @mcp.tool(
        name="db-plan-workout-update",
        description="""Edytuj pojedyncze pola planned_workout (bez DELETE+INSERT).

Args (wszystkie opcjonalne poza id):
  id: id planned_workout.
  title, target_distance_km, target_pace_sec_per_km, target_hr_max,
  target_duration_min, notes, date, type_key.

Rules:
- Odmawia edycji title/type_key/date/target_* jeśli status='done' (chroni logged workout).
  Notes można edytować zawsze (nawet w done — to komentarz użytkownika).
- Zmiana date przelicza week_start automatycznie.
- Jeśli chcesz przenieść w czasie: db-plan-workout-update(id=112, date='2026-09-06')."""
    )
    @_wrap_401
    def db_plan_workout_update(
        id: int,
        title: str | None = None,
        target_distance_km: float | None = None,
        target_pace_sec_per_km: int | None = None,
        target_hr_max: int | None = None,
        target_duration_min: int | None = None,
        notes: str | None = None,
        date: str | None = None,
        type_key: str | None = None,
    ) -> str:
        row = _tq("""
            SELECT p.id, s.key AS status_key
              FROM planned_workouts p JOIN workout_statuses s ON s.id = p.status_id
             WHERE p.id = ? AND p.user_id = ?
        """, (id, USER_ID))
        if not row:
            return _dumps({"status": "error", "message": f"no planned_workout id={id} for user_id={USER_ID}"})
        is_done = row[0]["status_key"] == "done"
        given_core = {k for k, v in {
            "title": title, "date": date, "type_key": type_key,
            "target_distance_km": target_distance_km,
            "target_pace_sec_per_km": target_pace_sec_per_km,
            "target_hr_max": target_hr_max, "target_duration_min": target_duration_min,
        }.items() if v is not None}
        if is_done and given_core:
            return _dumps({"status": "error",
                           "message": f"workout id={id} is 'done' — only 'notes' can be edited (attempted core fields: {sorted(given_core)})"})
        updates: list[str] = []
        params: list = []
        if title is not None:
            updates.append("title = ?"); params.append(title)
        if target_distance_km is not None:
            updates.append("target_distance_km = ?"); params.append(target_distance_km)
        if target_pace_sec_per_km is not None:
            updates.append("target_pace_sec_per_km = ?"); params.append(target_pace_sec_per_km)
        if target_hr_max is not None:
            updates.append("target_hr_max = ?"); params.append(target_hr_max)
        if target_duration_min is not None:
            updates.append("target_duration_min = ?"); params.append(target_duration_min)
        if notes is not None:
            updates.append("notes = ?"); params.append(notes)
        if type_key is not None:
            tt = _tq("SELECT id FROM workout_types WHERE key = ?", (type_key,))
            if not tt:
                return _dumps({"status": "error", "message": f"unknown type_key {type_key!r}"})
            updates.append("type_id = ?"); params.append(tt[0]["id"])
        if date is not None:
            updates.append("date = ?"); params.append(date)
            updates.append("week_start = ?"); params.append(_monday(date))
        if not updates:
            return _dumps({"status": "error", "message": "no fields to update"})
        updates.append("updated_at = datetime('now')")
        params.extend([id, USER_ID])
        _tx(f"UPDATE planned_workouts SET {', '.join(updates)} WHERE id = ? AND user_id = ?", tuple(params))
        return _dumps({"ok": True, "id": id, "updated_fields": len(updates) - 1, "user_id": USER_ID})

    # =========================================================================
    # Races + VDOT
    # =========================================================================

    @mcp.tool(
        name="db-race-add",
        description="""Dodaj wyścig (planowany albo wykonany) do races.

Args:
  date: YYYY-MM-DD. Wymagany.
  name: nazwa (np. 'HM Gniezno'). Wymagany.
  distance_km: float (np. 21.0975 dla HM). Wymagany.
  actual_time_sec: opcjonalnie — sekundy netto, jeśli wyścig już był.
  target_time_sec: opcjonalnie — planowany czas.
  place_overall: opcjonalnie — miejsce open.
  strategy: opcjonalnie — opis strategii startowej.
  notes: opcjonalnie.
  is_pb: 0/1 (default 0). Do pełnej rekalkulacji użyj api.recompute_pbs() offline.

Dedup: UNIQUE(date, name)."""
    )
    @_wrap_401
    def db_race_add(
        date: str,
        name: str,
        distance_km: float,
        actual_time_sec: int | None = None,
        target_time_sec: int | None = None,
        place_overall: int | None = None,
        strategy: str | None = None,
        notes: str | None = None,
        is_pb: int = 0,
    ) -> str:
        n = (name or "").strip()
        if not n:
            return _dumps({"status": "error", "message": "name is required"})
        if not date or not distance_km:
            return _dumps({"status": "error", "message": "date and distance_km are required"})
        try:
            result = _tx("""
                INSERT INTO races (user_id, date, name, distance_km, target_time_sec,
                                   actual_time_sec, is_pb, place_overall, strategy, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (USER_ID, date, n, float(distance_km), target_time_sec,
                  actual_time_sec, int(is_pb), place_overall, strategy, notes))
            return _dumps({"ok": True, "id": result["lastrowid"], "date": date, "name": n,
                           "distance_km": distance_km, "user_id": USER_ID})
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                return _dumps({"status": "error", "message": f"race ({date}, {n}) already exists"})
            return _dumps({"status": "error", "message": f"{type(e).__name__}: {e}"})

    @mcp.tool(
        name="db-vdot-update",
        description="""Dodaj/aktualizuj wpis VDOT (progresja formy). UPSERT po (user_id, date).

Args:
  vdot: int (30-70). Wymagany.
  source: opis testu (np. 'HM Gniezno 1:35:12', 'test 5km 22:30'). Wymagany.
  date: YYYY-MM-DD, default today.
  threshold_pace_sec: opcjonalnie — sekundy/km (np. 264 = 4:24/km dla VDOT 55).
  notes: opcjonalnie.

Latest entry (per user_id) wygrywa w db-current-vdot."""
    )
    @_wrap_401
    def db_vdot_update(
        vdot: int,
        source: str,
        date: str | None = None,
        threshold_pace_sec: int | None = None,
        notes: str | None = None,
    ) -> str:
        from datetime import date as _d
        d = date or _d.today().isoformat()
        if not isinstance(vdot, int) or not (30 <= vdot <= 70):
            return _dumps({"status": "error", "message": f"vdot must be int 30-70, got {vdot!r}"})
        src = (source or "").strip()
        if not src:
            return _dumps({"status": "error", "message": "source is required"})
        _tx("""
            INSERT INTO vdot_history (user_id, date, vdot, t_pace_sec, source, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                vdot = excluded.vdot,
                t_pace_sec = excluded.t_pace_sec,
                source = excluded.source,
                notes = excluded.notes
        """, (USER_ID, d, int(vdot), threshold_pace_sec, src, notes))
        return _dumps({"ok": True, "date": d, "vdot": int(vdot), "source": src,
                       "threshold_pace_sec": threshold_pace_sec, "user_id": USER_ID})

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
