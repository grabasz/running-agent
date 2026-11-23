-- Migracja 012: szczegóły makroplanu (notatki #41/#42 usera).
-- Rozszerza 011 zamiast osobnych training_plans/plan_phases — faza jest kolumną tygodnia,
-- a "plan" = training_goals (1 aktywny na usera). Dochodzą: źródło planu,
-- struktura longa/akcentów, reguły, tempa docelowe i historia zmian (propozycja → akceptacja).

ALTER TABLE training_goals ADD COLUMN source TEXT NOT NULL DEFAULT 'deterministic';  -- deterministic / ai-panel / manual
ALTER TABLE training_goals ADD COLUMN methodology TEXT;
ALTER TABLE training_goals ADD COLUMN notes TEXT;

ALTER TABLE macro_plan_weeks ADD COLUMN long_structure TEXT;   -- "28 km: 10 E + 16 @M + 2 E"
ALTER TABLE macro_plan_weeks ADD COLUMN key_session TEXT;      -- opis akcentów tygodnia
ALTER TABLE macro_plan_weeks ADD COLUMN notes TEXT;

CREATE TABLE IF NOT EXISTS plan_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    goal_id     INTEGER NOT NULL REFERENCES training_goals(id) ON DELETE CASCADE,
    rule_type   TEXT    NOT NULL,          -- ban / cap / gate / allow
    subject     TEXT    NOT NULL,          -- np. 'sprint', 'week_km', 'long_km', 'quality_per_week'
    value       TEXT,                      -- np. '70', '2 jeśli kolano<=2/10'
    valid_from  TEXT,
    valid_to    TEXT,
    reason      TEXT
);
CREATE INDEX IF NOT EXISTS idx_plan_rules_goal ON plan_rules(goal_id);

CREATE TABLE IF NOT EXISTS pace_targets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    goal_id     INTEGER NOT NULL REFERENCES training_goals(id) ON DELETE CASCADE,
    zone        TEXT    NOT NULL,          -- E / M / T / I / HM
    min_sec     INTEGER NOT NULL,          -- szybsza granica (s/km)
    max_sec     INTEGER NOT NULL,
    valid_from  TEXT    NOT NULL,
    source      TEXT
);
CREATE INDEX IF NOT EXISTS idx_pace_targets_goal ON pace_targets(goal_id, zone, valid_from);

CREATE TABLE IF NOT EXISTS plan_revisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    goal_id     INTEGER NOT NULL REFERENCES training_goals(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    event_type  TEXT    NOT NULL,          -- created / race_added / missed_days / pain / overreach / manual
    reason      TEXT,
    diff_json   TEXT,
    accepted    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_plan_revisions_goal ON plan_revisions(goal_id, created_at);
