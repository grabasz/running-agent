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
-- COMPONENTS (per-item odhaczanie)
-- ============================================

-- name: components_for
-- All components of one planned workout, ordered by idx
SELECT c.*,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon
  FROM planned_workout_components c
  JOIN workout_statuses s ON s.id = c.status_id
 WHERE c.planned_workout_id = :planned_workout_id
 ORDER BY c.order_idx, c.id;


-- name: components_for_date
-- All components for a given date, joined with parent context
SELECT c.id AS component_id, c.order_idx, c.label, c.actual_notes AS component_notes,
       cs.key AS component_status, cs.display_pl AS component_status_display, cs.icon AS component_status_icon,
       p.id AS planned_id, p.date, p.title, p.notes AS planned_notes,
       p.target_distance_km, p.target_pace_sec_per_km, p.target_hr_max,
       p.weather_temp_c, p.weather_note,
       t.key AS type_key, t.display_pl AS type_display, t.category AS type_category, t.icon AS type_icon,
       ps.key AS planned_status
  FROM planned_workout_components c
  JOIN workout_statuses cs ON cs.id = c.status_id
  JOIN planned_workouts p ON p.id = c.planned_workout_id
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses ps ON ps.id = p.status_id
 WHERE p.date = :date
 ORDER BY p.id, c.order_idx, c.id;


-- name: components_today
-- Same as components_for_date but bound to today
SELECT c.id AS component_id, c.order_idx, c.label, c.actual_notes AS component_notes,
       cs.key AS component_status, cs.display_pl AS component_status_display, cs.icon AS component_status_icon,
       p.id AS planned_id, p.date, p.title, p.notes AS planned_notes,
       p.target_distance_km, p.target_pace_sec_per_km, p.target_hr_max,
       p.weather_temp_c, p.weather_note,
       t.key AS type_key, t.display_pl AS type_display, t.category AS type_category, t.icon AS type_icon,
       ps.key AS planned_status
  FROM planned_workout_components c
  JOIN workout_statuses cs ON cs.id = c.status_id
  JOIN planned_workouts p ON p.id = c.planned_workout_id
  JOIN workout_types t ON t.id = p.type_id
  JOIN workout_statuses ps ON ps.id = p.status_id
 WHERE p.date = date('now')
 ORDER BY p.id, c.order_idx, c.id;


-- name: component_add<!
-- Add a single component to a planned workout
INSERT INTO planned_workout_components
    (planned_workout_id, order_idx, label, status_id)
VALUES
    (:planned_workout_id, :order_idx, :label,
     COALESCE((SELECT id FROM workout_statuses WHERE key = :status_key), 1));


-- name: mark_component_status!
-- Update status of a single component
UPDATE planned_workout_components
   SET status_id = (SELECT id FROM workout_statuses WHERE key = :status_key),
       actual_notes = COALESCE(:actual_notes, actual_notes),
       updated_at = datetime('now')
 WHERE id = :id;


-- name: component_by_id^
SELECT c.*,
       s.key AS status_key, s.display_pl AS status_display, s.icon AS status_icon,
       p.date AS planned_date, p.title AS planned_title
  FROM planned_workout_components c
  JOIN workout_statuses s ON s.id = c.status_id
  JOIN planned_workouts p ON p.id = c.planned_workout_id
 WHERE c.id = :id;


-- name: sync_parent_status_from_components!
-- Aggregate: after modifying components, recompute parent status.
-- Rules:
--   all done      -> parent 'done'
--   all skipped   -> parent 'skipped'
--   any done/modified with any not-planned -> parent 'modified'
--   all planned   -> parent 'planned'
UPDATE planned_workouts
   SET status_id = (
       SELECT CASE
           WHEN SUM(CASE WHEN cs.key = 'done'     THEN 1 ELSE 0 END) = COUNT(*) THEN (SELECT id FROM workout_statuses WHERE key = 'done')
           WHEN SUM(CASE WHEN cs.key = 'skipped'  THEN 1 ELSE 0 END) = COUNT(*) THEN (SELECT id FROM workout_statuses WHERE key = 'skipped')
           WHEN SUM(CASE WHEN cs.key = 'planned'  THEN 1 ELSE 0 END) = COUNT(*) THEN (SELECT id FROM workout_statuses WHERE key = 'planned')
           ELSE (SELECT id FROM workout_statuses WHERE key = 'modified')
       END
       FROM planned_workout_components c
       JOIN workout_statuses cs ON cs.id = c.status_id
       WHERE c.planned_workout_id = :planned_workout_id
   ),
   updated_at = datetime('now')
 WHERE id = :planned_workout_id
   AND EXISTS (SELECT 1 FROM planned_workout_components WHERE planned_workout_id = :planned_workout_id);


-- name: delete_components_for!
-- Wipe all components for a planned workout (used when re-splitting title)
DELETE FROM planned_workout_components WHERE planned_workout_id = :planned_workout_id;


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
