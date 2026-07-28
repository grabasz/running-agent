"""Plan handlers — /today /tomorrow /week /schedule_week."""
from __future__ import annotations
from datetime import date, timedelta
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import turso as t  # type: ignore


def _fmt_pace(sec):
    if not sec or sec <= 0:
        return "—"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}/km"


def _fmt_workout_line(w: dict) -> str:
    """Jedna linia planu — HTML."""
    icon = w.get("type_icon") or "•"
    status_icon = w.get("status_icon") or ""
    title = escape(w.get("title") or w.get("type_display") or "")
    parts = [f"{icon} {status_icon} <b>{title}</b>"]
    dist = w.get("target_distance_km")
    pace = w.get("target_pace_sec_per_km")
    hr = w.get("target_hr_max")
    extras = []
    if dist:
        extras.append(f"{dist:g} km")
    if pace:
        extras.append(_fmt_pace(pace))
    if hr:
        extras.append(f"HR≤{hr}")
    if extras:
        parts.append(f"  <i>{' · '.join(extras)}</i>")
    notes = w.get("notes")
    if notes:
        parts.append(f"  📝 {escape(notes[:200])}")
    return "\n".join(parts)


async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with t.TursoDB() as db:
        rows = t.planned_today(db)
    if not rows:
        await update.message.reply_text(
            f"Brak planu na dzis ({t.today_iso()}).\n"
            f"Uzyj /schedule_week zeby wygenerowac scaffold."
        )
        return
    header = f"📅 <b>Dzis — {t.today_iso()}</b>"
    body = "\n\n".join(_fmt_workout_line(r) for r in rows)
    await update.message.reply_text(f"{header}\n\n{body}", parse_mode=ParseMode.HTML)


async def cmd_tomorrow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tomorrow = t.tomorrow_iso()
    with t.TursoDB() as db:
        rows = t.planned_for_date(db, tomorrow)
    if not rows:
        await update.message.reply_text(f"Brak planu na jutro ({tomorrow}).")
        return
    header = f"📅 <b>Jutro — {tomorrow}</b>"
    body = "\n\n".join(_fmt_workout_line(r) for r in rows)
    await update.message.reply_text(f"{header}\n\n{body}", parse_mode=ParseMode.HTML)


DAY_NAMES = ["Pon", "Wt", "Sr", "Cz", "Pt", "Sob", "Nd"]


async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ws = t.monday_of()
    with t.TursoDB() as db:
        rows = t.planned_week(db, ws)
    if not rows:
        await update.message.reply_text(
            f"Brak planu na biezacy tydzien ({ws}).\n"
            f"Uzyj /schedule_week zeby utworzyc szkielet."
        )
        return
    # Group by date
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    lines = [f"📅 <b>Tydzien od {ws}</b>\n"]
    from datetime import date as _date
    for offset in range(7):
        day_iso = (date.fromisoformat(ws) + timedelta(days=offset)).isoformat()
        day_name = DAY_NAMES[offset]
        if day_iso in by_date:
            for w in by_date[day_iso]:
                icon = w.get("type_icon") or "•"
                status = w.get("status_icon") or ""
                title = escape(w.get("title") or w.get("type_display") or "")
                dist = w.get("target_distance_km")
                dist_str = f" ({dist:g}km)" if dist else ""
                lines.append(f"<b>{day_name}</b> {icon}{status} {title}{dist_str}")
        else:
            lines.append(f"<b>{day_name}</b> —")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ============================================================
# /schedule_week — scaffold according to your usual weekly rhythm
# ============================================================
#
# Customize this template to your own week. It is loaded from
# `bot/weekly_template.json` if that file exists, otherwise the generic
# fallback below is used. Fields:
#   day:        0=Mon, 1=Tue, ..., 6=Sun
#   type_key:   one of workout_types.key in the DB (e.g. easy/long/tempo/rest)
#   title:      Telegram-visible title. Use {km} for easy distance, {km_long}
#               for the /schedule_week [long_km] argument.
#   distance, pace_sec_per_km, hr_max: targets (nullable)
#   notes:      free-text
import json
from pathlib import Path

_DEFAULT_SCAFFOLD = [
    # (offset_from_monday, type_key, title, distance_km, pace_sec_per_km, hr_max, notes)
    (0, "easy", "🏃 Easy {km}km @ conversational pace",
     6.0, 390, 145, "Warm up 10min, then steady."),
    (1, "easy", "🏃 Easy {km}km + light strides at the end",
     5.0, 390, 145, "4x100m strides after the run — form, not speed."),
    (2, "tempo", "🏃 Tempo — 2km warm + 4km @ T + 2km cool",
     8.0, 265, 165, "Tempo effort should feel comfortably hard, not race pace."),
    (3, "easy", "🏃 Easy {km}km + 💪 Strength session",
     5.0, 390, 145, "Recovery pace run + full-body lifts in the evening."),
    (4, "rest", "🛑 REST + mobility 20-30min", None, None, None,
     "Foam roll + hip mobility. Prepare the legs for the long run."),
    (5, "long", "🏃 Long run {km_long}km — steady effort",
     None, 380, 152,
     "Fuel + hydrate. Last 20% slightly faster if legs feel good."),
    (6, "easy", "🏃 Easy {km}km recovery (or REST if fatigued)",
     5.0, 400, 140, "Listen to the body — swap for REST if soreness > 2/10."),
]


def _load_scaffold():
    tpl = Path(__file__).resolve().parent.parent / "weekly_template.json"
    if not tpl.exists():
        return _DEFAULT_SCAFFOLD
    try:
        data = json.loads(tpl.read_text(encoding="utf-8"))
        return [
            (d["day"], d["type_key"], d["title"],
             d.get("distance_km"), d.get("pace_sec_per_km"), d.get("hr_max"),
             d.get("notes", ""))
            for d in data
        ]
    except Exception:
        return _DEFAULT_SCAFFOLD


_SCAFFOLD = _load_scaffold()


async def cmd_schedule_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Wygeneruj scaffold tygodnia od najblizszego poniedzialku.

    Args (opcjonalne):
        /schedule_week — cel long = 15 km
        /schedule_week 18 — cel long = 18 km
        /schedule_week 18 next — poniedzialek nastepnego tygodnia
    """
    args = ctx.args or []
    long_km = 15.0
    week_offset = 0
    for a in args:
        if a.lower() == "next":
            week_offset = 7
        elif a.replace(".", "").isdigit():
            long_km = float(a)

    ws = (date.fromisoformat(t.monday_of()) + timedelta(days=week_offset)).isoformat()

    with t.TursoDB() as db:
        if t.week_has_plan(db, ws):
            await update.message.reply_text(
                f"Tydzien {ws} juz ma plan.\n"
                f"Jesli chcesz nadpisac — najpierw usun na dashboardzie.\n"
                f"(Bot nie kasuje planow zeby nie zniszczyc twojej pracy.)"
            )
            return

        created = []
        for offset, type_key, title_tpl, dist, pace, hr, notes in _SCAFFOLD:
            day = (date.fromisoformat(ws) + timedelta(days=offset)).isoformat()
            if type_key == "long":
                title = title_tpl.format(km_long=int(long_km))
                dist_final = long_km
            else:
                title = title_tpl.format(km=int(dist) if dist else 0)
                dist_final = dist
            pid = t.planned_add(
                db,
                date=day, week_start=ws, type_key=type_key,
                title=title,
                target_distance_km=dist_final,
                target_pace_sec_per_km=pace,
                target_hr_max=hr,
                notes=notes,
            )
            created.append((day, title, pid))

    lines = [f"✅ Scaffold tygodnia <b>{ws}</b> utworzony ({len(created)} sesji):\n"]
    for day, title, pid in created:
        lines.append(f"  {day}  {escape(title[:70])}")
    lines.append("\nEdytuj szczegoly na dashboardzie (🧠 Rozkminy nie, sekcja Przeglad).")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
