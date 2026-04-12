"""Backup and version control utilities."""

from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path

from ttt_core.utils.common import ensure_parent, utc_now


def write_backup_set(
    backups_dir: Path, writes: list[tuple[Path, str, str]]
) -> Path:
    """Write a backup set and apply new text to target paths atomically."""
    timestamp = utc_now().replace(":", "").replace("-", "")
    backup_dir = backups_dir / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for path, old_text, new_text in writes:
        relative = path.as_posix().lstrip("/")
        backup_path = backup_dir / relative
        ensure_parent(backup_path)
        if path.exists():
            backup_path.write_text(old_text, encoding="utf-8")
        else:
            backup_path.write_text("", encoding="utf-8")
        manifest.append(
            {
                "path": str(path),
                "backup": str(backup_path),
                "had_original": path.exists(),
            }
        )
        temp_path = path.with_suffix(path.suffix + ".tmp")
        ensure_parent(temp_path)
        temp_path.write_text(new_text, encoding="utf-8")
        temp_path.replace(path)
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return backup_dir


def restore_backup_set(backup_dir: Path) -> list[str]:
    """Restore files from a backup set manifest."""
    import json

    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[str] = []
    for item in manifest:
        path = Path(item["path"])
        backup = Path(item["backup"])
        if item.get("had_original"):
            ensure_parent(path)
            shutil.copyfile(backup, path)
        elif path.exists():
            path.unlink()
        restored.append(str(path))
    return restored


def create_project_backup(project_root: Path) -> Path:
    """Create a versioned backup of the entire project (used by version_control.py)."""
    prefix = project_root.name
    backup_root = project_root / "version_backup"
    if not backup_root.exists():
        backup_root.mkdir(parents=True)

    # Find max version number from existing backup folders
    max_version = 0
    pattern = re.compile(rf"^{re.escape(prefix)}_v(\d{{3}})_")
    for item in backup_root.iterdir():
        if item.is_dir():
            match = pattern.match(item.name)
            if match:
                version_num = int(match.group(1))
                if version_num > max_version:
                    max_version = version_num

    next_version = f"v{max_version + 1:03d}"
    timestamp = datetime.datetime.now().strftime("%d%m%Y_%H%M")
    backup_folder_name = f"{prefix}_{next_version}_{timestamp}"
    backup_path = backup_root / backup_folder_name
    backup_path.mkdir(parents=True)

    # Copy everything recursively except version_backup and backup script
    script_name = "version_control.py"
    for item in project_root.iterdir():
        if item.name == "version_backup" or item.name == script_name:
            continue
        dst_path = backup_path / item.name
        if item.is_dir():
            shutil.copytree(item, dst_path)
        else:
            shutil.copy2(item, dst_path)

    return backup_path
