"""History handlers — /lastrun /lastgym."""
from __future__ import annotations
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


def _fmt_dur(sec):
    if not sec or sec <= 0:
        return "—"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


async def cmd_lastrun(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with t.TursoDB() as db:
        r = t.last_run(db)
    if not r:
        await update.message.reply_text("Brak biegow w bazie.")
        return

    dist = r.get("distance_km") or 0
    pace = _fmt_pace(r.get("pace_sec_per_km"))
    dur = _fmt_dur(r.get("moving_sec"))
    hr = r.get("hr_avg") or "—"
    hr_max = r.get("hr_max") or "—"
    cad = r.get("cadence_avg") or "—"
    gct_bal = r.get("gct_balance_left_pct")
    gct = r.get("ground_contact_ms")
    vo = r.get("vertical_oscillation_cm")
    elev = r.get("elevation_gain_m") or 0
    te = r.get("training_effect_aerobic")
    load = r.get("training_load")

    lines = [
        f"🏃 <b>Ostatni bieg</b> — {r['date']}"
        + (f" <i>({escape(r.get('name') or '')})</i>" if r.get('name') else ""),
        f"📏 {dist:.2f} km · ⏱ {dur} · {pace} · ⬆ {elev} m",
        f"❤ HR avg <b>{hr}</b> / max {hr_max} · 👣 {cad} spm",
    ]
    if gct_bal is not None:
        bias = "L" if gct_bal > 50 else ("P" if gct_bal < 50 else "•")
        lines.append(f"⚖ GCT bal <b>{gct_bal:.1f}%</b> ({bias}) · gct {gct}ms · vo {vo}cm")
    if te or load:
        te_s = f"TE {te:.1f}" if te else ""
        load_s = f"load {load:.0f}" if load else ""
        lines.append(f"📊 {' · '.join(x for x in (te_s, load_s) if x)}")
    if r.get("type"):
        lines.append(f"🏷 typ: {escape(r['type'])}")
    if r.get("notes"):
        lines.append(f"📝 {escape(r['notes'][:200])}")
    src = r.get("source") or "?"
    lines.append(f"\n<i>source: {src}</i>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def _fmt_set(s: dict) -> str:
    w = s.get("weight_kg")
    reps = s.get("reps")
    dur = s.get("duration_sec")
    if dur:
        val = f"{dur}s"
    elif reps:
        val = f"{reps} rep"
    else:
        val = "?"
    if w:
        per_side = " (per strone)" if s.get("weight_per_side") else ""
        val = f"{val} @{w:g}kg{per_side}"
    rpe = f" RPE {s['rpe']}" if s.get("rpe") else ""
    return f"    {s['set_num']}: {val}{rpe}"


async def cmd_lastgym(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with t.TursoDB() as db:
        g = t.last_gym(db)
        if not g:
            await update.message.reply_text("Brak sesji silowni w bazie.")
            return
        sets = t.gym_sets(db, g["id"])

    lines = [
        f"💪 <b>Ostatnia silownia</b> — {g['date']}"
        + (f" <i>({escape(g.get('context') or '')})</i>" if g.get("context") else ""),
    ]
    if g.get("duration_min"):
        lines.append(f"⏱ {g['duration_min']} min"
                     + (f" · ❤ HR avg {g['hr_avg']}" if g.get("hr_avg") else "")
                     + (f" · kcal {g['calories']}" if g.get("calories") else ""))

    # Group sets by exercise
    by_ex: dict[str, list[dict]] = {}
    for s in sets:
        by_ex.setdefault(s["exercise"], []).append(s)

    for ex, xs in by_ex.items():
        lines.append(f"\n<b>{escape(ex)}</b>")
        for s in xs:
            lines.append(_fmt_set(s))

    if g.get("notes"):
        lines.append(f"\n📝 {escape(g['notes'][:250])}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
