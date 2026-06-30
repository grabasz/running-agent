-- ============================================
-- PLANNED WORKOUTS (training plan)
-- ============================================

-- name: add<!
INSERT INTO planned_workouts
    (date, week_start, type_id, status_id, title, target_distance_km,
     target_duration_min, target_pace_sec_per_km, target_hr_max, notes,
     weather_temp_c, weather_note)
VALUES
    (:date, :week_start, :type_id, :status_id, :title, :target_distance_km,
     :target_duration_min, :target_pace_sec_per_km, :target_hr_max, :notes,
     :weather_temp_c, :weather_note);


-- name: by_id^
SELECT p.*,
       t.key AS type_key, t.display_pl AS type_display, t.category AS type_category, t.icon AS type_icon,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses s ON s.id = p.status_id
 WHERE p.id = :id;


-- name: today
-- All workouts planned for today (usually 1, but can be 2 if double-day)
SELECT p.*,
       t.key AS type_key, t.display_pl AS type_display, t.category AS type_category, t.icon AS type_icon,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses s ON s.id = p.status_id
 WHERE p.date = date('now')
 ORDER BY p.id;


-- name: by_date
SELECT p.*,
       t.key AS type_key, t.display_pl AS type_display, t.category AS type_category, t.icon AS type_icon,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses s ON s.id = p.status_id
 WHERE p.date = :date
 ORDER BY p.id;


-- name: week_plan
-- Full week (Monday-anchored)
SELECT p.*,
       t.key AS type_key, t.display_pl AS type_display, t.category AS type_category, t.icon AS type_icon,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses s ON s.id = p.status_id
 WHERE p.week_start = :week_start
 ORDER BY p.date, p.id;


-- name: current_week
-- Auto-detect current Monday and return that week
SELECT p.*,
       t.key AS type_key, t.display_pl AS type_display, t.category AS type_category, t.icon AS type_icon,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses s ON s.id = p.status_id
 WHERE p.week_start = date('now', 'weekday 0', '-6 days')
 ORDER BY p.date, p.id;


-- name: upcoming
-- Next N days AFTER today (jutro i później; pomija dziś)
SELECT p.*,
       t.key AS type_key, t.display_pl AS type_display, t.icon AS type_icon,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses s ON s.id = p.status_id
 WHERE p.date > date('now')
   AND p.date <= date('now', :days)
 ORDER BY p.date, p.id
 LIMIT :limit;


-- name: mark_status!
-- Update status of a planned workout. Use status_key ('done'|'modified'|'skipped'|'planned')
UPDATE planned_workouts
   SET status_id = (SELECT id FROM workout_statuses WHERE key = :status_key),
       actual_notes = COALESCE(:actual_notes, actual_notes),
       updated_at = datetime('now')
 WHERE id = :id;


-- name: link_actual_run!
-- After /run saves the actual run, link it to the planned workout for the same date
UPDATE planned_workouts
   SET actual_run_id = :run_id,
       status_id = (SELECT id FROM workout_statuses WHERE key = 'done'),
       updated_at = datetime('now')
 WHERE id = :id;


-- name: link_actual_session!
-- After /silownia saves the gym session, link it
UPDATE planned_workouts
   SET actual_session_id = :session_id,
       status_id = (SELECT id FROM workout_statuses WHERE key = 'done'),
       updated_at = datetime('now')
 WHERE id = :id;


-- name: auto_link_run_for_date^
-- Find a planned workout for given date that is 'planned' and run-category — to auto-link with /run
SELECT p.id
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
 WHERE p.date = :date
   AND t.category = 'run'
   AND p.actual_run_id IS NULL
 ORDER BY p.id
 LIMIT 1;


-- name: auto_link_session_for_date^
-- Same for strength sessions
SELECT p.id
  FROM planned_workouts p
  JOIN workout_types t ON t.id = p.type_id
 WHERE p.date = :date
   AND t.category = 'strength'
   AND p.actual_session_id IS NULL
 ORDER BY p.id
 LIMIT 1;


-- name: delete_week!
-- Wipe a whole week's plan (e.g. before regenerating it)
DELETE FROM planned_workouts WHERE week_start = :week_start;


-- name: week_summary
-- Aggregate stats for a week (planned vs done)
SELECT s.key AS status_key, s.display_pl AS status_display,
       COUNT(*) AS n,
       SUM(p.target_distance_km) AS total_distance_km
  FROM planned_workouts p
  JOIN workout_statuses s ON s.id = p.status_id
 WHERE p.week_start = :week_start
 GROUP BY s.id, s.key, s.display_pl
 ORDER BY s.sort_order;


-- ============================================
-- TYPES + STATUSES (helpers for UI)
-- ============================================

-- name: list_types
SELECT * FROM workout_types ORDER BY sort_order;


-- name: list_statuses
SELECT * FROM workout_statuses ORDER BY sort_order;


-- name: type_by_key^
SELECT * FROM workout_types WHERE key = :key;


-- name: status_by_key^
SELECT * FROM workout_statuses WHERE key = :key;
