#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
WORKBENCH_REQUIREMENTS="$ROOT_DIR/requirements-workbench.txt"
WORKBENCH_HASH_FILE="$VENV_DIR/.workbench_requirements.sha256"

show_help() {
  cat <<'EOF'
TTT root launcher

Usage:
  ./ttt.sh                Launch the browser workbench
  ./ttt.sh web            Launch the browser workbench
  ./ttt.sh web-fake       Launch the browser workbench with fake LLM responses
  ./ttt.sh prep-data      Download/build offline lexical data
  ./ttt.sh smoke          Run the scripted workbench smoke test
  ./ttt.sh test           Run the ttt_core unit tests
  ./ttt.sh epub           Build EPUB output
  ./ttt.sh help           Show this help

Notes:
  - The default command is `web`.
  - `prep-data --background` runs lexical data preparation in the background.
EOF
}

requirements_hash() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$WORKBENCH_REQUIREMENTS" | awk '{print $1}'
    return
  fi
  "$VENV_PY" - <<PY
import hashlib
from pathlib import Path
print(hashlib.sha256(Path("$WORKBENCH_REQUIREMENTS").read_bytes()).hexdigest())
PY
}

ensure_workbench_env() {
  if [[ ! -x "$VENV_PY" ]]; then
    python3 -m venv "$VENV_DIR"
  fi

  local current_hash
  current_hash="$(requirements_hash)"
  if [[ ! -f "$WORKBENCH_HASH_FILE" ]] || [[ "$(cat "$WORKBENCH_HASH_FILE")" != "$current_hash" ]]; then
    "$VENV_PY" -m pip install --upgrade pip >/dev/null
    "$VENV_PY" -m pip install -r "$WORKBENCH_REQUIREMENTS"
    printf '%s\n' "$current_hash" > "$WORKBENCH_HASH_FILE"
  fi
}

python_env() {
  printf '%s:%s%s' "$ROOT_DIR/src" "$ROOT_DIR" "${PYTHONPATH:+:$PYTHONPATH}"
}

PID_DIR="$ROOT_DIR/.ttt_workbench"
mkdir -p "$PID_DIR"
WEB_PID_FILE="$PID_DIR/ttt-web.pid"
PREP_PID_FILE="$PID_DIR/ttt-prep-data.pid"
EPUB_PID_FILE="$PID_DIR/ttt-epub.pid"

_kill_by_pidfile() {
  local pidfile="$1"
  local name="$2"
  if [[ -f "$pidfile" ]]; then
    local old_pid
    old_pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      echo "Stopping existing $name (PID $old_pid)..."
      kill -TERM "$old_pid" 2>/dev/null || true
      local waited=0
      while kill -0 "$old_pid" 2>/dev/null && [[ $waited -lt 5 ]]; do
        sleep 1
        waited=$((waited + 1))
      done
      if kill -0 "$old_pid" 2>/dev/null; then
        echo "Forcing $name termination..."
        kill -KILL "$old_pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pidfile"
  fi
}

_write_pidfile() {
  printf '%s\n' "$$" > "$1"
}

run_web() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  local host="${TTT_WEB_HOST:-127.0.0.1}"
  local port="${TTT_WEB_PORT:-8765}"

  _kill_by_pidfile "$WEB_PID_FILE" "web server"
  _write_pidfile "$WEB_PID_FILE"

  echo "TTT Browser Workbench: http://$host:$port"
  exec env PYTHONPATH="$(python_env)" "$VENV_PY" -m uvicorn ttt_webapp.app:app --host "$host" --port "$port"
}

run_prep_data() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  export PYTHONPATH="$(python_env)"
  chmod +x src/ttt_workbench/scripts/prepare_lexical_data.sh
  _kill_by_pidfile "$PREP_PID_FILE" "prep-data"
  _write_pidfile "$PREP_PID_FILE"
  exec src/ttt_workbench/scripts/prepare_lexical_data.sh "${@:2}"
}

run_smoke() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  export TTT_WEBAPP_FAKE_LLM=1
  env PYTHONPATH="$(python_env)" "$VENV_PY" src/ttt_workbench/scripts/stress_test_workbench.py "${@:2}"
  exec env PYTHONPATH="$(python_env)" "$VENV_PY" src/ttt_workbench/scripts/ui_integration_test.py
}

run_test() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  export TTT_WEBAPP_FAKE_LLM=1
  exec env PYTHONPATH="$(python_env)" "$VENV_PY" -m pytest tests/ -v "${@:2}"
}

run_epub() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  _kill_by_pidfile "$EPUB_PID_FILE" "epub generator"
  _write_pidfile "$EPUB_PID_FILE"
  exec env PYTHONPATH="$(python_env)" "$VENV_PY" src/ttt_epub/generate_epub.py "${@:2}"
}

COMMAND="${1:-web}"

case "$COMMAND" in
  web)
    run_web "$@"
    ;;
  web-fake)
    export TTT_WEBAPP_FAKE_LLM=1
    run_web "$@"
    ;;
  prep-data)
    run_prep_data "$@"
    ;;
  smoke)
    run_smoke "$@"
    ;;
  test)
    run_test "$@"
    ;;
  epub)
    run_epub "$@"
    ;;
  help|-h|--help)
    show_help
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    echo >&2
    show_help >&2
    exit 1
    ;;
esac
