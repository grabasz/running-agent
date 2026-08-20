"""Symmetric encryption utilities for user-private fields.

Model: AES-256-GCM (authenticated encryption), per-user 32-byte key.

Klucz przechowywany w env:
  - Dashboard (Streamlit Cloud): USER1_ENC_KEY / USER2_ENC_KEY per user
  - MCP na Fly per app: ENC_KEY (garmin-mcp-grabb ma klucz Bartka,
    garmin-mcp-mati ma klucz Matiego)

Fields z prefixem 'enc:v1:' są szyfrowane. Bez prefixu = plaintext
(backward compat dla istniejących danych — dopóki nie uruchomisz
migrate_encrypt_existing.py).

Bez klucza + z prefixem -> [ENCRYPTED — brak klucza] (nie deszyfruje).
Bez klucza przy write -> plaintext (nie szyfruje — zero-config fallback).
"""
from __future__ import annotations

import base64
import os
import secrets as _secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC_PREFIX = "enc:v1:"


def _b64pad(s: str) -> str:
    return s + "=" * (-len(s) % 4)


def get_key_for_user(user_id: int) -> bytes | None:
    """Klucz szyfrowania z env. None = szyfrowanie wyłączone dla tego usera."""
    key_str = os.environ.get(f"USER{user_id}_ENC_KEY") or os.environ.get("ENC_KEY")
    if not key_str:
        return None
    raw = base64.urlsafe_b64decode(_b64pad(key_str))
    if len(raw) < 32:
        raise ValueError(f"ENC key za krótki: {len(raw)}B (potrzeba ≥32B)")
    return raw[:32]


def encrypt(plaintext: str, key: bytes) -> str:
    aesgcm = AESGCM(key)
    nonce = _secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return MAGIC_PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt(ciphertext: str, key: bytes) -> str:
    if not ciphertext.startswith(MAGIC_PREFIX):
        return ciphertext
    blob = base64.urlsafe_b64decode(_b64pad(ciphertext[len(MAGIC_PREFIX):]))
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


def maybe_decrypt(value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith(MAGIC_PREFIX):
        return value
    key = get_key_for_user(user_id)
    if key is None:
        return "[ENCRYPTED — brak klucza]"
    try:
        return decrypt(value, key)
    except Exception:
        return "[ENCRYPTED — błąd deszyfracji]"


def maybe_encrypt(value: str | None, user_id: int) -> str | None:
    if value is None:
        return value
    if not isinstance(value, str) or not value.strip():
        return value
    if value.startswith(MAGIC_PREFIX):
        return value
    key = get_key_for_user(user_id)
    if key is None:
        return value
    return encrypt(value, key)
