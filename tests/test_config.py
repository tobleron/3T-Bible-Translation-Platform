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
    DEFAULT_LLAMA_CPP_STREAM_TIMEOUT_SECONDS,
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

    def test_config_precedence_env_over_default_and_legacy(self, tmp_path, monkeypatch):
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config.yaml").write_text(
            "llama_cpp:\n  base_url: http://legacy.local:8080/v1\n",
            encoding="utf-8",
        )
        (tmp_path / "config" / "default_config.yaml").write_text(
            "llama_cpp:\n  base_url: http://default.local:8080/v1\n",
            encoding="utf-8",
        )
        (tmp_path / ".env").write_text(
            "TTT_LLAMA_CPP_BASE_URL=http://dotenv.local:8080/v1\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TTT_LLAMA_CPP_BASE_URL", "http://env.local:8080/v1")
        cfg = load_config(tmp_path)
        assert cfg["llama_cpp"]["base_url"] == "http://env.local:8080/v1"

    def test_dotenv_applies_when_env_is_not_exported(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text(
            "TTT_LLAMA_CPP_BASE_URL=http://dotenv.local:8080/v1\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("TTT_LLAMA_CPP_BASE_URL", raising=False)
        cfg = load_config(tmp_path)
        assert cfg["llama_cpp"]["base_url"] == "http://dotenv.local:8080/v1"

    def test_invalid_stream_timeout_env_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TTT_LLAMA_CPP_STREAM_TIMEOUT", "not-a-number")
        cfg = load_config(tmp_path)
        assert cfg["llama_cpp"]["stream_timeout_seconds"] == DEFAULT_LLAMA_CPP_STREAM_TIMEOUT_SECONDS

    def test_stream_timeout_env_overrides_config(self, tmp_path, monkeypatch):
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "default_config.yaml").write_text(
            "llama_cpp:\n  stream_timeout_seconds: 999\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TTT_LLAMA_CPP_STREAM_TIMEOUT", "123")
        cfg = load_config(tmp_path)
        assert cfg["llama_cpp"]["stream_timeout_seconds"] == 123


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
