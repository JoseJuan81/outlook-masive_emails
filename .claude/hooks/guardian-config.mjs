#!/usr/bin/env node
// Guardián de configuración — hook PreToolUse.
//
// Los agentes vigilados por la puerta de calidad (desarrollador, tester)
// tienen Write/Edit completos: sin este hook podrían reescribir la puerta que
// los juzga (hooks, comandos de verificación, línea base, settings) y
// declararse aprobados a sí mismos.
//
// Solo aplica a los agentes vigilados: la sesión principal y el resto de roles
// pueden corregir la configuración de la puerta.
//
// EXCLUSIÓN DELIBERADA: .claude/agents/ NO está protegido. En una ola
// posterior hay que poder corregir la documentación de los agentes (incluidos
// sus prompts y sus hooks declarados); protegerlo dejaría el sistema
// imposible de arreglar sin intervención manual.
//
// INVARIANTE DE NO-COLISIÓN: este hook y guardian-escritura.mjs pueden hablar
// en el mismo evento, pero cada proceso imprime su propio JSON y Claude Code
// los parsea por separado. Los dos niegan por motivos distintos (config de la
// puerta vs. rutas no permitidas), nunca por la misma ruta.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { RAIZ, aRelativo, denegar } from "./permitidas.mjs";

/** Herramientas que escriben en disco. */
const HERRAMIENTAS = ["Write", "Edit", "MultiEdit", "NotebookEdit"];

/** Configuración de la puerta: rutas exactas (o carpetas) intocables. */
const RUTAS_PROTEGIDAS = [
  ".claude/hooks/",
  ".claude/verificacion.json",
  ".claude/linea-base.json",
  ".claude/settings.json",
  ".claude/settings.local.json",
];

const CONFIG = join(RAIZ, ".claude/verificacion.json");

let entrada;
try {
  entrada = JSON.parse(readFileSync(0, "utf8") || "{}");
} catch {
  process.stderr.write(
    "Guardián de configuración: la entrada del hook no es JSON válido; no hay nada que juzgar, se permite.\n",
  );
  process.exit(0);
}

const herramienta = entrada?.tool_name ?? "";
if (!HERRAMIENTAS.includes(herramienta)) process.exit(0);

const destino = entrada?.tool_input?.file_path ?? entrada?.tool_input?.notebook_path;
if (typeof destino !== "string" || !destino) process.exit(0);

// La lista de agentes vigilados vive en la configuración de la puerta.
let agentesVigilados;
try {
  const config = JSON.parse(readFileSync(CONFIG, "utf8"));
  agentesVigilados = Array.isArray(config.agentesVigilados) ? config.agentesVigilados : [];
} catch {
  process.stderr.write(
    "Guardián de configuración: no se pudo leer .claude/verificacion.json; se permite la escritura (fail-open).\n",
  );
  process.exit(0);
}

// agent_type es el campo `name` del frontmatter del subagente.
const agente = entrada?.agent_type ?? "";
if (!agentesVigilados.includes(agente)) process.exit(0);

const rel = aRelativo(destino);
if (!rel || rel.startsWith("../")) process.exit(0);

const protegida = RUTAS_PROTEGIDAS.some((ruta) =>
  ruta.endsWith("/") ? rel.startsWith(ruta) : rel === ruta,
);
if (!protegida) process.exit(0);

denegar(
  `Guardián de configuración: bloqueado el intento de escribir en «${rel}» por el agente «${agente}».\n\n` +
    `La configuración de la puerta de calidad no se puede reescribir desde un agente vigilado: ` +
    `podrías cambiar los comandos que te juzgan o el estado de la línea base y declararte aprobado.\n\n` +
    `Rutas protegidas:\n${RUTAS_PROTEGIDAS.map((r) => `  - ${r}`).join("\n")}\n\n` +
    `Si el cambio es necesario, descríbelo en tu entregable: corresponde al humano o al ` +
    `Coordinador (sesión principal) aplicarlo.`,
);

process.exit(0);
