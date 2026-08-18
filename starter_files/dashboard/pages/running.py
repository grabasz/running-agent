"""Zakladka Bieganie — filtry typu, wykresy tempa/HR, running dynamics, tabela."""
from __future__ import annotations
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.queries import q_runs_recent, q_runs_with_dynamics
from dashboard.helpers import fmt_pace
from dashboard.utils import get_user_id


def page_running():
    st.title("🏃 Bieganie")

    user_id = get_user_id()
    runs_df = q_runs_recent(limit=50, user_id=user_id)
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
    dyn = q_runs_with_dynamics(since="-90 days", user_id=user_id)
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
