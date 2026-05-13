Pokaż ostatni bieg ze Stravy jako tabelkę. Wykonaj DOKŁADNIE te kroki po kolei:

**KROK 1** — pobierz listę:
`strava:get-recent-activities` (perPage: 5) → znajdź ostatnią aktywność typu Run (ignoruj Walk/Ride/Hike).

**KROK 2** — szczegóły:
`strava:get-activity-details` dla ID z kroku 1.

**KROK 3** — laps:
`strava:get-activity-laps` dla tego samego ID.

**KROK 4** — streams (ZAWSZE dla biegu):
`strava:get-activity-streams` z parametrami:
- streamTypes: ["distance", "altitude"]
- format: "compact"
- resolution: "medium"

**KROK 5** — oblicz wzn. per km używając skryptu Python:
Weź arrays `distance` i `altitude` ze streams (jako listy liczb).
Użyj narzędzia **Edit** (NIE Write) żeby podmienić w `elev_per_km.py` tylko linię `dist = [...]` i linię `alt = [...]` na nowe dane (zachowaj całą resztę pliku bez zmian):
```
dist = [<wartości z distance stream>]
alt = [<wartości z altitude stream>]
```
Następnie uruchom `python elev_per_km.py` przez Bash i użyj jego outputu jako wartości wzn. per km.

**KROK 6** — OUTPUT. Skopiuj ten format DOKŁADNIE (zamień wartości w nawiasach):

🏃 [nazwa aktywności] — [dzień tygodnia po polsku] [DD.MM.YYYY]
| 📏 Dystans   | [X.XX km]                           |
| ⚡ Tempo śr. | [X:XX/km]                           |
| ⏱️ Czas      | [HH:MM:SS]                          |
| 💓 HR śr.    | [XXX bpm]                           |
| 📈 Wznos.    | [+Xm łącznie]                       |
| 🏷️ Typ       | [Easy / Tempo / Interwały / Wyścig] |

Kadencja z lapów (`average_cadence`) to wartość jednonożna — ZAWSZE mnóż ×2 przed wyświetleniem (np. Strava 87.5 → pokazuj 175 spm).
Moc (`average_watts`) pobierz z lapów bez przeliczania.

| km | tempo | HR  | kad  | moc  | wzn.       | komentarz                        |
|----|-------|-----|------|------|------------|----------------------------------|
| 1  | X:XX  | XXX | XXX  | XXX W| +Xm / -Xm  | [komentarz — patrz wytyczne]     |
[...każdy km osobno, nigdy nie grupuj...]

**Wytyczne do komentarzy per km — WAŻNE:**
Komentarz to OBSERWACJA TRENERSKA, nie dowcip słowny ani pusta metafora.
Pisz co faktycznie się dzieje w tym kilometrze — na podstawie kombinacji tempa, HR i wzn.
- Wzrost HR bez zmiany tempa → "serce pracuje, nogi stoją" / "HR pnie się, tempo broni"
- Szybki km po zjeździe → "zjazd skasowany z głową" / "grawitacja dołożyła"
- Wolniejszy km na podbiegu → "podbieg wziął swoje" / "tempo upada, HR rośnie"
- Km dołkowy bez wyraźnej przyczyny → "chwilowy dołek — jeden tylko" / "energia spadła"
- Przyspieszenie w końcówce → "tu się robi wyścig" / "silnik odpala"
- Bardzo spójna seria km → "taki rytm to robota treningowa" / "jak po sznurku"
- Najszybszy km → "szczyt formy tego dnia" / "wszystko na stół"
NIE pisz żartów słownych, NIE pisz pustych metafor (np. "jak jazz w ucho"), NIE przesadzaj z wykrzyknikami.
Komentarz max 6–8 słów. Ton: konkretny, obserwacyjny, jakbyś mówił do biegacza tuż po linii mety.

Żadnego tekstu przed tabelką.

**KROK 7** — PODSUMOWANIE (tylko dla Wyścigu; dla Easy/Tempo/Interwałów pomiń):

Przed napisaniem podsumowania załaduj `fitness.md` i `races.md` (jeśli nie były jeszcze czytane w tej sesji) — potrzebujesz kontekstu: cel wyścigu, poprzednie PB, T-pace, kolejne starty.

Napisz sekcję `## 📋 Analiza wyścigu` złożoną z dwóch części:

**✅ Co poszło bardzo dobrze** — minimum 4 konkretne obserwacje poparte danymi z lapów/splits. Pisz rzeczowo, ale z energią. Nie wymieniaj rzeczy oczywistych ("dobiegłeś do mety").

**🔧 Co warto rozważyć** — minimum 3 konkretne punkty z odniesieniem do kolejnych startów lub planu treningowego. Nie bądź ogólnikowy ("trenuj więcej") — wskaż konkretny km, konkretny HR, konkretne tempo. Zakończ jednym zdaniem spinającym całość w kontekście sezonu.

**KROK 8** — AKTUALIZACJA PLIKÓW KONTEKSTU (tylko dla Wyścigu; wykonaj po KROK 7):

Oblicz VDOT z wynikowego czasu i dystansu (użyj standardowych tabel Danielsa lub wzoru). Porównaj z aktualnym VDOT z `fitness.md`.

**Jeśli nowy T-pace jest szybszy o >5s/km względem obecnego w `fitness.md`:**

1. Zaktualizuj `fitness.md` przez **Edit** (nie Write) — podmień:
   - Linię z VDOT i datą aktualizacji
   - Wszystkie strefy: E-pace, M-pace, T-pace, I-pace, R-pace
   - Dodaj wpis do sekcji "Historia progu mleczanowego" (nowa linia na końcu listy)
   - Zaktualizuj "Race Predictors" jeśli sekcja istnieje

2. Jeśli wynik to nowe PB na danym dystansie — zaktualizuj `profile.md` przez **Edit**:
   - Podmień odpowiednią linię w sekcji `## PB`

3. Po edycji wyświetl podsumowanie zmian:
```
📝 Zaktualizowano pliki:
- fitness.md: VDOT [stary] → [nowy], T-pace [stary] → [nowy]
- profile.md: PB HM [stary] → [nowy]  ← tylko jeśli PB
```

**Jeśli różnica T-pace ≤5s/km** — nie edytuj plików, napisz jedną linię:
`ℹ️ Forma potwierdzona, próg bez zmian (różnica <5s/km — poniżej progu aktualizacji).`
