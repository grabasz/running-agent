"""Thin wrapper over aiosql. SQL queries live in `queries/*.sql`.

Usage:
    import api
    with api.connect() as conn:
        sid = api.gym.session_add(conn, date="2026-06-29", duration_min=90,
                                   hr_avg=None, hr_max=None, calories=None,
                                   context="Test", notes=None)
        sets = api.gym.exercise_progression(conn, exercise="RDL", limit=10)

Each .sql file in `queries/` is loaded as its own submodule (queries/gym.sql -> api.gym).
SQL function suffixes: `<!` returns lastrowid (INSERT), `^` one row, `$` scalar,
no suffix = list of rows (sqlite3.Row, dict-like).
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import aiosql

try:
    from .init_db import DB_PATH, get_connection
except ImportError:
    from init_db import DB_PATH, get_connection  # type: ignore

QDIR = Path(__file__).parent / "queries"

# ============================================
# Load queries per file (each file = own namespace)
# ============================================

def _load(name: str):
    return aiosql.from_path(QDIR / name, "sqlite3",
                            kwargs_only=False,
                            mandatory_parameters=False)

gym             = _load("gym.sql")
runs            = _load("runs.sql")
weekly_volume   = _load("weekly_volume.sql")
races           = _load("races.sql")
body            = _load("body.sql")
vdot            = _load("vdot.sql")
planned         = _load("planned.sql")
_stats          = _load("stats.sql")


# ============================================
# Connection helper (auto-commit / rollback)
# ============================================

@contextmanager
def connect():
    """Open a connection with auto-commit. Use `with api.connect() as conn:`."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================
# Higher-level helpers (multi-step operations)
# ============================================

def stats_summary() -> dict:
    """Row counts for all tables — sanity check / dashboard tile."""
    with connect() as conn:
        return {row["tbl"]: row["n"] for row in _stats.counts(conn)}


def race_pb(distance_km: float, tolerance: float = 0.5):
    """PB for given distance ±tolerance km (HM = 21.0975 ±0.5)."""
    with connect() as conn:
        return races.pb_for_distance(conn,
                                     min_km=distance_km - tolerance,
                                     max_km=distance_km + tolerance)


def recompute_pbs():
    """Reset and recompute is_pb flags for all races."""
    with connect() as conn:
        races.recompute_pbs(conn)
        races.flag_pbs(conn)
