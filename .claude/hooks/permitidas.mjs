#!/usr/bin/env node
// Allowlist compartida de rutas escribibles + protocolo de denegación.
//
// Dos conceptos que NO son intercambiables:
//
//   esPermitido → la ruta está dentro de lo que el rol puede escribir DENTRO
//                  del repo. Se consulta para BLOQUEAR.
//   esNeutro     → la ruta está fuera del repo (o en un scratchpad). Se
//                  consulta para NO BLOQUEAR. Una ruta neutra no está
//                  "permitida en el repo": simplemente no es una escritura
//                  prohibida, así que no se toca.
//
// La raíz del repo se resuelve con import.meta.url, nunca con process.cwd()
// ni con process.env.CLAUDE_PROJECT_DIR (esa variable llega vacía en este
// entorno): un hook que arranca con otro cwd debe seguir encontrando el repo.
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

/** Carpetas del repo donde un rol de documentos puede escribir. */
export const PERMITIDAS = [
  ".claude/planes/",
  ".claude/disenos/",
  ".claude/cache/",
  "docs/",
];

/** Excepciones por nombre exacto: entregables de raíz que el ciclo produce. */
export const ARCHIVOS_PERMITIDOS = ["SPEC.md"];

/** Rutas fuera del repo que nunca cuentan como escritura prohibida. */
export const NEUTRALES = [
  "/dev/null",
  "/dev/stdout",
  "/dev/stderr",
  "/dev/fd/",
  "/proc/",
  "/sys/",
  "/tmp/",
  "/var/tmp/",
];

/** Resuelve un destino (relativo o absoluto) contra la raíz del repo. */
export function aAbsoluto(destino) {
  if (typeof destino !== "string" || !destino) return "";
  return isAbsolute(destino) ? resolve(destino) : resolve(RAIZ, destino);
}

/**
 * Ruta relativa a RAIZ con separadores "/".
 * Si el destino queda fuera del repo, devuelve algo que empieza por "../".
 */
export function aRelativo(destino) {
  const absoluto = aAbsoluto(destino);
  if (!absoluto) return "";
  return relative(RAIZ, absoluto).split("\\").join("/");
}

/**
 * ¿La ruta está en las carpetas o entregables que el rol puede escribir?
 * "SPEC.md" casa EXACTO: "SPEC.md.bak" no cuela.
 */
export function esPermitido(destino) {
  const rel = aRelativo(destino);
  if (!rel) return false;
  if (ARCHIVOS_PERMITIDOS.includes(rel)) return true;
  return PERMITIDAS.some((carpeta) => rel.startsWith(carpeta));
}

/**
 * ¿La ruta está en una zona neutra (/tmp, /dev, scratchpad…)?
 * Se consulta para NO bloquear, nunca para autorizar escritura dentro del repo.
 */
export function esNeutro(destino, { scratchpad } = {}) {
  const absoluto = aAbsoluto(destino);
  if (!absoluto) return false;

  if (NEUTRALES.some((prefijo) => coincideConPrefijo(absoluto, prefijo))) return true;

  if (typeof scratchpad === "string" && scratchpad) {
    const base = resolve(scratchpad);
    if (absoluto === base || absoluto.startsWith(`${base}/`)) return true;
  }

  return false;
}

function coincideConPrefijo(absoluto, prefijo) {
  const base = resolve(prefijo);
  // El prefijo ORIGINAL decide si es carpeta: resolve() ya le quitó la barra
  // final, así que hay que mirar el prefijo, no la ruta resuelta.
  if (prefijo.endsWith("/")) {
    return absoluto === base || absoluto.startsWith(`${base}/`);
  }
  return absoluto === base;
}

/**
 * Salida estándar de denegación de Claude Code (JSON por stdout).
 * El motivo se lee tal cual en el mensaje del agente.
 */
export function denegar(motivo) {
  console.log(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: motivo,
      },
    }),
  );
}
