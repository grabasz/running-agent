-- Multi-tenant, faza 2: dodanie user_id do wszystkich tabel z danymi usera.
-- Uzupełnienie migracji 003 (która objęła tylko planned_workouts + body_state).
-- Backfill: wszystkie istniejące wiersze → user_id=1 (domyślny user seedowany w schema.sql).

ALTER TABLE runs
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

ALTER TABLE gym_sessions
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

ALTER TABLE weekly_volume
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

ALTER TABLE races
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

ALTER TABLE vdot_history
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

ALTER TABLE notes
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

ALTER TABLE tasks
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

ALTER TABLE weekly_goals
    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id);

CREATE INDEX IF NOT EXISTS idx_runs_user_date            ON runs(user_id, date);
CREATE INDEX IF NOT EXISTS idx_gym_sessions_user_date    ON gym_sessions(user_id, date);
CREATE INDEX IF NOT EXISTS idx_weekly_volume_user_week   ON weekly_volume(user_id, week_start);
CREATE INDEX IF NOT EXISTS idx_races_user_date           ON races(user_id, date);
CREATE INDEX IF NOT EXISTS idx_vdot_history_user_date    ON vdot_history(user_id, date);
CREATE INDEX IF NOT EXISTS idx_notes_user_created        ON notes(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status         ON tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_weekly_goals_user_week    ON weekly_goals(user_id, week_start);
