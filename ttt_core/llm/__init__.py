"""LLM client interfaces for llama.cpp and OpenAI."""

from ttt_core.llm.llama_cpp import LlamaCppClient
from ttt_core.llm.openai_client import OpenAIClient

__all__ = ["LlamaCppClient", "OpenAIClient"]
