#!/usr/bin/env node
// Validador de schema de los planes — hook PreToolUse con matcher Write.
//
// Convierte el schema de los planes en algo ejecutable: hasta ahora estaba
// documentado en CLAUDE.md y AGENTS_SYSTEM.md, pero nadie lo comprobaba.
//
// Sólo valida planes JSON: un .md no se valida.
//
// INVARIANTE DE NO-COLISIÓN: este hook sólo habla cuando el destino es
// .claude/plans/*.json, que es una ruta PERMITIDA. Por tanto
// guardian-escritura.mjs nunca hablará en el mismo evento (su regla es
// justamente la contraria: habla cuando la ruta NO es permitida). Los dos
// hooks pueden registrarse juntos en el mismo matcher sin que se pisen.
import { existsSync, readFileSync } from "node:fs";
import { aAbsoluto, aRelativo, denegar } from "./permitidas.mjs";

/** Claves obligatorias de nivel superior del plan. */
const CLAVES_RAIZ = [
  "spec",
  "objetivo",
  "resumen_causa_raiz",
  "archivos_a_tocar",
  "olas",
  "restricciones_plataforma_heredadas",
  "riesgos_y_contradicciones_reportadas_al_coordinador",
];

/** Claves obligatorias de cada tarea. */
const CLAVES_TAREA = [
  "id",
  "rol",
  "titulo",
  "descripcion",
  "archivos",
  "criterios_de_aceptacion",
];

let entrada;
try {
  entrada = JSON.parse(readFileSync(0, "utf8") || "{}");
} catch {
  process.stderr.write(
    "Validador de plan: la entrada del hook no es JSON válido; no hay nada que validar, se permite.\n",
  );
  process.exit(0);
}

const herramienta = entrada?.tool_name ?? "";
if (herramienta !== "Write") process.exit(0);

const destino = entrada?.tool_input?.file_path;
if (typeof destino !== "string" || !destino) process.exit(0);

// Sólo los planes JSON de .claude/planes/ se validan.
const rel = aRelativo(destino);
if (!rel.startsWith(".claude/planes/") || !rel.endsWith(".json")) process.exit(0);

/* ───────────────────────────── contenido a validar ────────────────────────── */

let contenido = null;
if (typeof entrada?.tool_input?.content === "string") {
  contenido = entrada.tool_input.content;
} else {
  const ruta = aAbsoluto(destino);
  if (existsSync(ruta)) {
    try {
      contenido = readFileSync(ruta, "utf8");
    } catch {
      contenido = null;
    }
  }
}

// Sin contenido no hay nada que validar.
if (contenido === null) process.exit(0);

/* ─────────────────────────────── validaciones ─────────────────────────────── */

let plan;
try {
  plan = JSON.parse(contenido);
} catch (error) {
  denegar(
    `Validador de plan: «${rel}» no es JSON válido.\n\n` +
      `  ${error.message}\n\n` +
      `Un plan debe ser un JSON parseable: es lo que consumen el resto de agentes y la puerta ` +
      `de calidad. Corrige el JSON y vuelve a escribir el plan.`,
  );
  process.exit(0);
}

const errores = [];

if (plan === null || typeof plan !== "object" || Array.isArray(plan)) {
  errores.push("El plan debe ser un objeto JSON de nivel superior.");
} else {
  const faltanRaiz = CLAVES_RAIZ.filter((clave) => !(clave in plan));
  if (faltanRaiz.length) {
    errores.push(
      `Faltan claves de nivel superior: ${faltanRaiz.join(", ")}. ` +
        `Se requieren: ${CLAVES_RAIZ.join(", ")}.`,
    );
  }

  const sobran = Object.keys(plan).filter((clave) => !CLAVES_RAIZ.includes(clave));
  if (sobran.length) {
    // Tolerancia: el schema no se inventa, las claves extra solo se avisan.
    process.stderr.write(
      `Validador de plan: «${rel}» tiene claves de nivel superior no documentadas: ` +
        `${sobran.join(", ")}. Se permiten, pero revisa que sean intencionadas.\n`,
    );
  }

  const tareas = buscarTareas(plan.olas);
  if (!tareas.length) {
    errores.push(
      "No se encontró ninguna tarea dentro de «olas». " +
        "Cada tarea necesita: id, rol, titulo, descripcion, archivos, criterios_de_aceptacion.",
    );
  }

  for (const tarea of tareas) {
    const faltan = CLAVES_TAREA.filter((clave) => !(clave in tarea.nodo));
    if (faltan.length) {
      errores.push(
        `La tarea${tarea.etiqueta ? ` «${tarea.etiqueta}»` : ""} (${tarea.camino}) ` +
          `no tiene: ${faltan.join(", ")}. Se requieren: ${CLAVES_TAREA.join(", ")}.`,
      );
      continue;
    }

    const criterios = tarea.nodo.criterios_de_aceptacion;
    if (!Array.isArray(criterios) || criterios.length === 0) {
      errores.push(
        `La tarea${tarea.etiqueta ? ` «${tarea.etiqueta}»` : ""} (${tarea.camino}) ` +
          `tiene «criterios_de_aceptacion» vacío o que no es una lista: ` +
          `un criterio sin comprobar con un comando no es un criterio.`,
      );
    }
  }
}

if (errores.length) {
  denegar(
    `Validador de plan: «${rel}» no cumple el schema de los planes.\n\n` +
      `${errores.map((e) => `  - ${e}`).join("\n")}\n\n` +
      `Corrige el plan y vuelve a escribirlo. Si el schema debe cambiar, eso lo decide el ` +
      `Coordinador, no el agente que escribe el plan.`,
  );
}

process.exit(0);

/* ────────────────────────────── búsqueda de tareas ─────────────────────────── */

/**
 * Busca tareas recursivamente dentro de «olas»: no se asume la forma exacta
 * del anidamiento (olas[].tareas[], olas[].subtareas[], …).
 *
 * Una tarea es un objeto que tiene alguna clave propia de tarea
 * (id/rol/titulo/descripcion/archivos/criterios_de_aceptacion) o que cuelga
 * de una clave con nombre de tarea («tareas», «task», «subtareas»).
 */
function buscarTareas(nodo, camino = "olas", clavePadre = "olas") {
  const encontradas = [];

  const visitar = (valor, rutaActual, clave) => {
    if (Array.isArray(valor)) {
      valor.forEach((elemento, indice) => visitar(elemento, `${rutaActual}[${indice}]`, clave));
      return;
    }
    if (!valor || typeof valor !== "object") return;

    const esTarea = pareceTarea(valor, clave);
    if (esTarea) {
      encontradas.push({ nodo: valor, camino: rutaActual, etiqueta: valor.id ?? valor.titulo });
      return; // dentro de una tarea no se busca otra tarea
    }

    for (const [subclave, subvalor] of Object.entries(valor)) {
      visitar(subvalor, `${rutaActual}.${subclave}`, subclave);
    }
  };

  visitar(nodo, camino, clavePadre);
  return encontradas;
}

function pareceTarea(nodo, clavePadre) {
  if (/tarea|task/i.test(clavePadre ?? "")) return true;
  return CLAVES_TAREA.some((clave) => clave in nodo);
}
