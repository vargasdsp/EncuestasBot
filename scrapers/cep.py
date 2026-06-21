"""
Scraper for CEP – Encuesta Nacional de Opinión Pública
URL: https://www.cepchile.cl/opinion-publica/encuesta-cep/
Frequency: 3-4 times per year (months without new entries are normal)
"""
import argparse
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

INDEX_URL = "https://www.cepchile.cl/opinion-publica/encuesta-cep/"


def _find_pdf_in_page(page_url: str) -> str | None:
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("CEP – error fetching entry page %s: %s", page_url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if (
            "static.cepchile.cl" in href
            or href.endswith(".pdf")
            or "pdf" in text
            or "descargar" in text
            or "informe" in text
        ):
            return href if href.startswith("http") else "https://www.cepchile.cl" + href
    return None


def check() -> Entrega | None:
    try:
        resp = requests.get(INDEX_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("CEP – error fetching %s: %s", INDEX_URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for links/headings matching "Encuesta CEP N°XX" or "Encuesta CEP N.° XX"
    best_num = -1
    best_link = None
    best_titulo = None

    pattern = re.compile(r"Encuesta\s+CEP\s+N[°o\.]+\s*(\d+)", re.IGNORECASE)

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        m = pattern.search(text)
        if m:
            num = int(m.group(1))
            if num > best_num:
                best_num = num
                best_link = a["href"]
                best_titulo = text

    # Also scan headings
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        text = tag.get_text(" ", strip=True)
        m = pattern.search(text)
        if m:
            num = int(m.group(1))
            if num > best_num:
                best_num = num
                best_titulo = text
                parent_a = tag.find_parent("a") or tag.find("a")
                best_link = parent_a["href"] if parent_a and parent_a.get("href") else INDEX_URL

    if best_num < 0:
        log.error("CEP – could not find any encuesta number on the page")
        return None

    if best_link and not best_link.startswith("http"):
        best_link = "https://www.cepchile.cl" + best_link

    link = best_link or INDEX_URL
    pdf_url = _find_pdf_in_page(link) if link != INDEX_URL else None

    # Try to extract date from titulo or page
    fecha = None
    if best_titulo:
        date_match = re.search(
            r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|octubre|noviembre|diciembre)\s+(?:–|-|—)?\s*\d{4}",
            best_titulo,
            re.IGNORECASE,
        )
        if date_match:
            fecha = date_match.group(0)

    id_unico = f"cep-n{best_num}"

    return Entrega(
        fuente="CEP – ENCUESTA NACIONAL DE OPINIÓN PÚBLICA",
        titulo=best_titulo or f"Encuesta CEP N°{best_num}",
        fecha=fecha,
        resumen=None,
        link=link,
        pdf_url=pdf_url,
        id_unico=id_unico,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    result = check()
    if result:
        print(result)
    else:
        print("No entry found.")
