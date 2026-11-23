"""Makroplan Cracovia Maraton 18.04.2027 — synteza panelu AI (Pfitzinger × Magness, 2 rundy).

Seed danych usera (nie stałe metodyki) — ładowany raz skryptem scripts/seed_macro_cracovia.py.
Kolumny tygodnia: (week_start, phase, km, deload, long_km, long_structure, key_session, notes)
"""
GOAL = {
    "name": "Cracovia Maraton 2027 — sub-3:30", "race_date": "2027-04-18", "distance_km": 42.195,
    "target_time_sec": 12600, "start_date": "2026-11-23", "baseline_km": 40.6, "peak_km": 68,
    "runs_per_week": 5, "source": "ai-panel", "methodology": "Pfitzinger × Magness (panel 2 trenerów)",
    "notes": "Starty: 10K Sylwestrowy 31.12 (test), HM Lago Maggiore 07.03 (B, chęć sub-1:38), M 18.04 sub-3:30.",
}
W = [
 ("2026-11-23", "base", 47, 0, 17, "16-17 km E, twardy limit 18", "T 3x2 km @4:32-4:40", "Tydzień już zaplanowany — bez zmian."),
 ("2026-11-30", "base", 50, 0, 19, "19 km E 5:35-6:10", "T 2x3 km @4:33-4:40", "Mezocykl 1: baza + próg, 1 akcent."),
 ("2026-12-07", "base", 53, 0, 21, "21 km E, ostatnie 3 km 5:15-5:25", "T 3x2.5 km @4:33-4:40", "Siła 2x/tydz. od grudnia."),
 ("2026-12-14", "base", 55, 0, 22, "22 km E", "T 5 km ciągłe @4:35-4:40 · MLR 12 km E", "Start MLR (pierwsze, co bramka obcina)."),
 ("2026-12-21", "base", 44, 1, 17, "17 km E", "T 4x1.6 km @4:33-4:40 + przebieżki", "Deload świąteczny."),
 ("2026-12-28", "race", 44, 0, 16, "16 km E w nd 03.01", "START 10K Sylwestrowy czw 31.12: 44:30-45:15", "Wynik = kalibracja T/M/I na styczeń."),
 ("2027-01-04", "build", 54, 0, 21, "21 km E, ostatnie 4 @5:05-5:10", "T 6 km @4:33-4:38 · MLR 13 km E", "2. akcent tylko gdy kolano ≤2/10."),
 ("2027-01-11", "build", 57, 0, 24, "24 km: 18 E + 6 @M 4:58-5:03", "T 2x3.2 km cruise @4:32-4:38 · MLR 14 km E", "Pierwszy finisz @M w longu."),
 ("2027-01-18", "build", 60, 0, 27, "27 km E, ostatnie 4 @5:05", "T 7 km @4:34-4:40 · MLR 14 km E", "Krok objętości, bez I."),
 ("2027-01-25", "build", 50, 1, 20, "20 km E", "I 5x800 m @4:15-4:22 (tylko dwójka 0/10, inaczej 4x1.6 km T)", "Deload; koniec kickboxingu."),
 ("2027-02-01", "build", 62, 0, 26, "26 km: 16 E + 10 @M 4:58-5:03", "T 5x1.6 km @4:32-4:36 · MLR 14 km E", "Koniec zakazu sprintów — nadal bez podbiegów."),
 ("2027-02-08", "specific", 65, 0, 30, "30 km E, ostatnie 3 @5:10-5:20; żele 60 g/h", "T 3x3 km @4:32-4:36 · MLR 15 km E", "Pierwsze 30 km."),
 ("2027-02-15", "specific", 66, 0, 28, "28 km: 10 E + 14 @M 4:56-5:02 + 4 E", "T alternacja 8 km (1 km @4:35 / 1 km @5:00) · MLR 14 km E", "Kluczowy long specyficzny przed HM."),
 ("2027-02-22", "specific", 56, 0, 22, "22 km: 13 E + 3x2 km @4:40 / 1 km @5:00", "T 6 km @4:33-4:38 · MLR 12 km E", "Lekki spadek przed HM."),
 ("2027-03-01", "race", 44, 0, 0, "START HM Lago Maggiore nd 07.03 (+3 rozgrzewki)", "wt 3x1.6 km @4:35 · HM: 1-5 km 4:40-4:42, 5-15 km 4:37-4:39 (HR≤172), od 15 km wyścig", "Mini-taper; podróż pt/sb = 4 km shakeout."),
 ("2027-03-08", "recovery", 48, 1, 20, "20 km E, HR≤145, bez M", "czw 5 km @M tylko gdy HRV/RHR wróciły", "Regeneracja po HM i podróży; reset tempa M wg wyniku HM."),
 ("2027-03-15", "specific", 60, 0, 28, "28 km: 8 E + 16 @M + 4 E (próba generalna tempa)", "T 4x2 km @4:32-4:36 · MLR 14 km E", "16 km @M przy HR≤168 bez dryfu = 3:30 realne."),
 ("2027-03-22", "specific", 68, 0, 32, "32 km: 22 E + 6 @M 4:58-5:05 (Wielkanoc — można w sb)", "T cruise 3x3 km @4:32-4:38 · MLR 15 km E", "Szczyt; 70 km tylko gdy bramki zielone 3 tyg. Bez I."),
 ("2027-03-29", "taper", 56, 0, 24, "24 km: 14 E + 10 @M (generalka: buty, śniadanie, żele)", "T 2x3 km @4:33-4:38 · MLR 13 km E", "Taper 1. Ostatni dłuższy blok @M — 3 tyg. przed."),
 ("2027-04-05", "taper", 45, 0, 18, "18 km: 13 E + 5 @M", "T 4x1.6 km @4:33-4:38 · MLR 12 km E", "Taper 2: intensywność zostaje, objętość spada."),
 ("2027-04-12", "race", 69, 0, 0, "START Cracovia Maraton nd 18.04: 4:58-5:00 równo", "wt 8 km z 2x2 km @M · sb shakeout 4-5 km", "~27 km + maraton. Ładowanie węgli od czw."),
]
RULES = [
 ("ban", "sprinty / podbiegi powtórzeniowe", "zakaz; od 01.02 tylko luźne przebieżki", "2026-11-23", "2027-04-18", "dwójka prawa"),
 ("cap", "week_km", "68 (70 raz, gdy bramki zielone 3 tyg.)", None, None, "hist. max 68.5"),
 ("cap", "long_km", "33; przyrost max +3 km względem dotychczasowego max", None, None, "22.11 przeskok +40%"),
 ("cap", "quality_per_week", "1", "2026-11-23", "2026-12-31", "kolano PFPS"),
 ("gate", "2nd_quality", "2 akcenty tylko gdy kolano ≤2/10 rano", "2027-01-01", None, "kolano PFPS"),
 ("gate", "daily_readiness", "kolano ≤2, dwójka 0-1, RHR ≤+5 bpm, HRV w normie, nastrój ok → inaczej easy/wolne", None, None, "Magness"),
 ("gate", "reactive_deload", "2 niezaliczone bramki w 7 dni albo kolano ≥3 dwa dni z rzędu → -25% km, long -20%, 1 akcent T", None, None, "Magness"),
 ("cap", "overshoot", ">10% ponad plan (long lub tydzień) → kolejny tydzień max planowany, bez 'kredytu'", None, None, "skłonność do przeskakiwania"),
 ("gate", "gct_asymmetry", ">51/49 przez 3+ km lub dryf HR >8 bpm @M → następny long bez @M", None, None, "marker zmęczenia"),
 ("gate", "i_pace", "I tylko przy dwójce 0/10, nigdy w tygodniu nowego najdłuższego longa/szczytu", "2027-01-01", None, "dwójka"),
 ("allow", "kickboxing", "bez low kicków; liczy się jako dzień ciężki, ≥48h od longa", None, "2027-01-31", "decyzja #39"),
 ("allow", "sila", "1x XI, 2x XII-I, 1x II-III (glute/kolano, jednonóż)", None, None, "decyzja #39"),
 ("allow", "basen", "1x/tydz. cały blok", None, None, "decyzja #39"),
 ("cap", "recovery_runs", "recovery solo; grupy easy HR≤145", None, None, "grupy wciągają"),
 ("gate", "missed_days", "1-2 dni → dalej wg planu; 3-6 → tydzień 70%, 1×T; 7+/gorączka → 2 tyg. 60/80% i powrót do tygodnia pasującego objętością", None, None, "#42"),
 ("gate", "mlr_first_cut", "przy niezaliczonej bramce najpierw wypada MLR, long zostaje", None, None, "Pfitzinger"),
]
PACES = [  # zone, min, max, valid_from, source
 ("E", 330, 380, "2026-11-23", "panel; HR≤145"),
 ("M", 295, 302, "2026-11-23", "cel 4:58; reset po 10K i HM"),
 ("T", 272, 280, "2026-11-23", "HM 1:38:59 → T 4:32-4:40"),
 ("I", 253, 262, "2027-01-01", "po teście 31.12; tylko dwójka 0/10"),
 ("HM", 277, 282, "2027-03-01", "Lago: 4:37-4:42, HR≤172 do 15 km"),
]
