-- ============================================
-- GYM SESSIONS + SETS
-- ============================================

-- name: session_add<!
INSERT INTO gym_sessions
    (date, duration_min, hr_avg, hr_max, calories, context, notes)
VALUES
    (:date, :duration_min, :hr_avg, :hr_max, :calories, :context, :notes);


-- name: set_add<!
INSERT INTO gym_sets
    (session_id, exercise, set_num, reps, duration_sec,
     weight_kg, weight_per_side, rest_sec, rpe, notes)
VALUES
    (:session_id, :exercise, :set_num, :reps, :duration_sec,
     :weight_kg, :weight_per_side, :rest_sec, :rpe, :notes);


-- name: sessions_recent
SELECT *
  FROM gym_sessions
 ORDER BY date DESC, id DESC
 LIMIT :limit;


-- name: session_by_id^
SELECT *
  FROM gym_sessions
 WHERE id = :session_id;


-- name: sets_for_session
SELECT *
  FROM gym_sets
 WHERE session_id = :session_id
 ORDER BY set_num;


-- name: exercise_progression
SELECT s.date,
       gs.set_num,
       gs.reps,
       gs.weight_kg,
       gs.weight_per_side,
       gs.duration_sec,
       gs.notes
  FROM gym_sets gs
  JOIN gym_sessions s ON s.id = gs.session_id
 WHERE gs.exercise = :exercise
 ORDER BY s.date DESC, gs.set_num
 LIMIT :limit;


-- name: top_exercises_by_volume
-- Highest tonnage in period (volume = sum(reps * weight_kg))
SELECT gs.exercise,
       SUM(COALESCE(gs.reps, 0) * COALESCE(gs.weight_kg, 0)) AS volume_kg,
       COUNT(*) AS sets
  FROM gym_sets gs
  JOIN gym_sessions s ON s.id = gs.session_id
 WHERE s.date >= :since
 GROUP BY gs.exercise
 ORDER BY volume_kg DESC;
