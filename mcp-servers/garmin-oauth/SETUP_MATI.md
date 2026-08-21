# SETUP_MATI — Garmin MCP dla drugiego użytkownika (Mati)

Duplikuje setup z `README.md` (Bartek) dla Matiego: własne tokeny Garmin + osobny Fly app + własny Custom Connector. Setup ~35 min, weekend/piątek wieczorem z Matim obok.

**Efekt końcowy:** Mati wpina `https://garmin-mcp-mati.fly.dev/mcp` do swojego (albo tymczasowo Bartka) Claude/Custom Connector i wywołuje `mcp__garmin-mati__*` na swoich danych, zapisy do DB idą na `user_id=2`.

## ⚠️ Zależność

**Krok 2 wymaga USER_ID env var w `server.py`** (Fork 3 tego setup). Bez tego MCP zwróci dane Matiego z Garmina ale zapisy do DB (przez skille /run itp.) polecą na Bartka (user_id=1) — konflikt. Sprawdź czy `server.py` zawiera `USER_ID = int(os.getenv("USER_ID", "1"))` przed deployem. Jak nie ma — dokończ Fork 3 najpierw.

## Prereqs (30 sek)

- `flyctl --version` → jest zainstalowany, jesteś zalogowany (`flyctl auth whoami`)
- Konto Fly ma **aktywną kartę** (organizational tier, żeby druga app się poszła)
- Mati ma pod ręką: email do Garmin Connect + hasło + telefon z MFA (SMS lub authenticator)

---

## Krok 1 — Tokeny Matiego lokalnie (~15 min)

### 1a. Odpal `test_login.py` z jego TOKEN_DIR

**Problem:** `test_login.py` ma `TOKEN_DIR` hardcoded na `~/.garminconnect/` (nie respektuje `GARMINTOKENS` env var). Trzeba tymczasową kopię pliku.

```powershell
Copy-Item C:\Users\grabb\.mcp-servers\garmin-oauth\test_login.py `
          C:\Users\grabb\.mcp-servers\garmin-oauth\test_login_mati.py
```

Otwórz `test_login_mati.py`, zmień linię 23:
```python
TOKEN_DIR = str(Path.home() / ".garminconnect-mati")
```

### 1b. Wprowadź kredencjały Matiego do keyring

Uruchom `setup_credentials.py` interaktywnie — ale on też pisze pod `SERVICE = "garmin-mcp"`. Bartka kredencjały nadpiszemy chwilowo:

```powershell
# BACKUP kredencjaliami Bartka (przywrócimy po tokenach Matiego)
$bartekEmail = (& python -c "import keyring; print(keyring.get_password('garmin-mcp', 'email'))")
$bartekPass  = (& python -c "import keyring; print(keyring.get_password('garmin-mcp', 'password'))")

# Wpisz Matiego (Mati podaje przy tobie, nie widzisz przez ramię)
python C:\Users\grabb\.mcp-servers\garmin-oauth\setup_credentials.py
```

### 1c. Login z MFA

```powershell
python C:\Users\grabb\.mcp-servers\garmin-oauth\test_login_mati.py
```

Zapyta o kod MFA — Mati podaje ze swojego telefonu. Sukces = wypisze daily summary.

### 1d. Weryfikacja + przywrócenie kredencjaliami Bartka

```powershell
# Sprawdź że tokeny się zapisały
Test-Path "$HOME\.garminconnect-mati\garmin_tokens.json"   # → True

# Przywróć Bartka do keyring (żeby `check-session` Bartka MCP dalej działało)
python -c "import keyring; keyring.set_password('garmin-mcp', 'email', '$bartekEmail'); keyring.set_password('garmin-mcp', 'password', '$bartekPass')"

# Skasuj temp script
Remove-Item C:\Users\grabb\.mcp-servers\garmin-oauth\test_login_mati.py
```

**Efekt:** `~/.garminconnect-mati/garmin_tokens.json` istnieje (~2KB), zawiera OAuth1 + OAuth2 tokeny Matiego. Ważne ~rok (OAuth1 rotates rocznie).

---

## Krok 2 — Drugi Fly app (~20 min)

### 2a. Skopiuj folder bez cache

```powershell
Copy-Item -Recurse -Exclude '__pycache__','*.pyc','body.json','.venv' `
  C:\Users\grabb\.mcp-servers\garmin-oauth `
  C:\Users\grabb\.mcp-servers\garmin-oauth-mati

cd C:\Users\grabb\.mcp-servers\garmin-oauth-mati
```

### 2b. Edytuj `fly.toml`

Zmień **tylko linijkę 6**:
```toml
app = 'garmin-mcp-mati'
```

Reszta bez zmian (`primary_region = 'ams'`, PORT, mount `garmin_tokens`, checks — patrz [README.md → Remote (http) → One-time setup](README.md) po szczegóły).

### 2c. Utwórz Fly app + volume

```powershell
flyctl launch --no-deploy --copy-config --name garmin-mcp-mati --region ams
flyctl volumes create garmin_tokens --region ams --size 1
```

**Uwaga:** volume `garmin_tokens` to nazwa lokalna do tej app (per-app scoped). Nie kolizja z Bartka volume o tej samej nazwie.

### 2d. Sekrety (INNY OAUTH_CLIENT_SECRET niż Bartka!)

```powershell
$oauthSecret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 40 | ForEach-Object {[char]$_})
$oauthSecret   # ZAPISZ — potrzebne w kroku 4 w Custom Connector

$garminTokens = Get-Content "$HOME\.garminconnect-mati\garmin_tokens.json" -Raw

flyctl secrets set `
  OAUTH_CLIENT_SECRET=$oauthSecret `
  GARMIN_TOKENS_JSON=$garminTokens `
  USER_ID=2
```

`USER_ID=2` — MCP odczyta i zapisze do DB pod `user_id=2` (jak Fork 3 wdrożone).

### 2e. Deploy

```powershell
flyctl deploy --remote-only
```

Build ~3 min. Po zakończeniu app żyje pod `https://garmin-mcp-mati.fly.dev`.

---

## Krok 3 — Smoke test (~5 min)

### 3a. Health

```powershell
curl.exe --ssl-no-revoke https://garmin-mcp-mati.fly.dev/health
```
→ `{"status":"ok"}`

### 3b. `/mcp initialize` z bearerem

```powershell
$token = "TU_WKLEJ_$oauthSecret"   # ten wygenerowany w kroku 2d

Set-Content -Path body.json -NoNewline -Encoding ascii -Value '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'

curl.exe --ssl-no-revoke `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  -X POST https://garmin-mcp-mati.fly.dev/mcp --data-binary "@body.json"
```

Szukaj `"serverInfo":{"name":"garmin-oauth"` w SSE output → HTTP działa. Rules PS (`curl.exe` nie `curl`, `--data-binary "@body.json"` nie inline, `--ssl-no-revoke` przy błędach CRL) — patrz [README.md → Smoke test → "Zasady bo PS jest wredny"](README.md).

### 3c. `tools/call` z Matiego danymi

Podmień body.json na wywołanie `check-session` żeby zweryfikować że tokeny Matiego łączą się z Garminem:

```powershell
Set-Content -Path body.json -NoNewline -Encoding ascii -Value '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"check-session","arguments":{}}}'

curl.exe --ssl-no-revoke -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  -X POST https://garmin-mcp-mati.fly.dev/mcp --data-binary "@body.json"
```

Powinno zwrócić Matiego daily steps/resting HR — nie Bartka.

---

## Krok 4 — Custom Connector w Claude

1. **Mati loguje się** do <https://claude.ai> (jego konto — jeśli ma; lub tymczasowo Bartka)
2. Settings → **Connectors** → **Add custom connector**
3. **Server URL:** `https://garmin-mcp-mati.fly.dev/mcp`
4. **Client ID:** `claude-connector`
5. **Client Secret:** paste `$oauthSecret` z kroku 2d
6. Save → **Connect** na karcie connectora
7. Redirect przez `/authorize` (auto-approves) i wraca → "Connected"
8. Nowy chat → tool picker pokazuje `garmin-mati` (albo pod jaką nazwą Claude zarejestrował connector) → dostępne narzędzia MCP

**Test:** *"sprawdź check-session garmina"* → Claude wywołuje MCP Matiego, dane Matiego wracają.

---

## Typowe błędy

| Objaw | Przyczyna | Fix |
|---|---|---|
| `MCP zwraca dane Bartka mimo tokenów Matiego` | `GARMIN_TOKENS_JSON` sekret niepoprawnie zaseeded (albo Fly app cache) | `flyctl ssh console -C "cat /data/garminconnect/garmin_tokens.json"` — porównaj z lokalnym Matiego. Jak inne: `flyctl ssh console -C "rm /data/garminconnect/garmin_tokens.json"` + restart |
| `Zapisy do DB idą na user_id=1 mimo USER_ID=2` | `server.py` nie odczytuje env var — Fork 3 nie wdrożone | Sprawdź `grep USER_ID server.py`. Jak brak — nie deployuj, dokończ Fork 3 najpierw |
| `flyctl launch fail: app name taken` | `garmin-mcp-mati` już zajęte (może przez ciebie z poprzedniej próby) | `flyctl apps list` → jak jest → `flyctl apps destroy garmin-mcp-mati -y`, spróbuj ponownie |
| `test_login_mati.py error: no such file .garminconnect-mati` | garth nie stworzył katalogu | `New-Item -ItemType Directory -Path "$HOME\.garminconnect-mati"` przed uruchomieniem |
| `Custom Connector "Failed to connect"` | Cloudflare/DNS jeszcze się propaguje (nowa app) | Poczekaj 2-3 min po `flyctl deploy` przed dodaniem connectora |

---

## Rollback

Jak coś padnie i chcesz zacząć od zera:

```powershell
flyctl apps destroy garmin-mcp-mati -y                   # usuwa Fly app + volume + sekrety
Remove-Item -Recurse C:\Users\grabb\.mcp-servers\garmin-oauth-mati
Remove-Item -Recurse "$HOME\.garminconnect-mati"         # tokeny Matiego
# w claude.ai: Settings → Connectors → 3-kropki obok "garmin-mati" → Remove
```

Nie ruszaj Bartka setupu — jego tokeny + Fly app są osobne.
