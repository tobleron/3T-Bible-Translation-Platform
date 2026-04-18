from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ttt_workbench import chainlit_app


def test_reply_display_parts_puts_answer_after_thinking() -> None:
    content = "<think>check source</think>```text\nVerse output.\n```"

    assert list(chainlit_app._reply_display_parts(content)) == [
        ("thinking", "check source"),
        ("answer", "```text\nVerse output.\n```"),
    ]


def test_thinking_block_label_is_not_chainlit_used_step() -> None:
    assert chainlit_app._thinking_block("check source") == (
        "<details><summary>Thinking..</summary>\n\n"
        "check source\n\n"
        "</details>"
    )


def test_streaming_thinking_block_is_open_details() -> None:
    assert chainlit_app._streaming_thinking_block("check source") == (
        "<details open><summary>Thinking..</summary>\n\n"
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
    assert reply == "<think>checking source</think>```text\nVerse output.\n```"
    assert msg is not None
    assert events[:4] == [
        ("message.send", "<details open><summary>Thinking..</summary>\n\n\n\n</details>"),
        (
            "message.update",
            "<details open><summary>Thinking..</summary>\n\nchecking\n\n</details>",
        ),
        (
            "message.update",
            "<details open><summary>Thinking..</summary>\n\nchecking source\n\n</details>",
        ),
        (
            "message.update",
            "<details><summary>Thinking..</summary>\n\nchecking source\n\n</details>",
        ),
    ]
    assert events[4:] == [
        ("message.send", ""),
        ("message.token", "```text\nVerse output.\n```"),
    ]
