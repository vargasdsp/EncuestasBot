"""
Scraper for Criteria – Agenda Criteria
URL: https://www.criteria.cl/agenda-criteria/
Frequency: weekly/monthly
"""
import argparse
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

URL = "https://www.criteria.cl/agenda-criteria/"


def _resolve_redirect(url: str) -> str:
    """Follow redirects and return the final URL (used for short download links)."""
    try:
        resp = requests.head(
            url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
        return resp.url
    except Exception:
        try:
            resp = requests.get(
                url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True,
                stream=True,
            )
            return resp.url
        except Exception:
            return url


def check() -> Entrega | None:
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("CRITERIA – error fetching %s: %s", URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Entries are typically divs/articles containing "Agenda Criteria DD Mes AAAA"
    entry = None
    for tag in soup.find_all(["article", "div", "section", "li"]):
        text = tag.get_text(" ", strip=True)
        if re.search(r"Agenda\s+Criteria", text, re.IGNORECASE):
            # Make sure it's a leaf-ish container (not the whole page)
            if len(tag.find_all(["article", "div", "li"])) < 10:
                entry = tag
                break

    if entry is None:
        log.error("CRITERIA – could not locate any entry on the page")
        return None

    # Title
    heading = entry.find(re.compile(r"^h[1-6]$"))
    titulo = heading.get_text(strip=True) if heading else entry.get_text(" ", strip=True)[:100]

    # Date from title
    fecha = None
    date_match = re.search(
        r"\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?\d{4}",
        titulo,
        re.IGNORECASE,
    )
    if date_match:
        fecha = date_match.group(0)

    # Links
    link = URL
    pdf_url = None
    for a in entry.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"]
        if not href.startswith("http"):
            href = "https://www.criteria.cl" + href
        if "resumen" in text or "ver" in text:
            link = href
        elif "descargar" in text or "download" in text or "/r/" in href:
            # Resolve the short link to get the actual PDF URL
            pdf_url = _resolve_redirect(href)

    id_unico = fecha or link

    return Entrega(
        fuente="CRITERIA – AGENDA CRITERIA",
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
