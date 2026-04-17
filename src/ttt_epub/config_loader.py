from pathlib import Path
import yaml

def load_config(root: Path) -> dict:
    """
    Read config from various potential locations, prioritizing the unified config.yaml.
    """
    # 1. Main project config
    main_cfg = root / "config.yaml"
    if main_cfg.exists():
        try:
            full_cfg = yaml.safe_load(main_cfg.read_text(encoding="utf-8")) or {}
            if "epub" in full_cfg:
                return full_cfg["epub"]
        except Exception:
            pass

    # 2. Dedicated epub config
    cfg_file = root / "config" / "epub_config.yaml"
    if cfg_file.exists():
        try:
            return yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
            
    # 3. Default config directory
    default_cfg = root / "config" / "default_config.yaml"
    if default_cfg.exists():
        try:
            full_cfg = yaml.safe_load(default_cfg.read_text(encoding="utf-8")) or {}
            if "epub" in full_cfg:
                return full_cfg["epub"]
        except Exception:
            pass

    raise SystemExit(f"✗ Could not find EPUB configuration in {main_cfg} or {cfg_file}")
