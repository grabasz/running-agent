-- ============================================
-- RACES
-- ============================================

-- name: add<!
INSERT INTO races
    (date, name, distance_km, target_time_sec, actual_time_sec,
     is_pb, place_overall, place_category, conditions_temp_c, strategy, notes)
VALUES
    (:date, :name, :distance_km, :target_time_sec, :actual_time_sec,
     :is_pb, :place_overall, :place_category, :conditions_temp_c, :strategy, :notes);


-- name: update_result!
-- Fill in actual time and refresh is_pb
UPDATE races
   SET actual_time_sec = :actual_time_sec,
       notes = COALESCE(:notes, notes)
 WHERE date = :date;


-- name: recompute_pbs!
-- Set is_pb=1 for the best time per distance (rounded to 0.1km)
UPDATE races SET is_pb = 0;

-- name: flag_pbs!
UPDATE races
   SET is_pb = 1
 WHERE id IN (
     SELECT r1.id FROM races r1
      WHERE r1.actual_time_sec IS NOT NULL
        AND r1.actual_time_sec = (
            SELECT MIN(r2.actual_time_sec) FROM races r2
             WHERE ABS(r2.distance_km - r1.distance_km) < 0.5
               AND r2.actual_time_sec IS NOT NULL
        )
 );


-- name: pb_for_distance^
SELECT *
  FROM races
 WHERE distance_km BETWEEN :min_km AND :max_km
   AND actual_time_sec IS NOT NULL
 ORDER BY actual_time_sec ASC
 LIMIT 1;


-- name: upcoming
SELECT *
  FROM races
 WHERE actual_time_sec IS NULL
   AND date >= date('now')
 ORDER BY date;


-- name: history
SELECT *
  FROM races
 WHERE actual_time_sec IS NOT NULL
 ORDER BY date DESC;
