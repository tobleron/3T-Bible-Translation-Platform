#!/usr/bin/env python3
"""Unified version control script using ttt_core."""

import sys
from pathlib import Path

# Add project root to path so ttt_core is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ttt_core.utils.backup import create_project_backup

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    backup_path = create_project_backup(project_root)
    print(f"✅ Backup created at: {backup_path}")
