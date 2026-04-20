from pathlib import Path
import logging
import yaml

logger = logging.getLogger(__name__)


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
        except (yaml.YAMLError, OSError) as e:
            logger.warning("Failed to parse %s: %s", main_cfg, e)

    # 2. Dedicated epub config
    cfg_file = root / "config" / "epub_config.yaml"
    if cfg_file.exists():
        try:
            return yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError) as e:
            logger.warning("Failed to parse %s: %s", cfg_file, e)

    # 3. Default config directory
    default_cfg = root / "config" / "default_config.yaml"
    if default_cfg.exists():
        try:
            full_cfg = yaml.safe_load(default_cfg.read_text(encoding="utf-8")) or {}
            if "epub" in full_cfg:
                return full_cfg["epub"]
        except (yaml.YAMLError, OSError) as e:
            logger.warning("Failed to parse %s: %s", default_cfg, e)

    raise SystemExit(f"✗ Could not find EPUB configuration in {main_cfg} or {cfg_file}")
