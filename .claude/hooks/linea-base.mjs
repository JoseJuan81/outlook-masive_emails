#!/usr/bin/env node
// Línea base congelada de lint — «no empeores el repo», comprobable por comando.
//
//   node .claude/hooks/linea-base.mjs verificar   → 0 si nadie empeoró, 1 si sí, 3 si ruff no está
//   node .claude/hooks/linea-base.mjs generar     → regenera el archivo (SOLO el usuario)
//
// Codigos de salida: 0 correcto · 1 fallo · 2 error de ejecucion · 3 no aplica.
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
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const ARCHIVO = join(RAIZ, ".claude/linea-base.json");
const INFORME = join(RAIZ, ".claude/cache/ruff-informe.json");

// `--no-sync` es obligatorio: `uv sync` a secas poda el grupo `test` de este repo
// (desinstala pytest). `--extend-exclude` y nunca `--exclude`: `--exclude`
// reemplaza la lista por defecto y ruff acabaría escaneando `.venv/`.
const ARGUMENTOS_LINT = [
  "run",
  "--no-sync",
  "ruff",
  "check",
  ".",
  "--output-format",
  "json",
  "--output-file",
  ".claude/cache/ruff-informe.json",
  "--extend-exclude",
  "Templates,html,logs,staging,preview",
  "--extend-exclude",
  "*.ipynb",
];

const COMANDO_LINT =
  "uv run --no-sync ruff check . --output-format json " +
  "--output-file .claude/cache/ruff-informe.json " +
  "--extend-exclude Templates,html,logs,staging,preview --extend-exclude '*.ipynb'";

const CLAVES_EDITABLES = ["_comentario", "generado", "comando", "totalErrores", "archivos"];

/** Ejecuta `uv` con un array de argumentos (nunca una cadena de shell). */
function ejecutar(args) {
  try {
    const salida = execFileSync("uv", args, {
      cwd: RAIZ,
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, FORCE_COLOR: "0", NO_COLOR: "1", TERM: "dumb" },
    });
    return { ok: true, salida: String(salida).trim(), codigo: 0 };
  } catch (error) {
    const salida =
      `${error.stdout ?? ""}${error.stderr ?? ""}`.trim() || String(error.message ?? error);
    return { ok: false, salida, codigo: error.status ?? null, errno: error.code ?? null };
  }
}

/** ¿Está ruff disponible? `uv run` NO autoinstala: si no está, no está. */
function ruffDisponible() {
  const r = ejecutar(["run", "--no-sync", "ruff", "--version"]);
  if (r.ok) return { disponible: true, version: r.salida };
  if (/Failed to spawn/i.test(r.salida)) {
    return { disponible: false, motivo: r.salida };
  }
  if (r.errno === "ENOENT") {
    return { disponible: false, motivo: `uv no está disponible: ${r.salida}` };
  }
  return { disponible: false, error: true, motivo: r.salida };
}

function rutaRelativa(ruta) {
  if (!ruta) return "";
  const absoluta = isAbsolute(ruta) ? ruta : join(RAIZ, ruta);
  return relative(RAIZ, absoluta).split("\\").join("/");
}

/**
 * Mide los errores de lint actuales sin escribir nada.
 * `ruff check` sale con 1 cuando hay violaciones (y el JSON se escribe igual);
 * con 2 cuando no se pudo ejecutar.
 */
function medir() {
  mkdirSync(dirname(INFORME), { recursive: true });
  rmSync(INFORME, { force: true });

  const r = ejecutar(ARGUMENTOS_LINT);
  if (!r.ok && r.codigo !== 1) {
    if (/Failed to spawn/i.test(r.salida)) {
      console.error(
        "No aplica: ruff no está instalado.\n" +
          "  uv run --no-sync ruff check . → \"Failed to spawn: ruff\"\n" +
          "  Instálalo con: uv add --dev ruff",
      );
      process.exit(3);
    }
    console.error(`No se pudo ejecutar el lint:\n${r.salida}`);
    process.exit(2);
  }

  if (!existsSync(INFORME)) {
    console.error(`El lint no generó el informe ${INFORME}.`);
    process.exit(2);
  }

  let diagnosticos;
  try {
    diagnosticos = JSON.parse(readFileSync(INFORME, "utf8"));
  } catch (error) {
    console.error(`El informe de ruff no es JSON válido: ${error.message}`);
    process.exit(2);
  }

  if (!Array.isArray(diagnosticos)) {
    console.error(
      "El informe de ruff no es el array de diagnósticos esperado " +
        `(recibe ${diagnosticos === null ? "null" : typeof diagnosticos}).`,
    );
    process.exit(2);
  }

  // `ruff check --output-format json` emite un array plano: un objeto por
  // violación. No hay `errorCount` por fichero, así que el presupuesto se
  // cuenta agrupando por `filename`.
  const porArchivo = {};
  for (const diagnostico of diagnosticos) {
    const ruta = rutaRelativa(diagnostico?.filename);
    if (!ruta) continue;
    porArchivo[ruta] = (porArchivo[ruta] ?? 0) + 1;
  }
  return porArchivo;
}

function totalDe(archivos) {
  return Object.values(archivos).reduce((suma, n) => suma + n, 0);
}

function cargarBase() {
  if (!existsSync(ARCHIVO)) return null;
  try {
    return JSON.parse(readFileSync(ARCHIVO, "utf8"));
  } catch (error) {
    console.error(`La línea base ${ARCHIVO} no es JSON válido: ${error.message}`);
    process.exit(2);
  }
}

const accion = process.argv[2];

if (accion === "generar") {
  const disponibilidad = ruffDisponible();
  if (!disponibilidad.disponible) {
    if (disponibilidad.error) {
      console.error(`No se pudo comprobar si ruff está disponible:\n${disponibilidad.motivo}`);
      process.exit(2);
    }
    console.error(
      "No aplica: ruff no está instalado. No se genera una línea base vacía.\n" +
        `  ${disponibilidad.motivo}\n` +
        "  Instálalo con: uv add --dev ruff",
    );
    process.exit(3);
  }

  const actual = medir();
  const base = cargarBase();
  const previo = base?.archivos ?? {};
  const totalPrevio = base?.totalErrores ?? totalDe(previo);
  const total = totalDe(actual);

  if (base) {
    // «Solo a la baja»: ningún presupuesto por fichero puede subir. Si el
    // total sube, es que algún fichero sube; y un total plano puede esconder
    // un fichero que sube mientras otro baja. Se rechazan los dos casos.
    const subidas = Object.entries(actual).filter(([f, n]) => n > (previo[f] ?? 0));
    if (subidas.length > 0) {
      console.error(
        "La línea base solo se regenera A LA BAJA. Estos archivos empeoraron respecto a la actual:\n" +
          subidas.map(([f, n]) => `  ${f}: ${previo[f] ?? 0} → ${n}`).join("\n") +
          `\n  Total: ${totalPrevio} → ${total}\n\n` +
          "Arregla los errores nuevos, o borra .claude/linea-base.json a mano si de verdad " +
          "quieres una línea base peor.",
      );
      process.exit(1);
    }
  }

  const previoExtra = {};
  if (base) {
    for (const [clave, valor] of Object.entries(base)) {
      if (!CLAVES_EDITABLES.includes(clave)) previoExtra[clave] = valor;
    }
  }

  writeFileSync(
    ARCHIVO,
    JSON.stringify(
      {
        _comentario:
          "Errores de lint heredados POR ARCHIVO (ruff). Generado midiendo este repo, nunca " +
          "copiado. Un archivo ausente tiene presupuesto CERO. Solo se regenera a la baja y por " +
          "decisión del usuario: node .claude/hooks/linea-base.mjs generar",
        generado: new Date().toISOString(),
        comando: COMANDO_LINT,
        totalErrores: total,
        archivos: actual,
        ...previoExtra,
      },
      null,
      2,
    ) + "\n",
  );

  console.log(
    `Línea base generada: ${total} errores en ${Object.keys(actual).length} archivo(s).` +
      (total === 0 ? "\nEl repo está limpio: el presupuesto es cero en TODO archivo." : ""),
  );
  for (const [f, n] of Object.entries(actual)) console.log(`  ${f}: ${n}`);
  process.exit(0);
}

if (accion === "verificar") {
  // Sin línea base no hay presupuesto que comparar: eso es un fallo, no un
  // «todo bien». Borrar la línea base no puede hacer que la comprobación pase.
  if (!existsSync(ARCHIVO)) {
    console.error(
      "FALTA LA LÍNEA BASE: no existe .claude/linea-base.json.\n\n" +
        "Sin línea base no hay presupuesto con el que comparar, así que no se puede afirmar " +
        "que nadie ha empeorado el repo. Esto NO es un «todo bien».\n\n" +
        "  Genérala (SOLO el usuario) con los DOS pasos:\n" +
        "    rm .claude/linea-base.json\n" +
        "    node .claude/hooks/linea-base.mjs generar\n\n" +
        "  El primer paso es necesario: `generar` se niega a subir el presupuesto de " +
        "cualquier archivo, así que con una línea base vacía (0) se negaría a escribir los " +
        "errores heredados que ya tiene el repo.\n" +
        "  A partir de ahí la línea base solo se regenera A LA BAJA.",
    );
    process.exit(1);
  }

  const base = cargarBase();
  const presupuesto = base?.archivos ?? {};

  const disponibilidad = ruffDisponible();
  if (!disponibilidad.disponible) {
    if (disponibilidad.error) {
      console.error(`No se pudo comprobar si ruff está disponible:\n${disponibilidad.motivo}`);
      process.exit(2);
    }
    console.error(
      "No aplica: ruff no está instalado, no se puede medir la línea base.\n" +
        `  ${disponibilidad.motivo}\n` +
        "  Instálalo con: uv add --dev ruff",
    );
    process.exit(3);
  }

  const actual = medir();
  const regresiones = [];
  const detalles = [];

  for (const [fichero, errores] of Object.entries(actual)) {
    const permitido = presupuesto[fichero] ?? 0; // fichero ausente → presupuesto cero
    const estado = errores > permitido ? "regresion" : "ok";
    detalles.push({ fichero, permitido, errores, estado });
    if (estado === "regresion") regresiones.push({ fichero, permitido, errores });
  }

  for (const detalle of detalles) {
    const marca = detalle.estado === "regresion" ? "REGRESIÓN" : "ok      ";
    const nota =
      detalle.permitido === 0 && detalle.errores > 0
        ? "  (presupuesto 0: fichero ausente de la línea base)"
        : "";
    console.log(
      `  ${marca}  ${detalle.fichero}: actual ${detalle.errores} / presupuesto ${detalle.permitido}${nota}`,
    );
  }

  const mejoras = Object.entries(presupuesto).filter(([f, n]) => (actual[f] ?? 0) < n);

  if (regresiones.length === 0) {
    console.log(
      `Línea base respetada. ${Object.keys(actual).length} archivo(s) con errores, ninguno por ` +
        `encima de su presupuesto.` +
        (mejoras.length ? ` ${mejoras.length} archivo(s) mejoraron.` : ""),
    );
    process.exit(0);
  }

  console.error(
    "\nREGRESIÓN DE LINT respecto a la línea base congelada:\n\n" +
      regresiones
        .map((r) => `  ${r.fichero}\n    permitido: ${r.permitido}   actual: ${r.errores}`)
        .join("\n") +
      "\n\nArregla los errores. Regenerar la línea base para que esto pase está prohibido: " +
      "solo la regenera el usuario, y solo a la baja.",
  );
  process.exit(1);
}

console.error(
  "Uso:\n" +
    "  node .claude/hooks/linea-base.mjs verificar   (compara con .claude/linea-base.json)\n" +
    "  node .claude/hooks/linea-base.mjs generar     (regenera la línea base; SOLO el usuario)",
);
process.exit(2);
