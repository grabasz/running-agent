"""Verify Garmin Connect OAuth login using credentials from Windows Credential Manager.

Handles 2FA/MFA by prompting for the code when Garmin returns needs_mfa.
On success, tokens are persisted to ~/.garminconnect/ (garth default) — next
runs (this script or the MCP server) will not need password OR MFA until
OAuth1 token expires (~1 year).

Run:
    python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\test_login.py
"""
from datetime import date
from pathlib import Path
import sys

try:
    import keyring
    from garminconnect import Garmin, GarminConnectAuthenticationError
except ImportError as e:
    print(f"ERROR: {e}. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

SERVICE = "garmin-mcp"
TOKEN_DIR = str(Path.home() / ".garminconnect")


def prompt_mfa() -> str:
    print()
    code = input("Podaj kod MFA (SMS/authenticator): ").strip()
    return code


def main() -> int:
    email = keyring.get_password(SERVICE, "email")
    password = keyring.get_password(SERVICE, "password")
    if not email or not password:
        print("ERROR: brak credentiali w Windows Credential Manager.", file=sys.stderr)
        print("Uruchom najpierw: python setup_credentials.py", file=sys.stderr)
        return 1

    print(f"Login: {email}")
    print(f"Token dir: {TOKEN_DIR}")
    print()

    # Try loading existing tokens first (silent OAuth2 refresh path)
    try:
        garmin = Garmin()
        garmin.login(TOKEN_DIR)
        print("[OK] Zalogowano z istniejacych tokenow (bez hasla, bez MFA).")
    except Exception as e:
        print(f"[INFO] Nie znaleziono zapisanych tokenow ({type(e).__name__}). Login pelny...")
        try:
            garmin = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
            # login(tokenstore) automatycznie zapisuje tokeny do wskazanego dir
            garmin.login(TOKEN_DIR)
            print(f"[OK] Login OK, tokeny zapisane w {TOKEN_DIR}")
        except GarminConnectAuthenticationError as auth_err:
            print(f"[FAIL] Auth error: {auth_err}", file=sys.stderr)
            return 2
        except Exception as gen_err:
            print(f"[FAIL] Unexpected: {type(gen_err).__name__}: {gen_err}", file=sys.stderr)
            import traceback; traceback.print_exc()
            return 3

    # Verification: fetch user profile + today's summary
    print()
    try:
        summary = garmin.get_user_summary(date.today().isoformat())
        print(f"[OK] Daily summary fetched. Steps: {summary.get('totalSteps', 'n/a')}, "
              f"Resting HR: {summary.get('restingHeartRate', 'n/a')}")
    except Exception as e:
        print(f"[FAIL] get_user_summary padlo: {e}", file=sys.stderr)
        return 4

    try:
        acts = garmin.get_activities(0, 3)
        print(f"[OK] Fetched last {len(acts)} activities:")
        for a in acts:
            print(f"    - {a.get('startTimeLocal','?')[:16]}  "
                  f"{a.get('activityType',{}).get('typeKey','?'):20s}  "
                  f"{(a.get('activityName') or '')[:40]}")
    except Exception as e:
        print(f"[FAIL] get_activities padlo: {e}", file=sys.stderr)
        return 5

    print()
    print("=== SUCCESS ===")
    print("Nastepne uruchomienia — instant (bez hasla, bez MFA).")
    print("Mozesz przejsc do Fazy 2 (MCP server).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
