#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"
SCRIPT="$ROOT_DIR/02_Human_Editorial_Workspace/scripts/prepare_lexical_data.py"
LOG_DIR="$ROOT_DIR/02_Human_Editorial_Workspace/.ttt_workbench/logs"

mkdir -p "$LOG_DIR"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Virtual environment not found at $VENV_PY" >&2
  echo "Run ./ttt.sh workbench once, or create .venv first." >&2
  exit 1
fi

if [[ "${1:-}" == "--background" ]]; then
  shift
  LOG_FILE="$LOG_DIR/prepare_lexical_data_$(date +%Y%m%d_%H%M%S).log"
  nohup "$VENV_PY" -u "$SCRIPT" "$@" >"$LOG_FILE" 2>&1 &
  PID=$!
  echo "Started lexical data prep in background."
  echo "PID: $PID"
  echo "Log: $LOG_FILE"
  exit 0
fi

exec "$VENV_PY" "$SCRIPT" "$@"
