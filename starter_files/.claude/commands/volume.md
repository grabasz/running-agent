Zaktualizuj `volume_log.md` tygodniowym kilometrażem ze Stravy **+ zapisz do DB** (`weekly_volume`).

**KROK 1** — uruchom skrypt:
```
python scripts/volume.py
```

Skrypt:
1. Pobiera 13 tygodni aktywności z API Stravy (auth wspólne ze strava-mcp)
2. Agreguje tygodniowo (poniedziałek-anchored)
3. Nadpisuje `volume_log.md` (km, wzn., czas, liczba biegów, najdłuższy, trend)
4. **Upsertuje do `db.weekly_volume`** (stderr: `<!-- saved N weeks to DB.weekly_volume -->`)

Output stdout to jedna linia: `Zapisano N tygodni → volume_log.md (avg X km/tydzień)`.

**KROK 2** — wyświetl wynik:
Przeczytaj `volume_log.md` i pokaż użytkownikowi tabelę. Dodaj 1-2 zdania komentarza: średnia tygodniowa, najwyższy tydzień, ewentualny trend (peak/recovery).

**KROK 3 (opcjonalnie)** — pytania historyczne idą prosto do DB, nie wymagają re-fetch:
```python
import sys; sys.path.insert(0, "db"); import api
with api.connect() as conn:
    rows = list(api.weekly_volume.recent(conn, weeks=14))
    # albo: api.weekly_volume.avg_last_n_weeks(conn, weeks=4)
```
