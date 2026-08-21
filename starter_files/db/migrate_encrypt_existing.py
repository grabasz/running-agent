"""Zaszyfruj istniejace plaintext dane user_id=X na Turso.

WYMAGA: env USER{ID}_ENC_KEY (albo ENC_KEY dla single-user). Wczytuje z db/.env.

Idempotentne: pomija wpisy juz zaczynajace sie od 'enc:v1:'.

Uzycie:
    # Bartek (user_id=1):
    python db/migrate_encrypt_existing.py --user 1 --dry-run
    python db/migrate_encrypt_existing.py --user 1

    # Mati (po setup, user_id=2):
    python db/migrate_encrypt_existing.py --user 2

Pola szyfrowane:
- notes.content
- tasks.title, tasks.description
- planned_workouts.actual_notes
- body_state.notes
- session_artifacts.title, .summary, .content_md

NIE ruszamy: dat, typow, dystansow, run metrics, katalogow.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
env_path = HERE / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(HERE))
from crypto import get_key_for_user, maybe_encrypt, MAGIC_PREFIX  # noqa: E402

TABLE_FIELDS = [
    ("notes",              ["content"]),
    ("tasks",              ["title", "description"]),
    ("planned_workouts",   ["actual_notes"]),
    ("body_state",         ["notes"]),
    ("session_artifacts",  ["title", "summary", "content_md"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", type=int, required=True, help="user_id do zaszyfrowania")
    ap.add_argument("--dry-run", action="store_true", help="pokaz co bylo by robione, nie modyfikuj")
    args = ap.parse_args()

    if get_key_for_user(args.user) is None:
        sys.stderr.write(f"BLAD: brak USER{args.user}_ENC_KEY ani ENC_KEY w env / db/.env\n")
        sys.exit(1)

    import libsql
    url = os.environ["TURSO_DATABASE_URL"]
    token = os.environ["TURSO_AUTH_TOKEN"]
    conn = libsql.connect(url, auth_token=token)

    total_updated = 0
    for table, fields in TABLE_FIELDS:
        cols = ["id"] + fields
        try:
            rows = conn.execute(
                f"SELECT {','.join(cols)} FROM {table} WHERE user_id = ?",
                (args.user,)
            ).fetchall()
        except Exception as e:
            print(f"  {table}: SKIP ({e})")
            continue

        n_updated = 0
        for row in rows:
            row_id = row[0]
            updates = {}
            for i, field in enumerate(fields, start=1):
                val = row[i]
                if val is None or not isinstance(val, str) or not val.strip():
                    continue
                if val.startswith(MAGIC_PREFIX):
                    continue  # juz zaszyfrowane
                encrypted = maybe_encrypt(val, args.user)
                if encrypted != val:
                    updates[field] = encrypted
            if not updates:
                continue
            n_updated += 1
            if args.dry_run:
                print(f"  {table}[id={row_id}]: DRY {list(updates.keys())}")
                continue
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE id = ?",
                (*updates.values(), row_id)
            )
        conn.commit()
        print(f"  {table}: {n_updated}/{len(rows)} zaszyfrowanych")
        total_updated += n_updated

    print()
    if args.dry_run:
        print(f"DRY RUN — total by zostalo zaszyfrowane: {total_updated} wierszy")
    else:
        print(f"DONE — total zaszyfrowanych: {total_updated} wierszy")
    conn.close()


if __name__ == "__main__":
    main()
