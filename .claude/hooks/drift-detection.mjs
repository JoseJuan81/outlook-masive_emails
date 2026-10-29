#!/usr/bin/env node
// Drift detection — comprueba que lo que declara un plan sigue existiendo en el código.
//
//   node .claude/hooks/drift-detection.mjs verificar [plan]   → modo estricto (deriva = fallo)
//   node .claude/hooks/drift-detection.mjs heuristico [plan]  → modo informativo (siempre 0)
//
// Códigos de salida: 0 correcto · 1 deriva · 2 error de ejecución · 3 no aplica.
//
// Modo estricto: verifica las referencias declaradas, de la forma
//   `fichero:línea ← símbolo`
// Si el fichero no existe, o el símbolo no aparece en el código, hay deriva.
//
// Modo heurístico: lista los símbolos que el plan menciona y que no se hallan
// en el código. No es un fallo: un símbolo puede ser nuevo y lo va a crear otro
// agente. Por eso este modo siempre sale con 0.
//
// Filtro de FORMA (no lista negra de palabras): un candidato debe parecer un
// identificador de Python — snake_case, `_privado` o PascalCase estricto — y
// no puede ser una ruta ni una keyword/builtin.
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PLANES_DIR = join(RAIZ, ".claude/planes");
const VERIFICACION = join(RAIZ, ".claude/verificacion.json");

const EXCLUIDOS = new Set([
  ".git",
  ".venv",
  "node_modules",
  "staging",
  "logs",
  "preview",
  "Templates",
  ".claude",
  "html",
  "__pycache__",
  "site-packages",
]);

const RAICES_FIJAS = ["domain", "application", "ports", "infrastructure", "web"];

const PALABRAS_RESERVADAS = new Set([
  // keywords de Python
  "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class",
  "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global",
  "if", "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return",
  "try", "while", "with", "yield", "match", "case",
  // builtins
  "abs", "all", "any", "ascii", "bin", "bool", "breakpoint", "bytearray", "bytes", "callable",
  "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir", "divmod", "enumerate",
  "eval", "exec", "filter", "float", "format", "frozenset", "getattr", "globals", "hasattr",
  "hash", "help", "hex", "id", "input", "int", "isinstance", "issubclass", "iter", "len",
  "list", "locals", "map", "max", "memoryview", "min", "next", "object", "oct", "open", "ord",
  "pow", "print", "property", "range", "repr", "reversed", "round", "set", "setattr", "slice",
  "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
  // convenciones habituales
  "self", "cls", "args", "kwargs", "init", "main",
]);

const LONGITUD_MINIMA = 4;
const LONGITUD_MAXIMA = 60;

const RE_TOKEN = /[A-Za-z0-9_]+(?:[./][A-Za-z0-9_]+)*/g;
const RE_REFERENCIA =
  /`?([A-Za-z0-9_./-]+\.(?:py|md|json)):(\d+)`?\s*(?:←|->|<-|=>)\s*`?([A-Za-z_][A-Za-z0-9_.]*)`?/g;
const RE_REFERENCIA_SIN_SIMBOLO = /`?([A-Za-z0-9_./-]+\.(?:py|md|json)):(\d+)`?/g;

const CLAVES_ESCANEABLES = /descripcion|criterios|titulo|resumen|detalle|que.?hacer|nota/i;

/** Raíces configuradas en .claude/verificacion.json → "drift": {"raices": [...]}. */
function raicesConfiguradas() {
  if (!existsSync(VERIFICACION)) return [];
  let configuracion;
  try {
    configuracion = JSON.parse(readFileSync(VERIFICACION, "utf8"));
  } catch {
    return [];
  }
  const bloque = configuracion?.drift;
  const lista = Array.isArray(bloque) ? bloque : (bloque?.raices ?? []);
  if (!Array.isArray(lista)) return [];
  return lista.filter((r) => typeof r === "string" && r.trim() !== "");
}

function tienePython(directorio) {
  let entradas;
  try {
    entradas = readdirSync(directorio, { withFileTypes: true });
  } catch {
    return false;
  }
  return entradas.some((e) => e.isFile() && e.name.endsWith(".py"));
}

/** Raíces de búsqueda: configuradas si las hay; si no, auto-detectadas. */
function raicesDeBusqueda() {
  const configuradas = raicesConfiguradas();
  const bases = configuradas.length > 0 ? configuradas : autoDetectadas();
  return [...new Set([...bases, ...RAICES_FIJAS])];
}

function autoDetectadas() {
  let entradas;
  try {
    entradas = readdirSync(RAIZ, { withFileTypes: true });
  } catch {
    return [];
  }
  return entradas
    .filter((e) => e.isDirectory() && !EXCLUIDOS.has(e.name))
    .filter((e) => tienePython(join(RAIZ, e.name)))
    .map((e) => e.name);
}

/** Índice en memoria: ruta relativa → contenido de cada .py del repo. */
function construirIndice(raices) {
  const indice = new Map();

  const anadir = (rutaAbsoluta) => {
    if (!rutaAbsoluta.endsWith(".py")) return;
    try {
      indice.set(relative(RAIZ, rutaAbsoluta).split("\\").join("/"), readFileSync(rutaAbsoluta, "utf8"));
    } catch {
      /* fichero ilegible: se ignora */
    }
  };

  for (const raiz of raices) {
    const absoluta = isAbsolute(raiz) ? raiz : join(RAIZ, raiz);
    if (!existsSync(absoluta)) continue;
    if (statSync(absoluta).isDirectory()) recorrer(absoluta, anadir);
    else anadir(absoluta);
  }

  // Los .py sueltos de la raíz (main.py, preview.py, …) siempre se indexan.
  for (const entrada of readdirSync(RAIZ, { withFileTypes: true })) {
    if (entrada.isFile() && entrada.name.endsWith(".py")) {
      anadir(join(RAIZ, entrada.name));
    }
  }

  return indice;
}

function recorrer(directorio, anadir) {
  let entradas;
  try {
    entradas = readdirSync(directorio, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entrada of entradas) {
    const ruta = join(directorio, entrada.name);
    if (entrada.isDirectory()) {
      if (EXCLUIDOS.has(entrada.name) || entrada.name === "__pycache__") continue;
      recorrer(ruta, anadir);
    } else if (entrada.isFile()) {
      anadir(ruta);
    }
  }
}

/* ------------------------------------------------------------------ */
/* Filtro de forma                                                     */
/* ------------------------------------------------------------------ */

function parteValida(parte) {
  if (/^[a-z_][a-z0-9_]*$/.test(parte)) return true; // snake_case y _privado
  // PascalCase estricto: empieza en mayúscula, sin `_`, y con al menos un
  // cambio minúscula→mayúscula (AirtableRepository sí; Gate, Cobertura no).
  if (/^[A-Z][A-Za-z0-9]*$/.test(parte) && /[a-z][A-Z]/.test(parte)) return true;
  return false;
}

/** ¿El token tiene forma de símbolo de Python? */
function formaValida(token) {
  if (typeof token !== "string") return false;
  if (token.length < LONGITUD_MINIMA || token.length > LONGITUD_MAXIMA) return false;
  if (PALABRAS_RESERVADAS.has(token)) return false;
  if (/\.(py|md|json)$/i.test(token)) return false; // es una ruta, no un símbolo
  const partes = token.split(".");
  return partes.every(parteValida);
}

/** Extrae candidatos con forma de símbolo del texto de un plan. */
function extraerSimbolos(texto) {
  if (!texto) return [];
  const candidatos = new Set();
  for (const match of texto.matchAll(RE_TOKEN)) {
    const token = match[0];
    if (token.includes("/")) continue; // ruta
    if (/\.(py|md|json)$/i.test(token)) continue; // nombre de fichero
    if (!formaValida(token)) continue;
    candidatos.add(token);
  }
  return [...candidatos];
}

/* ------------------------------------------------------------------ */
/* Planes                                                              */
/* ------------------------------------------------------------------ */

function nombreLegible(ruta) {
  const relativa = relative(RAIZ, ruta);
  return relativa.startsWith("..") ? ruta : relativa;
}

function planesDisponibles(rutaAlterna) {
  if (rutaAlterna) {
    const absoluta = isAbsolute(rutaAlterna) ? rutaAlterna : join(RAIZ, rutaAlterna);
    if (!existsSync(absoluta)) {
      console.error(`No existe el plan ${absoluta}`);
      process.exit(2);
    }
    return [absoluta];
  }
  if (!existsSync(PLANES_DIR)) return [];
  return readdirSync(PLANES_DIR)
    .filter((f) => f.endsWith(".md") || f.endsWith(".json"))
    .map((f) => join(PLANES_DIR, f))
    .filter((f) => statSync(f).isFile());
}

/** Texto plano de un plan: el .md entero o los strings relevantes del .json. */
function textoDelPlan(ruta) {
  const contenido = readFileSync(ruta, "utf8");
  if (!ruta.endsWith(".json")) return contenido;
  try {
    const datos = JSON.parse(contenido);
    return aplanar(datos)
      .filter(({ camino }) => camino.some((c) => CLAVES_ESCANEABLES.test(c)))
      .map(({ texto }) => texto)
      .join("\n");
  } catch (error) {
    console.error(`El plan ${ruta} no es JSON válido: ${error.message}`);
    process.exit(2);
  }
}

function aplanar(obj, camino = []) {
  if (obj == null) return [];
  if (typeof obj === "string") return [{ texto: obj, camino }];
  if (Array.isArray(obj)) return obj.flatMap((v, i) => aplanar(v, [...camino, String(i)]));
  if (typeof obj === "object") {
    return Object.entries(obj).flatMap(([k, v]) => aplanar(v, [...camino, k]));
  }
  return [];
}

/* ------------------------------------------------------------------ */
/* Referencias del modo estricto                                        */
/* ------------------------------------------------------------------ */

/** Extrae `{fichero, linea, simbolo}` de las referencias declaradas. */
function extraerReferencias(texto) {
  const referencias = [];
  const vistos = new Set();

  const anadir = (fichero, linea, simbolo) => {
    const clave = `${fichero}:${linea}:${simbolo ?? ""}`;
    if (vistos.has(clave)) return;
    vistos.add(clave);
    referencias.push({ fichero, linea: Number(linea), simbolo: simbolo ?? null });
  };

  for (const match of texto.matchAll(RE_REFERENCIA)) {
    anadir(match[1], match[2], match[3]);
  }
  for (const match of texto.matchAll(RE_REFERENCIA_SIN_SIMBOLO)) {
    // Una referencia con símbolo ya cubre su `fichero:línea`: no se cuenta dos veces.
    const yaCubierta = referencias.some(
      (r) => r.fichero === match[1] && r.linea === Number(match[2]) && r.simbolo,
    );
    if (yaCubierta) continue;
    anadir(match[1], match[2], null);
  }
  return referencias;
}

/** Resuelve la ruta de una referencia contra el índice. */
function resolverFichero(referencia, indice) {
  const limpia = referencia.replace(/^\.\//, "");
  if (indice.has(limpia)) return limpia;
  for (const ruta of indice.keys()) {
    if (ruta === limpia || ruta.endsWith(`/${limpia}`)) return ruta;
  }
  return null;
}

function simboloPresente(simbolo, indice, fichero) {
  const patron = new RegExp(`\\b${simbolo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`);
  if (fichero && indice.has(fichero) && patron.test(indice.get(fichero))) {
    return { encontrado: true, donde: fichero };
  }
  for (const [ruta, contenido] of indice) {
    if (patron.test(contenido)) return { encontrado: true, donde: ruta };
  }
  return { encontrado: false, donde: null };
}

/* ------------------------------------------------------------------ */
/* Subcomandos                                                         */
/* ------------------------------------------------------------------ */

const [, , accionRaw, rutaAlterna] = process.argv;

function modoVerificar(ruta) {
  const planes = planesDisponibles(ruta);
  if (planes.length === 0) {
    console.log(
      "No aplica: no hay planes que comprobar.\n" +
        "  Se esperan planes en .claude/planes/ (.md o .json), o una ruta alterna como argumento.",
    );
    process.exit(3);
  }

  const indice = construirIndice(raicesDeBusqueda());
  const derivas = [];
  let comprobadas = 0;

  for (const plan of planes) {
    const referencias = extraerReferencias(textoDelPlan(plan));
    if (referencias.length === 0) continue;
    const nombrePlan = nombreLegible(plan);

    for (const referencia of referencias) {
      comprobadas++;
      const fichero = resolverFichero(referencia.fichero, indice);
      if (!fichero) {
        derivas.push({
          plan: nombrePlan,
          referencia,
          motivo: `el fichero ${referencia.fichero} no existe`,
        });
        continue;
      }
      if (!referencia.simbolo) continue; // solo se comprobaba la existencia del fichero
      const busqueda = simboloPresente(referencia.simbolo, indice, fichero);
      if (!busqueda.encontrado) {
        derivas.push({
          plan: nombrePlan,
          referencia,
          motivo: `el símbolo ${referencia.simbolo} no aparece en ${fichero}`,
        });
      } else if (busqueda.donde !== fichero) {
        console.log(
          `  aviso  ${fichero}:${referencia.linea} ← ${referencia.simbolo} ` +
            `(encontrado en ${busqueda.donde})`,
        );
      }
    }
  }

  if (comprobadas === 0) {
    console.log(
      "No aplica: hay planes pero ninguna referencia declarada que comprobar.\n" +
        "  Formato esperado: `fichero:línea ← símbolo`.",
    );
    process.exit(3);
  }

  if (derivas.length === 0) {
    console.log(
      `Sin drift: ${comprobadas} referencia(s) comprobada(s) en ${planes.length} plan(es).`,
    );
    process.exit(0);
  }

  console.error(
    `Drift detectado: ${derivas.length} referencia(s) rotas:\n` +
      derivas
        .map(
          (d) =>
            `  ${d.plan}: ${d.referencia.fichero}:${d.referencia.linea}` +
            `${d.referencia.simbolo ? ` ← ${d.referencia.simbolo}` : ""}\n` +
            `    ${d.motivo}`,
        )
        .join("\n"),
  );
  process.exit(1);
}

function modoHeuristico(ruta) {
  const planes = planesDisponibles(ruta);
  if (planes.length === 0) {
    console.log(
      "No aplica: no hay planes que revisar. Lista de candidatos no hallados: vacía (0).\n" +
        "  Se esperan planes en .claude/planes/ (.md o .json), o una ruta alterna como argumento.",
    );
    process.exit(0);
  }

  const indice = construirIndice(raicesDeBusqueda());
  const totalIndice = indice.size;

  for (const plan of planes) {
    const nombrePlan = nombreLegible(plan);
    const candidatos = extraerSimbolos(textoDelPlan(plan));
    const noHallados = [];
    for (const candidato of candidatos) {
      const busqueda = simboloPresente(candidato, indice, null);
      if (!busqueda.encontrado) noHallados.push(candidato);
    }
    console.log(
      `${nombrePlan}: ${candidatos.length} candidato(s), ${noHallados.length} no hallados en el código.`,
    );
    for (const simbolo of noHallados) console.log(`  ${simbolo}`);
  }

  console.log(
    `\nModo heurístico: informativo, no falla. Índice: ${totalIndice} fichero(s) .py. ` +
      "Un símbolo no hallado puede ser nuevo (lo crea otro agente).",
  );
  process.exit(0);
}

if (accionRaw === "verificar") {
  modoVerificar(rutaAlterna);
} else if (accionRaw === "heuristico") {
  modoHeuristico(rutaAlterna);
} else if (accionRaw) {
  // Compatibilidad: una ruta suelta se trata como modo heurístico sobre ese plan.
  modoHeuristico(accionRaw);
} else {
  console.error(
    "Uso:\n" +
      "  node .claude/hooks/drift-detection.mjs verificar [ruta-a-plan]\n" +
      "  node .claude/hooks/drift-detection.mjs heuristico [ruta-a-plan]",
  );
  process.exit(2);
}
