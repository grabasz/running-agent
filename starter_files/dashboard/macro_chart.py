"""Wykres progresu makroplanu: realne km vs plan referencyjny vs replan od dziś.

Jedna oś (km/tydz). Kolory: slot 1 (niebieski) = wykonanie, slot 2 (pomarańcz)
= replan, plan referencyjny = neutralny szary. Legenda + hover z fazą tygodnia.
"""
from __future__ import annotations
import plotly.graph_objects as go

from planner.methodology import PHASE_LABELS

ACTUAL_COLOR = "#2a78d6"
REPLAN_COLOR = "#eb6834"
REFERENCE_COLOR = "#8a8984"


def render_progress_chart(reference: list[dict], actual_km: dict[str, float],
                          replan: list[dict], today_iso: str) -> go.Figure:
    fig = go.Figure()
    ref_x = [w["week_start"] for w in reference]
    act_x = sorted(k for k in actual_km if not ref_x or k >= ref_x[0])
    fig.add_bar(
        x=act_x, y=[actual_km[k] for k in act_x], name="Wykonane",
        marker=dict(color=ACTUAL_COLOR), opacity=0.9,
        hovertemplate="%{x}<br>Wykonane: %{y:.1f} km<extra></extra>",
    )
    if reference:
        fig.add_scatter(
            x=ref_x, y=[w["target_km"] for w in reference], name="Plan referencyjny",
            mode="lines+markers", line=dict(color=REFERENCE_COLOR, width=2, shape="hv"),
            marker=dict(size=8),
            customdata=[[PHASE_LABELS.get(w["phase"], w["phase"]), "odciążenie" if w["is_deload"] else ""]
                        for w in reference],
            hovertemplate="%{x}<br>Plan: %{y:.1f} km<br>%{customdata[0]} %{customdata[1]}<extra></extra>",
        )
    if replan:
        fig.add_scatter(
            x=[w["week_start"] for w in replan], y=[w["target_km"] for w in replan],
            name="Replan od dziś", mode="lines", line=dict(color=REPLAN_COLOR, width=2, dash="dash", shape="hv"),
            customdata=[PHASE_LABELS.get(w["phase"], w["phase"]) for w in replan],
            hovertemplate="%{x}<br>Replan: %{y:.1f} km<br>%{customdata}<extra></extra>",
        )
    fig.add_vline(x=today_iso, line=dict(color=REFERENCE_COLOR, width=1, dash="dot"))
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=30, b=10), bargap=0.25,
        yaxis_title="km / tydzień", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", rangemode="tozero")
    fig.update_xaxes(showgrid=False)
    return fig
