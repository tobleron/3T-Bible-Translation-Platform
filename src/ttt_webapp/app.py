from __future__ import annotations

from importlib import import_module
import sys


sys.modules[__name__] = import_module("ttt_workbench.webapp")
