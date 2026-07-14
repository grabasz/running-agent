"""Body handlers — /log body_state (kolano/lydka/plecy/...)."""
from __future__ import annotations
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import turso as t  # type: ignore


# Popularne lokalizacje z body_state — mapowanie skrotow user-friendly
LOCATION_ALIASES = {
    "kolano": "kolano_prawe",   # domyslnie prawe (aktywna kontuzja)
    "kolano_p": "kolano_prawe",
    "kolano_l": "kolano_lewe",
    "lydka": "lydka_prawa",
    "lydka_p": "lydka_prawa",
    "lydka_l": "lydka_lewa",
    "krzyz": "krzyz",
    "plecy": "plecy",
    "posladki": "posladki",
    "achilles": "achilles_prawe",
    "achilles_p": "achilles_prawe",
    "achilles_l": "achilles_lewe",
    "czworka": "czworka_prawa",
    "biodro": "biodro_prawe",
    "it_band": "it_band_prawy",
}


async def cmd_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /log <miejsce> <0-10> [notatka]
    /log <miejsce> doms [notatka]

    Przyklady:
      /log kolano 2 klika przy schodach
      /log lydka doms po longu
      /log krzyz 0 all good rano
    """
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "Uzycie: /log &lt;miejsce&gt; &lt;0-10|doms&gt; [notatka]\n\n"
            "Przyklady:\n"
            "• /log kolano 2 klika przy schodach\n"
            "• /log lydka doms po longu\n"
            "• /log krzyz 0 all good\n\n"
            "Skroty: kolano (=kolano_prawe), kolano_l, lydka, lydka_l, "
            "krzyz, plecy, posladki, achilles, czworka, biodro, it_band",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_loc = ctx.args[0].lower()
    loc = LOCATION_ALIASES.get(raw_loc, raw_loc)  # user moze podac pelna nazwe
    val = ctx.args[1].lower()

    pain = None
    doms = False
    if val == "doms":
        doms = True
    elif val.isdigit():
        pain = int(val)
        if not 0 <= pain <= 10:
            await update.message.reply_text("Pain skala 0-10.")
            return
    else:
        await update.message.reply_text(
            f"Nieznana wartosc: <b>{escape(val)}</b>. Uzyj 0-10 albo 'doms'.",
            parse_mode=ParseMode.HTML,
        )
        return

    notes = " ".join(ctx.args[2:]).strip() or None

    with t.TursoDB() as db:
        t.log_body(db, location=loc, pain_0_10=pain, doms=doms, notes=notes)

    parts = [f"📝 body_state / {escape(loc)}"]
    if pain is not None:
        parts.append(f"pain <b>{pain}/10</b>")
    if doms:
        parts.append("DOMS 🔥")
    if notes:
        parts.append(f"<i>{escape(notes)}</i>")
    await update.message.reply_text(" · ".join(parts), parse_mode=ParseMode.HTML)
