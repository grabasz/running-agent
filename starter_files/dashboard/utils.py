"""Session-state accessors dla user_id i user_name.

Zgodnie z CODING_STANDARDS: user_id ZAWSZE parametr do queries. Nigdy globalna
mutable state — zawsze czytaj fresh z st.session_state (Streamlit i tak
reruns per interaction, wiec cache dla nas zbedny).
"""
from __future__ import annotations
import os
import streamlit as st


def get_user_id() -> int:
    """Aktualny zalogowany user_id (default 1 dla local dev bez auth)."""
    return int(st.session_state.get("user_id", 1))


def get_user_name() -> str:
    """Display name aktualnego usera (fallback: 'User')."""
    return str(st.session_state.get("user_name", "User"))


def get_dashboard_title() -> str:
    """Tytul dashboardu (env override dla self-hosted instances)."""
    return os.getenv("DASHBOARD_TITLE", "Running Dashboard")
