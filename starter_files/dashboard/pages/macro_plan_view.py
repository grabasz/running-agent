"""Makroplan — widok aktywnego planu: bieżący tydzień, cały plan, reguły i tempa."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from planner.methodology import PHASE_LABELS


def _pace(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def render_this_week(now: dict | None) -> None:
    if not now or not now.get("this_week"):
        return
    w, nxt = now["this_week"], now.get("next_week")
    st.markdown(f"### 📍 Tydzień {now['week_no']}/{now['weeks_total']} · "
                f"{PHASE_LABELS.get(w['phase'], w['phase'])}"
                f"{' · odciążenie' if w['is_deload'] else ''} · **{w['target_km']:g} km**")
    c1, c2 = st.columns(2)
    c1.markdown(f"**Akcenty:** {w.get('key_session') or '—'}")
    c2.markdown(f"**Long:** {w.get('long_structure') or w.get('long_km')}")
    if w.get("notes"):
        st.caption(w["notes"])
    if nxt:
        st.caption(f"Następny ({nxt['week_start']}): {nxt['target_km']:g} km · "
                   f"{nxt.get('key_session') or ''} · long: {nxt.get('long_structure') or nxt.get('long_km')}")


def render_plan_table(reference: list[dict], shadow: list[dict]) -> None:
    det = {w["week_start"]: w for w in shadow}
    rows = [{
        "tydzień": w["week_start"], "faza": PHASE_LABELS.get(w["phase"], w["phase"]),
        "km": w["target_km"], "km DET": (det.get(w["week_start"]) or {}).get("target_km"),
        "long": w.get("long_structure") or w.get("long_km"), "akcenty": w.get("key_session"),
        "deload": "✓" if w["is_deload"] else "",
    } for w in reference]
    with st.expander("📋 Cały makroplan (km DET = plan deterministyczny do porównania)"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_rules(now: dict | None) -> None:
    if not now:
        return
    with st.expander(f"📏 Reguły ważne dziś ({len(now['rules'])}) i tempa"):
        if now["paces"]:
            st.markdown(" · ".join(f"**{p['zone']}** {_pace(p['min_sec'])}-{_pace(p['max_sec'])}"
                                   for p in now["paces"]))
        for r in now["rules"]:
            until = f" (do {r['valid_to']})" if r.get("valid_to") else ""
            st.markdown(f"- `{r['rule_type']}` **{r['subject']}**: {r.get('value') or ''}{until}")
        for rev in now["revisions"]:
            st.caption(f"🕓 {rev['created_at']} · {rev['event_type']}: {rev['reason']}")
