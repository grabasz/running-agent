"""Two-way sync between local SQLite (data.db) and Turso cloud.

Strategy: keep aiosql + sqlite3 locally (fast, offline, no row_factory issues),
push/pull manually via libsql client. Call after every write operation to keep
cloud current.

Usage:
    python db/sync.py push     # local -> Turso (after writes)
    python db/sync.py pull     # Turso -> local (use on a new machine)
    python db/sync.py status   # compare row counts both ways

Or from Python:
    from db.sync import push, pull, status
    push()  # silent on success, prints diffs
"""
from __future__ import annotations
import os
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


def _turso():
    if not URL or not TOKEN:
        raise RuntimeError("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN not set in .env")
    return libsql.connect(URL, auth_token=TOKEN)


def _user_tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    # Both sqlite3 (Row) and libsql (tuple) work with [0]
    return [r[0] for r in rows]


def _row_count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# Table dependency order: parents first, then dependents (matters for FK constraints).
# Used by push/pull to avoid FK violations during DELETE+INSERT cycles.
TABLE_ORDER = [
    # Lookups (no FK deps)
    "workout_statuses",
    "workout_types",
    # Parents (no FK out)
    "gym_sessions",
    "runs",
    "races",
    "vdot_history",
    "weekly_volume",
    "body_state",
    "body_weight",
    # Dependents (FK to parents above)
    "gym_sets",          # -> gym_sessions
    "run_laps",          # -> runs
    "run_streams",       # -> runs
    "planned_workouts",  # -> workout_types, workout_statuses, runs, gym_sessions
]


def push(verbose: bool = True) -> dict:
    """Push local rows to Turso. Strategy: DELETE in reverse dep order, INSERT in dep order.

    Returns dict {table: rows_pushed} per table.
    """
    if not LOCAL_DB.exists():
        raise RuntimeError(f"Local DB not found at {LOCAL_DB}")

    local = sqlite3.connect(LOCAL_DB)
    local.row_factory = sqlite3.Row
    turso = _turso()

    out = {}
    try:
        # 1. Clear remote in reverse order (dependents first)
        for table in reversed(TABLE_ORDER):
            turso.execute(f"DELETE FROM {table}")

        # 2. Insert in forward order (parents first)
        for table in TABLE_ORDER:
            rows = local.execute(f"SELECT * FROM {table}").fetchall()
            if rows:
                cols = rows[0].keys()
                placeholders = ", ".join("?" for _ in cols)
                col_list = ", ".join(cols)
                sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
                for r in rows:
                    turso.execute(sql, tuple(r[c] for c in cols))
            out[table] = len(rows)
            if verbose:
                print(f"  push [{table:20}] {len(rows)} rows")
        turso.commit()
    finally:
        local.close()
    return out


def pull(verbose: bool = True) -> dict:
    """Pull all rows from Turso to local. Overwrites local data.

    Use on a fresh machine or to revert local changes.
    """
    turso = _turso()
    local = sqlite3.connect(LOCAL_DB)

    out = {}
    try:
        tables = _user_tables(turso)
        for table in tables:
            rows = turso.execute(f"SELECT * FROM {table}").fetchall()
            # Need column names — libsql cursor.description has them
            cur = turso.execute(f"SELECT * FROM {table}")
            cur.fetchone()
            cols = [d[0] for d in cur.description]
            local.execute(f"DELETE FROM {table}")
            if rows:
                placeholders = ", ".join("?" for _ in cols)
                col_list = ", ".join(cols)
                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
                local.executemany(sql, rows)
            out[table] = len(rows)
            if verbose:
                print(f"  pull [{table:20}] {len(rows)} rows")
        local.commit()
    finally:
        local.close()
    return out


def status() -> None:
    """Print row counts locally vs Turso (highlight diffs)."""
    if not LOCAL_DB.exists():
        print(f"Local DB not found at {LOCAL_DB}")
        return
    local = sqlite3.connect(LOCAL_DB)
    turso = _turso()
    try:
        local_tables = set(_user_tables(local))
        turso_tables = set(_user_tables(turso))
        all_tables = sorted(local_tables | turso_tables)

        print(f"{'table':22} {'local':>8} {'turso':>8}  diff")
        print("-" * 50)
        for t in all_tables:
            l = _row_count(local, t) if t in local_tables else "—"
            r = _row_count(turso, t) if t in turso_tables else "—"
            marker = ""
            if isinstance(l, int) and isinstance(r, int) and l != r:
                marker = f"  ⚠️ Δ={l - r}"
            print(f"{t:22} {l:>8} {r:>8}{marker}")
    finally:
        local.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "push":
        push()
    elif cmd == "pull":
        pull()
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print("Usage: python db/sync.py [push|pull|status]", file=sys.stderr)
        sys.exit(1)
