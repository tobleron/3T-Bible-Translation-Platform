"""Tests for ttt_core configuration loader."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ttt_core.config import (
    load_config,
    _deep_merge,
    _defaults,
    DEFAULT_LLAMA_CPP_BASE_URL,
)


class TestLoadConfig:
    def test_load_config_returns_dict(self):
        cfg = load_config()
        assert isinstance(cfg, dict)

    def test_defaults_include_required_keys(self):
        cfg = load_config()
        assert "paths" in cfg
        assert "llama_cpp" in cfg
        assert "openai" in cfg
        assert "workbench" in cfg

    def test_llama_cpp_has_default_url(self):
        cfg = load_config()
        assert cfg["llama_cpp"]["base_url"] == DEFAULT_LLAMA_CPP_BASE_URL


class TestDeepMerge:
    def test_merge_simple(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested(self):
        base = {"llama_cpp": {"base_url": "http://old"}}
        override = {"llama_cpp": {"api_key": "key123"}}
        result = _deep_merge(base, override)
        assert result["llama_cpp"]["base_url"] == "http://old"
        assert result["llama_cpp"]["api_key"] == "key123"

    def test_override_replaces_non_dict(self):
        base = {"key": {"nested": "value"}}
        override = {"key": "replacement"}
        result = _deep_merge(base, override)
        assert result["key"] == "replacement"


class TestDefaults:
    def test_defaults_has_required_paths(self):
        root = Path("/tmp/test")
        defaults = _defaults(root)
        assert "paths" in defaults
        assert "root" in defaults["paths"]
        assert defaults["paths"]["root"] == str(root)

    def test_defaults_llama_cpp_settings(self):
        defaults = _defaults(Path("/tmp"))
        assert "base_url" in defaults["llama_cpp"]
        assert "api_key" in defaults["llama_cpp"]
        assert "stream_timeout_seconds" in defaults["llama_cpp"]
