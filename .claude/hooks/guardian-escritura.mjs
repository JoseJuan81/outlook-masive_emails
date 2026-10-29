#!/usr/bin/env node
// Guardián de escritura — hook PreToolUse para los roles que producen
// documentos (planificador, disenador-web).
//
// Esos roles llevan Write porque tienen que escribir su plan o su spec, pero
// Write no sabe de carpetas y un prompt es una sugerencia, no un bloqueo.
// Este hook es el bloqueo.
//
// Se declara en el frontmatter del agente, no en settings.json, para que solo
// aplique mientras ese agente está activo.
//
// Regla: se deniega SOLO cuando la ruta no es ni permitida ni neutra. Ante la
// duda, se permite.
//
// INVARIANTE DE NO-COLISIÓN: este hook solo habla cuando el destino NO es una
// ruta permitida. validar-plan.mjs solo habla cuando el destino SÍ es
// .claude/planes/*.json, que es ruta permitida. Jamás hablan los dos en el
// mismo evento.
import { readFileSync } from "node:fs";
import {
  PERMITIDAS,
  ARCHIVOS_PERMITIDOS,
  aAbsoluto,
  aRelativo,
  esPermitido,
  esNeutro,
  denegar,
} from "./permitidas.mjs";

/** Herramientas que escriben en disco. MultiEdit faltaba y era una fuga real. */
const HERRAMIENTAS = ["Write", "Edit", "MultiEdit", "NotebookEdit"];

let entrada;
try {
  entrada = JSON.parse(readFileSync(0, "utf8") || "{}");
} catch {
  process.stderr.write(
    "Guardián de escritura: la entrada del hook no es JSON válido; no hay nada que juzgar, se permite.\n",
  );
  process.exit(0);
}

const herramienta = entrada?.tool_name ?? "";
if (!HERRAMIENTAS.includes(herramienta)) process.exit(0);

const destino = entrada?.tool_input?.file_path ?? entrada?.tool_input?.notebook_path;
if (typeof destino !== "string" || !destino) process.exit(0);

if (esPermitido(destino)) process.exit(0);
if (esNeutro(destino)) process.exit(0);

const rel = aRelativo(destino);
const mostrado = rel.startsWith("../") ? `${aAbsoluto(destino)} (fuera del repo)` : rel;

const rutas = [...PERMITIDAS.map((c) => `  - ${c}`), ...ARCHIVOS_PERMITIDOS.map((a) => `  - ${a}`)];

denegar(
  `Guardián de escritura: bloqueado el intento de escribir en «${mostrado}».\n\n` +
    `Tu rol produce DOCUMENTOS, no código de producción. Solo puedes escribir en:\n` +
    `${rutas.join("\n")}\n\n` +
    `Si tu tarea parece exigir tocar código de producción, es que la tarea está mal ` +
    `asignada: descríbelo en tu entregable y deja que el orquestador se lo pase al rol ` +
    `«desarrollador», que es el único que escribe código en este repo (domain/, ` +
    `application/, ports/, infrastructure/, web/, main.py, send_from_staging.py). ` +
    `No busques una ruta alternativa para escribirlo tú.`,
);

process.exit(0);
