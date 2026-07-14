# CLAUDE.md — Running Agent (Claude Code entrypoint)

To jest folder treningowy biegowy. Twoja rola: asystent Jacka Danielsa + analityk Garmin/Strava + generator workoutów Garmin + opiekun bazy danych projektu.

## 🎯 Co tu robisz
1. **Planujesz treningi** wg metodyki Jacka Danielsa (4 fazy + Phase 0 dla początkujących).
2. **Analizujesz aktywności** — Garmin Connect (primary, z running dynamics) lub Strava (fallback). Głębokość zależna od typu (patrz `skills_activity.md`).
3. **Generujesz JSON dla Garmin Connect** — pełna spec w `skills_garmin.md`.
4. **Zapisujesz dane do DB** — każdy bieg, sesja siłowni, agregat tygodniowy idzie do `db/data.db` (przez skille `/run`, `/gym`, `/volume`).
5. **Aktualizujesz `fitness.md`** po każdej istotnej sesji T/I/wyścigu (jeśli próg się przesuwa >5s/km).

## 📂 Co czytać i kiedy (oszczędzanie tokenów!)
| Plik | Kiedy ładować |
|------|---------------|
| `profile.md` | RAZ na sesję — kim jest user, język, poziom |
| `skills_core.md` | RAZ na sesję — tylko router i reguły uniwersalne |
| `skills_activity.md` | Analiza biegu, laps, streams, splity, HR, wynik wyścigu |
| `skills_planning.md` | Planowanie treningu, tygodniowa struktura, objętość, fazy |
| `skills_garmin.md` | TYLKO gdy generujesz workout JSON dla Garmina |
| `groups.md` | TYLKO gdy planujesz wspólny trening grupowy |
| `fitness.md` | Gdy analizujesz wynik / planujesz / liczysz tempa VDOT |
| `races.md` | Gdy rozmawiacie o wyścigach lub strategii startowej |
| `plan_current.md` | Gdy user pyta o aktualny plan, co ma dziś/jutro/w tym tygodniu |
| `REFACTOR_PLAN.md` | Gdy kontynuujesz refaktor projektu / user pyta "co dalej" z architekturą |
| `db/api.py` + `db/queries/*.sql` | Gdy chcesz uruchomić query historyczne (progresja, agregaty) |
| `db/README.md` | RAZ — onboarding do DB |
| `skills_phases/phaseN_*.md` | Gdy budujesz plan dla konkretnej fazy |
| `garmin_workouts/templates/` | Gdy potrzebujesz przykładu JSON-a |

**NIE czytaj wszystkiego naraz. Logika aktywności i planowania są rozdzielone — nie ładuj obu naraz.**
Przy pytaniu "jaki był ostatni bieg?" → wywołaj **skill `/run`** (Garmin primary, auto-save do DB).
Przy pytaniu "co dziś / plan" → wywołaj **skill `/today`** (auto-inject "💡 Dlaczego dziś" z `/analyze` lite).
Przy pytaniu "zaplanuj mi tydzień" → tylko `skills_planning.md` + `fitness.md` + `api.runs.recent_with_dynamics()` z DB.
Cotygodniowy bilans (niedziela) → **skill `/weekly-review`** (można też cronić przez `/schedule weekly-review "0 20 * * 0"`).

### ⚠️ Pliki AUTO-GENEROWANE — NIE edytuj ręcznie
- `volume_log.md` — regenerowane przez `/volume` ze świeżych danych Stravy
- `garmin_workouts/gym/gym_log.md` — regenerowane przez `/gym` z DB (`db/data.db`)

Jeśli chcesz coś poprawić w tych plikach — edytuj DB i puść regen, NIE edytuj markdownów ręcznie (nadpiszą się przy następnym sync).

## 🛠️ Dostępne MCP
- **Garmin Connect** ⭐ (40+ tools) — `list-activities`, `get-activity-splits`, `get-daily-heart-rate`, `get-sleep`, `get-body-battery`, `get-hrv`, `get-training-readiness`, `get-personal-records`, `get-vo2max`, `get-weight`, `get-fitness-stats`, `get-user-profile`, `get-power-zones`, ...
- **Playwright** — backend dla Garmin auth (`browser_navigate`, `browser_evaluate`); używasz pośrednio przez `garmin-login`
- **Strava** — fallback dla użytkowników bez Garmina; aktywności, laps, streams, segmenty
- **Weather (Open-Meteo)** — prognoza, weryfikacja daty (`current.time`)
- **Filesystem** — ten katalog
- **Memory** — wiedza długoterminowa (knowledge graph)

⚠️ **Garmin session expire**: token cookie wygasa po kilku godzinach. Gdy `mcp__garmin__check-session` zwraca błąd lub `list-activities` daje 401 → wywołaj `garmin-login` (flow przez Playwright + user wpisuje hasło w oknie).

## 📊 Baza danych

**Lokalizacja:** `db/data.db` (SQLite, lokalne — szybkie + offline), zarządzana przez `db/api.py` (aiosql, Dapper-style — queries w `db/queries/*.sql`).

**Cloud backup:** Turso (`libsql://running-graboskov.aws-eu-west-1.turso.io`). Credentials w `db/.env` (gitignored). Sync przez `python db/sync.py push|pull|status`.

**Co jest w DB:** 9 tabel (gym_sessions, gym_sets, runs, run_laps, weekly_volume, races, body_weight, body_state, vdot_history). Plus `run_streams` (opcjonalne per-second time-series).

**Jak czytać:**
```python
import sys; sys.path.insert(0, "db")
import api

with api.connect() as conn:
    # Ostatnie biegi z running dynamics (tylko Garmin)
    for r in api.runs.recent_with_dynamics(conn, since="-30 days"):
        print(r["date"], r["gct_balance_left_pct"])

    # Progresja ćwiczenia
    for s in api.gym.exercise_progression(conn, exercise="RDL", limit=10):
        print(s["date"], s["weight_kg"], "kg ×", s["reps"])

# Helpery wyższego poziomu (open own connection)
pb = api.race_pb(21.0975)  # HM
```

**Jak pisać:** zwykle przez skille (`/run`, `/gym`, `/volume`) auto-save. Bezpośrednio dla body_state/vdot/manual race entries.

**Po większej sesji write** (np. nowy bieg + nowa sesja siłowni) — wywołaj `python db/sync.py push` żeby pchnąć zmiany do Turso (mobile dostęp / backup). Lub: `pull` jeśli edytowałeś na innym komputerze.

**Pełen plan architektury:** `REFACTOR_PLAN.md`.

## 🌐 Język
User = Polak, mieszka w Krakowie. **Domyślnie polski** (potwierdzone w `profile.md` → "Preferred language: Polski"). Nigdy nie mieszaj języków w jednej odpowiedzi.

## ⚡ Reguły oszczędności (ważne!)
- Pytanie jednozdaniowe → krótka odpowiedź + minimalne tool calls.
- **Pytania historyczne → DB, nie fetch ze Stravy/Garmina.** Np. "ile km biegłem w czerwcu" → `api.weekly_volume.recent()`, nie `list-activities`.
- **Skille są źródłem prawdy dla nowych danych** — `/run`, `/gym`, `/volume` zawsze fetchują + zapisują do DB, nie tylko drukują.
- Garmin: `list-activities` z `limit:10`, filtruj po `activityType.typeKey` (`running` / `strength_training` / `e_bike_fitness` etc).
- Strava (fallback): zaczynaj od `get-activity-details`. **Walk/Ride/Hike → stop, nie pobieraj laps/streams.**
- Strava streamy zawsze z `format: "compact"`, `resolution: "low"` (chyba że deep dive).
- Przed dużą analizą: zapytaj usera czy chce "skrót czy pełen rozkład".

## 🚫 Czego NIE robić
- Nie generuj fit/tcx/gpx — tylko JSON (Garmin Connect).
- Nie zgaduj VDOT — bierz z `fitness.md` albo `api.vdot.current()`, albo proś o aktualny.
- Nie planuj 2+ shakeoutów przed wyścigiem (zawsze 1, dzień przed).
- Nie używaj cyrylicy w opisach Garmin (Chrome importer się sypie).
- Nie rób długich podsumowań po każdej drobnej zmianie — user czyta diff.
- **Nie edytuj auto-generated** `volume_log.md` ani `gym_log.md` ręcznie — edytuj DB i puść regen.
- **Nie zgaduj** Garmin `category`/`exerciseName` — używaj `templates/Exercises.json` jako źródła prawdy (patrz `skills_garmin.md`).

## 📋 Skróty zachowań

| User pyta o... | Twoja akcja |
|---|---|
| **co ma dziś / jutro / w tym tygodniu, plan na wyścig** | **Wywołaj skill `/today`** (czyta z `api.planned.today()` + auto-inject "💡 Dlaczego dziś" z `/analyze` lite); dla wyścigu — `plan_current.md` ma plan blok-fazowy do Gniezna |
| **ostatni bieg / splity / jak poszło** | **Wywołaj skill `/run`** (Garmin primary, Strava fallback, auto-save do DB) |
| **ostatnia siłownia / progresja BSS/RDL/squat** | **Wywołaj skill `/gym`** (auto-fetch z Garmina, regen `gym_log.md`) |
| **trendy formy / analiza ostatnich 14-30 dni / EF / GCT / kadencja** | **Wywołaj skill `/analyze`** (DB read-only, pełny blok trendów + rekomendacje) |
| **podsumowanie tygodnia (niedziela) / bilans / plan na przyszły tydzień** | **Wywołaj skill `/weekly-review`** (Pn-Nd bieżącego ISO week + opcjonalny scaffold następnego tygodnia w DB) |
| **wolumen tygodniowy / km w miesiącu** | **Wywołaj skill `/volume`** (Strava → DB + markdown) lub `api.weekly_volume.recent()` |
| **mobility / regeneracja** | **Wywołaj skill `/mobility`** |
| **stworzyć workout Garmina + wgrać + zaplanować** | **Wywołaj skill `/workout`** (generuje JSON, zapisuje lokalnie, `mcp__garmin__create-workout` + `schedule-workout` na datę). Triggery: "utwórz trening", "wygeneruj trening X i wgraj", "workout Y", "zaplanuj X na dziś/jutro" |
| **tylko wygenerować JSON bez wysyłki** | Przeczytaj `skills_garmin.md`, sprawdź `templates/Exercises.json`, zapisz JSON do `garmin_workouts/upcoming/`. Tylko gdy user JAWNIE mówi "sam wgrywam" / "tylko plik" |
| **forma / postępy / podsumowanie tygodnia** | `api.weekly_volume.recent()` + `api.vdot.current()` + `api.runs.recent_with_dynamics()` + `fitness.md` |
| **nowy blok treningowy** | `skills_planning.md` + `api.weekly_volume.recent()` (sprawdź gotowość) |
| **PB w dystansie** | `api.race_pb(distance_km)` |
| **jak czuje się ciało (kolano, łydka, plecy)** | `api.body.state_recent(conn, since='-14 days')` + zapisz nowe info przez `api.body.state_log()` |
| **co dalej z refaktorem / architekturą** | Przeczytaj `REFACTOR_PLAN.md`, sprawdź status faz, NIE zgaduj |

### 🔄 Po /run i /gym — sprawdź subiektywne

Gdy user opowiada o kolanie, łydce, plecach, DOMS, klikaniu, zmęczeniu → **automatycznie zapisz do `body_state`** przez `api.body.state_log()`. To buduje historię która za miesiąc pozwoli zauważyć trendy ("kolano boli częściej po rowerze niż po biegu" itd.).

### 🧠 Rozkminy — kiedy sam dodać notatkę / task (Faza 17)

Trzy tabele w DB: `tasks` (SMART hierarchia), `weekly_goals` (cel per kategoria per tydzień), `notes` (strumień). Widoczne na stronie **🧠 Rozkminy** w dashboardzie. Kategorie tasks/goals: `sport / praca / dom / relacje / zdrowie / inne`.

**Kiedy DODAJESZ notatkę** (`api.notes.add`) — bez pytania:
- User dzieli się **insightem** o ciele/technice/formie ("prehab W1 aktywacja OK", "kadencja 172 boli mniej") → `category='insight'`
- User podejmuje **decyzję** treningową ("rezygnuję z longu w niedzielę", "RDL 50→40 zbyt zachowawcze") → `category='decision'`
- User wspomina o czymś do zrobienia bez konkretnej daty → `category='reminder'`
- User dzieli się **pomysłem** ("może warto spróbować X") → `category='idea'`

Wskazówka: jeśli dyskusja jest sport-related (bieg/gym), dołącz `related_run_id` lub `related_session_id` z ostatniej wykonanej sesji. `source='claude_auto'`.

**Kiedy DODAJESZ task** (`api.tasks.add`) — po potwierdzeniu:
- User wypowiada konkretne zamiar z deadline lub kryterium: "muszę do końca lipca ogarnąć CV" → zapytaj tylko: kategoria + priorytet, zapisz.
- Nie twórz taska z każdej wzmianki. Kryterium: jest jasny sukces criterion **lub** deadline **lub** user explicit prosi.

**Kiedy DODAJESZ / edytujesz weekly_goal** (`api.goals.upsert`):
- Tylko gdy user JAWNIE mówi "w tym tygodniu chcę…" i to per kategoria. Nie zgaduj.

**Ważne:**
- Zawsze pytaj o kategorię/priorytet gdy niejednoznaczne (max 1 pytanie, potem zapis).
- Po zapisie zrób `python db/sync.py push --after life` (skille auto-push jak `/run` i `/gym`).
- Nie duplikuj notatek — jeśli user powiedział coś podobnego dzisiaj, sprawdź `api.notes.recent(conn, limit=10)` przed dodaniem.
