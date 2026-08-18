"""Zakladka Cwiczenia — katalog exercises + edycja YouTube link + name_en."""
from __future__ import annotations
import pandas as pd
import streamlit as st

from dashboard.queries import q_all_exercises
from dashboard.callbacks import _apply_exercise_edit


def page_exercises():
    st.title("🏋️ Baza ćwiczeń")
    st.caption("Katalog ćwiczeń używanych w rutynach. Edytuj angielską nazwę i link YouTube — obejrzysz technikę z telefona.")

    all_ex = q_all_exercises()
    if not all_ex:
        st.info("Brak ćwiczeń w bazie. Uruchom seed lub dodaj przez SQL / Claude MCP.")
        return

    # Prosta tabela podglądu na górze
    df = pd.DataFrame(all_ex)
    df_view = df[["name", "name_en", "category", "tool"]].copy()
    df_view["YT"] = df["youtube_url"].apply(lambda u: "✅" if u else "—")
    df_view["name_en"] = df_view["name_en"].fillna("—")
    df_view.columns = ["Nazwa PL", "Nazwa EN", "Kategoria", "Narzędzie", "YT"]
    st.dataframe(df_view, hide_index=True, use_container_width=True, height=min(280, 50 + 35 * len(df_view)))

    st.divider()
    st.markdown("### 📖 Szczegóły + edycja (EN + YouTube)")

    for ex in all_ex:
        yt_icon = "✅" if ex.get("youtube_url") else "⚪"
        en_part = f" · _{ex['name_en']}_" if ex.get("name_en") else ""
        hdr = f"{yt_icon} **{ex['name']}**{en_part} — {ex.get('category') or '?'} · {ex.get('tool') or '?'}"
        with st.expander(hdr, expanded=False):
            st.markdown(ex["description_md"])
            if ex.get("youtube_url"):
                st.link_button("▶️ Zobacz na YouTube", ex["youtube_url"])
            st.divider()
            with st.form(f"ex_form_{ex['id']}", clear_on_submit=False):
                col1, col2 = st.columns([1, 2])
                with col1:
                    new_en = st.text_input(
                        "Nazwa EN",
                        value=ex.get("name_en") or "",
                        placeholder="np. Clamshell (right)",
                        key=f"en_{ex['id']}",
                    )
                with col2:
                    new_url = st.text_input(
                        "YouTube URL",
                        value=ex.get("youtube_url") or "",
                        placeholder="https://youtube.com/watch?v=... (pusto = usuń)",
                        key=f"yt_url_{ex['id']}",
                    )
                if st.form_submit_button("💾 Zapisz"):
                    _apply_exercise_edit(ex["id"], new_url, new_en)
                    st.success("Zapisane. Odśwież żeby zobaczyć.")
                    st.rerun()
