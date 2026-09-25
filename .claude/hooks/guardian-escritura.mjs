#!/usr/bin/env node
// Guardián de escritura — hook PreToolUse para `planificador` y `diseñador-web`.
//
// Esos dos agentes producen documentos, no código. Llevan `Write` porque tienen
// que escribir su plan y su spec, pero `Write` no sabe de carpetas y un prompt es
// una sugerencia, no un bloqueo. Este hook es el bloqueo.
//
// Se declara en el frontmatter del agente, no en settings.json, para que solo
// aplique mientras ese agente está activo.
//
// Salida: JSON con permissionDecision deny (el motivo llega al agente).
import { readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";

const RAIZ = process.env.CLAUDE_PROJECT_DIR ?? process.cwd();

/** Únicas rutas donde un agente de documentos puede escribir. */
const PERMITIDAS = [".claude/planes/", ".claude/disenos/", "docs/"];

/** Excepciones por nombre exacto: entregables de raíz que el ciclo sí produce. */
const ARCHIVOS_PERMITIDOS = ["SPEC.md"];

let entrada;
try {
  entrada = JSON.parse(readFileSync(0, "utf8") || "{}");
} catch {
  process.exit(0); // sin entrada parseable no hay nada que juzgar
}

const herramienta = entrada.tool_name ?? "";
if (!["Write", "Edit", "NotebookEdit"].includes(herramienta)) process.exit(0);

const destino = entrada.tool_input?.file_path ?? entrada.tool_input?.notebook_path;
if (!destino) process.exit(0);

const absoluto = isAbsolute(destino) ? destino : resolve(RAIZ, destino);
const rel = relative(RAIZ, absoluto).split("\\").join("/");

const permitido =
  ARCHIVOS_PERMITIDOS.includes(rel) || PERMITIDAS.some((carpeta) => rel.startsWith(carpeta));

if (permitido) process.exit(0);

const fuera = rel.startsWith("..") ? `${absoluto} (fuera del repo)` : rel;

console.log(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason:
        `Guardián de escritura: bloqueado el intento de escribir en ${fuera}.\n\n` +
        `Tu rol produce DOCUMENTOS, no código. Solo puedes escribir en: ` +
        `${PERMITIDAS.join(", ")} o ${ARCHIVOS_PERMITIDOS.join(", ")}.\n\n` +
        `Si tu tarea parece exigir tocar código, es que la tarea está mal asignada: ` +
        `descríbelo en tu entregable y deja que el orquestador se lo pase a "desarrollador", ` +
        `que es el único rol que escribe en src/. No busques una ruta alternativa para ` +
        `escribirlo tú.`,
    },
  }),
);
process.exit(0);