-- Migracja 009: Users profile extension (task #58)
-- Adds columns needed by auto-planner + form-trend (per-user max_hr).
-- Nullable — istniejący user_id=1 (Bartek) i user_id=2 (Mati) dostają defaults
-- w UPDATE-ach na końcu; new users startują z NULL.

PRAGMA foreign_keys = OFF;

-- Idempotent ALTER-y — SQLite od 3.35 wspiera "ADD COLUMN IF NOT EXISTS" tylko
-- via pragma_table_info hack. Kolumny są nullable + z DEFAULT NULL, więc drugie
-- uruchomienie po prostu wybuchnie "duplicate column name" — łapiemy w migration
-- runnerze. Jeśli runner naiwny (surowy sqlite3), user powtórzenia miga jak
-- normalny błąd i przeskakuje.
ALTER TABLE users ADD COLUMN max_hr             INTEGER;
ALTER TABLE users ADD COLUMN resting_hr         INTEGER;
ALTER TABLE users ADD COLUMN birth_year         INTEGER;
ALTER TABLE users ADD COLUMN safety_max_km_week INTEGER;
ALTER TABLE users ADD COLUMN preferences        TEXT;

-- Defaults dla istniejących userów.
-- Bartek: max_hr z HR max obserwowanego w 2026 (~195), grupowe biegi Kuba Pn / Pychowice Śr.
UPDATE users
   SET max_hr             = 195,
       resting_hr         = 48,
       birth_year         = 1985,
       safety_max_km_week = NULL,
       preferences        = '{"group_days":[["Mon","easy"],["Wed","easy"]]}'
 WHERE id = 1;

-- Mati: age-based estimated max_hr (220 - 14 = 206, cap 205), safety cap 30 km/tydz.
UPDATE users
   SET max_hr             = 205,
       resting_hr         = 55,
       birth_year         = 2012,
       safety_max_km_week = 30,
       preferences        = '{"safety_notes":"14yo — no I/R, easy 80%+"}'
 WHERE id = 2;

PRAGMA foreign_keys = ON;
