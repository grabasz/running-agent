Pobierz ostatnią sesję siłowni z Garmina i **zapisz do DB** + regeneruj `gym_log.md`.

---

## KROK 1 — Pobierz sesję

### 1A. Garmin (preferowane)

1. `mcp__garmin__list-activities` z `limit: 10`
2. **Znajdź pierwszy element** z `activityType.typeKey == "strength_training"`. Zapamiętaj ten **cały obiekt** (z `summarizedExerciseSets` w środku).
3. **Zapisz** ten obiekt jako JSON do `db/_tmp_silownia.json` (Write tool).
4. **Wywołaj**: `python scripts/silownia_save.py db/_tmp_silownia.json "<context>"` gdzie `<context>` to krótki opis sesji (np. `"Silownia A + Prehab"`, `"Powrot po przerwie"`). Jeśli niepewny → pomiń argument.
5. Skrypt:
   - INSERT/UPDATE do `gym_sessions` + `gym_sets` (per-set heurystyka: total_reps / n_sets)
   - Regeneruje `garmin_workouts/gym/gym_log.md` (ostatnie 5 sesji + Wzorzec aktualnych możliwości)
   - Drukuje gotowy markdown — **wklej output 1:1**

**Jeśli Garmin zwraca 401 / fail** → przejdź do **1B**.

### 1B. Manual entry (fallback)

Brak skryptu manual — poproś usera o wklejenie logu z Garmin Connect (jak 27.06.2026). Ręcznie buduj activity JSON z `summarizedExerciseSets` i wywołaj jak w 1A.

---

## KROK 2 — Komentarze trenerskie

Jeśli user wspomniał o subiektywnych odczuciach (kolano, plecy, technika, energia) — zapisz do `body_state`:

```python
api.body.state_log(conn, date='YYYY-MM-DD', location='kolano_prawe', pain_0_10=N, notes='...')
```

Albo zaktualizuj `notes` konkretnych setów:

```sql
UPDATE gym_sets SET notes = 'plan @BW, wzial 2x8kg, kontrolowal'
 WHERE session_id = <id> AND exercise = 'BSS' AND set_num = 1;
```

Po updacie wykonaj **`python scripts/silownia_save.py --render-only`** żeby zregenerować `gym_log.md` z nowymi notatkami.

---

## KROK 3 — Analiza progresji (opcjonalnie, gdy user pyta)

Wzorzec aktualnych możliwości jest na końcu `gym_log.md`. Plus query:

```python
api.gym.exercise_progression(conn, exercise='RDL', limit=20)
api.gym.top_exercises_by_volume(conn, since='2026-01-01')
```

---

## KROK 4 — Sprzątanie

```
rm db/_tmp_silownia.json
```

---

## ⚠️ Znane ograniczenia Garmin sumaryzowanego API

- `summarizedExerciseSets` daje **sumaryczne dane per ćwiczenie**, nie per set. Skrypt dzieli `total_reps / n_sets` (np. BSS 52 reps / 3 = 17 per set, choć faktycznie było 16+16+20).
- Dla niektórych ćwiczeń bez `subCategory` (np. CORE bez DEAD_BUG) — nazwa będzie ogólna ("Cwiczenia na tulow"). User może `UPDATE` nazwę ręcznie.
- `volume`, `duration`, `maxWeight` w Garmin = gramy/ms — skrypt konwertuje na kg/sec.
- Pełna per-set granulacja (np. 12+12+12 vs 36 total) wymagałaby fetch przez `get-workout` z `workoutId` — TODO na później.
