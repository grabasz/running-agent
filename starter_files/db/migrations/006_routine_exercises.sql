-- Migracja 006: exercises catalog + routines + routine_exercises
-- Cel: wyciagnac hardkodowana rutyne z dashboard.py (ROUTINE_EXERCISES const)
-- do 3 tabel bazy danych. Umozliwia:
--  - reuzycie cwiczen w wielu rutynach
--  - historia zmian rutyn (active_from/active_to)
--  - link YouTube per cwiczenie (user doda przez dashboard)

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    tool TEXT,
    description_md TEXT NOT NULL,
    youtube_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    name TEXT NOT NULL,
    focus TEXT,
    total_time_min INTEGER,
    active_from TEXT NOT NULL,
    active_to TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS routine_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    exercise_id INTEGER NOT NULL REFERENCES exercises(id),
    position INTEGER NOT NULL,
    duration_or_reps TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_routines_active ON routines(user_id, active_from);
CREATE INDEX IF NOT EXISTS idx_routine_exercises_routine ON routine_exercises(routine_id, position);
