from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "02_Human_Editorial_Workspace"

for candidate in (ROOT, WORKSPACE):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)
