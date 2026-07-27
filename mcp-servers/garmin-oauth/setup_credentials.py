"""One-time interactive script to save Garmin Connect email + password
to a local secret store. Run from this folder:

    python setup_credentials.py

On Windows the password is DPAPI-encrypted by Credential Manager (via keyring).
On macOS keyring uses the Keychain, on Linux it uses SecretService if available.
Nothing is written in plaintext by this script.

If you prefer to keep credentials in an .env file for a headless/server
install, set GARMIN_EMAIL + GARMIN_PASSWORD in the environment instead of
running this script — server.py reads env vars as a fallback.
"""
import os
from getpass import getpass
from pathlib import Path
import sys

try:
    import keyring
except ImportError:
    print("ERROR: keyring not installed. Run: pip install keyring", file=sys.stderr)
    sys.exit(1)

SERVICE = os.environ.get("GARMIN_KEYRING_SERVICE", "garmin-mcp")


def main() -> int:
    print(f"=== Garmin MCP: setup credentials (service='{SERVICE}') ===")
    print("Saves Garmin Connect email + password to your OS secret store via keyring.")
    print()

    current_email = keyring.get_password(SERVICE, "email")
    if current_email:
        print(f"Current email: {current_email}")
        keep = input("Keep this email? [Y/n]: ").strip().lower()
        if keep in ("", "y", "yes"):
            email = current_email
        else:
            email = input("New email: ").strip()
    else:
        email = input("Garmin Connect email: ").strip()

    if not email:
        print("Empty email. Abort.", file=sys.stderr)
        return 1

    password = getpass("Password (hidden): ")
    if not password:
        print("Empty password. Abort.", file=sys.stderr)
        return 1

    keyring.set_password(SERVICE, "email", email)
    keyring.set_password(SERVICE, "password", password)

    print()
    print(f"OK. Email saved for service='{SERVICE}'.")
    print("Password saved to your OS secret store (DPAPI/Keychain/SecretService).")
    print()
    print("Next step: complete OAuth login (handles MFA if enabled on your account):")
    print(f"  python {Path(__file__).with_name('test_login.py').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
