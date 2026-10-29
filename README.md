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
- [🤖 Envío por línea de comandos (CLI)](#-envío-por-línea-de-comandos-cli)
- [📁 Estructura del proyecto](#-estructura-del-proyecto)
- [🔧 Solución de problemas](#-solución-de-problemas)
- [📜 Licencia](#-licencia)

---

## CLI o Web?

| Flujo | Cuándo usarlo | Comando de entrada |
|-------|---------------|--------------------|
| **Web (recomendado)** | Uso diario, previsualización visual, monitoreo de progreso | `uv run web/run.py` → `http://localhost:8000` |
| **CLI (avanzado)** | Scripts automatizados, pipelines, tareas batch sin UI | `main.py` o `send_from_staging.py` |

> 📌 **Tip:** La interface web envuelve internamente los mismos scripts CLI. Para el 95% de los casos, usá la Web.

---

## ✨ Características

- 🌐 **Interface web FastAPI** con subida de plantillas, previsualización y envío en un solo lugar.
- 📩 **Importación EML/MSG** — extrae HTML e imágenes inline directamente desde correos guardados.
- 🗂️ **Múltiples fuentes de contactos**: Airtable, Notion, CSV y Supabase.
- 👁️ **Previsualización real** con el nombre del destinatario sustituido.
- 📤 **Envío masivo por Outlook Desktop** vía `win32com` (sin SMTP, sin servidores externos).
- 📊 **Tracking** de cada corrida en `tracking/run_*.json` con totales, fallos y tiempos.
- 🧱 **Arquitectura hexagonal** (domain / application / infrastructure / ports) fácil de extender. Ojo: `application/`, `ports/` e `infrastructure/adapters/` son **capa en pruebas**; el envío real va por `domain/entities.py` + `infrastructure/repositories/` + `infrastructure/services/` → `send_from_staging.py`.

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

> ⚠️ **Importante:** `win32com` solo funciona en **Windows nativo**. En WSL2 necesitás invocar el Python de Windows directamente (ver [🤖 Envío por línea de comandos](#-envío-por-línea-de-comandos-cli)).

> 📌 **Tip sobre WSL2:** el intérprete de Windows se resuelve solo. Definí
> `WINDOWS_PYTHON_PATH` en el `.env` (o exportalo) y usá `bash send.sh`. **No
> hardcodees la ruta**: `/mnt/c/Users/TU_USUARIO/AppData/Local/Programs/Python/Python313/python.exe`
> es un ejemplo con marcador, y la ruta real depende de la carpeta de perfil de
> Windows y de la versión de Python instalada en cada máquina.

---

## 🚀 Instalación

```bash
git clone URL_DEL_REPOSITORIO
cd outlook-masive_emails
uv sync --all-groups                          # instala todas las dependencias
```

> ⚠️ **Importante:** usá `--all-groups`. Un `uv sync` a secas **desinstala
> pytest**, porque uv poda el grupo `test` de este repo (verificado:
> `uv sync --dry-run` → «Would uninstall 5 packages: iniconfig, packaging,
> pluggy, pygments, pytest»). Sin ese grupo no hay forma de correr la suite.

Si preferís `pip`:

```bash
pip install -r requirements.txt
```

> 📌 **Tip:** `uv sync --all-groups` baja automáticamente `fastapi`, `uvicorn[standard]`, `extract-msg`, `beautifulsoup4`, `requests`, `pandas`, `python-dotenv` y `pywin32` (solo en Windows).

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

# Opcional: ruta al python.exe de Windows cuando corrés desde WSL2.
# La usa `send.sh` y la UI web para localizar el intérprete de Outlook COM.
# Poné la ruta REAL de tu máquina (esto es un ejemplo con marcador).
# WINDOWS_PYTHON_PATH=/mnt/c/Users/TU_USUARIO/AppData/Local/Programs/Python/Python313/python.exe
# WINDOWS_PYTHON_PATH=
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
- Guarda las imágenes inline en `html/images/body/` con nombres `a.png`, `b.png`, … (la extensión se detecta del binario: `png`, `jpg` o `gif`; por defecto `png`).
- Reemplaza las referencias de imagen por `{images[0]}`, `{images[1]}`, …
- Escribe el resultado en `html/templates/body_html.html`.

> 📌 **Tip:** Después de importar, abrí `html/templates/body_html.html` y reemplazá el nombre del destinatario por `{name}`:
> ```html
> <!-- Antes -->  Hola Juan,
> <!-- Después --> Hola {name},
> ```

---

## 🤖 Envío por línea de comandos (CLI)

Para scripts automatizados, pipelines y tareas batch sin UI. Son **dos pasos
en dos runtimes distintos**:

```bash
# 1. En WSL2 → arma staging/emails_to_send.json
uv run main.py --view "Mi vista de Airtable"

# 2. En Windows → lee el staging y envía vía win32com
#    (ruta de ejemplo: usá la REAL de tu máquina, no esta)
/mnt/c/Users/TU_USUARIO/AppData/Local/Programs/Python/Python313/python.exe send_from_staging.py
```

> ⚠️ **`main.py` NO se lanza con el Python de Windows.** Importa
> `domain.entities` e `infrastructure.*`, que viven en el venv de **uv** (WSL);
> el Python de Windows no los tiene. Solo `send_from_staging.py` se ejecuta
> con `python.exe`.

`send.sh` es el wrapper que encadena ambos pasos **y resuelve solo el
intérprete de Windows**, para que no tengas que hardcodear una ruta que
depende de cada máquina. El orden de resolución es:

1. `WINDOWS_PYTHON_PATH` del entorno.
2. `WINDOWS_PYTHON_PATH` del `.env` de la raíz del proyecto.
3. Instalaciones habituales bajo `/mnt/c` (mismo criterio que la UI web).

```bash
# Envío real: uv run main.py → python.exe send_from_staging.py
bash send.sh --view "Mi vista de Airtable"
```

Antes de un envío real podés comprobar la máquina **sin enviar nada**:

```bash
bash send.sh --dry-run --view "Mi vista de Airtable"
```

El `--dry-run` resuelve el intérprete, imprime el `uv run main.py` que
ejecutaría, la ruta del intérprete de Windows que encontró y el staging que
generaría, y **no envía ningún correo**. Si no encuentra el intérprete, falla
con un mensaje que dice exactamente qué definir y dónde.

> Si tu Windows está montado en otro sitio que `/mnt/c`, definí
> `WINDOWS_MOUNT_ROOT` (por defecto `/mnt/c`).

> La interface web es la recomendada para el uso diario (`🖥️ Levantar la
> interface web`), pero esta ruta por CLI es una de las dos entradas reales
> al staging: la otra es `POST /api/send`.

---

## 📁 Estructura del proyecto

```
masive_emails/
├── web/                   # Interface FastAPI (UI + API REST)
│   ├── app.py             # Rutas /, /api/upload-eml, /api/send, /api/send/progress, ...
│   ├── run.py             # Entry point: uvicorn.run(...)
│   └── templates/         # index.html (UI)
├── domain/                # Entidades y reglas de negocio  ✅ PRODUCCIÓN
│   ├── entities.py
│   └── types.py
├── infrastructure/        # Adaptadores
│   ├── repositories/      # airtable, notion, csv, supabase, multi   ✅ PRODUCCIÓN
│   ├── services/          # html_email_builder, send_tracker, html_preview, logging  ✅ PRODUCCIÓN
│   ├── providers/         # (vacío por ahora: solo __init__.py)
│   └── adapters/          # outlook_desktop_adapter  ⚠️ capa en pruebas
├── application/           # Casos de uso (hexagonal)   ⚠️ capa en pruebas
│   └── send_emails.py
├── ports/                 # Interfaces (contact_repository, email_sender, signature_provider)  ⚠️ capa en pruebas
├── html/templates/        # body_html.html, base_html.html, sign__html.html, subject.txt
├── staging/               # Payloads pre-ensamblados por la UI
├── tracking/              # Logs por corrida: run_YYYY-MM-DD_HH-MM-SS.json
├── send_from_staging.py   # Envío real vía win32com (standalone, sin imports del proyecto)
├── main.py                # Entry point CLI: arma el staging (producción)
├── preview.py             # Genera preview/email_preview.html
├── import_email_template.py  # Importa .eml/.msg → html/templates/body_html.html
├── send.sh                # Wrapper bash: resuelve el Python de Windows, staging + envío (--dry-run = simula)
├── pyproject.toml         # Dependencias (uv)
└── requirements.txt       # Pip-compatible snapshot
```

> ⚠️ **Lo hexagonal no es todo el camino de envío.** El envío real es:
> `main.py` (o `web/app.py` vía `POST /api/send`) → `staging/emails_to_send.json`
> → `send_from_staging.py` → Outlook COM. `application/`, `ports/` e
> `infrastructure/adapters/` los usan los tests, no producción.

---

## 🔧 Solución de problemas

- **Outlook no se abre / `win32com` falla** — verificá que `OUTLOOK_SENDER_EMAIL` esté configurada y que Outlook Desktop esté instalado. `win32com` solo funciona en **Windows nativo**, no en WSL2 ni Linux.
- **Airtable devuelve 401** — el `AIRTABLE_TOKEN` expiró o no tiene scope `data.records:read`. Regeneralo en [airtable.com/create/tokens](https://airtable.com/create/tokens).
- **Las imágenes no se ven en el correo recibido** — confirmá que `html/images/body/` contiene los archivos y que `body_html.html` usa `{images[N]}` en los `src`.
- **WSL2 no encuentra Outlook** — el envío necesita el Python **nativo de Windows** (con `pywin32`), no el de WSL2. Definí `WINDOWS_PYTHON_PATH` en el `.env` con la ruta real de tu máquina y usá `bash send.sh` (que la resuelve solo) o `bash send.sh --dry-run` para verificar la máquina sin enviar nada.
- **`uv sync` falla con `pywin32`** — es normal fuera de Windows. Las dependencias condicionales se saltean automáticamente.
- **`uv sync` desinstaló pytest** — volvés a la línea anterior: `uv sync` a secas poda el grupo `test` de este repo. Usá `uv sync --all-groups` y verificá con `uv run --no-sync pytest`.
- **`ModuleNotFoundError: domain` al correr `main.py`** — lo estás lanzando con el Python de Windows. `main.py` necesita el venv de **uv**: corré `uv run main.py` (WSL). El único script que va con `python.exe` es `send_from_staging.py`.
- **No aparece `pytest` en el venv** — `uv sync --all-groups` (no `uv sync`).

---

## 📜 Licencia

MIT — ver cabecera del repositorio.
