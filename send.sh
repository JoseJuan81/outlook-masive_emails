#!/bin/bash
#
# Wrapper de envío: encadena los dos runtimes del flujo real.
#
#   1. WSL + uv   -> arma staging/emails_to_send.json (main.py)
#   2. Windows    -> send_from_staging.py envía vía Outlook COM
#
# `main.py` NUNCA se lanza con el Python de Windows: importa `domain.*` e
# `infrastructure.*`, que viven en el venv de uv. Solo `send_from_staging.py`
# se ejecuta con `python.exe`.
#
# El intérprete de Windows se resuelve en este orden:
#   1. $WINDOWS_PYTHON_PATH del entorno. Si la variable está definida pero
#      vacía, se ignora el valor del .env (útil para depurar).
#   2. WINDOWS_PYTHON_PATH del .env de la raíz del proyecto.
#   3. Instalaciones habituales bajo $WINDOWS_MOUNT_ROOT (por defecto /mnt/c).
#
# Variables de entorno:
#   WINDOWS_PYTHON_PATH  ruta al python.exe de Windows (con pywin32 instalado)
#   WINDOWS_MOUNT_ROOT   raíz del montaje de Windows en WSL (por defecto /mnt/c)
#
# Uso:
#   bash send.sh [--dry-run] [opciones de main.py]

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
STAGING_FILE="${PROJECT_ROOT}/staging/emails_to_send.json"
MOUNT_ROOT="${WINDOWS_MOUNT_ROOT:-/mnt/c}"

WINDOWS_PYTHON=""
WINDOWS_PYTHON_ORIGIN=""

log() {
    printf '%s\n' "$*"
}

error() {
    printf 'ERROR: %s\n' "$*" >&2
}

usage() {
    cat <<'EOF'
Uso: bash send.sh [--dry-run] [opciones de main.py]

  --dry-run   Resuelve el intérprete de Windows y muestra lo que haría
              (comando de uv, intérprete encontrado, staging). NO envía nada.
  -h, --help  Muestra esta ayuda.

Opciones de main.py (--view, --test-email) se pasan tal cual.
EOF
}

# Valor de una clave del .env. Devuelve 1 si el fichero o la clave no existen.
# Si la clave aparece varias veces gana la última (igual que python-dotenv).
dotenv_value() {
    local key="$1"
    local file="$2"
    local line trimmed rest value=""
    local found=0

    if [[ ! -f "$file" ]]; then
        return 1
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        trimmed="${line%$'\r'}"
        trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"

        if [[ -z "$trimmed" ]]; then
            continue
        fi
        if [[ "${trimmed:0:1}" == "#" ]]; then
            continue
        fi

        rest="$trimmed"
        if [[ "$rest" == "export "* ]]; then
            rest="${rest#export }"
            rest="${rest#"${rest%%[![:space:]]*}"}"
        fi
        if [[ "$rest" != "$key="* ]]; then
            continue
        fi

        value="${rest#"$key="}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ ${#value} -ge 2 ]]; then
            if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]]; then
                value="${value:1:${#value}-2}"
            elif [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
                value="${value:1:${#value}-2}"
            fi
        fi
        found=1
    done < "$file"

    if [[ "$found" -eq 1 ]]; then
        printf '%s' "$value"
        return 0
    fi
    return 1
}

# Instalaciones de Python habituales bajo el montaje de Windows.
candidate_paths() {
    local root="$1"
    local versions=(Python313 Python312 Python311 Python310 Python39)
    local version found

    # Instalaciones "para todos los usuarios" en la raíz de C:
    for version in "${versions[@]}"; do
        printf '%s\n' "${root}/${version}/python.exe"
    done

    # Anaconda / Miniconda a nivel de sistema:
    printf '%s\n' "${root}/ProgramData/Anaconda3/python.exe"
    printf '%s\n' "${root}/ProgramData/miniconda3/python.exe"
    printf '%s\n' "${root}/Anaconda3/python.exe"

    # Instalaciones por usuario bajo AppData. El placeholder /USER/ se mantiene
    # literal porque el nombre real de la carpeta de perfil de Windows puede
    # coincidir con él (p. ej. /mnt/c/Users/USER/).
    for version in "${versions[@]}"; do
        printf '%s\n' "${root}/Users/USER/AppData/Local/Programs/Python/${version}/python.exe"
    done
    printf '%s\n' "${root}/Users/USER/Anaconda3/python.exe"
    printf '%s\n' "${root}/Users/USER/miniconda3/python.exe"

    # Variantes con el usuario de WSL:
    if [[ -n "${USER:-}" ]]; then
        for version in "${versions[@]}"; do
            printf '%s\n' "${root}/Users/${USER}/AppData/Local/Programs/Python/${version}/python.exe"
        done
        printf '%s\n' "${root}/Users/${USER}/Anaconda3/python.exe"
        printf '%s\n' "${root}/Users/${USER}/miniconda3/python.exe"
    fi

    # Perfiles reales de Windows: el nombre de la carpeta de perfil no siempre
    # coincide con $USER de WSL.
    for found in "${root}"/Users/*/AppData/Local/Programs/Python/Python3*/python.exe; do
        if [[ -f "$found" ]]; then
            printf '%s\n' "$found"
        fi
    done
}

# Resuelve el python.exe de Windows. Deja el resultado en WINDOWS_PYTHON y
# WINDOWS_PYTHON_ORIGIN. Devuelve 1 si no encuentra ninguno y 2 si el valor
# explícito de WINDOWS_PYTHON_PATH apunta a un fichero inexistente.
resolve_windows_python() {
    local explicit="" origin="" candidate env_defined=0

    if [[ -n "${WINDOWS_PYTHON_PATH+x}" ]]; then
        env_defined=1
    fi

    if [[ -n "${WINDOWS_PYTHON_PATH:-}" ]]; then
        explicit="$WINDOWS_PYTHON_PATH"
        origin="entorno (WINDOWS_PYTHON_PATH)"
    elif [[ "$env_defined" -eq 0 ]]; then
        if explicit="$(dotenv_value WINDOWS_PYTHON_PATH "$ENV_FILE")"; then
            origin=".env (WINDOWS_PYTHON_PATH)"
        fi
    fi

    if [[ -n "$explicit" ]]; then
        if [[ -f "$explicit" ]]; then
            WINDOWS_PYTHON="$explicit"
            WINDOWS_PYTHON_ORIGIN="$origin"
            return 0
        fi
        error "WINDOWS_PYTHON_PATH apunta a un fichero que no existe:"
        error "  $explicit"
        error "Corrigí el valor en ${ENV_FILE} o exportalo con la ruta real."
        return 2
    fi

    while IFS= read -r candidate; do
        if [[ -f "$candidate" ]]; then
            WINDOWS_PYTHON="$candidate"
            WINDOWS_PYTHON_ORIGIN="autodetección"
            return 0
        fi
    done < <(candidate_paths "$MOUNT_ROOT")

    return 1
}

show_resolution_error() {
    error "No se encontró ningún intérprete de Windows (python.exe) para enviar los correos."
    error ""
    error "El envío necesita el Python NATIVO de Windows (con pywin32): win32com y"
    error "Outlook COM no funcionan dentro de WSL2."
    error ""
    error "Qué hacer (elegí una):"
    error "  1. Definí WINDOWS_PYTHON_PATH en el .env de la raíz del proyecto:"
    error "       ${ENV_FILE}"
    error "     con la ruta real de TU máquina, por ejemplo:"
    error "       WINDOWS_PYTHON_PATH=/mnt/c/Users/TU_USUARIO/AppData/Local/Programs/Python/Python313/python.exe"
    error ""
    error "  2. O exportala solo para esta sesión:"
    error "       export WINDOWS_PYTHON_PATH=/ruta/real/a/python.exe"
    error ""
    error "  3. Verificá que la ruta existe y tiene pywin32:"
    error "       ls -l \"\$WINDOWS_PYTHON_PATH\""
    error "       \"\$WINDOWS_PYTHON_PATH\" -c \"import win32com.client; print('pywin32 OK')\""
}

describe_staging() {
    local file="$1"
    local count=0

    printf '  ruta    : %s\n' "$file"
    if [[ -f "$file" ]]; then
        count="$(grep -c '"to":' "$file" || true)"
        printf '  estado  : existe\n'
    else
        printf '  estado  : no existe todavía (lo genera `uv run main.py`)\n'
    fi
    printf '  correos : %s\n' "$count"
}

run_dry_run() {
    local main_args_display="main.py"
    local arg

    for arg in "${MAIN_ARGS[@]+"${MAIN_ARGS[@]}"}"; do
        printf -v arg '%q' "$arg"
        main_args_display="${main_args_display} ${arg}"
    done

    log "============================================================"
    log " send.sh -- simulacro (--dry-run): no se prepara ni se envía nada"
    log "============================================================"
    log ""
    log "Intérprete de Windows (Outlook COM):"
    printf '  origen  : %s\n' "$WINDOWS_PYTHON_ORIGIN"
    printf '  ruta    : %s\n' "$WINDOWS_PYTHON"
    printf '  existe  : %s\n' "$( [[ -f "$WINDOWS_PYTHON" ]] && printf 'sí' || printf 'NO' )"
    log ""
    log "Staging:"
    describe_staging "$STAGING_FILE"
    log ""
    log "Comandos que se ejecutarían (NO se ejecutan):"
    log "  1) uv run ${main_args_display}"
    log "  2) ${WINDOWS_PYTHON} send_from_staging.py"
    log ""
    if command -v uv >/dev/null 2>&1; then
        printf 'uv       : %s\n' "$(command -v uv)"
    else
        printf 'uv       : NO ENCONTRADO en el PATH (hace falta para el paso 1)\n'
    fi
    log ""
    log "Nada se ha enviado. Quitá --dry-run para hacer el envío real."
}

main() {
    local dry_run=0
    local arg

    MAIN_ARGS=()
    for arg in "$@"; do
        case "$arg" in
            --dry-run)
                dry_run=1
                ;;
            -h|--help)
                usage
                return 0
                ;;
            *)
                MAIN_ARGS+=("$arg")
                ;;
        esac
    done

    local status=0
    resolve_windows_python || status=$?
    if [[ "$status" -ne 0 ]]; then
        if [[ "$status" -ne 2 ]]; then
            show_resolution_error
        fi
        return 1
    fi

    if [[ "$dry_run" -eq 1 ]]; then
        run_dry_run
        return 0
    fi

    if ! command -v uv >/dev/null 2>&1; then
        error "uv no está instalado o no está en el PATH."
        error "Instalalo con: curl -LsSf https://astral.sh/uv/install.sh | sh"
        return 1
    fi

    cd "$PROJECT_ROOT"

    log "==> [1/2] Preparando el staging (Python de WSL, venv de uv)"
    uv run main.py "${MAIN_ARGS[@]+"${MAIN_ARGS[@]}"}"

    log "==> [2/2] Enviando con Outlook COM (Python de Windows)"
    log "    intérprete: ${WINDOWS_PYTHON}"
    "$WINDOWS_PYTHON" send_from_staging.py
}

main "$@"
