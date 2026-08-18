"""Zakladka Przeglad — metryki top row + biezacy tydzien + body state + volume chart.

**ODSTEPSTWO od SRP:** ten plik ma >200 linii bo `page_overview` to naturalny
dashboard aggregujacy 4 sekcje (metryki / plan tygodnia z komponentami /
body state / volume chart). Podzial na sub-sekcje bylby przedwczesny —
sa scisle powiazane wizualnie i bez zaleznosci runtime.
"""
from __future__ import annotations
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.constants import CATEGORY_TABS, STATUS_OPTIONS
from dashboard.queries import (
    q_weekly_volume, q_vdot_history, q_races_history, q_races_upcoming,
    q_current_week_with_components, q_body_state,
)
from dashboard.callbacks import _apply_component_status, _apply_planned_status
from dashboard.helpers import fmt_pace, fmt_time
from dashboard.utils import get_user_id


def page_overview():
    st.title("🏃 Przegląd")

    user_id = get_user_id()

    # --- Top metrics row ---
    # Single volume query (12 weeks) — slice for both metrics-row (top 4) and chart below.
    vol_df_12 = q_weekly_volume(weeks=12, user_id=user_id).sort_values("week_start", ascending=False)
    vdot_hist = q_vdot_history(limit=1, user_id=user_id)
    races_hist = q_races_history(user_id=user_id)
    races_up = q_races_upcoming(user_id=user_id)

    col1, col2, col3, col4, col5 = st.columns(5)
    if not vdot_hist.empty:
        v = vdot_hist.iloc[0]
        col1.metric("VDOT", int(v["vdot"]),
                    help=f"T-pace: {fmt_pace(v['t_pace_sec'])} | {v['date']}")
    pb_hm = next((r for r in races_hist if abs(r["distance_km"] - 21.0975) < 0.5 and r["is_pb"]), None)
    if pb_hm:
        col2.metric("PB HM", fmt_time(pb_hm["actual_time_sec"]),
                    help=f"{pb_hm['name']} ({pb_hm['date']})")
    if not vol_df_12.empty:
        last_week_km = float(vol_df_12.iloc[0]["distance_km"])
        avg_4w = float(vol_df_12["distance_km"].head(4).mean())
        col3.metric("Ostatni tydzień", f"{last_week_km:.1f} km",
                    delta=f"{last_week_km - avg_4w:+.1f} vs avg 4w")
        col4.metric("Średnia 4 tyg", f"{avg_4w:.1f} km")
    if races_up:
        nxt = races_up[0]
        days_left = (datetime.strptime(nxt["date"], "%Y-%m-%d").date() - datetime.now().date()).days
        target = fmt_time(nxt["target_time_sec"]) if nxt.get("target_time_sec") else "—"
        col5.metric(f"🏁 {nxt['name'][:20]}", f"{days_left} dni",
                    help=f"{nxt['date']} | cel: {target}")

    st.divider()

    # --- Biezacy tydzien + Body state ---
    left, right = st.columns([3, 2])

    with left:
        _render_current_week(user_id)

    with right:
        _render_body_state()

    st.divider()

    # --- Wolumen tygodniowy chart ---
    st.subheader("📊 Wolumen tygodniowy (12 tyg)")
    if not vol_df_12.empty:
        vol_chart = vol_df_12.sort_values("week_start")
        fig = px.bar(vol_chart, x="week_start", y="distance_km",
                     color="trend", text="distance_km",
                     color_discrete_map={"peak": "#22c55e", "recovery": "#f59e0b", None: "#3b82f6"},
                     labels={"week_start": "Tydzień (pon)", "distance_km": "km", "trend": "Trend"})
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        fig.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)


def _render_current_week(user_id: int):
    """Sekcja biezacego tygodnia — tabs kategorii, expandery per plan, selectboxy statusu."""
    st.subheader("📅 Bieżący tydzień")
    week, comps_by_pid = q_current_week_with_components(user_id=user_id)
    if not week:
        st.info(
            "Brak planu na ten tydzień. "
            "Jeśli powinien być — kliknij **🔄 Odśwież dane** w sidebarze (stale cache). "
            "Jeśli faktycznie nie ma → uruchom `db/seed_current_week.py`."
        )
        return

    status_labels = {k: v for k, v in STATUS_OPTIONS}
    status_keys = [k for k, _ in STATUS_OPTIONS]

    def _cat_bucket(p):
        c = p.get("type_category")
        return c if c in ("run", "strength") else "other"

    tabs = st.tabs([label for _, label in CATEGORY_TABS])
    for (cat_key, _), tab in zip(CATEGORY_TABS, tabs):
        with tab:
            items = week if cat_key == "all" else [p for p in week if _cat_bucket(p) == cat_key]
            if not items:
                st.caption("_Brak wpisów w tej kategorii._")
                continue
            for p in items:
                _render_planned_row(p, comps_by_pid, status_labels, status_keys, cat_key)


def _render_planned_row(p, comps_by_pid, status_labels, status_keys, cat_key):
    """Render jednego planu (expander z komponentami lub parent-level status)."""
    pid = p["id"]
    comps = comps_by_pid.get(pid, [])
    header_bits = [
        p.get("status_icon") or "",
        p["date"],
        p.get("type_icon") or "",
        (p.get("title") or "").strip() or p.get("type_display", ""),
    ]
    header = " · ".join(b for b in header_bits if b)
    if p.get("weather_temp_c") is not None:
        wnote = p.get("weather_note") or ""
        header += f"  ({int(p['weather_temp_c'])}°C{(' · ' + wnote) if wnote else ''})"
    with st.expander(header, expanded=(p["date"] == datetime.now().strftime("%Y-%m-%d"))):
        if p.get("notes"):
            st.caption(f"📝 {p['notes']}")
        if not comps:
            # Fallback: parent-level status control (title puste albo migrate padło)
            default_idx_p = status_keys.index(p.get("status_key")) if p.get("status_key") in status_keys else 0
            col_p_status, col_p_notes, col_p_btn = st.columns([2, 3, 1])
            new_p_status = col_p_status.selectbox(
                "Status", status_keys, index=default_idx_p,
                format_func=lambda k: status_labels[k],
                key=f"pw_status_{cat_key}_{pid}", label_visibility="collapsed",
            )
            new_p_notes = col_p_notes.text_input(
                "Notatka", value=p.get("actual_notes") or "",
                key=f"pw_notes_{cat_key}_{pid}", placeholder="notatka (opcjonalnie)",
                label_visibility="collapsed",
            )
            if col_p_btn.button("Zapisz", key=f"pw_save_{cat_key}_{pid}"):
                _apply_planned_status(pid, new_p_status, new_p_notes)
                st.toast(f"✅ {p.get('title','?')[:30]} → {status_labels[new_p_status]}", icon="☁️")
                st.rerun()
            return
        for c in comps:
            cid = c["id"]
            col_lbl, col_status, col_notes, col_btn = st.columns([3, 2, 3, 1])
            col_lbl.markdown(f"{c.get('status_icon','')} **{c['label']}**")
            default_idx = status_keys.index(c["status_key"]) if c["status_key"] in status_keys else 0
            new_status = col_status.selectbox(
                "Status", status_keys, index=default_idx,
                format_func=lambda k: status_labels[k],
                key=f"pwc_status_{cat_key}_{cid}", label_visibility="collapsed",
            )
            new_notes = col_notes.text_input(
                "Notatka", value=c.get("actual_notes") or "",
                key=f"pwc_notes_{cat_key}_{cid}", placeholder="notatka (opcjonalnie)",
                label_visibility="collapsed",
            )
            if col_btn.button("Zapisz", key=f"pwc_save_{cat_key}_{cid}"):
                _apply_component_status(cid, pid, new_status, new_notes)
                st.toast(f"✅ {c['label']} → {status_labels[new_status]}", icon="☁️")
                st.rerun()


def _render_body_state():
    """Sekcja Stan ciala — tabela 14 dni + trend 30 dni per lokalizacja."""
    st.subheader("🩺 Stan ciała (14 dni)")
    user_id = get_user_id()
    # Single 30-day query — reuse for table (last 14 dni) + trend chart (30 dni).
    body_30 = pd.DataFrame(q_body_state(since="-30 days", user_id=user_id))
    if body_30.empty:
        st.info("Brak wpisów body_state.")
        return
    body_30["date"] = pd.to_datetime(body_30["date"])
    cutoff_14d = pd.Timestamp.now() - pd.Timedelta(days=14)
    bdf = body_30[body_30["date"] >= cutoff_14d].copy()
    bdf["pain_display"] = bdf.apply(
        lambda r: f"{r['pain_0_10']}/10" if pd.notna(r['pain_0_10']) else ("DOMS" if r['doms'] else "—"),
        axis=1
    )
    bdf["date_str"] = bdf["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        bdf[["date_str", "location", "pain_display", "notes"]].rename(columns={
            "date_str": "Data", "location": "Gdzie", "pain_display": "Ból", "notes": "Notatki"
        }),
        hide_index=True, use_container_width=True, height=220,
    )
    # Trend bólu per lokalizacja (30 dni)
    trend = body_30[body_30["pain_0_10"].notna()]
    if not trend.empty:
        fig = px.line(trend.sort_values("date"), x="date", y="pain_0_10",
                      color="location", markers=True,
                      labels={"pain_0_10": "Ból 0-10", "date": "", "location": ""})
        fig.update_layout(height=220, margin=dict(t=10, b=10, l=10, r=10),
                          yaxis=dict(range=[-0.3, 10], dtick=2),
                          legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, use_container_width=True)
