-- Migracja 008: Faza 18C - UNIQUE constraints multi-tenant (task #58)
-- planned_workouts + races: UNIQUE(date, ...) -> UNIQUE(user_id, date, ...)

PRAGMA foreign_keys = OFF;

-- === PLANNED_WORKOUTS ===
ALTER TABLE planned_workouts RENAME TO _planned_workouts_old;

CREATE TABLE planned_workouts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    date                     TEXT NOT NULL,
    week_start               TEXT NOT NULL,
    type_id                  INTEGER NOT NULL REFERENCES workout_types(id),
    status_id                INTEGER NOT NULL DEFAULT 1 REFERENCES workout_statuses(id),
    title                    TEXT,
    target_distance_km       REAL,
    target_duration_min      INTEGER,
    target_pace_sec_per_km   INTEGER,
    target_hr_max            INTEGER,
    notes                    TEXT,
    weather_temp_c           REAL,
    weather_note             TEXT,
    actual_run_id            INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    actual_session_id        INTEGER REFERENCES gym_sessions(id) ON DELETE SET NULL,
    actual_notes             TEXT,
    created_at               TEXT DEFAULT (datetime('now')),
    updated_at               TEXT,
    user_id                  INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    UNIQUE(user_id, date, type_id)
);

INSERT INTO planned_workouts SELECT * FROM _planned_workouts_old;
DROP TABLE _planned_workouts_old;

CREATE INDEX IF NOT EXISTS idx_planned_user_date ON planned_workouts(user_id, date);
CREATE INDEX IF NOT EXISTS idx_planned_status ON planned_workouts(status_id);

-- === RACES ===
ALTER TABLE races RENAME TO _races_old;

CREATE TABLE races (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,
    name              TEXT NOT NULL,
    distance_km       REAL,
    target_time_sec   INTEGER,
    actual_time_sec   INTEGER,
    is_pb             INTEGER DEFAULT 0,
    place_overall     INTEGER,
    place_category    TEXT,
    conditions_temp_c REAL,
    strategy          TEXT,
    notes             TEXT,
    run_id            INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    user_id           INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    UNIQUE(user_id, date, name)
);

INSERT INTO races SELECT * FROM _races_old;
DROP TABLE _races_old;

CREATE INDEX IF NOT EXISTS idx_races_user_date ON races(user_id, date);

PRAGMA foreign_keys = ON;
