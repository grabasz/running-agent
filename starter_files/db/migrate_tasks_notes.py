"""Faza 17: dodaj tabele tasks / weekly_goals / notes (lokalnie + Turso).

Idempotentne — CREATE TABLE IF NOT EXISTS. Bezpieczne do wielokrotnego uruchomienia.

Trzy tabele wspierają stronę "Rozkminy" na dashboardzie:
- tasks: hierarchiczna lista (parent_id NULL = projekt/root), SMART (title + success_criteria + due_date opcjonalne)
- weekly_goals: cel per kategoria per tydzień (sport/praca/dom/relacje/zdrowie/inne)
- notes: strumień notatek (insight/decision/reminder/idea), Claude auto-wrzuca lub user manual

Uruchomienie:
    python db/migrate_tasks_notes.py              # tylko lokalnie
    python db/migrate_tasks_notes.py --turso      # lokalnie + Turso (fresh install cloud)
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import api  # type: ignore
from sync import _turso  # type: ignore


DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id           INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    category            TEXT NOT NULL,              -- sport / praca / dom / relacje / zdrowie / inne
    title               TEXT NOT NULL,              -- SMART: Specific
    description         TEXT,
    success_criteria    TEXT,                       -- SMART: Measurable — "co znaczy 'zrobione'"
    due_date            TEXT,                       -- SMART: Time-bound (opcjonalne, YYYY-MM-DD)
    status              TEXT NOT NULL DEFAULT 'open',  -- open / done / wontdo
    priority            TEXT,                       -- low / med / high (NULL = brak)
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT,
    done_at             TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);

CREATE TABLE IF NOT EXISTS weekly_goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start  TEXT NOT NULL,                      -- ISO Monday YYYY-MM-DD
    category    TEXT NOT NULL,                      -- sport / praca / dom / relacje / zdrowie / inne
    goal        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',       -- open / done
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT,
    UNIQUE(week_start, category)
);

CREATE INDEX IF NOT EXISTS idx_weekly_goals_week ON weekly_goals(week_start);

CREATE TABLE IF NOT EXISTS notes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,              -- YYYY-MM-DD
    category            TEXT NOT NULL,              -- insight / decision / reminder / idea
    content             TEXT NOT NULL,
    related_task_id     INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    related_run_id      INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    related_session_id  INTEGER REFERENCES gym_sessions(id) ON DELETE SET NULL,
    source              TEXT DEFAULT 'chat',        -- chat / claude_auto / manual
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notes_date ON notes(date);
CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);
CREATE INDEX IF NOT EXISTS idx_notes_task ON notes(related_task_id);
"""


def _apply_ddl(conn) -> None:
    for stmt in DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)


def main(turso: bool = False) -> None:
    with api.connect() as conn:
        _apply_ddl(conn)
        conn.commit()
        counts = {
            "tasks": conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            "weekly_goals": conn.execute("SELECT COUNT(*) FROM weekly_goals").fetchone()[0],
            "notes": conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0],
        }
        print("[migrate_tasks_notes] local tables ready:")
        for name, n in counts.items():
            print(f"  {name:15} {n} rows")

    if turso:
        t = _turso()
        try:
            _apply_ddl(t)
            t.commit()
            print("[migrate_tasks_notes] Turso tables ready")
        finally:
            try:
                t.close()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--turso", action="store_true",
                        help="Also apply DDL to Turso (fresh cloud install).")
    args = parser.parse_args()
    main(turso=args.turso)
