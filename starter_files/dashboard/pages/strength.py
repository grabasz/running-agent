"""Zakladka Silownia — sesje, progresja cwiczen, top tonaz."""
from __future__ import annotations
import pandas as pd
import plotly.express as px
import streamlit as st

import api  # type: ignore

from dashboard.queries import q_gym_sessions, q_exercise_progression, q_top_exercises
from dashboard.utils import get_user_id


def page_strength():
    st.title("💪 Siłownia")

    user_id = get_user_id()
    sessions = q_gym_sessions(limit=10, user_id=user_id)
    if not sessions:
        st.warning("Brak sesji siłowni w DB. Wywołaj `/silownia` żeby zaimportować z Garmina.")
        return

    # Selector cwiczenia — inline SQL bo lista unikalnych cwiczen z gym_sets,
    # nie warta osobnego query helpera (jednorazowy uzytek w tej zakladce).
    with api.connect() as conn:
        ex_list = [r["exercise"] for r in conn.execute(
            "SELECT DISTINCT exercise FROM gym_sets ORDER BY exercise"
        ).fetchall()]

    selected_ex = st.selectbox("Wybierz ćwiczenie", ex_list,
                                index=ex_list.index("RDL") if "RDL" in ex_list else 0)

    progression = q_exercise_progression(selected_ex, limit=30, user_id=user_id)
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
            st.subheader("Wolumen sesji (reps × kg)")
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
    top = q_top_exercises(since="2026-01-01", user_id=user_id)
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
