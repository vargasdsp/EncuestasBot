"""
Telegram notification helpers.
Handles sending text messages and PDF documents with proper caption length limits.
"""
import io
import logging
import re
from typing import Optional

import requests
from telegram import Bot
from telegram.constants import ParseMode

from scrapers.base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

TELEGRAM_CAPTION_LIMIT = 1024


def _build_message(entrega: Entrega) -> str:
    lines = [f"🚨 NUEVA ENTREGA: {entrega.fuente}"]
    if entrega.fecha:
        lines.append(f"🗓 {entrega.fecha}")
    if entrega.resumen:
        # Keep resumen short for Telegram
        resumen = entrega.resumen[:200]
        if len(entrega.resumen) > 200:
            resumen += "…"
        lines.append(resumen)
    lines.append(f"🔗 {entrega.link}")
    return "\n".join(lines)


async def send_entrega(bot: Bot, chat_id: str, entrega: Entrega) -> None:
    message_text = _build_message(entrega)

    if entrega.pdf_url:
        pdf_bytes = _download_pdf(entrega.pdf_url)
        if pdf_bytes:
            await _send_with_pdf(bot, chat_id, message_text, pdf_bytes, entrega)
            return

    # No PDF available – send text only
    await bot.send_message(
        chat_id=chat_id,
        text=message_text,
        disable_web_page_preview=False,
    )
    log.info("Sent text notification for %s", entrega.fuente)


async def send_manual_descifra(bot: Bot, chat_id: str, pdf_bytes: bytes, fecha: Optional[str] = None) -> None:
    """Send a manually provided Descifra PDF to the community."""
    from scrapers.base import Entrega
    entrega = Entrega(
        fuente="ENCUESTA DESCIFRA",
        titulo="Encuesta Descifra",
        fecha=fecha,
        resumen=None,
        link="",
        pdf_url=None,
        id_unico="manual",
    )
    message_text = _build_message(entrega)
    await _send_with_pdf(bot, chat_id, message_text, pdf_bytes, entrega)


async def _send_with_pdf(bot: Bot, chat_id: str, message_text: str, pdf_bytes: bytes, entrega: Entrega) -> None:
    filename = re.sub(r"\W+", "_", entrega.fuente.lower()).strip("_") + ".pdf"

    if len(message_text) <= TELEGRAM_CAPTION_LIMIT:
        await bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(pdf_bytes),
            filename=filename,
            caption=message_text,
        )
    else:
        # Caption too long: send text first, then PDF without caption
        await bot.send_message(chat_id=chat_id, text=message_text, disable_web_page_preview=False)
        await bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(pdf_bytes),
            filename=filename,
        )
    log.info("Sent PDF notification for %s", entrega.fuente)


def _download_pdf(url: str) -> Optional[bytes]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and not url.endswith(".pdf"):
            log.warning("URL %s does not look like a PDF (Content-Type: %s)", url, content_type)
        data = resp.content
        if len(data) < 1000:
            log.warning("PDF from %s seems too small (%d bytes), skipping", url, len(data))
            return None
        return data
    except Exception as exc:
        log.warning("Could not download PDF from %s: %s", url, exc)
        return None
