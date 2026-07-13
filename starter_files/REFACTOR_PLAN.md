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

## ✅ Faza 9 — Streamlit Cloud deployment (ZROBIONE 30.06.2026)

Dashboard żyje publicznie na Streamlit Cloud z password gate. Mobile dostęp przez "Add to Home Screen" (PWA-like). Workflow daily: skille zapisują lokalnie → `python db/sync.py push` → przycisk "🔄 Odśwież dane" w dashboardzie pulluje fresh z Turso.



**Strategia: pull-on-start zamiast libsql adapter** — `dashboard.py` w cloud-mode wykrywa `TURSO_DATABASE_URL`, pulluje fresh snapshot z Turso (~1MB, <1s) do `data_replica.db` w `/tmp` przez `api.bootstrap_cloud()`, potem reszta kodu czyta z replicy jak z lokalnej sqlite. Powód: libsql nie obsługuje `sqlite3.Row` (zwraca tuple) → próba przepisania `api.py` na libsql wymagałaby patchowania każdego `dict(r)` w dashboardzie i helperach (`recent_with_dynamics` etc.). Pull-on-start = 0 zmian w queries/aiosql/`dict(r)`.

**Zmiany w kodzie (zrobione):**
- `db/init_db.py` — `DB_PATH` honoruje `RUNNING_DB_PATH` env (override dla cloud)
- `db/api.py` — nowa funkcja `bootstrap_cloud(force=False)`: idempotent w obrębie procesu, materializuje schemat + pulluje wszystkie tabele
- `dashboard.py` — bridge `st.secrets → os.environ` (Streamlit Cloud secrets → Python env), `_bootstrap_once()` w `@st.cache_resource`, sidebar pokazuje tryb (☁️ cloud / 💾 local), refresh force-pulluje
- `dashboard.py` — **password gate** (`st.secrets["APP_PASSWORD"]`); brak hasła w secrets = open access (lokalny dev), z hasłem = gate przed renderem
- `requirements.txt` (nowy, root) — `streamlit pandas plotly aiosql libsql python-dotenv`
- `.streamlit/config.toml` (nowy) — dark theme + headless
- `.streamlit/secrets.toml.example` (nowy) — template
- `DEPLOYMENT.md` (nowy) — instrukcja krok-po-kroku
- `.gitignore` — zawężone `.streamlit/secrets.toml` (zamiast całego katalogu, żeby `config.toml` + `.example` weszły do repo)

**Smoke test (zielony):**
- local sqlite: `bootstrap_cloud()` zwraca `None`, queries działają na `db/data.db`
- cloud mode (env z `db/.env`): pull z Turso, `runs=7 gym=2 planned=7`, drugi call idempotent
- `streamlit run dashboard.py` → HTTP 200 lokalnie, password gate skipowany bez `APP_PASSWORD`

**Do zrobienia po stronie usera (manualnie):**
1. Skopiuj zmienione/nowe pliki do `D:\git\running-agent\running-agent\starter_files\`:
   - mod: `db/init_db.py`, `db/api.py`, `dashboard.py`
   - nowe: `requirements.txt`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`, `DEPLOYMENT.md`
2. Commit + push na `main`
3. Streamlit Cloud (`https://share.streamlit.io`): New app → wskaż `starter_files/dashboard.py` → Secrets → wklej `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `APP_PASSWORD` → Deploy
4. PWA na telefonie: otwórz URL → Add to Home Screen

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
✅ Faza 9   Streamlit Cloud deploy + password gate (PWA na telefonie)
```

## 🎯 Kolejny krok — Faza 10: Generator workoutów ze strony (Poziom A)

**Cel:** dodać do dashboardu 5. stronę "💪 Generator workoutów" — formularz, który użytkownik wypełnia na telefonie i ściąga gotowy JSON do importu w Garmin Connect mobile/web. ~2h pracy.

**MVP scope (Poziom A — form → JSON download):**
- Selectbox typu workoutu: Easy / Tempo / Interval / Long / Repetition / Strength
- Inputy zależne od typu (dystans, intensywność, struktura interwałów, lista ćwiczeń siłowych)
- Validation: dla siłowych — kategoria + exerciseName z `templates/Exercises.json` (NIE zgaduj nazw — patrz memory `feedback_garmin_exercise_names.md`)
- Pod spodem `garmin_gen.py` lub nowy generator składający JSON z templates'ów
- Output: `st.download_button("Pobierz JSON", data=json_str, file_name=f"{typ}_{date}.json")`
- Workflow user: na telefonie wypełnia → pobiera JSON do Files (iOS) / Downloads (Android) → otwiera Garmin Connect app → Import workout

**Out of scope (Poziom B, na później):**
- Auto-push do konta Garmin przez API (wymaga auth, session refresh, secrets)
- AI-powered generator z opisu naturalnego (wymaga Claude API key)

**Trade-off accepted:** ręczny krok importu w Garmin Connect (30s) vs. ~6h dodatkowej pracy na Poziom B i utrzymanie sesji.

**Dependencies:** brak — wszystko już w repo (`garmin_gen.py`, `Exercises.json`).

---

## 🎯 Faza 11 — Running-agent MCP (Claude Desktop parity)

**Cel:** Claude Desktop (Mati, telefon/laptop bez Claude Code) ma dziś MCP parity dla *odczytu* (garmin/strava/weather/filesystem/memory), ale **nie może wykonywać Pythona** → brak zapisu do DB, brak regen logów, brak Turso sync. Skille `/run`, `/silownia`, `/dzis` w Desktop działają tylko "na sucho".

**Rozwiązanie:** własny cienki MCP server (**FastMCP**, ~200 linii, `db/mcp_server.py`) wrapujący istniejące `db/api.py` + `scripts/*_save.py`. Zero nowej logiki biznesowej — tylko ekspozycja istniejących funkcji jako MCP tools.

**Zestaw tools (MVP):**
| Tool | Wrapuje | Po co |
|------|---------|-------|
| `save-run` | `garmin_save.save_run()` / `strava_save.save_strava_run()` | `/run` z Desktopu zapisuje do DB |
| `save-gym-session` | `silownia_save.save_strength()` + regen gym_log | `/silownia` z Desktopu |
| `get-today-plan` | `api.planned.today()` + `upcoming()` | `/dzis` bez czytania markdownów |
| `mark-workout-status` | `api.planned.mark_status()` | odhaczanie planu |
| `log-body-state` | `api.body.state_log()` | subiektywne odczucia → DB |
| `weekly-volume` | `api.weekly_volume.recent()` | pytania historyczne bez Stravy |
| `turso-push` | `db/sync.py push` | backup po write |

**Konfiguracja:** wpis w `claude_desktop_config.json` (install.ps1 Step 6 już przygotowany na dopisanie): `python db/mcp_server.py` przez stdio. Wymaga `pip install fastmcp` w requirements.

**Uwaga vs anty-cele:** to NIE jest MCP dla Garmina (etweisberg zostaje) — to MCP dla **własnej bazy projektu**, jedyna brakująca zdolność Desktopu.

**Relacja do Fazy 10:** częściowo ją zastępuje — jeśli Desktop może wywołać `create-workout` (garmin MCP) + zapis do DB (ten MCP), generator na dashboardzie traci priorytet dla Bartka; zostaje wartościowy dla userów mobile-only (form → JSON download bez Claude).

**Estymacja:** ~2-3h (server + test w Desktop + wpis do install.ps1 + README).

---


**Zaktualizowana kolejność (13.07.2026 po fix crash dashboard + task/notes decyzje):**

1. **Faza 17** — Task/Goal/Notes system + strona 'Rozkminy' — ~4h ⭐⭐⭐
2. **Faza 12 MVP** — Telegram bot (read-only + notes/tasks/log) — ~3-4h ⭐⭐
3. **Faza 14** — Garth auth migration — ~4-6h ⭐ (niezależny value: 2-tyg session)
4. **Faza 12.5** — Bot: `/workout upload` (auto-push do Garmina) — ~1h (po Fazie 14)
5. **Faza 11** — Running-agent MCP dla Claude Desktop/mobile — ~2-3h (opcjonalne)
6. **Faza 15/16/13/10/8.5** — nice-to-have niezależne

**Pozostałe opcje (nice-to-have):**
- **Faza 8.5** — skill `/tydzien` (auto-generator tygodniowego planu z `plan_current.md` + body_state + pogoda) — ~1h
- **Faza 10** — Generator workoutów ze strony (Poziom A: form → JSON download) — ~2h (częściowo zastąpione przez `/workout-json` w Fazie 12)
- **Faza 13** — Multi-user (gdy będziesz miał Mati/Jurek/Pychowice RC jako współ-userów) — ~4h
- **Faza 15** — Pogoda (`temperature_c` / `humidity_pct` / `wind_kmh`) w `runs` + backfill z Open-Meteo (sekcja niżej) — ~3-4h
- **Faza 16** — Body Battery + Training Readiness w `runs` (kontekst świeżości przed biegiem) — ~2-3h

Wszystkie niezależne. Codzienna rutyna projektu jest w pełni działająca.

---

## 🎯 Faza 12 — Telegram bot (mobile native)

**Cel:** dać Bartkowi dostęp do systemu z telefonu bez potrzeby otwierania Claude Code / dashboardu. Push notyfikacja rano z `/today`, quick body logging w chwili zdarzenia, notatki/taski w każdej chwili. **Decyzja architektoniczna 13.07.2026:** bot pisze BEZPOŚREDNIO do Turso (libsql client), NIE ma lokalnego SQLite — stateless deploy.

**Decyzja UX 13.07.2026:** bez auto-push komentarza po biegu — tylko `/lastrun` on-demand. To upraszcza deploy (bot bez crona, bez Garmin auth po stronie serwera).

**Hosting:** Fly.io free tier (256MB RAM) lub Railway. Alternatywa: Raspberry Pi w domu jeśli chcesz self-host.

**Auth:** Telegram Bot API token + whitelist Twojego user_id w env vars serwera. Zero OAuth.

**Zakres MVP (~3-4h):**

Struktura: `bot/bot.py` (main), `bot/handlers/*.py` (per komenda), `bot/config.py` (env), `bot/db.py` (thin wrapper na `db/api.py` z libsql zamiast sqlite).

**Komendy read-only (bez zależności):**
| Komenda | Co robi | Wywołuje |
|---------|---------|----------|
| `/today` | Dzisiejszy plan | `api.planned.today()` |
| `/tomorrow` | Jutrzejszy plan | `api.planned.upcoming(days='+1 days')` |
| `/week` | Cały tydzień z statusami | `api.planned.current_week()` |
| `/lastrun` | Analiza ostatniego biegu (pace, HR, GCT, kadencja, coach comment) | `api.runs.recent(limit=1)` + reuse logic z `/run` skill |
| `/lastgym` | Ostatnia siłownia | `api.gym.sessions_recent(limit=1)` |

**Komendy write (wymaga Fazy 17 dla notes/tasks):**
| Komenda | Co robi | Wywołuje |
|---------|---------|----------|
| `/log kolano 2 [notatka]` | body_state pain=2 | `api.body.state_log()` |
| `/n insight/decision/idea X` | Nowa notatka | `api.notes.add()` (Faza 17) |
| `/n reminder X` | Nowy task (bo reminder = todo) | `api.tasks.add()` (Faza 17) |
| `/tasks` | Pokaż todo tasks | `api.tasks.list(status='todo')` (Faza 17) |
| `/goals` | Cel tygodnia + status | `api.goals.current_week()` (Faza 17) |
| `/goal sport zbudować kadencję 172` | Ustaw goal | `api.goals.add()` (Faza 17) |

**Komenda workout:**
| Komenda | Co robi | Wymaga |
|---------|---------|--------|
| `/workout silownia_a` | Generuj JSON + wyślij plik | – |
| `/workout silownia_a upload` | Generuj + wgraj do Garmina + zaplanuj | **Faza 14** (garth) |

**Push notyfikacje:**
- **Auto rano 7:00** — codzienny `/today` (cron w bocie, systemd timer albo Fly.io scheduled job)
- **Custom** — na żądanie w kolejnych rozszerzeniach

**Smart chat (regex-based, bez LLM):**
Bot rozpoznaje wzorce naturalne bez LLM:
- `kolano 2/10 klika przy schodach` → body_state z parsingiem
- `przypomnij mi jutro X` → task z due_date=tomorrow
- `dziś: X` → notatka category=insight
Odpowiada `[tak/nie]` przed zapisem.

**Estymacja:** ~3-4h (bot + 15 komend + Fly.io deploy + Telegram Bot API setup).

**Powiązania z innymi fazami:**
- **Wymaga Fazy 17** dla notes/tasks/goals komend
- **Nie wymaga Fazy 14** (bo bez auto push komentarza, bez auto upload do Garmina)
- **Faza 12.5** (auto upload workout) dopiero po Fazie 14 — trywialne dodanie 1 komendy

---

---

## 🎯 Faza 17 — Task/Goal/Notes system + strona 'Rozkminy'

**Cel:** Bartek 13.07.2026: *"życie i trening to jedno, a jednak potrzebuję takich rozkmin — trzeba dodać coś takiego"*. Dashboard obecnie pokrywa **tylko sport**. Bartek jest bezrobotny (długotrwale) + ma aktywne rekrutacje + narzuca sobie sam porządek dnia → potrzebuje integracji z życiową częścią (weekly goals, taski hierarchiczne, notatki z rozmów).

**Decyzja architektoniczna (13.07.2026):** **niezależny system w naszej DB**, NIE integracja z Microsoft TODO. Powód: MS Graph OAuth per-user, bidirectional sync = konflikty, brak kontekstu do reszty DB (body_state/runs/planned). Kompromis: możliwy jednokierunkowy export DB → MS TODO w Fazie 17.5, jeśli zajdzie potrzeba.

**Schema (3 nowe tabele):**

```sql
-- Zadania z hierarchią (task bez parent_id = "projekt")
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    title TEXT NOT NULL,                -- SPECIFIC
    description TEXT,                    -- kontekst, opis "jak"
    success_criteria TEXT,               -- MEASURABLE (jak poznam że skończone)
    category TEXT NOT NULL,              -- 'sport' | 'praca' | 'dom' | 'relacje' | 'zdrowie' | 'inne'
    status TEXT DEFAULT 'todo',          -- 'todo' | 'in_progress' | 'done' | 'cancelled' | 'blocked'
    priority INTEGER DEFAULT 3,          -- 1 (must) - 5 (whatever)
    due_date DATE,                       -- TIME-BOUND (null = anytime)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    notes TEXT
);

-- Cel tygodnia (jeden per kategoria per tydzień)
CREATE TABLE weekly_goals (
    id INTEGER PRIMARY KEY,
    week_start DATE NOT NULL,            -- Monday
    category TEXT NOT NULL,              -- 'sport' | 'praca' | 'dom' | 'relacje' | 'zdrowie'
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'planned',       -- 'planned' | 'done' | 'partial' | 'missed'
    outcome_notes TEXT,                  -- wypełniane w /weekly-review
    UNIQUE(week_start, category)
);

-- Notatki "ważne z rozmów" (Claude sam wrzuca via skille)
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    date DATE DEFAULT (date('now')),
    category TEXT,                       -- 'insight' | 'decision' | 'reminder' | 'idea'
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT,                           -- CSV, wyszukiwalne
    source TEXT,                         -- 'claude:/run' | 'user' | 'claude:/plan-week'
    read INTEGER DEFAULT 0
);
```

**Task bez `parent_id` = projekt.** Filtr `parent_id IS NULL` zwraca projekty top-level.

**Zakres pracy (Faza 17):**
1. Schema migration w `db/init_db.py` + `db/migrate.py`
2. Queries w `db/queries/tasks.sql`, `goals.sql`, `notes.sql` (aiosql)
3. API w `db/api.py`: `api.tasks.add/list/update/delete`, `api.goals.*`, `api.notes.*`
4. Nowa strona Streamlit `page_life()` — hierarchiczny widok tasków, weekly goals na górze, notatki tygodnia
5. CRUD z UI: dodaj/edytuj/usuń task, zmień status, dodaj sub-task
6. Integracja z `/weekly-review` skill: pokaż co się udało/nie z zeszłego tygodnia
7. CLAUDE.md sekcja "kiedy Claude automatycznie dodaje do notes/tasks":
   - **insight** — obserwacja o ciele/technice/planie (np. "prehab W1 aktywacja OK")
   - **decision** — decyzja o zmianie planu (np. "RDL 50→40 kg zbyt zachowawcze, wracamy")
   - **reminder** — coś do zrobienia (→ tasks)
   - **idea** — pomysł na przyszłość (→ notes)
8. Turso migration + push preset `--after=life`

**Powiązane memory:**
- `project-dashboard-life-notes` (priorytet WYSOKI)
- `project-dashboard-plan-granulacja` (granulacja tabeli planu)

**Estymacja:** ~4h (schema+API 1h, UI 2h, integracja z skill+CLAUDE.md 1h).

**Relacja do Fazy 12 (Telegram bot):** bot zyskuje komendy `/task X` (add), `/notatka Y` (add), `/goals` (show weekly). Bez Fazy 17 bot nie ma sensu w kontekście życiowym.

---

## 🎯 Faza 14 — Garmin auth: garth zamiast Playwright

**Cel:** wyeliminować zależność od przeglądarki (Playwright) w loginie do Garmina. Obecnie `mcp__garmin__garmin-login` odpala izolowany Chromium → user wpisuje hasło ręcznie → cookies eksportowane do `~/.garmin-connect-mcp/session.json`. Sesja pada po kilku godzinach → cały flow od nowa.

**Rozwiązanie:** natywny OAuth login przez bibliotekę **`garth`** (Python) — programmatic username/password → OAuth1 + OAuth2 tokens → refresh token żyje **tygodniami**, zero browsera.

**Root cause obecnego bólu:**
- `etweisberg/garmin-connect-mcp` używa Playwright do obejścia Cloudflare TLS fingerprinting (decyzja z 29.06.2026)
- Query-endpointy już działają jako plain HTTP (używają wyciągniętych cookies) — auth to jedyny puzzle wymagający browsera
- Faktycznie: `garth` też radzi sobie z Cloudflare (używa `curl_cffi` pod maską, TLS impersonation Chrome)

**Zakres pracy:**
1. **Fork `etweisberg/garmin-connect-mcp`** (lub kontrybucja upstream jeśli maintainer zechce)
2. **Patch `src/lib/garmin-auth.ts`** — zamiast Playwright wywołuje shell subprocess do Python skryptu z `garth`
3. **`scripts/garmin_login.py`** — nowy, korzysta z `garth.Client()`, przyjmuje `--email` / `--password` (lub prompts interaktywnie), zapisuje session do tego samego pliku `~/.garmin-connect-mcp/session.json` w formacie kompatybilnym z resztą MCP
4. **`scripts/garmin_refresh.py`** — check-session sprawdza expiry i wywołuje refresh gdy potrzeba (garth to obsługuje)
5. **CLAUDE.md update** — sekcja "Garmin session expire" opisuje nowy flow: pierwszy raz login, potem tygodnie ciszy

**Trade-offs:**
- ✅ Zero interakcji browserem, sesja tygodniowa
- ✅ Można trzymać hasło w `~/.garmin-connect-mcp/.env` (gitignored) — lub prompt raz przy setup
- ❌ **2FA/MFA edge case**: gdy Garmin wymusi 2FA (nowe urządzenie, nietypowe IP), garth potrzebuje interactive prompt na OTP. W praktyce rzadkie (~1× / 3 miesiące)
- ❌ Node MCP musi umieć spawnować Python (Node → subprocess → Python) — dodatkowa ruchoma część vs. natywnie Node

**Dependencies:** `pip install garth` (~200KB, MIT).

**Estymacja:** ~4-6h (fork + patch + Python scripts + test + PR/dokumentacja).

**Relacja do Fazy 11:** Faza 11 (running-agent MCP) używa istniejącego Garmin MCP jako read-only backend. Faza 14 wymienia auth pod spodem — Faza 11 działa niezależnie, ale skorzysta z niezawodniejszej sesji.

---

## 🎯 Faza 15 — Pogoda w runs + backfill

**Cel:** dodać warunki pogodowe do rekordów biegowych żeby wykresy HR-vs-pace przestały mieszać "regres formy" z "gorący dzień". Bez pogody: bieg 5:44/km z HR 130 (11.06, chłodno) vs 5:43/km z HR 141 (08.07, upał) wygląda jak fitness regression — z pogodą widać, że różnica to +11 bpm z powodu +10°C, a forma stoi.

**Nowe kolumny w `runs`:**
- `temperature_c REAL` — średnia temperatura biegu
- `humidity_pct INTEGER` — średnia wilgotność
- `wind_kmh REAL` — średnia prędkość wiatru
- `weather_source TEXT` — `'garmin'` | `'strava'` | `'openmeteo'` (żeby wiedzieć jak wiarygodne)

**Źródła danych (priority):**
1. **Garmin** — `mcp__garmin__get-activity-weather` (per activity) → daje `temp`, `humidity`, `wind` dla biegów Garmin. Wywołanie tylko dla `source='garmin'` biegów.
2. **Strava** — `average_temp` w `details` (gdy zegarek ma czujnik). Historycznie prawdopodobnie puste; można olać.
3. **Open-Meteo `weather_archive`** (fallback dla wszystkich) — jeśli mamy `start_lat`/`start_lng` + `start_time`, fetch pogody historycznej z archiwum. Dokładny (~1h resolution).

**Zakres pracy:**
1. **Schema** — `ALTER TABLE runs ADD COLUMN temperature_c REAL / humidity_pct INTEGER / wind_kmh REAL / weather_source TEXT`, update `schema.sql`, ALTER na Turso
2. **Queries** — `run_upsert_garmin` + `run_upsert_strava` przyjmują nowe kolumny
3. **Save scripts** — `garmin_save.py` (opcjonalnie fetchuje `get-activity-weather` przy save; można też lazy w backfill), `strava_save.py` (parsuje `average_temp`)
4. **Backfill script** `scripts/backfill_weather.py`:
   - Dla każdego `run` bez `temperature_c`:
     - Jeśli Garmin: fetch `get-activity-weather` (per aid, ~200ms)
     - Fallback: fetch Open-Meteo `weather_archive` (potrzebne start_lat/lng — z `run_laps.startLatitude` pierwszego lapa albo z `raw_json`)
   - Rate limit: 1 req / 2s dla Open-Meteo (ich free tier tolerance)
5. **Dashboard**:
   - Karta Bieganie: nowy filtr "Temperatura (od-do)" nad wykresami
   - HR-vs-pace scatter kolorowany po temperaturze (color scale niebieski→czerwony)
   - Panel "warunki dnia" w tabeli ostatnich biegów: kolumna `🌡️ °C / 💧 % / 💨 km/h`

**Trade-offs:**
- ✅ Faktyczna analiza formy (odseparowana od pogody) — pierwszy krok do "HR-drift over time at constant conditions"
- ✅ Backfill jednorazowy — potem każdy nowy save już auto-fetchuje
- ❌ Open-Meteo trzymają ~2 lata historii — dla starszych biegów może brakować dokładności
- ❌ Garmin `get-activity-weather` czasem zwraca null (bez GPS w budynku, treadmill etc.) — trzeba obsłużyć

**Dependencies:** brak — `mcp__weather__weather_archive` już jest w MCP stack, Garmin MCP już jest.

**Estymacja:** ~3-4h (schema + queries + save + backfill 69 biegów + dashboard filtry).

**Relacja do innych faz:**
- Faza 8.5 (skill `/tydzien`) mogłaby pobierać prognozę → decyzja o intensywności (upał → skróć)
- Faza 5 (dashboard) — obecny wykres HR vs pace stanie się znacznie bardziej użyteczny

---

## 🎯 Faza 16 — Body Battery + Training Readiness w runs

**Cel:** dodać kontekst świeżości do rekordów biegowych — z jakim zapasem energii wchodziłeś w trening i co Garmin sugerował rano. Razem z Fazą 15 (pogoda) i istniejącymi metrykami (HR, tempo, dynamika) — pełny obraz dlaczego bieg wyglądał jak wyglądał.

**Motywacja (przykład):**
- Bieg z BB start 85 + Training Readiness 78 rano → HR 130 przy 5:44 = normalne dla świeżego
- Bieg z BB start 45 + TR 30 → HR 141 przy 5:43 = **oczywiste** że nogi/serce zmęczone, nie regres formy
- Bez tych danych: interpretujesz każde odchylenie jako fitness change

**Nowe kolumny w `runs`:**
- `body_battery_start INTEGER` — 0-100, BB w momencie startu biegu ⚠️ **już jest w schemacie** (Faza 2d), tylko niewypełnione
- `body_battery_end INTEGER` — 0-100, BB tuż po biegu (`current - drain during run`) ⚠️ **też już jest**
- `body_battery_drain INTEGER` (nowa) — computed: start - end, ile "spaliło"
- `training_readiness_start INTEGER` — 0-100, score rano tego dnia (NOWA kolumna)
- `training_readiness_level TEXT` — Garminowa etykieta: `PRIME`, `HIGH`, `MODERATE`, `LOW`, `POOR`

**Źródła danych:**
1. **Body Battery** — `mcp__garmin__get-body-battery` (per day) → zwraca timeline `[{timestamp, level}, ...]` co ~3 min. Wystarczy dopasować `run.start_time` do najbliższego samplea → `body_battery_start`. Podobnie po biegu → `body_battery_end`.
2. **Training Readiness** — `mcp__garmin__get-training-readiness` (per day) → snapshot dziennego score'u rano. Fetch dla daty biegu.

**Zakres pracy:**
1. **Schema** — dodać `body_battery_drain INTEGER`, `training_readiness_start INTEGER`, `training_readiness_level TEXT`. Update `schema.sql`. ALTER na Turso.
2. **Queries** — `run_upsert_garmin` przyjmuje nowe kolumny (Strava nie ma tych danych — zostaje NULL).
3. **`garmin_save.py`** — po INSERT biegu wywołaj `_fetch_bb_snapshot(start_time)` + `_fetch_training_readiness(date)`, UPDATE runsa. Async, po głównym save żeby nie blokował.
4. **Backfill script** `scripts/backfill_freshness.py`:
   - Dla każdego Garmin runa: fetch BB timeline dnia + TR score rano
   - Rate limit: ~1 fetch/s (Garmin tolerance)
   - ~40 Garmin biegów × 2 fetch = ~80 API calls, ~2 min
5. **Dashboard:**
   - Karta Bieganie: kolumna `🔋 BB start / drain` + `💪 Ready` w tabeli
   - Scatter: BB_start vs HR_avg (kolor = TR level) — pokazuje "wchodziłem świeży a HR wysokie? → coś się dzieje"
   - Timeline: `training_readiness_start` na osi X (data), Twój planned type jako kolor — widać czy nie robisz Tempo gdy TR=LOW

**Trade-offs:**
- ✅ Faktyczna interpretacja HR: "wysokie HR bo zmęczony", nie "spadek formy"
- ✅ Backfill jednorazowy przez tydzień
- ✅ Kolumny BB już w schemacie (część roboty zrobiona 2 tyg temu)
- ❌ Training Readiness działa tylko na wybranych zegarkach Garmin (Fenix 6+, Forerunner 245+ w niektórych regionach). Musisz sprawdzić czy Twój generuje.
- ❌ BB timeline też nie zawsze pełny (jak zegarek na ładowaniu → braki) — trzeba obsłużyć NULL

**Dependencies:** brak — `mcp__garmin__get-body-battery` i `mcp__garmin__get-training-readiness` już w MCP stack (dodane do allowlisty dzisiaj).

**Estymacja:** ~2-3h (schema 2 kolumny, save script fetch, backfill, dashboard 1 wykres + kolumny).

**Relacja do innych faz:**
- **Faza 15** (pogoda) — komplementarne. Razem: "wysokie HR bo zmęczony **i** ciepło", nie jedno albo drugie.
- Faza 8.5 (skill `/tydzien`) — mogłaby brać TR score rano → dynamicznie modyfikować intensywność planu

---

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
| 30.06.2026 | Streamlit Cloud: pull-on-start zamiast libsql adapter | libsql nie obsługuje sqlite3.Row → adapter wymagałby patchowania każdego `dict(r)` w dashboard + helperach; pull ~1MB <1s, zerowy refactor queries |
| 30.06.2026 | Password gate przez `st.secrets["APP_PASSWORD"]` (nie OAuth) | MVP — 10 linii kodu, brak setupu Google/GitHub login; gdy będzie multi-user (Faza 12), przejdziemy na proper auth |
| 30.06.2026 | Generator workoutów: Poziom A (form → JSON download) zamiast Poziom B (auto-push do Garmin) | A: 2h pracy, zero auth; B: 6h + utrzymanie sesji/cookies. Ręczny import w Garmin Connect mobile = 30s. Migrujemy do B gdy A się sprawdzi codziennie |
| 06.07.2026 | Faza 11: własny running-agent MCP (FastMCP wrapping db/api.py) dla Claude Desktop | Desktop ma MCP parity dla odczytu, ale nie wykonuje Pythona → bez tego brak zapisu do DB / Turso sync. ~200 linii, zero nowej logiki. Nie łamie anty-celu "nie piszemy MCP dla Garmina" — to MCP dla własnej bazy |
| 08.07.2026 | Faza 14: `garth` zamiast Playwright do Garmin auth | Playwright login = izolowany Chromium, hasło ręcznie, sesja pada po godzinach. `garth` robi natywny OAuth (curl_cffi bije Cloudflare), refresh token żyje tygodniami, zero browsera. 2FA edge case akceptowalny (~1×/3mc). Fork etweisberg-mcp lub PR upstream. |
| 09.07.2026 | Faza 15: pogoda (`temperature_c` / `humidity` / `wind`) w `runs` + backfill Open-Meteo | Bez pogody wykres HR-vs-pace miesza "regres formy" z "gorący dzień". Bezpośredni trigger: 11.06 vs 08.07 przy tym samym tempie 5:44/km — HR 130 vs 141 (+11 bpm), różnica wygląda jak spadek formy, ale to prawdopodobnie różnica ~10°C. Sources: Garmin `get-activity-weather` (primary) → Open-Meteo `weather_archive` (fallback). |
| 09.07.2026 | Faza 16: Body Battery + Training Readiness w `runs` | Kolumny BB już w schemacie (Faza 2d) ale niewypełnione. Dodać `training_readiness_start` + fetch przy save (BB timeline + TR score dnia). Razem z Fazą 15 daje pełny obraz "co wpłynęło na HR" — pogoda + zmęczenie. Training Readiness > Body Battery bo purpose-built + breakdown WHY (recovery / HRV / sleep / load / stress). |

---

*Plik aktualizowany w trakcie refaktoru. Edytuj swobodnie — Claude czyta to jako źródło prawdy.*
