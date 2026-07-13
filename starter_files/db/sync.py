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
    "planned_workout_components",  # -> planned_workouts, workout_statuses
]


def _is_stream_error(exc: BaseException) -> bool:
    msg = str(exc)
    return "stream not found" in msg or "stream expired" in msg or "STREAM_EXPIRED" in msg


def _push_table(local, table: str, mode: str, max_retries: int = 3):
    """Run DELETE or INSERT for a single table with a fresh Turso connection.

    Each call opens its own libsql connection so a dead Hrana stream from a prior
    table can't poison the next one. Retries transparently on stream-not-found errors.
    """
    for attempt in range(1, max_retries + 1):
        turso = _turso()
        try:
            if mode == "delete":
                turso.execute(f"DELETE FROM {table}")
                turso.commit()
                return 0
            # mode == "insert"
            rows = local.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                return 0
            cols = rows[0].keys()
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(cols)
            sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
            params = [tuple(r[c] for c in cols) for r in rows]
            turso.executemany(sql, params)
            turso.commit()
            return len(rows)
        except ValueError as e:
            if _is_stream_error(e) and attempt < max_retries:
                continue  # fresh connection on next iteration
            raise
        finally:
            try:
                turso.close()
            except Exception:
                pass


PRESET_AFTER = {
    # Skille pass `--after=run` etc. to push only the touched tables (+FK deps).
    # Order matters: subset preserves TABLE_ORDER; DELETE reverse, INSERT forward.
    "run":     ["runs", "run_laps", "planned_workouts", "planned_workout_components"],
    "gym":     ["gym_sessions", "gym_sets", "planned_workouts", "planned_workout_components"],
    "planned": ["planned_workouts", "planned_workout_components"],
    "volume":  ["weekly_volume"],
    "body":    ["body_state"],
    "vdot":    ["vdot_history", "races"],
}


def _local_row_count(local, table: str) -> int:
    try:
        return local.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0  # table missing


def push(verbose: bool = True, tables: list[str] | None = None,
         skip_empty: bool = True) -> dict:
    """Push local rows to Turso. DELETE reverse dep order, INSERT dep order.

    Each table runs on its own connection with executemany + per-table commit,
    which avoids Hrana stream expiry during long-running syncs (fix for the
    "stream not found" errors that used to strand run_laps mid-push).

    Args:
        verbose: print per-table row counts
        tables: restrict push to these tables only (must be subset of TABLE_ORDER).
                None = push all (backward compatible).
        skip_empty: skip DELETE+INSERT for tables that are empty locally
                    (they're already empty upstream after previous pushes).

    Returns dict {table: rows_pushed} per table (skipped tables absent).
    """
    if not LOCAL_DB.exists():
        raise RuntimeError(f"Local DB not found at {LOCAL_DB}")

    local = sqlite3.connect(LOCAL_DB)
    local.row_factory = sqlite3.Row

    if tables:
        # Filter to intersect + preserve TABLE_ORDER
        selected = [t for t in TABLE_ORDER if t in tables]
        unknown = set(tables) - set(TABLE_ORDER)
        if unknown:
            raise ValueError(f"Unknown tables: {sorted(unknown)}")
    else:
        selected = TABLE_ORDER

    if skip_empty:
        selected = [t for t in selected if _local_row_count(local, t) > 0]
        if not selected and verbose:
            print("  (nothing to push — all selected tables empty locally)")

    out = {}
    try:
        for table in reversed(selected):
            _push_table(local, table, "delete")

        for table in selected:
            n = _push_table(local, table, "insert")
            out[table] = n
            if verbose:
                print(f"  push [{table:20}] {n} rows")
    finally:
        local.close()
    return out


def _pull_table(local, table: str, max_retries: int = 3):
    """Pull rows for one table with a fresh Turso connection + retry on stream expiry.

    Fresh connection per table avoids the Hrana stream from the previous
    table (or a stale replica after long inactivity) poisoning the next one.
    Single SELECT per table — description + rows off the same cursor.
    """
    for attempt in range(1, max_retries + 1):
        turso = _turso()
        try:
            cur = turso.execute(f"SELECT * FROM {table}")
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]

            local.execute(f"DELETE FROM {table}")
            if rows:
                placeholders = ", ".join("?" for _ in cols)
                col_list = ", ".join(cols)
                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
                local.executemany(sql, rows)
            return len(rows)
        except ValueError as e:
            if _is_stream_error(e) and attempt < max_retries:
                continue  # fresh connection on next iteration
            raise
        finally:
            try:
                turso.close()
            except Exception:
                pass


def pull(verbose: bool = True) -> dict:
    """Pull all rows from Turso to local. Overwrites local data.

    Use on a fresh machine or to revert local changes. Per-table fresh
    connection + retry on Hrana stream expiry (same fix as push).
    """
    # Table list requires one connection — retried on stream errors.
    for attempt in range(1, 4):
        turso = _turso()
        try:
            tables = _user_tables(turso)
            break
        except ValueError as e:
            if _is_stream_error(e) and attempt < 3:
                continue
            raise
        finally:
            try:
                turso.close()
            except Exception:
                pass

    local = sqlite3.connect(LOCAL_DB)
    out = {}
    try:
        for table in tables:
            n = _pull_table(local, table)
            out[table] = n
            if verbose:
                print(f"  pull [{table:20}] {n} rows")
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
    import argparse
    try:
        from .perf import log_run  # package-relative when imported
    except ImportError:
        sys.path.insert(0, str(HERE))
        from perf import log_run  # type: ignore

    parser = argparse.ArgumentParser(prog="db.sync")
    parser.add_argument("cmd", choices=["push", "pull", "status"])
    parser.add_argument("--after", choices=list(PRESET_AFTER.keys()),
                        help="Push only tables touched by this skill (e.g. run, gym, planned).")
    parser.add_argument("--tables", help="Comma-separated table names to push.")
    parser.add_argument("--no-skip-empty", action="store_true",
                        help="Push empty tables too (default: skip).")
    args = parser.parse_args()

    perf_args = {"after": args.after, "tables": args.tables,
                 "no_skip_empty": args.no_skip_empty}
    perf_args = {k: v for k, v in perf_args.items() if v}

    with log_run(f"db.sync {args.cmd}", args=perf_args):
        if args.cmd == "push":
            tables = None
            if args.after:
                tables = PRESET_AFTER[args.after]
            elif args.tables:
                tables = [t.strip() for t in args.tables.split(",") if t.strip()]
            push(tables=tables, skip_empty=not args.no_skip_empty)
        elif args.cmd == "pull":
            pull()
        elif args.cmd == "status":
            status()
