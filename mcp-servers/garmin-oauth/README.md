# garmin-oauth MCP

Python MCP server for Garmin Connect. Runs in **two modes**:

- **stdio** (default) — for local Claude Code (`.mcp.json` on Windows)
- **http** — for remote hosting (Fly.io) so Claude iOS/Android app can use it via Custom Connectors

## Local (stdio) — already configured

Wired in `C:\Users\grabb\Documents\running\.mcp.json` as `garmin`. Tokens live in `~/.garminconnect/`. If OAuth1 expires (~1 year): run `python test_login.py` and re-enter MFA.

## Remote (http) — Fly.io deploy

### One-time setup

**1. Install flyctl** (PowerShell as admin):
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```
Then restart the shell so `flyctl` lands in PATH.

**2. Login + create app:**
```powershell
flyctl auth signup   # or: flyctl auth login
cd C:\Users\grabb\.mcp-servers\garmin-oauth
flyctl launch --no-deploy --copy-config --name garmin-mcp-grabb --region waw
```
(If `garmin-mcp-grabb` is taken, edit `fly.toml` and pick a different name.)

**3. Create persistent volume for OAuth tokens:**
```powershell
flyctl volumes create garmin_tokens --region waw --size 1
```

**4. Set secrets** — OAuth 2.1 client credentials + Garmin tokens seed:
```powershell
# Generate a strong random OAuth Client Secret — save it, you'll paste into Claude UI
$oauthSecret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 40 | ForEach-Object {[char]$_})
$oauthSecret   # copy this; you'll need it in Claude Custom Connector

flyctl secrets set OAUTH_CLIENT_SECRET=$oauthSecret
# OAUTH_CLIENT_ID defaults to "claude-connector"; override if you want:
# flyctl secrets set OAUTH_CLIENT_ID=some-name

# Seed the Garmin OAuth tokens from the local login
$garminTokens = Get-Content "$HOME\.garminconnect\garmin_tokens.json" -Raw
flyctl secrets set GARMIN_TOKENS_JSON=$garminTokens
```

**5. Deploy:**
```powershell
flyctl deploy --remote-only
```
(`--remote-only` builds on Fly's builder — no local Docker Desktop required. If you have Docker running locally you can drop the flag for a faster local build.)

### Smoke test (PowerShell)

**Zasady bo PS jest wredny:**
- **`curl.exe`** (z rozszerzeniem) — goły `curl` w PS to alias na `Invoke-WebRequest` z inną składnią
- **`--ssl-no-revoke`** — jeśli AV/firewall blokuje CRL/OCSP, schannel wywala `CRYPT_E_NO_REVOCATION_CHECK`; flaga to pomija (cert LE jest ważny, ryzyko zerowe)
- **JSON w single-quoted stringu jednoliniowym** — heredoc czasem dodaje newline w środku i JSON się rozjeżdża
- **`--data-binary`** zamiast `-d` — nie mieli w encodingu

**Test 1: /health (bez auth)**
Skopiuj cały blok, wklej do PS, Enter:
```powershell
curl.exe --ssl-no-revoke https://garmin-mcp-grabb.fly.dev/health
```
Oczekiwany output: `{"status":"ok"}`

**Test 2: /mcp initialize (z bearerem)**
Jeśli otwarłeś nową sesję PS, ustaw ponownie `$token` (wartość z `flyctl secrets` który wygenerowałeś w kroku 4):
```powershell
$token = "TU_WKLEJ_SWOJ_BEARER_TOKEN"
```

Potem skopiuj cały blok poniżej i wklej do PS (jednym paste'em):
```powershell
Set-Content -Path body.json -NoNewline -Encoding ascii -Value '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'

curl.exe --ssl-no-revoke -H "Authorization: Bearer $token" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -X POST https://garmin-mcp-grabb.fly.dev/mcp --data-binary "@body.json"
```
(Body idzie przez plik bo PS 5.1 ma bug: przy przekazywaniu stringa z `"` do external .exe zjada wewnętrzne cudzysłowy — serwer dostaje `{jsonrpc:2.0,...}` bez `"`. `@body.json` w curl = "czytaj body z pliku".)
Oczekiwany output (SSE):
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",...,"serverInfo":{"name":"garmin-oauth",...}}}
```

Jeśli widzisz `"serverInfo":{"name":"garmin-oauth"` — HTTP mode działa. Idź do "Wire into Claude mobile app" niżej.

**Typowe błędy:**
| Objaw | Przyczyna | Fix |
|---|---|---|
| `Cannot bind parameter 'Headers'` | użyłeś `curl` zamiast `curl.exe` | użyj `.exe` |
| `CRYPT_E_NO_REVOCATION_CHECK` | AV blokuje OCSP | dodaj `--ssl-no-revoke` |
| `Invalid Host header` | brak Fly domeny w allowlist | patrz `server.py` → `TransportSecuritySettings` |
| `Parse error -32700` | body ma newline w środku | użyj **single-line** `'...'` string zamiast heredoca |
| `unauthorized` (401) | pusty `$token` w nowej sesji PS | ustaw `$token = "..."` ponownie |

### Wire into Claude (web or mobile — Custom Connector w/ OAuth 2.1)

Anthropic Custom Connectors require OAuth. Our server implements OAuth 2.1
with a **pre-registered client** — DCR is disabled so nobody can self-register.

1. Open **claude.ai in browser** (mobile app may or may not have UI yet) → Settings → Connectors → Add custom connector
2. **Server URL:** `https://garmin-mcp-grabb.fly.dev/mcp`
3. **Client ID:** `claude-connector` (or whatever you set in OAUTH_CLIENT_ID)
4. **Client Secret:** paste `$oauthSecret` from step 4
5. Save → click **Connect** on the connector card
6. Browser will redirect through our /authorize (auto-approves) and back to Claude → connector shows "Connected"
7. New chat → tool picker shows `garmin` with all tools
8. Try: *"sprawdź check-session garmina"* — Claude calls the MCP tool over HTTPS to Fly

### Rotating the OAuth Client Secret

If the secret leaks:
```powershell
$newSecret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 40 | ForEach-Object {[char]$_})
flyctl secrets set OAUTH_CLIENT_SECRET=$newSecret
flyctl ssh console -C "rm /data/oauth-state.json"   # wipe cached client + old tokens
flyctl apps restart garmin-mcp-grabb
```
Then update the Client Secret in Claude Custom Connector → reconnect.

### Token refresh

`garminconnect` refreshes OAuth2 access token silently via API (no browser). The refresh gets written back to `TOKEN_DIR/garmin_tokens.json` on the **volume** — survives restarts and redeploys. When OAuth1 expires (~1 year), run `test_login.py` locally, then re-seed:

```powershell
$garminTokens = Get-Content "$HOME\.garminconnect\garmin_tokens.json" -Raw
flyctl secrets set GARMIN_TOKENS_JSON=$garminTokens
flyctl ssh console -C "rm /data/garminconnect/garmin_tokens.json"
flyctl apps restart garmin-mcp-grabb
```
(The `rm` forces the seed to re-fire; alternative: `flyctl ssh sftp` push the file directly.)

## Fallback

If OAuth path breaks, `mcp__garmin-cookies__*` still points to the old `@etweisberg` MCP (cookie-based) — see `C:\Users\grabb\Documents\running\.mcp.json`. To fully roll back: restore `.mcp.json.pre-oauth.backup`.
