#!/usr/bin/env node
// Línea base congelada de lint — «no empeores el repo», comprobable por comando.
//
//   node .claude/hooks/linea-base.mjs verificar   → 0 si nadie empeoró, 1 si sí
//   node .claude/hooks/linea-base.mjs generar     → regenera el archivo (SOLO el usuario)
//
// Política de archivos nuevos (§5.6): un archivo que no está en la línea base
// tiene presupuesto CERO. `base[archivo] ?? 0`. Todo lo nuevo nace limpio.
//
// Consecuencia que hay que anticipar en los refactors: mover código con errores
// heredados a un archivo nuevo convierte esos errores en regresión. El código
// sucio se queda donde está, o se limpia en una tarea aparte.
//
// La línea base solo se regenera A LA BAJA y por decisión explícita del usuario.
// Un agente que la regenera para pasar la puerta está falsificando el resultado.
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const ARCHIVO = join(RAIZ, ".claude/linea-base.json");
const INFORME = join(RAIZ, ".claude/cache/eslint-informe.json");
// El informe va a un ARCHIVO, no a stdout: npx u otros pueden imprimir avisos
// por stdout que corromperían el JSON.
const COMANDO_LINT =
  `npx eslint . -f json -o ${JSON.stringify(INFORME)} ` +
  "--cache --cache-location .claude/cache/eslint-base";

/** Errores de lint por archivo, en rutas relativas a la raíz del repo. */
function medir() {
  mkdirSync(dirname(INFORME), { recursive: true });
  rmSync(INFORME, { force: true });
  try {
    execSync(COMANDO_LINT, {
      cwd: RAIZ,
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, FORCE_COLOR: "0" },
    });
  } catch (error) {
    // eslint sale con código 1 cuando hay errores: el informe se escribe igual.
    if (!existsSync(INFORME)) {
      console.error(`No se pudo ejecutar el lint:\n${error.stderr ?? error.message}`);
      process.exit(2);
    }
  }

  if (!existsSync(INFORME)) {
    console.error(`El lint no generó el informe ${INFORME}.`);
    process.exit(2);
  }

  const informe = JSON.parse(readFileSync(INFORME, "utf8"));
  const porArchivo = {};
  for (const entrada of informe) {
    if (entrada.errorCount > 0) {
      porArchivo[relative(RAIZ, entrada.filePath)] = entrada.errorCount;
    }
  }
  return porArchivo;
}

function cargar() {
  if (!existsSync(ARCHIVO)) return { archivos: {} };
  return JSON.parse(readFileSync(ARCHIVO, "utf8"));
}

const accion = process.argv[2];

if (accion === "generar") {
  const archivos = medir();
  const previo = cargar().archivos ?? {};
  const subidas = Object.entries(archivos).filter(([f, n]) => n > (previo[f] ?? 0));

  if (subidas.length > 0 && existsSync(ARCHIVO)) {
    console.error(
      "La línea base solo se regenera A LA BAJA. Estos archivos empeoraron respecto a la actual:\n" +
        subidas.map(([f, n]) => `  ${f}: ${previo[f] ?? 0} → ${n}`).join("\n") +
        "\n\nArregla los errores nuevos, o borra .claude/linea-base.json a mano si de verdad " +
        "quieres una línea base peor.",
    );
    process.exit(1);
  }

  const total = Object.values(archivos).reduce((a, b) => a + b, 0);
  writeFileSync(
    ARCHIVO,
    JSON.stringify(
      {
        _comentario:
          "Errores de lint heredados POR ARCHIVO. Generado midiendo este repo, nunca copiado. " +
          "Un archivo ausente tiene presupuesto CERO. Solo se regenera a la baja y por " +
          "decisión del usuario: node .claude/hooks/linea-base.mjs generar",
        generado: new Date().toISOString(),
        comando: COMANDO_LINT,
        totalErrores: total,
        archivos,
      },
      null,
      2,
    ) + "\n",
  );
  console.log(
    `Línea base generada: ${total} errores en ${Object.keys(archivos).length} archivo(s).` +
      (total === 0 ? "\nEl repo está limpio: el presupuesto es cero en TODO archivo." : ""),
  );
  process.exit(0);
}

if (accion === "verificar") {
  const base = cargar().archivos ?? {};
  const actual = medir();
  const regresiones = [];

  for (const [archivo, errores] of Object.entries(actual)) {
    const permitido = base[archivo] ?? 0; // archivo nuevo → presupuesto cero
    if (errores > permitido) regresiones.push({ archivo, permitido, errores });
  }

  if (regresiones.length === 0) {
    const mejoras = Object.entries(base).filter(([f, n]) => (actual[f] ?? 0) < n);
    console.log(
      `Línea base respetada. ${Object.keys(actual).length} archivo(s) con errores, ninguno por ` +
        `encima de su presupuesto.` +
        (mejoras.length ? ` ${mejoras.length} archivo(s) mejoraron.` : ""),
    );
    process.exit(0);
  }

  console.error(
    "REGRESIÓN DE LINT respecto a la línea base congelada:\n\n" +
      regresiones
        .map((r) => `  ${r.archivo}\n    permitido: ${r.permitido}   actual: ${r.errores}`)
        .join("\n") +
      "\n\nArregla los errores. Regenerar la línea base para que esto pase está prohibido: " +
      "solo la regenera el usuario, y solo a la baja.",
  );
  process.exit(1);
}

console.error("Uso: node .claude/hooks/linea-base.mjs [verificar|generar]");
process.exit(2);