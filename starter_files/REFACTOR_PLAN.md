# Refactor Plan — Running Project

> **Cel ogólny**: przejść z plików `.md` jako źródło prawdy → **strukturalna baza danych** (SQLite → Turso) + **Garmin Connect** jako primary źródło aktywności (Strava jako fallback) + **dashboard** + **MCP server** dla Claude Desktop.
>
> **Filozofia**:
> - **Markdowny kontekstowe** (`plan_current.md`, `fitness.md`, `profile.md`, `races.md`, `groups.md`) **zostają jako edytowalne ręcznie** — Bartek edytuje w VS Code, Claude czyta jako kontekst
> - **Markdowny logów** (`gym_log.md`, `volume_log.md`) — **rendered views** generowane z DB (read-only kopia ostatnich N tygodni / aktualnych możliwości)
> - **Strava zostaje** jako fallback dla użytkowników bez Garmina (przyszłość multi-user, dziś Bartek jedyny)
> - **Multi-user** to faza dalej — dziś single-user, nie over-engineerujemy

---

## ✅ Faza 1 — DB foundation (ZROBIONE 28.06.2026)

**Co stoi:**
- `db/schema.sql` — 9 tabel: `gym_sessions`, `gym_sets`, `runs`, `run_laps`, `weekly_volume`, `races`, `body_weight`, `body_state`, `vdot_history`
- `db/queries/*.sql` — 7 plików SQL (Dapper-style), ładowane przez **aiosql** (`pip install aiosql`)
- `db/api.py` — thin wrapper na aiosql + `connect()` context manager + helpery (race_pb, stats_summary)
- `db/init_db.py` — tworzy/resetuje `data.db`
- `db/migrate.py` — jednorazowy import z `.md`
- `db/smoke_test.py` — 10 typowych zapytań (sanity check, wszystkie zielone)
- `db/README.md` — onboarding
- `db/.gitignore` — wyklucza `data.db`

**Stan bazy po migracji:** 14 weekly_volume, 8 races (3 z actuals + PB Białystok 1:39:37), 3 vdot_history, 2 gym_sessions + 36 gym_sets, 7 body_state (4 z 28.06 + 3 z 29.06).

**Decyzje architektoniczne:**
- **aiosql** wybrany zamiast SQLModel/SQLAlchemy (Dapper-style, SQL w plikach)
- **SQLite local-first** z planem na Turso (forward-compatible — libsql używa SQLite syntax)
- **kwargs_only=False, mandatory_parameters=False** w aiosql.from_path (proste kwargs)
- **Per-domain namespaces**: `api.gym.*`, `api.runs.*`, `api.races.*` (każdy `.sql` ładowany osobno)

---

## ✅ Faza 3 (alternatywa) — Garmin MCP (ZROBIONE 29.06.2026)

Zamiast pisać własny MCP server, używamy **etweisberg/garmin-connect-mcp** (npm package).

**Co działa:**
- `npm install -g @etweisberg/garmin-connect-mcp` + `npx playwright install chromium`
- Config w **`running/.mcp.json`** (NIE `~/.claude.json`) z **pełną ścieżką do `node.exe`** (Strava pattern)
- Login przez `mcp__garmin__garmin-login` → Playwright otwiera Garmin SSO → user wpisuje → token cached w `~/.garmin-connect-mcp/session.json`
- 40+ narzędzi: `list-activities`, `get-activity-details`, `get-activity-splits`, `get-daily-heart-rate`, `get-sleep`, `get-body-battery`, `get-hrv`, `get-training-readiness`, `get-personal-records`, ...

**Pitfall (rozwiązany):** Claude Code spawnuje przez Node child_process który NIE używa PATHEXT → `command: "npx"` failuje na Windows. Fix: pełna ścieżka `node.exe` + pełna ścieżka do `dist/index.js`.

**Session token expiruje po kilku godzinach** — re-login przez ten sam flow gdy `check-session` zwraca błąd.

---

## ✅ Faza 2a — `silownia.py` (ZROBIONE 29.06.2026)

**Co stoi:**
- `scripts/silownia_save.py` — `save_strength(activity, context)`, `render_gym_log(limit)`, `update_gym_log_file(limit)`. CLI: `python silownia_save.py <activity.json> ["context"]` lub `--render-only [limit]`.
- Mapping `EXERCISE_MAP` z Garmin `(category, subCategory)` → polskie nazwy (BSS, RDL, Goblet squat, Plank itp.) + fallback dla unmapped.
- Auto-regen `garmin_workouts/gym/gym_log.md` po każdym save: ostatnie N sesji + sekcja **"Wzorzec aktualnych możliwości"** (top ćwiczenia z max ciężarem ostatnich 90 dni).
- `.claude/commands/silownia.md` — nowy skill `/silownia`: Garmin primary fetch → save → render markdown.

**Real test 29.06.2026:** sesja 27.06 zaimportowana z Garmina (activityId 23399564351), 27 setów, gym_log.md regenerowany z aktualnymi danymi + Wzorzec ciężarów.

**Znane ograniczenia (nice-to-have do późniejszego usprawnienia):**
- Garmin `summarizedExerciseSets` daje **sumaryczne dane per ćwiczenie** (nie per-set). Heurystyka: `reps_per_set = total_reps / n_sets`. BSS 52/3 = 17 reps per set choć faktycznie było 16+16+20.
- Brak per-side dla hantli (Garmin nie rozróżnia 2×8kg, traci się jako "16 kg max").
- Niektóre ćwiczenia bez `subCategory` (np. CORE bez DEAD_BUG) → ogólna nazwa "Cwiczenia na tulow".
- Pełna granulacja per-set wymagałaby `get-workout` z `workoutId` — TODO później.

---

## ✅ Faza 2b — `volume.py` upgrade (ZROBIONE 29.06.2026)

**Co stoi:**
- `scripts/volume.py` — po obliczeniu weekly aggregates dorzucony blok try/except: `api.weekly_volume.upsert(...)` dla każdego tygodnia (z `trend='recovery'|'peak'|None`).
- Errors na stderr, stdout dla skilla bez zmian (`Zapisano N tygodni → volume_log.md`).
- `volume_log.md` zostaje generowany jak teraz (świeże aggregaty ze Stravy) — markdown wystarcza, nie regenerujemy z DB.

**Real test 29.06.2026:** `<!-- saved 13 weeks to DB.weekly_volume -->`. DB ma 14 tygodni (1 z migracji 23.03 + 13 świeżych ze Stravy do 22.06).

**Co nie zostało zrobione (świadomie):**
- `volume_log.md` NIE jest regenerowany z DB — agreguje fresh ze Stravy. Powód: kalkulacja avg/trend wymaga znajomości całego okresu, więc i tak liczy się 13 tygodni fresh. DB upsert to **bonus** dla queries typu "ile km w czerwcu" przez Claude.

---

## ✅ Faza 2c — `run.py` upgrade (ZROBIONE 29.06.2026)

**Co stoi:**
- `scripts/garmin_save.py` — `save_run()`, `render_run_table()` (czyta z DB i drukuje tabelkę markdown z dynamics + markerami w tym ⚖️ asymetria L/R), CLI z bundle JSON `{activity, splits, type}`.
- `scripts/strava_save.py` — analogiczne `save_strava_run(details, laps, streams)` z auto-klasyfikacją typu. Pisze `source='strava'` bez dynamics.
- `scripts/run.py` — po Strava fetch wywołuje `save_strava_run` (errors na stderr, stdout dla Claude bez zmian).
- `.claude/commands/run.md` — przepisany flow: **Garmin primary (KROK 1A) → Strava fallback (KROK 1B)**, oba zapisują do DB. Nowy ⚖️ marker dla asymetrii L/R w Garmin output.

**Real test 29.06.2026:**
- `run_id=1` — Garmin "Kraków Bieganie" (28.06), z running dynamics (GCT 288ms, bal 49.58%, TE 3.2)
- `run_id=2` — Strava "Lazy 5+3km - Lampa jak 🥵🥵🥵" (28.06), bez dynamics ale z auto-pauzami i polską nazwą

**Stan**: ten sam bieg jest w DB jako **dwa rekordy** (osobne `source='garmin'` i `'strava'`). Deduplikacja przez `link_strava_to_garmin` w `queries/runs.sql` jest gotowa ale nie wywoływana automatycznie — czyli na razie 2 rekordy per bieg.

**Następne usprawnienie (low priority)**: auto-merge w `strava_save.py` — przed INSERT sprawdź `find_by_date_and_distance`. Jeśli znaleziono rekord Garmina (source='garmin') → UPDATE z strava_id zamiast nowego INSERT.

**(Stara sekcja "co jeszcze zostało" — już nieaktualna):**

**Co**: po każdym `/run` → INSERT do `runs` + `run_laps` z **Garmina** (running dynamics!), Strava jako fallback.

**Pliki**:
- `scripts/run.py` — modify (Garmin primary, Strava fallback)
- Update `.claude/commands/run.md` (skill) żeby informował o zapisie do DB

**Flow**:
1. `mcp__garmin__list-activities` limit=10 → znajdź ostatni `running` (filtruj e_bike, swim, strength)
2. `mcp__garmin__get-activity-details` + `get-activity-splits` → pełne dane + lapy
3. INSERT/UPSERT po `garmin_activity_id` do `runs`
4. INSERT do `run_laps` per km
5. Wygeneruj tabelkę markdown (jak teraz) ale z running dynamics

**Wymaga Fazy 2d (schema upgrade) najpierw.**

---

## ✅ Faza 2d — Schema upgrade pod running dynamics (ZROBIONE 29.06.2026)

**Co stoi:**
- `db/schema.sql` rozszerzony: `runs` ma 13 nowych kolumn (garmin_activity_id, source, running dynamics, TE, HR zones), `run_laps` ma 5 nowych (running dynamics per lap), nowa tabela `run_streams` (per-second time-series)
- `db/queries/runs.sql` przepisany: `run_upsert_garmin<!`, `run_upsert_strava<!`, `link_strava_to_garmin!`, `find_by_date_and_distance^`, `recent_with_dynamics`, `gct_balance_progression`, plus extended `lap_add<!` z dynamics, plus `stream_add<!` / `streams_for_run` / `hr_above_threshold_seconds$`
- Reset DB + migrate + smoke test = wszystko zielone

**Decyzja:** Strava i Garmin mają **osobne UPSERT functions** (różne klucze: `strava_id` vs `garmin_activity_id`). Deduplikacja przez `find_by_date_and_distance` + `link_strava_to_garmin` (gdy strava sync widzi bieg już z Garmina, dorzuca strava_id do istniejącego rekordu).

---

## ⏸️ Faza 2d-stary (DO IGNOROWANIA — zrobione powyżej)

**Co**: dodać kolumny które Garmin daje a których nie ma w obecnym schemacie.

**Nowe kolumny w `runs`:**
- `garmin_activity_id INTEGER UNIQUE` (klucz Garmina, osobny od `strava_id`)
- `source TEXT` — `'garmin'` | `'strava'`
- `vertical_oscillation_cm REAL`
- `ground_contact_ms INTEGER`
- `gct_balance_pct REAL` (avg balance lewej nogi w %, ~50% = symetria)
- `stride_length_cm REAL`
- `vertical_ratio_pct REAL`
- `training_effect_aerobic REAL` (0-5)
- `training_effect_anaerobic REAL` (0-5)
- `recovery_time_hours INTEGER`
- `body_battery_start INTEGER`
- `body_battery_end INTEGER`
- `vo2max_at_activity INTEGER`

**Nowa tabela `run_laps`** — dodać kolumny:
- `gct_balance_left_pct REAL`
- `vertical_oscillation_cm REAL`
- `stride_length_cm REAL`

**Nowa tabela `run_streams`** (opcjonalna, dla per-second HR/pace/cadence):
- `run_id INTEGER REFERENCES runs(id)`
- `second INTEGER`
- `hr INTEGER`
- `pace_sec_per_km INTEGER`
- `cadence INTEGER`
- `power INTEGER`
- `altitude_m REAL`
- Index na (run_id, second)

**Migracja:**
- `ALTER TABLE` w schema.sql (lub osobny migration script)
- `db/init_db.py` musi to obsłużyć przy reset

**Deduplikacja Garmin/Strava:**
- Garmin primary — INSERT z `source='garmin'`, `garmin_activity_id`
- Strava fallback — przed INSERT szuka po dacie + dystansie ±100m. Jeśli znajdzie → UPDATE z `strava_id` (zachowuje `source='garmin'`)

---

## ✅ Faza 4 — Turso cloud (ZROBIONE 29.06.2026)

**Co stoi:**
- **Konto Turso** + baza `running` w regionie `aws-eu-west-1` (Warsaw najbliżej)
- **`db/.env`** (gitignored) z `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`
- **`db/migrate_to_turso.py`** — one-shot: apply schema (21 stmts) + copy local data → Turso
- **`db/sync.py`** — narzędzie do dwustronnej replikacji:
  - `push` — local → Turso (po operacjach write)
  - `pull` — Turso → local (na nowej maszynie / drugim komputerze)
  - `status` — porównanie row counts (highlight diffs)

**Architektura: hybrid mode** (NIE embedded replica)
- aiosql + sqlite3 zostają lokalnie (bez zmian — działają z dict-like Row)
- libsql client tylko do migracji + sync (zwraca tuples, nie pasuje do aiosql)
- Po każdej operacji write skrypty mogą wywołać `python db/sync.py push` — nie automatycznie (latency), tylko on-demand lub przez cron

**Real test 29.06.2026:** `sync status` — wszystkie 10 tabel zgodne local vs Turso (13 weekly_volume, 8 races, 36 gym_sets etc.).

**Co zostało jako TODO (nice-to-have):**
- Auto-push w skryptach przez `AUTO_PUSH=1` env var (na razie manual `python db/sync.py push`)
- Conflict resolution gdy edytujesz na 2 maszynach jednocześnie (na razie last-write-wins przez DELETE+INSERT)
- Token expiry — sprawdź czy `iat: 1782767763` ma `exp` ustawione; jeśli nie → permanentny, jeśli tak → rotate przez `turso db tokens create running`

---

## ✅ Faza 5 — Streamlit Dashboard (ZROBIONE 30.06.2026)

**Co stoi:**
- `dashboard.py` (~400 linii) — Streamlit app z 4 stronami (sidebar nav)
- `requirements_dashboard.txt` — deps (streamlit, pandas, plotly, libsql, dotenv) — gotowe do Streamlit Cloud
- Wszystkie DB queries cache'owane `@st.cache_data(ttl=30-60s)` — szybkie odświeżanie, nie spamuje DB
- Sidebar ma przycisk "🔄 Odśwież dane (clear cache)" — manualny reload

**4 ekrany:**
1. **🏃 Przegląd** — VDOT/PB metryki, **bieżący tydzień z planned_workouts** (z ikonami statusu + pogodą), body_state 14d, wolumen tygodniowy bar chart (12 tyg z trend coloring)
2. **🏃 Bieganie** — filtry typ; tempo w czasie scatter, HR vs pace scatter, **GCT Balance L/R line chart** z linią symetrii 50%, tabela ostatnich biegów
3. **💪 Siłownia** — selectbox ćwiczenia → progresja max ciężaru + wolumen sesji, **top exercises by tonnage** (90 dni bar chart), tabela ostatnich sesji
4. **🏆 Wyścigi** — upcoming + PB metrics, VDOT progresja z annotacjami, **race predictors** dla VDOT 54-57 (5km/10km/HM/M), historia

**Real test 30.06.2026:** 14/14 DB queries zielone (smoke test). Streamlit health: `ok`. App dostępny lokalnie na `http://localhost:8501`.

**Uruchomienie lokalne:**
```bash
cd C:/Users/grabb/Documents/running
streamlit run dashboard.py
# albo headless w background:
streamlit run dashboard.py --server.headless true --server.port 8501
```

**Cloud deployment (TODO post-MVP — wymaga libsql adapter):**
1. Push do GitHub (publiczny lub prywatny repo) — pamiętaj że `.env` jest w `.gitignore`
2. https://share.streamlit.io → New app → repo + `dashboard.py`
3. Secrets w UI Streamlit: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`
4. `dashboard.py` musi obsłużyć tryb cloud (czytać z libsql zamiast lokalnego sqlite3) — wymaga refactor `db/api.py` żeby był provider-agnostic. Na razie dashboard działa **tylko lokalnie z `data.db`**.

**Mobile access ad-hoc:** otwórz `http://[twoje-ip]:8501` na telefonie w tej samej sieci WiFi (Streamlit pokazuje Network URL przy starcie).

---

## ✅ Faza 6 — Update CLAUDE.md + skills (ZROBIONE 29.06.2026)

**Co stoi:**
- `CLAUDE.md` — przepisane sekcje:
  - "🎯 Co tu robisz" — punkt 5 o DB
  - "📂 Co czytać i kiedy" — dorzucono `db/api.py`, `REFACTOR_PLAN.md`, ostrzeżenie o auto-generated `volume_log.md` / `gym_log.md`
  - "🛠️ Dostępne MCP" — dorzucono **Garmin Connect (40+ tools)** ⭐ + Playwright
  - **Nowa sekcja "📊 Baza danych"** — quickstart z `import api`, examples query, link do `REFACTOR_PLAN.md`
  - "⚡ Reguły oszczędności" — "Pytania historyczne → DB, nie fetch ze Stravy/Garmina"
  - "🚫 Czego NIE robić" — nie edytuj auto-generated markdownów ręcznie
  - **"📋 Skróty zachowań" jako tabela** — każde pytanie usera → akcja (`/run`, `/silownia`, `/volume`, `api.race_pb()`, `api.body.state_recent()` itd.)
  - **Nowa sekcja "🔄 Po /run i /silownia — sprawdź subiektywne"** — automatycznie zapisuj subiektywne odczucia do `body_state`
- `.claude/commands/run.md` — przepisany 29.06 (Garmin primary, Strava fallback, oba do DB) — FAZA 2c
- `.claude/commands/silownia.md` — nowy 29.06 — FAZA 2a
- `.claude/commands/volume.md` — update: info o DB save + przykład query historycznego
- Skill `mobility` — niezmieniony (potrzebuje own update aby używał `body_state` z DB)

**Real test:** następna sesja Claude zacznie pytania od skille zamiast ręcznego czytania markdownów.

---

## ✅ Faza 7 — Cleanup (ZROBIONE 29.06.2026)

**Co stoi:**
- **Usunięte 7 plików temp** (~63 KB): `_tmp_alt.json`, `_tmp_dist.json`, `_tmp_elev.py`, `alt_tmp.json`, `dist_tmp.json`, `tmp_elev.py`, `running_context.md.bak`
- **Skille skonsolidowane**:
  - `skills_gym.md` przepisany od nowa w EN — pełen spec dla strength workouts (47 valid categories, lookup table dla biegacza, weight signaling rules, pre-save checklist)
  - `skills_garmin.md` — usunięta zduplikowana sekcja "Strength workouts" (115 linii); zostaje link "For strength workouts → load `skills_gym.md`"
  - `skills_garmin.md` jest teraz **tylko o running workouts** (sportTypeId=1, pace.zone)
- **`mobility` skill upgrade**: KROK 0 sprawdza `body_state` z DB (jeśli pain>=2 lub świeży DOMS → preferuj głęboką regenerację); KROK 1 używa `api.runs.recent()` zamiast re-fetch ze Stravy; KROK 5 zapisuje nowe odczucia do `body_state` przez `api.body.state_log()`
- **Komentarze PL → EN w kodzie**: docstringi i komenty w `db/api.py`, `db/migrate.py`, `db/schema.sql`, `db/queries/*.sql`, `db/smoke_test.py`, `scripts/garmin_save.py`, `scripts/strava_save.py`, `scripts/silownia_save.py`, `scripts/run.py`, `scripts/volume.py` — wszystkie wewnętrzne komentarze EN. Print labels widoczne dla usera (smoke_test) zostają jak są.

**Real test:** migrate.py + smoke_test.py → all green po reset.

---

## ✅ Faza 8 — Planned workouts (training plan w DB) (ZROBIONE 30.06.2026)

**Co stoi:**
- **Schema**: `planned_workouts` + lookup tables `workout_statuses` (4) + `workout_types` (13). Statusy: planned/done/modified/skipped. Typy: easy/tempo/interval/long/recovery/shakeout/race/strength_a/strength_b/mobility/rest/cross/kickboxing.
- **Queries** (`db/queries/planned.sql`): `add`, `today`, `by_date`, `week_plan`, `current_week`, `upcoming`, `mark_status`, `link_actual_run`, `link_actual_session`, `auto_link_run_for_date`, `auto_link_session_for_date`, `delete_week`, `week_summary`, `list_types`, `list_statuses`.
- **API** (`api.planned.*`) — załadowane z JOIN'ami zwracającymi `type_icon`, `status_icon`, `display_pl`.
- **Skill `/dzis`** (`.claude/commands/dzis.md`) — pokazuje dzisiejszy plan + pozwala oznaczyć status.
- **Auto-link** w `garmin_save.py`, `strava_save.py`, `silownia_save.py` — gdy `/run` lub `/silownia` zapisuje aktualną sesję, AUTOMAT odnajduje matching planned_workout dla tej daty i ustawia status=done + link `actual_run_id`/`actual_session_id`.
- **Seed**: `db/seed_current_week.py` — wpisał aktualny tydzień 29.06–05.07 (7 dni).
- **`plan_current.md`** zaktualizowany: usunięto duplikującą tabelę "BIEŻĄCY TYDZIEŃ", zostały tylko red flags + link do `/dzis` jako source of truth.
- **CLAUDE.md** zaktualizowany: skróty zachowań "co dziś/jutro" → wywołaj `/dzis`.
- **Sync push do Turso**: wszystkie 13 tabel (w tym `planned_workouts` 7 wierszy) zsynchronizowane.

**Real test 30.06.2026:**
- `api.planned.today(conn)` → zwrócił dzisiejszy plan
- `api.planned.upcoming(conn, days="+2 days", limit=1)` → poprawnie zwraca **jutro** (nie dziś — fixed bug)
- `api.planned.week_summary(conn, week_start="2026-06-29")` → "Zaplanowany: 7 workouts (27.5 km planned)"
- Turso ma wszystkie nowe tabele po `python db/migrate_to_turso.py --reset`

**Co zostało jako TODO (nice-to-have):**
- Skill `/tydzien` — generator nowego tygodniowego planu z plan_current.md + pogoda + body_state (na razie ręczna edycja `seed_current_week.py`)
- UI/Telegram bot — odczyt + write planned_workouts z mobile (Faza 5 lub osobna)

---

## 🎯 Stan refaktoru — **WSZYSTKIE GŁÓWNE FAZY ZAMKNIĘTE** ✅

```
✅ Faza 1   DB foundation (schema + aiosql + queries + migrate)
✅ Faza 2a  silownia.py
✅ Faza 2b  volume.py upgrade
✅ Faza 2c  run.py upgrade (Garmin + Strava)
✅ Faza 2d  Schema running dynamics
✅ Faza 3   Garmin MCP (etweisberg)
✅ Faza 4   Turso cloud
✅ Faza 5   Streamlit dashboard
✅ Faza 6   CLAUDE.md + skille
✅ Faza 7   Cleanup
✅ Faza 8   Planned workouts w DB
```

**Pozostałe opcje (nice-to-have):**
- **Faza 8.5** — skill `/tydzien` (auto-generator tygodniowego planu z `plan_current.md` + body_state + pogoda) — ~1h
- **Faza 9** — Streamlit Cloud deployment (mobile dostęp via URL) — wymaga refactor `db/api.py` żeby był provider-agnostic (sqlite3 lokalnie / libsql w cloud) — ~2h
- **Faza 10** — Telegram bot (mobile native, push notifications) — ~3h
- **Faza 11** — Multi-user (gdy będziesz miał Mati/Jurek/Pychowice RC jako współ-userów) — ~4h

Wszystkie niezależne. Codzienna rutyna projektu jest w pełni działająca.

---

## 🚫 Anty-cele (czego NIE robimy)

- **NIE migrujemy `plan_current.md`/`fitness.md`/`profile.md` do DB** — to kontekst edytowany ręcznie
- **NIE piszemy własnego MCP server dla Garmina** — etweisberg/garmin-connect-mcp wystarcza
- **NIE robimy multi-user** (tabela `users`, RLS) — dziś single-user, dorzucimy gdy będzie Mati/Jurek
- **NIE używamy ORM** (SQLAlchemy, SQLModel) — Bartek wybrał Dapper-style (aiosql)
- **NIE migrujemy do Postgres** — SQLite/Turso wystarczają

---

## 📅 Historia decyzji

| Data | Decyzja | Powód |
|------|---------|-------|
| 28.06.2026 | aiosql zamiast SQLModel | Bartek wybrał Dapper-style |
| 28.06.2026 | Markdowny kontekstowe zostają | Łatwość edycji w VS Code |
| 28.06.2026 | gym_log/volume_log jako rendered views | Bartek chce "aktualny stan / ostatnie tygodnie" |
| 29.06.2026 | Strava zostaje jako fallback | Multi-user przyszłość, dziś Bartek jedyny |
| 29.06.2026 | etweisberg/garmin-connect-mcp zamiast własnego MCP | Bartek znalazł działający OSS rozwiązujący Cloudflare TLS fingerprinting |
| 29.06.2026 | `.mcp.json` zamiast `~/.claude.json` dla MCP config | Strava pattern, pełna ścieżka do node.exe |
| 29.06.2026 | Osobne UPSERT functions dla Garmin i Strava | Różne klucze (`garmin_activity_id` vs `strava_id`), różne zestawy kolumn |
| 29.06.2026 | `garmin_save.py` jako moduł Pythona (nie MCP klient) | Skill `/run` koordynuje fetch → mapping → save (Claude orchestruje, Python persystuje) |
| 29.06.2026 | Bundle JSON `{activity, splits, type}` jako format CLI dla `garmin_save.py` | Łatwiej Claude'owi: 1 plik zamiast 2 argumentów |
| 29.06.2026 | `render_run_table(run_id)` czyta z DB, nie z aktywności in-memory | Spójność — to co w bazie, to co user widzi |
| 29.06.2026 | Garmin i Strava na razie tworzą **osobne rekordy** dla tego samego biegu | Auto-deduplikacja w strava_save.py to nice-to-have; nie blokuje workflow |
| 29.06.2026 | `summarizedExerciseSets` jako primary source dla silowni (zamiast `get-workout` per-set) | Prościej, sumaryczne dane wystarczą do trackingu progresji; per-set TODO |
| 29.06.2026 | `gym_log.md` jako auto-generated rendered view (Wzorzec ciężarów = top 90 dni z DB) | Bartek pyta o "aktualny stan" — agregat z bazy jest źródłem prawdy |
| 29.06.2026 | "📋 Skróty zachowań" w CLAUDE.md jako tabela `user pyta → action` | Czytelniejsze niż dotychczasowe bullety, każdy use-case ma skill |
| 29.06.2026 | Body state auto-log po /run i /silownia gdy user wspomina subiektywne | Buduje historię trendów (np. "kolano boli częściej po rowerze niż po biegu") |

---

*Plik aktualizowany w trakcie refaktoru. Edytuj swobodnie — Claude czyta to jako źródło prawdy.*
