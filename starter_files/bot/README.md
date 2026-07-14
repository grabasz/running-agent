# Running Agent — Telegram bot

Mobilny dostep do systemu treningowego: dzisiejszy plan, ostatni bieg,
notatki, taski, cele tygodnia, body_state log. Pisze BEZPOSREDNIO do Turso
(brak lokalnego SQLite → stateless deploy).

## Komendy

**Plan treningu**
- `/today` — plan na dzis
- `/tomorrow` — plan na jutro
- `/week` — caly biezacy tydzien
- `/schedule_week [long_km] [next]` — utworz scaffold (Kuba Piech Pn, Lazy Wt/Cz/Nd, Pychowice Sr, REST Pt, Long Sob)

**Historia**
- `/lastrun` — ostatni bieg (pace/HR/GCT/kadencja)
- `/lastgym` — ostatnia silownia (cwiczenia + ciezary)

**Rozkminy** (Faza 17)
- `/n insight <tresc>` — notatka: obserwacja
- `/n decision <tresc>` — notatka: decyzja
- `/n idea <tresc>` — notatka: pomysl
- `/n reminder <tresc>` — auto tworzy TASK (kategoria: inne, priority: med)
- `/tasks [kategoria]` — otwarte taski
- `/done <id>` — zaznacz task jako zrobiony
- `/goals` — cele tygodnia (per kategoria)
- `/goal <kategoria> <cel>` — ustaw cel tygodnia

**Cialo**
- `/log <miejsce> <0-10|doms> [notatka]` — body_state
  - np. `/log kolano 2 klika przy schodach`
  - skroty: kolano, kolano_l, lydka, krzyz, plecy, posladki, achilles, czworka, biodro, it_band

**Diagnostic**
- `/whoami` — twoj Telegram user_id (bez whitelist, do setup)

## Setup lokalny

1. Zainstaluj Python 3.11+
2. `cd bot`
3. `pip install -r requirements.txt`
4. Skopiuj `.env.example` -> `.env` i wypelnij:
   - **TELEGRAM_BOT_TOKEN** — od @BotFather: `/mybots` -> wybierz bota -> API Token
   - **ALLOWED_USER_IDS** — Twoj Telegram user_id (comma-separated jesli wiecej niz jeden)
     - Sposob 1: napisz `/start` do @userinfobot
     - Sposob 2: uruchom bota, wyslij mu `/whoami` — pokaze ID (`/whoami` dziala bez whitelist)
   - **TURSO_DATABASE_URL** + **TURSO_AUTH_TOKEN** — te same co w `db/.env`
5. `python bot.py`

## Deploy na Fly.io

```bash
cd bot
fly auth login                    # jednorazowo
fly apps create running-agent-bot # jednorazowo
fly secrets set \
    TELEGRAM_BOT_TOKEN=... \
    TURSO_DATABASE_URL=libsql://running-graboskov.aws-eu-west-1.turso.io \
    TURSO_AUTH_TOKEN=... \
    ALLOWED_USER_IDS=123456789
fly deploy
```

Po deploy:
- `fly logs` — na zywo
- `fly status` — health VM
- `fly ssh console` — shell w kontenerze (debug)

Restart po zmianie secrets:
```bash
fly deploy --strategy immediate
```

## Architektura

- **Direct Turso writes** — bot uzywa `libsql` do bezposredniego pisania do Turso.
  BRAK lokalnego SQLite → stateless deploy, brak volume mount.
- **Retry Hrana stream expiry** — `turso.py::TursoDB._execute` retryje 3× jesli
  stream padnie po dluzszym idle (analog wzorca z `db/sync.py`).
- **Whitelist** — kazdy handler przechodzi przez `guarded()` middleware ktore
  sprawdza `ALLOWED_USER_IDS`. Zero OAuth.
- **Long polling** — bot nie potrzebuje publicznego HTTP endpointu.
  Nie ma port bindings, health checks — Fly restartuje przy crashach.

## Powiazane

- `db/api.py` — analogiczne API dla Claude Code (lokalne sqlite3)
- Dashboard — te same tabele, widok na desktopie: `streamlit run dashboard.py`
- CLAUDE.md sekcja "Rozkminy" — kiedy Claude sam dodaje notatki/taski
