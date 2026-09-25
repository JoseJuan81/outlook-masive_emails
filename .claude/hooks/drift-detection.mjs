#!/usr/bin/env node
// Drift detection — verifica que las APIs citadas en un plan existen en el código.
//
// Uso:
//   node .claude/hooks/drift-detection.mjs .claude/planes/<plan>.json
//   node .claude/hooks/drift-detection.mjs verificar       ← escanea todos los planes
//
// Heurísticas:
//   - Extrae identificadores (camelCase / PascalCase / kebab-case) que parezcan
//     símbolos del código, dentro de las descripciones y criterios de cada tarea.
//   - Comprueba cada uno con `grep -r` en `src/` y en `supabase/`.
//   - Si un identificador no aparece en ningún archivo, lo marca como "huérfano".
//
// Esto NO es verificación semántica: una coincidencia falsa-positiva no rompe
// el plan. La intención es cazar el caso "el plan manda a llamar `useCycleData`
// y ese hook no existe", que es el típico quemado de ola.
import { execSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PLANES_DIR = join(RAIZ, ".claude/planes");

const ARG = process.argv[2];

if (!ARG) {
  console.error(
    "Uso:\n" +
      "  node .claude/hooks/drift-detection.mjs <ruta-a-plan.json>\n" +
      "  node .claude/hooks/drift-detection.mjs verificar   (escanea todos los planes)",
  );
  process.exit(2);
}

/** Busca identificadores con pinta de símbolo del código (>=3 chars). */
function extraerSimbolos(texto) {
  if (!texto) return [];
  const set = new Set();
  const regex = /\b([a-z][a-zA-Z0-9]{2,}|_[a-z][a-zA-Z0-9_]{2,}|[A-Z][a-zA-Z0-9]{2,})\b/g;
  let m;
  while ((m = regex.exec(texto)) !== null) {
    const s = m[1];
    // Filtra palabras comunes en español / inglés que no son símbolos.
    const BASURA = new Set([
      "con", "para", "por", "que", "como", "desde", "sobre", "entre",
      "los", "las", "del", "una", "uno", "ser", "sin", "con", "tras",
      "the", "and", "for", "with", "from", "into", "this", "that", "when",
      "use", "uses", "useState", "useEffect",
      "true", "false", "null", "undefined",
      "import", "export", "from", "const", "let", "var", "function",
      "return", "await", "async", "typeof", "instanceof",
      "String", "Number", "Boolean", "Object", "Array",
      "READ", "WRITE", "DELETE", "POST", "GET", "PUT",
      "T1", "T2", "T3", "T4", "T5",
    ]);
    if (BASURA.has(s)) continue;
    if (/^\d/.test(s)) continue;
    set.add(s);
  }
  return [...set];
}

function grepExiste(patron, ruta) {
  try {
    const r = execSync(
      `grep -rln --include='*.ts' --include='*.tsx' --include='*.sql' -F -e ${JSON.stringify(patron)} ${JSON.stringify(ruta)} 2>/dev/null || true`,
      { cwd: RAIZ, encoding: "utf8" },
    );
    return r.trim().length > 0;
  } catch {
    return false;
  }
}

/** Recorre el JSON extrayendo strings. */
function aplanar(obj, camino = []) {
  if (obj == null) return [];
  if (typeof obj === "string") return [{ texto: obj, camino }];
  if (Array.isArray(obj)) {
    return obj.flatMap((v, i) => aplanar(v, [...camino, String(i)]));
  }
  if (typeof obj === "object") {
    return Object.entries(obj).flatMap(([k, v]) => aplanar(v, [...camino, k]));
  }
  return [];
}

function cargar(ruta) {
  if (!existsSync(ruta)) {
    console.error(`No existe ${ruta}`);
    process.exit(2);
  }
  return JSON.parse(readFileSync(ruta, "utf8"));
}

function inspeccionarPlan(json) {
  const huerfanos = [];
  const coincidencias = [];
  const simbolosRevisados = new Set();

  const items = aplanar(json);

  for (const { texto, camino } of items) {
    // Solo nos interesa lo de las descripciones/criterios, no los nombres propios
    // de archivos (rutas) ni los comandos literales.
    if (camino.some((c) => /archivos|criterios/.test(c)) === false) continue;
    const simbolos = extraerSimbolos(texto);
    for (const s of simbolos) {
      if (simbolosRevisados.has(s)) continue;
      simbolosRevisados.add(s);
      const ok =
        grepExiste(s, "src") ||
        grepExiste(s, "supabase/migrations") ||
        grepExiste(s, "src/integrations/supabase/types.ts");
      if (!ok) huerfanos.push(s);
      else coincidencias.push(s);
    }
  }
  return { huerfanos, coincidencias };
}

if (ARG === "verificar") {
  if (!existsSync(PLANES_DIR)) {
    console.error(`No existe ${PLANES_DIR}`);
    process.exit(2);
  }
  const planes = readdirSync(PLANES_DIR).filter((f) => f.endsWith(".json"));
  if (planes.length === 0) {
    console.log("No hay planes en .claude/planes/.");
    process.exit(0);
  }
  let malo = false;
  for (const p of planes) {
    const ruta = join(PLANES_DIR, p);
    const plan = cargar(ruta);
    const { huerfanos } = inspeccionarPlan(plan);
    if (huerfanos.length) {
      malo = true;
      console.error(
        `Drift en ${p}: ${huerfanos.length} símbolo(s) no encontrado(s) en src/ ni supabase/:\n  ` +
          huerfanos.join("\n  "),
      );
    } else {
      console.log(`OK ${p}`);
    }
  }
  process.exit(malo ? 1 : 0);
}

// Modo por archivo
const plan = cargar(ARG);
const { huerfanos, coincidencias } = inspeccionarPlan(plan);

console.log(
  `Símbolos revisados: ${coincidencias.length + huerfanos.length} · ` +
    `coincidencias: ${coincidencias.length} · huerfanos: ${huerfanos.length}`,
);

if (huerfanos.length === 0) {
  console.log("Sin drift.");
  process.exit(0);
}

console.error(
  "Símbolos citados en el plan que NO aparecen en src/ ni supabase/:\n  " +
    huerfanos.join("\n  ") +
    "\n\nNo es necesariamente un error: puede ser un identificador nuevo que la tarea va a crear. " +
    "Pero si esperabas que existiera (un hook, una función, una tabla), es un quemado de ola: " +
    "corrige el plan antes de ejecutarlo.",
);
process.exit(1);