#!/usr/bin/env node
// Puerta de calidad — hook SubagentStop.
//
// Un agente que se autoevalúa siempre se aprueba. Este hook vuelve a ejecutar
// los comandos de calidad por su cuenta y bloquea al agente si fallan, pase lo
// que pase en su reporte.
//
// Uso:
//   node .claude/hooks/puerta-calidad.mjs            → modo hook (lee JSON por stdin)
//   node .claude/hooks/puerta-calidad.mjs completa   → modo manual, perfil completo
//
// Salidas: 0 = pasa (o se salta) · 2 = bloquea, con el detalle en stderr.
//
// No conoce ningún comando: los lee de .claude/verificacion.json (§5.4).
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const CONFIG = join(RAIZ, ".claude/verificacion.json");
const DIR_ESTADO = join(RAIZ, ".claude/cache/bloqueos");

/** Lee el JSON del hook por stdin. Devuelve `{}` si no hay nada (modo manual). */
function leerEntrada() {
  try {
    return JSON.parse(readFileSync(0, "utf8") || "{}");
  } catch {
    return {};
  }
}

function leerConfig() {
  if (!existsSync(CONFIG)) {
    console.error(`Puerta de calidad: falta ${CONFIG}. No hay nada que verificar.`);
    process.exit(0);
  }
  return JSON.parse(readFileSync(CONFIG, "utf8"));
}

/**
 * Cuenta los bloqueos por agente. `SubagentStop` no recibe `stop_hook_active`
 * (verificado contra la documentación oficial), así que la guarda anti-bucle
 * tiene que llevar su propio contador: tras N bloqueos deja pasar para que el
 * fallo escale al orquestador en vez de girar indefinidamente.
 */
function contarBloqueo(clave) {
  mkdirSync(DIR_ESTADO, { recursive: true });
  const archivo = join(DIR_ESTADO, `${clave.replace(/[^a-zA-Z0-9_-]/g, "_")}.json`);
  const previo = existsSync(archivo) ? JSON.parse(readFileSync(archivo, "utf8")) : { n: 0 };
  const actual = { n: previo.n + 1, ultimo: new Date().toISOString() };
  writeFileSync(archivo, JSON.stringify(actual));
  return actual.n;
}

function limpiarContador(clave) {
  const archivo = join(DIR_ESTADO, `${clave.replace(/[^a-zA-Z0-9_-]/g, "_")}.json`);
  if (existsSync(archivo)) writeFileSync(archivo, JSON.stringify({ n: 0 }));
}

/** Comprueba que el comando es ejecutable antes de correrlo (tolerancia §5.4). */
function comandoDisponible(comando) {
  const scriptPnpm = comando.match(/^pnpm (?!exec |dlx )([\w:-]+)/);
  if (scriptPnpm) {
    try {
      const pkg = JSON.parse(readFileSync(join(RAIZ, "package.json"), "utf8"));
      return Boolean(pkg.scripts?.[scriptPnpm[1]]);
    } catch {
      return false;
    }
  }
  const scriptNpm = comando.match(/^npm (?!exec )run ([\w:-]+)/);
  if (scriptNpm) {
    try {
      const pkg = JSON.parse(readFileSync(join(RAIZ, "package.json"), "utf8"));
      return Boolean(pkg.scripts?.[scriptNpm[1]]);
    } catch {
      return false;
    }
  }
  return true;
}

function ejecutar(comprobacion, timeouts) {
  if (!comandoDisponible(comprobacion.comando)) {
    return { ...comprobacion, estado: "saltado", salida: "el comando no existe en package.json" };
  }
  const timeoutMs =
    (timeouts && timeouts[comprobacion.etiqueta]) ||
    timeouts?.porDefecto ||
    600000;
  try {
    const salida = execSync(comprobacion.comando, {
      cwd: RAIZ,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: timeoutMs,
      env: { ...process.env, CI: "1", FORCE_COLOR: "0" },
    });
    return { ...comprobacion, estado: "ok", salida: salida.trim() };
  } catch (error) {
    const salida = `${error.stdout ?? ""}${error.stderr ?? ""}`.trim() || String(error.message);
    return { ...comprobacion, estado: "falla", salida, codigo: error.status ?? 1 };
  }
}

/** Recorta la salida por el centro: el principio y el final son lo informativo. */
function recortar(texto, maxLineas = 60) {
  const lineas = texto.split("\n");
  if (lineas.length <= maxLineas) return texto;
  const cabeza = lineas.slice(0, Math.floor(maxLineas / 2));
  const cola = lineas.slice(-Math.floor(maxLineas / 2));
  return [...cabeza, `   … (${lineas.length - maxLineas} líneas omitidas) …`, ...cola].join("\n");
}

function mensajeRechazo(fallos, intento, maximo) {
  const detalle = fallos
    .map(
      (f) =>
        `### ${f.etiqueta} — \`${f.comando}\` salió con código ${f.codigo}\n\n\`\`\`\n${recortar(f.salida)}\n\`\`\``,
    )
    .join("\n\n");

  return `PUERTA DE CALIDAD: BLOQUEADO (intento ${intento} de ${maximo})

No has terminado. ${fallos.length} comprobación(es) de calidad fallan AHORA MISMO en el
árbol de trabajo. Esta es la salida real de los comandos, ejecutados por la puerta,
no por ti:

${detalle}

## Qué tienes que hacer

Arreglar la causa real y volver a ejecutar los comandos tú mismo hasta que salgan
con código 0. Después pega su salida literal en tu reporte.

## Prohibido para pasar esta puerta

- Debilitar un test: cambiar una aserción, \`.skip\`, \`.only\`, subir un timeout,
  borrar un caso, o mockear el comportamiento que está bajo prueba.
- Regenerar la línea base congelada (\`.claude/linea-base.json\`) para que un error
  heredado deje de contar. Solo la regenera el usuario, y solo a la baja.
- Tocar la configuración del linter, del compilador o de vitest (\`eslint.config.js\`,
  \`tsconfig.json\`, \`vitest.config.ts\`) para silenciar el fallo.
- Añadir \`eslint-disable\`, \`@ts-ignore\` o \`@ts-expect-error\` para tapar el error.
- Declararte terminado con el fallo "documentado como conocido".
- Introducir lenguaje que medicalice, diagnostique o juzgue estados emocionales.
- Inferir la fase activa a partir de duraciones de referencia o bloques temporales.
- Exponer notas, sangrado, dolor, síntomas o historial emocional en el Modo Pareja.
- Crear tablas de Supabase sin RLS habilitado y políticas por \`user_id\`.

Si el fallo aparece en un archivo que NO es tuyo y hay otros agentes trabajando en
paralelo, vuelve a ejecutar el comando antes de investigarlo: casi siempre es
escritura concurrente, no un defecto real.

Si tras arreglarlo de verdad el fallo persiste y crees que es ajeno a tu tarea,
dilo explícitamente en tu reporte con la salida pegada, y para. No bajes el
estándar para pasar.`;
}

// ---------------------------------------------------------------------------

const entrada = leerEntrada();
const config = leerConfig();
const perfilPedido = process.argv[2];
const modoManual = Boolean(perfilPedido);
const perfil = perfilPedido ?? "rapida";
const comprobaciones = config.perfiles?.[perfil];

if (!comprobaciones) {
  console.error(`Puerta de calidad: no existe el perfil "${perfil}" en verificacion.json`);
  process.exit(modoManual ? 1 : 0);
}

// En modo hook, solo vigila a los agentes que escriben código. `planificador`,
// `diseñador-web`, `luna-serena` y `revisor` no tocan src/, y hacerles correr la
// suite entera solo añade contención de CPU (§5.5).
const tipoAgente = entrada.agent_type ?? entrada.agent_id ?? "desconocido";
const vigilados = config.agentesVigilados ?? [];
if (!modoManual && vigilados.length > 0 && !vigilados.includes(tipoAgente)) {
  process.exit(0);
}

const timeouts = config.timeouts
  ? { ...config.timeouts, porDefecto: config.timeoutPorComandoMs ?? 600000 }
  : { porDefecto: config.timeoutPorComandoMs ?? 600000 };
const resultados = comprobaciones.map((c) => ejecutar(c, timeouts));
const fallos = resultados.filter((r) => r.estado === "falla");
const saltados = resultados.filter((r) => r.estado === "saltado");

const resumen = resultados
  .map(
    (r) =>
      `${r.estado === "ok" ? "PASA" : r.estado === "saltado" ? "SALTADO" : "FALLA"}  ${r.etiqueta}  (${r.comando})`,
  )
  .join("\n");

if (modoManual) {
  console.log(`Puerta de calidad — perfil "${perfil}"\n\n${resumen}`);
  if (saltados.length) {
    console.log(`\nSaltados: ${saltados.map((s) => `${s.etiqueta} (${s.salida})`).join(", ")}`);
  }
  if (fallos.length) {
    console.error(`\n${mensajeRechazo(fallos, 1, config.maxBloqueosPorAgente ?? 3)}`);
    process.exit(2);
  }
  process.exit(0);
}

const clave = `${entrada.session_id ?? "sin-sesion"}-${tipoAgente}`;

if (fallos.length === 0) {
  limpiarContador(clave);
  process.exit(0);
}

const maximo = config.maxBloqueosPorAgente ?? 3;
const intento = contarBloqueo(clave);

if (intento > maximo) {
  // Guarda anti-bucle: deja pasar para que el fallo escale al orquestador, pero
  // deja constancia de que pasó sin cumplir.
  limpiarContador(clave);
  console.error(
    `PUERTA DE CALIDAD: agotados los ${maximo} bloqueos para "${tipoAgente}". Se deja pasar ` +
      `para no girar en bucle, PERO EL TRABAJO NO CUMPLE. Fallan: ` +
      `${fallos.map((f) => f.etiqueta).join(", ")}. Escala al orquestador.`,
  );
  process.exit(0);
}

const razon = mensajeRechazo(fallos, intento, maximo);

// Se emiten las dos formas documentadas de bloqueo: el JSON estructurado (que
// entrega `reason` al agente) y el código 2 con stderr. La documentación indica
// que en SubagentStop el stderr del código 2 se muestra solo al usuario, así que
// el JSON es lo que garantiza que el agente reciba el motivo.
console.log(JSON.stringify({ decision: "block", reason: razon }));
console.error(razon);
process.exit(2);