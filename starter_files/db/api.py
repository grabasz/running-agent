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

Cloud mode (Streamlit Cloud, dashboard direct-Turso):
    Ustaw env TURSO_DATABASE_URL + TURSO_AUTH_TOKEN — api.connect() zwraca
    libsql connection wrapped w adapter kompatybilny z aiosql (sqlite3.Row-like).
    Cache queries via @st.cache_data(ttl=60) — Turso hit tylko przy invalidation.
Local mode:
    Bez env → sqlite3 na db/data.db (Bartek/skille /run /gym /volume).
"""
from __future__ import annotations
import os
import re
from contextlib import contextmanager
from pathlib import Path
import aiosql

# Auto-load db/.env przy imporcie modulu — zeby skille (/run, /gym, /volume itd.)
# automatycznie widzialy TURSO_DATABASE_URL bez rownczesnego source'owania env.
# Po tym: import api -> connect() automatycznie idzie direct do Turso (libsql)
# zamiast do lokalnego sqlite3. Sync.py jest wtedy niepotrzebny w codziennym flow.
# Na Streamlit Cloud env przychodza przez st.secrets (dotenv no-op bo brak .env).
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # dotenv opcjonalny — bez niego dziala fallback na sqlite3 local

# Regex do konwersji :name -> ? dla libsql (bo libsql nie akceptuje dict params).
# Nie matchuje '::' (postgres cast) i pomija miejsca po znaku alfanumerycznym/':'.
_NAMED_PARAM_RE = re.compile(r"(?<![:\w]):(\w+)")


def _named_to_positional(sql: str, params: dict):
    """Konwertuj SQL z :name na ? i buduj tuple wartosci w kolejnosci wystapien."""
    order: list[str] = []

    def _repl(m):
        order.append(m.group(1))
        return "?"

    new_sql = _NAMED_PARAM_RE.sub(_repl, sql)
    try:
        values = tuple(params[k] for k in order)
    except KeyError as e:
        raise KeyError(f"Missing param {e} for SQL: {sql[:100]}...")
    return new_sql, values

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
# libsql adapter — aiosql-kompatybilny wrapper dla Turso.
# Robi z libsql.Connection cos co wyglada jak sqlite3.Connection:
# - .execute()/.executemany() zwracaja Cursor z .fetchone/.fetchall
#   dostajacym rows dict-like (indexowane i po nazwie kolumny, .keys()).
# - .row_factory setowalne (aiosql to robi) - noop, my juz mamy Row-like.
# - .commit/.rollback/.close - delegowane.
# ============================================

class _LibsqlRow:
    """Row dict-like: row[0], row['col'], row.keys() — pasuje do dashboard [dict(r) for r in rows]."""
    __slots__ = ("_cols", "_data")

    def __init__(self, cols, data):
        self._cols = cols
        self._data = tuple(data)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[key]
        try:
            return self._data[self._cols.index(key)]
        except ValueError:
            raise KeyError(key)

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return f"Row({dict(zip(self._cols, self._data))!r})"


class _LibsqlCursor:
    """Wrapper cursora libsql: dict-like rows + akceptacja dict params (:name -> ?)."""

    def __init__(self, real_cursor):
        self._cur = real_cursor

    @property
    def lastrowid(self):
        return getattr(self._cur, "lastrowid", None)

    @property
    def rowcount(self):
        return getattr(self._cur, "rowcount", -1)

    @property
    def description(self):
        return self._cur.description

    def _cols(self):
        d = self._cur.description
        return [c[0] for c in d] if d else []

    def execute(self, sql, params=None):
        if params is None:
            return _LibsqlCursor(self._cur.execute(sql))
        if isinstance(params, dict):
            sql, params = _named_to_positional(sql, params)
        elif not isinstance(params, (list, tuple)):
            params = tuple(params)
        return _LibsqlCursor(self._cur.execute(sql, params))

    def executemany(self, sql, params_list):
        params_list = list(params_list)
        if params_list and isinstance(params_list[0], dict):
            names = _NAMED_PARAM_RE.findall(sql)
            sql_conv = _NAMED_PARAM_RE.sub("?", sql)
            converted = [tuple(p[n] for n in names) for p in params_list]
            return _LibsqlCursor(self._cur.executemany(sql_conv, converted))
        return _LibsqlCursor(self._cur.executemany(sql, params_list))

    def fetchone(self):
        row = self._cur.fetchone()
        return None if row is None else _LibsqlRow(self._cols(), row)

    def fetchall(self):
        cols = self._cols()
        return [_LibsqlRow(cols, r) for r in self._cur.fetchall()]

    def __iter__(self):
        # libsql cursor nie jest iterowalny — bierzemy fetchall.
        cols = self._cols()
        for r in self._cur.fetchall():
            yield _LibsqlRow(cols, r)

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class _LibsqlConnAdapter:
    """Sqlite3-Connection lookalike nad libsql. Uzywane w cloud mode przez api.connect()."""

    def __init__(self, real_conn):
        object.__setattr__(self, "_c", real_conn)

    def __setattr__(self, k, v):
        # aiosql moze robic conn.row_factory = sqlite3.Row — noop, mamy juz dict-like rows.
        if k == "row_factory":
            return
        object.__setattr__(self, k, v)

    def execute(self, sql, params=None):
        if params is None:
            cur = self._c.execute(sql)
        else:
            # libsql wymaga tuple/list — aiosql passuje dict dla ':name' params.
            if isinstance(params, dict):
                sql, params = _named_to_positional(sql, params)
            elif not isinstance(params, (list, tuple)):
                params = tuple(params)
            cur = self._c.execute(sql, params)
        return _LibsqlCursor(cur)

    def executemany(self, sql, params_list):
        params_list = list(params_list)
        if params_list and isinstance(params_list[0], dict):
            names = _NAMED_PARAM_RE.findall(sql)
            sql_conv = _NAMED_PARAM_RE.sub("?", sql)
            converted = [tuple(p[n] for n in names) for p in params_list]
            cur = self._c.executemany(sql_conv, converted)
        else:
            cur = self._c.executemany(sql, params_list)
        return _LibsqlCursor(cur)

    def cursor(self):
        """aiosql opens cursor via conn.cursor() — return our wrapper."""
        return _LibsqlCursor(self._c.cursor())

    def commit(self):
        self._c.commit()

    def rollback(self):
        try:
            self._c.rollback()
        except Exception:
            # libsql moze nie mieć rollback dla autocommit conn
            pass

    def close(self):
        try:
            self._c.close()
        except Exception:
            pass

    def __getattr__(self, name):
        # fallback dla innych atrybutow libsql
        return getattr(self._c, name)


def _open_libsql():
    """Otworz swieze polaczenie libsql do Turso."""
    import libsql
    url = os.environ["TURSO_DATABASE_URL"]
    token = os.environ["TURSO_AUTH_TOKEN"]
    return _LibsqlConnAdapter(libsql.connect(url, auth_token=token))


def _is_cloud() -> bool:
    return bool(os.getenv("TURSO_DATABASE_URL") and os.getenv("TURSO_AUTH_TOKEN"))


# ============================================
# Connection helper (auto-commit / rollback)
# ============================================

@contextmanager
def connect():
    """Open a connection with auto-commit. Use `with api.connect() as conn:`.

    Cloud mode (TURSO env set) → libsql connection do Turso (adapter aiosql-friendly).
    Local mode → sqlite3 na db/data.db.
    """
    if _is_cloud():
        conn = _open_libsql()
    else:
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
# Legacy shim — usuniete bootstrap_cloud().
# Kod trzymajacy referencje dostanie no-op. Dashboard dostal osobne fix.
# ============================================

def bootstrap_cloud(force: bool = False) -> None:
    """Deprecated: dashboard laczy sie bezposrednio z Turso przez libsql adapter
    w api.connect(). Cache Streamlit (@st.cache_data ttl=60) trzyma latency w ryzach.

    Ta funkcja to no-op — zachowana dla kompatybilnosci wywolan.
    Design zmiana 2026-08-19: koniec z replica + sync bootstrap (data-loss incidents).
    """
    return None
