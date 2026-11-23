"""Zakladka Makroplan — cel, progres do celu, plan vs wykonanie, generator tygodnia."""
from __future__ import annotations
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from dashboard.helpers import fmt_time
from dashboard.macro_chart import render_progress_chart
from dashboard.macro_data import (q_macro_context, q_reference_weeks, replan_from_today,
                                  week_preview, save_goal_action, write_week_action,
                                  q_shadow_weeks, q_macro_now, to_week)
from dashboard.pages.macro_plan_view import render_this_week, render_plan_table, render_rules
from dashboard.queries import q_races_upcoming
from dashboard.utils import get_user_id
from planner import adherence, goal_progress, replan_advice, baseline_from_actual, monday
from planner.methodology import PHASE_LABELS

DISTANCES = {"5 km": 5.0, "10 km": 10.0, "Półmaraton": 21.0975, "Maraton": 42.195}
VDOT_STALE_DAYS = 90


def _parse_time(txt: str) -> int | None:
    parts = [int(p) for p in txt.strip().split(":") if p.strip().isdigit()]
    if not parts:
        return None
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


def _goal_form(user_id: int, ctx: dict, today: date, current: dict | None) -> None:
    races = q_races_upcoming(user_id=user_id)
    with st.expander("🎯 " + ("Zmień cel" if current else "Ustaw cel"), expanded=not current):
        with st.form("macro_goal"):
            opts = ["— własny —"] + [f"{r['date']} · {r['name']}" for r in races]
            pick = st.selectbox("Start z kalendarza (tabela races)", opts)
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Nazwa celu", value="")
            race_date = c2.date_input("Data startu", value=today + timedelta(weeks=16))
            dist = c3.selectbox("Dystans", list(DISTANCES), index=2)
            c4, c5, c6, c7 = st.columns(4)
            target = c4.text_input("Czas docelowy (H:MM:SS)", value="1:35:00")
            runs = c5.number_input("Biegów / tydz.", 2, 7, 5)
            base = c6.number_input("Baseline km/tydz.", 0.0, 200.0,
                                   float(baseline_from_actual(ctx["completed_weeks_km"])), step=1.0,
                                   help="Domyślnie: średnia z 4 ostatnich zakończonych tygodni (runs).")
            peak = c7.number_input("Szczyt km/tydz. (0 = auto)", 0.0, 200.0, 0.0, step=1.0)
            if st.form_submit_button("💾 Zapisz cel i wygeneruj makroplan", type="primary"):
                race = races[opts.index(pick) - 1] if pick != opts[0] else None
                goal = {
                    "race_id": race["id"] if race else None,
                    "name": (race["name"] if race else name) or "Cel",
                    "race_date": race["date"] if race else race_date.isoformat(),
                    "distance_km": race["distance_km"] if race else DISTANCES[dist],
                    "target_time_sec": (race or {}).get("target_time_sec") or _parse_time(target),
                    "runs_per_week": int(runs), "baseline_km": base, "peak_km": peak or None,
                }
                save_goal_action(user_id, ctx, goal, today)
                st.success("Zapisano cel i referencyjny makroplan.")
                st.rerun()


def _kpis(ctx: dict, goal: dict, prog: dict, adh: dict) -> None:
    c = st.columns(5)
    c[0].metric("VDOT teraz", ctx["vdot"], help=f"Ostatni wpis vdot_history: {ctx['vdot_date']}")
    if prog.get("goal_vdot"):
        c[1].metric("VDOT celu", prog["goal_vdot"], delta=f"{-prog['vdot_gap']:+.1f}")
        c[2].metric("Prognoza na start", fmt_time(prog["predicted_at_race_sec"]),
                    help=f"Dziś: {fmt_time(prog['predicted_now_sec'])}; cel: {fmt_time(goal['target_time_sec'])}")
        c[3].metric("Status", prog["status_label"])
    if prog.get("weeks_left") is not None:
        c[4].metric("Tygodnie do startu", f"{prog['weeks_left']:.0f}")
    if adh["overall_ratio"] is not None:
        st.caption(f"Wykonanie planu (zakończone tygodnie): **{adh['overall_ratio']:.0%}**")
    if ctx["vdot_date"] and (date.today() - date.fromisoformat(ctx["vdot_date"])).days > VDOT_STALE_DAYS:
        st.warning(f"VDOT z {ctx['vdot_date']} — ponad {VDOT_STALE_DAYS} dni. Zrób test / wpisz wynik startu, "
                   "inaczej tempa i prognoza są nieaktualne.")


def _week_generator(user_id: int, ctx: dict, goal: dict, replan) -> None:
    st.subheader("🗓️ Generator tygodnia")
    if not replan:
        st.info("Brak tygodni do zaplanowania (start minął?).")
        return
    labels = [f"{w.week_start} · {PHASE_LABELS[w.phase]} {w.week_in_phase}"
              f"{' · odciążenie' if w.is_deload else ''} · {w.target_km:g} km" for w in replan[:4]]
    idx = st.radio("Tydzień", range(len(labels)), format_func=labels.__getitem__, horizontal=False)
    week = replan[idx]
    days, warnings = week_preview(ctx, goal, week)
    for w in warnings:
        st.warning(w)
    df = pd.DataFrame(days)[["date", "type_key", "title", "target_distance_km", "notes"]]
    df["dzień"] = pd.to_datetime(df["date"]).dt.day_name()
    st.dataframe(df[["date", "dzień", "type_key", "title", "target_distance_km", "notes"]],
                 hide_index=True, use_container_width=True)
    st.caption(f"Suma: {df['target_distance_km'].sum():.1f} km (cel tygodnia {week.target_km:g} km). "
               "Zapis zastępuje tylko biegi o statusie 'planned' — siłownia i wykonane zostają.")
    if st.button("✅ Zapisz ten tydzień do planu", type="primary"):
        res = write_week_action(user_id, week.week_start, days)
        st.success(f"Zapisano {res['inserted']} treningów"
                   + (f"; pominięto {', '.join(res['skipped_dates'])} (już wykonane)" if res["skipped_dates"] else ""))


def page_macro():
    st.title("🧭 Makroplan")
    user_id, today = get_user_id(), date.today()
    ctx = q_macro_context(user_id, today.isoformat())
    goal = ctx["goal"]
    _goal_form(user_id, ctx, today, goal)
    if not goal:
        st.info("Ustaw cel, żeby zobaczyć makroplan i progres.")
        return
    st.subheader(f"🎯 {goal['name']} — {goal['race_date'] or 'bez daty'}")
    reference = q_reference_weeks(user_id, goal["id"])
    race_date = date.fromisoformat(goal["race_date"]) if goal["race_date"] else None
    prog = goal_progress(ctx["vdot"], goal["distance_km"] or 21.0975, goal["target_time_sec"], race_date, today)
    adh = adherence(reference, ctx["actual_km"], today)
    _kpis(ctx, goal, prog, adh)
    now = q_macro_now(user_id, today.isoformat())
    render_this_week(now)
    shadow = q_shadow_weeks(user_id)
    if shadow:   # plan AI aktywny + deterministyczny do porównania (i jako źródło generatora)
        this_monday = monday(today).isoformat()
        replan = [to_week(d) for d in shadow if d["week_start"] >= this_monday]
        names = {"ref_name": f"Plan aktywny ({goal.get('source') or 'ref'})",
                 "replan_name": "Plan deterministyczny"}
    else:
        replan = replan_from_today(ctx, goal, today)
        names = {}
    st.plotly_chart(render_progress_chart(reference, ctx["actual_km"], [w.to_dict() for w in replan],
                                          monday(today).isoformat(), **names), use_container_width=True)
    render_plan_table(reference, shadow)
    render_rules(now)
    for tip in replan_advice(adh, ctx["max_pain_7d"]):
        st.markdown(f"- {tip}")
    with st.expander("📋 Tabela: plan vs wykonanie"):
        st.dataframe(pd.DataFrame(adh["weeks"]), hide_index=True, use_container_width=True)
    st.divider()
    # Od piątku bieżący tydzień jest praktycznie zamknięty → generator od następnego.
    _week_generator(user_id, ctx, goal, replan[1:] if today.weekday() >= 4 else replan)
