"""Token budgeting for chat context assembly.

Provides a priority-based context packer that trims older messages
to stay within a model's context window, preserving the most recent
and most important context.
"""

from __future__ import annotations

import math
import re

CHARS_PER_TOKEN = 4

DEFAULT_CONTEXT_WINDOW = 32768
DEFAULT_OUTPUT_TOKENS = 4096
DEFAULT_BUDGET_RATIO = 0.7

__all__ = [
    "CHARS_PER_TOKEN",
    "DEFAULT_CONTEXT_WINDOW",
    "DEFAULT_OUTPUT_TOKENS",
    "DEFAULT_BUDGET_RATIO",
    "estimate_tokens",
    "pack_messages",
    "trim_context_to_budget",
]


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def pack_messages(
    prior_messages: list[dict[str, str]],
    current_message: dict[str, str],
    *,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
    output_tokens: int = DEFAULT_OUTPUT_TOKENS,
    budget_ratio: float = DEFAULT_BUDGET_RATIO,
    system_overhead: int = 0,
) -> list[dict[str, str]]:
    """Pack messages into a token budget.

    Returns a list of messages that fits within the allocated token budget,
    preserving the current message and as many recent prior messages as
    possible.

    The input token budget is calculated as::

        budget = int((context_window - output_tokens) * budget_ratio) - system_overhead

    Prior messages are included from newest to oldest until the budget is
    exhausted.  The current message is always included (it is the user's
    latest input and must go to the model).

    Args:
        prior_messages:  Historical chat messages (oldest first).
        current_message: The current user message to send.
        context_window:  Total context window size in tokens for the model.
        output_tokens:   Tokens reserved for the model's response.
        budget_ratio:     Fraction of input tokens to use (0.0-1.0).
        system_overhead:  Extra tokens consumed by system prompts, context
                          injection, etc.

    Returns:
        List of messages ready for the LLM, in conversation order.
    """
    input_budget = max(
        256,
        int((context_window - output_tokens) * budget_ratio) - system_overhead,
    )

    current_tokens = estimate_tokens(current_message.get("content", ""))
    remaining_budget = input_budget - current_tokens
    if remaining_budget < 0:
        remaining_budget = 0

    selected: list[dict[str, str]] = []
    for msg in reversed(prior_messages):
        msg_tokens = estimate_tokens(msg.get("content", ""))
        if msg_tokens <= remaining_budget:
            selected.append(msg)
            remaining_budget -= msg_tokens
        else:
            break

    selected.reverse()
    selected.append(current_message)
    return selected


def trim_context_to_budget(
    text: str,
    *,
    max_tokens: int = DEFAULT_CONTEXT_WINDOW - DEFAULT_OUTPUT_TOKENS,
) -> str:
    """Trim a text block to fit within a token budget.

    Keeps the beginning of the text (which typically contains the most
    important context/labels) and truncates at the last complete line
    that fits.

    Args:
        text:      The text to potentially trim.
        max_tokens: Maximum tokens allowed.

    Returns:
        The text, possibly truncated, fitting within the budget.
    """
    estimated = estimate_tokens(text)
    if estimated <= max_tokens:
        return text

    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars // 2:
        truncated = truncated[:last_newline]

    return truncated.rstrip() + "\n[...truncated to fit context window...]"