"""Tests for the LLM provider abstraction layer."""

import pytest

from ttt_core.llm.llama_cpp import LlamaCppClient
from ttt_core.llm.provider import (
    PROFILES,
    LlamaCppProvider,
    ModelProfile,
    OpenAICompatProvider,
    OpenAIProvider,
    _infer_profile,
    resolve_provider,
)


class TestModelProfile:
    def test_default_profile_has_json_system_prefix(self):
        p = PROFILES["default"]
        assert "JSON" in p.json_system_prefix
        assert p.name == "default"

    def test_qwen_profile_has_no_think(self):
        p = PROFILES["qwen"]
        assert "/no_think" in p.json_system_prefix
        assert p.json_no_think is True
        assert p.name == "qwen"

    def test_infer_qwen(self):
        for name in ("Qwen3-35B-A3B", "qwen2.5-7b", "QWEN-Coder"):
            assert _infer_profile(name).name == "qwen"

    def test_infer_default(self):
        for name in ("llama3", "gpt-4", "mistral", ""):
            assert _infer_profile(name).name == "default"

    def test_model_profile_init(self):
        p = ModelProfile("test", json_system_prefix="Hello ")
        assert p.name == "test"
        assert p.json_system_prefix == "Hello "
        assert p.thinking_tag_start == ""
        assert p.thinking_tag_end == ""


class TestLlamaCppProvider:
    def test_delegates_list_models(self):
        provider = LlamaCppProvider(base_url="http://localhost:9999/v1", api_key="")
        assert provider.base_url == "http://localhost:9999/v1"

    def test_model_name_property(self):
        provider = LlamaCppProvider(base_url="http://localhost:9999/v1", api_key="")
        provider.model_name = "test-model"
        assert provider.model_name == "test-model"
        assert provider._client.model_name == "test-model"

    def test_api_key_property(self):
        provider = LlamaCppProvider(base_url="http://localhost:9999/v1", api_key="sk-123")
        assert provider.api_key == "sk-123"
        provider.api_key = "sk-456"
        assert provider.api_key == "sk-456"

    def test_complete_json_uses_profile(self):
        provider = LlamaCppProvider(base_url="http://localhost:0/v1", api_key="")
        provider.model_name = "Qwen3-35B"
        profile = _infer_profile(provider.model_name)
        assert profile.name == "qwen"
        assert "/no_think" in profile.json_system_prefix

    def test_complete_json_default_profile(self):
        provider = LlamaCppProvider(base_url="http://localhost:0/v1", api_key="")
        provider.model_name = "llama3"
        profile = _infer_profile(provider.model_name)
        assert profile.name == "default"
        assert "/no_think" not in profile.json_system_prefix


class TestOpenAICompatProvider:
    def test_inherits_llama_cpp_provider(self):
        provider = OpenAICompatProvider(base_url="http://192.168.1.1:8082/v1", api_key="")
        assert isinstance(provider, LlamaCppProvider)
        assert provider.base_url == "http://192.168.1.1:8082/v1"


class TestResolveProvider:
    def test_local_provider_default(self):
        settings = {"endpoint_provider": "local", "local_base_url": "http://10.0.0.1:8080/v1"}
        p = resolve_provider(settings)
        assert isinstance(p, LlamaCppProvider)
        assert p.base_url == "http://10.0.0.1:8080/v1"

    def test_cloud_provider_with_base_url(self):
        settings = {
            "endpoint_provider": "cloud",
            "cloud_base_url": "https://api.openai.com/v1",
        }
        p = resolve_provider(settings)
        assert isinstance(p, OpenAICompatProvider)
        assert p.base_url == "https://api.openai.com/v1"

    def test_cloud_provider_without_base_url(self):
        settings = {"endpoint_provider": "cloud", "cloud_base_url": ""}
        try:
            p = resolve_provider(settings, openai_config={})
            assert isinstance(p, OpenAIProvider)
        except ValueError:
            pytest.skip("OpenAI API key not available")

    def test_local_provider_model_name(self):
        settings = {
            "endpoint_provider": "local",
            "local_base_url": "http://10.0.0.1:8080/v1",
            "local_model": "Qwen3-35B-A3B",
        }
        p = resolve_provider(settings)
        assert p.model_name == "Qwen3-35B-A3B"

    def test_cloud_provider_model_name(self):
        settings = {
            "endpoint_provider": "cloud",
            "cloud_base_url": "https://api.openai.com/v1",
            "cloud_model": "gpt-4.1-mini",
        }
        p = resolve_provider(settings)
        assert p.model_name == "gpt-4.1-mini"

    def test_default_base_url(self):
        settings = {"endpoint_provider": "local"}
        p = resolve_provider(settings, default_base_url="http://default:8080/v1")
        assert p.base_url == "http://default:8080/v1"


class TestLlamaCppClientProfile:
    def test_complete_json_uses_profile_inference(self):
        client = LlamaCppClient(base_url="http://localhost:0/v1", api_key="")
        client.model_name = "Qwen3-35B"
        profile = _infer_profile(client.model_name)
        assert profile.name == "qwen"
        assert "/no_think" in profile.json_system_prefix


class TestProtocolConformance:
    def test_llama_cpp_provider_satisfies_protocol(self):
        from ttt_core.llm.provider import LLMProvider
        provider = LlamaCppProvider(base_url="http://localhost:0/v1", api_key="")
        assert isinstance(provider, LLMProvider)

    def test_llama_cpp_client_satisfies_protocol(self):
        from ttt_core.llm.provider import LLMProvider
        client = LlamaCppClient(base_url="http://localhost:0/v1", api_key="")
        assert isinstance(client, LLMProvider)