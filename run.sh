#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_DIR="/var/log/callmetric"
PID_FILE="/tmp/callmetric-agent.pid"

mkdir -p "$LOG_DIR"

# Backoff exponential: 10s -> 30s -> 60s -> 60s (max)
BACKOFF_SLEEPS=(10 30 60)
MAX_BACKOFF=60
attempt=0
max_attempts=10  # reinicia hasta 10 veces, luego espera intervención manual

cleanup() {
    local exit_code=$?
    if [ -f "$PID_FILE" ]; then
        kill "$(cat "$PID_FILE")" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
    exit "$exit_code"
}
trap cleanup SIGINT SIGTERM EXIT

activate_venv() {
    if [ -f "$VENV_DIR/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    elif [ -f "$VENV_DIR/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/Scripts/activate"
    else
        echo "[run.sh] ERROR: No se encuentra el virtualenv en $VENV_DIR"
        exit 1
    fi
}

run_agent() {
    activate_venv
    cd "$SCRIPT_DIR"
    exec python -m src.main
}

while [ $attempt -lt $max_attempts ]; do
    echo "[run.sh] Iniciando agente (intento $((attempt + 1))/$max_attempts)..."

    # Ejecutar en background para capturar PID
    run_agent &
    AGENT_PID=$!
    echo $AGENT_PID > "$PID_FILE"

    # Esperar al agente
    wait $AGENT_PID
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "[run.sh] Agente terminó con código 0 (salida limpia). No se reintenta."
        exit 0
    fi

    attempt=$((attempt + 1))

    if [ $attempt -ge $max_attempts ]; then
        echo "[run.sh] ERROR: Se alcanzó el máximo de reintentos ($max_attempts). Abortando."
        exit 1
    fi

    # Calcular sleep con backoff
    idx=$((attempt - 1))
    if [ $idx -ge ${#BACKOFF_SLEEPS[@]} ]; then
        sleep_time=$MAX_BACKOFF
    else
        sleep_time=${BACKOFF_SLEEPS[$idx]}
    fi

    echo "[run.sh] Agente terminó con código $EXIT_CODE. Reintentando en ${sleep_time}s..."
    sleep "$sleep_time"
done
