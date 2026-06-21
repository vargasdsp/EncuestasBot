"""
Scraper for Panel Ciudadano – UDD
URL: https://panelciudadano.cl/estudios-publicados/ and category pages
robots.txt restricts automated bots – we use an honest User-Agent and throttle carefully.
"""
import argparse
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

CATEGORY_URLS = [
    "https://panelciudadano.cl/estudios-publicados/",
    "https://panelciudadano.cl/category/elecciones/",
    "https://panelciudadano.cl/category/gobierno/",
    "https://panelciudadano.cl/category/informacion/",
]

_SURVEY_KEYWORDS = re.compile(
    r"panel\s+ciudadano|encuesta|estudio|sondeo|\d+\s*%", re.IGNORECASE
)
_PERCENTAGE = re.compile(r"\d+\s*%")


def _is_survey_post(title: str, excerpt: str) -> bool:
    combined = f"{title} {excerpt}"
    has_panel = re.search(r"panel\s+ciudadano", combined, re.IGNORECASE)
    has_data = _PERCENTAGE.search(combined) or re.search(
        r"\bencuesta\b|\bestudio\b|\bsondeo\b", combined, re.IGNORECASE
    )
    return bool(has_panel and has_data)


def check() -> Entrega | None:
    best: Entrega | None = None

    for url in CATEGORY_URLS:
        entry = _check_url(url)
        if entry:
            # Return the first valid entry found (pages listed most-recent-first)
            if best is None:
                best = entry
        time.sleep(2)  # be polite between category pages

    return best


def _check_url(url: str) -> Entrega | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("PANEL CIUDADANO – error fetching %s: %s", url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for article in soup.find_all(["article", "div"], class_=re.compile(r"post|entry|card")):
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)

        excerpt_tag = article.find(["p", "div"], class_=re.compile(r"excerpt|summary|content"))
        excerpt = excerpt_tag.get_text(strip=True) if excerpt_tag else ""

        if not _is_survey_post(titulo, excerpt):
            continue

        # Find link
        link_tag = heading.find("a") or article.find("a", href=True)
        if not link_tag:
            continue
        post_url = link_tag["href"]
        if not post_url.startswith("http"):
            post_url = "https://panelciudadano.cl" + post_url

        # Extract slug as id_unico
        slug = post_url.rstrip("/").split("/")[-1]

        # Date
        fecha = None
        time_tag = article.find("time")
        if time_tag:
            fecha = time_tag.get("datetime", time_tag.get_text(strip=True))

        # PDF: look for download link within article
        pdf_url = None
        for a in article.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if href.endswith(".pdf") or "pdf" in text or "informe" in text or "ver informe" in text:
                pdf_url = href
                break

        resumen = excerpt[:300] if excerpt else None

        return Entrega(
            fuente="PANEL CIUDADANO – UDD",
            titulo=titulo,
            fecha=fecha,
            resumen=resumen,
            link=post_url,
            pdf_url=pdf_url,
            id_unico=slug,
        )

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
