"""POC testów query logic — pokazuje wzorzec do naśladowania po refaktorze dashboardu.

Testy CELOWO nie importują `dashboard.py` (Streamlit dependency, cache_data
wymaga runtime). Testują RÓWNOWAŻNY SQL wyekstrahowany z query functions.

Po refaktorze (queries.py wyekstrahowany z dashboard.py) testy będą mogły
importować funkcje bezpośrednio:

    from dashboard.queries import q_body_state
    def test_body_state(seeded_conn):
        assert q_body_state(seeded_conn, user_id=1, since="-30 days") == [...]

Aktualnie: kopiujemy SQL do testu, weryfikujemy zachowanie kontraktu.
"""
from __future__ import annotations
import sqlite3
import pytest


# ============================================
# TESTY LOGIKI SQL — do naśladowania per query po refaktorze
# ============================================


def test_body_state_multi_user_isolation(seeded_conn: sqlite3.Connection):
    """user_id=1 nie widzi wpisów user_id=2 (multi-tenant)."""
    # dodaj wpis dla Matiego
    seeded_conn.execute("""
        INSERT INTO body_state (user_id, date, location, pain_0_10, notes)
        VALUES (2, '2026-08-16', 'kolano_lewe', 5, 'mati seed')
    """)
    seeded_conn.commit()

    # Bartek widzi tylko swoje
    bartek_rows = seeded_conn.execute("""
        SELECT * FROM body_state WHERE user_id = ? ORDER BY date DESC
    """, (1,)).fetchall()
    assert len(bartek_rows) == 1
    assert bartek_rows[0]["location"] == "kolano_prawe"

    # Mati widzi tylko swoje
    mati_rows = seeded_conn.execute("""
        SELECT * FROM body_state WHERE user_id = ? ORDER BY date DESC
    """, (2,)).fetchall()
    assert len(mati_rows) == 1
    assert mati_rows[0]["location"] == "kolano_lewe"


@pytest.mark.xfail(
    reason="Task #58: brak UNIQUE(date, location) w body_state — blocker multi-user w Fazie 18C. "
    "Ten test dokumentuje żądane zachowanie po naprawie."
)
def test_body_state_upsert_replaces_same_day_location(seeded_conn: sqlite3.Connection):
    """UPSERT po (date, location) — kolejny wpis nadpisuje pain_0_10."""
    seeded_conn.execute("""
        INSERT INTO body_state (user_id, date, location, pain_0_10, notes)
        VALUES (1, '2026-08-16', 'kolano_prawe', 5, 'wieczorem gorzej')
        ON CONFLICT(date, location) DO UPDATE SET
            pain_0_10 = excluded.pain_0_10,
            notes = excluded.notes
    """)
    seeded_conn.commit()

    row = seeded_conn.execute("""
        SELECT pain_0_10, notes FROM body_state
        WHERE user_id = ? AND date = ? AND location = ?
    """, (1, "2026-08-16", "kolano_prawe")).fetchone()
    assert row["pain_0_10"] == 5
    assert row["notes"] == "wieczorem gorzej"


def test_notes_filter_by_category(seeded_conn: sqlite3.Connection):
    """Query po category zwraca tylko notes danej kategorii dla usera."""
    seeded_conn.execute("""
        INSERT INTO notes (user_id, date, category, content, source)
        VALUES (1, '2026-08-16', 'decision', 'decyzja X', 'test')
    """)
    seeded_conn.commit()

    insights = seeded_conn.execute("""
        SELECT * FROM notes
        WHERE user_id = ? AND category = ?
        ORDER BY date DESC
    """, (1, "insight")).fetchall()
    assert len(insights) == 1
    assert insights[0]["content"] == "test insight"

    decisions = seeded_conn.execute("""
        SELECT * FROM notes
        WHERE user_id = ? AND category = ?
        ORDER BY date DESC
    """, (1, "decision")).fetchall()
    assert len(decisions) == 1


def test_notes_user_isolation(seeded_conn: sqlite3.Connection):
    """Notatka Matiego nie wycieka do zapytania Bartka."""
    seeded_conn.execute("""
        INSERT INTO notes (user_id, date, category, content, source)
        VALUES (2, '2026-08-16', 'insight', 'mati insight', 'test')
    """)
    seeded_conn.commit()

    bartek = seeded_conn.execute("""
        SELECT content FROM notes WHERE user_id = ?
    """, (1,)).fetchall()
    contents = [r["content"] for r in bartek]
    assert "test insight" in contents
    assert "mati insight" not in contents


def test_body_state_recent_date_filter(seeded_conn: sqlite3.Connection):
    """Filter po date >= X pomija starsze wpisy."""
    # stary wpis (przed cutoffem)
    seeded_conn.execute("""
        INSERT INTO body_state (user_id, date, location, pain_0_10, notes)
        VALUES (1, '2026-01-01', 'plecy', 3, 'stary')
    """)
    seeded_conn.commit()

    recent = seeded_conn.execute("""
        SELECT * FROM body_state
        WHERE user_id = ? AND date >= ?
        ORDER BY date DESC
    """, (1, "2026-08-01")).fetchall()
    assert len(recent) == 1
    assert recent[0]["location"] == "kolano_prawe"


# ============================================
# ANTI-PATTERN test — SQL injection przez f-string
# ============================================


def test_ANTIPATTERN_fstring_sql_is_unsafe(tmp_conn: sqlite3.Connection):
    """Dokumentacja: NIGDY nie klej user input do SQL f-stringiem.
    Ten test PRZECHODZI ale pokazuje że atak by zadziałał — używaj `?` params."""
    tmp_conn.execute("""
        INSERT INTO body_state (user_id, date, location, pain_0_10, notes)
        VALUES (1, '2026-08-16', 'kolano_prawe', 2, 'ok')
    """)
    tmp_conn.commit()

    # ZŁE (nigdy tak nie rób):
    malicious = "kolano_prawe' OR '1'='1"
    bad_query = f"SELECT * FROM body_state WHERE location = '{malicious}'"
    rows = tmp_conn.execute(bad_query).fetchall()
    assert len(rows) == 1  # atak przeszedł (SELECT wszystkiego)

    # DOBRE:
    safe = tmp_conn.execute(
        "SELECT * FROM body_state WHERE location = ?", (malicious,)
    ).fetchall()
    assert len(safe) == 0  # bezpieczny binding, brak match

    # Wniosek: zawsze `?` / `:param` binding.
