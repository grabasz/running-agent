"""DB read tools (Turso).

Read-only queries against Turso for plan / VDOT / history / body state / notes.
Modularized from server.py — behavior identical.
"""
from __future__ import annotations
from db_common import (
    _tq, _dumps, _wrap_401, _monday, USER_ID,
    _ALLOWED_NOTE_CATEGORIES,
    _ALLOWED_TASK_CATEGORIES, _ALLOWED_TASK_PRIORITIES,
)

try:
    from crypto import maybe_decrypt as _dec
except ImportError:
    def _dec(v, _uid):
        return v


def _decrypt_rows(rows, fields):
    """Deszyfruj pola in-place na liscie dictow (fallback dla klucz-nie-ustawiony
    zwraca placeholder, patrz crypto.maybe_decrypt)."""
    for r in rows:
        for f in fields:
            if f in r:
                r[f] = _dec(r[f], USER_ID)
    return rows


def register_db_read_tools(mcp) -> None:
    """Register all DB read tools on the given FastMCP instance."""

    @mcp.tool(name="db-current-vdot", description="Get the current (latest) VDOT + threshold pace. Use for computing Jack Daniels training paces.")
    @_wrap_401
    def db_current_vdot() -> str:
        rows = _tq("SELECT date, vdot, t_pace_sec, source, notes FROM vdot_history WHERE user_id = ? ORDER BY date DESC LIMIT 1", (USER_ID,))
        return _dumps(rows[0] if rows else {"status": "no_vdot_recorded"})

    @mcp.tool(name="db-week-plan", description="Planned workouts for a week (Monday-anchored). Defaults to current week if week_start omitted (YYYY-MM-DD Monday date).")
    @_wrap_401
    def db_week_plan(week_start: str | None = None) -> str:
        ws = week_start or _monday()
        rows = _tq("""
            SELECT p.id, p.date, p.week_start, p.title, p.target_distance_km,
                   p.target_duration_min, p.target_pace_sec_per_km, p.target_hr_max, p.notes,
                   p.weather_temp_c, p.weather_note,
                   t.key AS type_key, t.display_pl AS type_display, t.category AS type_category,
                   s.key AS status_key, s.display_pl AS status_display,
                   p.actual_run_id, p.actual_session_id, p.actual_notes
              FROM planned_workouts p
              JOIN workout_types t ON t.id = p.type_id
              JOIN workout_statuses s ON s.id = p.status_id
             WHERE p.week_start = ? AND p.user_id = ?
             ORDER BY p.date, p.id
        """, (ws, USER_ID))
        return _dumps({"week_start": ws, "workouts": _decrypt_rows(rows, ["actual_notes"])})

    @mcp.tool(name="db-planned-for-date", description="Planned workouts for a specific date (YYYY-MM-DD). Empty list if nothing scheduled.")
    @_wrap_401
    def db_planned_for_date(date: str) -> str:
        rows = _tq("""
            SELECT p.id, p.date, p.title, p.target_distance_km, p.target_pace_sec_per_km, p.notes,
                   t.key AS type_key, t.display_pl AS type_display, t.category AS type_category,
                   s.key AS status_key
              FROM planned_workouts p
              JOIN workout_types t ON t.id = p.type_id
              JOIN workout_statuses s ON s.id = p.status_id
             WHERE p.date = ? AND p.user_id = ?
             ORDER BY p.id
        """, (date, USER_ID))
        return _dumps(rows)

    @mcp.tool(name="db-plan-components", description="All sub-components of a planned workout (per-item breakdown of a monolithic entry like 'REST + foam + mobility').")
    @_wrap_401
    def db_plan_components(planned_workout_id: int) -> str:
        rows = _tq("""
            SELECT c.id, c.order_idx, c.label, c.actual_notes,
                   s.key AS status_key, s.display_pl AS status_display
              FROM planned_workout_components c
              JOIN workout_statuses s ON s.id = c.status_id
              JOIN planned_workouts p ON p.id = c.planned_workout_id
             WHERE c.planned_workout_id = ? AND p.user_id = ?
             ORDER BY c.order_idx, c.id
        """, (planned_workout_id, USER_ID))
        return _dumps(rows)

    @mcp.tool(name="db-recent-runs", description="Recent runs with running dynamics (Garmin data). Default last 14 days.")
    @_wrap_401
    def db_recent_runs(days: int = 14) -> str:
        rows = _tq(f"""
            SELECT id, date, name, distance_km, moving_sec, pace_sec_per_km,
                   hr_avg, hr_max, cadence_avg, elevation_gain_m,
                   vertical_oscillation_cm, ground_contact_ms, gct_balance_left_pct,
                   stride_length_cm, vertical_ratio_pct,
                   training_effect_aerobic, training_load, type, notes
              FROM runs
             WHERE date >= date('now', '-{int(days)} days') AND user_id = ?
             ORDER BY date DESC, id DESC
        """, (USER_ID,))
        return _dumps(rows)

    @mcp.tool(name="db-recent-gym", description="Recent strength sessions with set-level details. Default last 14 days.")
    @_wrap_401
    def db_recent_gym(days: int = 14) -> str:
        sessions = _tq(f"""
            SELECT id, date, duration_min, hr_avg, hr_max, context, notes
              FROM gym_sessions
             WHERE date >= date('now', '-{int(days)} days') AND user_id = ?
             ORDER BY date DESC
        """, (USER_ID,))
        for s in sessions:
            s["sets"] = _tq("""
                SELECT exercise, set_num, reps, duration_sec, weight_kg, weight_per_side, rpe, notes
                  FROM gym_sets WHERE session_id = ? ORDER BY exercise, set_num
            """, (s["id"],))
        return _dumps(sessions)

    @mcp.tool(name="db-body-state", description="Body state entries (knee, calf, back pain, DOMS). Default last 14 days.")
    @_wrap_401
    def db_body_state(days: int = 14) -> str:
        rows = _tq(f"""
            SELECT date, location, pain_0_10, doms, notes
              FROM body_state
             WHERE date >= date('now', '-{int(days)} days') AND user_id = ?
             ORDER BY date DESC, location
        """, (USER_ID,))
        return _dumps(_decrypt_rows(rows, ["notes"]))

    @mcp.tool(name="db-weekly-volume", description="Weekly mileage history. Default last 6 weeks.")
    @_wrap_401
    def db_weekly_volume(weeks: int = 6) -> str:
        rows = _tq(f"""
            SELECT week_start, distance_km, elevation_gain_m, duration_sec, num_runs, longest_km, trend
              FROM weekly_volume
             WHERE user_id = ?
             ORDER BY week_start DESC LIMIT {int(weeks)}
        """, (USER_ID,))
        return _dumps(rows)

    @mcp.tool(name="db-race-pbs", description="All races with times and PBs. Useful for planning race strategy.")
    @_wrap_401
    def db_race_pbs() -> str:
        rows = _tq("""
            SELECT date, name, distance_km, target_time_sec, actual_time_sec, is_pb,
                   place_overall, strategy, notes
              FROM races
             WHERE user_id = ?
             ORDER BY date DESC
        """, (USER_ID,))
        return _dumps(rows)

    @mcp.tool(name="db-workout-types", description="List of allowed workout type keys (easy, tempo, interval, long, recovery, shakeout, race, strength_a, strength_b, mobility, rest, cross, kickboxing). Use with db-plan-workout.")
    @_wrap_401
    def db_workout_types() -> str:
        rows = _tq("SELECT key, display_pl, category, icon FROM workout_types ORDER BY sort_order")
        return _dumps(rows)

    @mcp.tool(
        name="db-get-notes",
        description="""Fetch recent notes from the stream (insight/decision/reminder/idea/observation).

Args:
  limit: max notes to return (default 15, max 50).
  category: optional filter — one of insight/decision/reminder/idea/observation.
  since_days: only notes newer than N days (default 30, max 365).

Returns: {count, notes: [{id, date, category, content, source, related_run_id, related_task_id, created_at}]} sorted newest-first.

Perfect for mobile: "co ostatnio zapisalem" / "pokaz ostatnie decyzje" / "insights z ostatniego tygodnia"."""
    )
    def db_get_notes(
        limit: int = 15,
        category: str | None = None,
        since_days: int = 30,
    ) -> str:
        limit = max(1, min(int(limit), 50))
        since_days = max(1, min(int(since_days), 365))
        since = f"-{since_days} days"
        sql = ("SELECT id, date, category, content, source, related_run_id, "
               "related_task_id, created_at FROM notes "
               "WHERE user_id = ? AND date >= date('now', ?)")
        params: list = [USER_ID, since]
        if category:
            cat = category.strip().lower()
            if cat not in _ALLOWED_NOTE_CATEGORIES:
                return _dumps({"status": "error",
                               "message": f"category must be one of {list(_ALLOWED_NOTE_CATEGORIES)}, got {category!r}"})
            sql += " AND category = ?"
            params.append(cat)
        sql += " ORDER BY date DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = _tq(sql, tuple(params))
        return _dumps({"count": len(rows), "notes": _decrypt_rows(rows, ["content"]), "user_id": USER_ID})

    @mcp.tool(
        name="db-get-workout-notes",
        description="""Fetch komentarze (actual_notes) z ostatnich planowanych treningow ktore user zapisal po ich wykonaniu.

To NIE jest ogolny notes-stream (db-get-notes) — to sa konkretne uwagi do treningow (np. jak sie czulem, kolano OK, sen, warunki).

Args:
  limit: max wpisow (default 10, max 30).
  status: filter — 'done' (default) | 'skipped' | 'all'. Zwykle chcesz tylko done.
  since_days: cofnij o N dni (default 30, max 365).
  only_with_notes: bool (default True) — pomin plany bez actual_notes (jesli chcesz tylko te co user skomentowal).

Returns: {count, workouts: [{id, date, type, title, target_distance_km, actual_notes, actual_run_id, actual_session_id, status, updated_at}]} sorted newest-first.

Perfect for mobile: "jak mi szly ostatnie treningi" / "co zapisalem po biegach" / "komentarze do treningow"."""
    )
    def db_get_workout_notes(
        limit: int = 10,
        status: str = "done",
        since_days: int = 30,
        only_with_notes: bool = True,
    ) -> str:
        limit = max(1, min(int(limit), 30))
        since_days = max(1, min(int(since_days), 365))
        since = f"-{since_days} days"
        if status not in ("done", "skipped", "all"):
            return _dumps({"status": "error", "message": f"invalid status {status!r} — use done/skipped/all"})
        sql = (
            "SELECT pw.id, pw.date, wt.key AS type, pw.title, pw.target_distance_km, "
            "pw.actual_notes, pw.actual_run_id, pw.actual_session_id, "
            "ws.key AS status, pw.updated_at "
            "FROM planned_workouts pw "
            "JOIN workout_types wt ON pw.type_id = wt.id "
            "JOIN workout_statuses ws ON pw.status_id = ws.id "
            "WHERE pw.user_id = ? AND pw.date >= date('now', ?)"
        )
        params: list = [USER_ID, since]
        if status != "all":
            sql += " AND ws.key = ?"
            params.append(status)
        if only_with_notes:
            sql += " AND pw.actual_notes IS NOT NULL AND TRIM(pw.actual_notes) != ''"
        sql += " ORDER BY pw.date DESC, pw.id DESC LIMIT ?"
        params.append(limit)
        rows = _tq(sql, tuple(params))
        return _dumps({"count": len(rows), "workouts": _decrypt_rows(rows, ["actual_notes"]), "user_id": USER_ID})

    @mcp.tool(
        name="db-tasks-list",
        description="""Lista zadań z tabeli tasks (Faza 17 Rozkminy).

Args:
  status: 'open' (default) | 'done' | 'wontdo' | 'all'. Aliasy: 'pending'/'todo' = 'open'.
  category: opcjonalny filtr — sport|praca|dom|relacje|zdrowie|inne.
  priority: opcjonalny filtr — low|medium|high.
  since_days: opcjonalny — created_at >= N dni wstecz (default: brak limitu — wszystkie).
  limit: max wpisów (default 20, max 100).

Returns: {count, tasks: [{id, parent_id, category, title, description, success_criteria,
                          due_date, priority, status, created_at, done_at}]}
sortowane po (due_date NULLS LAST, id).

Perfect for mobile: 'co mam do zrobienia' / 'jakie taski otwarte' / 'zaległe deadlines'."""
    )
    def db_tasks_list(
        status: str = "open",
        category: str | None = None,
        priority: str | None = None,
        since_days: int | None = None,
        limit: int = 20,
    ) -> str:
        limit = max(1, min(int(limit), 100))
        s = (status or "open").strip().lower()
        if s in ("pending", "todo"):
            s = "open"
        if s not in ("open", "done", "wontdo", "all"):
            return _dumps({"status": "error",
                           "message": f"status must be open|done|wontdo|all (aliases pending/todo -> open), got {status!r}"})
        sql = ("SELECT id, parent_id, category, title, description, success_criteria, "
               "due_date, priority, status, created_at, done_at "
               "FROM tasks WHERE user_id = ?")
        params: list = [USER_ID]
        if s != "all":
            sql += " AND status = ?"; params.append(s)
        if category:
            cat = category.strip().lower()
            if cat not in _ALLOWED_TASK_CATEGORIES:
                return _dumps({"status": "error",
                               "message": f"category must be one of {list(_ALLOWED_TASK_CATEGORIES)}"})
            sql += " AND category = ?"; params.append(cat)
        if priority:
            prio = priority.strip().lower()
            if prio not in _ALLOWED_TASK_PRIORITIES:
                return _dumps({"status": "error",
                               "message": f"priority must be one of {list(_ALLOWED_TASK_PRIORITIES)}"})
            sql += " AND priority = ?"; params.append(prio)
        if since_days is not None:
            sql += " AND created_at >= datetime('now', ?)"; params.append(f"-{int(since_days)} days")
        sql += " ORDER BY (due_date IS NULL), due_date, id LIMIT ?"
        params.append(limit)
        rows = _tq(sql, tuple(params))
        return _dumps({"count": len(rows),
                       "tasks": _decrypt_rows(rows, ["title", "description"]),
                       "user_id": USER_ID})

    @mcp.tool(
        name="db-form-trend",
        description="""Trend formy (hrTSS + CTL/ATL/TSB) — Coggan uproszczony pod HR z bazy runs.

Metodologia:
- hrTSS per run = duration_min × (avg_hr / hr_max)² × 100 (skala ~40-150 dla typowego biegu)
- CTL = 42-day EWMA(TSS) — chronic training load (baza wytrzymałości)
- ATL = 7-day EWMA(TSS) — acute (świeże zmęczenie)
- TSB = CTL - ATL — form (+5 wypoczęty, -15 zmęczony, -30 = przetrenowanie)

Args:
  weeks: ile tygodni cofnąć (default 8, max 26). Wewnętrznie liczy +42 dni warmup dla CTL EWMA.
  hr_max: opcjonalne — HRmax user'a (default 195; TODO: read from users table).

Returns: {weeks: [{week_start, volume_km, num_runs, avg_hr, avg_pace_sec, tss,
                   ctl_end, atl_end, tsb_end}], hr_max_used, notes}
najnowszy pierwszy.

Perfect for mobile: 'jaka moja forma', 'trend CTL 8 tygodni', 'czy jestem świeży pod wyścig'."""
    )
    @_wrap_401
    def db_form_trend(weeks: int = 8, hr_max: int | None = None) -> str:
        weeks = max(1, min(int(weeks), 26))
        hrmax = int(hr_max) if hr_max else 195  # TODO: read from users profile
        if not (140 <= hrmax <= 220):
            return _dumps({"status": "error", "message": f"hr_max must be 140-220, got {hr_max!r}"})
        lookback_days = weeks * 7 + 42
        rows = _tq(f"""
            SELECT date, distance_km, duration_sec, moving_sec, hr_avg, pace_sec_per_km
              FROM runs
             WHERE user_id = ?
               AND date >= date('now', '-{lookback_days} days')
               AND distance_km IS NOT NULL AND distance_km > 0.5
             ORDER BY date ASC
        """, (USER_ID,))
        if not rows:
            return _dumps({"weeks": [], "hr_max_used": hrmax,
                           "message": "no runs in range", "user_id": USER_ID})
        from datetime import date as _d, timedelta
        from collections import defaultdict
        per_day_tss: dict = defaultdict(float)
        per_week: dict = defaultdict(lambda: {"volume_km": 0.0, "num_runs": 0,
                                              "hr_sum": 0, "hr_count": 0,
                                              "pace_sum": 0.0, "pace_count": 0,
                                              "tss": 0.0})
        for r in rows:
            dur_min = (r["moving_sec"] or r["duration_sec"] or 0) / 60.0
            hr = r["hr_avg"] or 0
            tss = dur_min * (hr / hrmax) ** 2 * 100.0 if (dur_min > 0 and hr > 0) else 0.0
            per_day_tss[r["date"]] += tss
            d = _d.fromisoformat(r["date"])
            wk = (d - timedelta(days=d.weekday())).isoformat()
            wd = per_week[wk]
            wd["volume_km"] += r["distance_km"] or 0
            wd["num_runs"] += 1
            wd["tss"] += tss
            if hr > 0:
                wd["hr_sum"] += hr; wd["hr_count"] += 1
            if r["pace_sec_per_km"]:
                wd["pace_sum"] += r["pace_sec_per_km"]; wd["pace_count"] += 1
        today = _d.today()
        start = today - timedelta(days=lookback_days)
        ctl = 0.0
        atl = 0.0
        ctl_alpha = 2.0 / (42 + 1)
        atl_alpha = 2.0 / (7 + 1)
        per_day_form: dict = {}
        day = start
        while day <= today:
            tss = per_day_tss.get(day.isoformat(), 0.0)
            ctl = ctl * (1 - ctl_alpha) + tss * ctl_alpha
            atl = atl * (1 - atl_alpha) + tss * atl_alpha
            per_day_form[day.isoformat()] = {"ctl": ctl, "atl": atl, "tsb": ctl - atl}
            day += timedelta(days=1)
        output = []
        for wk in sorted(per_week.keys(), reverse=True):
            wd = per_week[wk]
            wsd = _d.fromisoformat(wk)
            end_day = min(wsd + timedelta(days=6), today).isoformat()
            f = per_day_form.get(end_day, {"ctl": 0, "atl": 0, "tsb": 0})
            output.append({
                "week_start": wk,
                "volume_km": round(wd["volume_km"], 1),
                "num_runs": wd["num_runs"],
                "avg_hr": round(wd["hr_sum"] / wd["hr_count"]) if wd["hr_count"] else None,
                "avg_pace_sec": round(wd["pace_sum"] / wd["pace_count"]) if wd["pace_count"] else None,
                "tss": round(wd["tss"], 1),
                "ctl_end": round(f["ctl"], 1),
                "atl_end": round(f["atl"], 1),
                "tsb_end": round(f["tsb"], 1),
            })
            if len(output) >= weeks:
                break
        return _dumps({
            "weeks": output,
            "hr_max_used": hrmax,
            "notes": "hrTSS Coggan uproszczony (duration_min × (avg_hr/hrmax)² × 100). CTL=EWMA42, ATL=EWMA7. TSB>+5 = wypoczęty, TSB<-15 = zmęczony, TSB<-30 = przetrenowanie.",
            "user_id": USER_ID,
        })

    @mcp.tool(
        name="db-get-training-paces",
        description="""Tempa treningowe wg tabeli Jacka Danielsa dla podanego VDOT (interpolowane).

Args:
  vdot: liczba (30-65). Jesli None -> pobierze z db-current-vdot dla biezacego user_id.

Returns:
  vdot, paces_sec_per_km {E_min, E_max, M, T, I, R}, paces_formatted (m:ss/km), notes.

Uzycie: AI planujace tydzien wg Danielsa (80% E, 1x T ~20 min, opcjonalnie 1x I 3-5 min repeats)."""
    )
    @_wrap_401
    def db_get_training_paces(vdot: float | None = None) -> str:
        if vdot is None:
            rows = _tq("SELECT vdot FROM vdot_history WHERE user_id = ? ORDER BY date DESC LIMIT 1", (USER_ID,))
            if not rows:
                return _dumps({"status": "error", "message": "brak VDOT w DB dla tego user_id. Zapisz test 5km + wpisz do vdot_history."})
            vdot = float(rows[0]["vdot"])
        paces_table = {
            30: {"E_min": 480, "E_max": 540, "M": 420, "T": 385, "I": 355, "R": 320},
            35: {"E_min": 435, "E_max": 495, "M": 385, "T": 355, "I": 325, "R": 290},
            40: {"E_min": 405, "E_max": 465, "M": 355, "T": 325, "I": 300, "R": 265},
            45: {"E_min": 380, "E_max": 440, "M": 330, "T": 305, "I": 280, "R": 245},
            50: {"E_min": 360, "E_max": 420, "M": 315, "T": 285, "I": 260, "R": 230},
            55: {"E_min": 340, "E_max": 400, "M": 295, "T": 270, "I": 245, "R": 215},
            60: {"E_min": 325, "E_max": 385, "M": 280, "T": 255, "I": 230, "R": 205},
            65: {"E_min": 310, "E_max": 370, "M": 265, "T": 240, "I": 220, "R": 195},
        }
        v_clamped = max(30.0, min(65.0, float(vdot)))
        vdot_low = int(v_clamped // 5) * 5
        vdot_high = min(65, vdot_low + 5)
        if vdot_low == vdot_high:
            paces = dict(paces_table[vdot_low])
        else:
            alpha = (v_clamped - vdot_low) / (vdot_high - vdot_low)
            p_lo = paces_table[vdot_low]
            p_hi = paces_table[vdot_high]
            paces = {k: round(p_lo[k] + alpha * (p_hi[k] - p_lo[k])) for k in p_lo}
        def _fmt(sec: int) -> str:
            return f"{sec // 60}:{sec % 60:02d}/km"
        return _dumps({
            "vdot": vdot,
            "paces_sec_per_km": paces,
            "paces_formatted": {
                "E_easy": f"{_fmt(paces['E_min'])} - {_fmt(paces['E_max'])}",
                "M_marathon": _fmt(paces["M"]),
                "T_threshold": _fmt(paces["T"]),
                "I_interval": _fmt(paces["I"]),
                "R_repetition": _fmt(paces["R"]),
            },
            "notes": "Daniels: 80%+ tygodnia = E. T ~20 min steady. I 3-5 min. R 200-400m sprints. Dla juniorow (<16) omijaj I i R.",
            "user_id": USER_ID,
        })
