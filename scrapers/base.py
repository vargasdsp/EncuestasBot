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
        "EncuestasChileBot/1.0 (monitor de encuestas publicas chilenas; "
        "contacto: nicolas.vargas@renca.cl)"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
}

REQUEST_TIMEOUT = 15
