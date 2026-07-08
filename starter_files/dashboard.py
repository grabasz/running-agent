"""Streamlit dashboard for the running project.

Run locally:
    streamlit run dashboard.py

Or from project root with custom port:
    streamlit run dashboard.py --server.port 8501

Deploy on Streamlit Cloud (https://share.streamlit.io):
  - Main file: dashboard.py
  - Secrets (TOML): TURSO_DATABASE_URL = "libsql://..."  and  TURSO_AUTH_TOKEN = "..."
  - On cold start the app pulls a fresh snapshot from Turso into a local replica
    file (see db.api.bootstrap_cloud). All queries then read from that snapshot,
    so no per-query round-trip to Turso.
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "db"))

# Bridge Streamlit Cloud secrets -> environment vars so db.api / db.sync pick them up.
# On localhost st.secrets is empty and this is a no-op.
try:
    for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
        if _key in st.secrets and not os.getenv(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass  # no secrets.toml — local sqlite mode

# Point the bootstrap replica at a writable tmp dir (Streamlit Cloud's working
# dir is ephemeral but /tmp is fine; locally we get a tmp file too, harmless).
if os.getenv("TURSO_DATABASE_URL") and not os.getenv("RUNNING_DB_PATH"):
    os.environ["RUNNING_DB_PATH"] = str(Path(tempfile.gettempdir()) / "running_replica.db")

import api  # type: ignore

# Must be the FIRST Streamlit command — before the password gate renders anything.
st.set_page_config(
    page_title="Bartek Running",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner="Pobieram dane z Turso…")
def _bootstrap_once():
    """Run once per Streamlit session. In cloud mode pulls fresh snapshot
    from Turso; in local mode returns None (data.db is already the source)."""
    return api.bootstrap_cloud()


# ============================================
# Password gate (only enforced when APP_PASSWORD secret is set)
# ============================================

def _check_password() -> bool:
    expected = None
    try:
        expected = st.secrets.get("APP_PASSWORD")
    except Exception:
        expected = None
    expected = expected or os.getenv("APP_PASSWORD")

    if not expected:
        return True  # no password configured — open access (local dev)

    if st.session_state.get("auth_ok"):
        return True

    st.title("🔒 Bartek Running")
    pw = st.text_input("Hasło", type="password", key="pw_input")
    if st.button("Zaloguj"):
        if pw == expected:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Złe hasło.")
    return False


if not _check_password():
    st.stop()

_REPLICA = _bootstrap_once()
_CLOUD_MODE = _REPLICA is not None


# ============================================
# DB helpers (cached for speed)
# ============================================

@st.cache_data(ttl=30)
def q_today():
    with api.connect() as conn:
        return [dict(r) for r in api.planned.today(conn)]


@st.cache_data(ttl=30)
def q_upcoming(days=7):
    with api.connect() as conn:
        return [dict(r) for r in api.planned.upcoming(conn, days=f"+{days} days", limit=7)]


@st.cache_data(ttl=30)
def q_current_week():
    with api.connect() as conn:
        return [dict(r) for r in api.planned.current_week(conn)]


@st.cache_data(ttl=15)
def q_current_week_with_components():
    """Zwraca plany bieżącego tygodnia z komponentami zgroupowanymi per planned_id."""
    with api.connect() as conn:
        week = [dict(r) for r in api.planned.current_week(conn)]
        by_planned: dict[int, list[dict]] = {}
        for p in week:
            comps = [dict(c) for c in api.planned.components_for(conn, planned_workout_id=p["id"])]
            by_planned[p["id"]] = comps
    return week, by_planned


def _apply_component_status(component_id: int, planned_id: int, status_key: str, notes: str | None) -> None:
    """Callback: update komponentu, sync parent, push do Turso, unieważnij cache."""
    with api.connect() as conn:
        api.planned.mark_component_status(
            conn, id=component_id, status_key=status_key, actual_notes=notes or None
        )
        api.planned.sync_parent_status_from_components(conn, planned_workout_id=planned_id)
        conn.commit()
    # Cache-bust: kolejne quiery zobaczą świeże dane
    q_current_week.clear()
    q_current_week_with_components.clear()
    q_today.clear()
    # Turso push - best effort, nie przerywaj UI gdy padnie
    try:
        from sync import push as _push  # type: ignore
        _push(verbose=False)
    except Exception as e:
        st.warning(f"Push do Turso nieudany: {e}")


@st.cache_data(ttl=60)
def q_weekly_volume(weeks=12):
    with api.connect() as conn:
        rows = [dict(r) for r in api.weekly_volume.recent(conn, weeks=weeks)]
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def q_runs_recent(limit=30):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.runs.recent(conn, limit=limit)])


@st.cache_data(ttl=60)
def q_runs_with_dynamics(since="-90 days"):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.runs.recent_with_dynamics(conn, since=since)])


@st.cache_data(ttl=60)
def q_gym_sessions(limit=20):
    with api.connect() as conn:
        return [dict(r) for r in api.gym.sessions_recent(conn, limit=limit)]


@st.cache_data(ttl=60)
def q_exercise_progression(exercise, limit=30):
    with api.connect() as conn:
        return pd.DataFrame([
            dict(r) for r in api.gym.exercise_progression(conn, exercise=exercise, limit=limit)
        ])


@st.cache_data(ttl=60)
def q_top_exercises(since="2026-01-01"):
    with api.connect() as conn:
        return pd.DataFrame([
            dict(r) for r in api.gym.top_exercises_by_volume(conn, since=since)
        ])


@st.cache_data(ttl=60)
def q_races_upcoming():
    with api.connect() as conn:
        return [dict(r) for r in api.races.upcoming(conn)]


@st.cache_data(ttl=60)
def q_races_history():
    with api.connect() as conn:
        return [dict(r) for r in api.races.history(conn)]


@st.cache_data(ttl=60)
def q_vdot_history(limit=10):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.vdot.history(conn, limit=limit)])


@st.cache_data(ttl=30)
def q_body_state(since="-14 days"):
    with api.connect() as conn:
        return [dict(r) for r in api.body.state_recent(conn, since=since)]


# ============================================
# Formatters
# ============================================

def fmt_pace(sec):
    if not sec or sec <= 0:
        return "—"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}/km"


def fmt_time(sec):
    if not sec or sec <= 0:
        return "—"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# Project VDOT scale (fitness.md) ≈ canonical Daniels & Gilbert VDOT + 6.3.
# Verified against fitness.md Race Predictors @55: 20:18 / 42:21 / 1:33:43 / 3:15:28 (±5s).
VDOT_CAL_OFFSET = 6.3


def daniels_race_time(vdot: float, distance_m: float) -> int:
    """Predicted race time (sec) for a project-scale VDOT — Daniels & Gilbert equations.

    Solves for T where VO2(velocity) / %VO2max(T) == canonical vdot (bisection).
    """
    import math

    vdot = vdot - VDOT_CAL_OFFSET

    def pct_vo2max(t_min):
        return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)

    def vo2(v_m_per_min):
        return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min ** 2

    lo, hi = 4.0, 420.0  # minutes
    for _ in range(60):
        mid = (lo + hi) / 2
        if vo2(distance_m / mid) / pct_vo2max(mid) > vdot:
            lo = mid  # running too fast for this vdot -> need more time
        else:
            hi = mid
    return int(round((lo + hi) / 2 * 60))


# ============================================
# Page: Przegląd
# ============================================

def page_overview():
    st.title("🏃 Przegląd")

    # --- Top metrics row ---
    vdot_hist = q_vdot_history(limit=1)
    races_hist = q_races_history()
    races_up = q_races_upcoming()
    vol_df = q_weekly_volume(weeks=4)

    col1, col2, col3, col4, col5 = st.columns(5)
    if not vdot_hist.empty:
        v = vdot_hist.iloc[0]
        col1.metric("VDOT", int(v["vdot"]),
                    help=f"T-pace: {fmt_pace(v['t_pace_sec'])} | {v['date']}")
    pb_hm = next((r for r in races_hist if abs(r["distance_km"] - 21.0975) < 0.5 and r["is_pb"]), None)
    if pb_hm:
        col2.metric("PB HM", fmt_time(pb_hm["actual_time_sec"]),
                    help=f"{pb_hm['name']} ({pb_hm['date']})")
    if not vol_df.empty:
        last_week_km = float(vol_df.iloc[0]["distance_km"]) if len(vol_df) else 0
        avg_4w = float(vol_df["distance_km"].head(4).mean())
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

    # --- Dziś + jutro ---
    left, right = st.columns([3, 2])

    with left:
        st.subheader("📅 Bieżący tydzień")
        week, comps_by_pid = q_current_week_with_components()
        if not week:
            st.info(
                "Brak planu na ten tydzień. "
                "Jeśli powinien być — kliknij **🔄 Odśwież dane** w sidebarze (stale cache). "
                "Jeśli faktycznie nie ma → uruchom `db/seed_current_week.py`."
            )
        else:
            CATEGORY_TABS = [
                ("all",      "🗓️ Wszystko"),  # default (Streamlit auto-selects first)
                ("run",      "🏃 Biegi"),
                ("strength", "💪 Siłownia"),
                ("other",    "🧘 Inne"),  # recovery / cross / mobility
            ]
            STATUS_OPTIONS = [
                ("planned",  "⏸️ Zaplanowany"),
                ("done",     "✅ Wykonany"),
                ("modified", "⚠️ Zmodyfikowany"),
                ("skipped",  "❌ Pominięty"),
            ]
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
                                st.caption("_Brak komponentów — uruchom `python db/migrate_components.py` żeby rozbić `title` po ` + `._")
                                continue
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

    with right:
        st.subheader("🩺 Stan ciała (14 dni)")
        body = q_body_state(since="-14 days")
        if not body:
            st.info("Brak wpisów body_state.")
        else:
            bdf = pd.DataFrame(body)
            bdf["pain_display"] = bdf.apply(
                lambda r: f"{r['pain_0_10']}/10" if pd.notna(r['pain_0_10']) else ("DOMS" if r['doms'] else "—"),
                axis=1
            )
            st.dataframe(
                bdf[["date", "location", "pain_display", "notes"]].rename(columns={
                    "date": "Data", "location": "Gdzie", "pain_display": "Ból", "notes": "Notatki"
                }),
                hide_index=True, use_container_width=True, height=220,
            )
            # Trend bólu per lokalizacja (30 dni)
            trend = pd.DataFrame(q_body_state(since="-30 days"))
            trend = trend[trend["pain_0_10"].notna()]
            if not trend.empty:
                trend["date"] = pd.to_datetime(trend["date"])
                fig = px.line(trend.sort_values("date"), x="date", y="pain_0_10",
                              color="location", markers=True,
                              labels={"pain_0_10": "Ból 0-10", "date": "", "location": ""})
                fig.update_layout(height=220, margin=dict(t=10, b=10, l=10, r=10),
                                  yaxis=dict(range=[-0.3, 10], dtick=2),
                                  legend=dict(orientation="h", y=-0.25))
                st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Wolumen tygodniowy chart ---
    st.subheader("📊 Wolumen tygodniowy (12 tyg)")
    vol_df_12 = q_weekly_volume(weeks=12).sort_values("week_start")
    if not vol_df_12.empty:
        fig = px.bar(vol_df_12, x="week_start", y="distance_km",
                     color="trend", text="distance_km",
                     color_discrete_map={"peak": "#22c55e", "recovery": "#f59e0b", None: "#3b82f6"},
                     labels={"week_start": "Tydzień (pon)", "distance_km": "km", "trend": "Trend"})
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        fig.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)


# ============================================
# Page: Bieg
# ============================================

def page_running():
    st.title("🏃 Bieganie")

    runs_df = q_runs_recent(limit=50)
    if runs_df.empty:
        st.warning("Brak biegów w DB. Wywołaj `/run` z Claude'a żeby zapisać aktualne dane.")
        return

    runs_df["date"] = pd.to_datetime(runs_df["date"])
    runs_df = runs_df.sort_values("date", ascending=False)

    # Filtry
    types = sorted(runs_df["type"].dropna().unique())
    selected_types = st.multiselect("Typ biegu", types, default=types)
    df = runs_df[runs_df["type"].isin(selected_types)] if selected_types else runs_df

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Tempo w czasie")
        if df["pace_sec_per_km"].notna().any():
            df_pace = df[df["pace_sec_per_km"].notna()].copy()
            df_pace["pace_min"] = df_pace["pace_sec_per_km"] / 60
            fig = px.scatter(df_pace, x="date", y="pace_min", color="type",
                             size="distance_km", hover_data=["name", "hr_avg"],
                             labels={"pace_min": "Tempo (min/km)", "date": "Data"})
            fig.update_yaxes(autorange="reversed")  # szybciej = niżej
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("HR avg vs pace")
        if df["hr_avg"].notna().any() and df["pace_sec_per_km"].notna().any():
            d = df.dropna(subset=["hr_avg", "pace_sec_per_km"]).copy()
            d["pace_min"] = d["pace_sec_per_km"] / 60
            fig = px.scatter(d, x="pace_min", y="hr_avg", color="type",
                             size="distance_km", hover_data=["date", "name"],
                             labels={"pace_min": "Tempo (min/km)", "hr_avg": "HR avg"})
            fig.update_xaxes(autorange="reversed")
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

    # Running dynamics (Garmin only)
    dyn = q_runs_with_dynamics(since="-90 days")
    if not dyn.empty and dyn["gct_balance_left_pct"].notna().any():
        st.divider()
        st.subheader("🦵 Running dynamics — GCT Balance L/R + kadencja")
        st.caption("50% = idealna symetria; pas 49-51% = norma. Wyższa kadencja przywraca symetrię "
                   "(potwierdzone: 170→176 spm wyprostowało balance z 48.2% do 49-50%).")
        dyn["date"] = pd.to_datetime(dyn["date"])
        dyn = dyn.sort_values("date")
        fig = go.Figure()
        fig.add_hrect(y0=49, y1=51, fillcolor="#22c55e", opacity=0.08, line_width=0)
        fig.add_trace(go.Scatter(x=dyn["date"], y=dyn["gct_balance_left_pct"],
                                  mode="lines+markers", name="GCT bal L%",
                                  line=dict(color="#3b82f6", width=2)))
        if "cadence_avg" in dyn.columns and dyn["cadence_avg"].notna().any():
            fig.add_trace(go.Scatter(x=dyn["date"], y=dyn["cadence_avg"],
                                      mode="lines+markers", name="Kadencja (spm)",
                                      yaxis="y2", line=dict(color="#f59e0b", width=2, dash="dot")))
        fig.add_hline(y=50, line_dash="dash", line_color="gray",
                      annotation_text="symetria 50%", annotation_position="top right")
        fig.update_layout(
            height=300, xaxis_title="Data",
            yaxis=dict(title="L% (50 = symetria)"),
            yaxis2=dict(title="spm", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Tabela
    st.divider()
    st.subheader("Ostatnie 10 biegów")
    cols = ["date", "start_time", "name", "distance_km", "pace_sec_per_km", "hr_avg", "type", "source"]
    cols = [c for c in cols if c in df.columns]  # start_time gracefully missing pre-migration
    display_df = df[cols].copy()
    display_df["tempo"] = display_df["pace_sec_per_km"].apply(fmt_pace)
    display_df["dystans"] = display_df["distance_km"].apply(lambda x: f"{x:.2f} km" if pd.notna(x) else "—")
    show_cols = ["date"] + (["start_time"] if "start_time" in display_df.columns else []) + \
                ["name", "dystans", "tempo", "hr_avg", "type", "source"]
    rename_map = {
        "date": "Data", "start_time": "Godz.", "name": "Nazwa",
        "hr_avg": "HR śr", "type": "Typ", "source": "Źródło",
    }
    st.dataframe(
        display_df[show_cols].head(10).rename(columns=rename_map),
        hide_index=True, use_container_width=True, height=400,
    )
    if len(display_df) > 10:
        with st.expander(f"Pokaż wszystkie ({len(display_df)})"):
            st.dataframe(
                display_df[show_cols].rename(columns=rename_map),
                hide_index=True, use_container_width=True,
            )


# ============================================
# Page: Siłownia
# ============================================

def page_strength():
    st.title("💪 Siłownia")

    sessions = q_gym_sessions(limit=10)
    if not sessions:
        st.warning("Brak sesji siłowni w DB. Wywołaj `/silownia` żeby zaimportować z Garmina.")
        return

    # Selector ćwiczenia
    with api.connect() as conn:
        ex_list = [r["exercise"] for r in conn.execute(
            "SELECT DISTINCT exercise FROM gym_sets ORDER BY exercise"
        ).fetchall()]

    selected_ex = st.selectbox("Wybierz ćwiczenie", ex_list,
                                index=ex_list.index("RDL") if "RDL" in ex_list else 0)

    progression = q_exercise_progression(selected_ex, limit=30)
    if not progression.empty:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader(f"Max ciężar {selected_ex}")
            df_w = progression[progression["weight_kg"].notna() & (progression["weight_kg"] > 0)].copy()
            if not df_w.empty:
                df_w["date"] = pd.to_datetime(df_w["date"])
                agg = df_w.groupby("date").agg(max_w=("weight_kg", "max")).reset_index()
                fig = px.line(agg, x="date", y="max_w", markers=True,
                              labels={"max_w": "Max ciężar (kg)", "date": "Data"})
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Bodyweight exercise — brak ciężaru do śledzenia")

        with col2:
            st.subheader(f"Wolumen sesji (reps × kg)")
            df_v = progression[progression["weight_kg"].notna() & (progression["weight_kg"] > 0)].copy()
            if not df_v.empty:
                df_v["volume"] = df_v["reps"] * df_v["weight_kg"]
                df_v["date"] = pd.to_datetime(df_v["date"])
                agg = df_v.groupby("date").agg(volume=("volume", "sum")).reset_index()
                fig = px.bar(agg, x="date", y="volume",
                             labels={"volume": "Volume (kg)", "date": "Data"})
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Top exercises by tonnage
    st.subheader("Top ćwiczenia po tonażu (od 2026-01-01)")
    top = q_top_exercises(since="2026-01-01")
    if not top.empty:
        top_filtered = top[top["volume_kg"] > 0].head(12)
        fig = px.bar(top_filtered, y="exercise", x="volume_kg", orientation="h",
                     text="volume_kg",
                     labels={"exercise": "Ćwiczenie", "volume_kg": "Tonnage (kg)"})
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        fig.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Ostatnie sesje")
    sess_df = pd.DataFrame(sessions)
    st.dataframe(
        sess_df[["date", "duration_min", "hr_avg", "calories", "context"]].rename(columns={
            "date": "Data", "duration_min": "Czas (min)", "hr_avg": "HR śr",
            "calories": "kcal", "context": "Kontekst"
        }),
        hide_index=True, use_container_width=True,
    )


# ============================================
# Page: Wyścigi
# ============================================

def page_races():
    st.title("🏆 Wyścigi")

    # Upcoming
    upcoming = q_races_upcoming()
    history = q_races_history()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📅 Nadchodzące")
        if upcoming:
            df = pd.DataFrame(upcoming)
            df["target"] = df["target_time_sec"].apply(
                lambda x: "—" if pd.isna(x) or x <= 0
                else f"sub {int(x)//3600}:{(int(x)%3600)//60:02d}"
            )
            df["dystans"] = df["distance_km"].apply(lambda x: f"{x:.1f} km")
            st.dataframe(
                df[["date", "name", "dystans", "target"]].rename(columns={
                    "date": "Data", "name": "Wyścig", "target": "Cel"
                }),
                hide_index=True, use_container_width=True,
            )
        else:
            st.info("Brak nadchodzących wyścigów.")

    with col2:
        st.subheader("🏅 PB")
        if history:
            pbs = [r for r in history if r["is_pb"]]
            for pb in pbs:
                t = pb["actual_time_sec"]
                time_str = f"{t//3600}:{(t%3600)//60:02d}:{t%60:02d}" if t >= 3600 else f"{(t%3600)//60}:{t%60:02d}"
                dist_str = "HM" if abs(pb["distance_km"] - 21.0975) < 0.5 else (
                    "Maraton" if abs(pb["distance_km"] - 42.195) < 0.5 else f"{pb['distance_km']:.1f}km"
                )
                st.metric(dist_str, time_str, help=f"{pb['name']} ({pb['date']})")

    st.divider()

    # VDOT progression
    st.subheader("📈 Progresja VDOT")
    vdot_df = q_vdot_history(limit=20)
    if not vdot_df.empty:
        vdot_df["date"] = pd.to_datetime(vdot_df["date"])
        vdot_df = vdot_df.sort_values("date")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=vdot_df["date"], y=vdot_df["vdot"],
                                  mode="lines+markers", name="VDOT",
                                  line=dict(color="#22c55e", width=3),
                                  marker=dict(size=10)))
        for _, r in vdot_df.iterrows():
            if r["source"]:
                fig.add_annotation(x=r["date"], y=r["vdot"],
                                    text=r["source"][:30], showarrow=True,
                                    arrowhead=2, ay=-30, font=dict(size=10))
        fig.update_layout(height=350, xaxis_title="Data", yaxis_title="VDOT")
        st.plotly_chart(fig, use_container_width=True)

        # Race predictors — computed from Daniels & Gilbert equations (any VDOT)
        current_vdot = float(vdot_df.iloc[-1]["vdot"])
        st.divider()
        st.subheader(f"🎯 Race predictors z VDOT {current_vdot:g}")
        distances = {"5km": 5000, "10km": 10000, "HM": 21097.5, "M": 42195}
        cols = st.columns(4)
        for i, (label, dist_m) in enumerate(distances.items()):
            cols[i].metric(label, fmt_time(daniels_race_time(current_vdot, dist_m)))

    st.divider()
    st.subheader("📜 Historia")
    if history:
        hdf = pd.DataFrame(history)
        hdf["czas"] = hdf["actual_time_sec"].apply(fmt_time)
        hdf["dystans"] = hdf["distance_km"].apply(lambda x: f"{x:.1f} km")
        hdf["pb"] = hdf["is_pb"].apply(lambda x: "🏅 PB" if x else "")
        st.dataframe(
            hdf[["date", "name", "dystans", "czas", "pb", "notes"]].rename(columns={
                "date": "Data", "name": "Wyścig", "notes": "Notatki"
            }),
            hide_index=True, use_container_width=True,
        )


# ============================================
# Sidebar / nav
# ============================================

PAGES = {
    "🏃 Przegląd": page_overview,
    "🏃 Bieganie": page_running,
    "💪 Siłownia": page_strength,
    "🏆 Wyścigi": page_races,
}

with st.sidebar:
    st.title("🏃 Running")
    page = st.radio("Nawigacja", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    if _CLOUD_MODE:
        st.caption(f"☁️ Turso replica: `{Path(_REPLICA).name}`")
    else:
        st.caption("💾 DB: `db/data.db` (local)")
    if st.button("🔄 Odśwież dane (clear cache)"):
        st.cache_data.clear()
        if _CLOUD_MODE:
            st.cache_resource.clear()
            api.bootstrap_cloud(force=True)
        st.rerun()

PAGES[page]()
