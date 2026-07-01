Pokaż ostatni bieg jako tabelkę i **zapisz do DB**.

**Garmin primary** (z running dynamics: GCT, vertical oscillation, stride length, training effect, VO₂max). **Strava fallback** gdy Garmin token wygasł.

---

## KROK 1 — pobierz bieg

### 1A. Spróbuj Garmin (preferowane, ma running dynamics)

1. `mcp__garmin__list-activities` z `limit: 10`
2. **Znajdź pierwszy element** z `activityType.typeKey == "running"` (pomiń e_bike, swim, strength). Zapamiętaj `activityId`.
3. `mcp__garmin__get-activity-splits` z `activityId` z kroku 2
4. Zbuduj bundle JSON: `{"activity": <element z list-activities>, "splits": <response get-activity-splits>}`
5. **Zapisz** bundle do `db/_tmp_garmin.json` (Write tool)
6. **Wywołaj**: `python scripts/garmin_save.py db/_tmp_garmin.json`
7. Skrypt zapisuje do DB (`runs` + `run_laps` z running dynamics) i drukuje gotową tabelkę markdown — **wklej output 1:1** poniżej.

**Jeśli `mcp__garmin__list-activities` zwraca błąd 401 / "session expired"** → przejdź do **1B**.

### 1B. Fallback Strava (gdy Garmin nie działa)

```
python scripts/run.py
```
Opcjonalnie: `python scripts/run.py <activity_id>` dla konkretnego biegu.

Skrypt automatycznie zapisuje do DB (`source='strava'`, bez running dynamics) i drukuje tabelkę markdown.

---

## KROK 2 — Wklej tabelkę + dostosuj 2 rzeczy

**Wklej output skryptu 1:1** (już ma `🏷️ Typ` z auto-klasyfikacji w nagłówku — skoryguj jeśli błędna). Potem:

1. **Weryfikuj Typ** w nagłówku (auto-klasyfikacja może się mylić) — `Easy` / `Tempo` / `Interwały` / `Wyścig` / `Long` / `Recovery` / `Shakeout`. Jeśli zmieniasz → `UPDATE runs SET type='...' WHERE id=<run_id>`.

2. **Zamień markery** (🔥 / 🐢 / 💓 / 📉 / ⛰️ / ⏸️ / ⚖️) w kolumnie komentarz na krótkie obserwacje trenerskie (6–8 słów). Marker tylko sygnalizuje GDZIE komentować.

**Pozostałe km zostaw bez komentarza.** Nie wymyślaj komentarzy do równych km.

### Auto-markery
- 🔥 najszybszy / 🐢 najwolniejszy
- 💓 HR peak
- 📉 dołek formy (najniższa kadencja)
- ⛰️ podbieg +Xm
- ⏸️ stop ~Xmin (tylko Strava — Garmin nie wykrywa pauz)
- **⚖️ asymetria L/R** (gdy GCT balance odchyła >0.7% od 50%) — **NOWE dla Garmina**

### Wytyczne komentarzy
Komentarz to obserwacja, nie dowcip. Tempo + HR + wzn + (dla Garmina) dynamics.
- HR rośnie, tempo trzyma → "serce pracuje, nogi stoją"
- Szybki km po zjeździe → "zjazd skasowany z głową"
- Wolniejszy km na podbiegu → "podbieg wziął swoje"
- Asymetria L/R rośnie → "prawa noga przejmuje pod zmęczeniem"
- Krótsze GCT + dłuższy krok → "forma elite-like po pauzie"
- Max 6–8 słów, ton trenerski, konkretny

Żadnego tekstu przed tabelką.

---

## KROK 3 — PODSUMOWANIE (tylko dla Wyścigu)

Dla `Easy` / `Tempo` / `Interwały` / `Long` / `Recovery` / `Shakeout` — **pomiń**.

Załaduj `fitness.md` i `races.md` (jeśli nie były czytane). Napisz `## 📋 Analiza wyścigu`:

**✅ Co poszło bardzo dobrze** — min. 4 obserwacje z danymi z laps/splits.

**🔧 Co warto rozważyć** — min. 3 punkty z odniesieniem do kolejnych startów. Konkretny km, HR, tempo. Zakończ jednym zdaniem spinającym w kontekście sezonu.

---

## KROK 4 — AKTUALIZACJA PLIKÓW (tylko dla Wyścigu, po KROK 3)

Oblicz VDOT z czasu i dystansu. Porównaj z `fitness.md`.

**Jeśli nowy T-pace szybszy o >5s/km:**

1. Zaktualizuj `fitness.md` (Edit): VDOT + data + wszystkie strefy + Historia progu + Race Predictors
2. Jeśli PB — zaktualizuj `profile.md` w sekcji `## PB`
3. Plus w DB: `INSERT INTO vdot_history` i `UPDATE races SET actual_time_sec=..., is_pb=1`
4. Wyświetl:
```
📝 Zaktualizowano:
- fitness.md: VDOT [stary] → [nowy], T-pace [stary] → [nowy]
- profile.md: PB HM [stary] → [nowy]  ← tylko jeśli PB
- DB: vdot_history +1, races UPDATE PB
```

**Jeśli różnica ≤5s/km:**
`ℹ️ Forma potwierdzona, próg bez zmian (różnica <5s/km — poniżej progu aktualizacji).`

---

## KROK 5 — Sprzątanie (opcjonalne)

Po użyciu usuń `db/_tmp_garmin.json` (Bash: `rm db/_tmp_garmin.json` lub Filesystem MCP).

---

## KROK 6 — Push do Turso (OBOWIĄZKOWY, na końcu)

Zawsze po zapisie do DB — bez pytania usera:

```
python db/sync.py push
```

Na końcu wypisz krótko: `☁️ Turso: OK` (lub błąd + info że lokalne zmiany zostały, do retry).

To samo dotyczy `mark_status` na `planned_workouts` (link z zapisanego biegu / update statusu). Cel: mobile / dashboard mają aktualne dane bez przypominania.
