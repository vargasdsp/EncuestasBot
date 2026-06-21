from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entrega:
    fuente: str
    titulo: str
    fecha: Optional[str]
    resumen: Optional[str]
    link: str
    pdf_url: Optional[str]
    id_unico: str


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# Honest bot UA for sites that explicitly allow bots (e.g. panelciudadano)
BOT_HEADERS = {
    "User-Agent": (
        "EncuestasChileBot/1.0 (monitor de encuestas publicas chilenas; "
        "contacto: nicolas.vargas@renca.cl)"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
}

REQUEST_TIMEOUT = 15
