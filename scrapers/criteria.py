"""
Scraper for Criteria – Agenda Criteria
URL: https://www.criteria.cl/agenda-criteria/
Frequency: weekly/monthly

Structure:
  Index page → entry card with heading + "Descargar" button (href /r/XXXXX)
  The /r/ link is a short URL that redirects to the actual PDF.
  The heading itself may link to a dedicated entry page.
"""
import argparse
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

URL = "https://www.criteria.cl/agenda-criteria/"


def _resolve_to_pdf(url: str) -> str | None:
    """Follow redirects on a short link and return final URL if it looks like a PDF."""
    if not url.startswith("http"):
        url = "https://www.criteria.cl" + url
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
            allow_redirects=True, stream=True,
        )
        final = resp.url
        ct = resp.headers.get("Content-Type", "")
        if "pdf" in ct or final.endswith(".pdf") or "pdf" in final.lower():
            return final
        # Even if content-type is ambiguous, trust /r/ short links
        if "/r/" in url:
            return final
        return final  # return anyway; worst case the PDF download will fail gracefully
    except Exception as exc:
        log.warning("CRITERIA – could not resolve redirect %s: %s", url, exc)
        return None


def check() -> Entrega | None:
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("CRITERIA – error fetching %s: %s", URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Walk all tags looking for one whose text starts with "Agenda Criteria"
    # and which contains a "Descargar" link — that's an entry card.
    for tag in soup.find_all(True):
        text = tag.get_text(" ", strip=True)
        if not re.search(r"^Agenda\s+Criteria", text, re.IGNORECASE):
            continue
        # Avoid the outermost wrappers (whole page, section) — look for a compact card
        child_blocks = tag.find_all(["article", "div", "section", "li"])
        if len(child_blocks) > 15:
            continue

        # Check there's a Descargar link inside
        download_a = None
        for a in tag.find_all("a", href=True):
            t = a.get_text(strip=True).lower()
            h = a["href"]
            if "descargar" in t or "download" in t or "/r/" in h:
                download_a = a
                break

        if download_a is None:
            continue

        # We found the entry card
        heading = tag.find(re.compile(r"^h[1-6]$"))
        titulo = heading.get_text(strip=True) if heading else text[:120]

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

        # Entry page link (heading link or "Resumen" link)
        link = URL
        for a in tag.find_all("a", href=True):
            t = a.get_text(strip=True).lower()
            h = a["href"]
            if not h.startswith("http"):
                h = "https://www.criteria.cl" + h
            if "resumen" in t or ("ver" in t and "descargar" not in t):
                link = h
                break
            # Heading itself might be a link
            if heading and a == heading.find("a"):
                link = h

        # Resolve the Descargar short link → PDF
        pdf_url = _resolve_to_pdf(download_a["href"])

        id_unico = fecha or link

        return Entrega(
            fuente="CRITERIA – AGENDA CRITERIA",
            titulo=titulo,
            fecha=fecha,
            resumen=None,
            link=link if link != URL else URL,
            pdf_url=pdf_url,
            id_unico=id_unico,
        )

    log.error("CRITERIA – could not locate any entry with a Descargar button on %s", URL)
    return None


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
