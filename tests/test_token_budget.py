"""Tests for the token budgeting module."""

import pytest

from ttt_core.llm.token_budget import (
    CHARS_PER_TOKEN,
    DEFAULT_BUDGET_RATIO,
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_OUTPUT_TOKENS,
    estimate_tokens,
    pack_messages,
    trim_context_to_budget,
)


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 1

    def test_short_string(self):
        result = estimate_tokens("hello")
        assert result >= 1
        assert result <= 5

    def test_long_text(self):
        text = "word " * 400
        result = estimate_tokens(text)
        assert result == pytest.approx(len(text) / CHARS_PER_TOKEN, abs=5)

    def test_consistency(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert estimate_tokens(text) == estimate_tokens(text)


class TestPackMessages:
    def test_basic_packing(self):
        priors = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "How are you?"},
        ]
        current = {"role": "user", "content": "Great!"}
        result = pack_messages(priors, current)
        assert result[-1] == current
        assert len(result) == 4

    def test_budget_limits_messages(self):
        long_content = "x" * 50000
        priors = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": long_content},
        ]
        current = {"role": "user", "content": "Short"}
        result = pack_messages(priors, current, context_window=1000, output_tokens=200)
        assert result[-1] == current
        total_tokens = sum(estimate_tokens(m["content"]) for m in result)
        budget = int((1000 - 200) * DEFAULT_BUDGET_RATIO)
        assert total_tokens <= budget + 200

    def test_current_message_always_included(self):
        priors = []
        current = {"role": "user", "content": "Just me"}
        result = pack_messages(priors, current)
        assert result == [current]

    def test_empty_priors(self):
        priors = []
        current = {"role": "user", "content": "Hello world"}
        result = pack_messages(priors, current)
        assert len(result) == 1
        assert result[0] == current

    def test_preserves_conversation_order(self):
        priors = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        current = {"role": "user", "content": "Fourth"}
        result = pack_messages(priors, current)
        assert result[0]["content"] == "First"
        assert result[1]["content"] == "Second"
        assert result[2]["content"] == "Third"
        assert result[3] == current

    def test_newer_messages_preferred(self):
        short = "Short message"
        long = "Long message " * 5000
        priors = [
            {"role": "user", "content": long},
            {"role": "assistant", "content": long},
            {"role": "user", "content": short},
        ]
        current = {"role": "user", "content": "Current"}
        result = pack_messages(priors, current, context_window=500, output_tokens=100)
        assert result[-1] == current
        assert any(m["content"] == short for m in result)

    def test_system_overhead(self):
        priors = [
            {"role": "user", "content": "Hello"},
        ]
        current = {"role": "user", "content": "World"}
        result_no_overhead = pack_messages(priors, current, system_overhead=0)
        result_with_overhead = pack_messages(priors, current, system_overhead=10000)
        assert len(result_with_overhead) <= len(result_no_overhead)

    def test_small_budget_still_includes_current(self):
        priors = [
            {"role": "user", "content": "A very long message " * 10000},
        ]
        current = {"role": "user", "content": "Current"}
        result = pack_messages(priors, current, context_window=256, output_tokens=64)
        assert result[-1] == current

    def test_custom_budget_ratio(self):
        priors = [
            {"role": "user", "content": "Hello"},
        ]
        current = {"role": "user", "content": "World"}
        result_low = pack_messages(priors, current, budget_ratio=0.3)
        result_high = pack_messages(priors, current, budget_ratio=0.9)
        assert len(result_low) <= len(result_high)


class TestTrimContextToBudget:
    def test_short_text_unchanged(self):
        text = "Hello world"
        assert trim_context_to_budget(text, max_tokens=100) == text

    def test_long_text_truncated(self):
        text = "Line one\nLine two\nLine three\n" * 100
        result = trim_context_to_budget(text, max_tokens=50)
        assert len(result) < len(text)
        assert "[...truncated" in result

    def test_truncation_preserves_line_boundary(self):
        text = "Short line\n" + "Very long line with lots of content " * 200 + "\n"
        result = trim_context_to_budget(text, max_tokens=30)
        assert result.endswith("[...truncated to fit context window...]")

    def test_exact_budget_no_truncation(self):
        text = "a" * 40
        result = trim_context_to_budget(text, max_tokens=estimate_tokens(text) + 1)
        assert result == text

    def test_custom_max_tokens(self):
        text = "a" * 4000
        result_default = trim_context_to_budget(text)
        result_large = trim_context_to_budget(text, max_tokens=50000)
        assert len(result_large) >= len(result_default)