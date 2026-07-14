"""Env config for the Telegram bot."""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

BOT_DIR = Path(__file__).parent
load_dotenv(BOT_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

# Comma-separated whitelist. Empty list = deny everyone (fail closed).
_ids = os.environ.get("ALLOWED_USER_IDS", "").replace(" ", "")
ALLOWED_USER_IDS: set[int] = {int(x) for x in _ids.split(",") if x.isdigit()}

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()


def validate() -> list[str]:
    """Return list of missing/invalid env vars (empty = all good)."""
    problems = []
    if not TELEGRAM_BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN")
    if not TURSO_DATABASE_URL:
        problems.append("TURSO_DATABASE_URL")
    if not TURSO_AUTH_TOKEN:
        problems.append("TURSO_AUTH_TOKEN")
    if not ALLOWED_USER_IDS:
        problems.append("ALLOWED_USER_IDS (empty = bot rejects everyone)")
    return problems
