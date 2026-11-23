"""Reguły metodyczne makroplanowania — jedno źródło prawdy dla planera.

Baza: Jack Daniels "Daniels' Running Formula" (fazy I-IV, limity jakości, progresja
objętości), uzupełniona o taper/roztrenowanie z Pfitzingera ("Advanced Marathoning",
"Faster Road Racing") tam, gdzie Daniels jest mniej konkretny.

ODSTĘPSTWO od "zero hardkodów danych" (CODING_STANDARDS): to nie są dane usera,
tylko stałe metodyki (jak tabela VDOT) — wersjonowane razem z kodem planera,
żeby wynik był deterministyczny i testowalny. Preferencje usera idą z DB.
"""
from __future__ import annotations

# ============================================
# Skala VDOT projektu
# ============================================
# Project VDOT scale (fitness.md) ≈ canonical Daniels & Gilbert VDOT + 6.3.
VDOT_CAL_OFFSET = 6.3

# ============================================
# Fazy (Daniels: I base → II early quality → III late quality → IV taper/final)
# ============================================
PHASE_RECOVERY = "recovery"          # roztrenowanie po starcie (Daniels: 1 dzień easy / 3 km startu)
PHASE_BASE = "base"                  # I  — E + strides, budowa objętości
PHASE_EARLY = "early_quality"        # II — R + T (ekonomia + próg)
PHASE_LATE = "late_quality"          # III — I + T (VO2max + próg), specyfika dystansu
PHASE_TAPER = "taper"                # IV — redukcja objętości, utrzymanie intensywności
PHASE_MAINTENANCE = "maintenance"    # brak celu — cykl 3:1 na bazie

PHASE_LABELS = {
    PHASE_RECOVERY: "Roztrenowanie",
    PHASE_BASE: "I · Baza",
    PHASE_EARLY: "II · Wczesna jakość",
    PHASE_LATE: "III · Późna jakość",
    PHASE_TAPER: "IV · Taper",
    PHASE_MAINTENANCE: "Utrzymanie",
    # fazy planów z panelu AI / ręcznych (Pfitzinger-style)
    "build": "Budowa", "specific": "Specyfika", "race": "Start",
}

# Udział faz w tygodniach budowy (po odjęciu tapera i roztrenowania).
# Daniels 24 tyg. = 6/6/6/6; przy krótszym cyklu priorytet: baza > III > II.
PHASE_WEIGHTS = {PHASE_BASE: 0.35, PHASE_EARLY: 0.30, PHASE_LATE: 0.35}
PHASE_MIN_WEEKS = {PHASE_BASE: 2, PHASE_EARLY: 1, PHASE_LATE: 2}

# ============================================
# Taper — tygodnie i mnożniki objętości szczytu (ostatni = tydzień startu).
# Daniels: 5K 5-7 dni | 10K 7 dni | HM ~10 dni | M 14-21 dni.
# W tygodniu startu mnożnik dotyczy km POZA startem (start doliczany osobno).
# ============================================
TAPER_BY_DISTANCE = [  # (max_km, [mnożniki od najdalszego do tygodnia startu])
    (5.5, [0.55]),
    (11.0, [0.50]),
    (22.0, [0.75, 0.40]),
    (99.0, [0.75, 0.60, 0.30]),
]

# ============================================
# Roztrenowanie po starcie (Daniels: 1 dzień easy na każde 3 km dystansu startu)
# ============================================
RECOVERY_KM_PER_DAY = 3.0
RECOVERY_WEEK_FACTORS = [0.50, 0.70, 0.85]   # kolejne tygodnie po starcie

# ============================================
# Progresja objętości
# ============================================
DELOAD_EVERY = 4                 # 3 tygodnie obciążenia + 1 odciążenie (Daniels/Pfitzinger)
DELOAD_FACTOR = 0.75             # odciążenie = -25%
STEP_MAX_PCT = 0.10              # max +10% na blok
STEP_KM_PER_RUN = 1.6            # Daniels: +1 mila na sesję biegową w tygodniu, co 3-4 tyg.
MIN_WEEK_KM = 10.0

# Progresja "weekly" (notatka #42 usera): co tydzień min(+7%, +5 km), deload co 4. ~70%.
WEEKLY_STEP_PCT = 0.07
WEEKLY_STEP_KM = 5.0
WEEKLY_DELOAD_FACTOR = 0.70
LONG_STEP_MAX_KM = 3.0           # long max +3 km względem dotychczasowego maksimum

# Starty pośrednie (B = mini-taper; C = start zamiast akcentu, bez zmian objętości)
TUNE_UP_B_WEEK_FACTOR = 0.70     # tydzień startu B: -30% (start wliczony)
TUNE_UP_B_AFTER_FACTOR = 0.85    # tydzień po starcie B: zredukowany, 1 akcent
TUNE_UP_B_PRE_FACTOR = 0.85      # tydzień przed startem B ≥ HM: lekki spadek
TUNE_UP_RECOVERY_MIN_KM = 21.0   # lżejszy tydzień po starcie tylko od HM wzwyż

# Domyślny szczyt objętości per dystans (gdy user nie poda) — km/tydz.
DEFAULT_PEAK_KM = [(5.5, 50.0), (11.0, 55.0), (22.0, 65.0), (99.0, 80.0)]

# ============================================
# Limity jakości (Daniels) — % tygodniowego km i absolutny cap
# ============================================
QUALITY_CAPS = {         # kind: (max_pct_of_week, max_km)
    "T": (0.10, 16.0),
    "I": (0.08, 10.0),
    "R": (0.05, 8.0),
    "M": (0.20, 29.0),
}
LONG_PCT = 0.25                  # long ≤ 25% tygodnia ...
LONG_PCT_LOW_VOLUME = 0.30       # ... lub 30% gdy tydzień < 64 km
LOW_VOLUME_KM = 64.0
LONG_MAX_MIN = 150               # long ≤ 150 min
# Maraton: long jako główny bodziec (Pfitzinger: 29-35 km przy 55-70 mil/tydz., do ~3 h).
LONG_PCT_MARATHON = 0.45
LONG_MAX_MIN_MARATHON = 180
LONG_MAX_KM = [(5.5, 16.0), (11.0, 18.0), (22.0, 22.0), (99.0, 35.0)]
WARMUP_COOLDOWN_KM = 4.0         # rozgrzewka + schłodzenie przy sesji Q
MIN_EASY_RUN_KM = 4.0

# Sesje jakościowe per faza i dystans: lista "kind" (Q1, Q2).
# "S" = strides (przebieżki) dołożone do easy, nie osobna sesja Q.
QUALITY_BY_PHASE = {
    PHASE_BASE:        {"short": ["S"],      "half": ["S"],      "marathon": ["S"]},
    PHASE_EARLY:       {"short": ["R", "T"], "half": ["R", "T"], "marathon": ["R", "T"]},
    PHASE_LATE:        {"short": ["I", "T"], "half": ["T", "I"], "marathon": ["M", "T"]},
    PHASE_TAPER:       {"short": ["I"],      "half": ["T"],      "marathon": ["M"]},
    PHASE_RECOVERY:    {"short": [],         "half": [],         "marathon": []},
    PHASE_MAINTENANCE: {"short": ["T"],      "half": ["T"],      "marathon": ["T"]},
}
# Udział jakości w tygodniu (przed capami) — tygodniowa "dawka" danego typu.
QUALITY_SHARE = {"T": 0.10, "I": 0.07, "R": 0.05, "M": 0.15}

# Realny przyrost VDOT u wytrenowanego biegacza: ~1 pkt / 4-6 tyg. (Daniels).
VDOT_GAIN_PER_WEEK_REALISTIC = 0.2
VDOT_GAIN_PER_WEEK_AMBITIOUS = 0.3

# ============================================
# Safety (body_state) — z REFACTOR_PLAN Faza 20
# ============================================
PAIN_EASY_ONLY = 5    # max ból ≥5 w 7 dni → tylko easy, objętość ×0.7
PAIN_DOWNGRADE = 3    # max ból ≥3 → degradacja intensywności, objętość ×0.9
PAIN_EASY_FACTOR = 0.70
PAIN_DOWNGRADE_FACTOR = 0.90
DOWNGRADE = {"I": "T", "R": "S", "T": "M", "M": "M", "S": "S"}

# ============================================
# Adaptacja do wykonania (planned vs actual)
# ============================================
ADHERENCE_LOW = 0.80     # <80% planu → nie podnoś poziomu, rebaseline na real
ADHERENCE_HIGH = 1.15    # >115% planu → nie dokładaj ponad plan


def by_distance(table: list[tuple[float, object]], distance_km: float):
    """Wybierz wartość z tabeli progowej [(max_km, value), ...] dla dystansu."""
    for max_km, value in table:
        if distance_km <= max_km:
            return value
    return table[-1][1]


def distance_family(distance_km: float) -> str:
    """5K/10K → short, HM → half, M → marathon."""
    if distance_km <= 11.0:
        return "short"
    if distance_km <= 22.0:
        return "half"
    return "marathon"
