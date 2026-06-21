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

_DATE_RE = re.compile(
    r"\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?\d{4}",
    re.IGNORECASE,
)


def _scrape_study_page(page_url: str) -> tuple[str | None, str | None]:
    """Return (pdf_url, fecha) from the individual study page."""
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("PULSO CIUDADANO – error fetching study page %s: %s", page_url, exc)
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")

    # --- Date ---
    fecha = None
    time_tag = soup.find("time")
    if time_tag:
        fecha = time_tag.get("datetime") or time_tag.get_text(strip=True)
    if not fecha:
        for tag in soup.find_all(["span", "div", "p"], class_=re.compile(r"date|fecha|published")):
            m = _DATE_RE.search(tag.get_text(strip=True))
            if m:
                fecha = m.group(0)
                break
    if not fecha:
        for meta in soup.find_all("meta", {"property": re.compile(r"article:published")}):
            m = re.search(r"\d{4}-\d{2}-\d{2}", meta.get("content", ""))
            if m:
                fecha = m.group(0)
                break

    # --- PDF: "Descargar" button ---
    pdf_url = None
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"]
        if not href.startswith("http"):
            href = "https://chile.activasite.com" + href
        if "descargar" in text or "download" in text:
            try:
                r = requests.get(
                    href, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                    allow_redirects=True, stream=True,
                )
                pdf_url = r.url
            except Exception:
                pdf_url = href
            break

    # Fallback: any .pdf link
    if not pdf_url:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://chile.activasite.com" + href
            if href.endswith(".pdf") or "pdf" in href.lower():
                pdf_url = href
                break

    if not pdf_url:
        log.warning("PULSO CIUDADANO – no Descargar/PDF link found in %s", page_url)

    return pdf_url, fecha


def check() -> Entrega | None:
    try:
        resp = requests.get(INDEX_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.error("PULSO CIUDADANO – error fetching %s: %s", INDEX_URL, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for article in soup.find_all(["article", "div", "li"], recursive=True):
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)
        if not re.search(r"Pulso\s+Ciudadano", titulo, re.IGNORECASE):
            continue

        # Find "Ver Noticia" link specifically
        study_url = None
        for a in article.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            href = a["href"]
            if not href.startswith("http"):
                href = "https://chile.activasite.com" + href
            if "ver" in text and ("noticia" in text or "estudio" in text or "informe" in text):
                study_url = href
                break

        # Fallback: heading link
        if not study_url:
            link_tag = heading.find("a") or article.find("a", href=True)
            if link_tag:
                href = link_tag["href"]
                study_url = href if href.startswith("http") else "https://chile.activasite.com" + href

        if not study_url:
            continue

        slug = study_url.rstrip("/").split("/")[-1] or re.sub(r"\W+", "-", titulo.lower())[:80]

        # Try date from index card first
        fecha = None
        m = _DATE_RE.search(titulo)
        if m:
            fecha = m.group(0)
        else:
            time_tag = article.find("time")
            if time_tag:
                fecha = time_tag.get("datetime") or time_tag.get_text(strip=True)

        # Visit study page → PDF + better date
        pdf_url, fecha_page = _scrape_study_page(study_url)
        if fecha_page and not fecha:
            fecha = fecha_page

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
