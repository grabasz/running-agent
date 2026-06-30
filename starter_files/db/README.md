# Running DB

Lokalna SQLite jako źródło prawdy dla strukturalnych danych.
**Forward-compatible z Turso/libSQL** (Faza 3 — chmura).

## Struktura

```
db/
├── schema.sql         # 9 tabel (DDL)
├── queries/           # SQL queries (Dapper-style, ładowane przez aiosql)
│   ├── gym.sql        #   session_add, set_add, exercise_progression, ...
│   ├── runs.sql       #   run_upsert, recent, lap_add, ...
│   ├── weekly_volume.sql
│   ├── races.sql      #   add, update_result, pb_for_distance, ...
│   ├── body.sql       #   weight_log, state_log, state_recent
│   ├── vdot.sql       #   add, current, history
│   └── stats.sql      #   counts (sanity)
├── init_db.py         # tworzy/resetuje data.db
├── api.py             # thin wrapper aiosql + connection helper
├── migrate.py         # jednorazowy import z .md
├── smoke_test.py      # sanity check — 10 zapytań
├── requirements.txt   # aiosql>=15.0
├── data.db            # ⚠️ git-ignored
└── README.md
```

## Dodawanie nowego zapytania

1. Dopisz do odpowiedniego `queries/*.sql`:
   ```sql
   -- name: easy_runs_last_n_days
   SELECT * FROM runs
    WHERE type = 'Easy' AND date >= date('now', :since)
    ORDER BY date DESC;
   ```
2. Od razu dostępne w API — bez modyfikacji `api.py`:
   ```python
   import api
   with api.connect() as conn:
       for r in api.runs.easy_runs_last_n_days(conn, since="-14 days"):
           print(r["date"], r["distance_km"])
   ```

Suffixy aiosql w nazwach queries:
- `name<!` → INSERT zwracający lastrowid
- `name!` → INSERT/UPDATE/DELETE (rowcount)
- `name^` → SELECT zwracający jeden wiersz lub `None`
- `name$` → scalar (single value)
- `name` (bez sufiksu) → lista wierszy (`sqlite3.Row`, dict-like)

## Tabele

| Tabela | Co zawiera | Źródło |
|--------|-----------|--------|
| `gym_sessions` | sesje siłowni (data, czas, HR, kontekst) | gym_log.md → potem `silownia.py` |
| `gym_sets` | serie ćwiczeń (reps/duration, ciężar) | gym_log.md → potem `silownia.py` |
| `runs` | biegi (dystans, tempo, HR, typ) | Strava → `run.py` (TODO upgrade) |
| `run_laps` | splity per km | Strava streams |
| `weekly_volume` | agregat tygodniowy | volume_log.md → `volume.py` (TODO upgrade) |
| `races` | wyścigi (target + actual + PB flag) | races.md + plan_current.md |
| `body_weight` | waga ciała | (pusta, dodawaj ręcznie) |
| `body_state` | objawy/DOMS/ból per lokalizacja | logujesz po sesji |
| `vdot_history` | progresja VDOT | fitness.md |

## Quickstart

```powershell
# (raz) inicjalizacja + migracja
cd db
python init_db.py
python migrate.py          # załaduj istniejące .md
python smoke_test.py       # sprawdź czy dane są

# reset i ponowna migracja (przy zmianach schematu/migratora)
python migrate.py --reset
```

## Użycie z innego skryptu

```python
import sys
sys.path.insert(0, r"C:\Users\grabb\Documents\running\db")
import api

with api.connect() as conn:
    # Ostatnie sesje siłowni
    for s in api.gym.sessions_recent(conn, limit=3):
        print(s["date"], s["context"])

    # Progresja ćwiczenia
    for s in api.gym.exercise_progression(conn, exercise="RDL", limit=10):
        print(s["date"], s["weight_kg"], "kg ×", s["reps"])

    # Dodaj sesję
    sid = api.gym.session_add(conn,
        date="2026-06-29", duration_min=30, hr_avg=None, hr_max=None,
        calories=None, context="Easy mobility", notes=None)
    api.gym.set_add(conn, session_id=sid, exercise="Plank", set_num=1,
        reps=None, duration_sec=60, weight_kg=None, weight_per_side=0,
        rest_sec=None, rpe=None, notes=None)

# Helpery wyższego poziomu (otwierają własne połączenie)
pb = api.race_pb(21.0975)   # HM
print(f"{pb['name']} {pb['actual_time_sec']//60}:{pb['actual_time_sec']%60:02d}")
```

## Co NIE jest migrowane (zostaje jako .md)

- `plan_current.md` — bieżący plan + edytowalny ręcznie
- `fitness.md` — strefy + VDOT current (vdot_history idzie do DB jako log)
- `profile.md` — kontekst użytkownika
- `groups.md`, `races.md` — kalendarz (już zmigrowany, ale plik zostaje)
- `skills_*.md` — instrukcje dla Claude

Te pliki edytujesz w VS Code, Claude czyta jako kontekst.

## Mapa faz refaktoru

- **Faza 1 (zrobione 28.06.2026)**: schemat + migracja + API + smoke test
- **Faza 2**: upgrade `volume.py` i `run.py` żeby pisały do DB; nowy `silownia.py`
- **Faza 3**: custom MCP server (`running-db`) — Claude Desktop też ma dostęp
- **Faza 4**: migracja do Turso (cloud) — `DB_PATH` na URL, reszta API bez zmian
- **Faza 5**: Streamlit dashboard (lub Next.js)
