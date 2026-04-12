"""Unified llama.cpp client supporting both streaming and non-streaming modes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Generator

import requests

from ttt_core.config import load_config
from ttt_core.utils.common import extract_json_payload


class LlamaCppClient:
    """Handles communication with the local llama.cpp server.

    Supports both:
    - ``complete()``: blocking call returning the full response
    - ``stream_generation()``: generator yielding tokens as they arrive
    - ``complete_json()``: blocking call with automatic JSON repair attempts
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        if base_url is None or api_key is None:
            cfg = load_config()
            llm_cfg = cfg.get("llama_cpp", {})
            if base_url is None:
                base_url = llm_cfg.get("base_url", "http://192.168.1.186:8081/v1")
            if api_key is None:
                api_key = llm_cfg.get("api_key")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ------------------------------------------------------------------
    # Model discovery
    # ------------------------------------------------------------------
    def list_models(self) -> list[str]:
        # If base_url already contains /v1, don't add it again
        if "/v1" in self.base_url:
            url = f"{self.base_url}/models"
        else:
            url = f"{self.base_url}/v1/models"
            
        try:
            request = urllib.request.Request(url, headers=self._get_headers())
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return [
                    item.get("id", "llama.cpp-model")
                    for item in payload.get("data", [])
                ] or ["llama.cpp-model"]
        except Exception:
            return ["llama.cpp-model"]

    # ------------------------------------------------------------------
    # Non-streaming completion
    # ------------------------------------------------------------------
    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.35,
        max_tokens: int = 2048,
        stop: list[str] | None = None,
        timeout_seconds: int = 300,
    ) -> str:
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "num_ctx": 4096,
            "stream": False,
        }
        if stop:
            payload["stop"] = stop
        data = json.dumps(payload).encode("utf-8")

        # Determine endpoint. llama.cpp legacy /completion vs /v1/completions
        if "/v1" in self.base_url:
            url = f"{self.base_url}/completions"
        else:
            url = f"{self.base_url}/completion"

        request = urllib.request.Request(
            url,
            data=data,
            headers=self._get_headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return self._extract_content(payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            # /v1/completions may not exist — fall back to chat endpoint
            if exc.code == 404 and "/v1" in self.base_url:
                return self._complete_via_chat(prompt, temperature, max_tokens, stop, timeout_seconds)
            return f"[ERROR] llama.cpp HTTP {exc.code}: {detail}"
        except TimeoutError:
            return f"[ERROR] llama.cpp request timed out after {timeout_seconds}s"
        except Exception as exc:
            return f"[ERROR] llama.cpp request failed: {exc}"

    def _complete_via_chat(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        stop: list[str] | None,
        timeout_seconds: int,
    ) -> str:
        """Fallback: use /v1/chat/completions when /v1/completions is unavailable."""
        chat_payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if stop:
            chat_payload["stop"] = stop
        data = json.dumps(chat_payload).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        request = urllib.request.Request(
            url,
            data=data,
            headers=self._get_headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return self._extract_content(payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return f"[ERROR] llama.cpp HTTP {exc.code}: {detail}"
        except TimeoutError:
            return f"[ERROR] llama.cpp request timed out after {timeout_seconds}s"
        except Exception as exc:
            return f"[ERROR] llama.cpp request failed: {exc}"

    # ------------------------------------------------------------------
    # Streaming completion
    # ------------------------------------------------------------------
    def stream_generation(
        self,
        model_name: str,
        prompt_or_messages: str | list[dict[str, str]],
        temperature: float,
    ) -> Generator[str, None, None]:
        """Connects to llama.cpp's /completion endpoint with streaming.

        Yields tokens as they arrive.  If a ``stop`` event is detected,
        yields a ``__STATS_BLOCK__…__END_STATS__`` marker.
        """
        if isinstance(prompt_or_messages, list):
            prompt_text = ""
            for msg in prompt_or_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_text += f"\n\n{role.upper()}: {content}"
            prompt_text += "\n\nASSISTANT:"
        else:
            prompt_text = prompt_or_messages

        payload = {
            "prompt": prompt_text,
            "temperature": temperature,
            "num_ctx": 4096,
            "stream": True,
            "n_predict": 4096,
        }

        try:
            if "/v1" in self.base_url:
                url = f"{self.base_url}/completions"
            else:
                url = f"{self.base_url}/completion"
                
            with requests.post(url, json=payload, headers=self._get_headers(), stream=True, timeout=300) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        data = json.loads(line_str[6:])
                        if "content" in data:
                            yield data["content"]
                        if data.get("stop"):
                            stats = {
                                "tokens_predicted": data.get("tokens_predicted"),
                                "generation_settings": data.get("generation_settings"),
                            }
                            yield f"__STATS_BLOCK__{json.dumps(stats)}__END_STATS__"
        except Exception as exc:
            yield f"\n[ERROR] llama.cpp generation failed: {exc}"

    # ------------------------------------------------------------------
    # JSON-mode completion with repair
    # ------------------------------------------------------------------
    def complete_json(
        self,
        prompt: str,
        *,
        required_keys: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        max_attempts: int = 3,
        timeout_seconds: int = 300,
    ) -> tuple[dict | list | None, str, int]:
        """Return ``(parsed_json, raw_response, attempts_used)``.

        Retries up to *max_attempts* times if the response is not valid JSON
        or misses required keys.
        """
        last_response = ""
        repair_reason = ""
        base_prompt = (
            "/no_think\n"
            "Model profile: qwen3.5 35B A3B thinking model.\n"
            "Return valid JSON only.\n"
            "The first non-whitespace character of your response must be { or [.\n"
            "Do not include markdown fences, commentary, XML tags, <think> blocks, or visible reasoning.\n\n"
        ) + prompt
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
            lowered = last_response.lower()
            leaked_reasoning = "<think>" in lowered or "thinking process" in lowered
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
                        repair_reason = (
                            "Visible reasoning leaked and the JSON schema was incomplete"
                        )
                        continue
                    repair_reason = "Missing required keys: " + ", ".join(missing)
                    continue
            return payload, last_response, attempt
        return None, last_response, max_attempts

    # ------------------------------------------------------------------
    # Compatibility: generate_response (matches OllamaClient / OpenAIClient API)
    # ------------------------------------------------------------------
    def generate_response(
        self, model_name: str, prompt_or_messages: str | list[dict], temperature: float
    ) -> str:
        """Compatibility wrapper for tools that expect the legacy API."""
        if isinstance(prompt_or_messages, list):
            prompt = "\n\n".join(
                f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                for msg in prompt_or_messages
            )
        else:
            prompt = prompt_or_messages
        return self.complete(prompt, temperature=temperature)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_content(payload: object) -> str:
        """Extract text content from various llama.cpp response shapes."""
        if isinstance(payload, dict):
            if "content" in payload:
                return payload["content"]
            if "choices" in payload and payload["choices"]:
                choice = payload["choices"][0]
                if isinstance(choice, dict):
                    if "text" in choice:
                        return choice["text"]
                    if "message" in choice and isinstance(choice["message"], dict):
                        return choice["message"].get("content", "")
        return str(payload)
