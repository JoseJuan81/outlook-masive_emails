# outlook-masive_emails

Sistema de envío masivo de correos electrónicos vía **Outlook COM** (Windows),
desarrollado en **Python** con **arquitectura hexagonal**. Los contactos
vienen de **Airtable**. El flujo principal es: importar plantilla EML →
previsualizar → enviar masivamente.

## Estilo de comunicación

- Respuestas cortas y directas. Ve al grano.
- No des explicaciones detalladas salvo que se pidan explícitamente.
- Prioriza ahorrar tokens: sin relleno, sin repetir el contexto ni resumir lo
  obvio.
- Mantén la memoria al mínimo: guarda solo lo no derivable del código/git.
- **Idioma**: español para respuestas, documentación y comentarios de código.
  Los identificadores de código van en inglés (`AirtableRepository`,
  `OutlookDesktopAdapter`, `generate_payload`).

## Flujo principal

```
EML/MSG → import_email_template.py → main.py → staging/emails_to_send.json
                                                        ↓
                                          outlook_send.py (Windows Python)
                                                        ↓
                                          Outlook COM → envío real
```

1. **Importar plantilla EML**: `import_email_template.py` parsea el EML/MSG,
   extrae asunto, HTML, imágenes inline (binarios para adjuntar vía COM) y
   reemplaza placeholders `{images[N]}` por `cid:image_N`.
2. **Generar staging**: `main.py` toma contactos desde Airtable (u otro
   repositorio), construye el HTML final por destinatario (con reemplazos de
   `{name}` y `{images[N]}`) y deja el resultado en `staging/emails_to_send.json`.
3. **Enviar**: `outlook_send.py` (ejecutado con Windows Python + `pywin32`)
   lee el staging y envía vía Outlook COM con imágenes embebidas como MAPI
   properties.

## Stack

| Capa              | Tecnología                                           |
| ----------------- | ---------------------------------------------------- |
| Lenguaje          | Python 3.13+                                         |
| Gestor            | **uv** (`uv.lock`, `pyproject.toml`)                 |
| Arquitectura      | Hexagonal: `domain/`, `application/`, `ports/`, `infrastructure/` |
| Web (preview)     | FastAPI + Jinja2 (`web/`)                            |
| Contactos         | Airtable REST API (también: Supabase, Notion, CSV)   |
| Envío             | Outlook COM vía Windows Python + `pywin32`          |
| Tests             | pytest (`test/` y `tests/`)                          |
| Tracking          | `tracking/` y `staging/`                            |

### Entorno de ejecución

Este proyecto corre en **WSL2** para desarrollo, pero el envío real se hace
con **Windows Python** (`/mnt/c/Python313/python.exe`) para acceder a
Outlook COM. El script `outlook_send.py` se ejecuta desde Windows Python,
NO desde WSL Python.

```sh
# En WSL: preparar el staging
uv run main.py

# En Windows: enviar
/mnt/c/Python313/python.exe outlook_send.py
```

## Comandos canónicos

Estos son los comandos que definen «terminado». La puerta de calidad los
ejecuta por su cuenta; no son decorativos.

```sh
uv run pytest                              # suite completa (test/ + tests/)
uv run pytest tests/test_<archivo>.py -v   # un archivo específico
uv run pytest -k "<patron>"                # tests por nombre
uv add --dev ruff                          # agregar linter (cuando se quiera)
uv add --dev mypy                          # agregar type checker (cuando se quiera)
```

## Definición de terminado

**Un agente que se autoevalúa siempre se aprueba.** Por eso:

1. Nada está terminado hasta que **un comando concreto sale con código 0** y
   se pega su **salida literal** en el reporte. No vale `✓`, no vale «pasa»,
   no vale una casilla marcada.
2. Un criterio de aceptación que no se comprueba con un comando **no es un
   criterio**: es un deseo. Se reescribe o se rechaza.
3. La puerta de calidad (`.claude/hooks/puerta-calidad.mjs`) vuelve a ejecutar
   los comandos por su cuenta al terminar cada agente que escribe código, y
   lo bloquea si fallan.

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
  son del `tester`. El `revisor` no puede escribir nada, y de ahí viene su
  independencia.

### Reglas duras de plataforma (específicas de este proyecto)

- **`outlook_send.py` permanece standalone.** Sin imports del proyecto
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
infraestructura:

```
domain/              ← entidades y tipos puros — sin I/O, sin imports externos
ports/               ← interfaces que application/ necesita (contact_repository_port, email_sender_port, signature_provider_port)
application/         ← casos de uso que orquestan domain + ports (send_emails.py)
infrastructure/      ← implementaciones concretas de los puertos
  ├── adapters/      ← Outlook COM, CSV, etc.
  ├── repositories/  ← Airtable, Supabase, Notion, CSV
  ├── services/      ← logging, html_email_builder, html_preview_service, send_tracker
  └── providers/     ← proveedores externos
html/                ← plantillas HTML, templates, assets (logos, imágenes)
Templates/           ← plantillas de correo (EML/MSG fuente)
web/                 ← app FastAPI de preview
main.py              ← entrypoint que arma el staging JSON
outlook_send.py      ← envío real (standalone, sin imports del proyecto)
preview.py           ← previsualización local
import_email_template.py ← parser EML/MSG
send_from_staging.py ← helper de staging
```

### Convenciones

- Nombres de archivo: `snake_case.py`. Tests: `test_<archivo>.py` (en `test/`
  o `tests/`).
- Módulos que solo corren en Windows o solo tocan COM/red/IO se identifican
  por su contexto (no hay sufijo `.server.py` como en TypeScript — la
  restricción es que `outlook_send.py` no importa del proyecto).
- Sin valores hardcodeados en UI web: usar plantillas de `web/templates/` y
  configuración vía `.env`.
- `outlook_send.py` es el único archivo que cruza la barrera WSL→Windows.

### Dónde NO hay red de seguridad

`pyproject.toml` configura pytest para incluir `testpaths = ["."]`, pero **la
suite es desigual**: `tests/` tiene tests más maduros, `test/` tiene tests más
recientes. `web/` no tiene tests automatizados (la UI de preview se valida
manualmente).

Consecuencia práctica: **un cambio puede romper la UI web y `uv run pytest`
sale en verde.** Cuando el trabajo toca `web/`, hay que decirlo explícitamente
en el reporte y dejar la verificación visual al usuario.

## Secretos

`.env` contiene credenciales de Airtable y cualquier otro proveedor. Está
excluido de git vía `.gitignore`. Documentar nombres de variables en
`.env.example`, nunca valores.

Las claves que ya están en commits antiguos siguen en el historial: la vía
correcta si importan es **rotarlas**, no borrarlas.

## Sistema de agentes

El **Coordinador es la sesión principal**, no un subagente: es el único que
puede pararse a pedirte aprobación y el único que puede delegar en paralelo.
Su rol está definido en [`.claude/agents/coordinador.md`](.claude/agents/coordinador.md).

El Coordinador **es el product owner**: clasifica, planifica, obtiene
aprobación y delega, pero no codifica. Sabe del negocio y tiene el concepto,
el motivo y la finalidad de la aplicación. Es el capitán del barco.

Los subagentes están definidos en `.claude/agents/` y documentados en
[`.claude/agents/TEAM.md`](.claude/agents/TEAM.md):

| Agente         | Modelo | Responsabilidad                                                                       |
| -------------- | ------ | ------------------------------------------------------------------------------------- |
| `planificador` | opus   | Spec → tareas atómicas con archivos exclusivos y olas sin solape                      |
| `diseñador-web`| sonnet | UI/UX, plantillas HTML para correos, design system, accesibilidad                     |
| `desarrollador`| sonnet | Implementar en el repo. **Único que escribe código de producción**                    |
| `tester`       | sonnet | Diseñar y ejecutar pruebas con pytest contra la spec                                  |
| `revisor`      | opus   | Tests debilitados primero, luego corrección, convenciones y restricciones de plataforma. **Sin `Write` ni `Edit`** |

Reglas clave del equipo: plan aprobado antes de ejecutar, spec de diseño antes
que código cuando hay UI nueva, QA obligatorio antes de dar algo por listo, y
cada agente es la única fuente de verdad de su área — no se "simplifica" una
spec ajena por cuenta propia.

**Ningún subagente lleva la herramienta `Agent`**: solo la sesión principal
delega. `planificador` y `diseñador-web` escriben documentos, no código, y un
hook `PreToolUse` los bloquea si lo intentan.

Los **agent teams experimentales se dejan apagados**: con ellos activos un
subagente con nombre arranca como compañero de equipo y no devuelve su
resultado, solo notifica que terminó, lo que rompe este ciclo.

Para entender el sistema completo: [`AGENTS_SYSTEM.md`](AGENTS_SYSTEM.md).
Para deshacerlo: ver `AGENTS_SYSTEM.md` sección "Setup inicial".

## Archivos clave

| Archivo                                    | Propósito                                                              |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `CLAUDE.md`                                | Este documento (fundacional del proyecto)                              |
| `AGENTS_SYSTEM.md`                         | Sistema de agentes (guía completa)                                     |
| `README.md`                                | Documentación general                                                  |
| `SPEC.md`                                  | Índice de ciclos activos                                               |
| `.claude/agents/coordinador.md`            | Rol del Coordinador (orquestador)                                      |
| `.claude/agents/TEAM.md`                   | Cómo colaboran los agentes                                             |
| `.claude/verificacion.json`                | Comandos de calidad por perfil                                         |
| `.claude/linea-base.json`                  | Línea base de errores heredados (cuando se agregue ruff)               |
| `pyproject.toml`                           | Dependencias + configuración de pytest                                 |
| `html/templates/subject.txt`               | Asunto por defecto del envío                                           |
