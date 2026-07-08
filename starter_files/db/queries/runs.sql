-- ============================================
-- RUNS + LAPS + STREAMS
-- ============================================

-- name: run_upsert_strava<!
-- Upsert run from Strava (key: strava_id). Pace computed in api.py before call.
-- Garmin-only columns (running dynamics, training_effect etc) left NULL.
INSERT INTO runs
    (strava_id, source, date, start_time, name, distance_km, duration_sec, moving_sec, pace_sec_per_km,
     hr_avg, hr_max, elevation_gain_m, elevation_loss_m, cadence_avg, power_avg,
     type, notes, raw_json)
VALUES
    (:strava_id, 'strava', :date, :start_time, :name, :distance_km, :duration_sec, :moving_sec, :pace_sec_per_km,
     :hr_avg, :hr_max, :elevation_gain_m, :elevation_loss_m, :cadence_avg, :power_avg,
     :type, :notes, :raw_json)
ON CONFLICT(strava_id) DO UPDATE SET
    date = excluded.date,
    start_time = excluded.start_time,
    name = excluded.name,
    distance_km = excluded.distance_km,
    duration_sec = excluded.duration_sec,
    moving_sec = excluded.moving_sec,
    pace_sec_per_km = excluded.pace_sec_per_km,
    hr_avg = excluded.hr_avg,
    hr_max = excluded.hr_max,
    elevation_gain_m = excluded.elevation_gain_m,
    elevation_loss_m = excluded.elevation_loss_m,
    cadence_avg = excluded.cadence_avg,
    power_avg = excluded.power_avg,
    type = excluded.type,
    notes = excluded.notes,
    raw_json = excluded.raw_json;


-- name: run_upsert_garmin<!
-- Upsert run from Garmin Connect (key: garmin_activity_id). Full column set — running dynamics, TE, body battery.
INSERT INTO runs
    (garmin_activity_id, source, date, start_time, name, distance_km, duration_sec, moving_sec, pace_sec_per_km,
     hr_avg, hr_max, cadence_avg, power_avg, power_max, power_norm,
     elevation_gain_m, elevation_loss_m,
     vertical_oscillation_cm, ground_contact_ms, gct_balance_left_pct, stride_length_cm, vertical_ratio_pct,
     training_effect_aerobic, training_effect_anaerobic, training_load,
     recovery_time_hours, body_battery_start, body_battery_end, vo2max_at_activity,
     hr_time_z1_sec, hr_time_z2_sec, hr_time_z3_sec, hr_time_z4_sec, hr_time_z5_sec,
     type, notes, raw_json)
VALUES
    (:garmin_activity_id, 'garmin', :date, :start_time, :name, :distance_km, :duration_sec, :moving_sec, :pace_sec_per_km,
     :hr_avg, :hr_max, :cadence_avg, :power_avg, :power_max, :power_norm,
     :elevation_gain_m, :elevation_loss_m,
     :vertical_oscillation_cm, :ground_contact_ms, :gct_balance_left_pct, :stride_length_cm, :vertical_ratio_pct,
     :training_effect_aerobic, :training_effect_anaerobic, :training_load,
     :recovery_time_hours, :body_battery_start, :body_battery_end, :vo2max_at_activity,
     :hr_time_z1_sec, :hr_time_z2_sec, :hr_time_z3_sec, :hr_time_z4_sec, :hr_time_z5_sec,
     :type, :notes, :raw_json)
ON CONFLICT(garmin_activity_id) DO UPDATE SET
    date = excluded.date,
    start_time = excluded.start_time,
    name = excluded.name,
    distance_km = excluded.distance_km,
    duration_sec = excluded.duration_sec,
    moving_sec = excluded.moving_sec,
    pace_sec_per_km = excluded.pace_sec_per_km,
    hr_avg = excluded.hr_avg,
    hr_max = excluded.hr_max,
    cadence_avg = excluded.cadence_avg,
    power_avg = excluded.power_avg,
    power_max = excluded.power_max,
    power_norm = excluded.power_norm,
    elevation_gain_m = excluded.elevation_gain_m,
    elevation_loss_m = excluded.elevation_loss_m,
    vertical_oscillation_cm = excluded.vertical_oscillation_cm,
    ground_contact_ms = excluded.ground_contact_ms,
    gct_balance_left_pct = excluded.gct_balance_left_pct,
    stride_length_cm = excluded.stride_length_cm,
    vertical_ratio_pct = excluded.vertical_ratio_pct,
    training_effect_aerobic = excluded.training_effect_aerobic,
    training_effect_anaerobic = excluded.training_effect_anaerobic,
    training_load = excluded.training_load,
    recovery_time_hours = excluded.recovery_time_hours,
    body_battery_start = excluded.body_battery_start,
    body_battery_end = excluded.body_battery_end,
    vo2max_at_activity = excluded.vo2max_at_activity,
    hr_time_z1_sec = excluded.hr_time_z1_sec,
    hr_time_z2_sec = excluded.hr_time_z2_sec,
    hr_time_z3_sec = excluded.hr_time_z3_sec,
    hr_time_z4_sec = excluded.hr_time_z4_sec,
    hr_time_z5_sec = excluded.hr_time_z5_sec,
    type = excluded.type,
    notes = excluded.notes,
    raw_json = excluded.raw_json;


-- name: link_strava_to_garmin!
-- When run already exists from Garmin, add strava_id via UPDATE.
-- Called when strava_sync sees a run matching by date+distance ±100m.
UPDATE runs
   SET strava_id = :strava_id
 WHERE id = :run_id
   AND strava_id IS NULL;


-- name: find_by_date_and_distance^
-- For Strava/Garmin deduplication by date and distance ±tolerance km
SELECT *
  FROM runs
 WHERE date = :date
   AND ABS(distance_km - :distance_km) <= :tolerance
 LIMIT 1;


-- name: recent
SELECT *
  FROM runs
 ORDER BY date DESC
 LIMIT :limit;


-- name: recent_by_type
SELECT *
  FROM runs
 WHERE type = :type
 ORDER BY date DESC
 LIMIT :limit;


-- name: by_date^
SELECT *
  FROM runs
 WHERE date = :date
 ORDER BY id DESC
 LIMIT 1;


-- name: recent_with_dynamics
-- Runs with running dynamics (Garmin only) from last N days
SELECT date, name, distance_km, pace_sec_per_km, hr_avg, cadence_avg,
       ground_contact_ms, gct_balance_left_pct,
       vertical_oscillation_cm, stride_length_cm, vertical_ratio_pct,
       training_effect_aerobic
  FROM runs
 WHERE source = 'garmin'
   AND date >= date('now', :since)
   AND ground_contact_ms IS NOT NULL
 ORDER BY date DESC;


-- name: gct_balance_progression
-- Trend of GCT balance L% across recent runs — detect asymmetry shifts over time
SELECT date, distance_km, gct_balance_left_pct,
       ABS(gct_balance_left_pct - 50.0) AS asymmetry_pct
  FROM runs
 WHERE gct_balance_left_pct IS NOT NULL
 ORDER BY date DESC
 LIMIT :limit;


-- ============================================
-- LAPS
-- ============================================

-- name: lap_add<!
INSERT INTO run_laps
    (run_id, lap_num, distance_km, duration_sec, pace_sec_per_km,
     hr_avg, hr_max, cadence_avg, power_avg, elev_up_m, elev_down_m,
     vertical_oscillation_cm, ground_contact_ms, gct_balance_left_pct,
     stride_length_cm, vertical_ratio_pct)
VALUES
    (:run_id, :lap_num, :distance_km, :duration_sec, :pace_sec_per_km,
     :hr_avg, :hr_max, :cadence_avg, :power_avg, :elev_up_m, :elev_down_m,
     :vertical_oscillation_cm, :ground_contact_ms, :gct_balance_left_pct,
     :stride_length_cm, :vertical_ratio_pct);


-- name: laps_for_run
SELECT *
  FROM run_laps
 WHERE run_id = :run_id
 ORDER BY lap_num;


-- name: delete_laps_for_run!
-- Before re-importing a run (e.g. update from Garmin) drop old laps
DELETE FROM run_laps WHERE run_id = :run_id;


-- ============================================
-- STREAMS (per-second time-series)
-- ============================================

-- name: stream_add<!
INSERT INTO run_streams (run_id, sec, hr, pace_sec_per_km, cadence, power, altitude_m)
VALUES (:run_id, :sec, :hr, :pace_sec_per_km, :cadence, :power, :altitude_m);


-- name: streams_for_run
SELECT *
  FROM run_streams
 WHERE run_id = :run_id
 ORDER BY sec;


-- name: delete_streams_for_run!
DELETE FROM run_streams WHERE run_id = :run_id;


-- name: hr_above_threshold_seconds$
-- How many seconds HR was above threshold during this run
SELECT COUNT(*)
  FROM run_streams
 WHERE run_id = :run_id
   AND hr >= :threshold;
