"""Dashboard package — modularny podzial monolitu dashboard.py.

Struktura:
  auth.py        — password gate + Turso bootstrap
  utils.py       — session_state accessors (get_user_id, get_user_name)
  constants.py   — LIFE_*, NOTE_*, ARTIFACT_CATEGORIES, VDOT_CAL_OFFSET
  helpers.py     — fmt_pace, fmt_time, daniels_race_time, monday_iso
  queries.py     — wszystkie @st.cache_data q_*
  callbacks.py   — _apply_*, _cb_*, _push_*, _invalidate_*
  pages/         — jedna zakladka = jeden plik

Wejscie dashboardu: `dashboard.py` w root starter_files/ (Streamlit Cloud
entry point). Wszystko tutaj jest ladowane przez `import dashboard.xxx`.
"""
