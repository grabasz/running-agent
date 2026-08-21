# SETUP_MATI v3 — kompletny recipe (Claude Mobile + Daniels + safety cap 14-latek)

Rozszerza `SETUP_MATI.md` (v2) o Claude Free, ograniczenia wiekowe, konto parent-managed, planowanie Danielsa i cap objętościowy dla nastolatka.

**Cel:** Mati (14 lat) planuje 3-4 treningi/tydz przez Claude Mobile (Free) używając MCP, z rezultatami z jego Garmina, w metodyce Jacka Danielsa. Ojciec (Bartek) trzyma nadzór przez dashboard.

---

## 1. Claude Free — czy wystarczy?

**TAK, wystarczy do codziennego planowania.** Custom Connectors + MCP działają w plan Free (Haiku model), z limitami:

- ~40-50 wiadomości / 5h okno rozliczeniowe
- Haiku 4.5 = szybki i tani, dla planowania tygodniowego wystarczy
- **Realistyczne użycie Matiego:** 1x/tydz plan (5-10 wiadomości), + kilka pytań ad-hoc (2-3/dzień) = zmieści się w limity

**Kiedy warto Pro ($20/mies):**
- Mati chce dużo eksperymentować z AI, długie rozmowy
- Bartek chce dać dostęp do Opus (lepsze planowanie długoterminowe, np. 12-tyg cykl do zawodów)
- Nie priorytet na start — Free jest OK.

---

## 2. Wiek i regulamin (14 lat)

- Claude Terms of Service: 18+ dla własnego konta w większości krajów (13+ z rodzicem w US wg wersji ToS)
- **Rekomendacja bezpieczna:**
  - Bartek zakłada konto Claude na własny email (albo alias `mati@bartek-domain.com`)
  - Konto zalogowane na iPhone Matiego jako "Mati's phone"
  - Bartek jako prawny opiekun akceptuje regulamin
  - iOS Screen Time / Family Sharing dodatkowo ogranicza czas w apce jeśli potrzeba
- **Nie zakładać** Matiemu osobnego konta z fałszywą datą urodzenia — potencjalne problemy z Terms i utrata historii jeśli Anthropic zauważy

---

## 3. Setup Garmin + Fly (z `SETUP_MATI.md` v2)

Wykonaj kroki 1-2 z **SETUP_MATI.md** (v2, w tym samym katalogu):

- **Krok 1** — tokeny Matiego lokalnie (`test_login_mati.py` z `GARMINTOKENS`)
- **Krok 2** — drugi Fly app `garmin-mcp-mati.fly.dev`:
  - `flyctl apps create garmin-mcp-mati`
  - Secrets: `USER_ID=2`, `AUTH_TOKEN=<random>`, `TURSO_DATABASE_URL=<same>`, `TURSO_AUTH_TOKEN=<same>`, `GARMIN_TOKENS_JSON=<content>`
  - **NOWY (PR #44):** `ENC_KEY=<klucz Matiego>` — patrz sekcja 5 poniżej
  - `flyctl deploy -a garmin-mcp-mati`

Szacowany czas: 45-60 min z Matim obok.

---

## 4. Konto Claude + Custom Connector iOS Matiego

1. **Bartek zakłada Claude account** (jeśli Mati nie ma):
   - https://claude.ai → Sign up własnym emailem (Bartka albo alias)
   - Akceptuje ToS jako opiekun
2. **iPhone Matiego** — instalacja Claude iOS + login tym samym kontem
3. **Custom Connector:**
   - Claude iOS → Settings → Connectors → Add Custom Connector
   - URL: `https://garmin-mcp-mati.fly.dev/mcp`
   - OAuth login (browser flow) — Mati loguje się swoim Fly `AUTH_TOKEN` (Bartek daje mu link/token przy setupie)
4. **Weryfikacja:** Mati wpisuje w Claude: *"jaki mam VDOT?"* → Claude wywołuje `db-current-vdot`, powinien zwrócić `no_vdot_recorded` (jeszcze nic nie ma w DB) — to sygnał że setup działa.

---

## 5. Szyfrowanie (PR #44 — prywatność notatek)

Notes/tasks/actual_notes Matiego są szyfrowane osobnym kluczem — **Bartek NIE widzi** treści Matiego (nawet w Turso).

```powershell
# Bartek generuje klucz dla Matiego (JEDNORAZOWO, zapisz w password manager):
python C:\Users\grabb\Documents\running\db\generate_enc_key.py
# -> np. "aBcDeFg..."

# Wklej do 2 miejsc:
# 1. Fly Mati:
flyctl -a garmin-mcp-mati secrets set ENC_KEY="aBcDeFg..."

# 2. Streamlit Cloud Secrets: USER2_ENC_KEY = "aBcDeFg..."
#    (przez UI: share.streamlit.io -> app -> Manage -> Secrets)
```

**Backup klucza obowiązkowy** — zguba = dane Matiego bezpowrotnie utracone.

---

## 6. VDOT + planowanie Danielsa

### 6a. Test 5 km (pomiar VDOT)

Mati wykonuje test wysiłkowy:
- 5 km z Garminem, na płaskim (Zakrzówek pętla albo bieżnia), rozgrzewka 10 min + 5 km max effort + wychłodzenie
- Wynik: czas 5 km → VDOT (Bartek wylicza z tabeli Daniels albo z Garmin Race Predictor)

Przykład: 5 km w 24:00 → VDOT ~38

### 6b. Wpisanie VDOT do DB

```powershell
# Bartek w PowerShell (lokalnie, `api.py` auto-loaduje .env, poleci do Turso):
python -c "import sys; sys.path.insert(0, 'C:/Users/grabb/Documents/running/db'); import api; conn = api.connect(); conn.execute('INSERT INTO vdot_history (user_id, vdot, source, date, notes) VALUES (2, 38, \"test 5km\", \"2026-08-23\", \"pierwszy test Matiego, Zakrzowek\")'); conn.commit(); print('OK')"
```

### 6c. Nowy tool `db-get-training-paces`

Po deployu (patrz sekcja 3), Mati może zapytać w Claude iOS:

> *"Jakie mam tempa treningowe?"*

Claude wywoła `db-get-training-paces` (bez args → pobierze VDOT z DB), zwróci:
```
VDOT 38:
  E (easy)     : 4:20 - 4:50/km   -- większość biegów
  T (threshold): 3:20/km          -- tempo, ~20 min steady
  I (interval) : 3:05/km          -- powtórzenia 3-5 min
  R (rep)      : 2:45/km          -- sprint 200-400m
```

(dla VDOT 38 realnie: E ~5:30-6:00 — sprawdź interpolację po deployu)

### 6d. Przykładowa pierwsza rozmowa Matiego

```
Mati: "Cześć, mam 14 lat, biegam od 3 miesięcy. Ostatnio 5km w 24 min.
       Chcę biegać 3 razy w tygodniu. Zaplanuj mi tydzień 25-31.08."

Claude:
  1. Wywoła db-current-vdot → VDOT 38
  2. Wywoła db-get-training-paces(38) → E, T, I, R tempa
  3. Wywoła db-workout-types → dostępne typy
  4. Zaplanuje przez db-plan-workout × 3:
     - Wt 26.08 easy 5km @5:30-6:00
     - Czw 28.08 easy 4km @5:30-6:00
     - Nd 31.08 easy 6-7km @5:30-6:00 (długi)
  5. Wypisze plan w tabeli.
```

---

## 7. ⚠️ Safety cap dla 14-latka

Rosnące kości i ścięgna wymagają ostrożności. **Wytyczne dla Matiego (do zakodowania jako rule w kontekście każdej sesji Matiego z Claude):**

- **Max 30 km/tydzień** przez pierwsze 3 miesiące
- **Max 8 km pojedynczy bieg** (długi max 10 km po 6 miesiącach)
- **Zero intervals (I) i repetition (R)** — kości i ścięgna dojrzewają do ~16 rż
- **Easy (E) 80%+ objętości**, jedno T raz na 2 tygodnie max
- **1 dzień odpoczynku między biegami** minimum
- **Fokus:** baza aerobowa + nawyk, nie wyniki
- **Bez zawodów >5 km** przez pierwsze pół roku

**Implementacja:**

Ponieważ FastMCP INSTRUCTIONS są globalne (nie per-user), safety cap wymaga per-app instrukcji. Dwa podejścia:

**A) TERAZ (proste):** Bartek dopisze do promptu Matiego na start:
> "Jesteś asystentem trenera dla Mati (14 lat). Limity: max 30 km/tydz, max 8 km jednorazowo, zero intervalów i repetycji, easy 80%. Fokus: aerobowa baza i nawyk."

**B) POTEM (docelowe):** Osobny plik `instructions_mati.md` ładowany warunkowo od `USER_ID == 2` w `server.py`:

```python
# w server.py przed FastMCP init:
INSTRUCTIONS_FILE = "instructions_mati.md" if USER_ID == 2 else None
instructions = open(INSTRUCTIONS_FILE).read() if INSTRUCTIONS_FILE else DEFAULT_INSTRUCTIONS
mcp = FastMCP("personal-training", instructions=instructions)
```

Odsunięte jako TODO — zacznij od podejścia A (prompt-level safety).

---

## 8. Strava?

**Nie potrzebna.** Nasze MCP używa Garmin API bezpośrednio, nie Stravy. Mati nie musi zakładać konta Strava.

Jeśli w przyszłości Mati chce dzielić się z klubem/znajomymi → założy konto Strava, podepnie w Garmin Connect (Settings → Partner Connections → Strava), auto-sync działa. Zero pracy po naszej stronie.

---

## 9. Checklist skrótowy (weekend, 60-90 min)

- [ ] Bartek: wygeneruj `ENC_KEY` Matiego + zapisz w password manager
- [ ] Bartek: `test_login_mati.py` z `GARMINTOKENS` — tokeny Matiego lokalnie
- [ ] Bartek: `flyctl apps create garmin-mcp-mati` + wszystkie secrets (USER_ID=2, ENC_KEY, TURSO_*, GARMIN_TOKENS_JSON, AUTH_TOKEN)
- [ ] Bartek: `flyctl deploy -a garmin-mcp-mati --remote-only` (wait ~5 min)
- [ ] Bartek: Streamlit Secrets → dodać `USER2_NAME`, `USER2_PASSWORD`, `USER2_ENC_KEY`
- [ ] Mati: test 5km z Garminem (Zakrzówek), Bartek wpisuje VDOT do `vdot_history`
- [ ] Mati: instalacja Claude iOS, login kontem Bartka
- [ ] Mati: Custom Connector → `garmin-mcp-mati.fly.dev`, OAuth flow
- [ ] Mati: pierwszy prompt "*Zaplanuj mi tydzień*" — Bartek asystuje przy pierwszej rozmowie, wtrąca safety cap w prompcie
- [ ] Bartek: dashboard weryfikacja — Mati zobaczy tylko swoje plany (user_id=2), Bartek swoje (user_id=1)

---

## 10. Co dalej (po pierwszym tygodniu)

- **Test #2 po 4-6 tygodniach** — nowy 5 km, wpisać nowy VDOT do `vdot_history` (Daniels: VDOT rośnie zwykle 1-3 punkty w 6 tyg dla początkującego)
- **Wprowadzenie longa 8 km** po 8 tygodniach regularności
- **Ewentualne pierwsze zawody** 5 km po 3 miesiącach — parkrun, szkolne
- **Instructions per-user** (opcja B z sekcji 7) — jeśli safety cap w prompcie okaże się niewystarczający
