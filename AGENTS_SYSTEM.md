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
          │ diseñador-web│ → specs de UI/UX, plantillas HTML (si hay UI nueva)
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

## Archivos del sistema

El sistema vive en `.claude/`. Estructura:

```
.claude/
├── agents/
│   ├── coordinador.md          # Orquestador (sesión principal, cargado como agente)
│   ├── planificador.md         # Spec → tareas atómicas
│   ├── diseñador-web.md        # UI/UX, plantillas HTML
│   ├── desarrollador.md        # Implementación en el repo (único que escribe código)
│   ├── tester.md               # Pruebas con pytest
│   ├── revisor.md              # Tests debilitados + prueba de mutación
│   ├── TEAM.md                 # Este archivo resumido
│   └── AGENT_TEAMS.md          # Docs sobre Agent Teams (experimental)
├── hooks/
│   ├── puerta-calidad.mjs      # Hook de calidad (SubagentStop)
│   ├── guardian-escritura.mjs  # Bloquea escritura no autorizada
│   ├── checkpoint.mjs          # Git tags para rollback
│   ├── drift-detection.mjs     # Verifica APIs citadas existen
│   └── linea-base.mjs          # Línea base de errores heredados
├── decisiones/
│   └── README.md               # Registro de decisiones de arquitectura
├── cache/                       # Estado de bloqueos, caché de lint
├── settings.json               # Config: hooks, autonomía
├── settings.local.json         # Permisos locales del sandbox
├── verificacion.json           # Comandos de calidad por perfil
└── linea-base.json             # Errores heredados por archivo (generado por el script)
```

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
- Delegar en `diseñador-web`
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

### Niveles de autonomía (en settings.json)

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
**Bloqueo**: Hook que impide Write/Edit fuera de `.claude/planes/`,
`.claude/disenos/`, `docs/`, `SPEC.md`

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

**Archivo**: `.claude/agents/diseñador-web.md`

**Herramientas**: Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Bash
**Bloqueo**: Hook que impide Write/Edit fuera de `.claude/disenos/`,
`.claude/planes/`, `docs/`, `SPEC.md`

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
3. Implementar respetando arquitectura hexagonal: domain → ports → application
   → infrastructure → entrypoints (main.py / import_email_template.py /
   outlook_send.py)
4. Verificar con `uv run pytest` (y ruff/mypy si están disponibles)
5. Reportar con salida literal de los comandos

**Reglas duras del proyecto**:
- `outlook_send.py` debe permanecer standalone (sin imports del proyecto)
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
`uv run pytest` (y lint/typecheck si aplica).

### 5. Tester (modelo: sonnet)

**Responsabilidad**: QA, diseño y ejecución de pruebas contra la spec.

**Archivo**: `.claude/agents/tester.md`

**Herramientas**: Read, Write, Edit, Bash, Glob, Grep

**Proceso**:
1. Leer spec y criterios del plan
2. Verificar que la implementación cumple la spec
3. Escribir tests faltantes en `tests/` o `test/`
4. Ejecutar suite completa con `uv run pytest`
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
E2E (send)       → outlook_send.py con mock de win32com (sin enviar correos reales)
```

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
4. **Convenciones** con grep (domain sin I/O, `outlook_send.py` standalone, etc.)
5. **Restricciones de plataforma** (las 5 listadas en desarrollador/revisor)
6. **Seguridad** (secrets en logs, validación de inputs antes de enviar)

**Regla clave**: no puede arreglar nada. Solo reportar. Su independencia
depende de no poder escribir.

---

## La puerta de calidad

Hook `SubagentStop` en `.claude/settings.json`:

```json
"hooks": {
  "SubagentStop": [
    {
      "matcher": "desarrollador|tester",
      "hooks": [
        {
          "type": "command",
          "command": "node .claude/hooks/puerta-calidad.mjs",
          "timeout": 900
        }
      ]
    }
  ]
}
```

**Perfiles (en `.claude/verificacion.json`)**:

```json
"perfiles": {
  "rapida": [
    { "etiqueta": "tests", "comando": "uv run pytest", "obligatorio": true },
    { "etiqueta": "lint", "comando": "uv run ruff check .", "obligatorio": false },
    { "etiqueta": "tipos", "comando": "uv run mypy .", "obligatorio": false }
  ],
  "completa": [
    { "etiqueta": "tests", "comando": "uv run pytest", "obligatorio": true },
    { "etiqueta": "lint", "comando": "uv run ruff check .", "obligatorio": false },
    { "etiqueta": "tipos", "comando": "uv run mypy .", "obligatorio": false },
    { "etiqueta": "linea-base", "comando": "node .claude/hooks/linea-base.mjs verificar", "obligatorio": false },
    { "etiqueta": "cobertura", "comando": "uv run pytest --cov=. --cov-report=term-missing", "obligatorio": false }
  ]
}
```

**Comportamiento**:
- Si la puerta falla → bloquea al agente, no puede declararse terminado
- Anti-bucle: tras 3 bloqueos, deja pasar para que el fallo escale al
  Coordinador
- La puerta ejecuta los comandos, no el agente → no puede mentir

**Nota sobre este proyecto**: `ruff` y `mypy` no están agregados todavía al
`pyproject.toml`. La puerta los salta si no están instalados
(`obligatorio: false`). Cuando se agreguen con `uv add --dev`, cambiar a
`obligatorio: true`.

---

## Hooks del sistema

### guardian-escritura.mjs

Bloquea Write/Edit en agentes que no deben escribir código. Se declara en el
frontmatter del agente:

```yaml
---
hooks:
  PreToolUse:
    - matcher: "Write|Edit|NotebookEdit"
      hooks:
        - type: command
          command: node .claude/hooks/guardian-escritura.mjs
---
```

**Rutas permitidas**:
- `.claude/planes/`
- `.claude/disenos/`
- `docs/`
- `SPEC.md` (exacto)

### checkpoint.mjs

Git tags para rollback antes de cada ola.

```sh
# Crear checkpoint antes de una ola
node .claude/hooks/checkpoint.mjs crear ola-ciclo-1-ola-1

# Rollback si algo sale mal
node .claude/hooks/checkpoint.mjs rollback ola-ciclo-1-ola-1 --confirmar

# Listar checkpoints
node .claude/hooks/checkpoint.mjs listar

# Verificar que existe
node .claude/hooks/checkpoint.mjs verificar ola-ciclo-1-ola-1
```

### drift-detection.mjs

Verifica que las APIs citadas en un plan existen en el código.

```sh
# Verificar un plan específico
node .claude/hooks/drift-detection.mjs .claude/planes/mi-plan.json

# Verificar todos los planes
node .claude/hooks/drift-detection.mjs verificar
```

### linea-base.mjs

Gestiona la línea base de errores heredados.

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
    "rapida": [...],
    "completa": [...]
  },
  "agentesVigilados": ["desarrollador", "tester"],
  "maxBloqueosPorAgente": 3,
  "timeouts": {
    "tests": 300000,
    "lint": 120000,
    "tipos": 300000
  }
}
```

Para adaptar a otro proyecto:
1. Cambiar los comandos en `perfiles`
2. Ajustar `agentesVigilados` según qué agentes escriben código
3. Ajustar `timeouts` según el tamaño del proyecto

### linea-base.json

```json
{
  "archivos": {
    "domain/entities.py": 0
  }
}
```

Cada archivo tiene un presupuesto de errores de lint. Hoy día 0 errores en
todos los archivos nuevos. Se genera ejecutando
`node .claude/hooks/linea-base.mjs generar` (solo el usuario, solo a la baja).

---

## Convenciones del proyecto

Estas convenciones están adaptadas al proyecto específico:

| Convención                                                       | Evidencia                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------ |
| `domain/` es lógica pura, sin I/O                               | `domain/entities.py`, `domain/types.py`                      |
| Arquitectura hexagonal: domain ← ports ← application ← infrastructure | Estructura del repo                                     |
| `outlook_send.py` standalone (sin imports del proyecto)         | Restricción de plataforma para evitar cache de `.pyc` Windows |
| Paths absolutos con `Path(__file__).resolve().parent`           | `import_email_template.py`, `main.py`                        |
| Filtrar archivos `.Identifier` al listar imágenes               | Restricción WSL/Windows                                      |
| HTML usa `{images[N]}` → `cid:image_N`                          | `application/send_emails.py`, `infrastructure/services/`     |
| Subject desde `html/templates/subject.txt`                      | `main.py`                                                    |
| Tests en `test/` y `tests/` (las dos suites coexisten)          | `pyproject.toml [tool.pytest.ini_options]`                   |
| Contactos desde Airtable REST API                               | `infrastructure/repositories/airtable_contact_repository.py` |
| Imágenes inline embebidas vía Outlook COM con MAPI properties   | `infrastructure/adapters/outlook_desktop_adapter.py`         |

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
6. **Decisiones que no se documentan.** → Van al registro de decisiones.
7. **Scope creep.** → El agente reporta trabajo extra, no lo expande en
   silencio.
8. **`outlook_send.py` con imports del proyecto.** → Rompe la restricción
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
4. Verificar: uv run pytest
5. Reportar con salida literal

## Reglas duras

- No reinterpretar la spec: si es ambiguo, preguntar
- No debilitar tests para pasar
- No tocar la configuración para silenciar errores
- `outlook_send.py` permanece standalone
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

$ uv run pytest
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

Sos el **último filtro**. No podés escribir ni editar nada. Tu independencia
depende de eso.

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
- `outlook_send.py` standalone
- Filtro `.Identifier`
- Subject desde archivo
- Paths absolutos

### 5. Seguridad

- ¿Alguna clave en logs?
- ¿Algún input sin validación?

## No hacés

- No arreglás nada (no tenés Write ni Edit)
- No aprobás por cansancio (crítico/alto → RECHAZADO)
```

---

## Setup inicial para un proyecto nuevo

1. **Crear estructura de carpetas**:
   ```sh
   mkdir -p .claude/{agents,hooks,decisiones,cache/bloqueos}
   ```

2. **Copiar este documento** como `AGENTS_SYSTEM.md`

3. **Copiar los prompts de agentes** (`coordinador.md`, `planificador.md`,
   `diseñador-web.md`, `desarrollador.md`, `tester.md`, `revisor.md`)

4. **Copiar los hooks**: `puerta-calidad.mjs`, `guardian-escritura.mjs`,
   `checkpoint.mjs`, `drift-detection.mjs`, `linea-base.mjs`

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
