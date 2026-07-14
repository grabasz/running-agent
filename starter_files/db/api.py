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

Cloud mode: call `api.bootstrap_cloud()` once before any query to pull the latest
snapshot from Turso into a local replica file (used by the Streamlit Cloud dashboard).
"""
from __future__ import annotations
import os
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
tasks           = _load("tasks.sql")
goals           = _load("goals.sql")
notes           = _load("notes.sql")
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


# ============================================
# Cloud bootstrap (Streamlit Cloud / read-only mirrors)
# ============================================

def bootstrap_cloud(force: bool = False) -> Path | None:
    """If TURSO_DATABASE_URL is set, pull a fresh snapshot from Turso into a
    local replica file and point DB_PATH at it. Idempotent within a process —
    pass force=True to re-pull.

    Returns the replica Path, or None when no cloud env is configured (local mode).
    """
    if not os.getenv("TURSO_DATABASE_URL"):
        return None  # local mode — DB_PATH already points at db/data.db

    global DB_PATH
    if not force and getattr(bootstrap_cloud, "_done", False):
        return DB_PATH

    # Import here so local-only installs don't need libsql / sync.py imports at module load.
    try:
        from .sync import pull as _pull, LOCAL_DB as _LOCAL_DB
        from . import init_db as _init_db
        from . import sync as _sync
    except ImportError:
        import sync as _sync  # type: ignore
        import init_db as _init_db  # type: ignore
        from sync import pull as _pull  # type: ignore

    # Replica file path: respect RUNNING_DB_PATH if set (e.g. /tmp on Streamlit Cloud),
    # otherwise default next to db/ as data_replica.db.
    replica = Path(os.getenv("RUNNING_DB_PATH") or (Path(__file__).parent / "data_replica.db"))
    replica.parent.mkdir(parents=True, exist_ok=True)

    # Make sync.py write to the replica, not the dev data.db.
    _sync.LOCAL_DB = replica
    # Materialise schema first so pull's DELETE/INSERT has tables to target.
    # reset=True: replica is disposable — wipe any stale schema from a previous deploy
    # (otherwise a leftover replica file will miss tables added by newer migrations).
    _init_db.DB_PATH = replica
    _init_db.init(reset=True)

    _pull(verbose=False)

    DB_PATH = replica
    _init_db.DB_PATH = replica
    bootstrap_cloud._done = True  # type: ignore[attr-defined]
    return replica
