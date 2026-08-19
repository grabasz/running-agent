"""Password gate + Turso bootstrap.

Wywolywane raz per session z entry point dashboard.py PRZED renderem
sidebar / pages. Blokuje `st.stop()` gdy brak autoryzacji lub brak DB.
"""
from __future__ import annotations
import os
import streamlit as st

import api  # type: ignore


@st.cache_resource(show_spinner="Ping Turso…")
def bootstrap_once():
    """Sanity-check Turso connectivity once per Streamlit session.

    Legacy nazwa — od 2026-08-19 dashboard laczy sie bezposrednio z Turso
    (bez replica/pull), wiec ta funkcja robi tylko `SELECT 1` zeby wykryc
    zerwane creds / brak sieci PRZED renderem stron.

    Returns {ok, replica: None, error}.
    """
    try:
        with api.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"ok": True, "replica": None, "error": None}
    except Exception as e:
        return {"ok": False, "replica": None, "error": f"{type(e).__name__}: {e}"}


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


def check_password(dashboard_title: str) -> bool:
    """True = user zautoryzowany albo local dev bez hasla. False = form login jeszcze niewypelniony."""
    # Local dev: brak hasla w env/secrets => otwarty dostep jako user domyslny (user_id=1).
    if not any(_get_secret(k) for k in ("USER1_PASSWORD", "USER2_PASSWORD", "USER3_PASSWORD", "APP_PASSWORD")):
        st.session_state.setdefault("user_id", 1)
        st.session_state.setdefault("user_name", os.getenv("DEFAULT_USER_NAME", "User"))
        return True

    if st.session_state.get("auth_ok"):
        return True

    st.title(f"🔒 {dashboard_title}")
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
