#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
WORKBENCH_REQUIREMENTS="$ROOT_DIR/02_Human_Editorial_Workspace/requirements-workbench.txt"
WORKBENCH_HASH_FILE="$VENV_DIR/.workbench_requirements.sha256"

show_help() {
  cat <<'EOF'
TTT root launcher

Usage:
  ./ttt.sh                Launch the browser workbench
  ./ttt.sh web            Launch the browser workbench
  ./ttt.sh web-fake       Launch the browser workbench with fake LLM responses
  ./ttt.sh textual        Launch the Textual workbench
  ./ttt.sh workbench      Launch the legacy terminal workbench
  ./ttt.sh textual-preview  Launch the Textual UI prototype
  ./ttt.sh prep-data      Download/build offline lexical data
  ./ttt.sh smoke          Run the scripted workbench smoke test
  ./ttt.sh test           Run the ttt_core unit tests
  ./ttt.sh translate      Run the legacy AI translation wrapper
  ./ttt.sh analyze        Run the legacy editorial analysis wrapper
  ./ttt.sh epub           Run the legacy EPUB builder wrapper
  ./ttt.sh backup         Create a versioned project backup
  ./ttt.sh help           Show this help

Notes:
  - The default command is `web`.
  - Use `./ttt.sh workbench` for the legacy line-based shell.
  - Inside the workbench, use `/epub-gen` to build EPUB output from committed JSON.
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

run_web() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  local host="${TTT_WEB_HOST:-127.0.0.1}"
  local port="${TTT_WEB_PORT:-8765}"
  echo "TTT Browser Workbench: http://$host:$port"
  exec env PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace" "$VENV_PY" -m uvicorn ttt_webapp.app:app --host "$host" --port "$port"
}

run_workbench() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  env PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace" "$VENV_PY" 02_Human_Editorial_Workspace/ttt_workbench.py
}

run_textual_preview() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  env PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace" "$VENV_PY" 02_Human_Editorial_Workspace/textual_workbench_preview.py
}

run_textual() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  env PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace" "$VENV_PY" 02_Human_Editorial_Workspace/textual_workbench.py
}

run_prep_data() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace${PYTHONPATH:+:$PYTHONPATH}"
  chmod +x 02_Human_Editorial_Workspace/scripts/prepare_lexical_data.sh
  exec 02_Human_Editorial_Workspace/scripts/prepare_lexical_data.sh "${@:2}"
}

run_smoke() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  env PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace" "$VENV_PY" 02_Human_Editorial_Workspace/scripts/stress_test_workbench.py "${@:2}"
  exec env PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace" "$VENV_PY" 02_Human_Editorial_Workspace/scripts/ui_integration_test.py
}

run_test() {
  cd "$ROOT_DIR"
  ensure_workbench_env
  exec env PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace" "$VENV_PY" -m pytest tests/ -v "${@:2}"
}

run_translate() {
  cd "$ROOT_DIR/01_AI_Translation_Engine"
  export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
  exec ./translate_verse.sh "${@:2}"
}

run_analyze() {
  cd "$ROOT_DIR/02_Human_Editorial_Workspace"
  export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace${PYTHONPATH:+:$PYTHONPATH}"
  exec ./analyze_translation.sh "${@:2}"
}

run_epub() {
  cd "$ROOT_DIR/03_EPUB_Production"
  exec ./make_epub.sh "${@:2}"
}

run_backup() {
  cd "$ROOT_DIR"
  exec env PYTHONPATH="$ROOT_DIR" "$VENV_PY" version_control.py "${@:2}"
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
  workbench)
    run_workbench "$@"
    ;;
  textual-preview)
    run_textual_preview "$@"
    ;;
  textual)
    run_textual "$@"
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
  translate)
    run_translate "$@"
    ;;
  analyze)
    run_analyze "$@"
    ;;
  epub)
    run_epub "$@"
    ;;
  backup)
    run_backup "$@"
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
