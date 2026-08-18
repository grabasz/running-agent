"""Zakladka Codzienna rutyna — cwiczenia z DB + trend kolana + historia zmian."""
from __future__ import annotations
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

import api  # type: ignore

from dashboard.queries import q_active_routine, q_routine_exercises, q_all_routines, q_body_state
from dashboard.utils import get_user_id


def page_routine():
    st.title("🌅 Codzienna rutyna")

    user_id = get_user_id()
    routine = q_active_routine(user_id)
    if not routine:
        st.warning("Brak aktywnej rutyny w bazie. Wejdź w 🏋️ Ćwiczenia → dodaj nową rutynę.")
        return

    total_min = f"~{routine['total_time_min']} min" if routine.get('total_time_min') else "kilka min"
    st.caption(
        f"**{total_min}** rano przed pracą. Rutyna: **{routine['name']}** "
        f"(od {routine['active_from']}) — fokus: **{routine.get('focus') or 'brak'}**."
    )

    st.markdown(
        "> **Zasada:** 1× każde ćwiczenie, nie 3 serie. "
        "Powtarzalność ważniejsza niż intensywność. "
        "Jeśli nie masz czasu na wszystko — zrób **przynajmniej pierwsze 2** (zwykle rolowanie), reszta to bonus."
    )

    st.divider()
    st.markdown("### 📋 Kolejność")

    exercises = q_routine_exercises(routine["id"])
    if not exercises:
        st.info("Rutyna nie ma jeszcze przypisanych ćwiczeń.")
    else:
        for ex in exercises:
            hdr = f"**#{ex['position']} · {ex['name']}** — {ex.get('duration_or_reps') or ''} · {ex.get('tool') or ''}"
            if ex.get('re_notes'):
                hdr += f"  _({ex['re_notes']})_"
            with st.expander(hdr, expanded=(ex['position'] <= 2)):
                st.markdown(ex["description_md"])
                if ex.get("youtube_url"):
                    st.link_button("▶️ Zobacz na YouTube", ex["youtube_url"])
                else:
                    st.caption("_Brak linku YouTube. Dodaj w zakładce 🏋️ Ćwiczenia._")

    st.divider()

    # --- Zapisz dziś ---
    st.markdown("### ✅ Zapisz jak było dziś")
    st.caption("Krótki wpis — buduje historię trendu kolana. Dopisz TYLKO gdy coś się zmienia lub coś boli mocniej.")

    with st.form("routine_daily_log", clear_on_submit=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            pain = st.selectbox(
                "Kolano prawe (klękanie)",
                options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                index=2,
                help="0 = nie boli wcale, 3 = lekki dyskomfort, 5 = wyraźny ból, 8+ = przerwij rutynę i idź do fizjo"
            )
        with col2:
            note = st.text_input(
                "Co dziś zauważyłeś?",
                placeholder="np. rolowanie stopy pomogło mocno; klękanie 2/10 rano; ITB roll boli mniej niż wczoraj",
                help="Opcjonalne. Krótkie zdanie."
            )
        submitted = st.form_submit_button("💾 Zapisz do body_state")
        if submitted:
            with api.connect() as conn:
                api.body.state_log(
                    conn,
                    user_id=user_id,
                    date=datetime.now().date().isoformat(),
                    location="kolano_prawe",
                    pain_0_10=int(pain),
                    doms=0,
                    notes=note.strip() or f"Poranna rutyna '{routine['name']}' zrobiona.",
                )
            st.cache_data.clear()
            st.success(f"✅ Zapisane: kolano_prawe = {pain}/10")
            st.rerun()

    st.divider()

    # --- Trend kolana (30 dni) ---
    st.markdown("### 📉 Kolano prawe — trend (30 dni)")
    body_30 = pd.DataFrame(q_body_state(since="-30 days", user_id=user_id))
    if body_30.empty:
        st.info("Brak wpisów — zacznij codziennie klikać wyżej.")
    else:
        knee = body_30[body_30["location"] == "kolano_prawe"].copy()
        if knee.empty:
            st.info("Brak wpisów dla kolano_prawe w ostatnich 30 dniach.")
        else:
            knee["date"] = pd.to_datetime(knee["date"])
            knee_pain = knee[knee["pain_0_10"].notna()].sort_values("date")
            if not knee_pain.empty:
                fig = px.line(knee_pain, x="date", y="pain_0_10", markers=True,
                              labels={"pain_0_10": "Ból 0-10", "date": ""})
                fig.update_layout(height=220, margin=dict(t=10, b=10, l=10, r=10),
                                  yaxis=dict(range=[-0.3, 10], dtick=2))
                st.plotly_chart(fig, use_container_width=True)
            with st.expander("Ostatnie 10 wpisów", expanded=False):
                recent = knee.head(10)[["date", "pain_0_10", "notes"]].copy()
                recent["date"] = recent["date"].dt.strftime("%Y-%m-%d")
                st.dataframe(recent.rename(columns={
                    "date": "Data", "pain_0_10": "Ból", "notes": "Notatki"
                }), hide_index=True, use_container_width=True)

    st.divider()

    # --- Kiedy zmienić rutynę ---
    st.markdown("### 🔄 Kiedy zmienić rutynę")
    st.markdown("""
- **Test diagnostyczny pokazał nowego winowajcę** → dopisz/wymień ćwiczenie pod ten obszar.
- **7+ dni bez poprawy klękania** (trend płaski) → coś nie działa, zmień akcent.
- **Fizjo powie inaczej** → posłuchaj fizjo, nie AI.
- **Nowy ból** w innej okolicy → dopisz ćwiczenie pod tamten obszar (nie usuwaj tego co działa).
- **Ból pod obciążeniem znika, klękanie zostaje** → rutyna działa na jedną warstwę problemu, może potrzebna USG.
    """)

    st.divider()

    # --- Historia zmian ---
    with st.expander("📜 Historia zmian rutyny", expanded=False):
        all_r = q_all_routines(user_id)
        if not all_r:
            st.caption("Brak historii.")
        else:
            for r in all_r:
                period = r["active_from"]
                if r["active_to"]:
                    period += f" → {r['active_to']}"
                else:
                    period += " → dziś"
                st.markdown(f"- **{period}** — **{r['name']}**"
                            + (f" — _{r['notes']}_" if r.get("notes") else ""))
