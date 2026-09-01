-- ============================================
-- WEEKLY VOLUME (agregat tygodniowy biegow)
-- ============================================

-- name: upsert!
-- Multi-tenant: UNIQUE(user_id, week_start) via idx_weekly_volume_user_week.
INSERT INTO weekly_volume
    (user_id, week_start, distance_km, elevation_gain_m, duration_sec, num_runs, longest_km, trend)
VALUES
    (:user_id, :week_start, :distance_km, :elevation_gain_m, :duration_sec, :num_runs, :longest_km, :trend)
ON CONFLICT(user_id, week_start) DO UPDATE SET
    distance_km = excluded.distance_km,
    elevation_gain_m = excluded.elevation_gain_m,
    duration_sec = excluded.duration_sec,
    num_runs = excluded.num_runs,
    longest_km = excluded.longest_km,
    trend = excluded.trend;


-- name: recent
SELECT *
  FROM weekly_volume
 WHERE user_id = COALESCE(:user_id, 1)
 ORDER BY week_start DESC
 LIMIT :weeks;


-- name: avg_last_n_weeks$
SELECT AVG(distance_km)
  FROM weekly_volume
 WHERE user_id = COALESCE(:user_id, 1)
   AND week_start IN (
     SELECT week_start FROM weekly_volume
      WHERE user_id = COALESCE(:user_id, 1)
      ORDER BY week_start DESC LIMIT :weeks
 );
