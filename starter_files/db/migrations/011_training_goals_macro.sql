-- Migracja 011: cele treningowe + referencyjny makroplan (Faza 20 — Auto-planner).
-- Zamiast template pool z REFACTOR_PLAN (011-013) — reguły metodyki żyją w
-- planner/methodology.py (deterministyczne, testowalne), w DB tylko cel + snapshot planu.

CREATE TABLE IF NOT EXISTS training_goals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id),
    race_id          INTEGER REFERENCES races(id),
    name             TEXT    NOT NULL,
    race_date        TEXT,                       -- NULL = cel bez startu (utrzymanie)
    distance_km      REAL,
    target_time_sec  INTEGER,
    start_date       TEXT    NOT NULL,           -- poniedziałek startu makrocyklu
    baseline_km      REAL    NOT NULL,
    peak_km          REAL,
    runs_per_week    INTEGER NOT NULL DEFAULT 5,
    status           TEXT    NOT NULL DEFAULT 'active',   -- active / done / archived
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_training_goals_user_status ON training_goals(user_id, status);

CREATE TABLE IF NOT EXISTS macro_plan_weeks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    goal_id        INTEGER NOT NULL REFERENCES training_goals(id) ON DELETE CASCADE,
    week_start     TEXT    NOT NULL,
    phase          TEXT    NOT NULL,
    week_in_phase  INTEGER NOT NULL,
    is_deload      INTEGER NOT NULL DEFAULT 0,
    is_race_week   INTEGER NOT NULL DEFAULT 0,
    target_km      REAL    NOT NULL,
    long_km        REAL,
    quality_json   TEXT,                         -- [{"kind":"T","km":5.0}, ...]
    UNIQUE(goal_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_macro_weeks_user_week ON macro_plan_weeks(user_id, week_start);
