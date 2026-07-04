Utwórz workout Garmina (running lub strength), **wgraj przez MCP** i **zaplanuj na datę**.

Ten skill triggeruje się gdy user prosi o **stworzenie treningu i wysłanie na Garmina**. Rozpoznawaj dowolne słownictwo:
- "utwórz trening", "wygeneruj trening", "workout", "zrób workout"
- "wgraj na garmina", "wyślij do garmina", "send-to-garmin"
- "zaplanuj X na dziś/jutro/sobotę"

**Domyślne zachowanie: generuj → zapisz lokalnie → wgraj do Garmin Connect → zaplanuj na datę.**

---

## KROK 1 — Wygeneruj JSON

### 1A. Running workout (sportTypeId=1)

Załaduj `skills_garmin.md` (jeśli nie w kontekście). Zbuduj JSON zgodnie ze specem:
- Warmup (time-based lub lap.button)
- Interval(y) z pace.zone lub HR zone
- Repeat groups jeśli intervały
- Cooldown lap.button

Bazuj tempo na `fitness.md` (VDOT current) + kontekście planu z `plan_current.md`.

### 1B. Strength workout (sportTypeId=5)

Załaduj `skills_gym.md` (jeśli nie w kontekście). **Krytyczne reguły**:
- `estimatedDistanceInMeters=0` (nie null)
- Kategorie tylko z 47-listy w `templates/Exercises.json` (parse!)
- `exerciseName` z Exercises.json lub `""`
- **Two-sided exercises**: parzysta liczba serii lub obie strony w 1 stepie (verified 03.07.2026)
- Weight signaling: 3 zgodne miejsca (name bez DUMBBELL_, weight=0, "WAGA: BEZ OBCIAZENIA" w 1. linii description)
- Repeat z 1 iter = odrzucenie

### Wspólne

- **Sprawdź kontuzje/preferencje z `body_state`** za ostatnie 14 dni (`api.body.state_recent`). Modyfikuj plan pod aktualny stan (kolano, hamstring, asymetria).
- **Nazwa workout**: `YYYY.MM.DD Nazwa_Pace_Dystans` (np. `2026.07.04 Long_14km_@6:00-6:15`)
- **Nazwa pliku**: `YYYY.MM.DD_Type_Detail.json` (np. `2026.07.04_Long_14km_600-615.json`)
- **ASCII-only** (Chrome importer nadal bugowałby, ale i MCP bezpieczniej z ASCII). Save przez `make_garmin.save_workout()`.

---

## KROK 2 — Zapisz lokalnie (backup + wersjonowanie)

**Zawsze** zapisz JSON do `garmin_workouts/upcoming/YYYY.MM.DD_Type_Detail.json` przez `make_garmin.save_workout()`. Nawet gdyby MCP fail — mamy plik do fallback (Chrome extension).

---

## KROK 3 — Wgraj do Garmin Connect

```
mcp__garmin__create-workout(workout=<pełny JSON jako string>)
```

Payload = zawartość zapisanego pliku (przez `open().read()` lub inline). Response zawiera `workoutId` — zapamiętaj.

### Session expired? (401 / błąd auth)

Wywołaj `garmin-login` flow (patrz `skills_core.md` / MCP `mcp__garmin__garmin-login`). Po zalogowaniu ponów `create-workout`.

Jeśli user nie może się zalogować → **fallback**:
- Plik już zapisany lokalnie w KROK 2
- Powiedz: "Session Garmina wygasła. Plik zapisany w `garmin_workouts/upcoming/...` — wgraj przez Chrome extension: [link do extension]"

---

## KROK 4 — Zaplanuj na datę

```
mcp__garmin__schedule-workout(workoutId=<z KROK 3>, date="YYYY-MM-DD")
```

### Wyznaczanie daty

- "na dziś" / brak wskazania → today
- "na jutro" → today+1
- "na sobotę" / dzień tygodnia → najbliższy wystąpienie
- "na 15.08" / konkret → parsuj
- Jeśli user pyta ogólnie "wygeneruj mi long" bez daty → sprawdź `planned_workouts` przez `api.planned` — znajdź najbliższy planned wpis typu `run` z tytułem pasującym do intencji (Long/Easy/Interval/etc.). Zaproponuj tę datę i planowaną strukturę.

---

## KROK 5 — Podsumowanie

Wypisz:
```
✅ Workout: <nazwa>
📁 Lokalny plik: garmin_workouts/upcoming/<nazwa>.json
☁️ Garmin Connect: workoutId=<id>
📅 Zaplanowany: YYYY-MM-DD
```

Plus (jeśli running): krótka tabelka struktury (warmup / intervals / cooldown z tempami) i pogoda + rekomendacja czasu dnia jeśli dziś.

Plus (jeśli strength): tabelka ćwiczeń (nazwa / serie × powt / ciężar / notatka) + kluczowe uwagi z kontekstu (kolano, asymetria).

---

## KROK 6 — Sprzątanie

Usuń tmp scripts (`_tmp_gw.py`, `_tmp_*.py`). Plik JSON w `upcoming/` **zostaje** (backup).

---

## Reguły niezmienne

- **NIE zgaduj** VDOT, pace, weight — bierz z `fitness.md` / DB / potwierdź z userem.
- **NIE forsuj progresji** jeśli `body_state` mówi o kontuzji/dyskomforcie w tym obszarze.
- **Zawsze respektuj plan** z `plan_current.md` (jeśli user nie mówi wprost inaczej).
- **Zawsze zapisz plik lokalnie** przed próbą MCP upload — MCP fail nie może zablokować całego skilla.
- **Nie oznaczaj** `planned_workouts.status_id=done` w tym skillu — workout jest dopiero *planowany*, nie wykonany. `done` idzie przez `/run` lub `/silownia` po fakcie.

## Znane ograniczenia

- Cyrillic w descriptions → Chrome importer bugowałby. MCP prawdopodobnie tolerantniejszy (endpoint JSON), ale i tak trzymaj ASCII-safe przez `ensure_ascii=True`.
- `schedule-workout` nadpisuje jeśli był poprzedni schedule na tę datę? Nie sprawdzone empirycznie — jeśli user chce podmiany, najpierw `mcp__garmin__delete-workout` starego.
