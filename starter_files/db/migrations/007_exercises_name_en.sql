-- 007_exercises_name_en.sql — dodac angielska nazwe do katalogu cwiczen

ALTER TABLE exercises ADD COLUMN name_en TEXT;

-- Uzupelnij istniejace 5 cwiczen
UPDATE exercises SET name_en = 'ITB Foam Rolling (right)'      WHERE key = 'itb_roll_prawy';
UPDATE exercises SET name_en = 'Foot Sole Ball Rolling (right)' WHERE key = 'stopa_roll_prawa';
UPDATE exercises SET name_en = 'Straight Leg Raise (right)'    WHERE key = 'slr_prawa';
UPDATE exercises SET name_en = 'Clamshell (right)'             WHERE key = 'clamshell_prawa';
UPDATE exercises SET name_en = 'Lying ITB Stretch'             WHERE key = 'itb_stretch_lezacy';
