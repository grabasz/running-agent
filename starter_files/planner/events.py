"""Zdarzenia i reguły nakładane na makrocykl po zbudowaniu progresji.

- starty pośrednie B/C (mini-taper, tydzień po, start zamiast akcentu),
- limity liczby akcentów do daty (np. "1 akcent do 31.12" — reguła kolana),
- wygładzenie longa: max +N km tydzień do tygodnia (user przeskakuje plan).

Wszystko czyste funkcje na liście WeekTarget — deterministyczne i testowalne.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta

from planner import methodology as M


@dataclass(frozen=True)
class TuneUp:
    race_date: date
    distance_km: float
    priority: str = "B"      # B = mini-taper + lżejszy tydzień po | C = start zamiast akcentu


def _week_of(weeks, d: date) -> int | None:
    for i, w in enumerate(weeks):
        if w.week_start <= d < w.week_start + timedelta(days=7):
            return i
    return None


def apply_tune_ups(weeks: list, tune_ups: tuple[TuneUp, ...]) -> None:
    """Modyfikuje tygodnie startów pośrednich in-place."""
    for t in tune_ups:
        i = _week_of(weeks, t.race_date)
        if i is None or weeks[i].is_race_week:
            continue
        w = weeks[i]
        race_q = {"kind": "race", "km": round(t.distance_km, 1), "date": t.race_date.isoformat()}
        weekend_race = t.race_date.weekday() >= 5
        if t.priority == "C":
            w.quality = [race_q] + w.quality[1:]
            continue
        factor = M.TUNE_UP_B_WEEK_FACTOR
        w.target_km = round(max(w.target_km * factor, t.distance_km + M.MIN_WEEK_KM), 1)
        w.quality = [race_q]
        w.is_deload = False
        if weekend_race:
            w.long_km = 0.0   # start zastępuje longa
        else:
            w.long_km = round(min(w.long_km, w.target_km * M.LONG_PCT_LOW_VOLUME), 1)
        w.tune_up = t.priority
        if t.distance_km >= M.TUNE_UP_RECOVERY_MIN_KM and i > 0 and not weeks[i - 1].is_deload:
            prev = weeks[i - 1]
            prev.target_km = round(prev.target_km * M.TUNE_UP_B_PRE_FACTOR, 1)
            prev.long_km = round(min(prev.long_km, prev.target_km * M.LONG_PCT_LOW_VOLUME), 1)
        if t.distance_km >= M.TUNE_UP_RECOVERY_MIN_KM and i + 1 < len(weeks)                 and not weeks[i + 1].is_race_week:
            nxt = weeks[i + 1]
            nxt.target_km = round(nxt.target_km * M.TUNE_UP_B_AFTER_FACTOR, 1)
            nxt.quality = nxt.quality[:1] if weekend_race else nxt.quality
            nxt.long_km = round(min(nxt.long_km, nxt.target_km * M.LONG_PCT_LOW_VOLUME), 1)


def apply_kind_bans(weeks: list, bans: tuple[tuple[str, date, str], ...]) -> None:
    """bans: ((kind, do_daty, zamiennik), ...) — np. ("R", 2027-02-01, "S") przy dwójce."""
    for w in weeks:
        for kind, until, repl in bans:
            if w.week_start < until:
                w.quality = [dict(q, kind=repl, km=0.0 if repl == "S" else q["km"])
                             if q["kind"] == kind else q for q in w.quality]


def apply_quality_caps(weeks: list, caps: tuple[tuple[date, int], ...]) -> None:
    """caps: ((do_kiedy_włącznie, max_akcentów), ...) — strides 'S' się nie liczą, start tak."""
    for w in weeks:
        for until, max_q in sorted(caps):
            if w.week_start <= until:
                kept, n = [], 0
                for q in w.quality:
                    if q["kind"] == "S":
                        kept.append(q)
                    elif n < max_q:
                        kept.append(q)
                        n += 1
                w.quality = kept
                break


def smooth_long(weeks: list, start_long_km: float | None, step_km: float) -> None:
    """Long rośnie max o step_km względem najdłuższego dotychczasowego longa.

    Tydzień odciążenia/startu może mieć krótszy long — kolejny tydzień
    wraca do poprzedniego maksimum (+step), nie startuje od zera.
    """
    best = start_long_km if start_long_km else None
    for w in weeks:
        if w.long_km <= 0:
            continue
        if best is not None:
            w.long_km = round(min(w.long_km, best + step_km), 1)
        if not w.is_deload and not w.is_race_week and not w.tune_up:
            best = max(best or 0.0, w.long_km)
