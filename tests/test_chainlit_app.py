from __future__ import annotations

import asyncio
from types import SimpleNamespace
from pathlib import Path

from ttt_workbench import chainlit_app


ROOT = Path(__file__).resolve().parents[1]


def test_reply_display_parts_puts_answer_after_thinking() -> None:
    content = "<think>check source</think>```text\nVerse output.\n```"

    assert list(chainlit_app._reply_display_parts(content)) == [
        ("thinking", "check source", None),
        ("answer", "```text\nVerse output.\n```"),
    ]

    persisted = '<think duration="65.200">check source</think>```text\nVerse output.\n```'
    assert list(chainlit_app._reply_display_parts(persisted)) == [
        ("thinking", "check source", 65.2),
        ("answer", "```text\nVerse output.\n```"),
    ]


def test_thinking_block_label_is_not_chainlit_used_step() -> None:
    assert chainlit_app._thinking_block("check source") == (
        '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary"><span class="ttt-thinking-pipe">|</span><span> Thought for 0s</span></summary>\n\n'
        "check source\n\n"
        "</details>"
    )
    assert "Thought for 1:05" in chainlit_app._thinking_block("check source", 65)


def test_streaming_thinking_block_is_collapsed_details() -> None:
    assert chainlit_app._streaming_thinking_block("check source") == (
        '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary is-streaming"><span class="ttt-thinking-pipe">|</span><span> Thinking</span><span class="ttt-thinking-dots">...</span></summary>\n\n'
        "check source\n\n"
        "</details>"
    )


def test_chainlit_thinking_message_precedes_final_message(monkeypatch) -> None:
    events: list[tuple[str, str]] = []

    class FakeMessage:
        def __init__(self, content: str = "", author: str | None = None) -> None:
            self.content = content
            self.author = author

        async def send(self):
            events.append(("message.send", self.content))
            return self

        async def stream_token(self, token: str, is_sequence=False):
            self.content = token if is_sequence else self.content + token
            events.append(("message.token", token))

        async def update(self):
            events.append(("message.update", self.content))

    class FakeLLM:
        def stream_generation(self, *args, **kwargs):
            yield "<think>checking"
            yield " source</think>"
            yield "```text\nVerse output.\n```"

    wb = SimpleNamespace(
        llm=FakeLLM(),
        active_model_name=lambda: "fake-model",
    )
    monkeypatch.setattr(
        chainlit_app,
        "cl",
        SimpleNamespace(Message=FakeMessage),
    )

    reply, error_occurred, msg = asyncio.run(chainlit_app._stream_model_reply(wb, []))

    assert error_occurred is False
    assert reply.startswith('<think duration="')
    assert reply.endswith('>checking source</think>```text\nVerse output.\n```')
    assert msg is not None
    assert events[:4] == [
        (
            "message.send",
            '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary is-streaming"><span class="ttt-thinking-pipe">|</span><span> Thinking</span><span class="ttt-thinking-dots">...</span></summary>\n\n\n\n</details>',
        ),
        (
            "message.update",
            '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary is-streaming"><span class="ttt-thinking-pipe">|</span><span> Thinking</span><span class="ttt-thinking-dots">...</span></summary>\n\nchecking\n\n</details>',
        ),
        (
            "message.update",
            '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary is-streaming"><span class="ttt-thinking-pipe">|</span><span> Thinking</span><span class="ttt-thinking-dots">...</span></summary>\n\nchecking source\n\n</details>',
        ),
        (
            "message.update",
            '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary"><span class="ttt-thinking-pipe">|</span><span> Thought for 0s</span></summary>\n\nchecking source\n\n</details>',
        ),
    ]
    assert events[4:] == [
        ("message.send", ""),
        ("message.token", "```text\nVerse output.\n```"),
    ]


def test_chainlit_copy_button_asset_is_configured() -> None:
    config_text = (ROOT / ".chainlit" / "config.toml").read_text(encoding="utf-8")
    script_text = (ROOT / "public" / "workbench-chainlit.js").read_text(encoding="utf-8")
    css_text = (ROOT / "public" / "workbench-chainlit.css").read_text(encoding="utf-8")

    assert 'custom_js = "/public/workbench-chainlit.js"' in config_text
    assert 'custom_css = "/public/workbench-chainlit.css"' in config_text
    assert "ttt-chainlit-copy-button" in script_text
    assert "COPY_ICON = '\\u29c9'" in script_text
    assert "ttt-chainlit-user-prompt" in script_text
    assert ".bg-accent.rounded-3xl" in script_text
    assert "writeClipboardText(messageText(container))" in script_text
    assert ".ttt-thinking-summary.is-streaming .ttt-thinking-dots" in css_text
