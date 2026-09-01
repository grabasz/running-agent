-- ============================================
-- USERS profile (extended in migration 009)
-- ============================================

-- name: profile^
-- Full user profile: id, name, display_name, max_hr, resting_hr, birth_year,
-- safety_max_km_week, preferences (JSON string). Consumer parses preferences.
SELECT id, name, display_name, garmin_token_dir,
       max_hr, resting_hr, birth_year, safety_max_km_week, preferences,
       created_at
  FROM users
 WHERE id = :user_id;


-- name: update_profile!
-- Partial update — pass NULL for fields to keep unchanged (COALESCE).
UPDATE users
   SET max_hr             = COALESCE(:max_hr, max_hr),
       resting_hr         = COALESCE(:resting_hr, resting_hr),
       birth_year         = COALESCE(:birth_year, birth_year),
       safety_max_km_week = COALESCE(:safety_max_km_week, safety_max_km_week),
       preferences        = COALESCE(:preferences, preferences)
 WHERE id = :user_id;


-- name: max_hr$
-- Scalar: return max_hr or NULL if unset. Consumer decides fallback (e.g. 195 for user 1).
SELECT max_hr FROM users WHERE id = :user_id;


-- name: list
-- Wszyscy userzy (dashboard admin, MCP subject discovery).
SELECT id, name, display_name, max_hr, safety_max_km_week
  FROM users
 ORDER BY id;
