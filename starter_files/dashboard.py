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

# Overridable via env for self-hosted instances (e.g. DASHBOARD_TITLE="Mati Running")
DASHBOARD_TITLE = os.getenv("DASHBOARD_TITLE", "Running Dashboard")

# Must be the FIRST Streamlit command — before the password gate renders anything.
# Tytul strony generyczny — password gate jeszcze nie wie kto sie loguje.
st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner="Pobieram dane z Turso…")
def _bootstrap_once():
    """Run once per Streamlit session. In cloud mode pulls fresh snapshot
    from Turso; in local mode returns None (data.db is already the source).

    Returns dict: {ok: bool, replica: Path|None, error: str|None}.
    Wrapped so a Turso outage doesn't crash the whole app before UI renders.
    """
    try:
        return {"ok": True, "replica": api.bootstrap_cloud(), "error": None}
    except Exception as e:
        return {"ok": False, "replica": None, "error": f"{type(e).__name__}: {e}"}


# ============================================
# Password gate (only enforced when APP_PASSWORD secret is set)
# ============================================

def _get_secret(key: str) -> str | None:
    """Streamlit secrets albo env var — dashboard hostowany w obu trybach."""
    try:
        v = st.secrets.get(key)
        if v:
            return str(v)
    except Exception:
        pass
    return os.getenv(key)


def _resolve_user(username: str, pw: str) -> tuple[int, str] | None:
    """Zweryfikuj (username, password) i zwróć (user_id, display_name) lub None.

    Konfiguracja przez env/secrets:
      USER<N>_NAME + USER<N>_PASSWORD (N=1..3)
      APP_PASSWORD (legacy) — dowolny username, mapuje na user_id=1
    """
    uname = username.strip().lower()
    if not uname or not pw:
        return None
    for uid in (1, 2, 3):
        stored_name = _get_secret(f"USER{uid}_NAME")
        stored_pw = _get_secret(f"USER{uid}_PASSWORD")
        if not (stored_name and stored_pw):
            continue
        if uname == stored_name.strip().lower() and pw == stored_pw:
            return (uid, stored_name)
    pw_app = _get_secret("APP_PASSWORD")
    if pw_app and pw == pw_app:
        name = _get_secret("USER1_NAME") or _get_secret("DEFAULT_USER_NAME") or "User"
        return (1, name)
    return None


def _check_password() -> bool:
    # Local dev: brak hasla w env/secrets => otwarty dostep jako user domyslny (user_id=1).
    if not any(_get_secret(k) for k in ("USER1_PASSWORD", "USER2_PASSWORD", "USER3_PASSWORD", "APP_PASSWORD")):
        st.session_state.setdefault("user_id", 1)
        st.session_state.setdefault("user_name", os.getenv("DEFAULT_USER_NAME", "User"))
        return True

    if st.session_state.get("auth_ok"):
        return True

    st.title(f"🔒 {DASHBOARD_TITLE}")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Użytkownik", key="username_input", autocomplete="username")
        pw = st.text_input("Hasło", type="password", key="pw_input", autocomplete="current-password")
        submitted = st.form_submit_button("Zaloguj")
    if submitted:
        resolved = _resolve_user(username, pw)
        if resolved:
            uid, uname = resolved
            st.session_state["auth_ok"] = True
            st.session_state["user_id"] = uid
            st.session_state["user_name"] = uname
            # Wyczysc cache poprzedniego usera (jesli ktos sie przelogowal)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("Zły użytkownik lub hasło.")
    return False


if not _check_password():
    st.stop()

_BOOT = _bootstrap_once()
if not _BOOT["ok"]:
    st.error(f"❌ Nie mogę pobrać danych z Turso.\n\n**Błąd:** `{_BOOT['error']}`")
    st.caption(
        "Możliwe przyczyny: chwilowa niedostępność Turso, wygasły token, sieć. "
        "Klik retry pobierze ponownie."
    )
    c1, c2 = st.columns([1, 4])
    if c1.button("🔄 Spróbuj ponownie", type="primary"):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()
    c2.caption("_Jeśli błąd wraca — sprawdź `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` w Streamlit secrets._")
    st.stop()

_REPLICA = _BOOT["replica"]
_CLOUD_MODE = _REPLICA is not None


# ============================================
# DB helpers (cached for speed)
# ============================================

# USER_ID + USER_NAME wybrane w loginie (session_state).
# _uid()/USER_ID: pierwszy raz USER_ID init sie po password gate (linia _check_password).
# Wszystkie q_ funkcje dostaja user_id jako parametr (cache-per-user).
def _uid() -> int:
    return int(st.session_state.get("user_id", 1))

USER_ID: int = _uid()
USER_NAME: str = str(st.session_state.get("user_name", "User"))


@st.cache_data(ttl=30)
def q_today(user_id: int):
    with api.connect() as conn:
        return [dict(r) for r in api.planned.today(conn, user_id=user_id)]


@st.cache_data(ttl=30)
def q_upcoming(user_id: int, days=7):
    with api.connect() as conn:
        return [dict(r) for r in api.planned.upcoming(conn, user_id=user_id, days=f"+{days} days", limit=7)]


@st.cache_data(ttl=15)
def q_current_week_with_components(user_id: int):
    """Zwraca plany bieżącego tygodnia z komponentami zgroupowanymi per planned_id."""
    with api.connect() as conn:
        week = [dict(r) for r in api.planned.current_week(conn, user_id=user_id)]
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
    q_current_week_with_components.clear()
    q_today.clear()
    # Turso push - best effort, nie przerywaj UI gdy padnie
    try:
        from sync import push as _push  # type: ignore
        _push(verbose=False)
    except Exception as e:
        st.warning(f"Push do Turso nieudany: {e}")


@st.cache_data(ttl=60)
def q_weekly_volume(user_id: int, weeks=12):
    with api.connect() as conn:
        rows = [dict(r) for r in api.weekly_volume.recent(conn, user_id=user_id, weeks=weeks)]
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def q_runs_recent(user_id: int, limit=30):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.runs.recent(conn, user_id=user_id, limit=limit)])


@st.cache_data(ttl=60)
def q_runs_with_dynamics(user_id: int, since="-90 days"):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.runs.recent_with_dynamics(conn, user_id=user_id, since=since)])


@st.cache_data(ttl=60)
def q_gym_sessions(user_id: int, limit=20):
    with api.connect() as conn:
        return [dict(r) for r in api.gym.sessions_recent(conn, user_id=user_id, limit=limit)]


@st.cache_data(ttl=60)
def q_exercise_progression(user_id: int, exercise, limit=30):
    with api.connect() as conn:
        return pd.DataFrame([
            dict(r) for r in api.gym.exercise_progression(conn, user_id=user_id, exercise=exercise, limit=limit)
        ])


@st.cache_data(ttl=60)
def q_top_exercises(user_id: int, since="2026-01-01"):
    with api.connect() as conn:
        return pd.DataFrame([
            dict(r) for r in api.gym.top_exercises_by_volume(conn, user_id=user_id, since=since)
        ])


@st.cache_data(ttl=60)
def q_races_upcoming(user_id: int):
    with api.connect() as conn:
        return [dict(r) for r in api.races.upcoming(conn, user_id=user_id)]


@st.cache_data(ttl=60)
def q_races_history(user_id: int):
    with api.connect() as conn:
        return [dict(r) for r in api.races.history(conn, user_id=user_id)]


@st.cache_data(ttl=60)
def q_vdot_history(user_id: int, limit=10):
    with api.connect() as conn:
        return pd.DataFrame([dict(r) for r in api.vdot.history(conn, user_id=user_id, limit=limit)])


@st.cache_data(ttl=30)
def q_body_state(user_id: int, since="-14 days"):
    with api.connect() as conn:
        return [dict(r) for r in api.body.state_recent(conn, user_id=user_id, since=since)]


@st.cache_data(ttl=30)
def q_tasks_all(user_id: int):
    with api.connect() as conn:
        return [dict(r) for r in api.tasks.list_all(conn, user_id=user_id)]


@st.cache_data(ttl=30)
def q_goals_week(user_id: int, week_start):
    with api.connect() as conn:
        return {r["category"]: dict(r) for r in api.goals.for_week(conn, user_id=user_id, week_start=week_start)}


@st.cache_data(ttl=30)
def q_notes_recent(user_id: int, limit=30):
    with api.connect() as conn:
        return [dict(r) for r in api.notes.recent(conn, user_id=user_id, limit=limit)]


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
    # Single volume query (12 weeks) — slice for both metrics-row (top 4) and chart below.
    vol_df_12 = q_weekly_volume(weeks=12, user_id=USER_ID).sort_values("week_start", ascending=False)
    vdot_hist = q_vdot_history(limit=1, user_id=USER_ID)
    races_hist = q_races_history(user_id=USER_ID)
    races_up = q_races_upcoming(user_id=USER_ID)

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

    # --- Dziś + jutro ---
    left, right = st.columns([3, 2])

    with left:
        st.subheader("📅 Bieżący tydzień")
        week, comps_by_pid = q_current_week_with_components(user_id=USER_ID)
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
        # Single 30-day query — reuse for table (last 14 dni) + trend chart (30 dni).
        body_30 = pd.DataFrame(q_body_state(since="-30 days", user_id=USER_ID))
        if body_30.empty:
            st.info("Brak wpisów body_state.")
        else:
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

    st.divider()

    # --- Wolumen tygodniowy chart ---
    st.subheader("📊 Wolumen tygodniowy (12 tyg)")
    # Reuse vol_df_12 fetched above; chart wants ascending sort.
    if not vol_df_12.empty:
        vol_chart = vol_df_12.sort_values("week_start")
        fig = px.bar(vol_chart, x="week_start", y="distance_km",
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

    runs_df = q_runs_recent(limit=50, user_id=USER_ID)
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
    dyn = q_runs_with_dynamics(since="-90 days", user_id=USER_ID)
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

    sessions = q_gym_sessions(limit=10, user_id=USER_ID)
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

    progression = q_exercise_progression(selected_ex, limit=30, user_id=USER_ID)
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
    top = q_top_exercises(since="2026-01-01", user_id=USER_ID)
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
    upcoming = q_races_upcoming(user_id=USER_ID)
    history = q_races_history(user_id=USER_ID)

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
    vdot_df = q_vdot_history(limit=20, user_id=USER_ID)
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
# Page: Rozkminy (życie + zadania + notatki)
# ============================================

LIFE_CATEGORIES = ["sport", "praca", "dom", "relacje", "zdrowie", "inne"]
LIFE_ICONS = {"sport": "🏃", "praca": "💼", "dom": "🏠",
              "relacje": "❤️", "zdrowie": "🩺", "inne": "🧩"}
NOTE_CATEGORIES = ["insight", "decision", "reminder", "idea"]
NOTE_ICONS = {"insight": "💡", "decision": "✅", "reminder": "🔔", "idea": "🌱"}


def _monday_iso(d=None) -> str:
    d = d or datetime.now().date()
    return (d - timedelta(days=d.weekday())).isoformat()


def _invalidate_life_cache():
    q_tasks_all.clear()
    q_goals_week.clear()
    q_notes_recent.clear()


def _push_life_to_turso():
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


def _render_task_row(t: dict, children_by_parent: dict, indent: int = 0):
    prio_icon = {"high": "🔥", "med": "▲", "low": "▽"}.get(t.get("priority") or "", "")
    due = f" · 📅 {t['due_date']}" if t.get("due_date") else ""
    done = t["status"] == "done"
    prefix = "&nbsp;&nbsp;&nbsp;&nbsp;" * indent + ("↳ " if indent else "")

    cols = st.columns([1, 9, 1])
    with cols[0]:
        st.checkbox(
            "done", value=done,
            key=f"task_chk_{t['id']}",
            label_visibility="collapsed",
            on_change=_cb_task_toggle,
            args=(t["id"], t["status"]),
        )
    with cols[1]:
        title_html = f"{prefix}<span style='opacity:{0.55 if done else 1}'>"
        if done:
            title_html += f"<s>{t['title']}</s>"
        else:
            title_html += f"<b>{t['title']}</b>"
        title_html += f" {prio_icon}{due}</span>"
        st.markdown(title_html, unsafe_allow_html=True)
        if t.get("description") or t.get("success_criteria"):
            with st.expander("szczegóły", expanded=False):
                if t.get("description"):
                    st.write(f"**Opis:** {t['description']}")
                if t.get("success_criteria"):
                    st.write(f"**Kryterium (SMART):** {t['success_criteria']}")
    with cols[2]:
        if st.button("🗑", key=f"task_del_{t['id']}",
                     help="Usuń task (kaskada — usuwa też podzadania)"):
            _cb_task_delete(t["id"])
            st.rerun()

    for child in children_by_parent.get(t["id"], []):
        _render_task_row(child, children_by_parent, indent + 1)


def page_life():
    st.title("🧠 Rozkminy")
    st.caption("Życie i trening w jednym miejscu — cele tygodnia, zadania, notatki.")

    week_start = _monday_iso()

    # ------- Cele tygodnia -------
    st.header(f"🎯 Cele tygodnia — od pon. {week_start}")
    goals_map = q_goals_week(week_start, user_id=USER_ID)

    filled_cats = [c for c in LIFE_CATEGORIES if goals_map.get(c)]
    empty_cats = [c for c in LIFE_CATEGORIES if not goals_map.get(c)]

    if filled_cats:
        goal_cols = st.columns(min(3, len(filled_cats)))
        for i, cat in enumerate(filled_cats):
            with goal_cols[i % 3]:
                existing = goals_map[cat]
                status = existing["status"]
                icon = LIFE_ICONS[cat]
                input_key = f"goal_input_{week_start}_{cat}"

                st.markdown(f"**{icon} {cat.capitalize()}**")
                c_chk, c_input = st.columns([1, 8], vertical_alignment="center")
                with c_chk:
                    st.checkbox(
                        "zrobione", value=(status == "done"),
                        key=f"goal_chk_{week_start}_{cat}",
                        label_visibility="collapsed",
                        help="Zaznacz gdy zrobione",
                        on_change=_cb_goal_toggle,
                        args=(existing["id"], status),
                    )
                with c_input:
                    st.text_input(
                        "cel", value=existing["goal"],
                        key=input_key,
                        placeholder="Cel na ten tydzień…",
                        label_visibility="collapsed",
                        on_change=_cb_goal_upsert,
                        args=(week_start, cat, input_key),
                    )
    else:
        st.caption("_Brak celów na ten tydzień — dodaj pierwszy poniżej._")

    if empty_cats:
        with st.expander(f"➕ Dodaj cel dla kategorii ({len(empty_cats)} dostępnych)", expanded=not filled_cats):
            with st.form(f"add_goal_form_{week_start}", clear_on_submit=True):
                add_cat = st.selectbox(
                    "Kategoria", empty_cats,
                    format_func=lambda c: f"{LIFE_ICONS[c]} {c.capitalize()}",
                    key=f"new_goal_cat_{week_start}",
                )
                add_text = st.text_input(
                    "Cel", key=f"new_goal_text_{week_start}",
                    placeholder="Cel na ten tydzień…",
                )
                if st.form_submit_button("Zapisz cel"):
                    if not add_text.strip():
                        st.error("Wpisz treść celu.")
                    else:
                        with api.connect() as conn:
                            api.goals.upsert(conn, week_start=week_start, category=add_cat,
                                             goal=add_text.strip(), status=None)
                        _invalidate_life_cache()
                        _push_life_to_turso()
                        st.rerun()

    st.divider()

    # ------- Zadania -------
    st.header("📋 Zadania")
    all_tasks = q_tasks_all(user_id=USER_ID)

    show_done = st.toggle("Pokaż wykonane", value=False, key="tasks_show_done")

    by_cat: dict[str, list[dict]] = {c: [] for c in LIFE_CATEGORIES}
    for t in all_tasks:
        if t["category"] in by_cat:
            by_cat[t["category"]].append(t)

    task_tabs = st.tabs([f"{LIFE_ICONS[c]} {c.capitalize()}" for c in LIFE_CATEGORIES])

    for cat, tab in zip(LIFE_CATEGORIES, task_tabs):
        with tab:
            cat_tasks = by_cat[cat]
            visible = cat_tasks if show_done else [t for t in cat_tasks if t["status"] == "open"]
            roots = [t for t in visible if not t["parent_id"]]
            children_by_parent: dict[int, list[dict]] = {}
            for t in visible:
                if t["parent_id"]:
                    children_by_parent.setdefault(t["parent_id"], []).append(t)

            if roots:
                for t in roots:
                    _render_task_row(t, children_by_parent)
            else:
                st.info("Brak zadań w tej kategorii.")

            with st.expander(f"➕ Dodaj task ({cat})", expanded=False):
                with st.form(f"add_task_form_{cat}", clear_on_submit=True):
                    title = st.text_input("Tytuł*", key=f"nt_title_{cat}",
                                          placeholder="Krótko i konkretnie (SMART: Specific)")
                    parent_opts = {0: "— brak (root task / projekt)"}
                    for t in cat_tasks:
                        if not t["parent_id"] and t["status"] == "open":
                            parent_opts[t["id"]] = f"↳ {t['title'][:50]}"
                    parent_id = st.selectbox(
                        "Podzadanie czego?", options=list(parent_opts.keys()),
                        format_func=lambda x: parent_opts[x], key=f"nt_parent_{cat}"
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        due = st.date_input("Termin (opcjonalny)",
                                            value=None, key=f"nt_due_{cat}")
                    with c2:
                        prio = st.selectbox("Priorytet",
                                            ["", "low", "med", "high"],
                                            key=f"nt_prio_{cat}")
                    desc = st.text_area("Opis (opcjonalny)", key=f"nt_desc_{cat}")
                    crit = st.text_input(
                        "Kryterium sukcesu (SMART: Measurable)",
                        key=f"nt_crit_{cat}",
                        placeholder="Skąd wiesz że jest zrobione? np. „Umowa podpisana”"
                    )
                    if st.form_submit_button("Zapisz"):
                        if not title.strip():
                            st.error("Tytuł jest wymagany")
                        else:
                            with api.connect() as conn:
                                api.tasks.add(
                                    conn,
                                    parent_id=parent_id if parent_id else None,
                                    category=cat,
                                    title=title.strip(),
                                    description=(desc.strip() or None),
                                    success_criteria=(crit.strip() or None),
                                    due_date=(due.isoformat() if due else None),
                                    priority=(prio or None),
                                    status=None,
                                )
                            _invalidate_life_cache()
                            _push_life_to_turso()
                            st.success("Task dodany")
                            st.rerun()

    st.divider()

    # ------- Notatki -------
    st.header("💡 Notatki")

    f1, f2 = st.columns([2, 1])
    with f1:
        cat_filter = st.selectbox(
            "Kategoria", ["wszystkie"] + NOTE_CATEGORIES,
            format_func=lambda c: c if c == "wszystkie" else f"{NOTE_ICONS[c]} {c}",
            key="notes_cat_filter",
        )
    with f2:
        limit = st.number_input("Pokaż ostatnie N", min_value=5, max_value=100,
                                 value=20, step=5, key="notes_limit")

    notes = q_notes_recent(limit=int(limit, user_id=USER_ID))
    if cat_filter != "wszystkie":
        notes = [n for n in notes if n["category"] == cat_filter]

    if notes:
        for n in notes:
            icon = NOTE_ICONS.get(n["category"], "•")
            row = st.columns([1, 10, 1])
            with row[0]:
                st.write(f"{icon} `{n['date']}`")
            with row[1]:
                st.write(n["content"])
                if n.get("source") and n["source"] != "chat":
                    st.caption(f"źródło: {n['source']}")
            with row[2]:
                if st.button("🗑", key=f"note_del_{n['id']}",
                             help="Usuń notatkę"):
                    _cb_note_delete(n["id"])
                    st.rerun()
    else:
        st.info("Brak notatek dla wybranego filtra. Dodaj poniżej.")

    with st.expander("➕ Dodaj notatkę", expanded=False):
        with st.form("add_note_form", clear_on_submit=True):
            cat = st.selectbox("Kategoria", NOTE_CATEGORIES,
                               format_func=lambda c: f"{NOTE_ICONS[c]} {c}",
                               key="nn_cat")
            content = st.text_area("Treść*", key="nn_content",
                                    placeholder="Insight, decyzja, przypomnienie, pomysł…")
            if st.form_submit_button("Zapisz"):
                if not content.strip():
                    st.error("Treść jest wymagana")
                else:
                    with api.connect() as conn:
                        api.notes.add(
                            conn,
                            date=datetime.now().date().isoformat(),
                            category=cat,
                            content=content.strip(),
                            related_task_id=None, related_run_id=None,
                            related_session_id=None,
                            source="manual",
                        )
                    _invalidate_life_cache()
                    _push_life_to_turso()
                    st.success("Notatka dodana")
                    st.rerun()


# ============================================
# Page: Nauka (edukacyjna sekcja dla wszystkich — szczegolnie Matiego)
# ============================================

def page_learning():
    st.title("🎓 O co chodzi w bieganiu?")
    st.caption("Twoi trenerzy — Jack Daniels + zdrowy rozsądek.")

    st.markdown("### 🏃‍♂️ 5 typów treningu — co i dlaczego")

    with st.expander("🌿 **Easy** — spokojnie, długo, o rozmowie", expanded=True):
        st.markdown("""
**Jak biegać:**  Tak wolno, żebyś mógł spokojnie **gadać pełnymi zdaniami**. Bez zadyszki. Bez patrzenia na zegarek co 100 m.

**Po co:**  Buduje **wytrzymałość podstawową** — Twoje serce staje się mocniejsze, mięśnie uczą się palić tłuszcz zamiast cukru.
Tego biegania nigdy nie jest za dużo. To fundament wszystkiego innego.

**Typowa dystansa:**  3–10 km, zależy od poziomu.
**Jak się czuć potem:**  Chcesz jeszcze pobiegać. Nie jesteś zmęczony.
        """)

    with st.expander("⚡ **Tempo** — komfortowo ciężko"):
        st.markdown("""
**Jak biegać:**  Tak szybko, że nie da się gadać pełnymi zdaniami — tylko krótkie słowa. Nie jest "cierpienie", ale też nie "spacer".
Wyobraź sobie że biegniesz **tempem, którym mógłbyś biec przez godzinę** i tylko pod koniec zaczyna boleć.

**Po co:**  Uczy ciało **wysiłku na granicy** — próg mleczanowy. Za tydzień będziesz umiał utrzymać to tempo dłużej.

**Typowa struktura:**  2 km rozgrzewka → 4-6 km tempo → 2 km wychłodzenie.
**Jak się czuć potem:**  Zadowolony i się nie zmęczyłeś 😅
        """)

    with st.expander("🛣️ **Long** — długo, wolno, bez pośpiechu"):
        st.markdown("""
**Jak biegać:**  Jak **Easy**, tylko **dłużej niż zwykle**. Tempo takie samo albo trochę wolniejsze.

**Po co:**  Twoje ciało uczy się być długo w ruchu bez zmęczenia. Kości, ścięgna, mięśnie się wzmacniają. To jest trening który robi z ciebie **biegacza na dystansie**.

**Typowa dystansa:**  10-20+ km (dla dorosłych), 5-8 km dla dzieci.
**Jak się czuć potem:**  Zmęczony ale spełniony. Wieczorem — spać jak dziecko.
        """)

    with st.expander("🔥 **Interval** — krótkie ale mocne odcinki"):
        st.markdown("""
**Jak biegać:**  **Bardzo szybko przez krótki dystans** (400-1000 m), potem przerwa (trucht lub spacer), potem znowu szybko. Kilka razy.
Przykład: 6 × 400 m po ~1:30, między nimi 200 m truchtu.

**Po co:**  Uczy ciało biegać **szybko** i **poprawia VO2max** — ile tlenu Twój organizm umie zużyć na minutę. Kluczowe dla szybkości.

**Jak się czuć potem:**  Wykończony, ale krótkotrwale. Dzień odpoczynku obowiązkowy.
        """)

    with st.expander("💧 **Recovery / Regeneracja** — po ciężkim dniu"):
        st.markdown("""
**Jak biegać:**  Jeszcze **wolniej niż Easy**. Praktycznie spacer szybszy. 20-40 minut.

**Po co:**  Ruch pobudza krew, krew zabiera "śmieci" z mięśni (kwas mlekowy, mikrouszkodzenia).
Po ciężkim treningu następnego dnia jest **lepiej** niż leżeć na kanapie.

**Jak się czuć potem:**  Lżej. Bezruchowe bóle znikają.
        """)

    st.divider()
    st.markdown("### 📊 Skala RPE — jak ciężko było?")
    st.caption("RPE = Rate of Perceived Exertion. Po każdym biegu spytaj sam siebie: **jak bardzo mnie to zmęczyło?**")

    rpe = [
        ("1-2", "🚶", "**Spacer**. W ogóle nie zauważyłem że biegałem."),
        ("3-4", "🌿", "**Easy**. Mogłem gadać pełnymi zdaniami. Chcę jeszcze."),
        ("5-6", "⚡", "**Tempo**. Krótkie słowa. Trochę pot. Umiem to utrzymać 30-60 min."),
        ("7-8", "🔥", "**Ciężko**. Ledwo słowo. Pot. Chcę żeby już się skończyło."),
        ("9", "😵", "**Bardzo ciężko**. Nie umiem gadać. Ostatnie 5 minut wyścigu."),
        ("10", "💀", "**Maksymalne**. Ostatnie 100 m sprintu. Nie da się utrzymać."),
    ]
    for score, icon, desc in rpe:
        st.markdown(f"- **{score}** {icon} — {desc}")

    st.divider()
    st.markdown("### 🎯 Dlaczego dziś ten trening?")
    st.caption(f"Twój aktualny plan na dzisiaj (jeśli jest):")

    plan_today = q_today(user_id=USER_ID)
    if plan_today:
        for p in plan_today:
            st.info(f"**{p.get('type_display_pl', p.get('type_key', '?'))}** — {p.get('title', 'brak tytułu')}")
            if p.get("notes"):
                st.caption(p["notes"])
    else:
        st.caption("Nic zaplanowanego na dziś. Odpoczynek lub decyduje ciało.")

    st.divider()
    st.markdown("### 🧠 3 zasady od trenera")
    st.markdown("""
1. **80% biegów to Easy.** Serio. Jeśli wszystkie biegi cię męczą — biegasz za szybko.
2. **Nie stawaj coraz ciężej co tydzień.** Ciało potrzebuje czasu żeby się dostosować. Lepiej mniej biegać ale konsekwentnie.
3. **Ból = zatrzymaj się.** Zmęczenie mięśni to normalne. Ostry ból (kolano, ścięgno) — koniec, nie biegasz przez 2-3 dni.
    """)


# ============================================
# Sidebar / nav
# ============================================

PAGES = {
    "🏃 Przegląd": page_overview,
    "🏃 Bieganie": page_running,
    "💪 Siłownia": page_strength,
    "🏆 Wyścigi": page_races,
    "🧠 Rozkminy": page_life,
    "🎓 Nauka": page_learning,
}

with st.sidebar:
    st.title(f"🏃 {USER_NAME}")
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
    if st.button("🚪 Wyloguj"):
        for k in ("auth_ok", "user_id", "user_name"):
            st.session_state.pop(k, None)
        st.cache_data.clear()
        st.rerun()

PAGES[page]()
