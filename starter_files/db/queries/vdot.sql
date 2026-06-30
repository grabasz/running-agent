-- ============================================
-- VDOT HISTORY
-- ============================================

-- name: add<!
INSERT INTO vdot_history (date, vdot, t_pace_sec, source, notes)
VALUES (:date, :vdot, :t_pace_sec, :source, :notes);


-- name: current^
SELECT *
  FROM vdot_history
 ORDER BY date DESC
 LIMIT 1;


-- name: history
SELECT *
  FROM vdot_history
 ORDER BY date DESC
 LIMIT :limit;
