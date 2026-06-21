"""
Scraper for CADEM – Plaza Pública
URL: https://cadem.cl/contenido/plaza-publica/
Frequency: weekly
"""
import argparse
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

URL = "https://cadem.cl/contenido/plaza-publica/"

_DATE_RE = re.compile(
    r"\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?\d{4}",
    re.IGNORECASE,
)


def _extract_date_from_page(page_url: str) -> str | None:
    """Visit the article page and extract the publication date."""
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    # Try <time> tag first
    time_tag = soup.find("time")
    if time_tag:
        dt = time_tag.get("datetime", "") or time_tag.get_text(strip=True)
        m = re.search(r"\d{4}-\d{2}-\d{2}", dt)
        if m:
            return m.group(0)  # ISO format; telegram_notify will render it in Spanish
        m = _DATE_RE.search(dt)
        if m:
            return m.group(0)

    # Try any element with date/fecha class
    for tag in soup.find_all(["span", "div", "p"], class_=re.compile(r"date|fecha|published|entry-date")):
        text = tag.get_text(strip=True)
        m = _DATE_RE.search(text)
        if m:
            return m.group(0)

    # Scan meta tags
    for meta in soup.find_all("meta", {"property": re.compile(r"article:published|pubdate")}):
        content = meta.get("content", "")
        m = re.search(r"\d{4}-\d{2}-\d{2}", content)
        if m:
            return m.group(0)

    return None


def check() -> Entrega | None:
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("CADEM – error fetching %s: %s", URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    entry = None
    for candidate in soup.find_all(["article", "div"], recursive=True):
        classes = " ".join(candidate.get("class", []))
        if "post" in classes or "entry" in classes or "card" in classes:
            entry = candidate
            break

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

    heading_tag = entry.find(re.compile(r"^h[1-6]$"))
    titulo = heading_tag.get_text(strip=True) if heading_tag else "Plaza Pública CADEM"

    # Try date from listing first
    fecha = None
    m = _DATE_RE.search(titulo)
    if m:
        fecha = m.group(0)
    else:
        date_tag = entry.find(["time", "span"], class_=re.compile(r"date|fecha|time"))
        if date_tag:
            fecha = date_tag.get("datetime") or date_tag.get_text(strip=True)

    # Links
    link = URL
    pdf_url = None
    for a in entry.find_all("a", href=True):
        text = a.get_text(strip=True).upper()
        href = a["href"]
        if not href.startswith("http"):
            href = "https://cadem.cl" + href
        if "VER" in text and "ESTUDIO" in text:
            link = href
        elif "PDF" in text or "DESCARGAR" in text:
            pdf_url = href

    # If no date yet, visit the article page to find it
    if not fecha and link != URL:
        fecha = _extract_date_from_page(link)

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
