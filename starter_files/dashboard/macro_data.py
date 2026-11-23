"""Makroplan — cached queries + akcje zapisu (osobno od render, CODING_STANDARDS).

Plan "na dziś" (replan) liczony zawsze od nowa z realnego baseline'u —
to jest mechanizm reagowania na bieżąco. Referencyjny plan z DB służy do
mierzenia adherence (plan vs wykonanie).
"""
from __future__ import annotations
from datetime import date, timedelta

import streamlit as st

import api  # type: ignore
from planner import (MacroInput, build_macrocycle, monday, render_week, apply_safety,
                     baseline_from_actual)
from planner import repo, plan_detail
from planner.macro import WeekTarget


@st.cache_data(ttl=30)
def q_macro_context(user_id: int, today_iso: str) -> dict:
    with api.connect() as conn:
        return repo.load_context(conn, user_id, date.fromisoformat(today_iso))


@st.cache_data(ttl=60)
def q_reference_weeks(user_id: int, goal_id: int) -> list[dict]:
    with api.connect() as conn:
        return repo.reference_weeks(conn, user_id, goal_id)


@st.cache_data(ttl=60)
def q_shadow_weeks(user_id: int) -> list[dict]:
    """Plan porównawczy (status 'shadow', np. deterministyczny obok planu AI)."""
    with api.connect() as conn:
        g = api.macro.goal_by_status(conn, user_id=user_id, status="shadow")
        return repo.reference_weeks(conn, user_id, g["id"]) if g else []


@st.cache_data(ttl=60)
def q_macro_now(user_id: int, today_iso: str) -> dict | None:
    with api.connect() as conn:
        return plan_detail.macro_now(conn, user_id, date.fromisoformat(today_iso))


def to_week(d: dict) -> WeekTarget:
    """Tydzień z DB → WeekTarget (generator dni pracuje na dataclass)."""
    return WeekTarget(week_start=date.fromisoformat(d["week_start"]), phase=d["phase"],
                      week_in_phase=d["week_in_phase"], is_deload=bool(d["is_deload"]),
                      target_km=d["target_km"], long_km=d["long_km"] or 0.0,
                      quality=d.get("quality") or [], is_race_week=bool(d["is_race_week"]),
                      tune_up="B" if any(q["kind"] == "race" for q in d.get("quality") or []) else None)


def macro_input(ctx: dict, goal: dict, start: date, baseline_km: float | None = None) -> MacroInput:
    """Spina cel + kontekst usera w wejście planera (bez I/O)."""
    race_date = date.fromisoformat(goal["race_date"]) if goal.get("race_date") else None
    return MacroInput(
        start=start,
        baseline_km=baseline_km if baseline_km is not None else baseline_from_actual(ctx["completed_weeks_km"]),
        vdot=ctx["vdot"], race_date=race_date, distance_km=goal.get("distance_km"),
        peak_km=goal.get("peak_km"), runs_per_week=goal.get("runs_per_week") or 5,
        safety_max_km=ctx.get("safety_max_km"), last_race=ctx.get("last_race"),
    )


def replan_from_today(ctx: dict, goal: dict, today: date):
    """Makroplan od bieżącego tygodnia z realnym baseline — reakcja na odchylenia."""
    return build_macrocycle(macro_input(ctx, goal, monday(today)))


def week_preview(ctx: dict, goal: dict, week) -> tuple[list[dict], list[str]]:
    """Dni dla tygodnia + ostrzeżenia safety (ból z body_state)."""
    safe_week, warnings = apply_safety(week, ctx["max_pain_7d"])
    race_date = date.fromisoformat(goal["race_date"]) if goal.get("race_date") else None
    days = render_week(safe_week, ctx["vdot"], ctx["prefs"], goal.get("runs_per_week") or 5,
                       race_date=race_date, race_km=goal.get("distance_km"))
    return days, warnings


def save_goal_action(user_id: int, ctx: dict, goal: dict, today: date) -> int:
    start = monday(today) + (timedelta(weeks=1) if today.weekday() >= 4 else timedelta())
    inp = macro_input(ctx, goal, start, goal.get("baseline_km"))
    weeks = build_macrocycle(inp)
    payload = {k: goal.get(k) for k in ("race_id", "name", "race_date", "distance_km",
                                         "target_time_sec", "peak_km", "runs_per_week")}
    payload.update(start_date=start.isoformat(), baseline_km=inp.baseline_km)
    with api.connect() as conn:
        gid = repo.save_goal(conn, user_id, payload, weeks)
    q_macro_context.clear()
    q_reference_weeks.clear()
    return gid


def write_week_action(user_id: int, week_start: date, days: list[dict]) -> dict:
    with api.connect() as conn:
        res = repo.write_week(conn, user_id, week_start, days)
    st.cache_data.clear()  # plan tygodnia widoczny też w Przeglądzie / Bieganiu
    return res
