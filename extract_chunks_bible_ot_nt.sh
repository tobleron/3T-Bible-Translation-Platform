#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"
SCRIPT="$ROOT_DIR/src/ttt_workbench/scripts/generate_chapter_chunks.py"
OUTPUT_DIR="$ROOT_DIR/output/ai_sessions/chapter_chunk_catalog"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Missing virtualenv python at $VENV_PY" >&2
  exit 1
fi

echo "Starting full Bible chunk extraction..."
echo "Script: $SCRIPT"
echo "Output: $OUTPUT_DIR"
BASE_URL="${TTT_LLAMA_CPP_BASE_URL:-http://10.0.0.1:8080/v1}"
echo "Endpoint: $BASE_URL"
echo

exec "$VENV_PY" "$SCRIPT" \
  --testament all \
  --output-dir "$OUTPUT_DIR" \
  --base-url "$BASE_URL" \
  "$@"
