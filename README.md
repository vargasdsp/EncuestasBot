# EncuestasBot — Monitor de Encuestas Chile

Bot de Telegram que vigila 6 fuentes de encuestas de opinión pública chilenas y avisa automáticamente en una comunidad cuando se publica una entrega nueva, adjuntando el PDF cuando está disponible.

## Fuentes monitoreadas

| Fuente | URL |
|--------|-----|
| CADEM – Plaza Pública | https://cadem.cl/contenido/plaza-publica/ |
| Criteria – Agenda Criteria | https://www.criteria.cl/agenda-criteria/ |
| CEP – Encuesta Nacional | https://www.cepchile.cl/opinion-publica/encuesta-cep/ |
| Panel Ciudadano – UDD | https://panelciudadano.cl/ |
| Pulso Ciudadano – Activa Research | https://chile.activasite.com/pulso-ciudadano/ |
| Encuesta Descifra (vía La Tercera) | https://www.latercera.com/ |

---

## Estructura del proyecto

```
.
├── bot.py                  # entrypoint: bot Telegram + scheduler
├── scrapers/
│   ├── __init__.py
│   ├── base.py             # dataclass Entrega + constantes compartidas
│   ├── cadem.py
│   ├── criteria.py
│   ├── cep.py
│   ├── panel_ciudadano.py
│   ├── pulso_ciudadano.py
│   └── descifra.py
├── storage.py              # persistencia SQLite
├── telegram_notify.py      # envío de mensajes/documentos
├── requirements.txt
├── Procfile
├── railway.json
└── README.md
```

---

## Variables de entorno

| Variable | Descripción | Obligatoria |
|----------|-------------|-------------|
| `TELEGRAM_BOT_TOKEN` | Token del bot (de @BotFather) | Sí |
| `TELEGRAM_CHAT_ID` | ID del grupo/comunidad donde se publican los avisos | Sí |
| `TELEGRAM_ADMIN_ID` | Tu user ID de Telegram | Sí |
| `CHECK_INTERVAL_MINUTES` | Intervalo del scheduler (default: `60`) | No |
| `DATABASE_PATH` | Ruta del archivo SQLite (default: `/data/state.db`) | No |

---

## Comandos del bot

| Comando | Quién lo puede usar | Descripción |
|---------|---------------------|-------------|
| `/status` | Cualquiera | Muestra la última entrega conocida de cada fuente |
| `/check` | Solo admin | Fuerza una revisión inmediata de todas las fuentes |
| `/descifra` + PDF adjunto | Solo admin | Republica un PDF de Descifra en la comunidad |

---

## Setup local (para desarrollo y pruebas)

### 1. Requisitos previos

- Python 3.11+
- pip

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Crea un archivo `.env` o exporta las variables directamente:

```bash
export TELEGRAM_BOT_TOKEN="tu_token_aqui"
export TELEGRAM_CHAT_ID="-100xxxxxxxxxx"
export TELEGRAM_ADMIN_ID="tu_user_id"
export DATABASE_PATH="./state.db"   # ruta local para desarrollo
```

### 4. Probar scrapers individuales (dry-run, sin enviar nada a Telegram)

Cada scraper se puede ejecutar directamente:

```bash
python -m scrapers.cadem --dry-run
python -m scrapers.criteria --dry-run
python -m scrapers.cep --dry-run
python -m scrapers.panel_ciudadano --dry-run
python -m scrapers.pulso_ciudadano --dry-run
python -m scrapers.descifra --dry-run
```

Esto imprime en consola la `Entrega` encontrada (o "No entry found.") sin tocar Telegram ni la base de datos.

### 5. Correr el bot localmente

```bash
python bot.py
```

---

## Despliegue en Railway

### Paso 1 — Crear el bot en Telegram

1. Abre [@BotFather](https://t.me/BotFather) en Telegram.
2. Envía `/newbot` y sigue las instrucciones.
3. Guarda el **token** que te entrega BotFather (`TELEGRAM_BOT_TOKEN`).

### Paso 2 — Crear el grupo/comunidad de Telegram

1. Crea un grupo o canal en Telegram.
2. Agrega el bot como **administrador** del grupo (con permiso para enviar mensajes y archivos).

### Paso 3 — Obtener el `TELEGRAM_CHAT_ID`

Envía cualquier mensaje en el grupo y consulta:

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Busca el campo `"chat": {"id": -100xxxxxxxxxx}`. Ese es tu `TELEGRAM_CHAT_ID`. También puedes usar el bot [@getidsbot](https://t.me/getidsbot).

### Paso 4 — Obtener tu `TELEGRAM_ADMIN_ID`

Envíale un mensaje a [@userinfobot](https://t.me/userinfobot). Te responderá con tu user ID numérico.

### Paso 5 — Crear el proyecto en Railway

1. Ve a [Railway](https://railway.app/) y crea una nueva cuenta o inicia sesión.
2. Crea un **New Project** → **Deploy from GitHub repo** → conecta tu repositorio.

### Paso 6 — Agregar un Volume para persistencia

1. En tu proyecto de Railway, ve a **Add Service** → **Volume**.
2. Móntalo en `/data` (el bot guarda `state.db` ahí por defecto).

> **Importante:** sin el Volume, el bot perderá el historial de entregas notificadas cada vez que se reinicie, y volverá a notificar todas las entregas como si fueran nuevas.

### Paso 7 — Configurar variables de entorno en Railway

En la sección **Variables** de tu servicio, agrega:

```
TELEGRAM_BOT_TOKEN   = tu_token_aqui
TELEGRAM_CHAT_ID     = -100xxxxxxxxxx
TELEGRAM_ADMIN_ID    = tu_user_id_numerico
CHECK_INTERVAL_MINUTES = 60
DATABASE_PATH        = /data/state.db
```

### Paso 8 — Desplegar

Railway detectará el `Procfile` y lanzará `python bot.py` como proceso worker persistente (always-on).

Verifica en los **Logs** que aparezca algo como:

```
Bot starting…
Scheduler started – checking every 60 minutes.
Starting check cycle…
Check cycle complete.
```

---

## Mecanismo manual para Descifra

Si tienes acceso a un PDF de Descifra antes de que aparezca en La Tercera:

1. Abre un chat privado con el bot.
2. Envía el PDF con `/descifra` como caption, o envía primero `/descifra` y luego responde a ese mensaje con el PDF.
3. El bot publicará el PDF en la comunidad con el formato estándar y te confirmará por privado.

---

## Manejo de errores

- Si un scraper falla, el error queda logueado y el resto de las fuentes sigue funcionando con normalidad.
- Si una fuente falla **3 ciclos consecutivos**, el bot te envía un aviso privado al `TELEGRAM_ADMIN_ID`:
  > ⚠️ El scraper de [FUENTE] lleva 3 fallos seguidos. Probablemente el sitio cambió su estructura HTML.

En ese caso, revisa el scraper correspondiente en `scrapers/<fuente>.py` y actualiza el selector HTML según la nueva estructura del sitio.

---

## Nota sobre robots.txt (Panel Ciudadano)

El sitio `panelciudadano.cl` tiene un `robots.txt` restrictivo. El bot respeta esto usando:

- Un `User-Agent` identificable y honesto.
- Una pausa de 2-3 segundos entre requests a distintos URLs del mismo sitio.
- Sin reintentos agresivos en caso de error.

Acceder a contenido público a pesar del `robots.txt` es técnicamente permitido (es una convención, no una ley), pero el bot se porta como un buen ciudadano de la web.
