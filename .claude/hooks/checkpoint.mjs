#!/usr/bin/env node
// Checkpoint — git tags efímeros para rollback antes de cada ola del ciclo.
//
// Uso:
//   node .claude/hooks/checkpoint.mjs crear <etiqueta>
//   node .claude/hooks/checkpoint.mjs rollback <etiqueta> --confirmar
//   node .claude/hooks/checkpoint.mjs listar
//   node .claude/hooks/checkpoint.mjs verificar <etiqueta>
//
// Política:
//   - Etiquetas con prefijo `chk-` para no contaminar el espacio de tags del repo.
//   - No se commitean etiquetas al remoto (`--no-push` por defecto; nunca push aquí).
//   - El rollback deja `main` en el commit anterior y borra cambios sin commitear.
//   - Antes de hacer rollback, valida que el árbol está limpio o que el usuario aceptó perderlos.
//
// Restricción de Lovable: nunca reescribir historia publicada. Por eso `rollback`
// usa `git reset --hard <hash>` (movimiento de branch pointer), no rebase ni
// amend ni push --force. La etiqueta queda en el repo por si hay que volver.
import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PREFIJO = "chk-";

function ejecutar(comando, opts = {}) {
  try {
    return {
      ok: true,
      salida: execSync(comando, {
        cwd: RAIZ,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
        ...opts,
      }).trim(),
    };
  } catch (error) {
    return {
      ok: false,
      salida: (error.stdout ?? "") + (error.stderr ?? "") || String(error.message),
      codigo: error.status ?? 1,
    };
  }
}

function enRepo() {
  return existsSync(join(RAIZ, ".git"));
}

function sanear(etiqueta) {
  if (!etiqueta) throw new Error("Falta el nombre de la etiqueta.");
  if (!/^[a-zA-Z0-9._/-]+$/.test(etiqueta)) {
    throw new Error(`Etiqueta inválida: "${etiqueta}".`);
  }
  return etiqueta.replace(/^chk[-:]/, "");
}

function etiquetaCompleta(nombre) {
  return `${PREFIJO}${nombre}`;
}

function assertLimpio() {
  const r = ejecutar("git status --porcelain");
  if (!r.ok) throw new Error(`No se pudo leer git status: ${r.salida}`);
  if (r.salida.length > 0) {
    throw new Error(
      `El árbol tiene cambios sin commitear. Haz commit o stash antes:\n${r.salida}\n\n` +
        `Si quieres tirar esos cambios y volver al checkpoint, pásale --confirmar y --perdonar-sucio.`,
    );
  }
}

const [, , accion, ...resto] = process.argv;

if (accion === "crear") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  const nombre = sanear(resto[0]);
  if (!nombre) {
    console.error("Uso: node .claude/hooks/checkpoint.mjs crear <etiqueta>");
    process.exit(2);
  }
  try {
    assertLimpio();
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
  const tag = etiquetaCompleta(nombre);
  const r = ejecutar(`git tag ${tag}`);
  if (!r.ok) {
    console.error(`No se pudo crear la etiqueta ${tag}:\n${r.salida}`);
    process.exit(1);
  }
  const hash = ejecutar("git rev-parse HEAD").salida;
  console.log(
    `Checkpoint creado: ${tag}\n` +
      `  Hash: ${hash}\n` +
      `  Restaurar con: node .claude/hooks/checkpoint.mjs rollback ${nombre} --confirmar`,
  );
  process.exit(0);
}

if (accion === "listar") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  const r = ejecutar(`git tag -l '${PREFIJO}*' --format='%(refname:short) %(objectname:short) %(creatordate:iso8601)'`);
  if (!r.ok) {
    console.error(`No se pudo listar:\n${r.salida}`);
    process.exit(1);
  }
  if (!r.salida) {
    console.log("No hay checkpoints.");
    process.exit(0);
  }
  console.log(r.salida);
  process.exit(0);
}

if (accion === "verificar") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  const nombre = sanear(resto[0]);
  const tag = etiquetaCompleta(nombre);
  const r = ejecutar(`git rev-parse --verify --quiet refs/tags/${tag}`);
  if (r.ok) {
    console.log(`Checkpoint existe: ${tag} → ${r.salida}`);
    process.exit(0);
  }
  console.error(`Checkpoint no encontrado: ${tag}`);
  process.exit(1);
}

if (accion === "rollback") {
  if (!enRepo()) {
    console.error("No estamos en un repo git.");
    process.exit(2);
  }
  const nombre = sanear(resto[0]);
  const args = resto.slice(1);
  const confirmar = args.includes("--confirmar");
  const perdonarSucio = args.includes("--perdonar-sucio");
  if (!confirmar) {
    console.error(
      `Esto va a mover HEAD a ${etiquetaCompleta(nombre)} y descartar todo lo no commiteado. ` +
        `Si estás seguro, repite con --confirmar. ` +
        `Si hay cambios que quieres tirar, añade --perdonar-sucio.`,
    );
    process.exit(1);
  }
  const tag = etiquetaCompleta(nombre);
  const hashRes = ejecutar(`git rev-parse --verify --quiet refs/tags/${tag}`);
  if (!hashRes.ok) {
    console.error(`Checkpoint no encontrado: ${tag}`);
    process.exit(1);
  }
  if (!perdonarSucio) {
    try {
      assertLimpio();
    } catch (e) {
      console.error(e.message);
      process.exit(1);
    }
  }
  const r = ejecutar(`git reset --hard ${tag}`);
  if (!r.ok) {
    console.error(`Rollback falló:\n${r.salida}`);
    process.exit(1);
  }
  console.log(
    `Rollback a ${tag} (${hashRes.salida}). El estado del repo ahora es el del checkpoint.\n` +
      `El tag sigue existiendo por si quieres volver. No se ha hecho push.`,
  );
  process.exit(0);
}

console.error(
  "Uso:\n" +
    "  node .claude/hooks/checkpoint.mjs crear <etiqueta>\n" +
    "  node .claude/hooks/checkpoint.mjs listar\n" +
    "  node .claude/hooks/checkpoint.mjs verificar <etiqueta>\n" +
    "  node .claude/hooks/checkpoint.mjs rollback <etiqueta> --confirmar [--perdonar-sucio]",
);
process.exit(2);