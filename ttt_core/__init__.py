"""ttt_core – Shared library for the TTT Bible Translation Project.

Provides unified access to:
- LLM clients (llama.cpp, OpenAI)
- Data repositories (Bible JSON, justifications, sources, lexical data)
- Domain models (SessionState, ChunkSuggestion, JustificationDraft, etc.)
- Utilities (book codes, parsing, backup, validation)
- Configuration (root config.yaml + env var overrides)
"""

from .config import load_config
from .llm import LlamaCppClient, OpenAIClient
from .models import SessionState, ChunkSuggestion, JustificationDraft
from .utils import book_ref_code, parse_range, parse_reference, normalize_book_key

__all__ = [
    "load_config",
    "LlamaCppClient",
    "OpenAIClient",
    "SessionState",
    "ChunkSuggestion",
    "JustificationDraft",
    "book_ref_code",
    "parse_range",
    "parse_reference",
    "normalize_book_key",
]
