"""Life handlers — Rozkminy: /n /tasks /done /goals /goal."""
from __future__ import annotations
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import turso as t  # type: ignore


NOTE_ICONS = {"insight": "💡", "decision": "✅", "reminder": "🔔", "idea": "🌱"}
CAT_ICONS = {"sport": "🏃", "praca": "💼", "dom": "🏠",
             "relacje": "❤️", "zdrowie": "🩺", "inne": "🧩"}


# ============================================================
# /n — dodaj notatke (reminder tworzy TASK)
# ============================================================

async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /n <kategoria> <tresc>
    kategorie: insight | decision | reminder | idea
    (reminder => auto tworzy task w kategorii 'inne', priority='med')

    Przyklad:
      /n insight prehab W1 aktywacja OK, glute medius czuje
      /n reminder kupic zele bez cukru
    """
    if not ctx.args:
        await update.message.reply_text(
            "Uzycie: /n &lt;insight|decision|reminder|idea&gt; &lt;tresc&gt;\n\n"
            "Np. /n insight kadencja 172 boli mniej",
            parse_mode=ParseMode.HTML,
        )
        return

    category = ctx.args[0].lower()
    if category not in t.VALID_NOTE_CATEGORIES:
        await update.message.reply_text(
            f"Nieznana kategoria: <b>{escape(category)}</b>.\n"
            f"Dostepne: insight, decision, reminder, idea.",
            parse_mode=ParseMode.HTML,
        )
        return

    content = " ".join(ctx.args[1:]).strip()
    if not content:
        await update.message.reply_text("Brak tresci notatki.")
        return

    with t.TursoDB() as db:
        if category == "reminder":
            # Reminder => task w kategorii 'inne' bez due_date
            task_id = t.add_task(
                db,
                category="inne",
                title=content[:200],
                description=None,
                success_criteria=None,
                due_date=None,
                priority="med",
            )
            # Dodaj tez notatke laczaca do taska (zeby historia)
            t.add_note(
                db,
                category="reminder",
                content=content,
                related_task_id=task_id,
                source="telegram",
            )
            await update.message.reply_text(
                f"🔔 <b>Task #{task_id}</b> utworzony (kategoria: inne)\n"
                f"<i>{escape(content)}</i>\n\n"
                f"Uzyj /done {task_id} zeby zaznaczyc jako zrobione.",
                parse_mode=ParseMode.HTML,
            )
        else:
            note_id = t.add_note(
                db,
                category=category,
                content=content,
                source="telegram",
            )
            icon = NOTE_ICONS.get(category, "•")
            await update.message.reply_text(
                f"{icon} <b>Notatka #{note_id}</b> ({category})\n"
                f"<i>{escape(content)}</i>",
                parse_mode=ParseMode.HTML,
            )


# ============================================================
# /tasks — lista otwartych taskow
# ============================================================

async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /tasks — wszystkie otwarte taski (grupowane po kategoriach)
    /tasks sport — tylko z jednej kategorii
    """
    cat_filter = None
    if ctx.args:
        cat_filter = ctx.args[0].lower()
        if cat_filter not in t.VALID_TASK_CATEGORIES:
            await update.message.reply_text(
                f"Nieznana kategoria: <b>{escape(cat_filter)}</b>.\n"
                f"Dostepne: {', '.join(sorted(t.VALID_TASK_CATEGORIES))}.",
                parse_mode=ParseMode.HTML,
            )
            return

    with t.TursoDB() as db:
        rows = t.tasks_open(db, category=cat_filter)

    if not rows:
        msg = (f"Brak otwartych taskow"
               f" w kategorii <b>{escape(cat_filter)}</b>." if cat_filter else
               "Brak otwartych taskow.")
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    lines = [f"📋 <b>Otwarte taski"
             + (f" — {escape(cat_filter)}" if cat_filter else "")
             + f"</b> ({len(rows)})\n"]

    if cat_filter:
        for r in rows:
            lines.append(_fmt_task_line(r))
    else:
        # Group by category
        by_cat: dict[str, list[dict]] = {}
        for r in rows:
            by_cat.setdefault(r["category"], []).append(r)
        for cat, xs in by_cat.items():
            icon = CAT_ICONS.get(cat, "•")
            lines.append(f"\n<b>{icon} {cat}</b>")
            for r in xs:
                lines.append(_fmt_task_line(r))

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def _fmt_task_line(r: dict) -> str:
    prio_icon = {"high": "🔥 ", "med": "▲ ", "low": "▽ "}.get(r.get("priority") or "", "")
    due = f" · 📅 {r['due_date']}" if r.get("due_date") else ""
    return f"  #{r['id']} {prio_icon}{escape(r['title'][:80])}{due}"


# ============================================================
# /done <id>
# ============================================================

async def cmd_task_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/done <task_id>"""
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Uzycie: /done <id>\nnp. /done 5")
        return
    tid = int(ctx.args[0])
    with t.TursoDB() as db:
        existing = t.task_by_id(db, tid)
        if not existing:
            await update.message.reply_text(f"Task #{tid} nie istnieje.")
            return
        if existing["status"] == "done":
            await update.message.reply_text(
                f"Task #{tid} juz jest zaznaczony jako zrobiony. "
                f"Zeby cofnac, edytuj na dashboardzie."
            )
            return
        t.task_mark_done(db, tid)
    await update.message.reply_text(
        f"✅ Task #{tid} zrobiony: <i>{escape(existing['title'][:100])}</i>",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# /goals — cele tygodnia
# ============================================================

async def cmd_goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ws = t.monday_of()
    with t.TursoDB() as db:
        rows = t.week_goals(db, ws)
    if not rows:
        await update.message.reply_text(
            f"Brak celow na tydzien {ws}.\n"
            f"Ustaw: /goal &lt;kategoria&gt; &lt;cel&gt;\n"
            f"Np. /goal praca wyslac 5 CV",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = [f"🎯 <b>Cele tygodnia — od {ws}</b>\n"]
    for r in rows:
        cat = r["category"]
        icon = CAT_ICONS.get(cat, "•")
        st = "✅" if r["status"] == "done" else "⏸"
        lines.append(f"{st} {icon} <b>{cat}</b>: {escape(r['goal'])}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ============================================================
# /goal <kategoria> <cel>
# ============================================================

async def cmd_set_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/goal <kategoria> <cel>"""
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "Uzycie: /goal &lt;kategoria&gt; &lt;cel&gt;\n\n"
            f"Kategorie: {', '.join(sorted(t.VALID_TASK_CATEGORIES))}.\n"
            "Np. /goal praca wyslac 5 CV",
            parse_mode=ParseMode.HTML,
        )
        return
    cat = ctx.args[0].lower()
    if cat not in t.VALID_TASK_CATEGORIES:
        await update.message.reply_text(
            f"Nieznana kategoria: <b>{escape(cat)}</b>.\n"
            f"Dostepne: {', '.join(sorted(t.VALID_TASK_CATEGORIES))}.",
            parse_mode=ParseMode.HTML,
        )
        return
    goal_text = " ".join(ctx.args[1:]).strip()
    if not goal_text:
        await update.message.reply_text("Brak tresci celu.")
        return

    ws = t.monday_of()
    with t.TursoDB() as db:
        t.upsert_goal(db, week_start=ws, category=cat, goal=goal_text)

    icon = CAT_ICONS.get(cat, "•")
    await update.message.reply_text(
        f"🎯 Cel <b>{cat}</b> {icon} na tydzien {ws}: <i>{escape(goal_text)}</i>",
        parse_mode=ParseMode.HTML,
    )
