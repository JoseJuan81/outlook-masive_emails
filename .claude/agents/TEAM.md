# Equipo de Agentes — outlook-masive_emails

Este documento define cómo colaboran los agentes de este proyecto.

**El Coordinador es la sesión principal, no un subagente.** Su rol está
definido en [`coordinador.md`](./coordinador.md), que **no lleva frontmatter
YAML**: al no registrarse como agente, no aparece en la lista de agentes
disponibles y no se puede lanzar como subagente. El motivo no es cosmético:

- Un subagente **no puede pararse a pedirte aprobación**: devuelve un resultado
  y muere. Cualquier «parada» que prometa su prompt es ficción — o decide solo,
  o falla.
- Un subagente **no puede lanzar otros subagentes** sin la herramienta `Agent`,
  y dársela crea una recursión difícil de acotar.
- La sesión principal sí conserva la conversación contigo, sí puede parar y sí
  puede delegar en paralelo.

Los demás son ejecutores especializados que arrancan **en frío** (ventana
vacía: solo su prompt, el mensaje de delegación, `CLAUDE.md`, `README.md` y el
estado de git) y devuelven un informe.

## Roles

| Rol              | Archivo                                          | Modelo  | Responsabilidad                                                                              |
| ---------------- | ------------------------------------------------ | ------- | -------------------------------------------------------------------------------------------- |
| Coordinador      | [`coordinador.md`](./coordinador.md)             | —       | Verificar, planificar el ciclo, obtener aprobación, delegar, desbloquear                     |
| Planificador     | [`planificador.md`](./planificador.md)           | opus    | Spec → tareas atómicas con archivos exclusivos y olas sin solape                             |
| Diseñador Web    | [`disenador-web.md`](./disenador-web.md)         | sonnet  | UI/UX, plantillas HTML para correos, design system, accesibilidad                          |
| Desarrollador    | [`desarrollador.md`](./desarrollador.md)         | sonnet  | Implementar en el repo. **Único que escribe código de producción**                           |
| Tester           | [`tester.md`](./tester.md)                       | sonnet  | Diseñar y ejecutar pruebas con pytest contra la spec                                         |
| Revisor          | [`revisor.md`](./revisor.md)                     | opus    | Tests debilitados, prueba de mutación, corrección, convenciones, restricciones de plataforma |

**Reparto de modelos**: razonamiento fuerte donde se decide y se juzga
(`planificador`, `revisor`); modelo medio donde se ejecuta con criterios
explícitos y puerta objetiva (`desarrollador`, `tester`, `disenador-web`).

Este proyecto **no tiene agente experto de dominio** (como `luna-serena` en
`cycle-companion`): es una herramienta técnica interna (pipeline de envío
masivo de correos), no un producto con reglas de negocio que requieran una
autoridad separada del desarrollador. Si en algún momento aparece contenido de
producto que requiera validación separada (por ejemplo: validación legal de
plantillas HTML), se agrega un agente de dominio siguiendo el patrón de
`cycle-companion`.

## Flujo de trabajo

```
   ┌──────────────┐
   │   Usuario    │  escribe SPEC.md, lanza el ciclo
   └──────┬───────┘
          ▼
   ┌────────────────────────────┐
   │  Sesión principal          │  Fase 0: árbol limpio + puerta completa en verde
   │  (Coordinador)             │
   └──────┬─────────────────────┘
          ▼
     ┌──────────────┐
     │ planificador │ → plan con olas y archivos exclusivos → 🛑 usuario aprueba
     └──────┬───────┘
            ▼
     ┌──────────────┐
     │ disenador-web│  (solo si hay UI) → spec → 🛑 usuario aprueba
     └──────┬───────┘
            ▼
   ── por cada ola ────────────────────────────────────────────────────────
     ┌─────────────┐ ┌─────────────┐   en paralelo, archivos disjuntos
     │desarrollador│ │desarrollador│   ← puerta rápida en cada SubagentStop
     └──────┬──────┘ └──────┬──────┘
            └───────┬───────┘
                    ▼
               ┌────────┐
               │ tester │ ← puerta rápida
               └───┬────┘
                   ▼
              ┌──────────┐
              │ revisor  │  tests debilitados → mutación → corrección
              └────┬─────┘  (sin Write ni Edit; el guardian de Bash le impide escribir)
                   ▼
            puerta COMPLETA → siguiente ola
   ──────────────────────────────────────────────────────────────────────────
          ▼
   🛑 Parada final: verificación completa, SIN commitear
```

### Los tres mecanismos que sostienen el sistema

Sin ellos, esto es un grupo de agentes que se autoaprueban.

1. **Verificación objetiva.** Ningún agente da nada por terminado porque lo
   diga. El hook `SubagentStop` (`../hooks/puerta-calidad.mjs`) vuelve a
   ejecutar los comandos por su cuenta y sale con código 2 si fallan.
2. **Línea base congelada.** «No empeores el repo» comprobable por comando
   (`../linea-base.json`), verificado con
   `node .claude/hooks/linea-base.mjs verificar`. `ruff` ya está en el
   `pyproject.toml`; la línea base **solo la regenera el usuario, y solo a la
   baja**.
3. **Olas con archivos exclusivos.** Dos tareas de la misma ola nunca
   comparten un archivo. La intersección se verifica por comando antes de
   lanzar cada ola.

## Sistema de hooks

Los hooks se registran en **dos sitios distintos**, y por eso están separados.

### En `.claude/settings.json` (aplican a todo subagente del proyecto)

| Evento | Matcher | Hook | Qué hace |
| ------ | ------- | ---- | -------- |
| `SubagentStop` | `desarrollador\|tester` | `puerta-calidad.mjs rapida` | Ejecuta los comandos del perfil `rapida` y **bloquea** al subagente (código de salida 2 + motivo en stderr) si alguno falla |
| `PreToolUse` | `Write\|Edit\|MultiEdit\|NotebookEdit` | `guardian-config.mjs` | Impide que un agente **vigilado** (`desarrollador`, `tester`) reescriba la configuración de la puerta que lo juzga: `.claude/hooks/`, `.claude/agents/`, `.claude/verificacion.json`, `.claude/linea-base.json`, `.claude/settings.json`, `.claude/settings.local.json` |

### En el frontmatter del agente (aplican solo mientras ese agente está activo)

| Hook | Matcher | En qué agente | Qué hace |
| ---- | ------- | ------------- | -------- |
| `guardian-escritura.mjs` | `Write\|Edit\|MultiEdit\|NotebookEdit` | `planificador`, `disenador-web` | Bloquea la escritura fuera de `.claude/planes/`, `.claude/disenos/`, `.claude/cache/`, `docs/`, `SPEC.md` |
| `guardian-bash.mjs` | `Bash` | los cinco | Cierra la fuga por Bash, en **dos modos** según el rol: en `planificador`/`disenador-web`/`revisor` es una allowlist estricta (`echo x > main.py`, `sed -i`, `rm -rf`, `git reset --hard`, `git clean`, `uv add`/`sync`/`lock`… denegados; el `revisor` solo puede escribir en `/tmp`, lo que hace **técnica** su independencia); en `desarrollador`/`tester` permite el código de producción y solo niega las rutas de la configuración de la puerta y los comandos destructivos |
| `validar-plan.mjs` | `Write` | `planificador` | Valida el schema de los planes `.claude/planes/*.json` |

Los comandos `checkpoint.mjs`, `drift-detection.mjs` y `linea-base.mjs` **no son
hooks**: son CLI que el Coordinador invoca a mano.

### La puerta juzga el árbol en el que se trabaja

El evento `SubagentStop` trae `cwd` («current working directory when the hook
is invoked»; si Claude entra en un worktree, es la raíz del worktree). La
puerta lo usa como raíz de trabajo cuando contiene su propio
`.claude/verificacion.json` —es decir, cuando es un checkout— y el checkout
principal en cualquier otro caso. Sin esto, un agente que trabaja en un
worktree aislado sería juzgado contra el checkout principal, que no contiene
sus cambios: la puerta le aprobaría todo.

`.claude/agents/` está entre las rutas protegidas de `guardian-config.mjs`
(Write/Edit) **y** de `guardian-bash.mjs` en su modo «vigilado» (Bash): los
hooks de cada rol se registran en **su** frontmatter, así que un agente
vigilado que pudiera reescribir `.claude/agents/` podría quitarse a sí mismo
el `hooks:` que lo protege. La sesión principal (Coordinador) no está
restringida y sigue pudiendo corregir los prompts de los roles.

**Límite conocido — workspace trust**: los hooks de proyecto **NO se ejecutan**
si la carpeta no es confiable en Claude Code. Sin trust, la puerta no bloquea
y todo parece ir bien. Es la trampa más fácil de pasar por alto al leer un
«pasó».

## Cómo delega el Coordinador

Con la herramienta **Agent**. Para correr en paralelo, varias invocaciones en
un mismo mensaje.

```text
Agent(subagent_type: "planificador",    prompt: "Spec: SPEC.md. Verifica con grep todo lo que afirma antes de planificar...")
Agent(subagent_type: "desarrollador",  prompt: "Tarea T1 del plan. ARCHIVOS EXCLUSIVOS: ... Criterios: `comando` → ...")
Agent(subagent_type: "revisor",        prompt: "Revisa la ola 1. Informes adjuntos como afirmaciones a comprobar, no como hechos.")
```

**Ningún subagente lleva la herramienta `Agent`.** Solo la sesión principal
delega.

### El coste real: el arranque en frío

Los subagentes no heredan la conversación. Se mitiga metiendo el contexto
**duradero** en archivos que el agente lee (`CLAUDE.md`, `README.md`, el plan
generado) y dejando en el prompt solo la tarea, sus criterios y punteros. Pero
no se elimina: **un prompt escueto produce un agente que reinventa lo que ya
estaba decidido.**

`CLAUDE.md` es el archivo de mayor apalancamiento del sistema, porque lo lee
cada subagente al arrancar. Un `CLAUDE.md` flojo degrada a todos los agentes a
la vez.

## Restricciones de plataforma (no negociables)

Este proyecto tiene restricciones específicas que todo el equipo respeta.
Cualquier violación es defecto crítico:

1. **`send_from_staging.py` permanece standalone.** Sin imports del proyecto.
   Razón: evitar cache de `.pyc` de Windows Python
   (`/mnt/c/Python313/python.exe`).
2. **Paths absolutos** con `Path(__file__).resolve().parent`. Razón: el
   directorio de trabajo del usuario no es predecible.
3. **Filtrar archivos `.Identifier`** al listar imágenes. Razón: WSL ve
   archivos espurios generados por OneDrive/Windows.
4. **Subject desde `html/templates/subject.txt`**, nunca hardcodeado.
5. **HTML usa `{images[N]}` → `cid:image_N`** para imágenes inline. Los
   binarios se embeben vía Outlook COM con MAPI properties.

Las reglas 1 y 3 son **defecto crítico** si se violan. Las reglas 2, 4 y 5 son
defecto alto.

**Ojo con la arquitectura**: el repo tiene capa hexagonal (`domain/`, `ports/`,
`application/`, `infrastructure/`), pero **la capa hexagonal no es el camino de
envío**. El envío real es `import_email_template.py` → `main.py` (o
`web/app.py`) → `staging/emails_to_send.json` → `send_from_staging.py` (Windows)
→ Outlook COM. `application/send_emails.py` y
`infrastructure/adapters/outlook_desktop_adapter.py` los usan **solo los
tests**.

## Reglas generales

1. **Plan-first.** El Coordinador siempre presenta el plan y espera aprobación
   explícita antes de ejecutar. Nunca delega sin que el usuario lo haya visto
   y aceptado.
2. **Spec antes que código.** Nunca se envía trabajo al desarrollador sin spec
   de `disenador-web` cuando hay UI nueva — excepto trabajo puramente técnico
   de backend (dominio, adaptadores, repositorios, bug de lógica, refactor sin
   cambio de comportamiento).
3. **QA es obligatorio.** Ninguna feature pasa a "lista" sin `tester` y sin
   `revisor`. Cualquier defecto crítico o alto → rechazo automático.
4. **El agente especializado es la única fuente de verdad de su área.** El
   desarrollador no reinterpreta ni "simplifica conservadoramente" una spec de
   diseño — si algo es ambiguo, la pregunta sube al Coordinador, no se decide
   por su cuenta. El tester no aprueba una desviación de spec solo porque
   "funciona técnicamente" — es un defecto.
5. **No scope creep.** Si un agente descubre trabajo fuera de su encargo, lo
   reporta — no lo expande en silencio. En particular, los bugs que aparecen al
   cubrir código sin tests **se reportan, no se arreglan en la misma tarea**.
6. **Las preguntas suben al Coordinador.** Ningún agente inventa una respuesta
   a una decisión de producto o de arquitectura que no le corresponde.
7. **Contexto completo en cada hand-off.** Al pasar trabajo de un agente a
   otro, incluir siempre: el objetivo final del usuario, el historial de
   decisiones relevante, y el entregable completo del agente anterior — nunca
   asumir que el siguiente ya lo conoce.
8. **El usuario es el revisor final.** El Coordinador presenta el resultado al
   usuario al cierre de cada ola, no solo al final del proyecto.
9. **Activación autónoma.** El usuario no necesita indicar qué agente usar —
   ante cualquier solicitud, el Coordinador la clasifica, decide la ruta y
   activa los agentes necesarios en orden.
10. **Respuestas breves por defecto.** Toda comunicación de un agente hacia el
    usuario es corta y directa, sin explicaciones extensas, salvo que el
    usuario las pida explícitamente. Esto **no** limita los entregables
    técnicos estructurados entre agentes (specs, checklists, reportes de
    defectos, hand-offs) — esos siguen siendo tan completos como haga falta.
11. **Nada externo sin aprobación.** Ningún agente crea repositorios,
    despliegues ni recursos remotos sin aprobación explícita del usuario. **Y
    nadie commitea sin que el usuario lo pida.**
12. **La desconfianza va en las dos direcciones.** Un agente verifica los datos
    que **recibe**, no solo los que produce. Un dato del plan es una hipótesis:
    si el recuento no cuadra, se corrige al Coordinador y se dice.
13. **Tope de 3 intentos por tarea.** Al tercero se para y se avisa al usuario
    con el diagnóstico. No hay cuarto intento y no se baja el estándar.

## Clasificación rápida de solicitudes

| Tipo de solicitud                                                                                | Ruta                                                |
| ------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| Feature con spec escrita, varios archivos                                                        | ciclo completo (Fase 1-4)                           |
| Feature nueva con UI (cualquier archivo en `web/`, `html/`, `Templates/`)                        | `planificador` → `disenador-web` → `desarrollador`  |
| Feature nueva puramente backend (`domain/`, `application/`, `infrastructure/`, `ports/`)        | `planificador` → `desarrollador`                    |
| Diseño/rediseño de UI, UX, plantilla HTML                                                        | `disenador-web`                                     |
| Bug técnico (crash, parser EML falla, Airtable no carga, Outlook COM falla)                      | `desarrollador` → `tester`                          |
| Refactor sin cambio de comportamiento                                                            | `tester` (caracterización) → `desarrollador`        |
| Auditoría / verificación de que algo funciona                                                    | `revisor`                                           |

En un refactor el orden se invierte a propósito: la red de caracterización se
escribe **antes** de tocar nada, porque es lo único que demuestra que el
comportamiento no cambió.

## Convenciones

- **Límite de tamaño de archivo**: no definido explícitamente. Si un archivo
  crece demasiado, dividir por responsabilidad de capa (`domain/` puro,
  `application/`, `infrastructure/`, `ports/`).
- **Idioma**: español para respuestas al usuario, documentación y comentarios
  de código. Los identificadores de código en inglés (`AirtableRepository`,
  `OutlookDesktopAdapter`, `generate_payload`).
- **Nombres de archivo**: `snake_case.py`. Tests: `test_<archivo>.py` o
  `tests/test_<archivo>.py` (las dos suites coexisten).
- **Suite de tests**: pytest, configurado en `pyproject.toml`
  `[tool.pytest.ini_options]` con `pythonpath = ["."]` y
  `testpaths = ["."]`. Comando canónico: `uv run --no-sync pytest`.
  (`uv sync` a secas desinstala pytest: poda el grupo `test`. Para instalar
  sin romper nada, `uv sync --all-groups`.)

## Diferencias con otros proyectos de la familia

| Aspecto                       | `cycle-companion` | `video-pipeline`   | **outlook-masive_emails** |
| ----------------------------- | ----------------- | ------------------ | ------------------------- |
| Stack                         | React/TS/pnpm     | TanStack/TS/pnpm   | **Python/uv**             |
| Restricción externa           | Lovable           | Lovable            | **WSL2 + Windows Python** |
| `CLAUDE.md` como              | Documento fundacional | Convenciones + orq. embebido | **Documento fundacional** |
| `send_from_staging.py` standalone  | n/a            | n/a                | **Sí (crítica)**          |
| Agente de dominio             | `luna-serena`     | ninguno            | **ninguno**               |
| Tests E2E                     | Playwright        | Vitest             | **pytest**                |
| Línea base congelada activa   | Sí (eslint)       | Sí (eslint)        | **Sí (ruff, `linea-base.mjs`)** |
