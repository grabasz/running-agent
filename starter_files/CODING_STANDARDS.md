# Zasady kodowania — Running Agent

**AI (Claude) musi sprawdzić ten plik przed każdym write kodu Python. User (Bartek) egzekwuje.**

## SOLID (pragmatycznie)

- **SRP** — jedna funkcja/moduł = jedna odpowiedzialność. Jeśli funkcja robi query + transform + render → rozbij.
- **OCP** — dodanie nowej zakładki/typu ćwiczenia/kategorii notatki nie wymaga edycji 5 miejsc. Rejestruj przez dict/tabelę.
- **DIP** — funkcje nie tworzą `conn` same. Dostają przez arg (`def foo(conn, user_id)`). Testowalne bez patchowania.

## Praktyczne

- **Max 200 linii per plik.** Powyżej → rozbij po odpowiedzialnościach.
- **Cached queries** (`@st.cache_data`) w osobnym module od render code.
- **Callbacks** (`on_change`, submit handlers) w osobnym module od render.
- **Constants / config** na górę pliku (albo w `constants.py`), nie inline w środku funkcji.
- **Zero hardkodów danych.** Ćwiczenia, plany, opisy → DB, nie Python constants.
- **user_id ZAWSZE jako parametr.** Nigdy hardkodowany w funkcji.
- Konwencje nazw: `page_*` (strona dashboardu), `q_*` (query cached), `_apply_*` (callback), `render_*` (fragment UI reużywalny).

## Testy jednostkowe (must)

- **Każda query function → test pytest** z SQLite in-memory (fixture `tmp_conn` w `conftest.py`).
- **Callback functions → test z mock conn** (verify SQL wywołany z właściwymi params).
- UI streamlit (renderowanie widgetów) — pomijamy, e2e za drogie.
- Struktura: `tests/test_<moduł>.py`, uruchamiane przez `pytest -q`.
- CI: `pytest tests/ -v` musi być zielony przed merge.

## Anti-patterns — banned

- ❌ **Business logic w f-string SQL** (`f"SELECT ... WHERE user={user_id}"`) — używaj `?` / `:param` binding.
- ❌ **Silent `except: pass`** — chyba że jest KOMENTARZ dlaczego akceptujemy błąd.
- ❌ **Global mutable state** modyfikowany z wielu miejsc (poza `st.session_state` który to legit Streamlit pattern).
- ❌ **Hardkodowany user_id** w signature albo body funkcji.
- ❌ **Kopiowana logika** w 3+ miejscach → wyekstrahuj do `components.py` / helper.
- ❌ **Import time side effects** (query do DB, print, dziwne mutate) — tylko w funkcjach.

## Kiedy AI może naruszyć zasady

Tylko z jawnym uzasadnieniem w komentarzu w kodzie **i** wzmiance w PR description. Przykład OK:
```python
# ODSTĘPSTWO od SRP: łączymy query + render bo Streamlit form_submit musi być inline
```

Bez uzasadnienia → user odrzuca PR.

## Refactor priorities (bieżące)

1. `dashboard.py` (1627 linii) → `dashboard/` package z pages/, queries.py, callbacks.py, components.py
2. `mcp-servers/garmin-oauth/server.py` (1195 linii) → analogiczny podział (task #57)
