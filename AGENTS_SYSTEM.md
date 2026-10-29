# Sistema de Agentes Autónomos — outlook-masive_emails

Este documento es **auto-contenido**: al entregárselo a un AI en un proyecto
nuevo, el AI tiene todo lo necesario para entender el sistema de agentes de
este proyecto. No requiere contexto previo.

---

## Qué es este sistema

Un sistema de **6 roles** que trabajan en olas sucesivas bajo un **Coordinador**
(sesión principal). Cada rol tiene herramientas restringidas, criterios de
aceptación objetivos (comandos), y una puerta de calidad automatizada que nadie
puede falsificar.

**El problema que resuelve**: un agente que se autoevalúa siempre se aprueba.
Este sistema introduce verificadores objetivos (comandos) y separación de roles
para que el trabajo sea comprobable, no opinable.

---

## Arquitectura de roles

```
Usuario → Coordinador (sesión principal)
              ↓
          ┌──────────────┐
          │ planificador │ → genera planes con tareas atómicas y olas sin solape
          └──────┬───────┘
                 ↓
          ┌──────────────┐
          │ disenador-web│ → specs de UI/UX, plantillas HTML (si hay UI nueva)
          └──────┬───────┘
                 ↓
     ┌───────────┴───────────┐
     ↓                       ↓
┌─────────────┐ ┌─────────────┐   en paralelo
│desarrollador│ │desarrollador│   archivos disjuntos
└──────┬──────┘ └──────┬──────┘
       └───────┬───────┘
               ↓
         ┌─────────┐
         │ tester  │ → pruebas contra la spec
         └────┬────┘
              ↓
         ┌─────────┐
         │ revisor │ → busca tests debilitados + mutación
         └────┬────┘
              ↓
   puerta COMPLETA → siguiente ola
```

---

## El flujo de producción real

El repo tiene capa hexagonal (`domain/`, `ports/`, `application/`,
`infrastructure/`), pero **la capa hexagonal NO es el camino de envío**. El
envío real es este:

```
import_email_template.py → html/templates/body_html.html + html/images/body/*.png
    ↓
main.py   (o web/app.py, vía POST /api/send)  → staging/emails_to_send.json
    ↓
send_from_staging.py   (Python de Windows)     → Outlook COM
```

Qué se usa en producción y qué no (verificado con `grep` sobre todos los
`.py`):

| Módulo | ¿En el camino de producción? |
| ------ | ---------------------------- |
| `domain/entities.py`, `domain/types.py` | Sí (`main.py`, `web/app.py`, repositorios) |
| `infrastructure/repositories/*` | Sí (`main.py`, `web/app.py`) |
| `infrastructure/services/*` | Sí (`main.py`, `preview.py`, `web/app.py`) |
| `ports/*` | Solo a través de `application/` |
| `application/send_emails.py` | **No**: lo importan solo `test/test_architecture.py` y `test/test_preview_flow.py` |
| `infrastructure/adapters/outlook_desktop_adapter.py` | **No**: lo importa solo `test/test_outlook_adapter.py` |

Consecuencia práctica: un cambio en `application/` o en el adaptador de
Outlook **no altera el envío real**. El envío lo hace `send_from_staging.py`,
que es standalone y no importa nada del proyecto.

---

## Archivos del sistema

El sistema vive en `.claude/`. Estructura:

```
.claude/
├── agents/
│   ├── coordinador.md          # Rol del Coordinador (documentado; NO es un subagente)
│   ├── planificador.md         # Spec → tareas atómicas
│   ├── disenador-web.md        # UI/UX, plantillas HTML
│   ├── desarrollador.md         # Implementación en el repo (único que escribe código)
│   ├── tester.md               # Pruebas con pytest
│   ├── revisor.md              # Tests debilitados + prueba de mutación
│   └── TEAM.md                 # Este archivo resumido
├── hooks/
│   ├── puerta-calidad.mjs      # Puerta de calidad (SubagentStop, en settings.json)
│   ├── guardian-config.mjs     # Impide reescribir la config de la puerta (settings.json)
│   ├── guardian-escritura.mjs  # Bloquea escritura fuera de las rutas permitidas (frontmatter)
│   ├── guardian-bash.mjs       # Bloquea la fuga por Bash (frontmatter)
│   ├── validar-plan.mjs        # Valida el schema de los planes .json (frontmatter)
│   ├── permitidas.mjs          # Allowlist de rutas + protocolo de denegación (compartido)
│   ├── checkpoint.mjs          # Git tags para rollback (CLI manual)
│   ├── drift-detection.mjs     # Verifica APIs citadas existen (CLI manual)
│   └── linea-base.mjs          # Línea base de errores heredados (CLI manual)
├── planes/                     # Plan .json + plan .md de cada ciclo
├── cache/                      # Estado de bloqueos, caché de lint
├── worktrees/                  # Copias de trabajo aisladas (Agent Teams)
├── settings.json               # Hooks registrados del proyecto
├── settings.local.json         # Permisos locales del sandbox
├── verificacion.json           # Comandos de calidad por perfil
└── linea-base.json             # Errores heredados por archivo (generado por el script)
```

`coordinador.md` **no tiene frontmatter YAML**: documenta el rol del
Coordinador, que se aplica a la **sesión principal** (ver «El
Coordinador»).

Los hooks se registran en **dos sitios distintos**, y por eso están separados:

- En `.claude/settings.json`: los que aplican a cualquier subagente del
  proyecto (`puerta-calidad.mjs`, `guardian-config.mjs`).
- En el **frontmatter** del agente: los que solo aplican mientras ese agente
  está activo (`guardian-escritura.mjs`, `guardian-bash.mjs`,
  `validar-plan.mjs`).

En la raíz:
- `CLAUDE.md` — documento fundacional del proyecto (qué es, flujo principal, stack, restricciones).
- `SPEC.md` — índice de ciclos activos.
- `AGENTS_SYSTEM.md` — este documento (guía completa).
- `README.md` — documentación general del proyecto.

---

## El Coordinador

El Coordinador es la **sesión principal**, no un subagente. Su rol está
definido en `.claude/agents/coordinador.md`. Es el único que puede pedir
aprobación al usuario y el único que puede delegar en paralelo.

`coordinador.md` no lleva frontmatter YAML a propósito: al no registrarlo como
agente, no aparece en la lista de agentes disponibles y no se puede lanzar
como subagente.

### Fases del ciclo

**Fase 0 — Precomprobación**
```sh
git status --porcelain
node .claude/hooks/puerta-calidad.mjs completa
```
- Si hay cambios sin commitear → parar
- Si la puerta falla → parar (el repo ya está roto)
- Si falta la spec o no hay ciclo activo → preguntar al usuario

**Fase 1 — Plan**
- Delegar en `planificador`
- Verificar el plan: solapes, APIs existentes, criterios con comando
- 🛑 Parada: usuario aprueba el plan

**Fase 2 — Diseño** (solo si hay UI)
- Delegar en `disenador-web`
- 🛑 Parada: usuario aprueba el diseño

**Fase 3 — Ejecución por olas**

Para cada ola:
1. Verificar checkpoint existe
2. Lanzar desarrolladores en paralelo
3. Delegar en `tester`
4. Delegar en `revisor`
5. Puerta completa
6. Si falla: rollback o devolver al agente

**Fase 4 — Cierre**
- Puerta completa final
- 🛑 Parada: mostrar resultado al usuario
- **No commitees** hasta que el usuario lo pida

### Niveles de autonomía (referenciados, no implementados)

`coordinador.md` describe una clave `autonomia` con esta forma:

```json
"autonomia": {
  "replanificar": "aprobacion",
  "agregar_tarea": "aprobacion",
  "cambiar_criterio": "aprobacion",
  "crear_checkpoint": "automatico",
  "continuar_sin_commit": "aprobacion"
}
```

`automatico` = el Coordinador actúa sin preguntar. `aprobacion` = pide al
usuario.

**Hoy esa clave NO existe en `.claude/settings.json`**: el fichero solo
contiene `hooks`. La autonomía real se aplica con las paradas 🛑 del prompt y
con el hook `SubagentStop`. Si se implementa la clave, hay que añadirla al
`settings.json` de verdad.

---

## Los 6 roles

### 1. Coordinador (sesión principal)

**Responsabilidad**: clasificar solicitudes, planificar el ciclo, obtener
aprobación, delegar, desbloquear.

**Archivo**: `.claude/agents/coordinador.md`

**No escribe código de producción.** No toma decisiones de diseño.

### 2. Planificador (modelo: opus)

**Responsabilidad**: descomponer una spec en tareas atómicas con archivos
exclusivos y olas sin solape.

**Archivo**: `.claude/agents/planificador.md`

**Herramientas**: Read, Grep, Glob, Bash, Write
**Bloqueo**: hook `guardian-escritura.mjs` (y `guardian-bash.mjs`) que impiden
escribir fuera de `.claude/planes/`, `.claude/disenos/`, `.claude/cache/`,
`docs/`, `SPEC.md`

**Proceso**:
1. Leer SPEC.md y verificar cada símbolo/ruta con grep
2. Listar archivos reales a tocar
3. Cortar en tareas atómicas (archivos disjuntos, criterio verificable con comando)
4. Agrupar en olas (intersección vacía entre tareas de la misma ola)
5. Verificar solapes con script
6. Generar `.claude/planes/<nombre>.json` + `.claude/planes/<nombre>.md`

**Regla clave**: un dato de la spec es una hipótesis. Verificar con grep
antes de planificar.

### 3. Diseñador Web (modelo: sonnet)

**Responsabilidad**: UI/UX, design system, especificaciones de interacción y
accesibilidad. Plantillas HTML para correos.

**Archivo**: `.claude/agents/disenador-web.md`

**Herramientas**: Read, Write, Edit, WebSearch, WebFetch, Bash
**Bloqueo**: hooks `guardian-escritura.mjs` y `guardian-bash.mjs` que impiden
escribir fuera de `.claude/planes/`, `.claude/disenos/`, `.claude/cache/`,
`docs/`, `SPEC.md`

**Entregable**: `.claude/disenos/<pantalla>.md`

**Contenido obligatorio de la spec**:
- Flujo (usuario llega → acción → éxito/falla)
- Componentes a reutilizar (o plantillas existentes en `Templates/`/`html/`)
- Estados diseñados (default, hover, focus, loading, error, empty, job en progreso)
- Tokens introducidos (si hay nuevos)
- Accesibilidad (orden de foco, screen reader, contraste)

**Regla clave para correos HTML**:
- CSS inline siempre (los clientes de correo no respetan `<style>`)
- Evitar `data:` URIs en imágenes — usar referencias `cid:image_N`
- Tablas para layout cuando sea necesario por compatibilidad con Outlook
- Charset UTF-8 siempre

**Regla clave**: no escribir código. Describir y que el desarrollador implemente.

### 4. Desarrollador (modelo: sonnet)

**Responsabilidad**: implementación. **Único que escribe código de producción.**

**Archivo**: `.claude/agents/desarrollador.md`

**Herramientas**: Read, Write, Edit, Bash, Glob, Grep

**Proceso**:
1. Leer spec/plan completo
2. Verificar que las APIs citadas existen
3. Implementar en la capa que corresponda: `domain/` (puro), `ports/`
   (interfaces), `infrastructure/` (adaptadores, repositorios, servicios) y
   los entrypoints (`main.py`, `import_email_template.py`, `web/app.py`,
   `send_from_staging.py`)
4. Verificar con `uv run --no-sync pytest` (y la regresión de lint con
   `node .claude/hooks/linea-base.mjs verificar`)
5. Reportar con salida literal de los comandos

**Reglas duras del proyecto**:
- `send_from_staging.py` debe permanecer standalone (sin imports del proyecto)
- Paths siempre absolutos con `Path(__file__).resolve().parent`
- Filtrar archivos `.Identifier` al listar imágenes en WSL
- El HTML para correos usa `{images[N]}` como placeholders que se reemplazan
  con `cid:image_N`
- Subject se lee de `html/templates/subject.txt`, nunca hardcodeado
- Arquitectura hexagonal: dependencias hacia adentro

**Reglas duras generales**:
- Archivos exclusivos: no tocar nada fuera de los asignados
- No reinterpretar la spec: si es ambiguo, preguntar
- No debilitar tests para pasar
- No tocar la configuración para silenciar errores

**Entregable**: reporte con `git diff --stat`, salida literal de
`uv run --no-sync pytest` (y lint/typecheck si aplica).

### 5. Tester (modelo: sonnet)

**Responsabilidad**: QA, diseño y ejecución de pruebas contra la spec.

**Archivo**: `.claude/agents/tester.md`

**Herramientas**: Read, Write, Edit, Bash, Glob, Grep

**Proceso**:
1. Leer spec y criterios del plan
2. Verificar que la implementación cumple la spec
3. Escribir tests faltantes en `tests/` o `test/`
4. Ejecutar suite completa con `uv run --no-sync pytest`
5. Emitir APROBADO o RECHAZADO

**Reglas duras**:
- No aprobar desviaciones de spec aunque "funcione técnicamente"
- Los casos de prueba salen de la spec, no del código (excepto en refactors)
- No debilitar tests
- Los bugs encontrados se reportan, no se arreglan en la misma tarea

**Severidad**:
- Crítica/Alta → RECHAZADO automático
- Media/Baja → criterio del Coordinador

**Estrategia de testing para este proyecto**:
```
Unit tests       → funciones puras (parsers EML, builders, reemplazos de template)
Integration      → carga de contactos desde Airtable (con credenciales de test)
E2E (staging)    → uv run main.py → verifica emails_to_send.json generado correctamente
E2E (send)       → send_from_staging.py con mock de win32com (sin enviar correos reales)
```

Las suites viven en `tests/` (reciente, 2026-09-25) y `test/` (legacy,
2026-07-17). `tests/` es la que crece; `test/` conserva los tests de la capa
hexagonal. `web/` **sí** tiene tests automatizados (`tests/conftest.py`,
`tests/test_send_payload.py`, `tests/test_upload_eml.py`,
`tests/test_regression_cross_contamination.py` importan `web.app`); lo que no
tiene cobertura automatizada es el **render visual** de la UI.

### 6. Revisor (modelo: opus)

**Responsabilidad**: filtrado final. Busca tests debilitados, mide calidad
con mutación.

**Archivo**: `.claude/agents/revisor.md`

**Herramientas**: Read, Grep, Glob, Bash (NO Write, NO Edit)

**Proceso (en orden)**:
1. **Tests debilitados** (antes que nada)
   - Buscar aserciones eliminadas, `@pytest.skip`/`xfail` añadidos, timeouts subidos
   - Si encuentra → defecto crítico
2. **Prueba de mutación** sobre copia aislada
   - Trabajar en `/tmp`, nunca en el original
   - 15-30 mutaciones variadas sobre el código de la ola
   - Clasificar supervivientes: dentro o fuera del alcance
3. **Corrección** contra spec y plan
4. **Convenciones** con grep (domain sin I/O, `send_from_staging.py` standalone, etc.)
5. **Restricciones de plataforma** (las 5 listadas en desarrollador/revisor)
6. **Seguridad** (secrets en logs, validación de inputs antes de enviar)

**Regla clave**: solo reporta, no arregla. No lleva `Write` ni `Edit`, así que
no puede tocar ficheros por la vía directa — **pero sí lleva `Bash`**, que
permitiría escribir igual (`sed -i`, redirecciones, `python -c`). Ese hueco
lo cierra el hook `guardian-bash.mjs`, declarado también en su frontmatter:
le **deniega** los comandos con semántica de escritura cuando apuntan al
repo, y solo le deja escribir en `/tmp` (la copia aislada de la mutación).
Su independencia es, por tanto, **técnica**, no solo de convención.

---

## La puerta de calidad

Hook `SubagentStop` registrado en `.claude/settings.json` (fichero real, tal
como está hoy):

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "desarrollador|tester",
        "hooks": [
          {
            "type": "command",
            "command": "node \"${CLAUDE_PROJECT_DIR:-$PWD}\"/.claude/hooks/puerta-calidad.mjs rapida",
            "timeout": 900,
            "statusMessage": "Puerta de calidad: ejecutando las comprobaciones…"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "node \"${CLAUDE_PROJECT_DIR:-$PWD}\"/.claude/hooks/guardian-config.mjs",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Dos eventos, dos hooks:

| Evento | Matcher | Hook | Qué hace |
| ------ | ------- | ---- | -------- |
| `SubagentStop` | `desarrollador\|tester` | `puerta-calidad.mjs rapida` | Ejecuta los comandos del perfil `rapida` y bloquea si fallan |
| `PreToolUse` | `Write\|Edit\|MultiEdit\|NotebookEdit` | `guardian-config.mjs` | Impide que un agente vigilado reescriba la configuración de la puerta (`.claude/hooks/`, `.claude/agents/`, `.claude/verificacion.json`, `.claude/linea-base.json`, `.claude/settings.json`, `.claude/settings.local.json`) |

`.claude/agents/` está protegida a propósito: los hooks de cada rol se
registran en **su propio** frontmatter, así que un agente vigilado que
pudiera reescribir `.claude/agents/` podría quitarse a sí mismo el `hooks:` que
lo protege y desarmar la puerta. La sesión principal (Coordinador) no está
restringida y sigue pudiendo corregir los prompts de los roles.

**La puerta juzga el árbol en el que se trabaja.** El evento `SubagentStop`
trae `cwd` («current working directory when the hook is invoked»; si Claude
entra en un worktree, es la raíz del worktree). La puerta lo usa como raíz de
trabajo cuando contiene su propio `.claude/verificacion.json` —es decir,
cuando es un checkout— y el checkout principal en cualquier otro caso. Sin
esto, un agente que trabaja en un worktree aislado sería juzgado contra el
checkout principal, que no contiene sus cambios: la puerta le aprobaría todo.

**Perfiles (en `.claude/verificacion.json`)** — el hook no conoce ningún
comando concreto: los lee de ahí. Ese fichero es la fuente de verdad.

| Perfil | Cuándo corre | Comprobaciones |
| ------ | ------------ | -------------- |
| `rapida` | En cada `SubagentStop` de `desarrollador` y `tester` | `tests` (`uv run --no-sync pytest`), `lint` (`node .claude/hooks/linea-base.mjs verificar`), `tipos` (`uv run --no-sync mypy .`) |
| `completa` | A mano, el Coordinador, al cerrar cada ola | las tres de `rapida` + `drift` (`node .claude/hooks/drift-detection.mjs verificar`) |

`completa` **no** se registra como hook: su presupuesto de timeouts no cabe en
los 900 s del evento `SubagentStop`.

**Semántica de `obligatorio`** (no significa «opcional»):

- `true` + comprobación **no ejecutable** (herramienta ausente) → **FALLA** y
  bloquea, con motivo accionable. Un obligatorio saltado en silencio es el
  fail-open que hay que cerrar.
- `false` + comprobación no ejecutable → **SALTADO**, no bloquea.
- Herramienta presente + comando fallando → **FALLA** y bloquea, **siempre**.

La disponibilidad de la herramienta nunca suaviza el resultado.

**Comportamiento**:
- Si la puerta falla → **bloquea al subagente**: el hook sale con **código 2**
  y el motivo va por `stderr`. El subagente no puede declararse terminado.
- Anti-bucle: tras `maxBloqueosPorAgente` (3) bloqueos del mismo `agent_id`,
  deja pasar para que el fallo escale al Coordinador. La invocación manual
  (sin `agent_id`) siempre bloquea: ahí el bloqueo lo pidió un humano.
- Fail-closed por tipo de agente: si el evento dice quién es y ese rol no
  está en `agentesVigilados`, la puerta no comprueba nada (no es trabajo suyo).
  Si el evento **no** trae `agent_type`, se ejecutan **todas** las
  comprobaciones: nunca se sale en silencio por no saber quién eres.
- La puerta ejecuta los comandos, no el agente → no puede mentir.

**Trampa conocida — workspace trust**: los hooks de proyecto **NO se ejecutan**
si la carpeta no es confiable en Claude Code. Sin trust, la puerta no bloquea
y todo parece ir bien. Antes de fiarse de un «pasó», comprobar el trust.

**Sobre `uv sync`**: `uv sync` a secas **desinstala pytest** en este repo
(poda el grupo `test`). Para instalar sin romper nada: `uv sync --all-groups`.
Los comandos de la puerta usan `uv run --no-sync` justamente para no mutar el
entorno del proyecto.

**Nota sobre este proyecto**: `ruff` ya está en `pyproject.toml`
(`ruff>=0.17.3`, grupo `dev`); `mypy` no. La comprobación `lint` no es un
`ruff check` crudo: mide la **regresión contra la línea base congelada**
(`.claude/linea-base.json`) con `linea-base.mjs verificar`. Esa línea base
solo la regenera el usuario, y solo a la baja.

---

## Hooks del sistema

Los hooks se registran en **dos sitios**, y por eso están separados:

| Dónde | Qué se registra | Por qué |
| ----- | ---------------- | ------- |
| `.claude/settings.json` | `puerta-calidad.mjs` (`SubagentStop`), `guardian-config.mjs` (`PreToolUse`) | Aplican a **cualquier** subagente del proyecto, esté o no activo su agente |
| Frontmatter del agente | `guardian-escritura.mjs`, `guardian-bash.mjs`, `validar-plan.mjs` | Aplican **solo mientras ese agente está activo**, y solo a sus capacidades |

`checkpoint.mjs`, `drift-detection.mjs` y `linea-base.mjs` **no son hooks**: son
CLI que el Coordinador invoca a mano.

### guardian-escritura.mjs

Bloquea Write/Edit en agentes que no deben escribir código. Se declara en el
frontmatter del agente:

```yaml
---
hooks:
  PreToolUse:
    - matcher: "Write|Edit|MultiEdit|NotebookEdit"
      hooks:
        - type: command
          command: 'node "${CLAUDE_PROJECT_DIR:-$PWD}"/.claude/hooks/guardian-escritura.mjs'
          timeout: 10
---
```

**Rutas permitidas** (definidas en `.claude/hooks/permitidas.mjs`, que es la
allowlist compartida):
- `.claude/planes/`
- `.claude/disenos/`
- `.claude/cache/`
- `docs/`
- `SPEC.md` (exacto)

### guardian-bash.mjs

Cierra la fuga que `guardian-escritura.mjs` deja abierta: `Write` no es la
única forma de escribir en disco. Se declara en el frontmatter de **los cinco
roles**, con matcher `Bash`:

```yaml
    - matcher: "Bash"
      hooks:
        - type: command
          command: 'node "${CLAUDE_PROJECT_DIR:-$PWD}"/.claude/hooks/guardian-bash.mjs'
          timeout: 10
```

El hook tiene **dos modos**, según el rol del evento. El modo se decide con
`agent_type` contra la lista `agentesVigilados` de `.claude/verificacion.json`
(`desarrollador`, `tester`); si falta `agent_type`, cae al modo restrictivo.

| Modo | Roles | Regla |
|---|---|---|
| **documentos** | `planificador`, `disenador-web`, `revisor` | Allowlist estricta: solo se permite escribir en `.claude/planes/`, `.claude/disenos/`, `.claude/cache/`, `docs/` y `SPEC.md`. |
| **vigilado** | `desarrollador`, `tester` | Escriben código de producción, así que sus comandos de Bash son legítimos: se les niegan **las rutas de la configuración de la puerta** (`.claude/hooks/`, `.claude/verificacion.json`, `.claude/linea-base.json`, los `settings.json`) y los comandos que destruyen el árbol o el entorno. |

Analiza el comando y **deniega** las escrituras prohibidas: redirecciones
(`echo x > domain/entities.py`), `sed -i`, `rm -rf`, `git reset --hard`,
`git clean`, `uv add`/`sync`/`lock`, `writeFileSync` embebido… Ante la duda
permite: un falso positivo manda al agente a un rodeo, un falso negativo lo
deja escribir.

> **Por qué el rol vigilado tiene su propio modo:** `guardian-config.mjs` solo
> cubre `Write`/`Edit`/`NotebookEdit`. Sin este modo, `desarrollador` y
> `tester` —los dos roles vigilados por la puerta— podían reescribir por Bash
> la configuración que los juzga (`echo x > .claude/hooks/puerta-calidad.mjs`
> pasaba limpio). Ese hueco era el hallazgo **D4** de la auditoría.
>
> **Lo que el rol vigilado sigue sin poder hacer:** mutar el entorno
> (`uv sync`, `uv add`, `uv remove`, `uv lock`). El entorno lo prepara el
> usuario con `uv sync --all-groups`; `uv sync` a secas **poda el grupo
> `test`** de este repo y desinstala pytest.

### guardian-config.mjs

Vive en `.claude/settings.json` (evento `PreToolUse`), no en el frontmatter:
aplica a todos los subagentes, pero **solo** restringe a los que están en
`agentesVigilados` (`desarrollador`, `tester`).

Impide que un agente vigilado reescriba la configuración de la puerta que lo
juzga. Rutas protegidas:

- `.claude/hooks/`
- `.claude/verificacion.json`
- `.claude/linea-base.json`
- `.claude/settings.json`
- `.claude/settings.local.json`

`.claude/agents/` **no** está protegido a propósito: en una ola posterior hay
que poder corregir la documentación de los agentes, incluidos sus hooks
declarados.

### validar-plan.mjs

Valida el **schema** de los planes JSON. Se declara en el frontmatter del
`planificador` con matcher `Write` (solo aplica a `.claude/planes/*.json`;
un `.md` no se valida). Sin esto, el schema estaba documentado pero nadie lo
comprobaba.

### checkpoint.mjs

Git tags para rollback antes de cada ola. **CLI manual**, no es un hook.

```sh
# Crear checkpoint antes de una ola
node .claude/hooks/checkpoint.mjs crear ola-ciclo-1-ola-1

# Restaurar (rollback) si algo sale mal
node .claude/hooks/checkpoint.mjs restaurar ola-ciclo-1-ola-1

# Listar checkpoints
node .claude/hooks/checkpoint.mjs listar

# Estado del árbol y de los checkpoints
node .claude/hooks/checkpoint.mjs estado
```

### drift-detection.mjs

Verifica que las APIs citadas en un plan existen en el código. **CLI manual**,
no es un hook.

```sh
# Verificar un plan específico
node .claude/hooks/drift-detection.mjs .claude/planes/mi-plan.json

# Verificar todos los planes
node .claude/hooks/drift-detection.mjs verificar

# Revisión heurística
node .claude/hooks/drift-detection.mjs heuristico
```

### linea-base.mjs

Gestiona la línea base de errores heredados. **CLI manual**, no es un hook.

```sh
# Verificar que no se agregaron errores
node .claude/hooks/linea-base.mjs verificar

# Regenerar línea base (solo usuario, solo a la baja)
node .claude/hooks/linea-base.mjs generar
```

---

## Configuración de verificación

### verificacion.json

Este archivo es la **única** configuración que cambia cuando se cambia de
stack. El hook `puerta-calidad.mjs` no conoce ningún comando concreto: los lee
de aquí.

**Estructura**:
```json
{
  "perfiles": {
    "rapida": [
      { "etiqueta": "tests", "comando": "uv run --no-sync pytest", "obligatorio": true },
      { "etiqueta": "lint", "comando": "node .claude/hooks/linea-base.mjs verificar", "obligatorio": false },
      { "etiqueta": "tipos", "comando": "uv run --no-sync mypy .", "obligatorio": false }
    ],
    "completa": [
      { "etiqueta": "tests", "comando": "uv run --no-sync pytest", "obligatorio": true },
      { "etiqueta": "lint", "comando": "node .claude/hooks/linea-base.mjs verificar", "obligatorio": false },
      { "etiqueta": "tipos", "comando": "uv run --no-sync mypy .", "obligatorio": false },
      { "etiqueta": "drift", "comando": "node .claude/hooks/drift-detection.mjs verificar", "obligatorio": false }
    ]
  },
  "agentesVigilados": ["desarrollador", "tester"],
  "maxBloqueosPorAgente": 3,
  "timeoutPorComandoMs": 300000,
  "timeouts": {
    "tests": 300000,
    "lint": 120000,
    "tipos": 120000,
    "linea-base": 120000,
    "drift": 120000,
    "cobertura": 600000
  }
}
```

Códigos de salida de los comandos: `0` = pasa · `1` = falla · `2` = error de
ejecución · `3` = no aplica (convención compartida con `linea-base.mjs` y
`drift-detection.mjs`).

Para adaptar a otro proyecto:
1. Cambiar los comandos en `perfiles`
2. Ajustar `agentesVigilados` según qué agentes escriben código
3. Ajustar `timeouts` según el tamaño del proyecto
4. Usar `uv run --no-sync`: la puerta **nunca** debe mutar el entorno del
   proyecto

### linea-base.json

```json
{
  "_comentario": "Errores de lint heredados POR ARCHIVO...",
  "generado": "2025-09-25T00:00:00.000Z",
  "comando": "uv run ruff check . -f json -o .claude/cache/eslint-informe.json",
  "totalErrores": 0,
  "archivos": {}
}
```

Cada archivo tiene un presupuesto de errores de lint; un archivo **ausente**
tiene presupuesto **cero**. Hoy `archivos` está **vacío**: cualquier error de
ruff en el repo es una regresión y `linea-base.mjs verificar` sale con `1`.

El hook es **fail-closed a propósito**: si la línea base no existe, sale con
`1` y lo dice («Esto NO es un «todo bien»»), no con `3`. Borrar la línea base
no puede hacer que la comprobación pase. La única forma de que `lint` no
bloquee es tener la base sembrada **y** no haber empeorado el repo.

Se genera ejecutando `node .claude/hooks/linea-base.mjs generar` — **solo el
usuario, y solo a la baja**. Regenerarla para tapar un error está prohibido.

---

## Convenciones del proyecto

Estas convenciones están adaptadas al proyecto específico:

| Convención                                                       | Evidencia                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------ |
| `domain/` es lógica pura, sin I/O                               | `domain/entities.py`, `domain/types.py`                      |
| Arquitectura hexagonal: domain ← ports ← application ← infrastructure | Estructura del repo (pero **no** es el camino de envío: ver «El flujo de producción real») |
| `send_from_staging.py` standalone (sin imports del proyecto)     | Restricción de plataforma para evitar cache de `.pyc` Windows |
| Paths absolutos con `Path(__file__).resolve().parent`           | `import_email_template.py`, `main.py`                        |
| Filtrar archivos `.Identifier` al listar imágenes               | Restricción WSL/Windows                                      |
| HTML usa `{images[N]}` → `cid:image_N`                          | `infrastructure/services/html_email_builder.py` (el `{images[N]}` lo escribe `import_email_template.py`) |
| Subject desde `html/templates/subject.txt`                      | `main.py`                                                    |
| Tests en `test/` y `tests/` (las dos suites coexisten)          | `pyproject.toml [tool.pytest.ini_options]`                   |
| Contactos desde Airtable REST API                               | `infrastructure/repositories/airtable_contact_repository.py` |
| Imágenes inline embebidas vía Outlook COM con MAPI properties   | `send_from_staging.py` (el adaptador `infrastructure/adapters/outlook_desktop_adapter.py` solo lo usan los tests) |

---

## Anti-patrones (errores comunes)

1. **Un agente se autoevalúa.** → Solo la puerta de calidad verifica.
2. **Dos agentes tocan el mismo archivo en la misma ola.** → El plan debe
   verificar solapes por comando.
3. **Un agente "simplifica" la spec.** → Eso es un defecto, no una
   optimización.
4. **Tests que no cazan bugs.** → Mutación revela esto.
5. **La puerta se salta porque "ya sabemos que pasa".** → La puerta es la
   única verdad.
6. **Decisiones que no se documentan.** → Van al entregable del ciclo y a
   `SPEC.md` (no hay un registro de decisiones aparte en este repo).
7. **Scope creep.** → El agente reporta trabajo extra, no lo expande en
   silencio.
8. **`send_from_staging.py` con imports del proyecto.** → Rompe la restricción
   de standalone. Defecto crítico.
9. **Subject hardcodeado en código.** → Debe leerse de
   `html/templates/subject.txt`.
10. **Listar imágenes sin filtrar `.Identifier`.** → En WSL aparecen
    archivos espurios que rompen el envío.

---

## Plantilla de Agent Prompts

### Planificador

```markdown
# Planificador

Convertís una especificación en un plan que otros agentes pueden ejecutar en
paralelo sin pisarse. **No escribís código.** Tu única salida es un documento
en `.claude/planes/`.

## Regla número uno: verificá lo que recibís

Un dato de la spec es una hipótesis. Antes de escribir una tarea:
- Cada símbolo, ruta, función que la spec menciona → comprobalo con grep
- Cada recuento → contalo vos
- Si la spec contradice el código, gana el código

## Proceso

1. Leer SPEC.md entero y verificar con grep
2. Listar archivos reales a tocar
3. Cortar en tareas atómicas (archivos disjuntos + criterio con comando)
4. Agrupar en olas (intersección vacía)
5. Criterios de aceptación: cada uno con comando que sale código 0
6. Verificar solapes antes de entregar

## Reglas duras

- **No escribís código.** Hook te bloquea.
- **No inventás APIs.** Todo símbolo citado, verificado con grep.
- **No agrupás por comodidad.** Si dudás, olas separadas.
- **No decidas vos si el plan se ejecuta.** Lo entregás y el Coordinador
  lo lleva al usuario.

## Formato de entrega

Dos archivos:
1. `.claude/planes/<nombre>.json` — legible por máquina
2. `.claude/planes/<nombre>.md` — explicación para el usuario
```

### Desarrollador

```markdown
# Desarrollador

Implementás features siguiendo la spec de diseño y la arquitectura del
proyecto. **Único que escribís código de producción.**

## Regla número uno: verificá lo que recibís

- Todo símbolo, ruta, función de la tarea → comprobalo con grep
- Si no existe, pará y decilo. No construyas sobre aire.
- Si la tarea contradice el código, gana el código

## Archivos exclusivos

Tu tarea tiene una lista de archivos que son tuyos. **No toques ningún otro.**
Si necesitás uno que no está, pará y decilo.

## Stack del proyecto

Python 3.13+ con uv, arquitectura hexagonal, Outlook COM vía Windows Python
para el envío, Airtable como fuente de contactos, imágenes inline con
`cid:image_N`.

## Workflow

1. Leer spec/plan completo
2. Verificar que las APIs citadas existen
3. Implementar respetando la arquitectura hexagonal
4. Verificar: uv run --no-sync pytest
5. Reportar con salida literal

## Reglas duras

- No reinterpretar la spec: si es ambiguo, preguntar
- No debilitar tests para pasar
- No tocar la configuración para silenciar errores
- `send_from_staging.py` permanece standalone
- Archivos exclusivos: no tocar nada fuera de los asignados

## Checklist de entrega

```markdown
## Implementación: [Nombre]

### Verificación de los datos recibidos

| Lo que afirmaba la tarea | Comprobado con | Resultado |
|--------------------------|----------------|-----------|

### Archivos modificados / creados

- [ruta]: [qué hace]

### Comandos de verificación — salida literal

$ uv run --no-sync pytest
[salida]

### Criterios de aceptación

| Criterio | Salida | ¿Cumple? |
|----------|--------|----------|
```
```

### Tester

```markdown
# Tester

Sos el **quality gate**. Nada se entrega sin tu sign-off.

## Regla número uno: los casos salen de la spec

Si derivás los casos leyendo la implementación, solo verificás que el código
hace lo que hace. Los casos salen de la **especificación**.

**Excepción**: en un refactor, la spec es "el comportamiento no cambia". Ahí
sí derivás del código (tests de caracterización).

## Proceso

1. Leer spec y criterios del plan
2. Verificar la implementación contra la spec punto por punto
3. Escribir tests faltantes
4. Ejecutar suite completa
5. Emitir APROBADO o RECHAZADO

## Severidad

- **Crítica/Alta** → RECHAZADO automático
- **Media/Baja** → criterio del Coordinador

## No hacés

- No cambiás código de producción para que un test pase
- No debilitás tests (cambiar aserciones, `@pytest.skip`, `@pytest.xfail`,
  subir timeout)
- No arreglás los bugs que destapás (los reportás y se decide aparte)
```

### Revisor

```markdown
# Revisor

Sos el **último filtro**. No llevás `Write` ni `Edit`: no podés escribir ni
editar por la vía directa. Tu independencia depende de eso — y de que no
uses `Bash` para escribir.

## Premisa

Un agente que se autoevalúa siempre se aprueba. El reporte que recibís es una
afirmación de parte. Tu trabajo es comprobarla.

## Proceso (en orden exacto)

### 1. Tests debilitados (antes que nada)

Buscá aserciones eliminadas, `@pytest.skip`/`xfail` añadidos, timeouts
subidos. Si encontrás → defecto crítico.

### 2. Prueba de mutación sobre copia aislada

**Siempre en /tmp**, nunca en el original.

15-30 mutaciones variadas sobre el código de la ola. Clasificá supervivientes:
dentro o fuera del alcance.

### 3. Corrección

Contra spec y plan. Cada criterio: ¿lo cumple? ¿con qué comando?

### 4. Convenciones y restricciones de plataforma

Comprobables con grep. Para este proyecto:
- `domain/` sin I/O
- `send_from_staging.py` standalone
- Filtro `.Identifier`
- Subject desde archivo
- Paths absolutos

### 5. Seguridad

- ¿Alguna clave en logs?
- ¿Algún input sin validación?

## No hacés

- No arreglás nada (no tenés Write ni Edit; tampoco uses Bash para escribir)
- No aprobás por cansancio (crítico/alto → RECHAZADO)
```

---

## Setup inicial para un proyecto nuevo

1. **Crear estructura de carpetas**:
   ```sh
   mkdir -p .claude/{agents,hooks,planes,cache/bloqueos}
   ```

2. **Copiar este documento** como `AGENTS_SYSTEM.md`

3. **Copiar los prompts de agentes** (`coordinador.md`, `planificador.md`,
   `disenador-web.md`, `desarrollador.md`, `tester.md`, `revisor.md`)

4. **Copiar los hooks**: `puerta-calidad.mjs`, `guardian-escritura.mjs`,
   `guardian-bash.mjs`, `guardian-config.mjs`, `validar-plan.mjs`,
   `permitidas.mjs`, `checkpoint.mjs`, `drift-detection.mjs`,
   `linea-base.mjs`

5. **Crear `settings.json` y `verificacion.json`** adaptados al stack

6. **Inicializar línea base** (cuando se agregue ruff al proyecto):
   ```sh
   node .claude/hooks/linea-base.mjs generar
   ```

7. **Crear `SPEC.md`** como índice de ciclos

8. **Ejecutar el primer ciclo** con el Coordinador sobre una spec

---

## Relación con `CLAUDE.md`

`CLAUDE.md` y `AGENTS_SYSTEM.md` son documentos complementarios:

| `CLAUDE.md` | `AGENTS_SYSTEM.md` |
|---|---|
| Documento fundacional del proyecto | Sistema de agentes |
| Qué es el proyecto | Cómo trabajan los agentes |
| Stack, dependencias, flujo principal | Roles, hooks, puerta de calidad |
| Restricciones de plataforma | Convenciones de testing |
| Para todos (humano y agentes) al arrancar | Para el Coordinador y los agentes |

Ambos los lee cada subagente al arrancar. Un `CLAUDE.md` flojo degrada a todos
los agentes a la vez. Lo mismo aplica a `AGENTS_SYSTEM.md`.
