"""Unified configuration loader.

Reads ``config.yaml`` from the project root and overlays environment
variables prefixed with ``TTT_``.  Falls back to legacy config locations
during the transition period.
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
    2. ``config.yaml`` at *project_root*
    3. Legacy ``config.yaml`` in ``02_Human_Editorial_Workspace/``
    4. Sensible defaults
    """
    if project_root is None:
        project_root = _detect_project_root()

    cfg = _defaults()

    # 3. Legacy workbench config (fallback)
    legacy_cfg = _load_yaml(project_root / "02_Human_Editorial_Workspace" / "config.yaml")
    cfg = _deep_merge(cfg, legacy_cfg)

    # 2. Root config.yaml (overrides legacy)
    root_cfg = _load_yaml(project_root / "config.yaml")
    cfg = _deep_merge(cfg, root_cfg)

    # 1. Environment variables (highest priority)
    cfg = _apply_env_overrides(cfg)

    return cfg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_project_root() -> Path:
    """Heuristic: look for PROJECT_GUIDE.md or 01_AI_Translation_Engine."""
    here = Path.cwd()
    for parent in [here, *here.parents]:
        if (parent / "PROJECT_GUIDE.md").exists():
            return parent
        if (parent / "01_AI_Translation_Engine").is_dir():
            return parent
    return here


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _defaults() -> dict[str, Any]:
    return {
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
