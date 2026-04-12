#!/bin/bash
# Wrapper to generate the final Bible EPUB

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"

echo "📚 Generating Bible EPUB from refined JSON files..."

"$VENV_PY" generate_epub.py --md --txt
echo "✅ EPUB generation complete. Check the current directory for .epub, .md and .txt output."
