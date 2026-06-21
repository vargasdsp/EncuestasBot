"""
Scraper for Panel Ciudadano – UDD
Checks the home page and several category pages.
Posts live at panelciudadano.cl/<slug> (top-level), not just under categories.
robots.txt restricts bots – honest User-Agent, no parallel requests.
"""
import argparse
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import Entrega, BOT_HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

URLS_TO_CHECK = [
    "https://panelciudadano.cl/",                          # home — shows latest posts
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


def _find_pdf_in_post(post_url: str) -> str | None:
    """Visit the individual post and look for a PDF download link."""
    try:
        resp = requests.get(post_url, headers=BOT_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("PANEL CIUDADANO – error fetching post %s: %s", post_url, exc)
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if href.endswith(".pdf") or "pdf" in text or "descargar" in text or "informe" in text:
            return href if href.startswith("http") else "https://panelciudadano.cl" + href
    return None


def check() -> Entrega | None:
    for url in URLS_TO_CHECK:
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

    # Strategy 1: structured article/post containers
    candidates = (
        soup.find_all(["article", "div"], class_=re.compile(r"post|entry|card|item"))
        or soup.find_all("article")
    )

    # Strategy 2: if no containers found, look for any heading that links to a post
    if not candidates:
        for heading in soup.find_all(re.compile(r"^h[1-6]$")):
            a = heading.find("a", href=True)
            if not a:
                continue
            titulo = heading.get_text(strip=True)
            href = a["href"]
            if not href.startswith("http"):
                href = "https://panelciudadano.cl" + href
            # Only consider internal links
            if "panelciudadano.cl" not in href:
                continue
            if _is_survey_post(titulo, ""):
                slug = href.rstrip("/").split("/")[-1]
                fecha = _extract_date(None, href)
                pdf_url = _find_pdf_in_post(href)
                log.info("PANEL CIUDADANO – found via heading scan: %s", titulo)
                return Entrega(
                    fuente="PANEL CIUDADANO – UDD",
                    titulo=titulo,
                    fecha=fecha,
                    resumen=None,
                    link=href,
                    pdf_url=pdf_url,
                    id_unico=slug,
                )
        log.warning("PANEL CIUDADANO – no candidates found on %s", url)
        return None

    log.debug("PANEL CIUDADANO – %d candidate elements on %s", len(candidates), url)

    for article in candidates:
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)

        excerpt_tag = article.find(["p", "div"], class_=re.compile(r"excerpt|summary|content|entry"))
        excerpt = excerpt_tag.get_text(strip=True) if excerpt_tag else ""

        if not _is_survey_post(titulo, excerpt):
            log.debug("PANEL CIUDADANO – skipped (filter): %s", titulo)
            continue

        link_tag = heading.find("a") or article.find("a", href=True)
        if not link_tag:
            continue
        post_url = link_tag["href"]
        if not post_url.startswith("http"):
            post_url = "https://panelciudadano.cl" + post_url

        slug = post_url.rstrip("/").split("/")[-1]

        time_tag = article.find("time")
        fecha = _extract_date(time_tag, post_url)

        # Look for PDF in the article card first, then visit the post page
        pdf_url = None
        for a in article.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if href.endswith(".pdf") or "pdf" in text or "informe" in text:
                pdf_url = href
                break
        if not pdf_url:
            pdf_url = _find_pdf_in_post(post_url)

        log.info("PANEL CIUDADANO – found entry: %s", titulo)
        return Entrega(
            fuente="PANEL CIUDADANO – UDD",
            titulo=titulo,
            fecha=fecha,
            resumen=excerpt[:300] if excerpt else None,
            link=post_url,
            pdf_url=pdf_url,
            id_unico=slug,
        )

    log.warning("PANEL CIUDADANO – no matching post found on %s", url)
    return None


def _extract_date(time_tag, post_url: str) -> str | None:
    if time_tag:
        return time_tag.get("datetime") or time_tag.get_text(strip=True)
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
