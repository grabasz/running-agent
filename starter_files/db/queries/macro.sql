-- ============================================
-- MACRO PLAN (Faza 20) — cele treningowe + referencyjny makroplan
-- ============================================

-- name: goal_add<!
INSERT INTO training_goals
    (user_id, race_id, name, race_date, distance_km, target_time_sec,
     start_date, baseline_km, peak_km, runs_per_week, status, source, methodology, notes)
VALUES
    (:user_id, :race_id, :name, :race_date, :distance_km, :target_time_sec,
     :start_date, :baseline_km, :peak_km, :runs_per_week, :status, :source, :methodology, :notes);


-- name: goal_active^
SELECT *
  FROM training_goals
 WHERE user_id = :user_id AND status = 'active'
 ORDER BY id DESC
 LIMIT 1;


-- name: goal_by_status^
-- 'shadow' = plan porównawczy (np. deterministyczny obok aktywnego planu AI).
SELECT *
  FROM training_goals
 WHERE user_id = :user_id AND status = :status
 ORDER BY id DESC
 LIMIT 1;


-- name: goal_archive_status!
UPDATE training_goals
   SET status = 'archived'
 WHERE user_id = :user_id AND status = :status;


-- name: goal_archive_active!
UPDATE training_goals
   SET status = 'archived'
 WHERE user_id = :user_id AND status = 'active';


-- name: week_add!
INSERT INTO macro_plan_weeks
    (user_id, goal_id, week_start, phase, week_in_phase, is_deload, is_race_week,
     target_km, long_km, quality_json, long_structure, key_session, notes)
VALUES
    (:user_id, :goal_id, :week_start, :phase, :week_in_phase, :is_deload, :is_race_week,
     :target_km, :long_km, :quality_json, :long_structure, :key_session, :notes);


-- name: weeks_for_goal
SELECT *
  FROM macro_plan_weeks
 WHERE goal_id = :goal_id AND user_id = :user_id
 ORDER BY week_start;


-- name: actual_weekly_km
-- Realne km per tydzień liczone z `runs` (świeższe niż cache weekly_volume).
-- date(d, 'weekday 0', '-6 days') = poniedziałek tygodnia ISO.
SELECT date(date, 'weekday 0', '-6 days') AS week_start,
       ROUND(SUM(distance_km), 1)          AS km,
       COUNT(*)                            AS num_runs
  FROM runs
 WHERE user_id = :user_id
   AND date >= :since
 GROUP BY 1
 ORDER BY 1;


-- name: max_pain_since^
SELECT COALESCE(MAX(pain_0_10), 0) AS max_pain
  FROM body_state
 WHERE user_id = :user_id AND date >= :since;


-- name: last_race_before^
SELECT date, distance_km, name
  FROM races
 WHERE user_id = :user_id AND date <= :before
 ORDER BY date DESC
 LIMIT 1;


-- name: delete_components_of_planned_runs!
DELETE FROM planned_workout_components
 WHERE planned_workout_id IN (
   SELECT id FROM planned_workouts
    WHERE user_id = :user_id
      AND week_start = :week_start
      AND status_id = (SELECT id FROM workout_statuses WHERE key = 'planned')
      AND type_id IN (SELECT id FROM workout_types WHERE category = 'run'));


-- name: delete_planned_runs_in_week!
-- Usuwa TYLKO biegi o statusie 'planned' — siłownia/mobility i wykonane zostają.
DELETE FROM planned_workouts
 WHERE user_id = :user_id
   AND week_start = :week_start
   AND status_id = (SELECT id FROM workout_statuses WHERE key = 'planned')
   AND type_id IN (SELECT id FROM workout_types WHERE category = 'run');


-- name: rule_add!
INSERT INTO plan_rules (user_id, goal_id, rule_type, subject, value, valid_from, valid_to, reason)
VALUES (:user_id, :goal_id, :rule_type, :subject, :value, :valid_from, :valid_to, :reason);


-- name: rules_active_on
SELECT rule_type, subject, value, valid_from, valid_to, reason
  FROM plan_rules
 WHERE user_id = :user_id AND goal_id = :goal_id
   AND (valid_from IS NULL OR valid_from <= :on_date)
   AND (valid_to IS NULL OR valid_to >= :on_date)
 ORDER BY rule_type, subject;


-- name: pace_add!
INSERT INTO pace_targets (user_id, goal_id, zone, min_sec, max_sec, valid_from, source)
VALUES (:user_id, :goal_id, :zone, :min_sec, :max_sec, :valid_from, :source);


-- name: paces_on
-- Najnowsze tempo per strefa obowiązujące w danym dniu.
SELECT p.zone, p.min_sec, p.max_sec, p.valid_from, p.source
  FROM pace_targets p
 WHERE p.user_id = :user_id AND p.goal_id = :goal_id AND p.valid_from <= :on_date
   AND p.valid_from = (SELECT MAX(q.valid_from) FROM pace_targets q
                        WHERE q.goal_id = p.goal_id AND q.zone = p.zone AND q.valid_from <= :on_date)
 ORDER BY p.zone;


-- name: revision_add!
INSERT INTO plan_revisions (user_id, goal_id, event_type, reason, diff_json, accepted)
VALUES (:user_id, :goal_id, :event_type, :reason, :diff_json, :accepted);


-- name: revisions_for_goal
SELECT id, created_at, event_type, reason, diff_json, accepted
  FROM plan_revisions
 WHERE user_id = :user_id AND goal_id = :goal_id
 ORDER BY created_at DESC, id DESC;
