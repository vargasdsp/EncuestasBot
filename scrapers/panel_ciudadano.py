"""
Scraper for Panel Ciudadano – UDD
URLs: estudios-publicados + category pages
robots.txt restricts bots – we use an honest User-Agent and throttle carefully.
"""
import argparse
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import Entrega, BOT_HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

CATEGORY_URLS = [
    "https://panelciudadano.cl/estudios-publicados/",
    "https://panelciudadano.cl/category/elecciones/",
    "https://panelciudadano.cl/category/gobierno/",
    "https://panelciudadano.cl/category/informacion/",
]

_PANEL_RE = re.compile(r"panel\s+ciudadano", re.IGNORECASE)
_SURVEY_RE = re.compile(r"\d+\s*%|\bencuesta\b|\bestudio\b|\bsondeo\b", re.IGNORECASE)


def _is_survey_post(title: str, excerpt: str) -> bool:
    combined = f"{title} {excerpt}"
    return bool(_PANEL_RE.search(combined) and _SURVEY_RE.search(combined))


def check() -> Entrega | None:
    for url in CATEGORY_URLS:
        entry = _check_url(url)
        if entry:
            return entry
        time.sleep(2)
    return None


def _check_url(url: str) -> Entrega | None:
    try:
        resp = requests.get(url, headers=BOT_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("PANEL CIUDADANO – error fetching %s: %s", url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try structured article/post elements first
    candidates = soup.find_all(["article", "div"], class_=re.compile(r"post|entry|card|item"))
    if not candidates:
        # Fallback: all articles
        candidates = soup.find_all("article")

    log.debug("PANEL CIUDADANO – found %d candidate elements on %s", len(candidates), url)

    for article in candidates:
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)

        excerpt_tag = article.find(["p", "div"], class_=re.compile(r"excerpt|summary|content|entry"))
        excerpt = excerpt_tag.get_text(strip=True) if excerpt_tag else ""

        if not _is_survey_post(titulo, excerpt):
            continue

        link_tag = heading.find("a") or article.find("a", href=True)
        if not link_tag:
            continue
        post_url = link_tag["href"]
        if not post_url.startswith("http"):
            post_url = "https://panelciudadano.cl" + post_url

        slug = post_url.rstrip("/").split("/")[-1]

        fecha = None
        time_tag = article.find("time")
        if time_tag:
            fecha = time_tag.get("datetime", time_tag.get_text(strip=True))

        pdf_url = None
        for a in article.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if href.endswith(".pdf") or "pdf" in text or "informe" in text:
                pdf_url = href
                break

        resumen = excerpt[:300] if excerpt else None

        log.info("PANEL CIUDADANO – found entry: %s", titulo)
        return Entrega(
            fuente="PANEL CIUDADANO – UDD",
            titulo=titulo,
            fecha=fecha,
            resumen=resumen,
            link=post_url,
            pdf_url=pdf_url,
            id_unico=slug,
        )

    # If nothing matched the filter, return the first post found (false-positive allowed)
    # with a clear log so we can tune the filter later
    for article in candidates:
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)
        link_tag = heading.find("a") or article.find("a", href=True)
        if not link_tag:
            continue
        log.debug("PANEL CIUDADANO – skipped (filter): %s", titulo)

    log.warning("PANEL CIUDADANO – no matching post found on %s", url)
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
