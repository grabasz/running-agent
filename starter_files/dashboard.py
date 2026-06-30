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
# Config
# ============================================

st.set_page_config(
    page_title="Bartek Running",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


# ============================================
# Page: Przegląd
# ============================================

def page_overview():
    st.title("🏃 Przegląd")

    # --- Top metrics row ---
    vdot_hist = q_vdot_history(limit=1)
    races_hist = q_races_history()
    vol_df = q_weekly_volume(weeks=4)

    col1, col2, col3, col4 = st.columns(4)
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

    st.divider()

    # --- Dziś + jutro ---
    left, right = st.columns([3, 2])

    with left:
        st.subheader("📅 Bieżący tydzień")
        week = q_current_week()
        if not week:
            st.info("Brak planu na ten tydzień. Edytuj `db/seed_current_week.py` i uruchom.")
        else:
            df = pd.DataFrame(week)
            df["display"] = (
                df["status_icon"].fillna("") + " " +
                df["type_icon"].fillna("") + " " +
                df["title"].fillna("")
            )
            df["pogoda"] = df.apply(
                lambda r: f"{int(r['weather_temp_c'])}°C{' · ' + r['weather_note'] if r['weather_note'] else ''}"
                          if pd.notna(r['weather_temp_c']) else "",
                axis=1
            )
            st.dataframe(
                df[["date", "display", "pogoda"]].rename(columns={
                    "date": "Data", "display": "Plan", "pogoda": "Pogoda"
                }),
                hide_index=True, use_container_width=True,
            )

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
                hide_index=True, use_container_width=True, height=300,
            )

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
    runs_df = runs_df.sort_values("date")

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
        st.subheader("🦵 Running dynamics — GCT Balance L/R")
        st.caption("50% = idealna symetria. Odchył pokazuje która noga dłużej w podporze (asymetria kompensacyjna).")
        dyn["date"] = pd.to_datetime(dyn["date"])
        dyn = dyn.sort_values("date")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dyn["date"], y=dyn["gct_balance_left_pct"],
                                  mode="lines+markers", name="GCT bal L%",
                                  line=dict(color="#3b82f6", width=2)))
        fig.add_hline(y=50, line_dash="dash", line_color="gray",
                      annotation_text="symetria 50%", annotation_position="top right")
        fig.update_layout(height=300, xaxis_title="Data", yaxis_title="L% (50 = symetria)")
        st.plotly_chart(fig, use_container_width=True)

    # Tabela
    st.divider()
    st.subheader("Ostatnie biegi")
    display_df = df[["date", "name", "distance_km", "pace_sec_per_km", "hr_avg", "type", "source"]].copy()
    display_df["tempo"] = display_df["pace_sec_per_km"].apply(fmt_pace)
    display_df["dystans"] = display_df["distance_km"].apply(lambda x: f"{x:.2f} km" if pd.notna(x) else "—")
    st.dataframe(
        display_df[["date", "name", "dystans", "tempo", "hr_avg", "type", "source"]].rename(columns={
            "date": "Data", "name": "Nazwa", "hr_avg": "HR śr", "type": "Typ", "source": "Źródło"
        }),
        hide_index=True, use_container_width=True, height=400,
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

        # Race predictors
        current_vdot = int(vdot_df.iloc[-1]["vdot"])
        st.divider()
        st.subheader(f"🎯 Race predictors z VDOT {current_vdot}")
        # Simplified Jack Daniels VDOT predictions (approximate)
        predictions = {
            54: {"5km": "20:39", "10km": "42:51", "HM": "1:34:53", "M": "3:17:29"},
            55: {"5km": "20:18", "10km": "42:21", "HM": "1:33:43", "M": "3:15:28"},
            56: {"5km": "19:57", "10km": "41:52", "HM": "1:32:35", "M": "3:13:32"},
            57: {"5km": "19:36", "10km": "41:24", "HM": "1:31:29", "M": "3:11:39"},
        }
        pred = predictions.get(current_vdot, predictions[55])
        cols = st.columns(4)
        for i, (dist, time) in enumerate(pred.items()):
            cols[i].metric(dist, time)

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
