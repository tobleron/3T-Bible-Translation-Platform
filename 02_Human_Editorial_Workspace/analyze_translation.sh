#!/bin/bash
# Wrapper to run the Human Editorial Review & Analysis Tools

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"

echo "🧐 Running Analysis Tool for Human Editorial Review..."

export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/02_Human_Editorial_Workspace${PYTHONPATH:+:$PYTHONPATH}"
"$VENV_PY" bible_translation_tool.py "$@"
