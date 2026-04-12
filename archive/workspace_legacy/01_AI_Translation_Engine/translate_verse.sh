#!/bin/bash
# Wrapper to run the AI Translation Engine (LLM Loops)
# Uses local llama.cpp endpoint by default

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"

echo "🚀 Starting AI Translation Engine..."
echo "Using llama.cpp at 192.168.1.186:8080"

export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
"$VENV_PY" TTT_Bible_crafter.py "$@"
