"""Telegram bot — mobile access to the running project.

Uruchomienie lokalne:
    cd bot && python bot.py

Deploy: patrz README.md w tym folderze.
"""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

sys.path.insert(0, str(Path(__file__).parent))

import config  # type: ignore
from handlers import plan, history, life, body  # type: ignore


logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bot")


# ============================================================
# Whitelist middleware
# ============================================================

async def _whitelist_gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if user is allowed. Log and reply politely if not."""
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    if uid in config.ALLOWED_USER_IDS:
        return True
    log.warning("Odrzucony uzytkownik: %s (@%s)", uid,
                update.effective_user.username or "?")
    if update.message:
        await update.message.reply_text(
            f"Ten bot jest prywatny.\n\n"
            f"Twoj Telegram user_id: <code>{uid}</code>\n"
            f"Dodaj go do ALLOWED_USER_IDS w konfiguracji jesli to twoj bot.",
            parse_mode=ParseMode.HTML,
        )
    return False


def guarded(handler):
    """Wrap handler so it only runs for whitelisted users."""
    async def _wrapped(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await _whitelist_gate(update, ctx):
            return
        try:
            return await handler(update, ctx)
        except Exception as e:
            log.exception("Handler crash: %s", e)
            if update.message:
                await update.message.reply_text(
                    f"Blad: <code>{type(e).__name__}: {e}</code>",
                    parse_mode=ParseMode.HTML,
                )
    _wrapped.__name__ = handler.__name__
    return _wrapped


# ============================================================
# /start + /help
# ============================================================

HELP_TEXT = """<b>Bartek Running bot</b>

<b>Plan treningu</b>
/today — plan na dzis
/tomorrow — plan na jutro
/week — caly biezacy tydzien
/schedule_week [km] — utworz scaffold tygodnia (jesli pusty)

<b>Historia</b>
/lastrun — ostatni bieg (pace/HR/GCT)
/lastgym — ostatnia silownia (cwiczenia + ciezary)

<b>Rozkminy</b>
/n insight|decision|reminder|idea &lt;tresc&gt; — dodaj notatke
    (reminder tworzy TASK, reszta tworzy notatke)
/tasks [kategoria] — otwarte taski
/done &lt;id&gt; — zaznacz task jako wykonany
/goals — cele tygodnia
/goal &lt;kategoria&gt; &lt;cel&gt; — ustaw cel tygodnia

<b>Cialo</b>
/log &lt;miejsce&gt; &lt;0-10&gt; [notatka] — pain/DOMS
    np. /log kolano_prawe 2 klika przy schodach

Kategorie tasks/goals: sport, praca, dom, relacje, zdrowie, inne
Kategorie notes: insight, decision, reminder, idea
"""


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_whoami(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Diagnostic — returns your user_id (nie wymaga whitelist)."""
    u = update.effective_user
    await update.message.reply_text(
        f"Twoje ID: <code>{u.id}</code>\nUsername: @{u.username or '?'}",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# Setup / boot
# ============================================================

async def _post_init(app: Application):
    """After the bot connects — set the command menu shown in Telegram UI."""
    commands = [
        BotCommand("today", "Plan na dzis"),
        BotCommand("tomorrow", "Plan na jutro"),
        BotCommand("week", "Plan tygodnia"),
        BotCommand("lastrun", "Ostatni bieg"),
        BotCommand("lastgym", "Ostatnia silownia"),
        BotCommand("tasks", "Otwarte taski"),
        BotCommand("goals", "Cele tygodnia"),
        BotCommand("n", "Dodaj notatke (insight/decision/reminder/idea)"),
        BotCommand("log", "Log body_state (kolano/lydka/etc)"),
        BotCommand("help", "Pomoc"),
    ]
    await app.bot.set_my_commands(commands)
    me = await app.bot.get_me()
    log.info("Bot @%s wystartowal. Whitelist: %s",
             me.username, sorted(config.ALLOWED_USER_IDS) or "PUSTA (odrzuca wszystkich)")


def build_app() -> Application:
    problems = config.validate()
    if problems:
        print(f"[bot] Missing env vars: {problems}", file=sys.stderr)
        if "TELEGRAM_BOT_TOKEN" in problems:
            sys.exit(1)

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    # Diagnostic (bez whitelist)
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler(["start", "help"], guarded(cmd_start)))

    # Plan
    app.add_handler(CommandHandler("today", guarded(plan.cmd_today)))
    app.add_handler(CommandHandler("tomorrow", guarded(plan.cmd_tomorrow)))
    app.add_handler(CommandHandler("week", guarded(plan.cmd_week)))
    app.add_handler(CommandHandler("schedule_week", guarded(plan.cmd_schedule_week)))

    # Historia
    app.add_handler(CommandHandler("lastrun", guarded(history.cmd_lastrun)))
    app.add_handler(CommandHandler("lastgym", guarded(history.cmd_lastgym)))

    # Rozkminy
    app.add_handler(CommandHandler("n", guarded(life.cmd_note)))
    app.add_handler(CommandHandler("tasks", guarded(life.cmd_tasks)))
    app.add_handler(CommandHandler("done", guarded(life.cmd_task_done)))
    app.add_handler(CommandHandler("goals", guarded(life.cmd_goals)))
    app.add_handler(CommandHandler("goal", guarded(life.cmd_set_goal)))

    # Cialo
    app.add_handler(CommandHandler("log", guarded(body.cmd_log)))

    # Fallback dla nieznanych komend (tylko whitelist)
    app.add_handler(MessageHandler(filters.COMMAND, guarded(cmd_help)))

    return app


def main():
    app = build_app()
    log.info("Startuje polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
