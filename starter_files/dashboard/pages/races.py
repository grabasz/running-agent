"""Zakladka Wyscigi — nadchodzace, PB, VDOT progresja, race predictors."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.queries import q_races_upcoming, q_races_history, q_vdot_history
from dashboard.helpers import fmt_time, daniels_race_time
from dashboard.utils import get_user_id


def page_races():
    st.title("🏆 Wyścigi")

    user_id = get_user_id()
    upcoming = q_races_upcoming(user_id=user_id)
    history = q_races_history(user_id=user_id)

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
    vdot_df = q_vdot_history(limit=20, user_id=user_id)
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
