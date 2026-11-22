"""Deterministyczny planer makrocyklu (Faza 20 — Auto-planner).

Moduły:
  methodology — stałe metodyki (Daniels + Pfitzinger: fazy, taper, deload, limity Q)
  paces       — tempa Danielsa, predyktor czasu, VDOT z wyniku
  macro       — makrocykl: fazy + objętość tydzień po tygodniu
  week        — mikrocykl: tydzień → dni (format db-plan-week-bulk) + safety layer
  progress    — progres do celu, adherence plan vs real, wskazówki replanu
  repo        — zapis/odczyt w DB (jedyny moduł dotykający conn)
"""
from planner.macro import MacroInput, WeekTarget, build_macrocycle, monday
from planner.week import render_week, apply_safety
from planner.progress import goal_progress, adherence, baseline_from_actual, replan_advice

__all__ = ["MacroInput", "WeekTarget", "build_macrocycle", "monday", "render_week",
           "apply_safety", "goal_progress", "adherence", "baseline_from_actual", "replan_advice"]
