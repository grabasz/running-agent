"""Shared utilities for the Garmin MCP server.

Modularized from server.py:
- Constants: TOKEN_DIR, USER_ID, allowed enums for notes/tasks
- Garmin client singleton (lazy) + _wrap_401 decorator
- Turso lazy connection + _tq/_tx query helpers
- _monday(), _dumps(), _seed_tokens_from_env()

Kept behavior-identical to pre-split server.py — this is a pure move.
"""
from __future__ import annotations
import functools
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

# Use Windows Certificate Store (via truststore) instead of bundled certifi.
# See server.py rationale — must be injected BEFORE requests/urllib3 import,
# so this happens at db_common import (which every module transitively imports).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass

try:
    from garminconnect import Garmin, GarminConnectAuthenticationError  # noqa: F401
except ImportError:
    print("Missing garminconnect. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


TOKEN_DIR = os.environ.get("TOKEN_DIR") or str(Path.home() / ".garminconnect")

# Multi-tenant: which DB user this MCP instance operates on.
# Default 1 (Bartek) for backward compat with existing deploys / local dev.
# Set USER_ID=2 for Matiego's Fly deploy, etc.
USER_ID = int(os.environ.get("USER_ID", "1"))


# Enum allowlists shared between write tools.
_ALLOWED_NOTE_CATEGORIES = ("insight", "decision", "reminder", "idea", "observation")
_ALLOWED_TASK_CATEGORIES = ("sport", "praca", "dom", "relacje", "zdrowie", "inne")
_ALLOWED_TASK_PRIORITIES = ("low", "medium", "high")
_ALLOWED_EXERCISE_CATEGORIES = ("rolowanie", "aktywacja", "stretch", "wzmocnienie", "kardio")


def _seed_tokens_from_env() -> None:
    """First-boot bootstrap for cloud deploy.

    If TOKEN_DIR has no garmin_tokens.json but env var GARMIN_TOKENS_JSON is set,
    write it to disk once. After that OAuth2 refresh writes update the volume
    normally, so this only runs on a fresh machine/volume.
    """
    tokens_path = Path(TOKEN_DIR) / "garmin_tokens.json"
    if tokens_path.exists():
        return
    seed = os.environ.get("GARMIN_TOKENS_JSON")
    if not seed:
        return
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    tokens_path.write_text(seed, encoding="utf-8")
    print(f"[seed] wrote {tokens_path} from GARMIN_TOKENS_JSON env", file=sys.stderr)


# ----------------------------------------------------------------------------
# Garmin client singleton
# ----------------------------------------------------------------------------

_client: "Garmin | None" = None


def _get_client() -> "Garmin":
    """Lazy singleton — loads OAuth tokens once, refreshes OAuth2 silently on expiry."""
    global _client
    if _client is None:
        c = Garmin()
        c.login(TOKEN_DIR)
        _client = c
    return _client


def _reset_client() -> None:
    global _client
    _client = None


# ----------------------------------------------------------------------------
# JSON + 401-retry decorator
# ----------------------------------------------------------------------------

def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _wrap_401(fn):
    """Decorator: on 401 reset client + retry once. Preserves signature for FastMCP."""
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "unauthor" in msg:
                _reset_client()
                try:
                    return fn(*args, **kwargs)
                except Exception as e2:
                    return _dumps({
                        "status": "error",
                        "message": f"{type(e2).__name__}: {e2}",
                        "fix": "Run: python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\test_login.py",
                    })
            return _dumps({"status": "error", "message": f"{type(e).__name__}: {e}"})
    inner.__signature__ = inspect.signature(fn)
    return inner


# ----------------------------------------------------------------------------
# Turso (libsql) connection + query helpers
# ----------------------------------------------------------------------------

_turso_conn = None


def _turso():
    """Lazy libsql connection to Turso. Re-created on failure."""
    global _turso_conn
    if _turso_conn is None:
        import libsql
        url = os.environ.get("TURSO_DATABASE_URL")
        token = os.environ.get("TURSO_AUTH_TOKEN")
        if not url or not token:
            raise RuntimeError("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN not set")
        _turso_conn = libsql.connect(url, auth_token=token)
    return _turso_conn


def _tq(sql: str, params=None):
    """Turso query returning list[dict]. Params can be tuple (?) or dict (:name)."""
    cur = _turso().execute(sql, params or ())
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _tx(sql: str, params=None) -> dict:
    """Turso write. Returns {'rowcount': N, 'lastrowid': X}."""
    conn = _turso()
    cur = conn.execute(sql, params or ())
    conn.commit()
    return {"rowcount": cur.rowcount, "lastrowid": cur.lastrowid}


def _monday(d: "str | None" = None) -> str:
    """Get Monday-anchored week_start for a given date (or today)."""
    from datetime import date as _d, timedelta
    day = _d.fromisoformat(d) if d else _d.today()
    return (day - timedelta(days=day.weekday())).isoformat()
