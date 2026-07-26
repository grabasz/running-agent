"""One-time interactive script to save Garmin Connect email + password
to Windows Credential Manager (via keyring). Run in PowerShell:

    python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\setup_credentials.py

The password is DPAPI-encrypted by Windows. Nothing lands in plaintext files.
"""
from getpass import getpass
import sys

try:
    import keyring
except ImportError:
    print("ERROR: keyring not installed. Run: pip install keyring", file=sys.stderr)
    sys.exit(1)

SERVICE = "garmin-mcp"
DEFAULT_EMAIL = "grabbartek@gmail.com"


def main() -> int:
    print("=== Garmin MCP: setup credentials ===")
    print("Zapisuje email + haslo do Windows Credential Manager.")
    print()

    current_email = keyring.get_password(SERVICE, "email")
    if current_email:
        print(f"Aktualny email: {current_email}")
        keep = input("Zostawic ten email? [Y/n]: ").strip().lower()
        if keep in ("", "y", "yes", "t", "tak"):
            email = current_email
        else:
            email = input(f"Nowy email [{DEFAULT_EMAIL}]: ").strip() or DEFAULT_EMAIL
    else:
        email = input(f"Email [{DEFAULT_EMAIL}]: ").strip() or DEFAULT_EMAIL

    password = getpass("Haslo (nie widoczne): ")
    if not password:
        print("Bledne haslo (puste). Abort.", file=sys.stderr)
        return 1

    keyring.set_password(SERVICE, "email", email)
    keyring.set_password(SERVICE, "password", password)

    print()
    print(f"OK. Email zapisany dla service='{SERVICE}'.")
    print(f"Haslo zapisane (DPAPI-encrypted w Windows Credential Manager).")
    print()
    print("Nastepny krok:")
    print("  python C:\\Users\\grabb\\.mcp-servers\\garmin-oauth\\test_login.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
