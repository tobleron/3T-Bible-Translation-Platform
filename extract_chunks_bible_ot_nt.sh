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
echo "Endpoint: http://192.168.1.186:8081/v1"
echo

exec "$VENV_PY" "$SCRIPT" \
  --testament all \
  --output-dir "$OUTPUT_DIR" \
  --base-url "http://192.168.1.186:8081/v1" \
  "$@"
