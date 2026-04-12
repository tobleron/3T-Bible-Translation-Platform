"""Unified configuration loader.

Reads the legacy root ``config.yaml`` when present, then overlays
``config/default_config.yaml`` and finally environment variables
prefixed with ``TTT_``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(project_root: Path | None = None) -> dict[str, Any]:
    """Return a merged configuration dictionary.

    Priority (highest first):
    1. ``TTT_`` environment variables
    2. ``config/default_config.yaml`` at *project_root*
    3. legacy ``config.yaml`` at *project_root*
    4. Sensible defaults
    """
    if project_root is None:
        project_root = _detect_project_root()

    _load_dotenv(project_root / ".env")
    cfg = _defaults(project_root)

    legacy_cfg = _load_yaml(project_root / "config.yaml")
    cfg = _deep_merge(cfg, legacy_cfg)

    config_dir_cfg = _load_yaml(project_root / "config" / "default_config.yaml")
    cfg = _deep_merge(cfg, config_dir_cfg)

    # 1. Environment variables (highest priority)
    cfg = _apply_env_overrides(cfg)

    return cfg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_project_root() -> Path:
    """Heuristic: look for pyproject.toml or src/."""
    here = Path.cwd()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / "src").is_dir():
            return parent
    return here


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _defaults(root: Path) -> dict[str, Any]:
    return {
        "paths": {
            "root": str(root),
            "data": str(root / "data"),
            "raw_data": str(root / "data" / "raw"),
            "final_data": str(root / "data" / "final"),
            "processed_bibles": str(root / "data" / "processed"),
            "bible_dir": str(root / "data" / "final" / "_HOLY_BIBLE"),
            "justifications_dir": str(root / "data" / "final" / "_HOLY_BIBLE_JUSTIFICATIONS"),
            "lexical_db": str(root / "data" / "raw" / "lexical_index" / "lexical.db"),
            "output": str(root / "output"),
            "ai_sessions": str(root / "output" / "ai_sessions"),
            "reports": str(root / "output" / "reports"),
            "resources": str(root / "resources"),
            "prompts": str(root / "resources" / "prompts"),
            "rules": str(root / "resources" / "rules"),
            "assets": str(root / "resources" / "assets"),
        },
        "llama_cpp": {
            "base_url": "http://192.168.1.186:8080",
            "api_key": os.environ.get("TTT_LLAMA_CPP_API_KEY", ""),
        },
        "openai": {
            "api_key": os.environ.get("OPENAI_API_KEY", ""),
            "available_models": ["gpt-4o", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"],
            "models_without_temperature": ["o4-mini"],
        },
        "workbench": {
            "sessions_directory": "sessions",
            "static_prompts_directory": "static_prompts",
            "saved_responses_directory": "saved_responses",
            "cleanup_temp_files": True,
            "user_color": "yellow",
            "ai_panel_color": "bright_green",
            "success_color": "green",
            "error_color": "red",
            "info_color": "yellow",
            "rule_color": "grey50",
        },
        "epub": {
            "meta": {
                "epub_title": "The Holy Bible",
                "version_number": "0.5",
                "publication_date": "May 2025",
                "bible_edition": "TTT",
            },
            "formatting": {
                "verse_font_size": "1em",
                "line_spacing": "1.5",
                "epub_title_font_size": "2em",
                "book_title_font_size": "1.6em",
                "chapter_title_font_size": "1.3em",
                "superscript_font_size": "0.7em",
            },
        },
    }


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    """Overlay ``TTT_XXX`` env vars onto the config."""
    if os.environ.get("TTT_LLAMA_CPP_BASE_URL"):
        cfg.setdefault("llama_cpp", {})["base_url"] = os.environ["TTT_LLAMA_CPP_BASE_URL"]
    if os.environ.get("TTT_LLAMA_CPP_API_KEY"):
        cfg.setdefault("llama_cpp", {})["api_key"] = os.environ["TTT_LLAMA_CPP_API_KEY"]
    if os.environ.get("TTT_OPENAI_API_KEY"):
        cfg.setdefault("openai", {})["api_key"] = os.environ["TTT_OPENAI_API_KEY"]
    return cfg

def _load_dotenv(path: Path) -> None:
    """Very simple .env loader if python-dotenv is not installed."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                # setdefault ensures that explicitly set ENV vars override .env
                os.environ.setdefault(key.strip(), val.strip())
