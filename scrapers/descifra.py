"""
Scraper for Encuesta Descifra – automatic mechanism via La Tercera
URL: https://www.latercera.com/ (search for notes containing "Descifra")
NOTE: La Tercera is a paywall site. We only collect the headline and link –
      we NEVER attempt to bypass the paywall.
Frequency: irregular
"""
import argparse
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import Entrega, HEADERS, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

# La Tercera search URL for "Descifra encuesta"
SEARCH_URL = "https://www.latercera.com/?s=encuesta+descifra"
# Also try the politics section
POLITICA_URL = "https://www.latercera.com/politica/"

_DESCIFRA_PATTERN = re.compile(r"descifra", re.IGNORECASE)


def _scan_page(url: str) -> Entrega | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("DESCIFRA – error fetching %s: %s", url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for article in soup.find_all(["article", "div", "li"], recursive=True):
        heading = article.find(re.compile(r"^h[1-6]$"))
        if not heading:
            continue
        titulo = heading.get_text(strip=True)
        if not _DESCIFRA_PATTERN.search(titulo):
            continue

        link_tag = heading.find("a") or article.find("a", href=True)
        if not link_tag:
            continue
        article_url = link_tag["href"]
        if not article_url.startswith("http"):
            article_url = "https://www.latercera.com" + article_url

        # Date
        fecha = None
        time_tag = article.find("time")
        if time_tag:
            fecha = time_tag.get("datetime", time_tag.get_text(strip=True))

        # Excerpt / bajada (only what's freely visible)
        excerpt_tag = article.find(["p", "div"], class_=re.compile(r"excerpt|summary|bajada|lead"))
        resumen = excerpt_tag.get_text(strip=True)[:300] if excerpt_tag else None

        slug = article_url.rstrip("/").split("/")[-1] or re.sub(r"\W+", "-", titulo.lower())[:80]

        return Entrega(
            fuente="ENCUESTA DESCIFRA (vía La Tercera)",
            titulo=titulo,
            fecha=fecha,
            resumen=resumen,
            link=article_url,
            pdf_url=None,  # never available via La Tercera
            id_unico=slug,
        )

    return None


def check() -> Entrega | None:
    result = _scan_page(SEARCH_URL)
    if result is None:
        result = _scan_page(POLITICA_URL)
    return result


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
