from pathlib import Path
import yaml

def load_config(root: Path) -> dict:
    """
    Read ``config/epub_config.yaml`` and return the parsed config.
    """
    cfg_file = root / "config" / "epub_config.yaml"
    try:
        return yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"✗ Missing {cfg_file.relative_to(root)}")
