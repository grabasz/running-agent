"""Zakladka Artefakty sesji — kluczowe dokumenty z rozmow z AI.

Dostep z telefona bez wracania do transkryptu (testy, plany, przepisy, hipotezy).
"""
from __future__ import annotations
from datetime import datetime
import streamlit as st

import api  # type: ignore

from dashboard.constants import ARTIFACT_CATEGORIES
from dashboard.queries import q_artifacts
from dashboard.callbacks import _push_artifacts_to_turso, enc
from dashboard.utils import get_user_id


def page_artifacts():
    st.title("📎 Artefakty sesji")
    st.caption(
        "Kluczowe dokumenty z rozmów z AI (testy, plany, przepisy, hipotezy). "
        "Dostęp z telefona — bez wracania do transkryptu."
    )

    user_id = get_user_id()

    # Filtry
    col_search, col_cat, col_arch = st.columns([2, 1, 1])
    with col_search:
        search = st.text_input("🔍 Szukaj w tytule", key="art_search", placeholder="np. kolano, plan…")
    with col_cat:
        cat_filter = st.selectbox(
            "Kategoria",
            options=["(wszystkie)"] + list(ARTIFACT_CATEGORIES.keys()),
            format_func=lambda k: k if k == "(wszystkie)" else f"{ARTIFACT_CATEGORIES[k][0]} {ARTIFACT_CATEGORIES[k][1]}",
            key="art_cat",
        )
    with col_arch:
        show_arch = st.checkbox("Zarchiwizowane", key="art_arch")

    artifacts = q_artifacts(user_id=user_id, include_archived=show_arch)
    if search:
        s = search.lower()
        artifacts = [a for a in artifacts if s in (a["title"] or "").lower()]
    if cat_filter != "(wszystkie)":
        artifacts = [a for a in artifacts if a["category"] == cat_filter]

    if not artifacts:
        st.info('Brak artefaktów — poproś AI: "zapisz to jako artifact".')
        st.stop()

    st.caption(f"**{len(artifacts)}** artefaktów")
    st.divider()

    for a in artifacts:
        icon, cat_pl = ARTIFACT_CATEGORIES.get(a["category"], ("📎", a["category"]))
        arch_prefix = "🗄️ " if a["archived"] else ""
        header = f"{arch_prefix}{icon} **{a['title']}** · `{a['date']}` · _{cat_pl}_"
        with st.expander(header, expanded=False):
            if a["summary"]:
                st.markdown(f"> {a['summary']}")
            st.markdown(a["content_md"])
            st.divider()
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                label = "📂 Przywróć" if a["archived"] else "🗄️ Archiwizuj"
                if st.button(label, key=f"art_arch_{a['id']}"):
                    with api.connect() as conn:
                        conn.execute(
                            "UPDATE session_artifacts SET archived = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
                            (0 if a["archived"] else 1, a["id"], user_id),
                        )
                        conn.commit()
                    st.cache_data.clear()
                    _push_artifacts_to_turso()
                    st.rerun()
            with col2:
                st.caption(f"źródło: `{a['source']}`")
            with col3:
                st.caption(f"utworzono: {a['created_at']}")

    st.divider()

    with st.expander("➕ Dodaj artifact ręcznie", expanded=False):
        with st.form("art_add", clear_on_submit=True):
            title = st.text_input("Tytuł*")
            summary = st.text_input("Summary (1-2 zdania, opcjonalne)")
            cat = st.selectbox(
                "Kategoria",
                options=list(ARTIFACT_CATEGORIES.keys()),
                format_func=lambda k: f"{ARTIFACT_CATEGORIES[k][0]} {ARTIFACT_CATEGORIES[k][1]}",
            )
            content = st.text_area("Content (markdown)*", height=200)
            if st.form_submit_button("💾 Zapisz"):
                if not title.strip() or not content.strip():
                    st.error("Tytuł i content wymagane")
                else:
                    with api.connect() as conn:
                        conn.execute(
                            "INSERT INTO session_artifacts (user_id, date, category, title, summary, content_md, source) "
                            "VALUES (?, ?, ?, ?, ?, ?, 'manual')",
                            (user_id, datetime.now().date().isoformat(), cat,
                             enc(title.strip(), user_id),
                             enc(summary.strip() or None, user_id),
                             enc(content.strip(), user_id)),
                        )
                        conn.commit()
                    st.cache_data.clear()
                    _push_artifacts_to_turso()
                    st.success("Zapisano")
                    st.rerun()
