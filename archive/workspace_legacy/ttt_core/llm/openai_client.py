"""OpenAI API client."""

from __future__ import annotations

import os
from typing import Generator

from openai import OpenAI


class OpenAIClient:
    """Handles all communication with the OpenAI API."""

    def __init__(self, config: dict) -> None:
        api_key = os.environ.get("OPENAI_API_KEY") or config.get("openai", {}).get(
            "api_key"
        )
        if not api_key or "PASTE_YOUR" in api_key:
            raise ValueError(
                "OpenAI API key not found. Please set the OPENAI_API_KEY env var "
                "or add it to config.yaml."
            )
        self.client = OpenAI(api_key=api_key)
        openai_config = config.get("openai", {})
        self.available_models = openai_config.get(
            "available_models", ["gpt-4o", "gpt-3.5-turbo"]
        )
        self.no_temp_models = openai_config.get("models_without_temperature", [])

    def list_models(self) -> list[str]:
        return self.available_models

    def generate_response(
        self, model_name: str, prompt_or_messages: str | list[dict], temperature: float
    ) -> str:
        if not isinstance(prompt_or_messages, list):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = prompt_or_messages

        completion_kwargs: dict = {
            "model": model_name,
            "messages": messages,
        }
        if model_name not in self.no_temp_models:
            completion_kwargs["temperature"] = temperature

        try:
            response = self.client.chat.completions.create(**completion_kwargs)
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            return ""
        except Exception as exc:
            return f"\n[ERROR] OpenAI generation failed: {exc}"

    def stream_generation(
        self, model_name: str, prompt_or_messages: str | list[dict], temperature: float
    ) -> Generator[str, None, None]:
        if not isinstance(prompt_or_messages, list):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = prompt_or_messages

        completion_kwargs: dict = {
            "model": model_name,
            "messages": messages,
        }
        if model_name not in self.no_temp_models:
            completion_kwargs["temperature"] = temperature

        try:
            completion_kwargs["stream"] = True
            stream = self.client.chat.completions.create(**completion_kwargs)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            yield f"\n[ERROR] OpenAI generation failed: {exc}"
