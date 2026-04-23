"""LLM client interfaces for llama.cpp and OpenAI."""

from ttt_core.llm.llama_cpp import LlamaCppClient
from ttt_core.llm.openai_client import OpenAIClient
from ttt_core.llm.provider import (
    LLMProvider,
    LlamaCppProvider,
    ModelProfile,
    OpenAICompatProvider,
    OpenAIProvider,
    PROFILES,
    resolve_provider,
)

__all__ = [
    "LlamaCppClient",
    "OpenAIClient",
    "LLMProvider",
    "LlamaCppProvider",
    "OpenAICompatProvider",
    "OpenAIProvider",
    "ModelProfile",
    "PROFILES",
    "resolve_provider",
]
