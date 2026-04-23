"""LLM provider abstraction layer.

Defines the LLMProvider protocol and factory for resolving provider
instances from workbench settings.  Each provider implements model
listing, completion, JSON completion, streaming, and response
generation using the API shape appropriate for its backend.
"""

from __future__ import annotations

from typing import Generator, Protocol, runtime_checkable

from ttt_core.llm.llama_cpp import LlamaCppClient
from ttt_core.llm.openai_client import OpenAIClient

__all__ = [
    "LLMProvider",
    "LlamaCppProvider",
    "OpenAICompatProvider",
    "OpenAIProvider",
    "ModelProfile",
    "PROFILES",
    "resolve_provider",
]


# ------------------------------------------------------------------
# Model prompt profiles
# ------------------------------------------------------------------

class ModelProfile:
    """Prompt hints and context limits for a specific model family."""

    __slots__ = ("name", "json_system_prefix", "json_no_think", "thinking_tag_start", "thinking_tag_end", "context_window", "output_tokens")

    def __init__(
        self,
        name: str,
        *,
        json_system_prefix: str = "",
        json_no_think: bool = False,
        thinking_tag_start: str = "",
        thinking_tag_end: str = "",
        context_window: int = 32768,
        output_tokens: int = 4096,
    ) -> None:
        self.name = name
        self.json_system_prefix = json_system_prefix
        self.json_no_think = json_no_think
        self.thinking_tag_start = thinking_tag_start
        self.thinking_tag_end = thinking_tag_end
        self.context_window = context_window
        self.output_tokens = output_tokens


PROFILES: dict[str, ModelProfile] = {
    "qwen": ModelProfile(
        name="qwen",
        json_system_prefix=(
            "/no_think\n"
            "Return valid JSON only.\n"
            "The first non-whitespace character of your response must be { or [.\n"
            "Do not include markdown fences, commentary, XML tags, "
            "thinking blocks, or visible reasoning.\n\n"
        ),
        json_no_think=True,
        thinking_tag_start="",
        context_window=32768,
        output_tokens=4096,
    ),
    "default": ModelProfile(
        name="default",
        json_system_prefix=(
            "Return valid JSON only.\n"
            "The first non-whitespace character of your response must be { or [.\n"
            "Do not include markdown fences or commentary.\n\n"
        ),
        context_window=32768,
        output_tokens=4096,
    ),
}


def _infer_profile(model_name: str) -> ModelProfile:
    lowered = (model_name or "").lower()
    if "qwen" in lowered:
        return PROFILES["qwen"]
    return PROFILES["default"]


# ------------------------------------------------------------------
# LLMProvider protocol
# ------------------------------------------------------------------

@runtime_checkable
class LLMProvider(Protocol):
    """Interface all LLM backends must satisfy."""

    base_url: str
    model_name: str
    last_model_discovery_error: str

    def list_models(self) -> list[str]: ...
    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.35,
        max_tokens: int | None = 16384,
        stop: list[str] | None = None,
        timeout_seconds: int = 600,
    ) -> str: ...
    def complete_json(
        self,
        prompt: str,
        *,
        required_keys: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = 16384,
        max_attempts: int = 3,
        timeout_seconds: int = 600,
    ) -> tuple[dict | list | None, str, int]: ...
    def stream_generation(
        self,
        model_name: str,
        prompt_or_messages: str | list[dict[str, str]],
        temperature: float,
        max_tokens: int | None = 16384,
        stop_event: object | None = None,
    ) -> Generator[str, None, None]: ...
    def generate_response(
        self, model_name: str, prompt_or_messages: str | list[dict], temperature: float
    ) -> str: ...


# ------------------------------------------------------------------
# Concrete providers
# ------------------------------------------------------------------

class LlamaCppProvider:
    """Provider backed by a llama.cpp server (or any /v1/chat/completions endpoint).

    This wraps :class:`LlamaCppClient` and adds model-profile-aware
    JSON completion instead of hard-coding Qwen prompt hints.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self._client = LlamaCppClient(base_url=base_url, api_key=api_key)

    @property
    def base_url(self) -> str:
        return self._client.base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._client.base_url = value

    @property
    def model_name(self) -> str:
        return self._client.model_name

    @model_name.setter
    def model_name(self, value: str) -> None:
        self._client.model_name = value

    @property
    def api_key(self) -> str:
        return self._client.api_key

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._client.api_key = value

    @property
    def stream_timeout_seconds(self) -> int:
        return self._client.stream_timeout_seconds

    @stream_timeout_seconds.setter
    def stream_timeout_seconds(self, value: int) -> None:
        self._client.stream_timeout_seconds = value

    @property
    def last_model_discovery_error(self) -> str:
        return self._client.last_model_discovery_error

    @last_model_discovery_error.setter
    def last_model_discovery_error(self, value: str) -> None:
        self._client.last_model_discovery_error = value

    def list_models(self) -> list[str]:
        return self._client.list_models()

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.35,
        max_tokens: int | None = 16384,
        stop: list[str] | None = None,
        timeout_seconds: int = 600,
    ) -> str:
        return self._client.complete(prompt, temperature=temperature, max_tokens=max_tokens, stop=stop, timeout_seconds=timeout_seconds)

    def stream_generation(
        self,
        model_name: str,
        prompt_or_messages: str | list[dict[str, str]],
        temperature: float,
        max_tokens: int | None = 16384,
        stop_event: object | None = None,
    ) -> Generator[str, None, None]:
        return self._client.stream_generation(model_name, prompt_or_messages, temperature, max_tokens=max_tokens, stop_event=stop_event)

    def generate_response(
        self, model_name: str, prompt_or_messages: str | list[dict], temperature: float
    ) -> str:
        return self._client.generate_response(model_name, prompt_or_messages, temperature)

    def complete_json(
        self,
        prompt: str,
        *,
        required_keys: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = 16384,
        max_attempts: int = 3,
        timeout_seconds: int = 600,
    ) -> tuple[dict | list | None, str, int]:
        profile = _infer_profile(self.model_name)
        base_prompt = profile.json_system_prefix + prompt
        from ttt_core.utils.common import extract_json_payload

        last_response = ""
        repair_reason = ""
        for attempt in range(1, max_attempts + 1):
            if attempt == 1:
                current_prompt = base_prompt
            else:
                current_prompt = (
                    base_prompt
                    + "\n\nYour previous response was invalid."
                    + (f" Reason: {repair_reason}." if repair_reason else "")
                    + "\nReturn JSON only now."
                )
            last_response = self._client.complete(
                current_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
            payload = extract_json_payload(last_response)
            lowered = last_response.lower()
            leaked_reasoning = " misconception" in lowered or "thinking process" in lowered
            if payload is None:
                if leaked_reasoning:
                    repair_reason = "Visible reasoning was emitted instead of JSON"
                    continue
                repair_reason = "No parseable JSON object or array was found"
                continue
            if required_keys and isinstance(payload, dict):
                missing = [key for key in required_keys if key not in payload]
                if missing:
                    if leaked_reasoning:
                        repair_reason = "Visible reasoning leaked and the JSON schema was incomplete"
                        continue
                    repair_reason = "Missing required keys: " + ", ".join(missing)
                    continue
            return payload, last_response, attempt
        return None, last_response, max_attempts


class OpenAICompatProvider(LlamaCppProvider):
    """Provider for OpenAI-compatible endpoints (Open WebUI, LM Studio, etc).

    Identical to LlamaCppProvider in practice — the underlying
    LlamaCppClient already detects ``/v1`` in the base URL and uses
    OpenAI-compatible chat/completions endpoint paths.
    """

    pass


class OpenAIProvider:
    """Provider backed by the official OpenAI API using the ``openai`` Python SDK."""

    def __init__(self, config: dict) -> None:
        self._client = OpenAIClient(config)
        self.base_url: str = "https://api.openai.com/v1"
        self.model_name: str = ""
        self.last_model_discovery_error: str = ""

    def list_models(self) -> list[str]:
        return self._client.list_models()

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.35,
        max_tokens: int | None = 16384,
        stop: list[str] | None = None,
        timeout_seconds: int = 600,
    ) -> str:
        model = self.model_name or (self.list_models()[0] if self.list_models() else "gpt-4.1-mini")
        messages = [{"role": "user", "content": prompt}]
        return self._client.generate_response(model, messages, temperature)

    def stream_generation(
        self,
        model_name: str,
        prompt_or_messages: str | list[dict[str, str]],
        temperature: float,
        max_tokens: int | None = 16384,
        stop_event: object | None = None,
    ) -> Generator[str, None, None]:
        model = model_name or self.model_name
        return self._client.stream_generation(model, prompt_or_messages, temperature)

    def generate_response(
        self, model_name: str, prompt_or_messages: str | list[dict], temperature: float
    ) -> str:
        return self._client.generate_response(model_name, prompt_or_messages, temperature)

    def complete_json(
        self,
        prompt: str,
        *,
        required_keys: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = 16384,
        max_attempts: int = 3,
        timeout_seconds: int = 600,
    ) -> tuple[dict | list | None, str, int]:
        profile = _infer_profile(self.model_name)
        base_prompt = profile.json_system_prefix + prompt
        from ttt_core.utils.common import extract_json_payload

        last_response = ""
        repair_reason = ""
        for attempt in range(1, max_attempts + 1):
            if attempt == 1:
                current_prompt = base_prompt
            else:
                current_prompt = (
                    base_prompt
                    + "\n\nYour previous response was invalid."
                    + (f" Reason: {repair_reason}." if repair_reason else "")
                    + "\nReturn JSON only now."
                )
            last_response = self.complete(
                current_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
            payload = extract_json_payload(last_response)
            if payload is None:
                repair_reason = "No parseable JSON object or array was found"
                continue
            if required_keys and isinstance(payload, dict):
                missing = [key for key in required_keys if key not in payload]
                if missing:
                    repair_reason = "Missing required keys: " + ", ".join(missing)
                    continue
            return payload, last_response, attempt
        return None, last_response, max_attempts


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def resolve_provider(
    settings: dict,
    *,
    default_base_url: str | None = None,
    default_api_key: str | None = None,
    openai_config: dict | None = None,
) -> LlamaCppProvider | OpenAICompatProvider | OpenAIProvider:
    """Return the appropriate provider for *settings*.

    ``settings`` should be the workbench ``web_settings`` mapping.  The
    ``endpoint_provider`` key selects between ``"local"`` (llama.cpp /
    OpenAI-compat local) and ``"cloud"`` (official OpenAI API).
    """
    provider = str(settings.get("endpoint_provider", "local")).strip().lower()

    if provider == "cloud":
        cloud_url = str(settings.get("cloud_base_url", "")).strip()
        if cloud_url:
            cloud_url = cloud_url.rstrip("/")
        cloud_key = (
            __import__("os").environ.get("TTT_OPENAI_API_KEY")
            or __import__("os").environ.get("OPENAI_API_KEY", "")
        )
        if not cloud_url:
            cfg = openai_config or {}
            return OpenAIProvider(cfg)
        api_key = cloud_key or default_api_key or ""
        p = OpenAICompatProvider(base_url=cloud_url, api_key=api_key)
        model = str(settings.get("cloud_model", "")).strip()
        if model:
            p.model_name = model
        return p

    local_url = str(settings.get("local_base_url", default_base_url or "")).strip()
    if not local_url:
        local_url = default_base_url or "http://10.0.0.1:8080/v1"
    local_url = local_url.rstrip("/")
    local_key = default_api_key or __import__("os").environ.get("TTT_LLAMA_CPP_API_KEY", "")
    p = LlamaCppProvider(base_url=local_url, api_key=local_key)
    model = str(settings.get("local_model", "")).strip()
    if model:
        p.model_name = model
    return p