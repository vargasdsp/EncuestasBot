"""
Scraper for Pulso Ciudadano – Activa Research
URL: https://chile.activasite.com/pulso-ciudadano/
Frequency: 1-2 times per month

Structure:
  Index page → entry card → "Ver Noticia" button → study page → "Descargar" button → PDF
"""
import argparse
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

INDEX_URL = "https://chile.activasite.com/pulso-ciudadano/"


def _find_pdf_in_study_page(page_url: str) -> str | None:
    """Visit the study page and find the Descargar button."""
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("PULSO CIUDADANO – error fetching study page %s: %s", page_url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for "Descargar" link first
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"]
        if not href.startswith("http"):
            href = "https://chile.activasite.com" + href
        if "descargar" in text or "download" in text:
            # Follow redirect to get actual PDF URL
            try:
                r = requests.get(
                    href, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                    allow_redirects=True, stream=True,
                )
                return r.url
            except Exception:
                return href

    # Fallback: any direct .pdf link
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = "https://chile.activasite.com" + href
        if href.endswith(".pdf") or "pdf" in href.lower():
            return href

    log.warning("PULSO CIUDADANO – no Descargar/PDF link found in %s", page_url)
    return None


def check() -> Entrega | None:
    try:
        resp = requests.get(INDEX_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("PULSO CIUDADANO – error fetching %s: %s", INDEX_URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find cards/articles that mention "Pulso Ciudadano"
    for article in soup.find_all(["article", "div", "li"], recursive=True):
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)
        if not re.search(r"Pulso\s+Ciudadano", titulo, re.IGNORECASE):
            continue

        # Find the "Ver Noticia" link specifically
        study_url = None
        for a in article.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            href = a["href"]
            if not href.startswith("http"):
                href = "https://chile.activasite.com" + href
            if "ver" in text and ("noticia" in text or "estudio" in text or "informe" in text):
                study_url = href
                break

        # Fallback: use the heading link
        if not study_url:
            link_tag = heading.find("a") or article.find("a", href=True)
            if link_tag:
                href = link_tag["href"]
                study_url = href if href.startswith("http") else "https://chile.activasite.com" + href

        if not study_url:
            continue

        slug = study_url.rstrip("/").split("/")[-1] or re.sub(r"\W+", "-", titulo.lower())[:80]

        # Date
        fecha = None
        date_match = re.search(
            r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|octubre|noviembre|diciembre)\s+\d{4}",
            titulo,
            re.IGNORECASE,
        )
        if date_match:
            fecha = date_match.group(0)
        else:
            time_tag = article.find("time")
            if time_tag:
                fecha = time_tag.get("datetime", time_tag.get_text(strip=True))

        # Visit the study page and find the Descargar button → PDF
        pdf_url = _find_pdf_in_study_page(study_url)

        return Entrega(
            fuente="PULSO CIUDADANO – ACTIVA RESEARCH",
            titulo=titulo,
            fecha=fecha,
            resumen=None,
            link=study_url,
            pdf_url=pdf_url,
            id_unico=slug,
        )

    log.error("PULSO CIUDADANO – no matching entry found on %s", INDEX_URL)
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
