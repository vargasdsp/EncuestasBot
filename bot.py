"""
Entrypoint: starts the Telegram bot + internal APScheduler for polling sources.
"""
import asyncio
import logging
import os
import time
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import scrapers.cadem as cadem
import scrapers.cep as cep
import scrapers.criteria as criteria
import scrapers.descifra as descifra
import scrapers.panel_ciudadano as panel_ciudadano
import scrapers.pulso_ciudadano as pulso_ciudadano
from scrapers.base import Entrega
from storage import Storage
from telegram_notify import send_entrega, send_manual_descifra

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (from environment variables)
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ADMIN_ID = int(os.environ["TELEGRAM_ADMIN_ID"])
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
DB_PATH = os.environ.get("DATABASE_PATH", "/data/state.db")
FAILURE_ALERT_THRESHOLD = 3

SCRAPERS = {
    "CADEM – PLAZA PÚBLICA": cadem.check,
    "CRITERIA – AGENDA CRITERIA": criteria.check,
    "CEP – ENCUESTA NACIONAL DE OPINIÓN PÚBLICA": cep.check,
    "PANEL CIUDADANO – UDD": panel_ciudadano.check,
    "PULSO CIUDADANO – ACTIVA RESEARCH": pulso_ciudadano.check,
    "ENCUESTA DESCIFRA (vía La Tercera)": descifra.check,
}

storage = Storage(DB_PATH)

# ---------------------------------------------------------------------------
# Core polling logic
# ---------------------------------------------------------------------------

async def run_check_cycle(app: Application) -> None:
    log.info("Starting check cycle…")
    for fuente, scraper_fn in SCRAPERS.items():
        try:
            entrega: Optional[Entrega] = scraper_fn()
        except Exception as exc:
            log.error("Scraper %s raised unhandled exception: %s", fuente, exc, exc_info=True)
            entrega = None

        if entrega is None:
            count = storage.record_failure(fuente)
            log.warning("Scraper %s returned no entry (consecutive failures: %d)", fuente, count)
            if count == FAILURE_ALERT_THRESHOLD:
                try:
                    await app.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=(
                            f"⚠️ El scraper de *{fuente}* lleva {count} fallos seguidos.\n"
                            "Probablemente el sitio cambió su estructura HTML."
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as alert_exc:
                    log.error("Could not send failure alert to admin: %s", alert_exc)
        else:
            storage.reset_failures(fuente)
            if storage.is_new(fuente, entrega.id_unico):
                if storage.get_last_seen(fuente) is None:
                    # First time ever seeing this source — seed without notifying
                    log.info("Seeding first entry for %s: %s (no notification)", fuente, entrega.id_unico)
                    storage.mark_notified(fuente, entrega.id_unico, entrega.titulo, entrega.link)
                    continue
                log.info("New entry detected for %s: %s", fuente, entrega.id_unico)
                try:
                    await send_entrega(app.bot, CHAT_ID, entrega)
                    storage.mark_notified(fuente, entrega.id_unico, entrega.titulo, entrega.link)
                except Exception as send_exc:
                    log.error("Failed to send notification for %s: %s", fuente, send_exc, exc_info=True)
            else:
                log.info("No new entry for %s (last seen: %s)", fuente, entrega.id_unico)

        # Brief pause between sources to avoid hammering sites
        time.sleep(3)

    log.info("Check cycle complete.")

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = storage.get_all_last_seen()
    if not rows:
        await update.message.reply_text("No hay entregas registradas todavía.")
        return

    lines = ["📊 *Estado actual del bot:*\n"]
    for row in rows:
        lines.append(
            f"• *{row['fuente']}*\n"
            f"  └ {row['titulo'] or 'Sin título'}\n"
            f"  └ Notificado: {row['notified_at'][:10]}\n"
            f"  └ {row['link'] or '(sin link)'}"
        )

    # Also show sources with no entry yet
    seen_fuentes = {r["fuente"] for r in rows}
    for fuente in SCRAPERS:
        if fuente not in seen_fuentes:
            lines.append(f"• *{fuente}*\n  └ _(sin entregas registradas aún)_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("No autorizado.")
        return
    await update.message.reply_text("⏳ Forzando revisión de todas las fuentes…")
    await run_check_cycle(context.application)
    await update.message.reply_text("✅ Ciclo de revisión completado.")


async def cmd_descifra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("No autorizado.")
        return

    # The PDF should be attached to the same message as the /descifra command (as caption),
    # or the previous message should be replied to.
    message = update.message
    doc = message.document

    if doc is None and message.reply_to_message:
        doc = message.reply_to_message.document

    if doc is None:
        await message.reply_text(
            "Adjunta el PDF al mensaje con el comando /descifra como caption, "
            "o responde a un mensaje con el PDF usando /descifra."
        )
        return

    if not doc.mime_type or "pdf" not in doc.mime_type.lower():
        await message.reply_text("El archivo adjunto no parece ser un PDF.")
        return

    await message.reply_text("⏳ Descargando PDF y publicando en la comunidad…")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await tg_file.download_as_bytearray()
        pdf_bytes = bytes(pdf_bytes)
    except Exception as exc:
        log.error("Could not download Descifra PDF from Telegram: %s", exc)
        await message.reply_text(f"❌ Error al descargar el PDF: {exc}")
        return

    try:
        await send_manual_descifra(context.bot, CHAT_ID, pdf_bytes)
    except Exception as exc:
        log.error("Could not publish manual Descifra PDF: %s", exc)
        await message.reply_text(f"❌ Error al publicar en la comunidad: {exc}")
        return

    # Record in storage so we don't double-notify if La Tercera picks it up later
    import hashlib
    digest = hashlib.md5(pdf_bytes[:4096]).hexdigest()[:12]
    storage.mark_notified("ENCUESTA DESCIFRA", f"manual-{digest}", "Descifra (manual)", "")
    await message.reply_text("✅ PDF publicado en la comunidad.")


async def handle_pdf_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a PDF sent directly (without /descifra caption) by the admin."""
    if update.effective_user.id != ADMIN_ID:
        return
    doc = update.message.document
    if doc and doc.mime_type and "pdf" in doc.mime_type.lower():
        caption = (update.message.caption or "").strip()
        if "/descifra" in caption:
            # Treat as /descifra command
            await cmd_descifra(update, context)
        # Otherwise ignore – don't auto-publish PDFs without explicit command


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_check_cycle,
        trigger="interval",
        minutes=CHECK_INTERVAL,
        args=[app],
        id="check_cycle",
        replace_existing=True,
    )
    return scheduler


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def post_init(app: Application) -> None:
    scheduler = setup_scheduler(app)
    scheduler.start()
    log.info("Scheduler started – checking every %d minutes.", CHECK_INTERVAL)
    # Run immediately on startup
    asyncio.create_task(run_check_cycle(app))


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("descifra", cmd_descifra))
    app.add_handler(
        MessageHandler(filters.Document.PDF & filters.ChatType.PRIVATE, handle_pdf_message)
    )

    log.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
