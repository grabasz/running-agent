-- ============================================
-- BODY WEIGHT + BODY STATE
-- ============================================

-- name: weight_log!
INSERT INTO body_weight (date, kg, notes)
VALUES (:date, :kg, :notes)
ON CONFLICT(date) DO UPDATE SET
    kg = excluded.kg,
    notes = excluded.notes;


-- name: weight_recent
SELECT *
  FROM body_weight
 ORDER BY date DESC
 LIMIT :limit;


-- name: state_log!
-- NOTE: UNIQUE(date, location) is single-tenant. Multi-tenant rebuild deferred
-- to Faza 18B — until then only user_id=1 (bartek) safely writes body_state.
INSERT INTO body_state (user_id, date, location, pain_0_10, doms, notes)
VALUES (:user_id, :date, :location, :pain_0_10, :doms, :notes)
ON CONFLICT(date, location) DO UPDATE SET
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
