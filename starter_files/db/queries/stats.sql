-- ============================================
-- STATS (sanity / dashboard tile counts)
-- ============================================

-- name: counts
SELECT 'gym_sessions'      AS tbl, COUNT(*) AS n FROM gym_sessions
UNION ALL SELECT 'gym_sets',         COUNT(*) FROM gym_sets
UNION ALL SELECT 'runs',             COUNT(*) FROM runs
UNION ALL SELECT 'run_laps',         COUNT(*) FROM run_laps
UNION ALL SELECT 'run_streams',      COUNT(*) FROM run_streams
UNION ALL SELECT 'weekly_volume',    COUNT(*) FROM weekly_volume
UNION ALL SELECT 'races',            COUNT(*) FROM races
UNION ALL SELECT 'body_weight',      COUNT(*) FROM body_weight
UNION ALL SELECT 'body_state',       COUNT(*) FROM body_state
UNION ALL SELECT 'vdot_history',     COUNT(*) FROM vdot_history
UNION ALL SELECT 'workout_statuses', COUNT(*) FROM workout_statuses
UNION ALL SELECT 'workout_types',    COUNT(*) FROM workout_types
UNION ALL SELECT 'planned_workouts', COUNT(*) FROM planned_workouts;
