"""Makrocykl: podział na fazy + progresja objętości tydzień po tygodniu.

Deterministyczne: te same wejścia → ten sam plan. Wejście = stan "na dziś"
(baseline z realnych km), więc ponowne wygenerowanie po każdym tygodniu
automatycznie reaguje na odchylenia (patrz progress.adapt_baseline).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

from planner import methodology as M
from planner.paces import training_paces, pace_range
from planner.events import TuneUp, apply_tune_ups, apply_quality_caps, apply_kind_bans, smooth_long
from planner.sessions import long_km as _long_km, quality as _quality


@dataclass(frozen=True)
class MacroInput:
    start: date                          # poniedziałek pierwszego planowanego tygodnia
    baseline_km: float                   # średnia realnych km z ostatnich tygodni
    vdot: float
    race_date: date | None = None
    distance_km: float | None = None
    peak_km: float | None = None
    runs_per_week: int = 5
    safety_max_km: float | None = None
    last_race: tuple[date, float] | None = None   # (data, km) → roztrenowanie
    horizon_weeks: int = 12              # gdy brak celu (maintenance)
    progression: str = "daniels"         # daniels: +1.6 km/bieg co blok | weekly: min(+7%, +5 km)/tydz.
    tune_ups: tuple[TuneUp, ...] = ()    # starty pośrednie B/C
    quality_caps: tuple[tuple[date, int], ...] = ()   # ((do_daty, max_akcentów), ...)
    long_start_km: float | None = None   # najdłuższy long z ostatnich tygodni
    long_step_km: float | None = None    # max przyrost longa tydz/tydz (None = bez limitu)
    long_cap_km: float | None = None     # twardy limit longa (reguła usera)
    taper_factors: tuple[float, ...] | None = None    # nadpisanie tapera metodyki
    kind_bans: tuple[tuple[str, date, str], ...] = ()  # ((kind, do_daty, zamiennik), ...)
    forced_deloads: tuple[date, ...] = ()               # np. Święta — deload w tym tygodniu


@dataclass
class WeekTarget:
    week_start: date
    phase: str
    week_in_phase: int
    is_deload: bool
    target_km: float
    long_km: float
    quality: list[dict] = field(default_factory=list)   # [{"kind": "T", "km": 5.0}]
    is_race_week: bool = False
    tune_up: str | None = None                          # "B"/"C" gdy w tygodniu start pośredni

    def to_dict(self) -> dict:
        d = asdict(self)
        d["week_start"] = self.week_start.isoformat()
        return d


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def allocate_phases(n: int) -> list[str]:
    """Podziel n tygodni budowy na I/II/III. Krótko → priorytet baza > III > II."""
    if n <= 0:
        return []
    order = [M.PHASE_BASE, M.PHASE_LATE, M.PHASE_EARLY]
    if n < sum(M.PHASE_MIN_WEEKS.values()):
        counts, rem = {}, n
        for p in order:
            counts[p] = min(M.PHASE_MIN_WEEKS[p], rem)
            rem -= counts[p]
    else:
        counts = {p: max(M.PHASE_MIN_WEEKS[p], int(n * w)) for p, w in M.PHASE_WEIGHTS.items()}
        i = 0
        while sum(counts.values()) < n:
            counts[order[i % 3]] += 1
            i += 1
        while sum(counts.values()) > n:
            p = max((q for q in counts if counts[q] > M.PHASE_MIN_WEEKS[q]), key=counts.get)
            counts[p] -= 1
    return ([M.PHASE_BASE] * counts[M.PHASE_BASE] + [M.PHASE_EARLY] * counts[M.PHASE_EARLY]
            + [M.PHASE_LATE] * counts[M.PHASE_LATE])


def recovery_weeks_needed(start: date, last_race: tuple[date, float] | None) -> int:
    """Daniels: 1 dzień easy na 3 km startu, liczone od dnia startu."""
    if not last_race:
        return 0
    race_day, km = last_race
    days_left = math.ceil(km / M.RECOVERY_KM_PER_DAY) - (start - race_day).days
    if days_left <= 0:
        return 0
    return min(math.ceil(days_left / 7), len(M.RECOVERY_WEEK_FACTORS))


def _phase_sequence(inp: MacroInput) -> list[str]:
    n_rec = recovery_weeks_needed(inp.start, inp.last_race)
    if not inp.race_date:
        return [M.PHASE_RECOVERY] * n_rec + [M.PHASE_MAINTENANCE] * max(inp.horizon_weeks - n_rec, 0)
    total = (monday(inp.race_date) - inp.start).days // 7 + 1
    if total <= 0:
        return []
    n_taper = min(len(M.by_distance(M.TAPER_BY_DISTANCE, inp.distance_km or 21.1)), total)
    n_rec = min(n_rec, total - n_taper)
    build = allocate_phases(total - n_taper - n_rec)
    return [M.PHASE_RECOVERY] * n_rec + build + [M.PHASE_TAPER] * n_taper


def build_macrocycle(inp: MacroInput) -> list[WeekTarget]:
    phases = _phase_sequence(inp)
    distance = inp.distance_km or 21.1
    family = M.distance_family(distance)
    default_peak = max(M.by_distance(M.DEFAULT_PEAK_KM, distance), inp.baseline_km)
    peak = inp.peak_km or default_peak
    if inp.safety_max_km:
        peak = min(peak, inp.safety_max_km)
    level = max(min(inp.baseline_km, peak), M.MIN_WEEK_KM)
    peak_reached = level
    long_pace = sum(pace_range("L", training_paces(inp.vdot))) // 2
    taper_f = list(inp.taper_factors or M.by_distance(M.TAPER_BY_DISTANCE, distance))
    weekly = inp.progression == "weekly"
    deload_factor = M.WEEKLY_DELOAD_FACTOR if weekly else M.DELOAD_FACTOR
    n_taper = phases.count(M.PHASE_TAPER)
    weeks: list[WeekTarget] = []
    build_idx = 0
    b_weeks = {(monday(t.race_date) - inp.start).days // 7 for t in inp.tune_ups if t.priority == "B"}
    forced = {(monday(d) - inp.start).days // 7 for d in inp.forced_deloads}
    for i, phase in enumerate(phases):
        ws = inp.start + timedelta(weeks=i)
        wip = 1 + sum(1 for p in phases[:i] if p == phase)
        deload = False
        if phase == M.PHASE_RECOVERY:
            target = level * M.RECOVERY_WEEK_FACTORS[wip - 1]
        elif phase == M.PHASE_TAPER:
            target = peak_reached * taper_f[len(taper_f) - n_taper + wip - 1]
        elif i in b_weeks:
            target = level      # start B = odciążenie (apply_tune_ups liczy mini-taper)
            build_idx = 0       # licznik deloadu od nowa, poziom bez wzrostu
        else:
            deload = build_idx % M.DELOAD_EVERY == M.DELOAD_EVERY - 1
            nxt = phases[i + 1] if i + 1 < len(phases) else None
            if deload and (nxt == M.PHASE_TAPER or {i + 1, i + 2} & (b_weeks | forced)):
                deload = False  # taper / start B / wymuszony deload tuż obok same odciążają
            if i in forced:
                deload, build_idx = True, M.DELOAD_EVERY - 1   # licznik: kolejny deload za 4 tyg.
            target = level * (deload_factor if deload else 1.0)
            peak_reached = max(peak_reached, level)
            if weekly and not deload:
                level = min(level * (1 + M.WEEKLY_STEP_PCT), level + M.WEEKLY_STEP_KM, peak)
            elif deload and not weekly:
                step = min(level * M.STEP_MAX_PCT, inp.runs_per_week * M.STEP_KM_PER_RUN)
                level = min(level + step, peak)
            build_idx += 1
        race_week = bool(inp.race_date) and ws == monday(inp.race_date)
        if race_week:
            target += distance  # mnożnik tapera = km treningowe; start doliczamy
        target = round(max(target, M.MIN_WEEK_KM), 1)
        weeks.append(WeekTarget(
            week_start=ws, phase=phase, week_in_phase=wip, is_deload=deload,
            target_km=target,
            long_km=0.0 if race_week else _long_km(target, distance, long_pace, inp.long_cap_km),
            quality=_quality(phase, family, target, deload, race_week),
            is_race_week=race_week,
        ))
    apply_tune_ups(weeks, inp.tune_ups)
    apply_kind_bans(weeks, inp.kind_bans)
    apply_quality_caps(weeks, inp.quality_caps)
    if inp.long_step_km:
        smooth_long(weeks, inp.long_start_km, inp.long_step_km)
    return weeks
