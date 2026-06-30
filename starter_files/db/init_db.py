"""Initialize the SQLite database from schema.sql.

Usage:
    python db/init_db.py            # create if not exists
    python db/init_db.py --reset    # drop existing, recreate (DANGEROUS)

DB_PATH resolution:
    1. RUNNING_DB_PATH env var (explicit override — used by Streamlit Cloud
       to point at a writable replica file pulled from Turso).
    2. Default: <repo>/db/data.db (local development).
"""
import os
import sys
import sqlite3
from pathlib import Path

DB_DIR = Path(__file__).parent
SCHEMA_PATH = DB_DIR / "schema.sql"

_env_path = os.getenv("RUNNING_DB_PATH")
DB_PATH = Path(_env_path) if _env_path else DB_DIR / "data.db"


def init(reset: bool = False) -> Path:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"[reset] Deleted {DB_PATH}")

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)
    conn.commit()
    conn.close()
    print(f"[init] DB ready: {DB_PATH}")
    return DB_PATH


def get_connection() -> sqlite3.Connection:
    """Open a connection with sensible defaults (FK enabled, row factory = dict-like)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    init(reset=reset)
