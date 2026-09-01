-- ============================================
-- BODY WEIGHT + BODY STATE
-- ============================================

-- name: weight_log!
-- Multi-tenant: UNIQUE(user_id, date) after migration 010.
INSERT INTO body_weight (user_id, date, kg, notes)
VALUES (:user_id, :date, :kg, :notes)
ON CONFLICT(user_id, date) DO UPDATE SET
    kg = excluded.kg,
    notes = excluded.notes;


-- name: weight_recent
SELECT *
  FROM body_weight
 WHERE user_id = :user_id
 ORDER BY date DESC
 LIMIT :limit;


-- name: state_log!
-- Multi-tenant: UNIQUE(user_id, date, location) — migration 008 already rebuilt table.
INSERT INTO body_state (user_id, date, location, pain_0_10, doms, notes)
VALUES (:user_id, :date, :location, :pain_0_10, :doms, :notes)
ON CONFLICT(user_id, date, location) DO UPDATE SET
    pain_0_10 = excluded.pain_0_10,
    doms = excluded.doms,
    notes = excluded.notes;


-- name: state_recent
SELECT *
  FROM body_state
 WHERE user_id = :user_id
   AND date >= date('now', :since)
 ORDER BY date DESC;


-- name: state_by_location
SELECT *
  FROM body_state
 WHERE user_id = :user_id
   AND location = :location
 ORDER BY date DESC
 LIMIT :limit;
