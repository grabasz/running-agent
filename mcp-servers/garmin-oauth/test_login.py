"""Verify Garmin Connect OAuth login using credentials stored via keyring.

Handles 2FA/MFA by prompting for the code when Garmin returns needs_mfa.
On success, tokens are persisted to ~/.garminconnect/ (garth default) — next
runs (this script or the MCP server) will not need password OR MFA until
OAuth1 token expires (~1 year).

Run from this folder:
    python test_login.py
"""
import os
from datetime import date
from pathlib import Path
import sys

try:
    import keyring
    from garminconnect import Garmin, GarminConnectAuthenticationError
except ImportError as e:
    print(f"ERROR: {e}. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

SERVICE = os.environ.get("GARMIN_KEYRING_SERVICE", "garmin-mcp")
TOKEN_DIR = os.environ.get("GARMIN_TOKEN_DIR", str(Path.home() / ".garminconnect"))


def prompt_mfa() -> str:
    print()
    code = input("Enter MFA code (SMS / authenticator app): ").strip()
    return code


def main() -> int:
    # Prefer explicit env vars (for headless / server installs), fall back to keyring.
    email = os.environ.get("GARMIN_EMAIL") or keyring.get_password(SERVICE, "email")
    password = os.environ.get("GARMIN_PASSWORD") or keyring.get_password(SERVICE, "password")
    if not email or not password:
        print("ERROR: no credentials found.", file=sys.stderr)
        print("Either:", file=sys.stderr)
        print("  - run: python setup_credentials.py    (interactive keyring)", file=sys.stderr)
        print("  - or set env vars GARMIN_EMAIL + GARMIN_PASSWORD", file=sys.stderr)
        return 1

    print(f"Login: {email}")
    print(f"Token dir: {TOKEN_DIR}")
    print()

    # Try loading existing tokens first (silent OAuth2 refresh path)
    try:
        garmin = Garmin()
        garmin.login(TOKEN_DIR)
        print("[OK] Logged in from saved tokens (no password, no MFA).")
    except Exception as e:
        print(f"[INFO] No saved tokens found ({type(e).__name__}). Full login...")
        try:
            garmin = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
            garmin.login(TOKEN_DIR)
            print(f"[OK] Login OK, tokens saved to {TOKEN_DIR}")
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
        print(f"[FAIL] get_user_summary failed: {e}", file=sys.stderr)
        return 4

    try:
        acts = garmin.get_activities(0, 3)
        print(f"[OK] Fetched last {len(acts)} activities:")
        for a in acts:
            print(f"    - {a.get('startTimeLocal','?')[:16]}  "
                  f"{a.get('activityType',{}).get('typeKey','?'):20s}  "
                  f"{(a.get('activityName') or '')[:40]}")
    except Exception as e:
        print(f"[FAIL] get_activities failed: {e}", file=sys.stderr)
        return 5

    print()
    print("=== SUCCESS ===")
    print("Subsequent runs will be instant (no password, no MFA).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
