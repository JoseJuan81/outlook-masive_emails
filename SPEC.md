# Spec activa del ciclo en curso

> Esta `SPEC.md` apunta al ciclo activo. Cada ciclo deja su plan legible por
> máquina en `.claude/planes/<nombre>.json` y su explicación en
> `.claude/planes/<nombre>.md`; este archivo es solo el índice que lee el
> Coordinador por defecto.

## Estado actual

**Ciclo 3 abierto — revisión del sistema de agentes, saneado del repo y
arreglo del envío.** Es el ciclo en curso. Los dos ciclos anteriores están
cerrados: su código ya está en `main` y sus planes quedan en `.claude/planes/`.

La spec fundacional del proyecto está en [`README.md`](README.md) (flujo EML →
preview → envío masivo vía Outlook COM, arquitectura hexagonal, stack
Python/uv, Airtable como fuente de contactos).

## Ciclo 3 — Sistema de agentes, saneado del repo y envío · ACTIVO

**Spec detallada**: esta misma entrada. El ciclo todavía no tiene plan propio
en `.claude/planes/`; cuando lo tenga, se enlaza aquí.

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
verificables por comando. La puerta de calidad está registrada en
`.claude/settings.json` y los guardianes funcionan; los arreglos de envío
están en su sitio; el saneado del repo está a medias (las duplicidades de la
raíz ya están en `tests/`, pero siguen en pie el `test/` legacy y
`contacts.py`/`env.py` en la raíz).

**Criterio de hecho**: la puerta de calidad en verde y la suite en verde.

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

**Pendiente que bloquea la puerta**: el perfil `rapida` incluye `lint`, que
mide la regresión contra la línea base congelada. `.claude/linea-base.json`
está vacía, así que todo error de ruff cuenta como regresión: `ruff` reporta
102 errores y `linea-base.mjs verificar` sale con `1`, con lo que la puerta
bloquea (código 2). **Solo el usuario regenera la línea base, y solo a la
baja**; la otra vía es arreglar los 102 errores.

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
   comando.
2. Editar este `SPEC.md` y añadir la entrada del nuevo ciclo **arriba** de los
   anteriores (el más reciente primero), y mover a CERRADO la entrada del
   ciclo que se cierra, anotando el commit.
3. Pedir al Coordinador que ejecute el ciclo sobre la spec.
