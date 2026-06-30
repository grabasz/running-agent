Pokaż dzisiejszy plan treningowy z DB (`planned_workouts`) i pozwól zaktualizować status.

---

## KROK 1 — Pokaż plan na dziś

```python
import sys; sys.path.insert(0, "db"); import api

with api.connect() as conn:
    today = list(api.planned.today(conn))
    tomorrow = list(api.planned.upcoming(conn, days="+2 days", limit=3))
```

Wyświetl tabelkę:

```
📅 [DD.MM, DZIEŃ]

🛑 REST + foam roll + Codzienny Beton     [⏸️ Zaplanowany]
   ⚠️ Notatki: Kuba Piech odpuszczony (kolano + upal)
   🌤️ Pogoda: 39°C (upal 39C)

➡️ Jutro: 🏃 Easy 5-6 km @6:10 RANO
```

Jeśli `today` jest **puste** → komunikat: `Brak zaplanowanego treningu na dziś. Wygeneruj /tydzien lub dodaj ręcznie.`

Jeśli jest **więcej niż 1 wpis** (double-day) → pokaż oba.

---

## KROK 2 — Aktualizacja statusu (gdy user mówi co zrobił)

Pasuj do tego co user napisał:

| User mówi | Akcja |
|---|---|
| "zrobione", "ok", "wykonane" | `api.planned.mark_status(conn, id=X, status_key='done', actual_notes=...)` |
| "zmodyfikowane", "zrobiłem 8km zamiast 10" | `mark_status(status_key='modified', actual_notes='zrobil 8km zamiast 10')` |
| "pominięte", "nie poszedłem", "odpuściłem" | `mark_status(status_key='skipped', actual_notes=powod)` |
| "biegłem", "/run" | wywołaj `/run` skill (zapis do `runs`) — auto-link do `planned_workouts` zrobi się sam przez `silownia_save.py` / `garmin_save.py` / `strava_save.py` |

Po update wyświetl potwierdzenie:
```
✅ Zaktualizowano: 29.06 REST → Wykonane
```

---

## KROK 3 — Body state (gdy user wspomina kolano/łydkę/itp)

Jak w `/run` i `/silownia` — automatycznie zapisz odczucia do `body_state` przez `api.body.state_log()`.

---

## KROK 4 — Sync (po większych zmianach)

Jeśli zaktualizowałeś więcej niż 1 wpis (np. cały tydzień retroaktywnie) — przypomnij `python db/sync.py push` żeby Turso miało aktualne dane.

---

## Helper: zaplanować NOWY tydzień

Gdy user pyta "zaplanuj kolejny tydzień" → patrz `/tydzien` skill (TODO, jeszcze nie istnieje — na razie ręcznie w `seed_current_week.py`).
