# outlook-masive-emails

> *Envío masivo de correos corporativos a través de Outlook Desktop, con interface web FastAPI y contactos desde Airtable, Notion, CSV o Supabase.*

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![Outlook COM](https://img.shields.io/badge/Outlook-win32com-0078D4?logo=microsoft-outlook&logoColor=white)
![Airtable](https://img.shields.io/badge/Contacts-Airtable-FFB400?logo=airtable&logoColor=white)
![uv](https://img.shields.io/badge/pkg-uv-5C2D91?logo=astral&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Tabla de contenidos

- [CLI o Web?](#-cli-o-web)
- [✨ Características](#-características)
- [🧭 Flujo general](#-flujo-general)
- [🛠️ Requisitos previos](#-requisitos-previos)
- [🚀 Instalación](#-instalación)
- [⚙️ Configuración](#-configuración)
- [🖥️ Levantar la interface web](#-levantar-la-interface-web)
- [📨 Envío masivo desde la interface](#-envío-masivo-desde-la-interface)
- [🧪 Previsualizar un correo antes de enviar](#-previsualizar-un-correo-antes-de-enviar)
- [🗂️ Importar plantilla desde EML/MSG por CLI](#-importar-plantilla-desde-emlmsg-por-cli)
- [🤖 Envío por línea de comandos (legacy)](#-envío-por-línea-de-comandos-legacy)
- [📁 Estructura del proyecto](#-estructura-del-proyecto)
- [🔧 Solución de problemas](#-solución-de-problemas)
- [📜 Licencia](#-licencia)

---

## CLI o Web?

| Flujo | Cuándo usarlo | Comando de entrada |
|-------|---------------|--------------------|
| **Web (recomendado)** | Uso diario, previsualización visual, monitoreo de progreso | `uv run web/run.py` → `http://localhost:8000` |
| **CLI (avanzado / legacy)** | Scripts automatizados, pipelines, tareas batch sin UI | `main.py` o `send_from_staging.py` |

> 📌 **Tip:** La interface web envuelve internamente los mismos scripts CLI. Para el 95% de los casos, usá la Web.

---

## ✨ Características

- 🌐 **Interface web FastAPI** con subida de plantillas, previsualización y envío en un solo lugar.
- 📩 **Importación EML/MSG** — extrae HTML e imágenes inline directamente desde correos guardados.
- 🗂️ **Múltiples fuentes de contactos**: Airtable, Notion, CSV y Supabase.
- 👁️ **Previsualización real** con el nombre del destinatario sustituido.
- 📤 **Envío masivo por Outlook Desktop** vía `win32com` (sin SMTP, sin servidores externos).
- 📊 **Tracking** de cada corrida en `tracking/run_*.json` con totales, fallos y tiempos.
- 🧱 **Arquitectura hexagonal** (domain / application / infrastructure / ports) fácil de extender.

---

## 🧭 Flujo general

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ 1. Importar EML │──▶│ 2. Elegir fuente  │──▶│ 3. Elegir vista  │
│   o MSG         │    │   de contactos    │    │   de la fuente   │
└─────────────────┘    └──────────────────┘    └────────┬────────┘
                                                        │
┌─────────────────┐    ┌──────────────────┐    ┌────────▼────────┐
│ 6. Monitorear   │◀──│ 5. POST /api/send │◀──│ 4. Previsualizar │
│   tracking      │    │   → win32com      │    │   con nombre     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

1. **Importar plantilla** (`.eml` o `.msg` desde Outlook).
2. **Seleccionar fuente** de contactos (Airtable / Notion / CSV / Supabase).
3. **Elegir vista** dentro de esa fuente.
4. **Previsualizar** con un nombre de prueba.
5. **Enviar** desde la UI (`POST /api/send` → `send_from_staging.py`).
6. **Monitorear** el progreso en `tracking/run_*.json`.

---

## 🛠️ Requisitos previos

| Requisito | Versión / Detalle |
|-----------|-------------------|
| Python | **3.13** |
| Gestor de paquetes | [`uv`](https://docs.astral.sh/uv/) (recomendado) o `pip` |
| Sistema operativo | **Windows nativo** — obligatorio para `win32com` / Outlook COM |
| Outlook | Desktop instalado y configurado con la cuenta remitente |
| Git | Para clonar el repositorio |

> ⚠️ **Importante:** `win32com` solo funciona en **Windows nativo**. En WSL2 necesitás invocar el Python de Windows directamente (ver [🤖 Envío por línea de comandos](#-envío-por-línea-de-comandos-legacy)).

> 📌 **Tip sobre WSL2:** invocá `/mnt/c/Python313/python.exe` para que `win32com` encuentre la instalación COM real de Outlook.

---

## 🚀 Instalación

```bash
git clone <repo>
cd masive_emails
uv sync                                       # instala todas las dependencias
```

Si preferís `pip`:

```bash
pip install -r requirements.txt
```

> 📌 **Tip:** `uv sync` baja automáticamente `fastapi`, `uvicorn[standard]`, `extract-msg`, `beautifulsoup4`, `requests`, `pandas`, `python-dotenv` y `pywin32` (solo en Windows).

---

## ⚙️ Configuración

Creá un archivo `.env` en la raíz del proyecto con las siguientes variables:

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `AIRTABLE_TOKEN` | Personal Access Token de Airtable | `patXXXXXXXXXXXXXX` |
| `AIRTABLE_BASE_ID` | ID de la base de Airtable | `appXXXXXXXXXXXXXX` |
| `AIRTABLE_CONTACT_TABLE_ID` | ID de la tabla de contactos | `tblXXXXXXXXXXXXXX` |
| `AIRTABLE_VIEW` | Vista por defecto cuando no se pasa `--view` | `"Mi vista principal"` |
| `OUTLOOK_SENDER_EMAIL` | Cuenta Outlook que firma y envía | `tu@empresa.com` |
| `PREVIEW_EMAIL_BEFORE_SEND` | Si vale `true`, abre el HTML antes de enviar | `true` |
| `PREVIEW_OPEN_IN_BROWSER` | Si vale `true`, abre el preview automáticamente | `true` |

Ejemplo de `.env`:

```env
AIRTABLE_TOKEN=patXXXXXXXXXXXXXX
AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX
AIRTABLE_CONTACT_TABLE_ID=tblXXXXXXXXXXXXXX
AIRTABLE_VIEW="Lista Contactos Perú :: No Compradores :: correo masivo"

OUTLOOK_SENDER_EMAIL=tu@empresa.com

PREVIEW_EMAIL_BEFORE_SEND=true
PREVIEW_OPEN_IN_BROWSER=true
```

---

## 🖥️ Levantar la interface web

```bash
uv run web/run.py
```

o equivalentemente:

```bash
uv run uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

Abrí tu navegador en **http://localhost:8000** y verás la UI.

> 📌 **Tip:** `--reload` reinicia el servidor al guardar cambios en `web/`. Para producción usá `uvicorn` sin `--reload` detrás de un proxy.

---

## 📨 Envío masivo desde la interface

Esta es la sección principal del proyecto. Paso a paso:

1. **Abrir la UI** en el navegador (`http://localhost:8000`).
2. **Subir la plantilla**: clic en **"Subir EML/MSG"** → seleccionar el archivo `.eml` o `.msg` descargado de Outlook. El sistema extrae HTML e imágenes inline automáticamente.
3. **Seleccionar fuente de contactos** en el selector lateral: Airtable, Notion, CSV o Supabase.
4. **Elegir la vista** concreta dentro de la fuente seleccionada.
5. **Previsualizar** rellenando el campo **"Nombre de prueba"** (sustituye `{name}` en el HTML).
6. **Escribir el asunto** del correo.
7. **Pulsar "Enviar"** — el sistema llama internamente a `POST /api/send`, que delega a `send_from_staging.py` ejecutado con **Python de Windows** vía `win32com`.
8. **Monitorear el progreso** con el panel lateral o recargando (`GET /api/send/progress` lee `staging/send_progress.json`).

> ⚠️ **Importante:** El envío real requiere **Windows nativo** con Outlook Desktop abierto y la cuenta `OUTLOOK_SENDER_EMAIL` configurada.

---

## 🧪 Previsualizar un correo antes de enviar

Atajo CLI para revisar el renderizado sin pasar por la UI:

```bash
uv run preview.py --name "Juan"
```

Genera `preview/email_preview.html` y lo abre en el navegador si `PREVIEW_OPEN_IN_BROWSER=true`.

---

## 🗂️ Importar plantilla desde EML/MSG por CLI

Alternativa cuando no querés usar la UI web:

```bash
uv run import_email_template.py
# o pasando ruta explícita:
uv run import_email_template.py ruta/al/correo.eml
```

El script:

- Extrae el cuerpo HTML del correo.
- Guarda las imágenes inline en `html/images/body/` con nombres `a.jpg`, `b.jpg`, etc.
- Reemplaza las referencias de imagen por `{images[0]}`, `{images[1]}`, …
- Escribe el resultado en `html/templates/body_html.html`.

> 📌 **Tip:** Después de importar, abrí `html/templates/body_html.html` y reemplazá el nombre del destinatario por `{name}`:
> ```html
> <!-- Antes -->  Hola Juan,
> <!-- Después --> Hola {name},
> ```

---

## 🤖 Envío por línea de comandos (legacy)

Flujo heredado, conservado para scripts automatizados y tareas avanzadas:

```bash
# WSL2 → necesita el Python de Windows en /mnt/c/
/mnt/c/Python313/python.exe main.py --view "Mi vista de Airtable"
```

> Este flujo se conserva solo por compatibilidad. **El flujo recomendado es la interface web** (`🖥️ Levantar la interface web`).

---

## 📁 Estructura del proyecto

```
masive_emails/
├── web/                   # Interface FastAPI (UI + API REST)
│   ├── app.py             # Rutas /, /api/upload-eml, /api/send, /api/send/progress, ...
│   ├── run.py             # Entry point: uvicorn.run(...)
│   └── templates/         # index.html (UI)
├── application/           # Casos de uso (hexagonal)
│   └── send_emails.py
├── domain/                # Entidades y reglas de negocio
│   ├── entities.py
│   └── types.py
├── ports/                 # Interfaces (contact_repository, email_sender, signature_provider)
├── infrastructure/        # Adaptadores
│   ├── repositories/      # airtable, notion, csv, supabase, multi
│   ├── providers/         # extractores EML/MSG
│   └── services/          # html_email_builder, send_tracker, html_preview, logging
├── html/templates/        # body_html.html, base_html.html, sign__html.html, subject.txt
├── staging/               # Payloads pre-ensamblados por la UI
├── tracking/              # Logs por corrida: run_YYYY-MM-DD_HH-MM-SS.json
├── send_from_staging.py   # Worker que la UI invoca para enviar vía win32com
├── main.py                # Entry point CLI legacy
├── preview.py             # Genera preview/email_preview.html
├── import_email_template.py  # Importa .eml/.msg → html/templates/body_html.html
├── send.sh                # Wrapper bash para envío CLI
├── pyproject.toml         # Dependencias (uv)
└── requirements.txt       # Pip-compatible snapshot
```

---

## 🔧 Solución de problemas

- **Outlook no se abre / `win32com` falla** — verificá que `OUTLOOK_SENDER_EMAIL` esté configurada y que Outlook Desktop esté instalado. `win32com` solo funciona en **Windows nativo**, no en WSL2 ni Linux.
- **Airtable devuelve 401** — el `AIRTABLE_TOKEN` expiró o no tiene scope `data.records:read`. Regeneralo en [airtable.com/create/tokens](https://airtable.com/create/tokens).
- **Las imágenes no se ven en el correo recibido** — confirmá que `html/images/body/` contiene los archivos y que `body_html.html` usa `{images[N]}` en los `src`.
- **WSL2 no encuentra Outlook** — invocá el script con `/mnt/c/Python313/python.exe` en lugar del Python de WSL2.
- **`uv sync` falla con `pywin32`** — es normal fuera de Windows. Las dependencias condicionales se saltean automáticamente.

---

## 📜 Licencia

MIT — ver cabecera del repositorio.
