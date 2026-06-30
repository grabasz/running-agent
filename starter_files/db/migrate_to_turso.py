"""One-shot migration: local SQLite (data.db) -> Turso cloud.

Usage:
    python db/migrate_to_turso.py            # apply schema + copy all data
    python db/migrate_to_turso.py --schema   # only schema (no data)
    python db/migrate_to_turso.py --reset    # drop all Turso tables first, then schema + data
"""
from __future__ import annotations
import os
import re
import sys
import sqlite3
from pathlib import Path

import libsql
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

URL = os.getenv("TURSO_DATABASE_URL")
TOKEN = os.getenv("TURSO_AUTH_TOKEN")
LOCAL_DB = HERE / "data.db"
SCHEMA_PATH = HERE / "schema.sql"

if not URL or not TOKEN:
    print("ERROR: TURSO_DATABASE_URL / TURSO_AUTH_TOKEN not set in .env", file=sys.stderr)
    sys.exit(1)


def split_statements(sql: str) -> list[str]:
    """Split SQL into individual statements (by semicolon, skipping comments/blanks)."""
    # Strip line comments
    cleaned = re.sub(r"--[^\n]*", "", sql)
    parts = [s.strip() for s in cleaned.split(";")]
    return [s for s in parts if s and not s.lower().startswith("pragma")]


def apply_schema(conn):
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = split_statements(schema)
    print(f"[schema] applying {len(statements)} statements...")
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()
    print("[schema] done")


def reset_tables(conn):
    """Drop all user tables from Turso (before re-applying schema)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    if not rows:
        print("[reset] no tables to drop")
        return
    print(f"[reset] dropping {len(rows)} tables...")
    for r in rows:
        conn.execute(f"DROP TABLE IF EXISTS {r[0]}")
    conn.commit()


def copy_data(turso, local):
    """Copy all rows from local SQLite tables -> Turso."""
    local.row_factory = sqlite3.Row
    tables = [r[0] for r in local.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    for table in tables:
        rows = local.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  [{table:20}] 0 rows  (skip)")
            continue
        cols = rows[0].keys()
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
        for r in rows:
            turso.execute(sql, tuple(r[c] for c in cols))
        turso.commit()
        print(f"  [{table:20}] {len(rows)} rows -> Turso")


def main():
    reset = "--reset" in sys.argv
    only_schema = "--schema" in sys.argv

    turso = libsql.connect(URL, auth_token=TOKEN)
    print(f"[turso] connected: {URL}")

    if reset:
        reset_tables(turso)

    apply_schema(turso)

    if only_schema:
        print("[done] schema only (no data)")
        return

    if not LOCAL_DB.exists():
        print(f"[warn] local DB not found at {LOCAL_DB}; skipping data copy")
        return

    print(f"\n[data] copying from {LOCAL_DB}...")
    local = sqlite3.connect(LOCAL_DB)
    try:
        copy_data(turso, local)
    finally:
        local.close()

    # Final stats
    print("\n[done] Turso table sizes:")
    rows = turso.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for r in rows:
        n = turso.execute(f"SELECT COUNT(*) FROM {r[0]}").fetchone()[0]
        print(f"  {r[0]:20} {n}")


if __name__ == "__main__":
    main()
