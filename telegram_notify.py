"""
Telegram notification helpers.
Handles sending text messages and PDF documents with proper caption length limits.
"""
import io
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests
from telegram import Bot

from scrapers.base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

TELEGRAM_CAPTION_LIMIT = 1024

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

MESES_NUM = {v: k for k, v in MESES_ES.items()}


def _now_es() -> str:
    """Current UTC time as a Spanish string."""
    now = datetime.now(timezone.utc)
    return f"{now.day} de {MESES_ES[now.month]} de {now.year}, {now.strftime('%H:%M')}h UTC"


def _fecha_to_iso(fecha: str) -> str | None:
    """Try to convert a Spanish date string like '21 de junio de 2026' to '2026.06.21'."""
    if not fecha:
        return None
    # Try ISO format first (e.g. from <time datetime="2026-06-21">)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", fecha)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    # Spanish: "21 de junio de 2026" or "21 junio 2026"
    m = re.search(
        r"(\d{1,2})\s+(?:de\s+)?("
        + "|".join(MESES_NUM.keys())
        + r")\s+(?:de\s+)?(\d{4})",
        fecha, re.IGNORECASE,
    )
    if m:
        day = int(m.group(1))
        month = MESES_NUM[m.group(2).lower()]
        year = int(m.group(3))
        return f"{year}.{month:02d}.{day:02d}"
    # "junio 2026" (no day)
    m = re.search(
        r"(" + "|".join(MESES_NUM.keys()) + r")\s+(\d{4})",
        fecha, re.IGNORECASE,
    )
    if m:
        month = MESES_NUM[m.group(1).lower()]
        year = int(m.group(2))
        return f"{year}.{month:02d}"
    return None


def _pdf_filename(entrega: Entrega) -> str:
    """Build a clean filename: Fuente_YYYY.MM.DD.pdf"""
    fuente_slug = re.sub(r"\s+", "_", entrega.fuente.split("–")[-1].strip())
    fuente_slug = re.sub(r"[^\w]", "_", fuente_slug).strip("_")
    iso = _fecha_to_iso(entrega.fecha or "")
    if iso:
        return f"{fuente_slug}_{iso}.pdf"
    # Fallback: use today's date
    today = datetime.now(timezone.utc)
    return f"{fuente_slug}_{today.year}.{today.month:02d}.{today.day:02d}.pdf"


def _build_message(entrega: Entrega) -> str:
    lines = [f"🚨 NUEVA ENTREGA: {entrega.fuente}"]
    if entrega.titulo:
        lines.append(f"📰 {entrega.titulo}")
    if entrega.fecha:
        lines.append(f"🗓 Publicación: {entrega.fecha}")
    if entrega.resumen:
        resumen = entrega.resumen[:200]
        if len(entrega.resumen) > 200:
            resumen += "…"
        lines.append(resumen)
    lines.append(f"🔗 {entrega.link}")
    lines.append(f"⏱ Detectado: {_now_es()}")
    return "\n".join(lines)


async def send_entrega(bot: Bot, chat_id: str, entrega: Entrega) -> None:
    message_text = _build_message(entrega)

    if entrega.pdf_url:
        pdf_bytes = _download_pdf(entrega.pdf_url)
        if pdf_bytes:
            await _send_with_pdf(bot, chat_id, message_text, pdf_bytes, entrega)
            return

    await bot.send_message(
        chat_id=chat_id,
        text=message_text,
        disable_web_page_preview=False,
    )
    log.info("Sent text notification for %s", entrega.fuente)


async def send_manual_descifra(bot: Bot, chat_id: str, pdf_bytes: bytes, fecha: Optional[str] = None) -> None:
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
    filename = _pdf_filename(entrega)

    if len(message_text) <= TELEGRAM_CAPTION_LIMIT:
        await bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(pdf_bytes),
            filename=filename,
            caption=message_text,
        )
    else:
        await bot.send_message(chat_id=chat_id, text=message_text, disable_web_page_preview=False)
        await bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(pdf_bytes),
            filename=filename,
        )
    log.info("Sent PDF notification for %s — file: %s", entrega.fuente, filename)


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
