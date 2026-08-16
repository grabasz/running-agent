# Tests

Testy jednostkowe DB / query logic dla dashboardu i api. Uruchamiane przez pytest.

## Wymagania

- `pytest` (`pip install pytest`)
- Reszta test infra samowystarczalna (in-memory SQLite, schema z `db/schema.sql`)

## Uruchamianie

```bash
# Z folderu starter_files/:
pytest tests/ -v

# Konkretny plik:
pytest tests/test_dashboard_queries.py -v

# Konkretny test:
pytest tests/test_dashboard_queries.py::test_notes_user_isolation -v
```

## Fixtures (w `conftest.py`)

- **`tmp_conn`** — czysta in-memory SQLite z pełną schemą (baseline + wszystkie migracje). Zero danych.
- **`seeded_conn`** — jak wyżej + minimalny seed:
  - `body_state`: 1 wpis dla Bartka (user_id=1)
  - `notes`: 1 wpis dla Bartka
  - users: 2 wiersze (Bartek, Mati) — z baseline schema

## Co testujemy

- **Query SQL logic** — czy filtry (user_id, date, category) działają
- **Multi-user isolation** — user A nie widzi danych user B
- **UPSERT semantics** — konflikt, ON CONFLICT behavior
- **Anti-patterns** — dokumentacyjne testy pokazujące co jest złe (np. SQL injection)

Po refaktorze `dashboard.py` → `dashboard/queries.py` testy będą mogły importować
funkcje bezpośrednio zamiast kopiować SQL.

## xfail — expected failures

Testy dokumentujące znane blockery (np. `test_body_state_upsert_...` = Task #58,
brak UNIQUE(date, location)). Pytest zwraca zielone dopóki blocker istnieje;
po naprawie test przejdzie jako XPASS i trzeba usunąć `xfail` marker.
