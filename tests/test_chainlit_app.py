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
        '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary"><span class="ttt-thinking-pipe">|</span><span> Thought for 0 seconds</span></summary>\n\n'
        "check source\n\n"
        "</details>"
    )
    assert "Thought for 1 minute 5 seconds" in chainlit_app._thinking_block("check source", 65)
    assert "Thought for 2 minutes 11 seconds" in chainlit_app._thinking_block("check source", 131)


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
            '<details class="ttt-thinking-block"><summary class="ttt-thinking-summary"><span class="ttt-thinking-pipe">|</span><span> Thought for 0 seconds</span></summary>\n\nchecking source\n\n</details>',
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

    assert 'custom_js = "/public/workbench-chainlit.js?v=2"' in config_text
    assert 'custom_css = "/public/workbench-chainlit.css?v=2"' in config_text
    assert "ttt-chainlit-copy-button" in script_text
    assert "COPY_ICON = '\\u29c9'" in script_text
    assert "ttt-chainlit-user-prompt" in script_text
    assert ".bg-accent.rounded-3xl" in script_text
    assert "writeClipboardText(messageText(container))" in script_text
    assert ".ttt-thinking-summary.is-streaming .ttt-thinking-dots" in css_text


def test_chainlit_config_uses_safe_local_defaults() -> None:
    config_text = (ROOT / ".chainlit" / "config.toml").read_text(encoding="utf-8")

    assert 'allow_origins = ["*"]' not in config_text
    assert 'allow_origins = ["http://127.0.0.1:8765", "http://localhost:8765"]' in config_text
    assert "unsafe_allow_html = true" in config_text
    assert "mask_user_env = true" in config_text
    assert "enabled = false" in config_text
    assert 'accept = []' in config_text
    assert "max_files = 0" in config_text
    assert "max_size_mb = 0" in config_text
    assert 'cot = "hidden"' in config_text


def test_ensure_active_chunk_uses_existing_book_chapter_first_chunk() -> None:
    calls: list[tuple[str, str, int, str]] = []

    class FakeWb:
        def __init__(self) -> None:
            self.state = SimpleNamespace(wizard_testament="old", book="Genesis", chapter=1)
            self._open = False

        def require_open_chunk(self):
            return self._open

        def testament(self):
            return "old"

        def current_chunk_key(self):
            return None

        def chapter_chunks(self, testament, book, chapter):
            return [SimpleNamespace(start_verse=1, end_verse=5)]

        def first_chunk_key(self, testament, book, chapter):
            return "1-5"

        def open_or_select_chunk(self, testament, book, chapter, chunk_key, announce=False):
            calls.append((testament, book, chapter, chunk_key))
            self._open = True

        def save_state(self):
            return None

        def select_chapter(self, testament, book, chapter):
            return None

        def navigator_catalog(self):
            return {"old": [], "new": []}

    wb = FakeWb()
    assert chainlit_app._ensure_active_chunk(wb) is True
    assert calls == [("old", "Genesis", 1, "1-5")]


def test_ensure_active_chunk_falls_back_to_navigator_catalog() -> None:
    calls: list[tuple[str, str, int, str]] = []

    class FakeWb:
        def __init__(self) -> None:
            self.state = SimpleNamespace(wizard_testament="", book="", chapter=0)
            self._open = False

        def require_open_chunk(self):
            return self._open

        def testament(self):
            return "new"

        def current_chunk_key(self):
            return None

        def chapter_chunks(self, testament, book, chapter):
            return []

        def first_chunk_key(self, testament, book, chapter):
            return "1-3" if (testament, book, chapter) == ("new", "Matthew", 1) else None

        def open_or_select_chunk(self, testament, book, chapter, chunk_key, announce=False):
            calls.append((testament, book, chapter, chunk_key))
            self._open = True

        def save_state(self):
            return None

        def select_chapter(self, testament, book, chapter):
            return None

        def navigator_catalog(self):
            return {
                "old": [],
                "new": [{"name": "Matthew", "first_chapter": 1, "first_ready_chapter": 1}],
            }

    wb = FakeWb()
    assert chainlit_app._ensure_active_chunk(wb) is True
    assert calls == [("new", "Matthew", 1, "1-3")]
