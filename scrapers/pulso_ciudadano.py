"""
Scraper for Pulso Ciudadano – Activa Research
URL: https://chile.activasite.com/pulso-ciudadano/
Frequency: 1-2 times per month
"""
import argparse
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

INDEX_URL = "https://chile.activasite.com/pulso-ciudadano/"


def _find_pdf_in_page(page_url: str) -> str | None:
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("PULSO CIUDADANO – error fetching study page %s: %s", page_url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if (
            href.endswith(".pdf")
            or "pdf" in text
            or "descargar" in text
            or "informe" in text
            or "download" in text
        ):
            return href if href.startswith("http") else "https://chile.activasite.com" + href
    return None


def check() -> Entrega | None:
    try:
        resp = requests.get(INDEX_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("PULSO CIUDADANO – error fetching %s: %s", INDEX_URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find first entry mentioning "Pulso Ciudadano"
    for article in soup.find_all(["article", "div", "li"], recursive=True):
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)
        if not re.search(r"Pulso\s+Ciudadano", titulo, re.IGNORECASE):
            continue

        # Link to individual study page
        link_tag = heading.find("a") or article.find("a", href=True)
        if not link_tag:
            continue
        study_url = link_tag["href"]
        if not study_url.startswith("http"):
            study_url = "https://chile.activasite.com" + study_url

        # id_unico: slug from URL or normalized title
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

        # Excerpt
        excerpt_tag = article.find(["p"], class_=re.compile(r"excerpt|summary|description"))
        resumen = excerpt_tag.get_text(strip=True)[:300] if excerpt_tag else None

        # PDF from study page
        pdf_url = _find_pdf_in_page(study_url)

        return Entrega(
            fuente="PULSO CIUDADANO – ACTIVA RESEARCH",
            titulo=titulo,
            fecha=fecha,
            resumen=resumen,
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
