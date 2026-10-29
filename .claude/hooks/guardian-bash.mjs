#!/usr/bin/env node
// Guardián de Bash — hook PreToolUse para los roles que producen documentos.
//
// guardian-escritura.mjs solo mira Write/Edit/…: un `echo "x" > main.py`
// pasa el gate por completo. Este hook cubre esa fuga.
//
// REGLA DE ORO: se deniega SOLO cuando se puede identificar con certeza una
// escritura prohibida. Ante la duda, se permite. Un falso positivo manda al
// agente a hacer un rodeo; un falso negativo deja escribir.
//
// Se analiza: redirecciones, comandos con semántica de escritura y escritores
// inline opacos (código embebido que escribe en disco y cuyo destino no se
// puede analizar con certeza).
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import {
  PERMITIDAS,
  ARCHIVOS_PERMITIDOS,
  aAbsoluto,
  aRelativo,
  esPermitido,
  esNeutro,
  denegar,
} from "./permitidas.mjs";

const REDIRECCIONES = new Set([">", ">>", ">|", "&>", "&>>"]);
const SEPARADORES = new Set([";", "&&", "||", "|", "&", "\n", "(", ")"]);
const MAX_PROFUNDIDAD_SUSTITUCION = 2;

let entrada;
try {
  entrada = JSON.parse(readFileSync(0, "utf8") || "{}");
} catch {
  process.stderr.write(
    "Guardián de Bash: la entrada del hook no es JSON válido; no hay nada que juzgar, se permite.\n",
  );
  process.exit(0);
}

const comando = entrada?.tool_input?.command;
if (typeof comando !== "string" || !comando.trim()) process.exit(0);

/* ────────────────────────────── helpers de ruta ───────────────────────────── */

/** Devuelve la ruta si hay que bloquearla, o null si se permite. */
function rutaBloqueante(destino) {
  if (typeof destino !== "string" || !destino.trim()) return null;
  if (esNeutro(destino)) return null;
  if (esPermitido(destino)) return null;
  return destino;
}

function mostrarRuta(destino) {
  const rel = aRelativo(destino);
  if (rel === "") return "la raíz del repo";
  if (rel.startsWith("../")) return aAbsoluto(destino);
  return rel;
}

function rutasPermitidas() {
  return [
    ...PERMITIDAS.map((c) => `  - ${c}`),
    ...ARCHIVOS_PERMITIDOS.map((a) => `  - ${a}`),
  ].join("\n");
}

/* ─────────────────────────── rutas indeterminadas ─────────────────────────── */

/** Rutas que un shell resuelve en tiempo de ejecución: no se pueden juzgar. */
function esRutaIndeterminada(destino) {
  return /[$`*?[\]{}()|&;<>]/.test(destino);
}

/* ─────────────────────────── análisis del comando ────────────────────────── */

/**
 * Punto de entrada del análisis. Devuelve un motivo de bloqueo o null.
 */
function analizar(texto, profundidad = 0) {
  // 1) Escritores inline opacos: código embebido que escribe en disco.
  const opaco = detectarEscritorInline(texto);
  if (opaco) return motivoEscritorOpaco(texto, opaco);

  // 2) Sustituciones de comando: `$(...)` y backticks se analizan aparte.
  const { limpio, sustituciones } = extraerSustituciones(texto);
  if (profundidad < MAX_PROFUNDIDAD_SUSTITUCION) {
    for (const sustitucion of sustituciones) {
      const motivo = analizar(sustitucion, profundidad + 1);
      if (motivo) return motivo;
    }
  }

  // 3) Here-docs: el cuerpo no es comando, se sustituye por un token neutro.
  const sinHeredocs = quitarHeredocs(limpio);

  // 4) Tokenizado y segmentado.
  const segmentos = segmentar(tokenizar(sinHeredocs));
  for (const segmento of segmentos) {
    const motivo = analizarSegmento(segmento, texto);
    if (motivo) return motivo;
  }

  return null;
}

/** Analiza un segmento: sus redirecciones y su comando principal. */
function analizarSegmento(tokens, comandoOriginal) {
  const palabras = [];
  const redirecciones = [];

  let i = 0;
  while (i < tokens.length) {
    const t = tokens[i];
    if (t.op && REDIRECCIONES.has(t.t)) {
      const destino = tokens[i + 1] && !tokens[i + 1].op ? tokens[i + 1].t : null;
      redirecciones.push({ op: t.t, destino });
      i += destino ? 2 : 1;
      continue;
    }
    if (!t.op) palabras.push(t.t);
    i += 1;
  }

  // Redirecciones: el destino es una escritura en disco.
  for (const redireccion of redirecciones) {
    const destino = redireccion.destino;
    if (!destino) continue;
    // Duplicación de descriptor (&1, &2) o número: no escribe en disco.
    if (/^&\d*$/.test(destino) || /^\d+$/.test(destino)) continue;
    // Destino que el shell resuelve en runtime: no se puede afirmar nada.
    if (esRutaIndeterminada(destino)) continue;
    if (rutaBloqueante(destino)) {
      return motivoRuta(comandoOriginal, destino, "una redirección");
    }
  }

  if (!palabras.length) return null;

  const sinEnvoltorios = quitarEnvoltorios(palabras);
  if (!sinEnvoltorios.length) return null;

  const nombre = basename(sinEnvoltorios[0]);
  const argumentos = sinEnvoltorios.slice(1);

  return analizarComando(nombre, argumentos, comandoOriginal);
}

/** Decide si el comando principal escribe y en qué rutas. */
function analizarComando(nombre, argumentos, comandoOriginal) {
  // Todas las ramas devuelven el mismo descriptor: {siempre, motivo} o {rutas}.
  // El motivo se convierte en cadena aquí, no en la rama que lo produce.
  const destinos =
    nombre === "git"
      ? analizarGit(argumentos, comandoOriginal)
      : nombre === "uv"
        ? analizarUv(argumentos, comandoOriginal)
        : destinosDeComando(nombre, argumentos);

  if (!destinos) return null;

  if (destinos.siempre) {
    return motivoSiempre(comandoOriginal, destinos.motivo);
  }

  for (const destino of destinos.rutas ?? []) {
    if (rutaBloqueante(destino)) {
      return motivoRuta(comandoOriginal, destino, `«${nombre}»`);
    }
  }

  return null;
}

/* ─────────────────────── comandos con semántica de escritura ───────────────── */

const CONSUME_VALOR = new Set(["-u", "-g", "-U", "-p", "-C", "-D", "-e", "-f", "-o", "-O", "-d", "-i"]);

function esFlag(palabra) {
  return palabra.startsWith("-") && palabra !== "-";
}

/** Operandos: argumentos que no son flags ni el valor de un flag con valor. */
function operandos(palabras, valoresConsumidos = new Set()) {
  const salida = [];
  for (let i = 0; i < palabras.length; i++) {
    const p = palabras[i];
    if (valoresConsumidos.has(p)) {
      i += 1;
      continue;
    }
    if (esFlag(p)) continue;
    salida.push(p);
  }
  return salida;
}

function valorDeFlag(palabras, nombres) {
  for (let i = 0; i < palabras.length; i++) {
    const p = palabras[i];
    for (const nombre of nombres) {
      if (p === nombre) return palabras[i + 1] ?? null;
      if (p.startsWith(`${nombre}=`)) return p.slice(nombre.length + 1);
    }
  }
  return null;
}

function tieneFlag(palabras, predicado) {
  return palabras.some((p) => predicado(p));
}

/** Un script sed se reconoce por un comando s/// d/// y/// con delimitadores. */
function pareceScriptSed(operando) {
  return /(^|;|\})\s*[0-9,$]*(s|d|y)\/[^/]*\/[^/]*/.test(operando);
}

function destinosDeComando(nombre, argumentos) {
  switch (nombre) {
    case "sed": {
      const inPlace = tieneFlag(argumentos, (p) => p === "-i" || p === "--in-place" || p.startsWith("-i."));
      if (!inPlace) return null;
      const ops = operandos(argumentos, new Set(["-e", "--expression", "-f", "--file"]));
      if (!ops.length) return null;
      const [primero, ...resto] = ops;
      const rutas = pareceScriptSed(primero) ? resto : ops;
      return { rutas };
    }
    case "tee":
      return { rutas: operandos(argumentos) };
    case "cp":
    case "mv": {
      const ops = operandos(argumentos);
      return ops.length ? { rutas: [ops[ops.length - 1]] } : null;
    }
    case "rm":
    case "rmdir":
    case "unlink":
    case "touch":
    case "truncate":
    case "mkdir":
      return { rutas: operandos(argumentos) };
    case "dd": {
      const destino = argumentos.find((p) => p.startsWith("of="));
      return destino ? { rutas: [destino.slice(3)] } : null;
    }
    case "curl": {
      const rutas = [];
      for (let i = 0; i < argumentos.length; i++) {
        const p = argumentos[i];
        if (p === "-o" || p === "--output") {
          if (argumentos[i + 1]) rutas.push(argumentos[i + 1]);
          i += 1;
          continue;
        }
        if (p.startsWith("--output=")) {
          rutas.push(p.slice("--output=".length));
          continue;
        }
        if (p.startsWith("-o") && p.length > 2) {
          rutas.push(p.slice(2));
          continue;
        }
        if (p === "-O") {
          // Descarga al directorio actual con el nombre remoto.
          rutas.push(process.cwd());
        }
      }
      return rutas.length ? { rutas } : null;
    }
    case "wget": {
      const destino = valorDeFlag(argumentos, ["--output-document", "-O"]);
      return destino ? { rutas: [destino] } : null;
    }
    case "ln": {
      const ops = operandos(argumentos);
      return ops.length ? { rutas: [ops[ops.length - 1]] } : null;
    }
    case "patch": {
      const ops = operandos(argumentos);
      if (!ops.length) {
        return {
          siempre: true,
          motivo:
            "«patch» sin fichero de parche aplica cambios a archivos que no se pueden determinar de antemano.",
        };
      }
      return { rutas: [ops[0]] };
    }
    case "rsync": {
      const ops = operandos(argumentos);
      return ops.length ? { rutas: [ops[ops.length - 1]] } : null;
    }
    case "tar": {
      const extrae =
        tieneFlag(argumentos, (p) => p === "-x" || p === "--extract" || /^-[a-zA-Z]*x/.test(p)) &&
        !tieneFlag(argumentos, (p) => p === "-t" || p === "--list");
      if (!extrae) return null;
      const directorio = valorDeFlag(argumentos, ["--directory", "-C"]);
      return { rutas: [directorio ?? process.cwd()] };
    }
    case "unzip": {
      const directorio = valorDeFlag(argumentos, ["--directory", "-d"]);
      return { rutas: [directorio ?? process.cwd()] };
    }
    default:
      return null;
  }
}

/* ─────────────────────────────── subcomandos git ──────────────────────────── */

function analizarGit(argumentos, comandoOriginal) {
  const sub = argumentos.find((p) => !p.startsWith("-"));
  if (!sub) return null;

  switch (sub) {
    case "checkout": {
      const guion = argumentos.indexOf("--");
      if (guion !== -1) {
        const rutas = argumentos.slice(guion + 1).filter((p) => !p.startsWith("-"));
        return rutas.length ? { rutas } : null;
      }
      // Sin "--" el argumento puede ser una rama: solo se bloquean las rutas evidentes.
      const rutas = operandos(argumentos).filter((p) => p.includes("/") || /\.[A-Za-z0-9]+$/.test(p) || p === ".");
      return rutas.length ? { rutas } : null;
    }
    case "restore": {
      if (tieneFlag(argumentos, (p) => p === "--staged")) return null;
      const guion = argumentos.indexOf("--");
      const rutas = (guion === -1 ? operandos(argumentos) : argumentos.slice(guion + 1)).filter(
        (p) => !p.startsWith("-"),
      );
      if (!rutas.length) {
        return {
          siempre: true,
          motivo: "«git restore» sin rutas restaura todo el árbol de trabajo.",
        };
      }
      return { rutas };
    }
    case "rm": {
      const guion = argumentos.indexOf("--");
      const rutas = (guion === -1 ? operandos(argumentos) : argumentos.slice(guion + 1)).filter(
        (p) => !p.startsWith("-"),
      );
      return rutas.length ? { rutas } : null;
    }
    case "mv": {
      const ops = operandos(argumentos);
      return ops.length ? { rutas: [ops[ops.length - 1]] } : null;
    }
    case "apply":
      return {
        siempre: true,
        motivo:
          "«git apply» modifica el árbol de trabajo con archivos que no se pueden determinar de antemano.",
      };
    case "reset":
      return tieneFlag(argumentos, (p) => p === "--hard")
        ? {
            siempre: true,
            motivo: "«git reset --hard» descarta cambios del árbol de trabajo y del índice.",
          }
        : null;
    case "clean":
      return tieneFlag(argumentos, (p) => p === "-n" || p === "--dry-run")
        ? null
        : {
            siempre: true,
            motivo: "«git clean» borra archivos no versionados del árbol de trabajo.",
          };
    default:
      return null;
  }
}

/* ─────────────────────────────── subcomandos uv ──────────────────────────── */

function analizarUv(argumentos, comandoOriginal) {
  const sub = argumentos.find((p) => !p.startsWith("-"));
  switch (sub) {
    case "add":
      return {
        siempre: true,
        motivo: "«uv add» modifica pyproject.toml (y uv.lock), que son intocables para este rol.",
      };
    case "remove":
    case "rm":
      return {
        siempre: true,
        motivo: "«uv remove» modifica pyproject.toml (y uv.lock), que son intocables para este rol.",
      };
    case "lock":
      return {
        siempre: true,
        motivo: "«uv lock» modifica uv.lock, que es intocable para este rol.",
      };
    case "sync":
      return {
        siempre: true,
        motivo: "«uv sync» modifica uv.lock y el entorno del proyecto (.venv/), intocables para este rol.",
      };
    default:
      return null;
  }
}

/* ───────────────────────────── escritores inline opacos ────────────────────── */

const ESCRITORES_OPACOS = [
  { patron: /(?<![\w])writeFileSync\s*\(/, nombre: "writeFileSync(" },
  { patron: /(?<![\w])writeFile\s*\(/, nombre: "writeFile(" },
  { patron: /(?<![\w])appendFileSync\s*\(/, nombre: "appendFileSync(" },
  { patron: /(?<![\w])appendFile\s*\(/, nombre: "appendFile(" },
  { patron: /\.write_text\s*\(/, nombre: ".write_text(" },
  { patron: /\.write_bytes\s*\(/, nombre: ".write_bytes(" },
  { patron: /\.unlink\s*\(/, nombre: ".unlink(" },
  { patron: /(?<![\w])os\.remove\s*\(/, nombre: "os.remove(" },
  { patron: /(?<![\w])os\.unlink\s*\(/, nombre: "os.unlink(" },
  { patron: /(?<![\w])os\.rmdir\s*\(/, nombre: "os.rmdir(" },
  { patron: /(?<![\w])shutil\.rmtree\s*\(/, nombre: "shutil.rmtree(" },
  { patron: /(?<![\w])shutil\.move\s*\(/, nombre: "shutil.move(" },
];

const RE_OPEN = /(?<![\w])open\s*\(\s*(['"`])[^'"`]*\1\s*,\s*(['"`])([^'"`]*)\2/g;

function detectarEscritorInline(texto) {
  for (const escritor of ESCRITORES_OPACOS) {
    if (escritor.patron.test(texto)) return escritor.nombre;
  }

  for (const coincidencia of texto.matchAll(RE_OPEN)) {
    const modo = coincidencia[3];
    if (modo && /[wa+]/.test(modo)) return `open(..., '${modo}')`;
  }

  return null;
}

/* ─────────────────────────────── motivos de bloqueo ────────────────────────── */

function motivoRuta(comandoOriginal, destino, origen) {
  return (
    `Guardián de Bash: comando bloqueado.\n\n` +
    `  ${comandoOriginal}\n\n` +
    `Escribe en «${mostrarRuta(destino)}» (${origen}), que no está entre las rutas que tu rol ` +
    `puede escribir.\n\n` +
    `Rutas permitidas para escribir:\n${rutasPermitidas()}\n\n` +
    `Alternativas: escribir el fichero con la herramienta Write en una de esas rutas, o dejar el ` +
    `cambio descrito en tu entregable para que lo aplique el rol «desarrollador», que es el ` +
    `único que escribe código de producción en este repo.`
  );
}

function motivoSiempre(comandoOriginal, explicacion) {
  return (
    `Guardián de Bash: comando bloqueado.\n\n` +
    `  ${comandoOriginal}\n\n` +
    `${explicacion}\n\n` +
    `Tu rol produce DOCUMENTOS, no código de producción ni cambios en el árbol de trabajo.\n` +
    `Si la tarea exige esta operación, descríbela en tu entregable y deja que el orquestador ` +
    `se la pase al rol «desarrollador».`
  );
}

function motivoEscritorOpaco(comandoOriginal, escritor) {
  return (
    `Guardián de Bash: comando bloqueado.\n\n` +
    `  ${comandoOriginal}\n\n` +
    `El comando contiene «${escritor}»: una escritura en disco cuyo destino no se puede ` +
    `analizar con certeza.\n\n` +
    `Tu rol produce DOCUMENTOS, no código de producción ni cambios en el árbol de trabajo.\n` +
    `Alternativas: usar la herramienta Write sobre una ruta permitida, o dejar el cambio ` +
    `descrito en tu entregable para que lo aplique el rol «desarrollador».`
  );
}

/* ─────────────────────────── tokenizado y segmentado ──────────────────────── */

/**
 * Tokeniza texto de shell respetando comillas simples, dobles y escapes.
 * Los operadores (`;`, `&&`, `|`, `>`, …) se emiten aparte para no confundirse
 * con texto entrecomillado.
 */
function tokenizar(texto) {
  const tokens = [];
  let actual = null;
  let i = 0;

  const cerrar = () => {
    if (actual) {
      tokens.push(actual);
      actual = null;
    }
  };
  const anadir = (texto, entrecomillado) => {
    if (!actual) actual = { t: "", op: false, quoted: false };
    actual.t += texto;
    if (entrecomillado) actual.quoted = true;
  };

  while (i < texto.length) {
    const c = texto[i];

    if (c === " " || c === "\t" || c === "\r") {
      cerrar();
      i += 1;
      continue;
    }

    if (c === "\n") {
      cerrar();
      tokens.push({ t: "\n", op: true, quoted: false });
      i += 1;
      continue;
    }

    if (c === "#" && !actual) {
      while (i < texto.length && texto[i] !== "\n") i += 1;
      continue;
    }

    if (c === "'") {
      i += 1;
      let buf = "";
      while (i < texto.length && texto[i] !== "'") {
        buf += texto[i];
        i += 1;
      }
      i += 1;
      anadir(buf, true);
      continue;
    }

    if (c === '"') {
      i += 1;
      let buf = "";
      while (i < texto.length && texto[i] !== '"') {
        if (texto[i] === "\\" && i + 1 < texto.length && '"\\$`'.includes(texto[i + 1])) {
          buf += texto[i + 1];
          i += 2;
          continue;
        }
        buf += texto[i];
        i += 1;
      }
      i += 1;
      anadir(buf, true);
      continue;
    }

    if (c === "\\") {
      i += 1;
      if (i < texto.length) {
        anadir(texto[i], true);
        i += 1;
      }
      continue;
    }

    const resto = texto.slice(i);
    const operadoresDobles = ["&>>", "&>", "&&", "||", ">>", ">|"];
    const operadorDoble = operadoresDobles.find((op) => resto.startsWith(op));
    if (operadorDoble) {
      cerrar();
      tokens.push({ t: operadorDoble, op: true, quoted: false });
      i += operadorDoble.length;
      continue;
    }

    // `&1` / `&2` son destinos de redirección, no separadores.
    if (c === "&" && /^&\d/.test(resto)) {
      const coincidencia = resto.match(/^&\d+/);
      anadir(coincidencia[0], false);
      i += coincidencia[0].length;
      continue;
    }

    if ([";", "|", "&", "(", ")", ">", "<"].includes(c)) {
      cerrar();
      tokens.push({ t: c, op: true, quoted: false });
      i += 1;
      continue;
    }

    anadir(c, false);
    i += 1;
  }

  cerrar();
  return tokens;
}

function segmentar(tokens) {
  const segmentos = [];
  let actual = [];

  for (const t of tokens) {
    if (t.op && SEPARADORES.has(t.t)) {
      if (actual.length) segmentos.push(actual);
      actual = [];
      continue;
    }
    actual.push(t);
  }
  if (actual.length) segmentos.push(actual);

  return segmentos;
}

/** Quita envoltorios (sudo, env…) para llegar al comando real. */
function quitarEnvoltorios(palabras) {
  const envoltorios = new Set(["sudo", "doas", "nohup", "time", "command", "exec", "builtin"]);

  let i = 0;
  while (i < palabras.length) {
    const p = palabras[i];
    if (envoltorios.has(p)) {
      i += 1;
      while (i < palabras.length && esFlag(palabras[i])) {
        if (CONSUME_VALOR.has(palabras[i])) i += 1;
        i += 1;
      }
      continue;
    }
    if (p === "env") {
      i += 1;
      while (
        i < palabras.length &&
        (esFlag(palabras[i]) || /^[A-Za-z_][A-Za-z0-9_]*=/.test(palabras[i]))
      ) {
        if (CONSUME_VALOR.has(palabras[i])) i += 1;
        i += 1;
      }
      continue;
    }
    break;
  }

  return palabras.slice(i);
}

/* ─────────────────────────── here-docs y sustituciones ────────────────────── */

const RE_HEREDOC = /<<(-?)\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\2/;

/**
 * Sustituye el cuerpo de los here-docs por líneas vacías: el cuerpo no es un
 * comando, así que no debe analizarse como tal.
 */
function quitarHeredocs(texto) {
  const lineas = texto.split("\n");
  const salida = [];
  let pendiente = null;

  for (const linea of lineas) {
    if (pendiente) {
      const prueba = pendiente.sangria ? linea.replace(/^\t+/, "") : linea;
      if (prueba.trim() === pendiente.delimitador) {
        pendiente = null;
        salida.push("");
      }
      continue;
    }

    const coincidencia = linea.match(RE_HEREDOC);
    if (coincidencia) {
      pendiente = { delimitador: coincidencia[3], sangria: coincidencia[1] === "-" };
      salida.push(linea.replace(RE_HEREDOC, ""));
      continue;
    }

    salida.push(linea);
  }

  return salida.join("\n");
}

/**
 * Extrae `$(...)` y backticks: su contenido es otro comando y se analiza
 * aparte. El resto del texto conserva su estructura.
 */
function extraerSustituciones(texto) {
  const sustituciones = [];
  let limpio = "";
  let i = 0;

  while (i < texto.length) {
    const c = texto[i];

    if (c === "'") {
      const fin = texto.indexOf("'", i + 1);
      const cierre = fin === -1 ? texto.length : fin;
      limpio += texto.slice(i, cierre + 1);
      i = cierre + 1;
      continue;
    }

    if (c === '"') {
      const fin = cerrarComillasDobles(texto, i);
      limpio += texto.slice(i, fin);
      i = fin;
      continue;
    }

    if (c === "$" && texto[i + 1] === "(") {
      const fin = parenCierre(texto, i + 1);
      sustituciones.push(texto.slice(i + 2, fin));
      limpio += " ";
      i = fin + 1;
      continue;
    }

    if (c === "`") {
      const fin = texto.indexOf("`", i + 1);
      const cierre = fin === -1 ? texto.length : fin;
      sustituciones.push(texto.slice(i + 1, cierre));
      limpio += " ";
      i = cierre + 1;
      continue;
    }

    limpio += c;
    i += 1;
  }

  return { limpio, sustituciones };
}

/** Índice (exclusivo) de la comilla doble que cierra la de la posición inicial. */
function cerrarComillasDobles(texto, inicio) {
  let i = inicio + 1;
  while (i < texto.length) {
    if (texto[i] === "\\") {
      i += 2;
      continue;
    }
    if (texto[i] === '"') return i + 1;
    i += 1;
  }
  return texto.length;
}

/** Índice del paréntesis que cierra el que abre en la posición dada. */
function parenCierre(texto, inicio) {
  let nivel = 0;
  let i = inicio;
  while (i < texto.length) {
    const c = texto[i];
    if (c === "(") nivel += 1;
    else if (c === ")") {
      nivel -= 1;
      if (nivel === 0) return i;
    }
    i += 1;
  }
  return texto.length;
}

/* ─────────────────────────────────── decisión ──────────────────────────────── */

const motivo = analizar(comando);
if (motivo) {
  denegar(motivo);
}

process.exit(0);
