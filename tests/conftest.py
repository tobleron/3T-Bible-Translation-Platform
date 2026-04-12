from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FAKE_BROWSER_STATE = ROOT / ".ttt_workbench" / "browser_fake_mode"

os.environ.setdefault("TTT_WEBAPP_FAKE_LLM", "1")

for candidate in (SRC, ROOT):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)


@pytest.fixture(autouse=True)
def _reset_browser_fake_mode_state():
    shutil.rmtree(FAKE_BROWSER_STATE, ignore_errors=True)
    yield
    shutil.rmtree(FAKE_BROWSER_STATE, ignore_errors=True)
