"""Rozbij planned_workouts.title po ' + ' na komponenty.

Idempotentne — przetwarza tylko wpisy, które jeszcze nie mają komponentów.
Odpalić po każdym seed_current_week.py jeśli chce się granularne odhaczanie.

Parser respektuje nawiasy — "Silownia B (upper + core + prehab)" ostaje 1 komponentem.

Uruchomienie:
    python db/migrate_components.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import api  # type: ignore


def split_title(title: str) -> list[str]:
    """Split by ' + ' only at nesting depth 0 (ignore + inside brackets)."""
    if not title:
        return []
    parts: list[str] = []
    buf = ""
    depth = 0
    i = 0
    while i < len(title):
        ch = title[i]
        if ch in "([":
            depth += 1
            buf += ch
        elif ch in ")]":
            depth = max(0, depth - 1)
            buf += ch
        elif depth == 0 and title[i:i + 3] == " + ":
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
            i += 3
            continue
        else:
            buf += ch
        i += 1
    if buf.strip():
        parts.append(buf.strip())
    return parts or [title.strip()]


def main() -> None:
    with api.connect() as conn:
        rows = conn.execute("""
            SELECT p.id, p.title, p.status_id
              FROM planned_workouts p
             WHERE NOT EXISTS (
                 SELECT 1 FROM planned_workout_components c
                  WHERE c.planned_workout_id = p.id
             )
             ORDER BY p.id
        """).fetchall()
        total = created = 0
        for r in rows:
            total += 1
            parts = split_title(r["title"] or "")
            for idx, label in enumerate(parts):
                conn.execute("""
                    INSERT INTO planned_workout_components
                        (planned_workout_id, order_idx, label, status_id)
                    VALUES (?, ?, ?, ?)
                """, (r["id"], idx, label, r["status_id"]))
                created += 1
        conn.commit()
        print(f"[migrate_components] planned rows processed: {total}, components created: {created}")


if __name__ == "__main__":
    main()
