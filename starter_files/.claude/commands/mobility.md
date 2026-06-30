Wygeneruj plan mobility dopasowany do kontekstu — sprawdź ostatni bieg, stan ciała z DB, i obecny plan, potem wydrukuj gotowy blok do skopiowania.

**KROK 0** — sprawdź stan ciała z DB:
```python
import sys; sys.path.insert(0, "db"); import api
with api.connect() as conn:
    pains = list(api.body.state_recent(conn, since="-7 days"))
    # Patrz na pain_0_10 + doms + notes
```
Jeśli któraś lokalizacja ma `pain_0_10 >= 2` lub świeży DOMS w pośladkach/udach → preferuj **głęboką regenerację**, nawet jeśli ostatni bieg był easy.

**KROK 1** — sprawdź kontekst treningowy:
- `plan_current.md` — co jest jutro?
- `api.runs.recent(conn, limit=3)` — ostatnie 3 biegi (HR max, dystans, typ) — szybsze niż ponowny fetch ze Stravy/Garmina

**KROK 2** — dobierz wariant mobility:

| Sytuacja | Wariant |
|----------|---------|
| Świeży DOMS / pain >=2 / dzień po interwałach / wyścigu / HR max >180 | **Głęboka regeneracja** |
| Dzień po Long Run / Tempo / pain 1 | **Standardowa** |
| Dzień wolny / easy / przed jakością / brak bólów | **Aktywizacja** |

**KROK 3** — wydrukuj DOKŁADNIE ten format (zamień wariant):

---
📋 MOBILITY — [wariant] | [DD.MM]

🔴 Rolowanie (foam roller) — 8 min
• Łydki — 60s każda, szukaj twardych punktów
• Czwórki — 60s każda, wolno wzdłuż mięśnia
• IT band (bok uda) — 45s każda
• Pośladki / piriformis — 45s każda

🟡 Rozciąganie statyczne — 5 min
• Hip flexor (half-kneeling) — 45s każda strona
• Hamstringi (leżąc, ręcznik) — 45s każda strona
• Łydka przy ścianie — 30s każda

🟢 Mobilność — 5 min
• Krążenia bioder (stojąc) — 10× w każdą stronę
• Kostki: krążenia + alfabet — 30s każda
• Thoracic rotation (klęk podparty) — 8× każda strona

⚡ Core — [2 lub 3] min
• Dead bug — 3×6 powtórzeń (każda strona)
• Plank — [2×30s lub 2×45s]

⏱️ Łącznie: ~20 min
---

**Warianty szczegółowe:**

GŁĘBOKA REGENERACJA (po interwałach / wyścigu):
- Rolowanie: 8 min (jak wyżej, bardzo wolno)
- Rozciąganie: 5 min (jak wyżej)
- Mobilność: 5 min (jak wyżej)
- Core: POMIŃ lub tylko 2×30s plank
- Dodaj: zimny prysznic na nogi 3 min jeśli masz opcję

STANDARDOWA (po LR / Tempo):
- Jak powyżej, core: dead bug + 2×45s plank

AKTYWIZACJA (przed jakością / dzień easy):
- Rolowanie: skróć do 5 min (tylko łydki + czwórki)
- Dodaj: 10× high knees w miejscu, 10× butt kicks
- Core: dead bug + plank + 10× bird dog
- Dodaj na końcu: 3×20m skip A żeby obudzić biodra

**KROK 4** — na końcu jedna linia kontekstu:
`💡 [Dlaczego ten wariant — np. "po 187bpm z wczoraj — nogi potrzebują rolki, nie obciążenia" lub "kolano 2/10 + DOMS pośladki — głęboka regeneracja"]`

**KROK 5 (jeśli user opisuje nowe odczucia ciała)** — zapisz do DB przez `api.body.state_log()`:
```python
api.body.state_log(conn, date="YYYY-MM-DD", location="kolano_prawe", pain_0_10=2, notes="...")
```
To buduje historię trendów dostępną przy kolejnym `/mobility`.
