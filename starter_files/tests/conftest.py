"""Pytest fixtures dla testów dashboardu / db api.

Wzorzec:
- `tmp_conn` — czysta in-memory SQLite z pełną schemą (raz per test)
- `seeded_conn` — jak wyżej + minimalny seed (user Bartek, 1 exercise, 1 routine, 1 body_state)

Użycie w testach:
    def test_cos(seeded_conn):
        rows = seeded_conn.execute(
            "SELECT * FROM body_state WHERE user_id = ?", (1,)
        ).fetchall()
        assert len(rows) == 1
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Odpal baseline schema.sql + wszystkie migracje po kolei."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        try:
            conn.executescript(sql_file.read_text(encoding="utf-8"))
        except sqlite3.OperationalError:
            # Migracje mogą zakładać brak tabel; baseline już je stworzył.
            # Idempotencja: pomijamy błędy "already exists".
            pass
    conn.commit()


@pytest.fixture
def tmp_conn() -> sqlite3.Connection:
    """Czysta in-memory DB z pełną schemą, bez danych."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def seeded_conn(tmp_conn: sqlite3.Connection) -> sqlite3.Connection:
    """In-memory DB z minimalnym seed dla scenariuszy multi-user + body_state."""
    conn = tmp_conn
    # users już seedowane w schema (id=1 bartek, id=2 mati)
    # dodaj body_state dla Bartka
    conn.execute("""
        INSERT INTO body_state (user_id, date, location, pain_0_10, notes)
        VALUES (1, '2026-08-16', 'kolano_prawe', 2, 'test seed')
    """)
    # notes dla Bartka
    conn.execute("""
        INSERT INTO notes (user_id, date, category, content, source)
        VALUES (1, '2026-08-16', 'insight', 'test insight', 'test')
    """)
    conn.commit()
    return conn
