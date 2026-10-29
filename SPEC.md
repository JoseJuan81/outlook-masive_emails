# Spec activa del ciclo en curso

> Esta `SPEC.md` apunta al ciclo activo. Cada ciclo deja su plan legible por
> máquina en `.claude/planes/<nombre>.json` y su explicación en
> `.claude/planes/<nombre>.md`; este archivo es solo el índice que lee el
> Coordinador por defecto.
>
> **`.claude/planes/` está en `.gitignore`** (decisión del ciclo 3: los planes
> son artefactos regenerables; el índice de ciclos es este `SPEC.md`, que sí se
> versiona). Dos consecuencias, para que no se infiera mal:
> los enlaces a planes de este archivo **solo resuelven en la máquina que los
> produjo** — en un clon nuevo no hay planes que abrir; y
> `node .claude/hooks/drift-detection.mjs verificar` no tiene nada que
> comprobar y sale con `3` ("no aplica") en lugar de con `0`.

## Estado actual

**Ciclo 3 cerrado — revisión del sistema de agentes, saneado del repo y
arreglo del envío.** Cerrado en `a888fee` (rango `2d40b8d..a888fee`, publicado
en `origin/main`). Los tres ciclos anteriores están cerrados: su código ya está
en `main` y sus planes quedan en `.claude/planes/`.

El ciclo 3 tuvo un **endurecimiento posterior (D7, D8, D9)** que cerró tres
huecos que la propia auditoría dejó abiertos: los prompts de los roles ya no
son reescribibles por un agente vigilado (D7), la puerta juzga el árbol en el
que el agente realmente trabaja, incluido un worktree aislado (D8), y la
resolución del intérprete de Python de Windows ya no descarta la ruta real
cuando el nombre de la carpeta de perfil de Windows coincide con el
placeholder (D9). Ver
[Endurecimiento posterior](#endurecimiento-posterior-d7-d8-y-d9).

**No hay ciclo activo.** Para abrir uno, sigue las instrucciones de la última
sección de este archivo.

La spec fundacional del proyecto está en [`README.md`](README.md) (flujo EML →
preview → envío masivo vía Outlook COM, arquitectura hexagonal, stack
Python/uv, Airtable como fuente de contactos).

## Ciclo 3 — Sistema de agentes, saneado del repo y envío · CERRADO

**Spec detallada**: esta misma entrada. El plan aprobado del ciclo vive en
`~/.claude/plans/abstract-mixing-dragon.md` (fuera del repo, a propósito:
`.claude/planes/` está en `.gitignore` porque sus artefactos son regenerables).

**Spec**: tres frentes.

1. **Sistema de agentes** — que la puerta de calidad funcione de verdad y que
   los hooks no se puedan esquivar:
   - `.claude/settings.json` registra la puerta en `SubagentStop` (matcher
     `desarrollador|tester`, perfil `rapida`, timeout 900 s) y
     `guardian-config.mjs` en `PreToolUse`.
   - `guardian-escritura.mjs` (escritura fuera de las rutas permitidas) y
     `guardian-bash.mjs` (la fuga por Bash) en el frontmatter de los dos roles
     que producen documentos; `validar-plan.mjs` (schema de los planes) en el
     `planificador`.
   - `guardian-config.mjs` impide que un agente vigilado (`desarrollador`,
     `tester`) reescriba `.claude/hooks/`, `.claude/verificacion.json`,
     `.claude/linea-base.json` ni los `settings.json`: la configuración de la
     puerta no se puede reescribir desde quien la puerta juzga.
   - Línea base de ruff congelada (`.claude/linea-base.json`), drift de planes
     (`drift-detection.mjs`) y checkpoints (`checkpoint.mjs`).
2. **Saneado del repo** — `test/` legacy frente a `tests/` vigente, scripts y
   documentación al día.
3. **Envío** — que el correo que sale no venga con recibos y que el staging
   quede escrito antes de lanzar el envío:
   - recibos de Outlook apagados en **ambas** rutas
     (`send_from_staging.py` e `infrastructure/adapters/outlook_desktop_adapter.py`);
   - log de diagnóstico restaurado (`[send_from_staging] staging cargado:`);
   - `fsync` del staging en las dos rutas que lo escriben (`main.py` y
     `web/app.py`).

**Resumen**: el ciclo convierte el sistema de agentes en algo que se ejecuta
de verdad (puerta de calidad registrada, guardianes de escritura/Bash/config,
verificador de planes, línea base de ruff, drift y checkpoints), limpia el
repo y cierra los agujeros del envío (recibos, log de diagnóstico,
persistencia del staging).

**Estado de implementación**: los tres frentes están implementados y son
verificables por comando.

- **Sistema de agentes**: `.claude/settings.json` registra la puerta en
  `SubagentStop` (matcher `desarrollador|tester`, perfil `rapida`, timeout
  900 s) y `guardian-config.mjs` en `PreToolUse`. Los guardianes están
  registrados en el frontmatter de los cinco roles. La auditoría D1–D6 está
  cerrada; el último hueco (D4: `desarrollador` y `tester` podían reescribir
  por Bash la puerta que los juzga) se cerró con `guardian-bash.mjs` en dos
  modos según el rol — "documentos" (allowlist estricta) y "vigilado" (código
  de producción permitido; solo se niegan las rutas de la puerta y los
  comandos destructivos).
- **Saneado del repo**: las duplicidades de la raíz están movidas a `tests/`;
  quedan `test/` (legacy, aún en pie) y `contacts.py`/`env.py` en la raíz.
- **Envío**: recibos apagados en las dos rutas, log de diagnóstico restaurado y
  `fsync` del staging en `main.py` y `web/app.py`.

**Criterio de hecho**: la suite en verde y la puerta de calidad en verde.

```sh
uv run --no-sync pytest                          # exit 0
node .claude/hooks/puerta-calidad.mjs rapida     # exit 0
```

Comprobaciones puntuales del frente de envío:

```sh
grep -n "ReadReceiptRequested = False" send_from_staging.py infrastructure/adapters/outlook_desktop_adapter.py
grep -n "os.fsync" main.py web/app.py
grep -n "staging cargado" send_from_staging.py
```

**Pendiente que bloquea la puerta (acción del usuario)**: el perfil `rapida`
incluye `lint`, que mide la regresión contra la línea base congelada.
`.claude/linea-base.json` sigue siendo el placeholder vacío (`"archivos": {}`),
generado antes de que ruff estuviera instalado, así que todo hallazgo de ruff
cuenta como regresión: `ruff` reporta **80** hallazgos y
`linea-base.mjs verificar` sale con `1`, con lo que la puerta bloquea (código
2). **Solo el usuario regenera la línea base, y solo a la baja**:

```sh
rm .claude/linea-base.json && node .claude/hooks/linea-base.mjs generar
```

La otra vía es arreglar los 80 hallazgos. Con la línea base regenerada, la
puerta queda en verde y `lint` puede pasar a `"obligatorio": true` en los dos
perfiles de `.claude/verificacion.json`.

### Endurecimiento posterior (D7, D8 y D9)

Tres huecos que la auditoría del ciclo 3 dejó abiertos, cerrados después.

**D7 — los prompts de los roles también están protegidos.** `guardian-config.mjs`
protegía `.claude/hooks/`, `.claude/verificacion.json`,
`.claude/linea-base.json` y los `settings.json`, pero **no** `.claude/agents/`.
Los hooks de cada rol se registran en **su propio** frontmatter: un agente
vigilado (`desarrollador`, `tester`) que pudiera reescribir `.claude/agents/`
podía quitarse a sí mismo el bloque `hooks:` que lo protege y desarmar la
puerta entera. La exclusión anterior («en una ola posterior hay que poder
corregir la documentación de los agentes») no hace falta: el hook solo
restringe a `agentesVigilados`, y la sesión principal (Coordinador) no está
restringida y sigue pudiendo corregir los prompts por la vía correcta.

La protección es **doble**: `guardian-config.mjs` la aplica a
Write/Edit/NotebookEdit y `guardian-bash.mjs` la aplica a Bash en su modo
«vigilado». Con solo una de las dos, el hueco seguiría abierto por la otra
vía (`echo x > .claude/agents/desarrollador.md` era el mismo bypass por
Bash).

**D8 — la puerta juzga el árbol en el que se trabaja.** El evento
`SubagentStop` trae `cwd` («current working directory when the hook is
invoked»; si Claude entra en un worktree, es la raíz del worktree). Antes la
puerta juzgaba siempre el checkout donde vive el script: un agente que
trabajaba en un worktree aislado era evaluado contra un árbol **sin sus
cambios**, así que la puerta le aprobaría todo. Ahora usa ese `cwd` como raíz
de trabajo cuando contiene su propio `.claude/verificacion.json` (es decir,
cuando es un checkout) y el checkout principal en cualquier otro caso.

**D9 — la resolución del intérprete de Python de Windows.** En `web/app.py`,
`_resolve_windows_python()` construía sus candidatos con el placeholder
`/USER/` y lo sustituía **en sitio** (`c.replace("/USER/", f"/{user}/")`),
descartando la variante literal. En una máquina donde la carpeta de perfil de
Windows se llama literalmente `USER`, la ruta real quedaba inalcanzable y la
resolución devolvía `None` sin `WINDOWS_PYTHON_PATH`. Ahora la lista de
candidatos vive en la función pura `_candidate_windows_python_paths()`, que
devuelve **las dos** variantes (literal y sustituida, sin duplicados).
Cerrado en `e31d097`, con 14 tests deterministas
(`tests/test_windows_python_resolution.py`) que fallan (9 de 14) contra el
código con el bug.

## Ciclo 2 — `MAPI_E_OBJECT_DELETED` en el gate de entrega · CERRADO

**Spec detallada**: `.claude/planes/fix-mapi-object-deleted.md`
(plan legible por máquina: `.claude/planes/fix-mapi-object-deleted.json`)

**Resumen**: `_item_in_outbox` trataba `MAPI_E_OBJECT_DELETED` como «el item
sigue en el Outbox», así que la entrega se marcaba como fallida aunque Outlook
ya la hubiera hecho. Ahora ese error se distingue y el caller presume entrega
cuando los Sent Items han crecido.

**Criterio de hecho**: `uv run pytest tests/test_send_from_staging_fix.py -v`
y `uv run pytest tests/test_outlook_com_order.py -v` en verde, con
`send_from_staging.py` todavía standalone. Cerrado en `ae3d2d9`.

## Ciclo 1 — Validación de entrega real antes de marcar `sent` · CERRADO

**Spec detallada**: `.claude/planes/fix-outlook-delivery-validation.md`
(plan legible por máquina: `.claude/planes/fix-outlook-delivery-validation.json`)

**Resumen**: `wait_for_sent` contaba los ítems de Sent Items, que Outlook
actualiza **antes** de que el servidor SMTP confirme: el script reportaba
`sent: 1` aunque el correo nunca llegara. Se sustituyó por un gate que
combina la salida del Outbox con `mail.SentOn`, más el workaround MAPI del
subject (`PR_SUBJECT`) y manejo de `pywintypes.com_error`.

**Criterio de hecho**: `uv run pytest tests/test_send_from_staging_fix.py -v`
y `uv run pytest tests/test_outlook_com_order.py -v` en verde. Cerrado en
`737b3ba`.

## Cómo abrir un ciclo nuevo

1. Crear `.claude/planes/<nombre-corto>.json` (legible por máquina, con el
   schema que valida `validar-plan.mjs`) y `.claude/planes/<nombre-corto>.md`
   (la explicación para el usuario) con la spec detallada de la feature a
   implementar. La spec debe terminar con un criterio de hecho medible con un
   comando. Ambos ficheros viven en `.claude/planes/`, que está en
   `.gitignore`: el plan es un artefacto local de trabajo, y lo que queda
   versionado es la entrada de este `SPEC.md`.
2. Editar este `SPEC.md` y añadir la entrada del nuevo ciclo **arriba** de los
   anteriores (el más reciente primero), y mover a CERRADO la entrada del
   ciclo que se cierra, anotando el commit.
3. Pedir al Coordinador que ejecute el ciclo sobre la spec.
