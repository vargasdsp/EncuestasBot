"""
Scraper for CADEM – Plaza Pública
URL: https://cadem.cl/contenido/plaza-publica/
Frequency: weekly
"""
import argparse
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

URL = "https://cadem.cl/contenido/plaza-publica/"


def check() -> Entrega | None:
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("CADEM – error fetching %s: %s", URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Each entry is usually an <article> or a div with class containing "post"
    # Find all entries and take the first (most recent)
    entry = None
    for candidate in soup.find_all(["article", "div"], recursive=True):
        classes = " ".join(candidate.get("class", []))
        if "post" in classes or "entry" in classes or "card" in classes:
            entry = candidate
            break

    # Fallback: look for a heading that matches the plaza pública pattern
    if entry is None:
        heading = soup.find(
            lambda tag: tag.name in ("h1", "h2", "h3", "h4")
            and re.search(r"Plaza\s+P[uú]blica", tag.get_text(), re.IGNORECASE)
        )
        if heading:
            entry = heading.find_parent(["article", "div", "section"]) or heading

    if entry is None:
        log.error("CADEM – could not locate any entry on the page")
        return None

    # Extract title
    heading_tag = entry.find(re.compile(r"^h[1-6]$"))
    titulo = heading_tag.get_text(strip=True) if heading_tag else "Plaza Pública CADEM"

    # Extract date from title or a date element
    fecha = None
    date_match = re.search(
        r"\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?\d{4}",
        titulo,
        re.IGNORECASE,
    )
    if date_match:
        fecha = date_match.group(0)
    else:
        date_tag = entry.find(["time", "span"], class_=re.compile(r"date|fecha|time"))
        if date_tag:
            fecha = date_tag.get_text(strip=True)

    # Extract links – look for "VER ESTUDIO" and "DESCARGAR PDF"
    link = URL
    pdf_url = None
    for a in entry.find_all("a", href=True):
        text = a.get_text(strip=True).upper()
        href = a["href"]
        if "VER" in text and "ESTUDIO" in text:
            link = href if href.startswith("http") else "https://cadem.cl" + href
        elif "PDF" in text or "DESCARGAR" in text:
            pdf_url = href if href.startswith("http") else "https://cadem.cl" + href

    # id_unico: prefer pdf_url, fallback to fecha, fallback to link
    id_unico = pdf_url or fecha or link

    return Entrega(
        fuente="CADEM – PLAZA PÚBLICA",
        titulo=titulo,
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
