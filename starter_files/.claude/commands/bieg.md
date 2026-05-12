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

**KROK 5** — oblicz wzn. per km ze streams:
Użyj arrays `distance` i `altitude` ze streams.
Dla każdego km: przeiteruj próbki gdzie dist[i-1] >= (km-1)*1000 i dist[i] <= km*1000.
Jeśli alt[i] > alt[i-1] → dodaj do `up`. Jeśli alt[i] < alt[i-1] → dodaj abs(diff) do `down`.
Format wyniku: `+{up:.0f}m / -{down:.0f}m`. Jeśli up=0 i down=0 → `—`.

**KROK 6** — OUTPUT. Skopiuj ten format DOKŁADNIE (zamień wartości w nawiasach):

🏃 [nazwa aktywności] — [dzień tygodnia po polsku] [DD.MM.YYYY]
| 📏 Dystans   | [X.XX km]                         |
| ⚡ Tempo śr. | [X:XX/km]                         |
| ⏱️ Czas      | [HH:MM:SS]                        |
| 💓 HR śr.    | [XXX bpm]                         |
| 📈 Wznos.    | [+Xm łącznie]                     |
| 🏷️ Typ       | [Easy / Tempo / Interwały / Wyścig] |

| km | tempo | HR  | wzn.      |
|----|-------|-----|-----------|
| 1  | X:XX  | XXX | +Xm / -Xm |
[...każdy km osobno, nigdy nie grupuj...]

Komentarz (opcjonalnie) dopiero PO tabelce. Żadnego tekstu przed tabelką.
