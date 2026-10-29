#!/usr/bin/env node
// Puerta de calidad — hook SubagentStop + CLI manual.
//
// Un agente que se autoevalúa siempre se aprueba. Este script vuelve a ejecutar
// los comandos de calidad por su cuenta y bloquea al agente si fallan, pase lo
// que pase en su reporte.
//
// Uso:
//   node .claude/hooks/puerta-calidad.mjs [rapida|completa]
//
// En hook, Claude Code pasa por stdin el JSON del evento (session_id, agent_id,
// agent_type). Si stdin es una TTY no se lee nunca: el script se quedaría
// esperando datos que no llegan.
//
// Salidas: 0 = pasa (o se salta) · 2 = bloquea, con el motivo en stderr.
//
// No conoce ningún comando: los lee de .claude/verificacion.json.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

let RAIZ;
try {
  ({ RAIZ } = await import("./permitidas.mjs"));
} catch {
  // La puerta no puede morir porque un archivo hermano esté roto: si falla la
  // importación, la raíz se resuelve igual (el script vive en <raiz>/.claude/hooks).
  RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
}

const CONFIG_POR_DEFECTO = join(RAIZ, ".claude/verificacion.json");
const DIR_ESTADO = join(RAIZ, ".claude/cache/bloqueos");

/** Timeout del evento SubagentStop (segundos) declarado en .claude/settings.json. */
const TIMEOUT_EVENTO_MS = 900_000;
/** pytest con más de 1 MB de salida revienta el buffer por defecto de Node. */
const MAX_BUFFER = 16 * 1024 * 1024;
/** Cuánto se espera a stdin antes de seguir sin evento (nunca colgar). */
const LECTURA_STDIN_MS = 2000;
/** Líneas de salida que se pegan en el mensaje de rechazo, por comprobación. */
const LINEAS_POR_COMPROBACION = 40;

/** Tokens de `uv run` que no son el nombre de la herramienta. */
const TOKENS_IGNORADOS = new Set(["uv", "run", "--no-sync", "--fiable", "node"]);

// ---------------------------------------------------------------------------
// Entrada
// ---------------------------------------------------------------------------

/** Parsea el JSON del evento; si no es válido, se sigue sin evento. */
function parseSeguro(texto) {
  try {
    return JSON.parse(texto || "{}");
  } catch {
    return {};
  }
}

/**
 * Lee el JSON del evento por stdin. Nunca se cuelga: si stdin es una TTY no se
 * lee, y si no llegan datos en LECTURA_STDIN_MS se sigue sin evento.
 */
function leerEntrada() {
  return new Promise((resolver) => {
    if (process.stdin.isTTY) {
      resolver({});
      return;
    }
    let datos = "";
    let resuelto = false;
    let timer;
    const terminar = (valor) => {
      if (resuelto) return;
      resuelto = true;
      clearTimeout(timer);
      resolver(valor);
    };
    timer = setTimeout(() => {
      process.stdin.destroy();
      terminar(parseSeguro(datos));
    }, LECTURA_STDIN_MS);
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      datos += chunk;
    });
    process.stdin.on("end", () => terminar(parseSeguro(datos)));
    process.stdin.on("error", () => terminar(parseSeguro(datos)));
  });
}

function leerConfig() {
  const ruta = process.env.PUERTA_VERIFICACION
    ? resolve(RAIZ, process.env.PUERTA_VERIFICACION)
    : CONFIG_POR_DEFECTO;
  if (!existsSync(ruta)) {
    console.error(`Puerta de calidad: falta ${ruta}. No hay nada que verificar.`);
    process.exit(0);
  }
  try {
    return JSON.parse(readFileSync(ruta, "utf8"));
  } catch (error) {
    console.error(`Puerta de calidad: ${ruta} no es JSON válido: ${error.message}`);
    process.exit(0);
  }
}

// ---------------------------------------------------------------------------
// Disponibilidad de la herramienta
// ---------------------------------------------------------------------------

/** Divide un comando en tokens respetando comillas simples y dobles. */
function tokenizar(comando) {
  const tokens = [];
  let actual = "";
  let hayToken = false;
  let comilla = null;
  for (const caracter of comando) {
    if (comilla) {
      if (caracter === comilla) comilla = null;
      else actual += caracter;
      continue;
    }
    if (caracter === '"' || caracter === "'") {
      comilla = caracter;
      hayToken = true;
      continue;
    }
    if (/\s/.test(caracter)) {
      if (hayToken) {
        tokens.push(actual);
        actual = "";
        hayToken = false;
      }
      continue;
    }
    actual += caracter;
    hayToken = true;
  }
  if (hayToken) tokens.push(actual);
  return tokens;
}

/**
 * Nombre de la herramienta que el comando invoca. `null` significa «no hay
 * nada que comprobar»: los comandos `node ...` usan el propio node, que está
 * disponible por definición.
 */
function extraerHerramienta(tokens) {
  if (tokens[0] === "node") return null;
  if (tokens[0] === "uv" && tokens[1] === "run") {
    for (const token of tokens.slice(2)) {
      if (token.startsWith("-")) continue;
      if (TOKENS_IGNORADOS.has(token)) continue;
      return token;
    }
  }
  return null;
}

/**
 * ¿Está la herramienta instalada? Se mira primero el venv del proyecto (es lo
 * que `uv run` usa) y después el PATH. Una herramienta ausente NO es un
 * comando roto: es "no disponible".
 */
function herramientaDisponible(tool) {
  if (!tool) return { disponible: true };
  const candidatos = [
    join(RAIZ, ".venv/bin", tool),
    join(RAIZ, ".venv/Scripts", `${tool}.exe`),
  ];
  for (const candidato of candidatos) {
    if (existsSync(candidato)) return { disponible: true, via: candidato };
  }
  if (!/^[A-Za-z0-9_.+-]+$/.test(tool)) return { disponible: false };
  const busqueda = spawnSync("/bin/sh", ["-c", `command -v ${tool}`], {
    encoding: "utf8",
    timeout: 10_000,
  });
  if (busqueda.status === 0 && (busqueda.stdout ?? "").trim()) {
    return { disponible: true, via: busqueda.stdout.trim() };
  }
  return { disponible: false };
}

/** Motivo accionable para una herramienta ausente. */
function motivoAusente(tool) {
  return (
    `«${tool}» no está instalado (no aparece en .venv/bin/ ni en el PATH).\n` +
    `Instalalo con: uv add --dev ${tool}\n` +
    `Si no corresponde a este repo, quitá la comprobación de .claude/verificacion.json.`
  );
}

// ---------------------------------------------------------------------------
// Ejecución
// ---------------------------------------------------------------------------

/** Recorta la salida por el centro: el principio y el final son lo informativo. */
function recortar(texto, maxLineas = LINEAS_POR_COMPROBACION) {
  const lineas = texto.split("\n");
  if (lineas.length <= maxLineas) return texto;
  const mitad = Math.floor(maxLineas / 2);
  return [
    ...lineas.slice(0, mitad),
    `   … (${lineas.length - maxLineas} líneas omitidas) …`,
    ...lineas.slice(-mitad),
  ].join("\n");
}

/**
 * Ejecuta una comprobación y devuelve su resultado crudo.
 * Estados: ok · falla · noDisponible · noAplica.
 */
function ejecutar(comprobacion, timeouts) {
  const timeoutMs = timeouts[comprobacion.etiqueta] ?? timeouts.porDefecto;
  const tokens = tokenizar(comprobacion.comando ?? "");
  if (tokens.length === 0) {
    return {
      ...comprobacion,
      estado: "falla",
      codigo: null,
      motivo: "comando vacío",
      salida: `La comprobación «${comprobacion.etiqueta}» no tiene comando.`,
    };
  }

  const tool = extraerHerramienta(tokens);
  const disponibilidad = herramientaDisponible(tool);
  if (!disponibilidad.disponible) {
    return {
      ...comprobacion,
      estado: "noDisponible",
      codigo: null,
      motivo: "no disponible",
      salida: motivoAusente(tool),
    };
  }

  const resultado = spawnSync(tokens[0], tokens.slice(1), {
    cwd: RAIZ,
    encoding: "utf8",
    timeout: timeoutMs,
    maxBuffer: MAX_BUFFER,
    env: { ...process.env, CI: "1", FORCE_COLOR: "0", NO_COLOR: "1" },
  });

  const salida = `${resultado.stdout ?? ""}${resultado.stderr ?? ""}`.trim();

  if (resultado.error) {
    const esTimeout = resultado.error.code === "ETIMEDOUT";
    return {
      ...comprobacion,
      estado: "falla",
      codigo: null,
      motivo: esTimeout ? `tiempo agotado (${timeoutMs} ms)` : "no se pudo ejecutar",
      salida: `${esTimeout ? `El comando no terminó en ${timeoutMs} ms.` : `No se pudo ejecutar el comando: ${resultado.error.message}`}\n${salida}`.trim(),
    };
  }

  // Red de seguridad: "Failed to spawn" es "la herramienta no está", no
  // "el comando está roto".
  if (/Failed to spawn/i.test(salida)) {
    return {
      ...comprobacion,
      estado: "noDisponible",
      codigo: resultado.status,
      motivo: "no disponible",
      salida: `${salida}\n${motivoAusente(tool)}`,
    };
  }

  if (resultado.status === 0) {
    return { ...comprobacion, estado: "ok", codigo: 0, motivo: "pasa", salida };
  }
  if (resultado.status === 3) {
    return { ...comprobacion, estado: "noAplica", codigo: 3, motivo: "no aplica", salida };
  }
  return {
    ...comprobacion,
    estado: "falla",
    codigo: resultado.status,
    motivo: resultado.status === 2 ? "error de ejecución" : "fallo",
    salida,
  };
}

/**
 * Traduce el resultado crudo al veredicto de la puerta.
 *
 *   obligatorio + herramienta ausente/no aplica → falla (bloquea)
 *   no obligatorio + herramienta ausente/no aplica → saltado (no bloquea)
 *   cualquier otro fallo                        → falla (bloquea)
 *
 * La disponibilidad de la herramienta nunca suaviza un fallo.
 */
function veredicto(resultado, obligatorio) {
  if (resultado.estado === "ok") return "ok";
  if (resultado.estado === "falla") return "falla";
  return obligatorio ? "falla" : "saltado";
}

// ---------------------------------------------------------------------------
// Contador de bloqueos
// ---------------------------------------------------------------------------

function rutaContador(clave) {
  return join(DIR_ESTADO, `${clave.replace(/[^A-Za-z0-9_-]/g, "_")}.json`);
}

function leerContador(clave) {
  try {
    const previo = JSON.parse(readFileSync(rutaContador(clave), "utf8"));
    return typeof previo.n === "number" ? previo.n : 0;
  } catch {
    return 0;
  }
}

function escribirContador(clave, n) {
  mkdirSync(DIR_ESTADO, { recursive: true });
  writeFileSync(
    rutaContador(clave),
    JSON.stringify({ n, ultimo: new Date().toISOString() }),
  );
}

// ---------------------------------------------------------------------------
// Mensaje de rechazo
// ---------------------------------------------------------------------------

function mensajeRechazo(fallos, intento, maximo) {
  const detalle = fallos
    .map((f) => {
      const causa =
        f.estado === "noDisponible"
          ? "no disponible: la herramienta no está instalada"
          : f.estado === "noAplica"
            ? "no aplica (código 3) y la comprobación es obligatoria"
            : f.codigo === null || f.codigo === undefined
              ? f.motivo
              : `salió con código ${f.codigo}`;
      return `### ${f.etiqueta} — \`${f.comando}\` ${causa}\n\n${recortar(f.salida)}`;
    })
    .join("\n\n");

  return `PUERTA DE CALIDAD: BLOQUEADO (intento ${intento} de ${maximo})

No has terminado. ${fallos.length} comprobación(es) de calidad fallan AHORA MISMO en el árbol de trabajo. Esta es la salida real de los comandos, ejecutados por la puerta, no por ti:

${detalle}

Qué tenés que hacer: arreglá la causa real y volvé a ejecutar los comandos vos mismo hasta que salgan con código 0. Después pegá su salida literal en tu reporte.

Prohibido para pasar esta puerta:
- Debilitar un test: cambiar una aserción, agregar @pytest.skip / @pytest.xfail, subir un timeout, borrar un caso, o mockear el comportamiento que está bajo prueba.
- Regenerar la línea base congelada (.claude/linea-base.json) para que un error heredado deje de contar. Solo la regenera el usuario, y solo a la baja.
- Tocar la configuración para silenciar un fallo: pyproject.toml, uv.lock, pytest.ini, setup.cfg. Tampoco # noqa ni # pragma: no cover.
- Declararte terminado con el fallo "documentado como conocido", ni con "es preexistente, lo anoto y sigo". Un fallo preexistente se reporta al Coordinador.
- Esquivar el fallo cambiando el alcance: borrar el archivo que falla, borrar el test que lo revela, o mover el código para que la línea base lo ignore.
- Arreglar en el mismo cambio un bug que no es tuyo.

Si el fallo no es tuyo: si el comando falla en un archivo que NO es tuyo y hay otros agentes trabajando en paralelo, repetí el comando antes de investigarlo: casi siempre es escritura concurrente.

Restricciones de plataforma que no se negocian:
- send_from_staging.py permanece standalone: sin imports de domain, application, infrastructure, ports ni html.
- Paths absolutos con Path(__file__).resolve().parent.
- Filtrar los archivos .Identifier al listar imágenes en WSL.
- El subject se lee de html/templates/subject.txt, nunca hardcodeado.`;
}

// ---------------------------------------------------------------------------

const entrada = await leerEntrada();
const config = leerConfig();
const perfil = process.argv[2] ?? "rapida";
const comprobaciones = config.perfiles?.[perfil];

if (!Array.isArray(comprobaciones)) {
  console.error(
    `Puerta de calidad: no existe el perfil "${perfil}" en .claude/verificacion.json`,
  );
  process.exit(2);
}

// Fail-closed por tipo de agente: si el evento dice quién es y ese rol no está
// vigilado, la puerta no comprueba nada (no es trabajo suyo). Si el evento NO
// trae agent_type, se ejecutan todas las comprobaciones: nunca se sale en
// silencio por no saber quién eres.
const vigilados = Array.isArray(config.agentesVigilados) ? config.agentesVigilados : [];
const tipoAgente = typeof entrada.agent_type === "string" ? entrada.agent_type : "";
if (tipoAgente && vigilados.length > 0 && !vigilados.includes(tipoAgente)) {
  console.error(
    `Puerta de calidad: el agente «${tipoAgente}» no está en agentesVigilados; no se ejecuta ninguna comprobación.`,
  );
  process.exit(0);
}

const timeouts = {
  ...(config.timeouts ?? {}),
  porDefecto: config.timeoutPorComandoMs ?? 300_000,
};

// Coherencia con el timeout del evento: si el perfil no cabe, se avisa (pero no
// se rompe nada). El perfil 'rapida' es el único que se registra como hook.
const presupuesto = comprobaciones.reduce(
  (total, c) => total + (timeouts[c.etiqueta] ?? timeouts.porDefecto),
  0,
);
if (presupuesto > TIMEOUT_EVENTO_MS) {
  console.error(
    `Puerta de calidad: aviso — el perfil «${perfil}» suma ${Math.round(presupuesto / 1000)} s de timeouts internos, más que el timeout del evento (${TIMEOUT_EVENTO_MS / 1000} s). Si se registra como hook, el evento puede cortarlo antes de terminar.`,
  );
}

const resultados = comprobaciones.map((comprobacion) => {
  const obligatorio = comprobacion.obligatorio !== false;
  const crudo = ejecutar(comprobacion, timeouts);
  return { ...crudo, obligatorio, veredicto: veredicto(crudo, obligatorio) };
});

const fallos = resultados.filter((r) => r.veredicto === "falla");
const saltados = resultados.filter((r) => r.veredicto === "saltado");

const resumen = resultados
  .map((r) => {
    const marca = r.veredicto === "ok" ? "OK" : r.veredicto === "saltado" ? "SALTADO" : "FALLA";
    const nota =
      r.veredicto === "saltado" ? ` — ${r.motivo}` : r.veredicto === "falla" ? ` — ${r.motivo}` : "";
    return `${marca.padEnd(7)} ${r.etiqueta.padEnd(11)} (${r.comando})${nota}`;
  })
  .join("\n");

console.log(`Puerta de calidad — perfil "${perfil}"\n\n${resumen}`);

if (fallos.length === 0) {
  // Contador por agent_id (no por tipo de agente): varios subagentes del mismo
  // rol en paralelo no comparten presupuesto de bloqueos.
  const agentId =
    typeof entrada.agent_id === "string" && entrada.agent_id ? entrada.agent_id : null;
  if (agentId) {
    const clave = agentId;
    if (leerContador(clave) > 0) escribirContador(clave, 0);
  }
  process.exit(0);
}

// Anti-bucle: la CLI manual (sin agent_id) siempre bloquea, porque ahí el
// bloqueo lo pidió un humano explícitamente. El contador solo aplica al hook.
const agentId =
  typeof entrada.agent_id === "string" && entrada.agent_id ? entrada.agent_id : null;
const maximo = config.maxBloqueosPorAgente ?? 3;
const previo = agentId ? leerContador(agentId) : 0;

if (agentId && previo >= maximo) {
  console.error(
    `PUERTA DE CALIDAD: agotados los ${maximo} bloqueos del agente «${agentId}». Se deja pasar para no girar en bucle, PERO EL TRABAJO NO CUMPLE. Fallan: ${fallos.map((f) => f.etiqueta).join(", ")}. Escala al Coordinador.`,
  );
  process.exit(0);
}

const intento = previo + 1;
if (agentId) escribirContador(agentId, intento);

// Bloqueo de un SubagentStop: código de salida 2 + el motivo en stderr. Es el
// mecanismo universal y documentado; el stdout queda limpio (sin JSON) para no
// romper el parseo de la salida del hook.
console.error(mensajeRechazo(fallos, intento, maximo));
process.exit(2);
