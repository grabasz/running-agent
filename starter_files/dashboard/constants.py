"""Stale uzywane w wielu miejscach dashboardu.

Zgodnie z CODING_STANDARDS: konfiguracja / stale na gorze, nie inline
w srodku funkcji. Kazda kategoria/tab/status ma miejsce tutaj.
"""
from __future__ import annotations

# ============================================
# Rozkminy — cele + zadania + notatki
# ============================================

LIFE_CATEGORIES = ["sport", "praca", "dom", "relacje", "zdrowie", "inne"]
LIFE_ICONS = {
    "sport": "🏃",
    "praca": "💼",
    "dom": "🏠",
    "relacje": "❤️",
    "zdrowie": "🩺",
    "inne": "🧩",
}

NOTE_CATEGORIES = ["insight", "decision", "reminder", "idea"]
NOTE_ICONS = {
    "insight": "💡",
    "decision": "✅",
    "reminder": "🔔",
    "idea": "🌱",
}


# ============================================
# Bieżący tydzień — kategorie i statusy planned_workouts
# ============================================

CATEGORY_TABS = [
    ("all",      "🗓️ Wszystko"),
    ("run",      "🏃 Biegi"),
    ("strength", "💪 Siłownia"),
    ("other",    "🧘 Inne"),
]

STATUS_OPTIONS = [
    ("planned",  "⏸️ Zaplanowany"),
    ("done",     "✅ Wykonany"),
    ("modified", "⚠️ Zmodyfikowany"),
    ("skipped",  "❌ Pominięty"),
]


# ============================================
# Artefakty sesji
# ============================================

ARTIFACT_CATEGORIES = {
    "diagnostic_test": ("🔬", "Test diagnostyczny"),
    "plan":            ("📋", "Plan"),
    "hypothesis":      ("🧪", "Hipoteza"),
    "recipe":          ("📝", "Recipe / howto"),
    "howto":           ("📝", "Recipe / howto"),
    "other":           ("📎", "Inne"),
}


# ============================================
# VDOT calibration
# ============================================

# Project VDOT scale (fitness.md) ≈ canonical Daniels & Gilbert VDOT + 6.3.
# Verified against fitness.md Race Predictors @55: 20:18 / 42:21 / 1:33:43 / 3:15:28 (±5s).
VDOT_CAL_OFFSET = 6.3
