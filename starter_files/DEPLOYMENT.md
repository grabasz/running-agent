# Streamlit Cloud — deploy dashboard

Dashboard można uruchomić publicznie (lub na własnym koncie) za darmo na Streamlit Cloud. Czyta dane z Turso przez pull-on-start (replica file w `/tmp`), więc nie ma per-query round-tripu do chmury.

## Architektura

```
   skille (/run, /silownia, /volume)
              │ zapis lokalny (sqlite3)
              ▼
        db/data.db  ──►  python db/sync.py push  ──►  Turso (libsql)
                                                         │
                                                         │ pull-on-start
                                                         ▼
                                                Streamlit Cloud
                                              (data_replica.db w /tmp)
```

- **Lokalnie**: dashboard używa `db/data.db`. Żadnych zmian, działa offline.
- **Cloud**: dashboard wykrywa `TURSO_DATABASE_URL` w env → wywołuje `api.bootstrap_cloud()` → pulluje całą bazę (~1MB, <1s) do replica file, potem czyta z niej tak jak z lokalnej.
- **Refresh**: przycisk "🔄 Odśwież dane" w sidebarze czyści cache + force-pulluje świeży snapshot.

## Krok po kroku — pierwszy deploy

### 1. Push repo na GitHuba

Repo jest już na githubie (`D:\git\running-agent\running-agent`). Upewnij się, że `starter_files/dashboard.py`, `starter_files/requirements.txt`, `starter_files/db/`, `starter_files/.streamlit/config.toml` są w gałęzi `main`.

⚠️ `db/.env` i `db/data.db` MUSZĄ być w `.gitignore` (są — sprawdzone).

### 2. Załóż konto Streamlit Cloud

→ <https://share.streamlit.io> → Sign in with GitHub.

### 3. New app

- **Repository**: `<twój-user>/running-agent`
- **Branch**: `main`
- **Main file path**: `starter_files/dashboard.py` (jeśli framework jest w starter_files; jeśli ten plik kopiujesz do roota repo — wskaz `dashboard.py`)
- **App URL**: dowolny subdomain `bartek-running.streamlit.app`

### 4. Secrets (TOML)

W ustawieniach app → **Secrets** wklej:

```toml
TURSO_DATABASE_URL = "libsql://running-graboskov.aws-eu-west-1.turso.io"
TURSO_AUTH_TOKEN   = "<TOKEN_Z_db/.env>"
```

Token bierzesz z `db/.env` (lub generujesz nowy bezterminowy: `turso db tokens create running --expiration none`).

### 5. Deploy

Streamlit Cloud sam buduje image z `requirements.txt`. Pierwszy build ~2-3 min. Potem cold start <10s (pull z Turso + bootstrap Streamlit).

## Workflow po deployu

1. Zapisujesz dane lokalnie (`/run`, `/silownia`, `/volume`) → trafiają do `db/data.db`.
2. Pushujesz do chmury: `python db/sync.py push`.
3. Otwierasz dashboard na telefonie → klikasz "🔄 Odśwież dane" → widzisz aktualne dane.

Można dodać krok 2 do auto-saveów w skillach (po każdym `/run` automatyczny `sync.push()`), ale na razie ręcznie.

## "Add to Home Screen" (PWA na telefonie)

iOS Safari / Android Chrome → otwórz dashboard URL → Share / menu → "Add to Home Screen". Otworzy się jako natywna aplikacja (bez paska adresu).

## Gdy coś nie działa

| Problem | Fix |
|---|---|
| `RuntimeError: TURSO_*` not set | Secrets w Streamlit Cloud nie ustawione lub literówka w TOML |
| `database not found` | Token wygasł — wygeneruj nowy `turso db tokens create running --expiration none` |
| Cold start >30s | Pull z Turso jest długi — sprawdź region (`aws-eu-west-1` powinien być blisko PL) |
| Dane "stare" | Ostatni `sync.py push` był dawno temu, albo nie kliknąłeś "🔄 Odśwież dane" |
| Build fail (libsql) | Streamlit Cloud używa Pythona 3.11 — libsql musi się buildować. Jeśli pip fail, sprawdź wersję w `requirements.txt` |
