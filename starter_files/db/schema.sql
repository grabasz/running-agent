-- Running Project DB schema
-- SQLite-compatible (forward-compatible with Turso/libSQL)
-- All dates: ISO 8601 YYYY-MM-DD

PRAGMA foreign_keys = ON;

-- ============================================
-- GYM
-- ============================================

CREATE TABLE IF NOT EXISTS gym_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,             -- YYYY-MM-DD
    duration_min    INTEGER,
    hr_avg          INTEGER,
    hr_max          INTEGER,
    calories        INTEGER,
    context         TEXT,                      -- e.g. "Powrot po przerwie", "pod kolano valgus"
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gym_sessions_date ON gym_sessions(date);

CREATE TABLE IF NOT EXISTS gym_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES gym_sessions(id) ON DELETE CASCADE,
    exercise        TEXT NOT NULL,             -- canonical PL name: "BSS", "RDL", "Goblet squat", "Plank"
    set_num         INTEGER NOT NULL,          -- 1, 2, 3
    reps            INTEGER,                   -- null for time-based
    duration_sec    INTEGER,                   -- null for reps-based (used for plank etc)
    weight_kg       REAL,                      -- null for bodyweight
    weight_per_side INTEGER DEFAULT 0,         -- 1 if weight_kg is per-side (e.g. BSS 2x8kg)
    rest_sec        INTEGER,
    rpe             INTEGER,                   -- subjective 1-10
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_gym_sets_session ON gym_sets(session_id);
CREATE INDEX IF NOT EXISTS idx_gym_sets_exercise ON gym_sets(exercise);

-- ============================================
-- RUNS
-- ============================================

CREATE TABLE IF NOT EXISTS runs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Provider keys
    strava_id                   INTEGER UNIQUE,
    garmin_activity_id          INTEGER UNIQUE,
    source                      TEXT,                  -- 'garmin' | 'strava' (which provider was primary)

    -- Basics
    date                        TEXT NOT NULL,         -- YYYY-MM-DD
    name                        TEXT,
    distance_km                 REAL,
    duration_sec                INTEGER,               -- elapsed
    moving_sec                  INTEGER,
    pace_sec_per_km             INTEGER,               -- derived: moving_sec / distance_km

    -- HR + cadence + power
    hr_avg                      INTEGER,
    hr_max                      INTEGER,
    cadence_avg                 INTEGER,
    power_avg                   INTEGER,
    power_max                   INTEGER,
    power_norm                  INTEGER,               -- normalized power

    -- Elevation
    elevation_gain_m            INTEGER,
    elevation_loss_m            INTEGER,

    -- Running dynamics (Garmin-only, NULL for Strava)
    vertical_oscillation_cm     REAL,
    ground_contact_ms           INTEGER,
    gct_balance_left_pct        REAL,                  -- % left foot in stance (50% = symmetric)
    stride_length_cm            REAL,
    vertical_ratio_pct          REAL,                  -- vertical_osc / stride_length (lower = more economical)

    -- Garmin Firstbeat metrics (Garmin-only)
    training_effect_aerobic     REAL,                  -- 0-5
    training_effect_anaerobic   REAL,                  -- 0-5
    training_load               REAL,
    recovery_time_hours         INTEGER,
    body_battery_start          INTEGER,
    body_battery_end            INTEGER,
    vo2max_at_activity          INTEGER,

    -- HR zones time (seconds) — pomocne dla analizy intensywności
    hr_time_z1_sec              INTEGER,
    hr_time_z2_sec              INTEGER,
    hr_time_z3_sec              INTEGER,
    hr_time_z4_sec              INTEGER,
    hr_time_z5_sec              INTEGER,

    -- Classification + notes
    type                        TEXT,                  -- Easy / Tempo / Interval / Race / Long / Recovery / Shakeout
    notes                       TEXT,
    raw_json                    TEXT                   -- full provider response (optional cache)
);

CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(date);
CREATE INDEX IF NOT EXISTS idx_runs_type_date ON runs(type, date);
CREATE INDEX IF NOT EXISTS idx_runs_source ON runs(source);

CREATE TABLE IF NOT EXISTS run_laps (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    lap_num                     INTEGER NOT NULL,
    distance_km                 REAL,
    duration_sec                INTEGER,
    pace_sec_per_km             INTEGER,
    hr_avg                      INTEGER,
    hr_max                      INTEGER,
    cadence_avg                 INTEGER,
    power_avg                   INTEGER,
    elev_up_m                   INTEGER,
    elev_down_m                 INTEGER,
    -- Running dynamics per lap (Garmin)
    vertical_oscillation_cm     REAL,
    ground_contact_ms           INTEGER,
    gct_balance_left_pct        REAL,
    stride_length_cm            REAL,
    vertical_ratio_pct          REAL
);

CREATE INDEX IF NOT EXISTS idx_run_laps_run ON run_laps(run_id);

-- run_streams: per-second time-series (HR, pace, cadence, power, altitude)
-- Optional — used for deep-dive (e.g. when did HR spike to 175 and for how long)
CREATE TABLE IF NOT EXISTS run_streams (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sec             INTEGER NOT NULL,                  -- seconds since start
    hr              INTEGER,
    pace_sec_per_km INTEGER,
    cadence         INTEGER,
    power           INTEGER,
    altitude_m      REAL
);

CREATE INDEX IF NOT EXISTS idx_run_streams_run_sec ON run_streams(run_id, sec);

CREATE TABLE IF NOT EXISTS weekly_volume (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start          TEXT UNIQUE NOT NULL,  -- ISO Monday YYYY-MM-DD
    distance_km         REAL,
    elevation_gain_m    INTEGER,
    duration_sec        INTEGER,
    num_runs            INTEGER,
    longest_km          REAL,
    trend               TEXT                    -- "peak", "recovery", or NULL
);

-- ============================================
-- RACES
-- ============================================

CREATE TABLE IF NOT EXISTS races (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,
    name                TEXT NOT NULL,
    distance_km         REAL NOT NULL,
    target_time_sec     INTEGER,                -- planned
    actual_time_sec     INTEGER,                -- achieved (NULL if future)
    is_pb               INTEGER DEFAULT 0,
    place_overall       INTEGER,
    place_category      TEXT,
    conditions_temp_c   REAL,
    strategy            TEXT,
    notes               TEXT,
    run_id              INTEGER REFERENCES runs(id),  -- link to Strava activity
    -- Dedup: one race per (date, name) — can't add Białystok 10.05 twice
    UNIQUE(date, name)
);

CREATE INDEX IF NOT EXISTS idx_races_date ON races(date);

-- ============================================
-- BODY
-- ============================================

CREATE TABLE IF NOT EXISTS body_weight (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    date    TEXT UNIQUE NOT NULL,
    kg      REAL NOT NULL,
    notes   TEXT
);

CREATE TABLE IF NOT EXISTS body_state (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,                  -- YYYY-MM-DD
    location    TEXT NOT NULL,                  -- "kolano_prawe", "lydka_prawa", "krzyz", "posladki_doms", etc
    pain_0_10   INTEGER,                        -- 0-10 (null if just DOMS flag)
    doms        INTEGER DEFAULT 0,              -- 1 if DOMS (zakwasy)
    notes       TEXT,
    UNIQUE(date, location)
);

CREATE INDEX IF NOT EXISTS idx_body_state_date ON body_state(date);

-- ============================================
-- PLANNED WORKOUTS (training plan, mobile-friendly)
-- ============================================

-- Lookup: workout statuses (planned / done / modified / skipped)
CREATE TABLE IF NOT EXISTS workout_statuses (
    id          INTEGER PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,
    display_pl  TEXT NOT NULL,
    display_en  TEXT NOT NULL,
    icon        TEXT,
    sort_order  INTEGER
);

-- Lookup: workout types (Easy / Tempo / Strength A / Mobility / REST etc.)
CREATE TABLE IF NOT EXISTS workout_types (
    id          INTEGER PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,         -- 'easy', 'tempo', 'strength_a', 'rest', ...
    display_pl  TEXT NOT NULL,
    display_en  TEXT NOT NULL,
    category    TEXT,                         -- 'run' / 'strength' / 'cross' / 'recovery'
    icon        TEXT,
    sort_order  INTEGER
);

-- Main table: planned workouts (one row per planned session)
CREATE TABLE IF NOT EXISTS planned_workouts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    date                    TEXT NOT NULL,                            -- YYYY-MM-DD
    week_start              TEXT NOT NULL,                            -- Monday-anchored YYYY-MM-DD

    -- What to do (lookup FKs)
    type_id                 INTEGER NOT NULL REFERENCES workout_types(id),
    status_id               INTEGER NOT NULL DEFAULT 1 REFERENCES workout_statuses(id),

    -- Targets
    title                   TEXT,                                     -- short description e.g. "Easy 5-6km @6:10 rano"
    target_distance_km      REAL,
    target_duration_min     INTEGER,
    target_pace_sec_per_km  INTEGER,                                  -- target avg pace
    target_hr_max           INTEGER,                                  -- HR cap
    notes                   TEXT,                                     -- modifications, context

    -- Conditions captured at planning time
    weather_temp_c          INTEGER,                                  -- forecast temp
    weather_note            TEXT,                                     -- "burza", "upal", "front"

    -- Execution links (filled after the session)
    actual_run_id           INTEGER REFERENCES runs(id),
    actual_session_id       INTEGER REFERENCES gym_sessions(id),
    actual_notes            TEXT,

    created_at              TEXT DEFAULT (datetime('now')),
    updated_at              TEXT,

    -- Dedup: one workout per (date, type) combination (allows double-day with different types,
    -- e.g. Easy run + Strength on the same day, but not two Easy runs)
    UNIQUE(date, type_id)
);

CREATE INDEX IF NOT EXISTS idx_planned_date ON planned_workouts(date);
CREATE INDEX IF NOT EXISTS idx_planned_week ON planned_workouts(week_start);
CREATE INDEX IF NOT EXISTS idx_planned_status ON planned_workouts(status_id);

-- Sub-components of a planned workout (per-item odhaczanie).
-- Monolityczny wpis "REST + foam roll + Codzienny Beton" rozbija się na 3 komponenty
-- z osobnym statusem — user może odhaczyć każdy z osobna.
CREATE TABLE IF NOT EXISTS planned_workout_components (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    planned_workout_id  INTEGER NOT NULL REFERENCES planned_workouts(id) ON DELETE CASCADE,
    order_idx           INTEGER NOT NULL DEFAULT 0,
    label               TEXT NOT NULL,
    status_id           INTEGER NOT NULL DEFAULT 1 REFERENCES workout_statuses(id),
    actual_notes        TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT,
    UNIQUE(planned_workout_id, order_idx)
);

CREATE INDEX IF NOT EXISTS idx_pwc_planned ON planned_workout_components(planned_workout_id);
CREATE INDEX IF NOT EXISTS idx_pwc_status ON planned_workout_components(status_id);

-- Seed lookup tables (idempotent — use INSERT OR IGNORE)
INSERT OR IGNORE INTO workout_statuses (id, key, display_pl, display_en, icon, sort_order) VALUES
    (1, 'planned',   'Zaplanowany',   'Planned',   '⏸️',  1),
    (2, 'done',      'Wykonany',      'Done',      '✅',  2),
    (3, 'modified',  'Zmodyfikowany', 'Modified',  '⚠️',  3),
    (4, 'skipped',   'Pominięty',     'Skipped',   '❌',  4);

INSERT OR IGNORE INTO workout_types (id, key, display_pl, display_en, category, icon, sort_order) VALUES
    (1,  'easy',         'Easy',          'Easy',          'run',      '🏃',  1),
    (2,  'tempo',        'Tempo',         'Tempo',         'run',      '⚡',  2),
    (3,  'interval',     'Interwały',     'Interval',      'run',      '🔥',  3),
    (4,  'long',         'Long run',      'Long run',      'run',      '🛣️',  4),
    (5,  'recovery',     'Recovery',      'Recovery',      'run',      '🌿',  5),
    (6,  'shakeout',     'Shakeout',      'Shakeout',      'run',      '🔧',  6),
    (7,  'race',         'Wyścig',        'Race',          'run',      '🏆',  7),
    (8,  'strength_a',   'Siłownia A',    'Strength A',    'strength', '💪',  8),
    (9,  'strength_b',   'Siłownia B',    'Strength B',    'strength', '💪',  9),
    (10, 'mobility',     'Mobility',      'Mobility',      'recovery', '🧘',  10),
    (11, 'rest',         'REST',          'REST',          'recovery', '🛑',  11),
    (12, 'cross',        'Cross-training', 'Cross-training','cross',    '🚴',  12),
    (13, 'kickboxing',   'Kickboxing',    'Kickboxing',    'cross',    '🥊',  13);

-- ============================================
-- VDOT / FITNESS PROGRESSION
-- ============================================

CREATE TABLE IF NOT EXISTS vdot_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL UNIQUE,           -- one VDOT entry per date (overwrite if re-test same day)
    vdot        INTEGER NOT NULL,
    t_pace_sec  INTEGER,                        -- seconds per km
    source      TEXT,                           -- "HM Bialystok 1:39:54" etc
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_vdot_date ON vdot_history(date);
