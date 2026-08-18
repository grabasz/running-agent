"""OAuth 2.1 provider for HTTP transport.

Serves MCP over streamable-http with OAuth 2.1 so Claude Custom Connectors
(and equivalent ChatGPT connectors) can authenticate. Single-user auto-approve:
no consent screen, DCR disabled, state persisted on disk.

Moved verbatim from server.py — behavior identical.
"""
from __future__ import annotations
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

from db_common import TOKEN_DIR, USER_ID


class _OAuthState:
    """Persistent OAuth state (clients + tokens) on disk.

    Access tokens are short-lived (1h) — surviving restarts is nice-to-have.
    Refresh tokens + registered clients MUST survive so Claude does not have
    to re-register after every machine sleep/restart on Fly.
    """

    def __init__(self, path: Path):
        self.path = path
        self.clients: dict[str, Any] = {}
        self.auth_codes: dict[str, Any] = {}
        self.access_tokens: dict[str, Any] = {}
        self.refresh_tokens: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        from mcp.shared.auth import OAuthClientInformationFull
        from mcp.server.auth.provider import AccessToken, RefreshToken
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[oauth] failed to load state: {e}", file=sys.stderr)
            return
        for cid, c in data.get("clients", {}).items():
            self.clients[cid] = OAuthClientInformationFull.model_validate(c)
        for tok, at in data.get("access_tokens", {}).items():
            self.access_tokens[tok] = AccessToken.model_validate(at)
        for tok, rt in data.get("refresh_tokens", {}).items():
            self.refresh_tokens[tok] = RefreshToken.model_validate(rt)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "clients": {k: v.model_dump(mode="json") for k, v in self.clients.items()},
            "access_tokens": {k: v.model_dump(mode="json") for k, v in self.access_tokens.items()},
            "refresh_tokens": {k: v.model_dump(mode="json") for k, v in self.refresh_tokens.items()},
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
        tmp.replace(self.path)


def _lenient_claude_client(client_info):
    """Return a client instance that accepts any redirect_uri under known MCP hosts.

    We pre-register the client with a placeholder redirect_uris entry (pydantic
    won't accept empty), then swap in this subclass when the SDK loads it —
    Claude/ChatGPT actual callback URLs vary per org / per connector and are
    not documented up-front. Unknown hosts fall through to parent which enforces
    the list.
    """
    from mcp.shared.auth import OAuthClientInformationFull

    ALLOWED_PREFIXES = (
        "https://claude.ai/",
        "https://claude.com/",
        "https://chatgpt.com/",
        "https://chat.openai.com/",
    )

    class _LenientClient(OAuthClientInformationFull):
        def validate_redirect_uri(self, redirect_uri):
            if redirect_uri is not None:
                s = str(redirect_uri).lower()
                if any(s.startswith(p) for p in ALLOWED_PREFIXES):
                    return redirect_uri
            return super().validate_redirect_uri(redirect_uri)

    return _LenientClient(**client_info.model_dump())


class SimpleOAuthProvider:
    """Single-user OAuth 2.1 provider with auto-approve.

    - Dynamic Client Registration disabled — clients must be pre-registered
      via OAUTH_CLIENT_ID + OAUTH_CLIENT_SECRET env (see run_http).
    - `authorize` auto-issues an auth code without a consent screen — this
      server is personal, only the owner will ever hit it, and the client
      secret at /token is the real security boundary.
    - Access token 1h TTL; refresh token long-lived.
    """

    def __init__(self, state: _OAuthState):
        self.state = state

    async def get_client(self, client_id: str):
        c = self.state.clients.get(client_id)
        if c is None:
            return None
        return _lenient_claude_client(c)

    async def register_client(self, client_info) -> None:
        self.state.clients[client_info.client_id] = client_info
        self.state.save()

    async def authorize(self, client, params) -> str:
        from mcp.server.auth.provider import AuthorizationCode, construct_redirect_uri
        code = "ac_" + secrets.token_urlsafe(32)
        self.state.auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject="owner",
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client, authorization_code: str):
        ac = self.state.auth_codes.get(authorization_code)
        if ac and ac.expires_at > time.time() and ac.client_id == client.client_id:
            return ac
        return None

    async def exchange_authorization_code(self, client, ac):
        self.state.auth_codes.pop(ac.code, None)
        return self._issue(client.client_id, ac.scopes, ac.resource)

    async def load_refresh_token(self, client, refresh_token: str):
        rt = self.state.refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(self, client, rt, scopes):
        self.state.refresh_tokens.pop(rt.token, None)
        return self._issue(client.client_id, scopes or rt.scopes, None)

    async def load_access_token(self, token: str):
        at = self.state.access_tokens.get(token)
        if at and (at.expires_at is None or at.expires_at > time.time()):
            return at
        return None

    async def revoke_token(self, token) -> None:
        from mcp.server.auth.provider import AccessToken, RefreshToken
        if isinstance(token, AccessToken):
            self.state.access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self.state.refresh_tokens.pop(token.token, None)
        self.state.save()

    def _issue(self, client_id: str, scopes: list[str], resource):
        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthToken
        at_tok = "at_" + secrets.token_urlsafe(32)
        rt_tok = "rt_" + secrets.token_urlsafe(32)
        now = int(time.time())
        self.state.access_tokens[at_tok] = AccessToken(
            token=at_tok, client_id=client_id, scopes=scopes,
            expires_at=now + 3600, resource=resource,
        )
        self.state.refresh_tokens[rt_tok] = RefreshToken(
            token=rt_tok, client_id=client_id, scopes=scopes,
        )
        self.state.save()
        return OAuthToken(
            access_token=at_tok, token_type="Bearer", expires_in=3600,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=rt_tok,
        )


def run_http(mcp, host: str, port: int) -> None:
    """Serve MCP over streamable-http with OAuth 2.1 (for Claude Custom Connectors)."""
    try:
        import uvicorn
        from starlette.responses import JSONResponse
        from pydantic import AnyHttpUrl
        from mcp.server.transport_security import TransportSecuritySettings
        from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions  # noqa: F401
        from mcp.server.auth.provider import ProviderTokenVerifier
    except ImportError as e:
        print(f"HTTP mode requires extra deps: {e}", file=sys.stderr)
        sys.exit(1)

    fly_app = os.environ.get("FLY_APP_NAME", "garmin-mcp-grabb")
    fly_host = f"{fly_app}.fly.dev"
    issuer_url = os.environ.get("OAUTH_ISSUER_URL", f"https://{fly_host}")

    mcp.settings.transport_security = TransportSecuritySettings(
        allowed_hosts=[fly_host, "127.0.0.1:*", "localhost:*"],
        allowed_origins=[f"https://{fly_host}", "http://127.0.0.1:*", "http://localhost:*"],
    )

    oauth_client_id = os.environ.get("OAUTH_CLIENT_ID", "claude-connector")
    oauth_client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
    if not oauth_client_secret:
        print("HTTP mode requires OAUTH_CLIENT_SECRET (set via `flyctl secrets set`)",
              file=sys.stderr)
        sys.exit(1)

    # Optional second client (e.g. ChatGPT connector) for isolation from Claude.
    extra_clients = []
    for suffix in ("_2", "_3"):
        cid = os.environ.get(f"OAUTH_CLIENT_ID{suffix}")
        csec = os.environ.get(f"OAUTH_CLIENT_SECRET{suffix}")
        if cid and csec:
            extra_clients.append((cid, csec, f"Connector{suffix}"))

    state_path = Path(os.environ.get("OAUTH_STATE_PATH") or (Path(TOKEN_DIR).parent / "oauth-state.json"))
    state = _OAuthState(state_path)

    # Pre-register the allowed clients. Purge any others (leftover DCR
    # registrations from before this security tightening).
    from mcp.shared.auth import OAuthClientInformationFull
    allowed_cids = {oauth_client_id, *(c[0] for c in extra_clients)}
    stale = [cid for cid in state.clients if cid not in allowed_cids]
    for cid in stale:
        print(f"[oauth] purging stale client {cid}", file=sys.stderr)
        state.clients.pop(cid)

    def _upsert(cid, csec, name, redirect_placeholder):
        existing = state.clients.get(cid)
        if existing is None or existing.client_secret != csec:
            state.clients[cid] = OAuthClientInformationFull(
                client_id=cid,
                client_secret=csec,
                redirect_uris=[AnyHttpUrl(redirect_placeholder)],
                token_endpoint_auth_method="client_secret_post",
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope="mcp",
                client_name=name,
            )

    _upsert(oauth_client_id, oauth_client_secret,
            "Claude Custom Connector", "https://claude.ai/api/mcp/auth_callback")
    for cid, csec, _name in extra_clients:
        # Placeholder redirect only for pydantic validation; real URI is
        # accepted by _lenient_claude_client via prefix allowlist.
        _upsert(cid, csec, cid, "https://chatgpt.com/connector/oauth/placeholder")
    state.save()

    provider = SimpleOAuthProvider(state)

    mcp.settings.auth = AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        resource_server_url=AnyHttpUrl(issuer_url),
        client_registration_options=None,
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=[],
    )
    mcp._auth_server_provider = provider
    mcp._token_verifier = ProviderTokenVerifier(provider)

    app = mcp.streamable_http_app()

    async def health(_request):
        return JSONResponse({"status": "ok", "user_id": USER_ID})
    app.router.add_route("/health", health, methods=["GET"])

    uvicorn.run(app, host=host, port=port, log_level="info")
