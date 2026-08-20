"""Wygeneruj 32-bajtowy klucz szyfrowania AES-256 (base64 urlsafe).

Uzycie:
    python db/generate_enc_key.py

Wynik wklej:
- Streamlit Cloud Secrets:     USER1_ENC_KEY = "..."   (Bartek user_id=1)
                                USER2_ENC_KEY = "..."   (Mati    user_id=2)
- Fly (per app):                flyctl -a garmin-mcp-grabb secrets set ENC_KEY="..."
                                flyctl -a garmin-mcp-mati  secrets set ENC_KEY="..."

Ten sam klucz MUSI byc wpisany w Streamlit (jako USER{id}_ENC_KEY)
i na odpowiedni Fly app (jako ENC_KEY) - inaczej AI iOS nie odczyta
notatek stworzonych z dashboard i odwrotnie.
"""
import base64
import secrets

key = secrets.token_bytes(32)
print(base64.urlsafe_b64encode(key).decode("ascii").rstrip("="))
