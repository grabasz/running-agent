-- Migracja 010: body_weight multi-tenant (task #58, PROBLEM A)
-- body_weight miało UNIQUE(date) — Mati i Bartek nie mogli ważyć się tego samego
-- dnia. Rebuild: dodaje user_id + UNIQUE(user_id, date).
-- Istniejące wiersze idą do user_id=1 (Bartek — jedyny historyczny user w body_weight).

PRAGMA foreign_keys = OFF;

ALTER TABLE body_weight RENAME TO _body_weight_old;

CREATE TABLE body_weight (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    date     TEXT NOT NULL,
    kg       REAL NOT NULL,
    notes    TEXT,
    UNIQUE(user_id, date)
);

-- Migruj z DEFAULT user_id=1 (wszystkie historyczne wpisy to Bartek).
INSERT INTO body_weight (id, user_id, date, kg, notes)
     SELECT id, 1, date, kg, notes FROM _body_weight_old;

DROP TABLE _body_weight_old;

CREATE INDEX IF NOT EXISTS idx_body_weight_user_date ON body_weight(user_id, date);

PRAGMA foreign_keys = ON;
