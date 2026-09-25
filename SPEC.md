# Spec activa del ciclo en curso

> Esta `SPEC.md` apunta al ciclo activo. Cada ciclo tiene su spec detallada en
> `.claude/planes/spec-ciclo-N-*.md`; este archivo es solo el índice que lee
> el Coordinador por defecto.

## Estado actual

**Sin ciclo activo todavía.** El sistema de agentes autónomos se terminó de
implementar y todavía no se ha ejecutado el primer `/ciclo`. La spec fundacional
del proyecto está en [`README.md`](README.md) (flujo EML → preview → envío
masivo vía Outlook COM, arquitectura hexagonal, stack Python/uv, Airtable como
fuente de contactos).

Cuando se abra el primer ciclo, este archivo apuntará a su spec detallada con
el formato:

```markdown
## Ciclo 1 — [título corto]

**Spec detallada:** `.claude/planes/spec-ciclo-1-<slug>.md`

**Resumen**: [1-2 frases]

**Criterio de hecho**: `node .claude/hooks/puerta-calidad.mjs completa` en
verde y verificación manual del flujo descrito en la spec.
```

## Cómo abrir un ciclo nuevo

1. Crear `.claude/planes/spec-ciclo-N-<slug>.md` con la spec detallada de la
   feature a implementar (formato libre, pero debe terminar con un criterio
   de hecho medible con un comando).
2. Editar este `SPEC.md` y añadir la entrada del nuevo ciclo arriba de los
   anteriores (el más reciente primero).
3. Pedir al Coordinador que ejecute el ciclo sobre la spec.
