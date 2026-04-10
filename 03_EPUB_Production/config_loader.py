from pathlib import Path
import yaml

def load_config(root: Path) -> dict:
    """
    Read *epub_config.yaml* at the project root and return the dict.
    """
    cfg_file = root / "epub_config.yaml"
    try:
        return yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit("✗ Missing epub_config.yaml")
