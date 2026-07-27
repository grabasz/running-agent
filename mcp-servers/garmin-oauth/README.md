# garmin-oauth MCP

Python MCP server for Garmin Connect. Runs in **two modes**:

- **stdio** (default) — for local Claude Code (wired via `.mcp.json`)
- **http** — for remote hosting (Fly.io) so Claude iOS/Android app or ChatGPT
  can use it via Custom Connectors

Throughout this README, replace `garmin-mcp-YOURNAME` with a globally unique
Fly.io app name of your choice.

## Local (stdio)

Add an entry to your project's `.mcp.json` pointing at `server.py` in this
folder. Tokens live in `~/.garminconnect/`. If OAuth1 expires (~1 year): run
`python test_login.py` and re-enter your MFA code.

## Remote (http) — Fly.io deploy

### One-time setup

**1. Install flyctl** (PowerShell as admin, on Windows):
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```
Then restart the shell so `flyctl` lands in PATH. On macOS/Linux see
<https://fly.io/docs/hands-on/install-flyctl/>.

**2. Login + create app** — from this folder (`mcp-servers/garmin-oauth`):
```powershell
flyctl auth signup   # or: flyctl auth login
flyctl launch --no-deploy --copy-config --name garmin-mcp-YOURNAME --region ams
```
Pick a region close to you: <https://fly.io/docs/reference/regions/>.
If the name is taken, edit `fly.toml` and pick a different one.

**3. Create persistent volume for OAuth tokens** (same region as the app):
```powershell
flyctl volumes create garmin_tokens --region ams --size 1
```

**4. Set secrets** — OAuth 2.1 client credentials + Garmin tokens seed:
```powershell
# Generate a strong random OAuth Client Secret — save it, you'll paste it
# into the Claude / ChatGPT connector UI.
$oauthSecret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 40 | ForEach-Object {[char]$_})
$oauthSecret   # copy this; you'll need it below

flyctl secrets set OAUTH_CLIENT_SECRET=$oauthSecret
# OAUTH_CLIENT_ID defaults to "claude-connector"; override if you want:
# flyctl secrets set OAUTH_CLIENT_ID=some-name

# Seed the Garmin OAuth tokens from your local login (run test_login.py first
# so the file exists).
$garminTokens = Get-Content "$HOME\.garminconnect\garmin_tokens.json" -Raw
flyctl secrets set GARMIN_TOKENS_JSON=$garminTokens

# Optional: a shared bearer token for smoke tests / non-OAuth callers.
$authToken = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 40 | ForEach-Object {[char]$_})
flyctl secrets set AUTH_TOKEN=$authToken
```

**5. Deploy:**
```powershell
flyctl deploy --remote-only
```
(`--remote-only` builds on Fly's builder — no local Docker Desktop required.
If you have Docker running locally you can drop the flag for a faster build.)

### Smoke test (PowerShell)

**PowerShell gotchas:**
- Use **`curl.exe`** (with `.exe`) — bare `curl` in PS is an alias for
  `Invoke-WebRequest`, which has a different flag syntax.
- **`--ssl-no-revoke`** — if AV/firewall blocks CRL/OCSP, schannel throws
  `CRYPT_E_NO_REVOCATION_CHECK`; this flag skips it (the LE cert is valid;
  zero risk locally).
- Keep JSON on a **single line** in a single-quoted string — heredocs can
  add newlines that break JSON parsing on the server.
- Prefer `--data-binary` over `-d` — no encoding mangling.

**Test 1: /health (no auth):**
```powershell
curl.exe --ssl-no-revoke https://garmin-mcp-YOURNAME.fly.dev/health
```
Expected: `{"status":"ok"}`.

**Test 2: /mcp initialize (with bearer):**
```powershell
$token = "PASTE_YOUR_AUTH_TOKEN"

Set-Content -Path body.json -NoNewline -Encoding ascii -Value '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'

curl.exe --ssl-no-revoke -H "Authorization: Bearer $token" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -X POST https://garmin-mcp-YOURNAME.fly.dev/mcp --data-binary "@body.json"
```
(Body via file because PS 5.1 has a bug: passing a string containing `"` to a
native .exe eats internal quotes — the server ends up with `{jsonrpc:2.0,...}`
without the `"`. `@body.json` tells curl to read the body from a file.)

Expected (SSE stream):
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",...,"serverInfo":{"name":"garmin-oauth",...}}}
```

**Common errors:**
| Symptom | Cause | Fix |
|---|---|---|
| `Cannot bind parameter 'Headers'` | you used `curl`, not `curl.exe` | use `.exe` |
| `CRYPT_E_NO_REVOCATION_CHECK` | AV blocks OCSP | add `--ssl-no-revoke` |
| `Invalid Host header` | Fly domain not in allowlist | check `server.py` → `TransportSecuritySettings` |
| `Parse error -32700` | body has embedded newline | use a **single-line** `'...'` string, not a heredoc |
| `unauthorized` (401) | empty `$token` in a fresh PS session | re-set `$token = "..."` |

### Wire into Claude (web or mobile — Custom Connector w/ OAuth 2.1)

Anthropic Custom Connectors require OAuth. Our server implements OAuth 2.1
with a **pre-registered client** — DCR (Dynamic Client Registration) is
disabled so nobody can self-register.

1. Open **claude.ai in browser** → Settings → Connectors → Add custom connector.
2. **Server URL:** `https://garmin-mcp-YOURNAME.fly.dev/mcp`
3. **Client ID:** `claude-connector` (or whatever you set in `OAUTH_CLIENT_ID`).
4. **Client Secret:** paste `$oauthSecret` from step 4 above.
5. Save → click **Connect** on the connector card.
6. Browser redirects through `/authorize` (auto-approves) and back to Claude
   → connector shows "Connected".
7. New chat → tool picker shows `garmin` with all tools.
8. Try: *"check-session garmin"* — Claude calls the MCP tool over HTTPS to Fly.

To also wire ChatGPT (or a second Claude instance) to the same server without
sharing credentials, set an isolated second client via `OAUTH_CLIENT_ID_2` +
`OAUTH_CLIENT_SECRET_2` (and optionally `_3` for a third client) — see
`server.py` for how the extras are picked up.

### Rotating the OAuth Client Secret

If the secret leaks:
```powershell
$newSecret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 40 | ForEach-Object {[char]$_})
flyctl secrets set OAUTH_CLIENT_SECRET=$newSecret
flyctl ssh console -C "rm /data/oauth-state.json"   # wipe cached client + old tokens
flyctl apps restart garmin-mcp-YOURNAME
```
Then update the Client Secret in the Custom Connector UI → reconnect.

### Token refresh

`garminconnect` refreshes the OAuth2 access token silently via API (no
browser). The refresh gets written back to `TOKEN_DIR/garmin_tokens.json` on
the **volume** — survives restarts and redeploys. When OAuth1 expires (~1
year), run `test_login.py` locally, then re-seed:

```powershell
$garminTokens = Get-Content "$HOME\.garminconnect\garmin_tokens.json" -Raw
flyctl secrets set GARMIN_TOKENS_JSON=$garminTokens
flyctl ssh console -C "rm /data/garminconnect/garmin_tokens.json"
flyctl apps restart garmin-mcp-YOURNAME
```
(The `rm` forces the seed to re-fire; alternative: `flyctl ssh sftp` push the
file directly.)
