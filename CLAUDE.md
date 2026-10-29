# outlook-masive_emails

Sistema de envío masivo de correos electrónicos vía **Outlook COM** (Windows),
desarrollado en **Python**. Los contactos vienen de **Airtable**. El flujo
principal es: importar plantilla EML → previsualizar → enviar masivamente.

El repo tiene una **capa hexagonal** (`domain/`, `ports/`, `application/`,
`infrastructure/`), pero **no todo el hexágono está en el camino de envío
real**: `application/` y `infrastructure/adapters/` son capa en pruebas (ver
[Arquitectura](#arquitectura)).

@.claude/agents/coordinador.md

## Estilo de comunicación

- Respuestas cortas y directas. Ve al grano.
- No des explicaciones detalladas salvo que se pidan explícitamente.
- Prioriza ahorrar tokens: sin relleno, sin repetir el contexto ni resumir lo
  obvio.
- Mantén la memoria al mínimo: guarda solo lo no derivable del código/git.
- **Idioma**: español para respuestas, documentación y comentarios de código.
  Los identificadores de código van en inglés (`AirtableRepository`,
  `HtmlEmailBuilder`, `generate_payload`).

## Flujo principal

Este es el flujo **real de producción**, verificado con `grep` sobre los
imports: no pasa por `application/` ni por `infrastructure/adapters/`.

```
EML/MSG → import_email_template.py → html/templates/body_html.html
                                           + html/images/body/*
                                                        ↓
                    main.py  (o web/app.py, vía POST /api/send)
                                                        ↓
                              staging/emails_to_send.json
                                                        ↓
                    send_from_staging.py (Python de Windows)
                                                        ↓
                                          Outlook COM → envío real
```

1. **Importar plantilla EML**: `import_email_template.py` parsea el EML/MSG,
   extrae asunto, HTML e imágenes inline (que deja en
   `html/images/body/`) y escribe `html/templates/body_html.html` con
   placeholders `{images[N]}`.
2. **Generar staging**: `main.py` (CLI) o `web/app.py` (UI, `POST /api/send`)
   toman contactos desde Airtable (u otro repositorio), construyen el HTML
   final por destinatario (con reemplazos de `{name}` y `{images[N]}`) y dejan
   el resultado en `staging/emails_to_send.json`.
3. **Enviar**: `send_from_staging.py` (ejecutado con Python de Windows +
   `pywin32`) lee el staging y envía vía Outlook COM con imágenes embebidas
   como MAPI properties.

## Stack

| Capa              | Tecnología                                           |
| ----------------- | ---------------------------------------------------- |
| Lenguaje          | Python 3.13+                                         |
| Gestor            | **uv** (`uv.lock`, `pyproject.toml`)                 |
| Arquitectura      | Hexagonal: `domain/`, `application/`, `ports/`, `infrastructure/` (parcial en producción, ver [Arquitectura](#arquitectura)) |
| Web (preview)     | FastAPI + Jinja2 (`web/`)                            |
| Contactos         | Airtable REST API (también: Supabase, Notion, CSV)   |
| Envío             | Outlook COM vía Windows Python + `pywin32`          |
| Tests             | pytest (`test/` y `tests/`)                          |
| Tracking          | `tracking/` y `staging/`                            |

### Entorno de ejecución

Este proyecto corre en **WSL2** para desarrollo, pero el envío real se hace
con **Windows Python** (`/mnt/c/Python313/python.exe`) para acceder a
Outlook COM. El script `send_from_staging.py` se ejecuta desde Windows Python,
NO desde WSL Python.

`main.py` y `preview.py` importan `domain.*` e `infrastructure.*`, que viven
en el venv de **uv** (WSL). El Python de Windows no los tiene: por eso
`main.py` **nunca** se lanza con `python.exe`, solo `send_from_staging.py` sí.

```sh
# En WSL: preparar el staging
uv run main.py

# En Windows: enviar
/mnt/c/Python313/python.exe send_from_staging.py
```

`send.sh` es el wrapper que encadena ambos pasos:

```bash
uv run main.py "$@" && /mnt/c/Python313/python.exe send_from_staging.py
```

## Comandos canónicos

Estos son los comandos que definen «terminado». La puerta de calidad los
ejecuta por su cuenta; no son decorativos.

```sh
uv sync --all-groups                       # instalar todo (grupos `dev` y `test`)
uv run --no-sync pytest                    # suite completa (test/ + tests/)
uv run --no-sync pytest tests/test_<archivo>.py -v   # un archivo específico
uv run --no-sync pytest -k "<patron>"      # tests por nombre
uv add --dev mypy                          # agregar type checker (cuando se quiera)
```

> ⚠️ **`uv sync` a secas DESINSTALA pytest.** Sin `--all-groups` uv poda el
> grupo `test` de este repo, que es donde vive pytest (verificado:
> `uv sync --dry-run` → «Would uninstall 5 packages: iniconfig, packaging,
> pluggy, pygments, pytest»). La puerta de calidad usa `uv run --no-sync`:
> nunca muta el entorno del proyecto.

El linter es **ruff** (ya está en el grupo `dev` de `pyproject.toml`), pero la
calidad de lint se mide como **regresión contra la línea base congelada**
(`.claude/linea-base.json`), no con `ruff check` crudo. Los comandos exactos
de cada perfil viven en `.claude/verificacion.json`, no aquí.

## Definición de terminado

**Un agente que se autoevalúa siempre se aprueba.** Por eso:

1. Nada está terminado hasta que **un comando concreto sale con código 0** y
   se pega su **salida literal** en el reporte. No vale `✓`, no vale «pasa»,
   no vale una casilla marcada.
2. Un criterio de aceptación que no se comprueba con un comando **no es un
   criterio**: es un deseo. Se reescribe o se rechaza.
3. La puerta de calidad (`.claude/hooks/puerta-calidad.mjs`) vuelve a ejecutar
   los comandos por su cuenta al terminar cada agente que escribe código, y
   lo bloquea si fallan. Ver [Puerta de calidad y hooks](#puerta-de-calidad-y-hooks).

## Reglas duras

Estas no se negocian, ni «por esta vez», ni para desbloquear una tarea.

- **Prohibido debilitar un test** para que pase: cambiar una aserción, agregar
  `@pytest.skip`/`@pytest.xfail`, subir un timeout, borrar un caso, o mockear
  el comportamiento que está bajo prueba.
- **Prohibido regenerar la línea base congelada** (`.claude/linea-base.json`)
  para que un error deje de contar. Solo la regenera el usuario, y solo a la
  baja.
- **Prohibido tocar la configuración** del linter, del compilador o de pytest
  (`pyproject.toml`, `uv.lock`) para silenciar un fallo. Igual con `noqa` y
  `pragma: no cover`.
- **Verifica los datos que recibes, no solo los que produces.** Un dato del
  plan o de una spec es una hipótesis: comprueba con `grep` cada símbolo,
  ruta y recuento antes de construir encima. Si no coincide, corrígelo y dilo.
- **Los bugs que aparecen al cubrir código sin tests se reportan, no se
  arreglan ahí.** Se caracteriza el comportamiento roto tal como está y se
  decide aparte. Mezclar «refactor» con «y de paso arreglo cosas» destruye la
  única garantía de un refactor: que nada cambió.
- **Si un comando falla en un archivo que no es tuyo** y hay agentes
  trabajando en paralelo, **repite el comando** antes de investigarlo. Casi
  siempre es escritura concurrente sobre el mismo árbol, no un defecto real.
- **Solo un rol escribe código de producción** (`desarrollador`). Los tests
  son del `tester`. El `revisor` no lleva `Write`, `Edit` ni `NotebookEdit`
  (sí tiene `Bash`), y de ahí viene su independencia: reportar, no arreglar.
  El hook `guardian-bash.mjs` cubre la fuga por Bash.

### Reglas duras de plataforma (específicas de este proyecto)

- **`send_from_staging.py` permanece standalone.** Sin imports del proyecto
  (`from domain...`, `from application...`, etc.). Razón: Windows Python cachea
  `.pyc` desde el directorio del script; un import cruzado con el código de
  WSL rompe esa caché. Esto es **defecto crítico** si se viola.
- **Paths absolutos** con `Path(__file__).resolve().parent`. El directorio de
  trabajo del usuario no es predecible.
- **Filtrar archivos `.Identifier`** al listar imágenes en WSL (los genera
  OneDrive/Windows). Esto es **defecto crítico** si se viola.
- **Subject desde `html/templates/subject.txt`**, nunca hardcodeado en
  código.
- **HTML usa `{images[N]}` → `cid:image_N`** para imágenes inline. Los
  binarios se embeben vía Outlook COM con MAPI properties (no como adjuntos
  separados).

## Arquitectura

Hexagonal, con separación entre dominio compartido, aplicación, puertos e
infraestructura. **Ojo: el hexágono no es todo el camino de envío.** Lo que
está en producción y lo que es capa en pruebas:

```
domain/              ← entidades y tipos puros — sin I/O, sin imports externos
                        ✅ PRODUCCIÓN: domain/entities.py lo usan main.py y web/app.py
ports/               ← interfaces que application/ necesita (contact_repository_port, email_sender_port, signature_provider_port)
                        ⚠️ solo a través de application/ → capa en pruebas
application/         ← casos de uso que orquestan domain + ports (send_emails.py)
                        ⚠️ Capa en pruebas: solo lo importan test/test_architecture.py
                        y test/test_preview_flow.py. Nada de producción lo usa.
infrastructure/
  ├── adapters/      ← Outlook COM, CSV, etc.
                        ⚠️ Capa en pruebas: solo lo importa test/test_outlook_adapter.py.
                        El envío real NO pasa por OutlookDesktopAdapter.
  ├── repositories/  ← Airtable, Supabase, Notion, CSV, multi
                        ✅ PRODUCCIÓN: main.py y web/app.py los usan
  ├── services/      ← logging, html_email_builder, html_preview_service, send_tracker
                        ✅ PRODUCCIÓN: main.py, preview.py y web/app.py los usan
  └── providers/     ← vacío por ahora (solo __init__.py)
html/                ← plantillas HTML, templates, assets (logos, imágenes)
Templates/           ← plantillas de correo (EML/MSG fuente)
web/                 ← app FastAPI de preview + entrada al staging (`POST /api/send`)
main.py              ← entrypoint que arma el staging JSON (producción)
send_from_staging.py ← envío real (standalone, sin imports del proyecto)
preview.py           ← previsualización local
import_email_template.py ← parser EML/MSG
```

En una frase: **el camino de envío real usa `domain/entities.py` +
`infrastructure/repositories/` + `infrastructure/services/`; `application/`,
`ports/` y `infrastructure/adapters/` son capa en pruebas.** El adaptador real
de Outlook COM vive en `send_from_staging.py`, no en
`infrastructure/adapters/outlook_desktop_adapter.py`.

### Convenciones

- Nombres de archivo: `snake_case.py`. Tests: `test_<archivo>.py` (en `test/`
  o `tests/`).
- Módulos que solo corren en Windows o solo tocan COM/red/IO se identifican
  por su contexto (no hay sufijo `.server.py` como en TypeScript — la
  restricción es que `send_from_staging.py` no importa del proyecto).
- Sin valores hardcodeados en UI web: usar plantillas de `web/templates/` y
  configuración vía `.env`.
- `send_from_staging.py` es el único archivo que cruza la barrera WSL→Windows.

### Dónde NO hay red de seguridad

`pyproject.toml` configura pytest para incluir `testpaths = ["."]`, pero **la
suite es desigual**: `tests/` es la suite reciente (último commit 2026-09-25) y
`test/` es legacy (último commit 2026-07-17). Los tests nuevos van a
`tests/`.

`web/` **sí tiene tests automatizados**: `tests/conftest.py`,
`tests/test_send_payload.py`, `tests/test_upload_eml.py` y
`tests/test_regression_cross_contamination.py` importan `web.app` y ejercitan
`/api/upload-eml`, `/api/preview` y `/api/send`. Lo que **no** tiene cobertura
automatizada es el **render visual** de la UI (CSS, layout, accesibilidad).

Consecuencia práctica: **un cambio puede romper el render visual de la UI web
y `uv run pytest` sale en verde.** Cuando el trabajo toca `web/`, hay que
decirlo explícitamente en el reporte y dejar la verificación visual al
usuario.

## Secretos

`.env` contiene credenciales de Airtable y cualquier otro proveedor. Está
excluido de git vía `.gitignore`. Documentar nombres de variables en
`.env.example`, nunca valores.

Las claves que ya están en commits antiguos siguen en el historial: la vía
correcta si importan es **rotarlas**, no borrarlas.

## Sistema de agentes

El **Coordinador es la sesión principal**, no un subagente: es el único que
puede pararse a pedirte aprobación y el único que puede delegar en paralelo.
Su rol está definido en [`.claude/agents/coordinador.md`](.claude/agents/coordinador.md),
que se carga en la sesión principal con la línea `@.claude/agents/coordinador.md`
de este archivo.

> `.claude/agents/coordinador.md` **no tiene frontmatter YAML**, así que no se
> registra como agente de Claude Code: no se puede delegar en él ni invocarlo
> con la herramienta `Agent`. El rol existe y se aplica a **la sesión
> principal**, que es quien lo carga.

El Coordinador **es el product owner**: clasifica, planifica, obtiene
aprobación y delega, pero no codifica. Sabe del negocio y tiene el concepto,
el motivo y la finalidad de la aplicación. Es el capitán del barco.

Los subagentes están definidos en `.claude/agents/` y documentados en
[`.claude/agents/TEAM.md`](.claude/agents/TEAM.md):

| Agente         | Modelo | Responsabilidad                                                                       |
| -------------- | ------ | ------------------------------------------------------------------------------------- |
| `planificador` | opus   | Spec → tareas atómicas con archivos exclusivos y olas sin solape                      |
| `disenador-web`| sonnet | UI/UX, plantillas HTML para correos, design system, accesibilidad                     |
| `desarrollador`| sonnet | Implementar en el repo. **Único que escribe código de producción**                    |
| `tester`       | sonnet | Diseñar y ejecutar pruebas con pytest contra la spec                                  |
| `revisor`      | opus   | Tests debilitados primero, luego corrección, convenciones y restricciones de plataforma. **Sin `Write`, `Edit` ni `NotebookEdit`** |

> El identificador del agente es **`disenador-web`** (sin tilde, sin
> espacio): es el `name:` de su frontmatter y el nombre del fichero
> `.claude/agents/disenador-web.md`. En prosa, «diseñador web» está bien.

Reglas clave del equipo: plan aprobado antes de ejecutar, spec de diseño antes
que código cuando hay UI nueva, QA obligatorio antes de dar algo por listo, y
cada agente es la única fuente de verdad de su área — no se "simplifica" una
spec ajena por cuenta propia.

**Ningún subagente lleva la herramienta `Agent`**: solo la sesión principal
delega. `planificador` y `disenador-web` escriben documentos, no código, y un
hook `PreToolUse` los bloquea si lo intentan.

Los **agent teams experimentales se dejan apagados**: con ellos activos un
subagente con nombre arranca como compañero de equipo y no devuelve su
resultado, solo notifica que terminó, lo que rompe este ciclo.

Para entender el sistema completo: [`AGENTS_SYSTEM.md`](AGENTS_SYSTEM.md).
Para deshacerlo: ver `AGENTS_SYSTEM.md` sección "Setup inicial".

## Puerta de calidad y hooks

La puerta de calidad **existe porque `.claude/settings.json` la registra**.
Los comandos que ejecuta viven en `.claude/verificacion.json` (perfiles
`rapida` y `completa`); el hook es genérico y no conoce ningún comando
concreto.

`.claude/settings.json` registra dos eventos:

| Evento        | Matcher                    | Comando                                            | Timeout |
| ------------- | -------------------------- | -------------------------------------------------- | ------- |
| `SubagentStop`| `desarrollador|tester`     | `node .claude/hooks/puerta-calidad.mjs rapida`      | 900 s   |
| `PreToolUse`  | `Write|Edit|MultiEdit|NotebookEdit` | `node .claude/hooks/guardian-config.mjs`   | 10 s    |

El perfil `rapida` suma 300 + 120 + 120 = **540 s**, dentro del timeout de
900 s del evento. El perfil `completa` suma más y **no** se registra como
hook: lo invoca el Coordinator a mano al cerrar cada ola.

### Semántica de `obligatorio`

No significa «opcional»:

- `obligatorio: true` + herramienta ausente → **FALLA** y bloquea, con motivo
  accionable. Un obligatorio saltado en silencio es el *fail-open* que hay que
  cerrar.
- `obligatorio: false` + herramienta ausente → **SALTADO**, no bloquea.
- Herramienta presente + comando fallando → **FALLA** y bloquea, siempre. La
  disponibilidad de la herramienta nunca suaviza el resultado.

El bloqueo del subagente es **código de salida 2 + el motivo en `stderr`**
(códigos de comandos: 0 = pasa · 1 = falla · 2 = error de ejecución · 3 = no
aplica).

### Hooks por agente (frontmatter)

Viven en el `hooks:` del frontmatter de los agentes:

| Hook                      | Matcher                    | Roles | Qué hace                                                                 |
| ------------------------- | -------------------------- | ----- | ------------------------------------------------------------------------ |
| `guardian-escritura.mjs`  | `Write|Edit|MultiEdit|NotebookEdit` | `planificador`, `disenador-web` | Solo permite escribir en `.claude/planes/`, `.claude/disenos/`, `.claude/cache/`, `docs/` y `SPEC.md` |
| `guardian-bash.mjs`       | `Bash`                     | los cinco | Cubre la fuga por Bash. **Dos modos**: en `planificador`/`disenador-web`/`revisor` es una allowlist estricta de documentos; en `desarrollador`/`tester` permite el código de producción y solo niega las rutas de la configuración de la puerta y los comandos destructivos (`sed -i`, `rm -rf`, `git reset --hard`, `git clean`, `uv add/sync/lock`, `writeFileSync`…) |
| `validar-plan.mjs`        | `Write` (solo `planificador`) | `planificador` | Valida el schema de `.claude/planes/*.json`                        |

> El modo de `guardian-bash.mjs` se decide con `agent_type` contra
> `agentesVigilados` de `.claude/verificacion.json`. Sin `agent_type` cae al
> modo restrictivo (*fail-safe*). Sin este modo, `desarrollador` y `tester`
> —los roles vigilados por la puerta— podían reescribir **por Bash** la
> configuración que los juzga: `guardian-config.mjs` solo cubre
> `Write`/`Edit`/`NotebookEdit`.

### CLI que el Coordinator invoca a mano

**No son hooks**: se ejecutan a mano con `node`.

```sh
node .claude/hooks/linea-base.mjs generar      # regenera la línea base — SOLO el usuario, y solo a la baja
node .claude/hooks/linea-base.mjs verificar     # compara con .claude/linea-base.json
node .claude/hooks/drift-detection.mjs verificar
node .claude/hooks/drift-detection.mjs heuristico
node .claude/hooks/checkpoint.mjs crear "<nombre>"
node .claude/hooks/checkpoint.mjs restaurar "<nombre>"
node .claude/hooks/checkpoint.mjs listar
node .claude/hooks/checkpoint.mjs estado
```

### Trampa conocida: workspace trust

**Los hooks de proyecto NO se ejecutan si la carpeta no es confiable en
Claude Code.** Sin trust, la puerta no bloquea y parece que todo va bien. Si
un hook no dispara, sospechá de trust antes que del hook.

## Archivos clave

| Archivo                                    | Propósito                                                              |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `CLAUDE.md`                                | Este documento (fundacional del proyecto)                              |
| `AGENTS_SYSTEM.md`                         | Sistema de agentes (guía completa)                                     |
| `README.md`                                | Documentación general                                                  |
| `SPEC.md`                                  | Índice de ciclos activos                                               |
| `.claude/agents/coordinador.md`            | Rol del Coordinador (orquestador) — sin frontmatter, lo carga la sesión principal |
| `.claude/agents/TEAM.md`                   | Cómo colaboran los agentes                                             |
| `.claude/settings.json`                    | Registra los hooks (puerta de calidad, guardian-config)                |
| `.claude/verificacion.json`                | Comandos de calidad por perfil (`rapida`, `completa`)                  |
| `.claude/hooks/puerta-calidad.mjs`         | Puerta de calidad: ejecuta el perfil y bloquea con exit 2              |
| `.claude/linea-base.json`                  | Línea base de errores heredados de lint (solo la regenera el usuario, y solo a la baja) |
| `domain/entities.py`                       | ✅ Producción: entidades puras que usan `main.py` y `web/app.py`       |
| `infrastructure/repositories/`             | ✅ Producción: Airtable, Notion, CSV, Supabase, multi                  |
| `infrastructure/services/`                 | ✅ Producción: html_email_builder, html_preview_service, logging, tracker |
| `infrastructure/adapters/`                 | ⚠️ Capa en pruebas (solo `test/test_outlook_adapter.py`)               |
| `application/`                             | ⚠️ Capa en pruebas (solo `test/test_architecture.py`, `test_preview_flow.py`) |
| `ports/`                                   | ⚠️ Capa en pruebas (solo a través de `application/`)                    |
| `main.py`                                  | ✅ Producción: arma `staging/emails_to_send.json` (CLI)                |
| `web/app.py`                               | ✅ Producción: arma el staging desde la UI (`POST /api/send`)          |
| `send_from_staging.py`                     | ✅ Producción: envío real vía COM, standalone, único cruce WSL→Windows |
| `pyproject.toml`                           | Dependencias + configuración de pytest                                 |
| `html/templates/subject.txt`               | Asunto por defecto del envío                                           |
