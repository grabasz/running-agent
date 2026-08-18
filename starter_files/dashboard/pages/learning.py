"""Zakladka Nauka — edukacyjna sekcja dla wszystkich (szczegolnie Matiego).

Statyczna tresc + jeden query do planu na dzis. Bez zapisow.
"""
from __future__ import annotations
import streamlit as st

from dashboard.queries import q_today
from dashboard.utils import get_user_id


def page_learning():
    st.title("🎓 O co chodzi w bieganiu?")
    st.caption("Twoi trenerzy — Jack Daniels + zdrowy rozsądek.")

    st.markdown("### 🏃‍♂️ 5 typów treningu — co i dlaczego")

    with st.expander("🌿 **Easy** — spokojnie, długo, o rozmowie", expanded=True):
        st.markdown("""
**Jak biegać:**  Tak wolno, żebyś mógł spokojnie **gadać pełnymi zdaniami**. Bez zadyszki. Bez patrzenia na zegarek co 100 m.

**Po co:**  Buduje **wytrzymałość podstawową** — Twoje serce staje się mocniejsze, mięśnie uczą się palić tłuszcz zamiast cukru.
Tego biegania nigdy nie jest za dużo. To fundament wszystkiego innego.

**Typowa dystansa:**  3–10 km, zależy od poziomu.
**Jak się czuć potem:**  Chcesz jeszcze pobiegać. Nie jesteś zmęczony.
        """)

    with st.expander("⚡ **Tempo** — komfortowo ciężko"):
        st.markdown("""
**Jak biegać:**  Tak szybko, że nie da się gadać pełnymi zdaniami — tylko krótkie słowa. Nie jest "cierpienie", ale też nie "spacer".
Wyobraź sobie że biegniesz **tempem, którym mógłbyś biec przez godzinę** i tylko pod koniec zaczyna boleć.

**Po co:**  Uczy ciało **wysiłku na granicy** — próg mleczanowy. Za tydzień będziesz umiał utrzymać to tempo dłużej.

**Typowa struktura:**  2 km rozgrzewka → 4-6 km tempo → 2 km wychłodzenie.
**Jak się czuć potem:**  Zadowolony i się nie zmęczyłeś 😅
        """)

    with st.expander("🛣️ **Long** — długo, wolno, bez pośpiechu"):
        st.markdown("""
**Jak biegać:**  Jak **Easy**, tylko **dłużej niż zwykle**. Tempo takie samo albo trochę wolniejsze.

**Po co:**  Twoje ciało uczy się być długo w ruchu bez zmęczenia. Kości, ścięgna, mięśnie się wzmacniają. To jest trening który robi z ciebie **biegacza na dystansie**.

**Typowa dystansa:**  10-20+ km (dla dorosłych), 5-8 km dla dzieci.
**Jak się czuć potem:**  Zmęczony ale spełniony. Wieczorem — spać jak dziecko.
        """)

    with st.expander("🔥 **Interval** — krótkie ale mocne odcinki"):
        st.markdown("""
**Jak biegać:**  **Bardzo szybko przez krótki dystans** (400-1000 m), potem przerwa (trucht lub spacer), potem znowu szybko. Kilka razy.
Przykład: 6 × 400 m po ~1:30, między nimi 200 m truchtu.

**Po co:**  Uczy ciało biegać **szybko** i **poprawia VO2max** — ile tlenu Twój organizm umie zużyć na minutę. Kluczowe dla szybkości.

**Jak się czuć potem:**  Wykończony, ale krótkotrwale. Dzień odpoczynku obowiązkowy.
        """)

    with st.expander("💧 **Recovery / Regeneracja** — po ciężkim dniu"):
        st.markdown("""
**Jak biegać:**  Jeszcze **wolniej niż Easy**. Praktycznie spacer szybszy. 20-40 minut.

**Po co:**  Ruch pobudza krew, krew zabiera "śmieci" z mięśni (kwas mlekowy, mikrouszkodzenia).
Po ciężkim treningu następnego dnia jest **lepiej** niż leżeć na kanapie.

**Jak się czuć potem:**  Lżej. Bezruchowe bóle znikają.
        """)

    st.divider()
    st.markdown("### 📊 Skala RPE — jak ciężko było?")
    st.caption("RPE = Rate of Perceived Exertion. Po każdym biegu spytaj sam siebie: **jak bardzo mnie to zmęczyło?**")

    rpe = [
        ("1-2", "🚶", "**Spacer**. W ogóle nie zauważyłem że biegałem."),
        ("3-4", "🌿", "**Easy**. Mogłem gadać pełnymi zdaniami. Chcę jeszcze."),
        ("5-6", "⚡", "**Tempo**. Krótkie słowa. Trochę pot. Umiem to utrzymać 30-60 min."),
        ("7-8", "🔥", "**Ciężko**. Ledwo słowo. Pot. Chcę żeby już się skończyło."),
        ("9", "😵", "**Bardzo ciężko**. Nie umiem gadać. Ostatnie 5 minut wyścigu."),
        ("10", "💀", "**Maksymalne**. Ostatnie 100 m sprintu. Nie da się utrzymać."),
    ]
    for score, icon, desc in rpe:
        st.markdown(f"- **{score}** {icon} — {desc}")

    st.divider()
    st.markdown("### 🎯 Dlaczego dziś ten trening?")
    st.caption("Twój aktualny plan na dzisiaj (jeśli jest):")

    plan_today = q_today(user_id=get_user_id())
    if plan_today:
        for p in plan_today:
            st.info(f"**{p.get('type_display_pl', p.get('type_key', '?'))}** — {p.get('title', 'brak tytułu')}")
            if p.get("notes"):
                st.caption(p["notes"])
    else:
        st.caption("Nic zaplanowanego na dziś. Odpoczynek lub decyduje ciało.")

    st.divider()
    st.markdown("### 🧠 3 zasady od trenera")
    st.markdown("""
1. **80% biegów to Easy.** Serio. Jeśli wszystkie biegi cię męczą — biegasz za szybko.
2. **Nie stawaj coraz ciężej co tydzień.** Ciało potrzebuje czasu żeby się dostosować. Lepiej mniej biegać ale konsekwentnie.
3. **Ból = zatrzymaj się.** Zmęczenie mięśni to normalne. Ostry ból (kolano, ścięgno) — koniec, nie biegasz przez 2-3 dni.
    """)
