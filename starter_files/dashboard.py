"""Streamlit dashboard for the running project — thin entry point.

Struktura modularna:
  dashboard/
    auth.py       — password gate + Turso ping
    utils.py      — session_state accessors
    constants.py  — LIFE_*, NOTE_*, ARTIFACT_CATEGORIES, VDOT_CAL_OFFSET
    helpers.py    — fmt_pace, fmt_time, daniels_race_time, monday_iso
    queries.py    — @st.cache_data q_*
    callbacks.py  — _apply_*, _cb_*
    pages/        — po jednej zakladce w pliku

Run locally:
    streamlit run dashboard.py

Deploy on Streamlit Cloud:
  - Main file: dashboard.py
  - Secrets (TOML): TURSO_DATABASE_URL + TURSO_AUTH_TOKEN
  - Dashboard laczy sie BEZPOSREDNIO z Turso (libsql), cache 60s per query.
    Zero replika, zero bootstrap-pull-init (2026-08-19 refactor po incident'ie
    utraty danych przez sync-based mirror).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))       # zeby `import dashboard.xxx` dzialalo
sys.path.insert(0, str(ROOT / "db"))

# Bridge Streamlit Cloud secrets -> environment vars so db.api pick them up.
# On localhost st.secrets is empty and this is a no-op.
try:
    for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
        if _key in st.secrets and not os.getenv(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass  # no secrets.toml — local sqlite mode

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

from dashboard.auth import check_password, bootstrap_once
from dashboard.utils import get_user_name
import api  # type: ignore

if not check_password(DASHBOARD_TITLE):
    st.stop()

_BOOT = bootstrap_once()
if not _BOOT["ok"]:
    st.error(f"❌ Nie mogę połączyć się z Turso.\n\n**Błąd:** `{_BOOT['error']}`")
    st.caption(
        "Możliwe przyczyny: chwilowa niedostępność Turso, wygasły token, sieć. "
        "Klik retry ponowi połączenie."
    )
    c1, c2 = st.columns([1, 4])
    if c1.button("🔄 Spróbuj ponownie", type="primary"):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()
    c2.caption("_Jeśli błąd wraca — sprawdź `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` w Streamlit secrets._")
    st.stop()

_CLOUD_MODE = bool(os.getenv("TURSO_DATABASE_URL") and os.getenv("TURSO_AUTH_TOKEN"))

from dashboard.pages.overview import page_overview
from dashboard.pages.routine import page_routine
from dashboard.pages.exercises import page_exercises
from dashboard.pages.artifacts import page_artifacts
from dashboard.pages.running import page_running
from dashboard.pages.strength import page_strength
from dashboard.pages.races import page_races
from dashboard.pages.life import page_life
from dashboard.pages.learning import page_learning


# ============================================
# Sidebar / nav
# ============================================

PAGES = {
    "🏃 Przegląd":            page_overview,
    "🌅 Codzienna rutyna":    page_routine,
    "🏋️ Ćwiczenia":           page_exercises,
    "📎 Artefakty":            page_artifacts,
    "🏃 Bieganie":             page_running,
    "💪 Siłownia":             page_strength,
    "🏆 Wyścigi":              page_races,
    "🧠 Rozkminy":             page_life,
    "🎓 Nauka":                page_learning,
}

with st.sidebar:
    st.title(f"🏃 {get_user_name()}")
    page = st.radio("Nawigacja", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    if _CLOUD_MODE:
        st.caption("☁️ Turso live (direct, cache 60s)")
    else:
        st.caption("💾 DB: `db/data.db` (local)")
    if st.button("🔄 Odśwież dane (clear cache)"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
    if st.button("🚪 Wyloguj"):
        for k in ("auth_ok", "user_id", "user_name"):
            st.session_state.pop(k, None)
        st.cache_data.clear()
        st.rerun()

PAGES[page]()
