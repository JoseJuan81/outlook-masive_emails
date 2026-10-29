#!/usr/bin/env node
// Checkpoint — tags git para poder volver a un punto concreto antes de cada ola.
//
//   node .claude/hooks/checkpoint.mjs crear <nombre>
//   node .claude/hooks/checkpoint.mjs restaurar <nombre>
//   node .claude/hooks/checkpoint.mjs listar
//   node .claude/hooks/checkpoint.mjs estado
//
// Códigos de salida: 0 correcto · 1 fallo · 2 error de ejecución.
//
// Política:
//   - Los tags llevan prefijo `checkpoint/` para no contaminar el espacio de
//     tags del repo. El usuario da el nombre sin prefijo.
//   - Nunca se hace push: el tag es local.
//   - `restaurar` mueve el puntero de la rama con `git reset --hard` (nunca
//     rebase, amend ni push --force). El tag sobrevive al reset.
//
// Todo se invoca con arrays de argumentos (execFileSync), nunca con una
// cadena de shell: las rutas y los mensajes no se interpolan en el shell.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PREFIJO = "checkpoint/";
const LONGITUD_MAXIMA = 50;
const CARACTERES_PROHIBIDOS = [" ", "/", "~", "^", ":", "?", "*", "[", "\\"];

/** Ejecuta git con un array de argumentos (nunca una cadena de shell). */
function git(args) {
  try {
    const salida = execFileSync("git", args, {
      cwd: RAIZ,
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, GIT_TERMINAL_PROMPT: "0", LC_ALL: "C" },
    });
    return { ok: true, salida: String(salida).trim(), codigo: 0 };
  } catch (error) {
    const salida =
      `${error.stdout ?? ""}${error.stderr ?? ""}`.trim() || String(error.message ?? error);
    return { ok: false, salida, codigo: error.status ?? null, errno: error.code ?? null };
  }
}

function enRepo() {
  return existsSync(join(RAIZ, ".git"));
}

function tieneCaracteresDeControl(texto) {
  return [...texto].some((caracter) => {
    const codigo = caracter.charCodeAt(0);
    return codigo < 32 || codigo === 127;
  });
}

/** Valida el nombre que da el usuario. Solo letras, dígitos, `.`, `_` y `-`. */
function sanear(nombre) {
  if (!nombre) throw new Error("Falta el nombre del checkpoint.");
  if (nombre.startsWith("-")) {
    throw new Error(
      `Nombre de checkpoint inválido: "${nombre}". No puede empezar por "-" (se leería como una opción).`,
    );
  }
  if (nombre.includes("..")) {
    throw new Error(`Nombre de checkpoint inválido: "${nombre}". No puede contener "..".`);
  }
  if (nombre.length > LONGITUD_MAXIMA) {
    throw new Error(
      `Nombre de checkpoint inválido: "${nombre}". Supera los ${LONGITUD_MAXIMA} caracteres.`,
    );
  }
  if (tieneCaracteresDeControl(nombre)) {
    throw new Error(
      `Nombre de checkpoint inválido: "${nombre}". No puede contener caracteres de control.`,
    );
  }
  for (const caracter of CARACTERES_PROHIBIDOS) {
    if (nombre.includes(caracter)) {
      throw new Error(
        `Nombre de checkpoint inválido: "${nombre}". No puede contener "${caracter}".`,
      );
    }
  }
  if (!/^[A-Za-z0-9._-]+$/.test(nombre)) {
    throw new Error(
      `Nombre de checkpoint inválido: "${nombre}". Solo se admiten letras, dígitos, ".", "_" y "-".`,
    );
  }
  return nombre;
}

function etiquetaCompleta(nombre) {
  return `${PREFIJO}${nombre}`;
}

/** Ficheros modificados o borrados (los untracked NO cuentan: hay artefactos por diseño). */
function estadoArbol() {
  const r = git(["status", "--porcelain", "--untracked-files=no"]);
  if (!r.ok) throw new Error(`No se pudo leer git status: ${r.salida}`);
  return r.salida.length > 0 ? r.salida.split("\n") : [];
}

function listarCheckpoints() {
  const r = git([
    "tag",
    "--list",
    `${PREFIJO}*`,
    "--format=%(refname:short) %(objectname:short) %(creatordate:iso8601)",
  ]);
  if (!r.ok) throw new Error(`No se pudo listar los checkpoints: ${r.salida}`);
  if (!r.salida) return [];
  return r.salida.split("\n").map((linea) => {
    const [nombre, hash, ...resto] = linea.trim().split(/\s+/);
    return { nombre, hash, fecha: resto.join(" ") };
  });
}

const [, , accion, ...resto] = process.argv;

if (accion === "crear") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  if (!resto[0]) {
    console.error("Uso: node .claude/hooks/checkpoint.mjs crear <nombre>");
    process.exit(2);
  }

  let nombre;
  try {
    nombre = sanear(resto[0]);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }

  const sucios = estadoArbol();
  if (sucios.length > 0) {
    console.error(
      "El árbol tiene cambios sin commitear, no se puede crear el checkpoint:\n" +
        sucios.map((linea) => `  ${linea}`).join("\n") +
        "\n\nHaz commit o stash antes. Los ficheros sin versionar (.claude/cache/, " +
        ".claude/planes/, …) no cuentan: son artefactos por diseño.",
    );
    process.exit(1);
  }

  const etiqueta = etiquetaCompleta(nombre);
  const existente = git(["rev-parse", "--verify", "--quiet", `refs/tags/${etiqueta}`]);
  if (existente.ok && existente.salida) {
    console.error(
      `El checkpoint ${etiqueta} ya existe (→ ${existente.salida.slice(0, 7)}). ` +
        "Bórralo o usa otro nombre.",
    );
    process.exit(1);
  }

  const sha = git(["rev-parse", "HEAD"]);
  if (!sha.ok) {
    console.error(`No se pudo resolver HEAD:\n${sha.salida}`);
    process.exit(2);
  }

  // `git tag -- <etiqueta> <sha>`: el separador `--` deja claro que lo que
  // sigue no es una opción.
  const creado = git(["tag", "--", etiqueta, sha.salida]);
  if (!creado.ok) {
    console.error(`No se pudo crear el checkpoint ${etiqueta}:\n${creado.salida}`);
    process.exit(1);
  }

  console.log(
    `Checkpoint creado: ${etiqueta}\n` +
      `  Hash: ${sha.salida}\n` +
      `  Restaurar con: node .claude/hooks/checkpoint.mjs restaurar ${nombre}`,
  );
  process.exit(0);
}

if (accion === "restaurar") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  if (!resto[0]) {
    console.error("Uso: node .claude/hooks/checkpoint.mjs restaurar <nombre>");
    process.exit(2);
  }

  let nombre;
  try {
    nombre = sanear(resto[0]);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }

  const etiqueta = etiquetaCompleta(nombre);
  const existe = git(["rev-parse", "--verify", "--quiet", `refs/tags/${etiqueta}`]);
  if (!existe.ok || !existe.salida) {
    console.error(`Checkpoint no encontrado: ${etiqueta}`);
    process.exit(1);
  }

  const descartar = resto.includes("--descartar");
  const sucios = estadoArbol();
  if (sucios.length > 0 && !descartar) {
    console.error(
      `El árbol tiene cambios sin commitear. Restaurar ${etiqueta} los descarta:\n` +
        sucios.map((linea) => `  ${linea}`).join("\n") +
        "\n\nHaz commit o stash antes, o repite con --descartar para perderlos.",
    );
    process.exit(1);
  }

  // `git reset --hard <etiqueta> --`: el `--` va AL FINAL. Con `--` delante
  // git responde "Cannot do hard reset with paths" (el separador ahí
  // convierte la etiqueta en un path). El nombre ya viene saneado, así que
  // no puede colarse como opción.
  const r = git(["reset", "--hard", etiqueta, "--"]);
  if (!r.ok) {
    console.error(`No se pudo restaurar ${etiqueta}:\n${r.salida}`);
    process.exit(1);
  }

  console.log(
    `Restaurado a ${etiqueta} (${existe.salida.slice(0, 7)}).\n` +
      "El tag sigue existiendo por si quieres volver. No se ha hecho push.",
  );
  process.exit(0);
}

if (accion === "listar") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  let checkpoints;
  try {
    checkpoints = listarCheckpoints();
  } catch (error) {
    console.error(error.message);
    process.exit(2);
  }
  if (checkpoints.length === 0) {
    console.log("No hay checkpoints.");
    process.exit(0);
  }
  console.log("Checkpoints existentes:");
  for (const c of checkpoints) {
    console.log(`  ${c.nombre}  ${c.hash}  ${c.fecha}`);
  }
  process.exit(0);
}

if (accion === "estado") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  let sucios;
  let checkpoints;
  try {
    sucios = estadoArbol();
    checkpoints = listarCheckpoints();
  } catch (error) {
    console.error(error.message);
    process.exit(2);
  }

  console.log(
    `Árbol de trabajo: ${sucios.length === 0 ? "LIMPIO" : "NO LIMPIO"} ` +
      `(${sucios.length} cambio(s) sin commitear)`,
  );
  for (const linea of sucios) console.log(`  ${linea}`);

  if (checkpoints.length === 0) {
    console.log("Último checkpoint: ninguno (no hay tags checkpoint/).");
    process.exit(0);
  }
  const ultimo = [...checkpoints].sort((a, b) => (a.fecha < b.fecha ? 1 : -1))[0];
  console.log(`Último checkpoint: ${ultimo.nombre}  ${ultimo.hash}  ${ultimo.fecha}`);
  process.exit(0);
}

console.error(
  "Uso:\n" +
    "  node .claude/hooks/checkpoint.mjs crear <nombre>\n" +
    "  node .claude/hooks/checkpoint.mjs restaurar <nombre> [--descartar]\n" +
    "  node .claude/hooks/checkpoint.mjs listar\n" +
    "  node .claude/hooks/checkpoint.mjs estado",
);
process.exit(2);
