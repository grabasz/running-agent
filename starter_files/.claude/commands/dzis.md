Pokaż dzisiejszy plan treningowy z DB (`planned_workouts` + `planned_workout_components`) i pozwól odhaczać per komponent.

---

## KROK 1 — Pokaż plan na dziś (z komponentami)

```python
import sys; sys.path.insert(0, "db"); import api
from collections import defaultdict

with api.connect() as conn:
    comps = list(api.planned.components_today(conn))
    tomorrow = list(api.planned.upcoming(conn, days="+2 days", limit=3))

# Grupuj komponenty po planned_id żeby złożyć widok
grouped = defaultdict(list)
for c in comps:
    grouped[dict(c)["planned_id"]].append(dict(c))
```

Wyświetl w formacie:

```
📅 [DD.MM, DZIEŃ]

🛑 REST (dzień odpoczynkowy)     [⚠️ Zmodyfikowany]
   ⚠️ Notatki: bez biegu — kolano
   🌤️ Pogoda: 34°C (burza 84%)
   Komponenty (odhacz `cid=X`):
     [✅ Wykonany]   cid=15  REST
     [⚠️ Zmodyfikowany] cid=16  foam roll
     [⏸️ Zaplanowany]   cid=17  Codzienny Beton

➡️ Jutro: 🏃 Easy 8 km @6:00
```

- Jeśli plan ma 1 komponent (nie rozbity), pokaż go inline bez nagłówka "Komponenty" — czytelniej.
- Jeśli `comps` jest **puste** → `Brak zaplanowanego treningu na dziś. Wygeneruj /tydzien lub dodaj ręcznie.`
- Double-day (2+ planned_id w `grouped`) → sekcja per planned_workout.

Ikonki statusów bierz z `component_status_icon`.

---

## KROK 2 — Aktualizacja statusu (per komponent lub per cały plan)

Domyślnie **odhacz komponent** (`mark_component_status`), nie cały wpis. User mówi konkretnie o czynności → mapuj na `label`.

| User mówi | Akcja |
|---|---|
| "foam roll zrobione", "beton wykonałem" | znajdź `cid` po label match → `api.planned.mark_component_status(conn, id=cid, status_key='done', actual_notes=...)` |
| "beton połowicznie" | `mark_component_status(status_key='modified', actual_notes='polowicznie')` |
| "odpuściłem foam roll" | `mark_component_status(status_key='skipped', actual_notes=...)` |
| "wszystko zrobione", "cały dzień OK" | odhacz WSZYSTKIE `cid` z `grouped[pid]` na `done`, potem sync parent |
| "biegłem", "/run" | wywołaj `/run` skill (zapis do `runs`) — auto-link zrobi się przez `garmin_save.py` / `strava_save.py` |

**PO KAŻDEJ zmianie komponentu:**

```python
api.planned.sync_parent_status_from_components(conn, planned_workout_id=pid)
conn.commit()
```

To auto-agreguje: wszystkie done → parent `done`; wszystkie skipped → `skipped`; wszystkie planned → `planned`; wszystko inne (mieszane) → `modified`.

Po update pokaż potwierdzenie:
```
✅ Odhaczono: 29.06 → foam roll (Wykonany)
   Parent status: modified (2/3 done)
```

**Fallback** — jeśli user wprost mówi o CAŁYM wpisie ("wszystko odpuściłem", "pominąłem cały dzień"), użyj `api.planned.mark_status(conn, id=pid, ...)` na parent + opcjonalnie propaguj na komponenty.

---

## KROK 3 — Body state (gdy user wspomina kolano/łydkę/itp)

Jak w `/run` i `/silownia` — automatycznie zapisz odczucia do `body_state` przez `api.body.state_log()`.

---

## KROK 4 — Push do Turso (OBOWIĄZKOWY, na końcu każdej zmiany)

Po każdym write do DB (`mark_component_status`, `mark_status`, `sync_parent_status_from_components`) — bez pytania:

```
python db/sync.py push
```

Wypisz `☁️ Turso: OK` (lub błąd). Nie blokuj reszty odpowiedzi jeśli push padnie (offline / creds).

---

## Helper: zaplanować NOWY tydzień

Gdy user pyta "zaplanuj kolejny tydzień" → patrz `/tydzien` skill (TODO, jeszcze nie istnieje — na razie ręcznie w `seed_current_week.py`).

Dla NOWYCH wpisów: po `api.planned.add(...)` można od razu dopisać komponenty:

```python
pid = api.planned.add(conn, ...)
for idx, label in enumerate(["REST", "foam roll", "Codzienny Beton"]):
    api.planned.component_add(conn, planned_workout_id=pid, order_idx=idx,
                              label=label, status_key="planned")
```

Albo zostaw title monolityczny i uruchom `python db/migrate_components.py` (idempotentne — rozbija tylko wpisy bez komponentów).
