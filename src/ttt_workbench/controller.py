from __future__ import annotations

import html
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from uuid import uuid4

from rich.panel import Panel

from ttt_core.data.repositories import ProjectPaths
from ttt_core.llm import LlamaCppClient
from ttt_core.models import (
    ChunkSuggestion,
    PendingTitleUpdate,
    PendingVerseUpdate,
    SessionState,
)
from ttt_core.utils import normalize_book_key

from .app import WorkbenchApp
from ttt_workbench.repositories import restore_backup_set

from .chunk_catalog import ChunkCatalogRepository
from .important_words import (
    glossary_word_order,
    important_word_positions,
    important_words,
    load_spacy_model,
    verse_word_stats,
)


ORIGINAL_LANGUAGE_SOURCES = frozenset({"SBLGNT", "WLC"})
_ALLOWED_INLINE_TAGS = frozenset({"i", "em", "b", "strong", "sup", "sub", "br"})
_BLOCKED_INLINE_TAGS = frozenset({"script", "style"})
_LEGACY_BOLD_RE = re.compile(r"(?<!\*)\*\*([^*\n][^*]*?)\*\*(?!\*)")
_LEGACY_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n][^*]*?)\*(?!\*)")


class _InlineMarkupSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.block_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        clean = tag.lower()
        if clean in _BLOCKED_INLINE_TAGS:
            self.block_depth += 1
            return
        if self.block_depth:
            return
        if clean == "br":
            self.parts.append("<br>")
            return
        if clean in _ALLOWED_INLINE_TAGS:
            self.parts.append(f"<{clean}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        clean = tag.lower()
        if clean in _BLOCKED_INLINE_TAGS:
            if self.block_depth:
                self.block_depth -= 1
            return
        if self.block_depth or clean == "br":
            return
        if clean in _ALLOWED_INLINE_TAGS:
            self.parts.append(f"</{clean}>")

    def handle_data(self, data: str) -> None:
        if self.block_depth:
            return
        self.parts.append(html.escape(data))

    def handle_entityref(self, name: str) -> None:
        if self.block_depth:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.block_depth:
            return
        self.parts.append(f"&#{name};")

    def sanitized_html(self) -> str:
        return "".join(self.parts)


class _InlineTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.block_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        clean = tag.lower()
        if clean in _BLOCKED_INLINE_TAGS:
            self.block_depth += 1
            return
        if self.block_depth:
            return
        if clean == "br":
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        clean = tag.lower()
        if clean in _BLOCKED_INLINE_TAGS and self.block_depth:
            self.block_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.block_depth:
            return
        self.parts.append(data)

    def plain_text(self) -> str:
        return "".join(self.parts)


@dataclass
class PromptSetting:
    key: str
    label: str
    path: Path


class BrowserWorkbench(WorkbenchApp):
    """Headless workbench controller for the browser app."""

    _editor_line_re = re.compile(r"(?m)^\s*(\d+)\s*[\.\):-]\s*")
    _editorial_prompt_defaults = {
        "grammar": (
            "You are a precise English copyeditor. Correct only grammar, spelling, punctuation, "
            "and natural English usage. Preserve wording, tone, meaning, and sentence structure "
            "as much as possible. Change sentence structure only when the original is clearly "
            "unacceptable English. Do not add information. Do not remove information."
        ),
        "concise": (
            "You are an editorial compressor. Rewrite the text more concisely while preserving "
            "the full meaning, all relevant information, and the same theological or technical nuance. "
            "Do not omit content. Do not broaden or soften claims."
        ),
        "scholarly": (
            "You are an academic editorial assistant. Rephrase the text in a scholarly, professional, "
            "editorial tone suitable for translation footnotes and justification prose. Preserve the "
            "writer's intent and factual content. Do not introduce new claims."
        ),
        "copyable": "Output verse(s) in plain text code block.",
    }

    def __init__(self) -> None:
        llm_override, fake_mode = self._build_llm_override()
        self.fake_llm_mode = fake_mode
        super().__init__(llm_override=llm_override)
        self._configure_runtime_storage()
        self.flash_messages: list[dict[str, str]] = []
        self.chunk_catalog_repo = ChunkCatalogRepository(self.paths, self.bible_repo)
        self.settings_file = self.runtime_state_dir / "web_settings.json"
        self.chunk_sessions_file = self.runtime_state_dir / "chunk_sessions.json"
        self.chunk_sessions = self._load_chunk_sessions()
        self.web_settings = self._load_web_settings()
        self._source_support_cache: dict[str, str] = {}
        self._source_availability_cache: dict[tuple[str, str, int], bool] = {}
        self.llm.base_url = self.resolve_active_base_url(refresh=True)
        self._sanitize_browser_state()

    @staticmethod
    def _build_llm_override() -> tuple[object | None, bool]:
        flag = os.environ.get("TTT_WEBAPP_FAKE_LLM", "").strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            return None, False
        from ttt_workbench.test_support import FakeLLM, install_safe_patches

        install_safe_patches()
        return FakeLLM(), True

    def _configure_runtime_storage(self) -> None:
        self.runtime_state_dir = self.paths.state_dir
        if not self.fake_llm_mode:
            return
        self.runtime_state_dir = self.paths.state_dir / "browser_fake_mode"
        self.runtime_state_dir.mkdir(parents=True, exist_ok=True)
        fake_backups = self.runtime_state_dir / "backups"
        fake_backups.mkdir(parents=True, exist_ok=True)
        self.paths.backups_dir = fake_backups
        self.paths.state_file = self.runtime_state_dir / "active_session.json"
        self.history_path = self.runtime_state_dir / "history.txt"
        self.state = self._load_state()

    @staticmethod
    def _looks_like_fake_snapshot(path: Path) -> bool:
        name = path.name
        return name.startswith("ttt-smoke-") or "fake-web-test-backup" in name

    def _sanitize_browser_state(self) -> None:
        if self.fake_llm_mode:
            return
        changed = False
        if self.state.session_id == "ui-test":
            self.state = SessionState(session_id=uuid4().hex[:8])
            changed = True
        clean_undo = [
            raw_path
            for raw_path in self.state.undo_stack
            if Path(raw_path).exists() and not self._looks_like_fake_snapshot(Path(raw_path))
        ]
        if clean_undo != self.state.undo_stack:
            self.state.undo_stack = clean_undo
            changed = True
        clean_chat = [
            item
            for item in self.state.chat_messages
            if not (
                item.get("role") == "assistant"
                and str(item.get("content", "")).startswith("[ERROR] llama.cpp")
            )
        ]
        if clean_chat != self.state.chat_messages:
            self.state.chat_messages = clean_chat
            changed = True
        if changed:
            self.save_state()

    def _load_web_settings(self) -> dict[str, Any]:
        defaults = {
            "base_url": self.llm.base_url,
            "endpoint_provider": "local",
            "local_base_url": self.llm.base_url,
            "local_api_key": "",
            "local_model": getattr(self, "model_name", ""),
            "cloud_base_url": "https://api.openai.com/v1",
            "cloud_api_key": "",
            "cloud_model": "gpt-4.1-mini",
            "model_cache": {"local": [], "cloud": []},
            "selected_sources": ["LSB", "ESV"],
        }
        if not self.settings_file.exists():
            return defaults
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except Exception:
            return defaults
        if not isinstance(payload, dict):
            return defaults
        endpoint_provider = str(payload.get("endpoint_provider") or defaults["endpoint_provider"]).strip().lower()
        if endpoint_provider not in {"local", "cloud"}:
            endpoint_provider = "local"
        local_base_url = self._normalize_endpoint_url(
            str(payload.get("local_base_url") or payload.get("base_url") or defaults["local_base_url"])
        )
        cloud_base_url = self._normalize_endpoint_url(str(payload.get("cloud_base_url") or defaults["cloud_base_url"]))
        active_base_url = cloud_base_url if endpoint_provider == "cloud" and cloud_base_url else local_base_url
        merged = {
            "base_url": active_base_url,
            "endpoint_provider": endpoint_provider,
            "local_base_url": local_base_url,
            "local_api_key": str(payload.get("local_api_key") or defaults["local_api_key"]),
            "local_model": str(payload.get("local_model") or defaults["local_model"]),
            "cloud_base_url": cloud_base_url,
            "cloud_api_key": str(payload.get("cloud_api_key") or defaults["cloud_api_key"]),
            "cloud_model": str(payload.get("cloud_model") or defaults["cloud_model"]),
            "model_cache": payload.get("model_cache", defaults["model_cache"]),
            "selected_sources": payload.get("selected_sources", defaults["selected_sources"]),
        }
        if (
            not self.fake_llm_mode
            and "fake-llm.local" in str(merged.get("base_url", ""))
        ):
            merged["base_url"] = defaults["base_url"]
        if merged != payload:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return merged

    @staticmethod
    def _normalize_endpoint_url(value: str) -> str:
        return value.strip().rstrip("/")

    def resolve_active_base_url(self, refresh: bool = False) -> str:
        return self._normalize_endpoint_url(str(self.web_settings.get("base_url", self.llm.base_url)))

    def refresh_active_endpoint(self) -> str:
        self.llm.base_url = self.resolve_active_base_url(refresh=True)
        provider = str(self.web_settings.get("endpoint_provider", "local")).strip().lower()
        api_key = self.web_settings.get("cloud_api_key" if provider == "cloud" else "local_api_key", "")
        if hasattr(self.llm, "api_key"):
            self.llm.api_key = str(api_key or "")
        if hasattr(self.llm, "model_name"):
            self.llm.model_name = self.active_model_name()
        return self.llm.base_url

    def active_model_name(self) -> str:
        provider = str(self.web_settings.get("endpoint_provider", "local")).strip().lower()
        key = "cloud_model" if provider == "cloud" else "local_model"
        model = str(self.web_settings.get(key, "")).strip()
        return model or self.model_name

    def active_provider_label(self) -> str:
        provider = str(self.web_settings.get("endpoint_provider", "local")).strip().lower()
        return "OpenAI" if provider == "cloud" else "Local"

    def save_web_settings(self, payload: dict[str, Any]) -> None:
        selected_sources = payload.get("selected_sources", self.web_settings.get("selected_sources", []))
        endpoint_provider = str(payload.get("endpoint_provider", self.web_settings.get("endpoint_provider", "local"))).strip().lower()
        if endpoint_provider not in {"local", "cloud"}:
            endpoint_provider = "local"
        local_base_url = self._normalize_endpoint_url(
            str(payload.get("local_base_url", payload.get("base_url", self.web_settings.get("local_base_url", self.llm.base_url))))
        )
        cloud_base_url = self._normalize_endpoint_url(
            str(payload.get("cloud_base_url", self.web_settings.get("cloud_base_url", "")))
        )
        active_base_url = cloud_base_url if endpoint_provider == "cloud" and cloud_base_url else local_base_url
        local_model = str(payload.get("local_model", self.web_settings.get("local_model", self.model_name))).strip()
        cloud_model = str(payload.get("cloud_model", self.web_settings.get("cloud_model", "gpt-4.1-mini"))).strip()
        active_model = str(payload.get("active_model", "")).strip()
        if active_model:
            if endpoint_provider == "cloud":
                cloud_model = active_model
            else:
                local_model = active_model
        self.web_settings = {
            "base_url": active_base_url,
            "endpoint_provider": endpoint_provider,
            "local_base_url": local_base_url,
            "local_api_key": str(payload.get("local_api_key", self.web_settings.get("local_api_key", ""))),
            "local_model": local_model,
            "cloud_base_url": cloud_base_url,
            "cloud_api_key": str(payload.get("cloud_api_key", self.web_settings.get("cloud_api_key", ""))),
            "cloud_model": cloud_model,
            "model_cache": self.web_settings.get("model_cache", {"local": [], "cloud": []}),
            "selected_sources": selected_sources,
        }
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(
            json.dumps(self.web_settings, indent=2), encoding="utf-8"
        )
        self.refresh_active_endpoint()

    def settings_payload(self) -> dict[str, Any]:
        return {
            "endpoint_provider": self.web_settings.get("endpoint_provider", "local"),
            "local_base_url": self.web_settings.get("local_base_url", self.llm.base_url),
            "local_api_key": self.web_settings.get("local_api_key", ""),
            "local_model": self.web_settings.get("local_model", self.model_name),
            "cloud_base_url": self.web_settings.get("cloud_base_url", ""),
            "cloud_api_key": self.web_settings.get("cloud_api_key", ""),
            "cloud_model": self.web_settings.get("cloud_model", "gpt-4.1-mini"),
            "local_model_options": self.cached_model_names("local"),
            "cloud_model_options": self.cached_model_names("cloud"),
            "active_model": self.active_model_name(),
            "active_base_url": self.resolve_active_base_url(),
        }

    def _load_chunk_sessions(self) -> dict[str, dict[str, Any]]:
        if not self.chunk_sessions_file.exists():
            return {}
        try:
            payload = json.loads(self.chunk_sessions_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        clean: dict[str, dict[str, Any]] = {}
        for key, value in payload.items():
            if isinstance(key, str) and isinstance(value, dict):
                clean[key] = value
        return clean

    def _save_chunk_sessions(self) -> None:
        self.chunk_sessions_file.parent.mkdir(parents=True, exist_ok=True)
        self.chunk_sessions_file.write_text(
            json.dumps(self.chunk_sessions, indent=2), encoding="utf-8"
        )

    def chunk_session_key(
        self,
        testament: str | None = None,
        book: str | None = None,
        chapter: int | None = None,
        chunk_key: str | None = None,
    ) -> str | None:
        testament_name = testament or self.state.wizard_testament or self.testament() or ""
        book_name = book or self.state.book or ""
        chapter_number = chapter or self.state.chapter or 0
        range_key = chunk_key or self.current_chunk_key() or ""
        if not (testament_name and book_name and chapter_number and range_key):
            return None
        internal_id = self.current_chunk_internal_id(testament_name, book_name, chapter_number, range_key)
        return f"{testament_name}|{normalize_book_key(book_name)}|{chapter_number}|{range_key}|{internal_id}"

    def legacy_chunk_session_key(
        self,
        testament: str | None = None,
        book: str | None = None,
        chapter: int | None = None,
        chunk_key: str | None = None,
    ) -> str | None:
        testament_name = testament or self.state.wizard_testament or self.testament() or ""
        book_name = book or self.state.book or ""
        chapter_number = chapter or self.state.chapter or 0
        range_key = chunk_key or self.current_chunk_key() or ""
        if not (testament_name and book_name and chapter_number and range_key):
            return None
        return f"{testament_name}|{normalize_book_key(book_name)}|{chapter_number}|{range_key}"

    def current_chunk_session(self) -> dict[str, Any]:
        key = self.chunk_session_key()
        if not key:
            return {}
        legacy_key = self.legacy_chunk_session_key()
        if key not in self.chunk_sessions and legacy_key and legacy_key in self.chunk_sessions:
            self.chunk_sessions[key] = self.chunk_sessions.pop(legacy_key)
        if key not in self.chunk_sessions:
            self.chunk_sessions[key] = {
                "active_session_id": uuid4().hex[:10],
                "sessions": {},
            }
        record = self.chunk_sessions[key]
        if "sessions" not in record:
            session_id = str(record.get("active_session_id") or uuid4().hex[:10])
            record = {
                "active_session_id": session_id,
                "sessions": {
                    session_id: {
                        "title": self.chunk_chat_session_title(1),
                        "messages": list(record.get("messages", [])),
                        "context_loaded": bool(record.get("context_loaded")),
                        "context_snapshot": str(record.get("context_snapshot", "")),
                        "focus_start": record.get("focus_start", self.state.focus_start),
                        "focus_end": record.get("focus_end", self.state.focus_end),
                    }
                },
            }
            self.chunk_sessions[key] = record
        active_id = str(record.get("active_session_id") or "")
        sessions = record.setdefault("sessions", {})
        if not active_id or active_id not in sessions:
            active_id = uuid4().hex[:10]
            record["active_session_id"] = active_id
            sessions[active_id] = {
                "title": self.chunk_chat_session_title(len(sessions) + 1),
                "messages": [],
                "context_loaded": False,
                "context_snapshot": "",
                "focus_start": self.state.focus_start,
                "focus_end": self.state.focus_end,
            }
        return sessions[active_id]

    def active_chat_session_id(self) -> str:
        key = self.chunk_session_key()
        if not key:
            return ""
        self.current_chunk_session()
        return str(self.chunk_sessions.get(key, {}).get("active_session_id", ""))

    def load_chunk_session(
        self,
        testament: str,
        book: str,
        chapter: int,
        chunk_key: str,
    ) -> None:
        key = self.chunk_session_key(testament, book, chapter, chunk_key)
        if key:
            self.current_chunk_session()
        session = self.current_chunk_session() if key else {}
        messages = session.get("messages", [])
        self.state.chat_messages = messages if isinstance(messages, list) else []
        focus_start = session.get("focus_start")
        focus_end = session.get("focus_end")
        if isinstance(focus_start, int) and isinstance(focus_end, int):
            self.state.focus_start = focus_start
            self.state.focus_end = focus_end

    def persist_current_chunk_session(self) -> None:
        key = self.chunk_session_key()
        if not key:
            return
        session = self.current_chunk_session()
        session["messages"] = list(self.state.chat_messages)
        session["context_loaded"] = bool(session.get("context_loaded"))
        session["context_snapshot"] = str(session.get("context_snapshot", ""))
        session["focus_start"] = self.state.focus_start
        session["focus_end"] = self.state.focus_end
        self._save_chunk_sessions()

    def clear_current_chunk_session(self) -> None:
        key = self.chunk_session_key()
        if key:
            session = self.current_chunk_session()
            session["messages"] = []
            session["context_loaded"] = False
            session["context_snapshot"] = ""
            self._save_chunk_sessions()
        self.state.chat_messages = []
        self.notify("Cleared the saved chat session for this chunk.")

    def abbreviated_book_name(self, book: str | None = None) -> str:
        raw = (book or self.state.book or "").strip()
        if not raw:
            return "Chunk"
        compact = re.sub(r"[^A-Za-z0-9 ]+", " ", raw)
        compact = re.sub(r"\s+", " ", compact).strip()
        direct = {
            "genesis": "Gen", "exodus": "Ex", "leviticus": "Lev", "numbers": "Num",
            "deuteronomy": "Deut", "joshua": "Josh", "judges": "Judg", "ruth": "Ruth",
            "1 samuel": "1Sam", "2 samuel": "2Sam", "1 kings": "1Kgs", "2 kings": "2Kgs",
            "1 chronicles": "1Chr", "2 chronicles": "2Chr", "ezra": "Ezra", "nehemiah": "Neh",
            "esther": "Esth", "job": "Job", "psalms": "Ps", "psalm": "Ps", "proverbs": "Prov",
            "ecclesiastes": "Eccl", "song of songs": "Song", "isaiah": "Isa", "jeremiah": "Jer",
            "lamentations": "Lam", "ezekiel": "Ezek", "daniel": "Dan", "hosea": "Hos",
            "joel": "Joel", "amos": "Amos", "obadiah": "Obad", "jonah": "Jonah", "micah": "Mic",
            "nahum": "Nah", "habakkuk": "Hab", "zephaniah": "Zeph", "haggai": "Hag",
            "zechariah": "Zech", "malachi": "Mal", "matthew": "Matt", "mark": "Mark",
            "luke": "Luke", "john": "John", "acts": "Acts", "romans": "Rom",
            "1 corinthians": "1Cor", "2 corinthians": "2Cor", "galatians": "Gal",
            "ephesians": "Eph", "philippians": "Phil", "colossians": "Col",
            "1 thessalonians": "1Th", "2 thessalonians": "2Th", "1 timothy": "1Tim",
            "2 timothy": "2Tim", "titus": "Titus", "philemon": "Phlm", "hebrews": "Heb",
            "james": "Jas", "1 peter": "1Pet", "2 peter": "2Pet", "1 john": "1Jn",
            "2 john": "2Jn", "3 john": "3Jn", "jude": "Jude", "revelation": "Rev",
        }
        key = compact.lower()
        if key in direct:
            return direct[key]
        parts = compact.split()
        if len(parts) == 1:
            return parts[0][:4].title()
        prefix = parts[0] if parts[0].isdigit() else ""
        words = parts[1:] if prefix else parts
        initials = "".join(word[0].upper() for word in words if word.lower() not in {"of", "the", "and"})
        return f"{prefix}{initials[:4]}" or "Chunk"

    def chunk_chat_session_title(self, index: int) -> str:
        book = self.abbreviated_book_name()
        chapter = self.state.chapter or 0
        chunk_range = self.current_chunk_key() or "range"
        return f"{book}_{chapter}_{chunk_range}_{index}"

    def new_current_chunk_chat_session(self) -> str:
        key = self.chunk_session_key()
        if not key:
            return ""
        self.current_chunk_session()
        record = self.chunk_sessions[key]
        sessions = record.setdefault("sessions", {})
        session_id = uuid4().hex[:10]
        record["active_session_id"] = session_id
        sessions[session_id] = {
            "title": self.chunk_chat_session_title(len(sessions) + 1),
            "messages": [],
            "context_loaded": False,
            "context_snapshot": "",
            "focus_start": self.state.focus_start,
            "focus_end": self.state.focus_end,
        }
        self.state.chat_messages = []
        self._save_chunk_sessions()
        self.save_state()
        return session_id

    def delete_current_chunk_chat_session(self) -> None:
        key = self.chunk_session_key()
        if not key:
            return
        self.current_chunk_session()
        record = self.chunk_sessions[key]
        sessions = record.setdefault("sessions", {})
        active_id = str(record.get("active_session_id", ""))
        if active_id and active_id in sessions:
            sessions.pop(active_id, None)
        if sessions:
            next_id = next(reversed(sessions))
            record["active_session_id"] = next_id
            session = sessions[next_id]
            messages = session.get("messages", [])
            self.state.chat_messages = messages if isinstance(messages, list) else []
        else:
            session_id = uuid4().hex[:10]
            record["active_session_id"] = session_id
            sessions[session_id] = {
                "title": self.chunk_chat_session_title(1),
                "messages": [],
                "context_loaded": False,
                "context_snapshot": "",
                "focus_start": self.state.focus_start,
                "focus_end": self.state.focus_end,
            }
            self.state.chat_messages = []
        self._save_chunk_sessions()
        self.save_state()
        self.notify("Deleted the active chat session.")

    def switch_current_chunk_chat_session(self, session_id: str) -> bool:
        key = self.chunk_session_key()
        if not key:
            return False
        self.current_chunk_session()
        record = self.chunk_sessions[key]
        sessions = record.setdefault("sessions", {})
        if session_id not in sessions:
            return False
        record["active_session_id"] = session_id
        session = sessions[session_id]
        messages = session.get("messages", [])
        self.state.chat_messages = messages if isinstance(messages, list) else []
        self._save_chunk_sessions()
        self.save_state()
        return True

    def save_state(self) -> None:
        if self.has_open_chunk():
            self.persist_current_chunk_session()
        super().save_state()

    def selected_sources(self) -> list[str]:
        values = self.web_settings.get("selected_sources", [])
        if not isinstance(values, list):
            values = []
        selected = [
            str(item).upper()
            for item in values
            if str(item).strip()
            and str(item).upper() in self.source_repo.catalog
            and str(item).upper() not in ORIGINAL_LANGUAGE_SOURCES
        ]
        if selected:
            return selected
        if not values:
            return []
        fallbacks = [
            alias
            for alias in ("LSB", "ESV", "NET")
            if alias in self.source_repo.catalog
        ]
        if fallbacks:
            return fallbacks
        return self.source_repo.list_sources()[:2]

    def set_selected_sources(self, aliases: list[str]) -> None:
        clean = [
            alias.upper()
            for alias in aliases
            if alias.upper() in self.source_repo.catalog
            and alias.upper() not in ORIGINAL_LANGUAGE_SOURCES
        ]
        self.save_web_settings({"selected_sources": clean})

    def chat_context_sources(self) -> list[str]:
        values = getattr(self.state, "browser_chat_sources", [])
        if not isinstance(values, list):
            return ["draft"]
        clean: list[str] = []
        for item in values:
            value = str(item).strip().lower()
            if value in {"draft", "original"} and value not in clean:
                clean.append(value)
        return clean or []

    def set_chat_context_sources(self, values: list[str]) -> None:
        clean: list[str] = []
        for item in values:
            value = str(item).strip().lower()
            if value in {"draft", "original"} and value not in clean:
                clean.append(value)
        self.state.browser_chat_sources = clean

    @staticmethod
    def _legacy_inline_markup_to_html(text: str) -> str:
        clean = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        clean = _LEGACY_BOLD_RE.sub(r"<strong>\1</strong>", clean)
        clean = _LEGACY_ITALIC_RE.sub(r"<em>\1</em>", clean)
        return clean.replace("\n", "<br>")

    @classmethod
    def sanitize_inline_markup(cls, text: str) -> str:
        prepared = cls._legacy_inline_markup_to_html(text)
        parser = _InlineMarkupSanitizer()
        parser.feed(prepared)
        parser.close()
        return parser.sanitized_html()

    @classmethod
    def plain_text_from_inline_markup(cls, text: str) -> str:
        sanitized = cls.sanitize_inline_markup(text)
        parser = _InlineTextExtractor()
        parser.feed(sanitized)
        parser.close()
        plain = parser.plain_text()
        return re.sub(r"\s+", " ", plain).strip()

    @classmethod
    def inline_markup_payload(cls, text: str) -> dict[str, str]:
        return {
            "raw": str(text or ""),
            "html": cls.sanitize_inline_markup(text),
            "text": cls.plain_text_from_inline_markup(text),
        }

    def prompt_settings(self) -> list[PromptSetting]:
        return [
            PromptSetting(
                key="chunk_schema",
                label="Chunk Schema Prompt",
                path=self.paths.chunking_prompts_dir / "chunk_schema.txt",
            ),
            PromptSetting(
                key="ot_chunk",
                label="OT Chunk Suggest Prompt",
                path=self.paths.chunking_prompts_dir / "ot_chunk_suggest.txt",
            ),
            PromptSetting(
                key="nt_chunk",
                label="NT Chunk Suggest Prompt",
                path=self.paths.chunking_prompts_dir / "nt_chunk_suggest.txt",
            ),
            PromptSetting(
                key="legacy_analysis",
                label="Legacy Analysis Prompt",
                path=self.paths.legacy_prompt_path,
            ),
        ]

    def editorial_prompts(self) -> dict[str, str]:
        prompts = dict(self._editorial_prompt_defaults)
        stored = getattr(self.state, "editorial_prompts", {}) or {}
        if isinstance(stored, dict):
            for key in ("grammar", "concise", "scholarly"):
                value = stored.get(key)
                if isinstance(value, str) and value.strip():
                    prompts[key] = value.strip()
        return prompts

    def save_editorial_prompts(self, updates: dict[str, str]) -> None:
        prompts = self.editorial_prompts()
        for key, value in updates.items():
            if key in prompts and isinstance(value, str) and value.strip():
                prompts[key] = value.strip()
        self.state.editorial_prompts = prompts

    @staticmethod
    def editorial_mode_label(mode: str) -> str:
        labels = {
            "grammar": "Grammar Only",
            "concise": "Concise Rewrite",
            "scholarly": "Scholarly Rewrite",
            "custom": "Custom Tweak",
        }
        return labels.get(str(mode).strip().lower(), "Editorial Output")

    def build_editorial_enhancement_prompt(
        self,
        *,
        source_text: str,
        instruction: str,
        context_label: str,
    ) -> str:
        return f"""
{instruction}

Source text:
{source_text.strip() or "[blank]"}

Return strict JSON only:
{{
  "text": "the revised text only"
}}

Rules:
- Return only one revised version.
- Do not add commentary, notes, bullets, or explanation.
- Do not wrap the answer in markdown fences.
""".strip()

    def run_editorial_enhancement(
        self,
        *,
        source_text: str,
        mode: str,
        context_label: str,
        prompt_override: str = "",
        custom_prompt: str = "",
    ) -> str:
        clean_mode = str(mode).strip().lower()
        text = str(source_text or "").strip()
        if not text:
            raise ValueError("Add text before running editorial enhancement.")
        prompts = self.editorial_prompts()
        if clean_mode == "custom":
            instruction = str(custom_prompt or "").strip()
            if not instruction:
                raise ValueError("Add a custom prompt before running the custom tweak.")
        else:
            instruction = str(prompt_override or "").strip() or prompts.get(clean_mode, "").strip()
            if clean_mode not in prompts:
                raise ValueError("Choose a valid editorial enhancement mode.")
        self.refresh_active_endpoint()
        payload, response, _attempts = self.llm.complete_json(
            self.build_editorial_enhancement_prompt(
                source_text=text,
                instruction=instruction,
                context_label=context_label,
            ),
            required_keys=["text"],
            temperature=0.7,
            max_tokens=900,
            max_attempts=3,
        )
        if not isinstance(payload, dict):
            if str(response).startswith("[ERROR]"):
                raise ValueError(self.explain_llm_failure(str(response)))
            raise ValueError("The endpoint did not return a valid editorial enhancement response.")
        result = str(payload.get("text", "")).strip()
        if not result:
            raise ValueError("The model returned an empty editorial enhancement response.")
        return result

    def prompt_payload(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        for item in self.prompt_settings():
            if item.path.exists():
                payload[item.key] = item.path.read_text(encoding="utf-8")
            else:
                payload[item.key] = ""
        return payload

    def save_prompt_payload(self, updates: dict[str, str]) -> None:
        for item in self.prompt_settings():
            if item.key not in updates:
                continue
            item.path.write_text(updates[item.key], encoding="utf-8")
        if self.paths.legacy_prompt_path.exists():
            self.legacy_prompt = self.paths.legacy_prompt_path.read_text(
                encoding="utf-8"
            )

    @staticmethod
    def activity_summary(title: str, body: str) -> str:
        for raw_line in body.splitlines():
            line = " ".join(
                raw_line.replace("│", " ")
                .replace("┆", " ")
                .replace("•", " ")
                .split()
            ).strip("─ ").strip()
            if not line or line.lower() == title.lower():
                continue
            return line
        return title

    def emit(self, renderable: object) -> None:
        title = "Notice"
        body = self.theme.render_transcript_text(renderable, width=90).strip()
        accent = "aqua"
        if isinstance(renderable, Panel):
            title = str(renderable.title or "Notice").strip() or "Notice"
            accent = self.infer_history_accent(title)
            panel_body = renderable.renderable
            if hasattr(panel_body, "plain"):
                body = str(panel_body.plain).strip()
            else:
                body = self.theme.render_text(panel_body, width=90).strip()
        if not body:
            return
        self.history_entries.append(
            {
                "title": title,
                "body": body,
                "accent": accent,
                "summary": self.activity_summary(title, body),
            }
        )
        if len(self.history_entries) > 120:
            self.history_entries = self.history_entries[-120:]
        self.flash_messages.append(
            {
                "title": title,
                "body": body,
                "accent": accent,
                "summary": self.activity_summary(title, body),
            }
        )

    def flush_ui(self) -> None:
        return

    def render_status(self) -> None:
        return

    def clear_flash(self) -> None:
        self.flash_messages = []

    def _dedup_flash_messages(self) -> list[dict[str, str]]:
        """Return flash messages with consecutive duplicates collapsed."""
        deduped: list[dict[str, str]] = []
        for msg in self.flash_messages[-10:]:
            if not msg.get("title") or msg["title"].strip().lower() in {"notice", ""}:
                continue
            body = (msg.get("body") or "").strip()
            summary = (msg.get("summary") or self.activity_summary(str(msg.get("title", "")), body)).strip()
            if not body and not summary:
                continue
            if deduped:
                prev = deduped[-1]
                if (
                    prev.get("title") == msg["title"]
                    and prev.get("summary", "").strip() == summary
                ):
                    continue
            msg = {**msg, "summary": summary}
            deduped.append(msg)
        return deduped

    def _dedup_activity_items(self) -> list[dict[str, str]]:
        """Return last 3 history entries with duplicates and system noise collapsed."""
        items = list(self.history_entries[-8:])
        _SYSTEM_TITLES = {"notice", "chunk opened", "notice ────────"}
        deduped: list[dict[str, str]] = []
        for item in items:
            title = (item.get("title") or "").strip().lower()
            summary = (item.get("summary") or "").strip()
            # Skip pure system noise
            if not summary or title in _SYSTEM_TITLES:
                continue
            # Skip entries that are just file path announcements
            if "ready" in summary.lower() and ".json" in summary:
                continue
            if deduped:
                prev = deduped[-1]
                if prev.get("title") == item.get("title") and prev.get("summary", "").strip() == summary:
                    continue
            deduped.append(item)
        return deduped[-3:]

    def current_chunk_key(self) -> str | None:
        if not self.state.chunk_start or not self.state.chunk_end:
            return None
        return f"{self.state.chunk_start}-{self.state.chunk_end}"

    def current_chunk_internal_id(
        self,
        testament: str | None = None,
        book: str | None = None,
        chapter: int | None = None,
        chunk_key: str | None = None,
    ) -> str:
        testament_name = testament or self.state.wizard_testament or self.testament() or ""
        book_name = book or self.state.book or ""
        chapter_number = chapter or self.state.chapter or 0
        range_key = chunk_key or self.current_chunk_key() or ""
        title = self._chunk_catalog_title(book_name, chapter_number, range_key) if book_name and chapter_number and range_key else ""
        if not title:
            title = self.state.draft_title.strip() or self.committed_chunk_title()
        basis = "|".join(
            [
                str(testament_name).strip().lower(),
                normalize_book_key(book_name),
                str(chapter_number),
                str(range_key).strip(),
                re.sub(r"\s+", " ", str(title or "").strip().lower()),
            ]
        )
        return f"chunk-{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:12]}"

    def navigator_catalog(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"old": [], "new": []}
        for testament in ("old", "new"):
            for book in self.bible_repo.canonical_books(testament):
                chapters = self.source_repo.chapters_for_book(book)
                if not chapters:
                    try:
                        chapters = self.bible_repo.chapters_for_book(testament, book)
                    except Exception:
                        chapters = []
                chunk_counts = self.chunk_catalog_repo.chunk_status_map(testament, book)
                payload[testament].append(
                    {
                        "name": book,
                        "chapters": chapters,
                        "chunk_counts": chunk_counts,
                        "first_chapter": chapters[0] if chapters else None,
                        "first_ready_chapter": min(chunk_counts) if chunk_counts else None,
                    }
                )
        return payload

    def project_summary(self) -> dict[str, Any]:
        """Calculate granular project progress and source stats."""
        total_chapters = 0
        cataloged_chapters = 0
        translated_chapters = 0
        total_chunks = 0
        
        # We'll also track verse-level progress for higher precision if possible
        # but chapter-level is safer/faster for now.
        
        for testament in ("old", "new"):
            for book in self.bible_repo.canonical_books(testament):
                chapters = self.source_repo.chapters_for_book(book)
                if not chapters:
                    try:
                        chapters = self.bible_repo.chapters_for_book(testament, book)
                    except Exception:
                        chapters = []
                
                total_chapters += len(chapters)
                
                # Catalog progress: chunks defined in _chunks.json
                chunk_counts = self.chunk_catalog_repo.chunk_status_map(testament, book)
                cataloged_chapters += len(chunk_counts)
                total_chunks += sum(chunk_counts.values())
                
                # Translation progress: committed JSON with text
                for chapter in chapters:
                    if self.bible_repo.chapter_exists(book, chapter):
                        try:
                            # We don't want to load every file if we can avoid it, 
                            # but for a dashboard summary it might be okay once.
                            # BibleRepository already builds an index.
                            translated_chapters += 1
                        except Exception:
                            continue

        sources = []
        for alias in self.source_repo.list_sources():
            path = self.source_repo.catalog.get(alias)
            sources.append({
                "alias": alias,
                "name": self.source_repo.display_names.get(alias, alias),
                "path": str(path.relative_to(self.paths.repo_root)) if path else ""
            })

        catalog_percent = (cataloged_chapters / total_chapters * 100) if total_chapters > 0 else 0
        translation_percent = (translated_chapters / total_chapters * 100) if total_chapters > 0 else 0
        
        return {
            "total_chapters": total_chapters,
            "cataloged_chapters": cataloged_chapters,
            "translated_chapters": translated_chapters,
            "total_chunks": total_chunks,
            "catalog_percent": round(catalog_percent, 1),
            "translation_percent": round(translation_percent, 1),
            "sources": sources,
        }

    def load_workspace(self, testament: str, book: str, chapter: int, chunk_key: str) -> None:
        start_verse, end_verse = [int(part) for part in chunk_key.split("-", 1)]
        self.open_chunk(book, chapter, start_verse, end_verse)
        self.state.footnote_draft = None
        self.state.wizard_testament = testament
        # Populate the visible title without treating committed text as draft work.
        if not self.state.draft_title.strip():
            self.state.draft_title = self.committed_chunk_title()
            if not self.state.draft_title.strip():
                self.state.draft_title = self._chunk_catalog_title(book, chapter, chunk_key)
        
        # Initialize editor state machine
        if self.chunk_has_committed_text() and not self.has_draft_work():
            self.state.browser_editor_state = "committed"
            self.state.browser_editor_mode = "review"
        else:
            self.state.browser_editor_state = "editing"
            self.state.browser_editor_mode = "draft"

        self.set_screen("STUDY", mode="COMMAND")
        self.save_state()

    def lock_editor(self) -> None:
        self.state.browser_editor_state = "locked"
        self.save_state()

    def unlock_editor(self) -> None:
        self.state.browser_editor_state = "editing"
        self.save_state()

    def start_revision(self) -> None:
        if self.state.browser_editor_state == "committed":
            if not self.has_draft_work():
                self.seed_draft_from_committed()
        self.state.browser_editor_state = "editing"
        self.state.browser_editor_mode = "draft"
        self.save_state()

    def select_chapter(self, testament: str, book: str, chapter: int) -> None:
        self.state.wizard_testament = testament
        self.state.wizard_book = book
        self.state.wizard_chapter = chapter
        self.state.book = book
        self.state.chapter = chapter
        self.state.chunk_start = None
        self.state.chunk_end = None
        self.state.focus_start = None
        self.state.focus_end = None
        self.state.browser_editor_mode = "draft"
        self.state.browser_editor_state = "editing"
        self.state.chat_messages = []
        self.state.draft_chunk = {}
        self.state.draft_title = ""
        self.state.title_alternatives = []
        self.state.last_review = None
        self.state.justify_draft = None
        self.state.footnote_draft = None
        self.state.chunk_suggestions = []
        self.state.chunk_suggestion_window_start = None
        self.state.chunk_suggestion_window_end = None
        self.state.mode = "COMMAND"
        self.set_screen("STUDY", mode="COMMAND")
        self.save_state()

    def _chunk_catalog_title(self, book: str, chapter: int, chunk_key: str) -> str:
        chunks = self.chapter_chunks(self.state.wizard_testament or self.testament() or "new", book, chapter)
        for chunk in chunks:
            if f"{chunk.start_verse}-{chunk.end_verse}" == chunk_key:
                return str(chunk.title).strip()
        return ""

    def committed_chunk_title(self) -> str:
        if not self.has_open_chunk():
            return ""
        try:
            chapter_doc = self.current_chapter()
            section_index = self.bible_repo.title_section_index(
                chapter_doc,
                self.state.chunk_start or 1,
                self.state.chunk_end or 1,
            )
        except Exception:
            return ""
        return str(
            chapter_doc.get("sections", [{}])[section_index].get("headline", "")
        ).strip()

    def chunk_has_committed_text(self) -> bool:
        if not self.has_open_chunk():
            return False
        chapter_map = self.chapter_verse_map()
        for verse in range((self.state.chunk_start or 1), (self.state.chunk_end or 1) + 1):
            if chapter_map.get(verse, "").strip():
                return True
        return False

    def has_draft_work(self) -> bool:
        if not self.has_open_chunk():
            return False
        # Only consider draft work within the current chunk boundaries
        for verse in range((self.state.chunk_start or 1), (self.state.chunk_end or 1) + 1):
            if str(self.state.draft_chunk.get(str(verse), "")).strip():
                return True
        draft_title = (self.state.draft_title or "").strip()
        if draft_title and self.chunk_has_committed_text():
            return draft_title != self.committed_chunk_title()
        return bool(draft_title)

    def default_editor_mode(self) -> str:
        return "review" if self.chunk_has_committed_text() else "draft"

    def editor_mode(self) -> str:
        mode = str(getattr(self.state, "browser_editor_mode", "draft") or "draft").lower()
        if mode not in {"draft", "review"}:
            return self.default_editor_mode()
        return mode

    def set_editor_mode(self, mode: str) -> str:
        clean = "review" if str(mode).lower() == "review" else "draft"
        self.state.browser_editor_mode = clean
        return clean

    def sync_editor_mode(self, *, force_default: bool = False) -> str:
        if not self.has_open_chunk():
            self.state.browser_editor_mode = "draft"
            self.state.browser_editor_state = "editing"
            return "draft"
        
        # If we are already in committed state, stick with it
        if self.state.browser_editor_state == "committed":
            self.state.browser_editor_mode = "review"
            return "review"

        # If we have committed text and NO draft work, and we are NOT actively editing, default to committed
        if self.chunk_has_committed_text() and not self.has_draft_work() and self.state.browser_editor_state != "editing":
            self.state.browser_editor_state = "committed"
            self.state.browser_editor_mode = "review"
            return "review"

        if force_default or self.editor_mode() not in {"draft", "review"}:
            mode = self.default_editor_mode()
            self.state.browser_editor_mode = mode
            if mode == "review":
                 self.state.browser_editor_state = "committed"
            else:
                 self.state.browser_editor_state = "editing"
            return mode

        mode = self.editor_mode()
        self.state.browser_editor_mode = mode
        return mode

    def seed_draft_from_committed(self) -> None:
        if not self.has_open_chunk():
            return
        chapter_map = self.chapter_verse_map()
        for verse in range((self.state.chunk_start or 1), (self.state.chunk_end or 1) + 1):
            committed = chapter_map.get(verse, "")
            if committed.strip():
                self.state.draft_chunk[str(verse)] = committed.strip()
        committed_title = self.committed_chunk_title()
        if committed_title:
            self.state.draft_title = committed_title
        self.state.browser_editor_state = "editing"
        self.set_editor_mode("draft")
        self.prepare_browser_commit_state()

    def first_chunk_key(self, testament: str, book: str, chapter: int) -> str | None:
        chunks = self.chapter_chunks(testament, book, chapter)
        if not chunks:
            return None
        first = chunks[0]
        return f"{first.start_verse}-{first.end_verse}"

    def chapter_chunks(
        self, testament: str, book: str, chapter: int
    ) -> list[ChunkSuggestion]:
        chunks = self.chunk_catalog_repo.load_chapter_chunks(testament, book, chapter)
        if chunks:
            return chunks
        if self.state.book == book and self.state.chapter == chapter and self.state.chunk_suggestions:
            return list(self.state.chunk_suggestions)
        return []

    def build_study_cards(self) -> list[dict[str, Any]]:
        if not self.has_open_chunk():
            return []
        start_verse = self.state.chunk_start or 1
        end_verse = self.state.chunk_end or start_verse
        testament = self.testament()
        cards: list[dict[str, Any]] = []
        if testament == "old":
            hebrew = self.lexical_repo.fetch_tokens(
                "hebrew_ot", self.state.book or "", self.state.chapter or 0, start_verse, end_verse
            )
            lxx = self.lexical_repo.fetch_tokens(
                "greek_ot_lxx", self.state.book or "", self.state.chapter or 0, start_verse, end_verse
            )
            for verse in range(start_verse, end_verse + 1):
                ref = self.lexical_ref(verse, corpus="hebrew_ot")
                heb_tokens = hebrew.get(ref, [])
                lxx_tokens = lxx.get(self.lexical_ref(verse, corpus="greek_ot_lxx"), [])
                cards.append(
                    {
                        "verse": verse,
                        "primary_label": "Hebrew",
                        "primary_surface": " ".join(
                            t.get("surface", "").strip()
                            for t in heb_tokens
                            if t.get("surface", "").strip()
                        )
                        or "[missing]",
                        "literal": " / ".join(
                            (t.get("english") or t.get("gloss") or "").replace("<br>", "; ").strip()
                            for t in heb_tokens
                            if (t.get("english") or t.get("gloss"))
                        )
                        or "[missing]",
                        "comparison_label": "LXX" if lxx_tokens else "",
                        "comparison_surface": " ".join(
                            t.get("surface", "").strip()
                            for t in lxx_tokens
                            if t.get("surface", "").strip()
                        ),
                        "comparison_literal": " / ".join(
                            (t.get("gloss") or t.get("english") or "").replace("<br>", "; ").strip()
                            for t in lxx_tokens
                            if (t.get("gloss") or t.get("english"))
                        ),
                        "translations": self.selected_translation_rows(verse),
                    }
                )
        else:
            greek = self.lexical_repo.fetch_tokens(
                "greek_nt", self.state.book or "", self.state.chapter or 0, start_verse, end_verse
            )
            for verse in range(start_verse, end_verse + 1):
                ref = self.lexical_ref(verse, corpus="greek_nt")
                tokens = greek.get(ref, [])
                cards.append(
                    {
                        "verse": verse,
                        "primary_label": "Greek",
                        "primary_surface": " ".join(
                            t.get("surface", "").strip()
                            for t in tokens
                            if t.get("surface", "").strip()
                        )
                        or "[missing]",
                        "literal": " / ".join(
                            (t.get("gloss") or t.get("english") or "").replace("<br>", "; ").strip()
                            for t in tokens
                            if (t.get("gloss") or t.get("english"))
                        )
                        or "[missing]",
                        "comparison_label": "",
                        "comparison_surface": "",
                        "comparison_literal": "",
                        "translations": self.selected_translation_rows(verse),
                    }
                )
        return cards

    def source_support_label(self, alias: str) -> str:
        if alias in self._source_support_cache:
            return self._source_support_cache[alias]
        mapping = self.source_repo._load_source(alias)
        has_ot = any(book == normalize_book_key("Genesis") for (book, _chapter, _verse) in mapping)
        has_nt = any(book == normalize_book_key("Matthew") for (book, _chapter, _verse) in mapping)
        if has_ot and has_nt:
            label = "OT + NT"
        elif has_nt:
            label = "NT only"
        elif has_ot:
            label = "OT only"
        else:
            label = "Partial"
        self._source_support_cache[alias] = label
        return label

    def source_available_for_chapter(self, alias: str, book: str, chapter: int) -> bool:
        if not book or not chapter:
            return False
        book_key = normalize_book_key(book)
        cache_key = (alias, book_key, chapter)
        if cache_key not in self._source_availability_cache:
            alias_map = self.source_repo._load_source(alias)
            self._source_availability_cache[cache_key] = any(
                key_book == book_key and key_chapter == chapter
                for (key_book, key_chapter, _verse) in alias_map.keys()
            )
        return self._source_availability_cache[cache_key]

    def comparison_source_options(self) -> list[dict[str, str | bool]]:
        current_testament = self.state.wizard_testament or self.testament() or "new"
        current_book = self.state.book or ""
        current_chapter = self.state.chapter or 0
        selected = set(self.selected_sources())
        preferred_order = [
            "NIV",
            "ESV",
            "LSB",
            "CSB",
            "NKJV",
            "NLT",
            "NET",
            "TLV",
            "KJV",
            "LSV",
            "BSB",
            "LEB",
            "NJB",
        ]
        available_aliases = [alias for alias in self.comparison_sources() if alias not in ORIGINAL_LANGUAGE_SOURCES]
        preferred = [alias for alias in preferred_order if alias in available_aliases]
        remaining = [alias for alias in available_aliases if alias not in preferred]
        ordered_aliases = preferred + (["__separator__"] if preferred and remaining else []) + remaining
        options: list[dict[str, str | bool]] = []
        for alias in ordered_aliases:
            if alias == "__separator__":
                options.append({"alias": alias, "label": "", "support": "", "selected": False, "available_here": False, "disabled": True, "separator": True})
                continue
            if alias in ORIGINAL_LANGUAGE_SOURCES:
                continue
            available_here = self.source_available_for_chapter(alias, current_book, current_chapter)
            support = self.source_support_label(alias)
            options.append(
                {
                    "alias": alias,
                    "label": alias,
                    "support": support,
                    "selected": alias in selected,
                    "available_here": available_here,
                    "disabled": current_testament == "old" and support == "NT only",
                    "separator": False,
                }
            )
        return options

    def selected_translation_rows(self, verse: int) -> list[dict[str, str]]:
        if not self.state.book or not self.state.chapter:
            return []
        rows: list[dict[str, str]] = []
        for alias in self.selected_sources():
            text = self.source_repo.verse_text(
                alias, self.state.book, self.state.chapter, verse
            ).strip()
            rows.append(
                {
                    "alias": alias,
                    "text": text,
                    "missing": "true" if not text else "",
                    "note": "Not present in this source for this verse." if not text else "",
                }
            )
        return rows

    def _chunk_join(self, pieces: list[str]) -> str:
        return " ".join(piece.strip() for piece in pieces if piece and piece.strip()).strip() or "[missing]"

    @staticmethod
    def _chunk_join_gloss(pieces: list[str]) -> str:
        """Join gloss parts, skipping empty ones. Returns empty string if nothing."""
        return " ".join(p.strip() for p in pieces if p.strip()).strip()

    @staticmethod
    def _literal_gloss_token(token: dict[str, str], lexicon: dict[str, str]) -> dict[str, str] | None:
        gloss = ""
        for key in BrowserWorkbench._strong_lookup_keys(token.get("strong_id", "")):
            gloss = lexicon.get(key, "")
            if gloss:
                break
        if not gloss:
            gloss = token.get("gloss", "")
        gloss = gloss.replace("<br>", "; ").replace("_", " ").strip(" ;")
        surface = BrowserWorkbench._clean_original_surface(token.get("surface", ""))
        if not gloss:
            return None
        return {"gloss": gloss, "surface": surface}

    @staticmethod
    def _strong_lookup_keys(value: str) -> list[str]:
        strong_id = str(value or "").strip()
        if not strong_id:
            return []
        keys = [strong_id]
        if strong_id.lower() not in keys:
            keys.append(strong_id.lower())
        match = re.match(r"^([HG]\d+)(?:[_-]?[A-Za-z]+)?$", strong_id)
        if match:
            base = match.group(1)
            for key in (base, strong_id[:1] + strong_id[1:].lower().replace("_", "")):
                if key and key not in keys:
                    keys.append(key)
        return keys

    @staticmethod
    def _clean_original_surface(value: str) -> str:
        return str(value or "").strip().replace("\\׃", "׃")

    def lexical_ref(self, verse: int, *, corpus: str = "") -> str:
        """Build a lexical reference key using corpus-specific book codes."""
        from ttt_core.utils import lexical_book_code
        code = lexical_book_code(self.state.book or "", corpus) if corpus else self.state.book or ""
        return f"{code}.{self.state.chapter or 0}.{verse}"

    def _fallback_verse_text(self, verse: int) -> str:
        """Get raw verse text from the Bible repo as fallback when lexical data is missing."""
        if not self.state.book or not self.state.chapter:
            return ""
        try:
            chapter_doc = self.bible_repo.load_chapter(self.state.book, self.state.chapter).doc
            verse_map = self.bible_repo.verse_map(chapter_doc)
            return verse_map.get(verse, "")
        except Exception:
            return ""

    def chunk_study_blocks(self) -> list[dict[str, Any]]:
        if not self.has_open_chunk():
            return []
        start_verse = self.state.chunk_start or 1
        end_verse = self.state.chunk_end or start_verse
        testament = self.testament()
        blocks: list[dict[str, Any]] = []
        if testament == "old":
            hebrew = self.lexical_repo.fetch_tokens(
                "hebrew_ot",
                self.state.book or "",
                self.state.chapter or 0,
                start_verse,
                end_verse,
            )
            lxx = self.lexical_repo.fetch_tokens(
                "greek_ot_lxx",
                self.state.book or "",
                self.state.chapter or 0,
                start_verse,
                end_verse,
            )

            # Collect all Strong's numbers for lexicon lookup
            heb_strongs = set()
            lxx_strongs = set()
            for verse in range(start_verse, end_verse + 1):
                for t in hebrew.get(self.lexical_ref(verse, corpus="hebrew_ot"), []):
                    if t.get("strong_id"):
                        heb_strongs.update(self._strong_lookup_keys(t["strong_id"]))
                for t in lxx.get(self.lexical_ref(verse, corpus="greek_ot_lxx"), []):
                    if t.get("strong_id"):
                        lxx_strongs.update(self._strong_lookup_keys(t["strong_id"]))

            # Look up real English from lexicon
            heb_lexicon = self.lexical_repo.fetch_lexicon_glosses("hebrew_ot", list(heb_strongs))
            lxx_lexicon = self.lexical_repo.fetch_lexicon_glosses("greek_ot_lxx", list(lxx_strongs))

            # Build Hebrew block: surface text + per-token gloss data
            heb_surface_parts = []
            heb_verse_lines: list[dict[str, Any]] = []
            heb_gloss_lines: list[dict[str, Any]] = []
            has_hebrew = False
            for verse in range(start_verse, end_verse + 1):
                tokens = hebrew.get(self.lexical_ref(verse, corpus="hebrew_ot"), [])
                surfaces = [
                    surface
                    for t in tokens
                    if (surface := self._clean_original_surface(t.get("surface", "")))
                ]
                gloss_tokens = [
                    gloss_token
                    for t in tokens
                    if (gloss_token := self._literal_gloss_token(t, heb_lexicon))
                ]
                if gloss_tokens:
                    heb_gloss_lines.append({"verse": verse, "tokens": gloss_tokens})
                verse_text = " ".join(surfaces)
                if not verse_text:
                    verse_text = self._fallback_verse_text(verse) or "[no data]"
                if verse_text and verse_text != "[no data]":
                    has_hebrew = True
                heb_surface_parts.append(verse_text)
                heb_verse_lines.append({"verse": verse, "text": verse_text})

            if has_hebrew:
                blocks.append({
                    "label": "Hebrew",
                    "caption": "Masoretic Text (WLC)",
                    "text": self._chunk_join(heb_surface_parts),
                    "verse_lines": heb_verse_lines,
                    "gloss_lines": heb_gloss_lines,
                    "kind": "hebrew",
                })

            # Build LXX block
            lxx_surface_parts = []
            lxx_verse_lines: list[dict[str, Any]] = []
            lxx_gloss_lines: list[dict[str, Any]] = []
            has_lxx = False
            for verse in range(start_verse, end_verse + 1):
                tokens = lxx.get(self.lexical_ref(verse, corpus="greek_ot_lxx"), [])
                surfaces = [t.get("surface", "").strip() for t in tokens if t.get("surface", "").strip()]
                gloss_tokens = [
                    gloss_token
                    for t in tokens
                    if (gloss_token := self._literal_gloss_token(t, lxx_lexicon))
                ]
                if gloss_tokens:
                    lxx_gloss_lines.append({"verse": verse, "tokens": gloss_tokens})
                verse_text = " ".join(surfaces) if surfaces else "[no data]"
                if verse_text != "[no data]":
                    has_lxx = True
                lxx_surface_parts.append(verse_text)
                lxx_verse_lines.append({"verse": verse, "text": verse_text})

            lxx_text = self._chunk_join(lxx_surface_parts) if has_lxx else ""
            if lxx_text and lxx_text != "[missing]":
                blocks.append({
                    "label": "LXX Greek",
                    "caption": "Septuagint (Rahlfs 1935)",
                    "text": lxx_text,
                    "verse_lines": lxx_verse_lines,
                    "gloss_lines": lxx_gloss_lines,
                    "kind": "greek",
                })
        else:
            greek = self.lexical_repo.fetch_tokens(
                "greek_nt",
                self.state.book or "",
                self.state.chapter or 0,
                start_verse,
                end_verse,
            )
            greek_strongs = set()
            for verse in range(start_verse, end_verse + 1):
                for t in greek.get(self.lexical_ref(verse, corpus="greek_nt"), []):
                    if t.get("strong_id"):
                        greek_strongs.update(self._strong_lookup_keys(t["strong_id"]))
            greek_lexicon = self.lexical_repo.fetch_lexicon_glosses("greek_nt", list(greek_strongs))

            greek_surface_parts = []
            greek_verse_lines: list[dict[str, Any]] = []
            greek_gloss_lines: list[dict[str, Any]] = []
            for verse in range(start_verse, end_verse + 1):
                tokens = greek.get(self.lexical_ref(verse, corpus="greek_nt"), [])
                surfaces = [t.get("surface", "").strip() for t in tokens if t.get("surface", "").strip()]
                gloss_tokens = [
                    gloss_token
                    for t in tokens
                    if (gloss_token := self._literal_gloss_token(t, greek_lexicon))
                ]
                if gloss_tokens:
                    greek_gloss_lines.append({"verse": verse, "tokens": gloss_tokens})
                verse_text = " ".join(surfaces) if surfaces else "[no data]"
                greek_surface_parts.append(verse_text)
                greek_verse_lines.append({"verse": verse, "text": verse_text})

            blocks.append({
                "label": "SBLGNT Greek",
                "caption": "SBL Greek New Testament",
                "text": self._chunk_join(greek_surface_parts),
                "verse_lines": greek_verse_lines,
                "gloss_lines": greek_gloss_lines,
                "kind": "greek",
            })

        translation_aliases = self.selected_sources() or ["LSB"]
        for alias in translation_aliases:
            verse_texts = []
            for verse in range(start_verse, end_verse + 1):
                verse_texts.append(self.source_repo.verse_text(
                    alias,
                    self.state.book or "",
                    self.state.chapter or 0,
                    verse,
                ).strip())
            blocks.append(
                {
                    "label": f"{alias}",
                    "caption": "",
                    "verse_texts": verse_texts,
                    "kind": "translation",
                }
            )
        return blocks

    def _primary_original_gloss_order(self, start_verse: int, end_verse: int, nlp: Any) -> dict[int, dict[str, int]]:
        corpus = "hebrew_ot" if self.testament() == "old" else "greek_nt"
        tokens_by_ref = self.lexical_repo.fetch_tokens(
            corpus,
            self.state.book or "",
            self.state.chapter or 0,
            start_verse,
            end_verse,
        )
        strongs: set[str] = set()
        for verse in range(start_verse, end_verse + 1):
            for token in tokens_by_ref.get(self.lexical_ref(verse, corpus=corpus), []):
                if token.get("strong_id"):
                    strongs.update(self._strong_lookup_keys(token["strong_id"]))
        lexicon = self.lexical_repo.fetch_lexicon_glosses(corpus, list(strongs))
        order_by_verse: dict[int, dict[str, int]] = {}
        for verse in range(start_verse, end_verse + 1):
            glosses: list[str] = []
            for token in tokens_by_ref.get(self.lexical_ref(verse, corpus=corpus), []):
                gloss_token = self._literal_gloss_token(token, lexicon)
                if gloss_token:
                    glosses.append(gloss_token["gloss"])
            order_by_verse[verse] = glossary_word_order(glosses, nlp)
        return order_by_verse

    def chunk_translation_word_analysis(self) -> dict[str, Any]:
        if not self.has_open_chunk() or not self.state.book or not self.state.chapter:
            return {"available": False, "message": "Open a chunk to analyze translation word choices.", "verses": []}
        nlp, error = load_spacy_model()
        if error or nlp is None:
            return {"available": False, "message": error, "verses": []}

        start_verse = self.state.chunk_start or 1
        end_verse = self.state.chunk_end or start_verse
        aliases = self.selected_sources() or ["LSB"]
        original_order_by_verse = self._primary_original_gloss_order(start_verse, end_verse, nlp)
        verses: list[dict[str, Any]] = []
        for verse in range(start_verse, end_verse + 1):
            translations: list[dict[str, Any]] = []
            for alias in aliases:
                text = self.source_repo.verse_text(
                    alias, self.state.book, self.state.chapter, verse
                ).strip()
                translations.append(
                    {
                        "alias": alias,
                        "text": text,
                        "words": important_words(text, nlp),
                        "word_positions": important_word_positions(text, nlp),
                    }
                )
            stats = verse_word_stats(translations, nlp, original_order_by_verse.get(verse, {}))
            verses.append(
                {
                    "verse": verse,
                    "translations": translations,
                    "word_choices": stats["word_choices"],
                    "word_groups": stats["word_groups"],
                }
            )
        return {
            "available": True,
            "model": "en_core_web_sm",
            "selected_count": len(aliases),
            "verses": verses,
        }

    def current_chunk_summary(self) -> dict[str, Any]:
        chunks = self.chapter_chunks(
            self.state.wizard_testament or self.testament() or "new",
            self.state.book or "",
            self.state.chapter or 0,
        )
        current_key = self.current_chunk_key()
        current_chunk = None
        for chunk in chunks:
            if f"{chunk.start_verse}-{chunk.end_verse}" == current_key:
                current_chunk = chunk
                break
        return {
            "chunk": current_chunk,
            "range_label": f"{self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}"
            if self.state.book and self.state.chapter and self.state.chunk_start and self.state.chunk_end
            else f"{self.state.book} {self.state.chapter}"
            if self.state.book and self.state.chapter
            else "No chunk selected",
        }

    def _current_chunk_bounds(self) -> tuple[int, int] | None:
        if not self.has_open_chunk():
            return None
        start = self.state.chunk_start or 1
        end = self.state.chunk_end or start
        return start, end

    @staticmethod
    def _format_verse_label(verses: list[int]) -> str:
        if not verses:
            return "?"
        if len(verses) == 1:
            return str(verses[0])
        if verses == list(range(verses[0], verses[-1] + 1)):
            return f"{verses[0]}-{verses[-1]}"
        return ", ".join(str(verse) for verse in verses)

    def chunk_justification_entries(self) -> list[dict[str, Any]]:
        bounds = self._current_chunk_bounds()
        if not bounds or not self.state.book or not self.state.chapter:
            return []
        start, end = bounds
        just_file = self.just_repo.load_document(self.state.book, self.state.chapter)
        merged: dict[str, dict[str, Any]] = {}

        def include(raw_entry: dict[str, Any], status: str) -> None:
            if raw_entry.get("_delete"):
                entry_id = str(raw_entry.get("id", "")).strip()
                if entry_id:
                    merged.pop(entry_id, None)
                return
            verses = sorted(
                {
                    int(item)
                    for item in raw_entry.get("verses", [])
                    if str(item).strip().isdigit()
                }
            )
            if not verses or verses[-1] < start or verses[0] > end:
                return
            entry_id = str(raw_entry.get("id") or f"{verses[0]}-{verses[-1]}")
            source_term = self.inline_markup_payload(raw_entry.get("source_term", ""))
            decision = self.inline_markup_payload(raw_entry.get("decision", ""))
            reason = self.inline_markup_payload(raw_entry.get("reason", ""))
            merged[entry_id] = {
                "id": entry_id,
                "verses": verses,
                "verse_label": self._format_verse_label(verses),
                "verse_spec": ", ".join(str(verse) for verse in verses),
                "source_term": source_term["raw"].strip(),
                "source_term_html": source_term["html"],
                "source_term_text": source_term["text"],
                "decision": decision["raw"].strip(),
                "decision_html": decision["html"],
                "decision_text": decision["text"],
                "reason": reason["raw"].strip(),
                "reason_html": reason["html"],
                "reason_text": reason["text"],
                "status": status,
            }

        for entry in just_file.doc.get("justifications", []):
            if isinstance(entry, dict):
                include(entry, "Saved")
        for pending in self.state.pending_justification_updates:
            if pending.book == self.state.book and pending.chapter == self.state.chapter:
                include(pending.entry, "Pending")

        return sorted(
            merged.values(),
            key=lambda item: (
                item["verses"][0] if item["verses"] else 10**9,
                item["id"],
            ),
        )

    def chunk_footnote_entries(self) -> list[dict[str, Any]]:
        bounds = self._current_chunk_bounds()
        if not bounds or not self.state.book or not self.state.chapter:
            return []
        start, end = bounds
        chapter_doc = self.bible_repo.load_chapter(self.state.book, self.state.chapter).doc
        merged: dict[tuple[int, str], dict[str, Any]] = {}

        def include(raw_entry: dict[str, Any], status: str) -> None:
            try:
                verse = int(raw_entry.get("verse", 0))
            except (TypeError, ValueError):
                return
            letter = str(raw_entry.get("letter", "")).strip()
            key = (verse, letter)
            if raw_entry.get("_delete"):
                merged.pop(key, None)
                return
            if verse < start or verse > end:
                return
            content = str(raw_entry.get("content", "")).strip()
            if not content:
                return
            content_markup = self.inline_markup_payload(content)
            merged[key] = {
                "verse": verse,
                "letter": letter,
                "verse_label": f"{verse}{letter}" if letter else str(verse),
                "content": content,
                "content_html": content_markup["html"],
                "content_text": content_markup["text"],
                "status": status,
            }

        for entry in chapter_doc.get("footnotes", []):
            if isinstance(entry, dict):
                include(entry, "Saved")
        for pending in self.state.pending_footnote_updates:
            if pending.book == self.state.book and pending.chapter == self.state.chapter:
                include(pending.entry, "Pending")

        return sorted(
            merged.values(),
            key=lambda item: (item["verse"], item["letter"]),
        )

    def study_provenance(self) -> list[dict[str, str]]:
        testament = self.state.wizard_testament or self.testament() or "new"
        if testament == "old":
            return [
                {
                    "label": "OT primary witness",
                    "value": "WLC Hebrew",
                    "note": "Westminster Leningrad Codex, shown through the offline lexical index.",
                },
                {
                    "label": "OT lexical literal aid",
                    "value": "STEPBible Hebrew tagged data + TBESH lexicon",
                    "note": "Gloss-based lexical aid, not probability-ranked.",
                },
                {
                    "label": "OT Greek comparison",
                    "value": "LXX Rahlfs 1935 / Marvel.Bible",
                    "note": "Used as a comparison witness where available.",
                },
                {
                    "label": "LXX literal aid",
                    "value": "Marvel.Bible gloss data",
                    "note": "Gloss-based token line for the LXX comparison text.",
                },
            ]
        return [
            {
                "label": "NT primary witness",
                "value": "SBLGNT Greek",
                "note": "Primary original-language NT witness in the current workflow.",
            },
            {
                "label": "NT lexical literal aid",
                "value": "STEPBible Greek tagged data + TBESG lexicon",
                "note": "Gloss-based lexical aid, not probability-ranked.",
            },
        ]

    def pending_commit_writes(self) -> list[tuple[Path, str, str, list[str]]]:
        return self.build_commit_plan()

    def current_editor_range(self) -> tuple[int, int]:
        if not self.has_open_chunk():
            return (1, 1)
        chunk_start = self.state.chunk_start or 1
        chunk_end = self.state.chunk_end or chunk_start
        start = self.state.focus_start or chunk_start
        end = self.state.focus_end or chunk_end
        start = max(chunk_start, min(start, chunk_end))
        end = max(start, min(end, chunk_end))
        return start, end

    def set_editor_range(self, start: int, end: int) -> tuple[int, int]:
        if not self.has_open_chunk():
            return (1, 1)
        chunk_start = self.state.chunk_start or 1
        chunk_end = self.state.chunk_end or chunk_start
        start = max(chunk_start, min(start, chunk_end))
        end = max(start, min(end, chunk_end))
        self.state.focus_start = start
        self.state.focus_end = end
        return start, end

    def editor_range_options(self) -> list[int]:
        if not self.has_open_chunk():
            return []
        return list(range((self.state.chunk_start or 1), (self.state.chunk_end or 1) + 1))

    def draft_editor_verses(self) -> list[dict[str, Any]]:
        """Return draft-only text for the current chunk."""
        if not self.has_open_chunk():
            return []
        start = self.state.chunk_start or 1
        end = self.state.chunk_end or start
        verses = []
        for verse in range(start, end + 1):
            text = self.state.draft_chunk.get(str(verse), "")
            verses.append({"verse": verse, "text": (text or "").rstrip()})
        return verses

    def review_editor_verses(self) -> list[dict[str, Any]]:
        if not self.has_open_chunk():
            return []
        chapter_map = self.chapter_verse_map()
        start = self.state.chunk_start or 1
        end = self.state.chunk_end or start
        verses = []
        for verse in range(start, end + 1):
            committed = chapter_map.get(verse, "")
            key = str(verse)
            draft_text = self.state.draft_chunk.get(key, "")
            changed = key in self.state.draft_chunk and draft_text.strip() != committed.strip()
            verses.append(
                {
                    "verse": verse,
                    "text": (committed or "").rstrip(),
                    "committed": committed.rstrip(),
                    "draft_text": (draft_text or "").rstrip(),
                    "changed": changed,
                }
            )
        return verses

    def editor_title(self, mode: str | None = None) -> str:
        current_mode = mode or self.editor_mode()
        if current_mode == "review":
            return self.committed_chunk_title()
        return self.state.draft_title

    def parse_range_draft(self, start: int, end: int, raw_text: str) -> dict[int, str]:
        chapter_map = self.chapter_verse_map()
        if start > end:
            return {}
        if not raw_text.strip():
            return {verse: "" for verse in range(start, end + 1)}

        # Try to detect verse-numbered lines first
        matches = list(self._editor_line_re.finditer(raw_text))
        if matches and len(matches) >= (end - start + 1):
            parsed: dict[int, str] = {}
            for index, match in enumerate(matches):
                verse = int(match.group(1))
                text_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
                if start <= verse <= end:
                    parsed[verse] = raw_text[match.end():text_end].strip()
            if parsed:
                return {
                    verse: parsed.get(
                        verse,
                        self.state.draft_chunk.get(str(verse), chapter_map.get(verse, "")).strip(),
                    )
                    for verse in range(start, end + 1)
                }

        # Fall back: split by double-newline and assign to verses in order
        blocks = [block.strip() for block in re.split(r"\n\s*\n", raw_text.strip()) if block.strip()]
        verse_count = end - start + 1
        if len(blocks) == verse_count:
            return {start + offset: block for offset, block in enumerate(blocks)}
        if verse_count == 1:
            return {start: raw_text.strip()}
        # If block count doesn't match, just assign everything to the first verse
        return {start: raw_text.strip(), **{v: "" for v in range(start + 1, end + 1)}}

    def save_range_draft(self, title: str, start: int, end: int, raw_text: str) -> None:
        self.state.draft_title = title.strip()
        parsed = self.parse_range_draft(start, end, raw_text)
        for verse, text in parsed.items():
            self.state.draft_chunk[str(verse)] = text.strip()
        self.prepare_browser_commit_state()
        self.save_state()

    def chapter_verse_map(self) -> dict[int, str]:
        if not self.state.book or not self.state.chapter:
            return {}
        chapter_doc = self.bible_repo.load_chapter(self.state.book, self.state.chapter).doc
        return self.bible_repo.verse_map(chapter_doc)

    def display_draft_verses(self) -> list[dict[str, Any]]:
        if not self.has_open_chunk():
            return []
        chapter_map = self.chapter_verse_map()
        verses: list[dict[str, Any]] = []
        for verse in range((self.state.chunk_start or 1), (self.state.chunk_end or 1) + 1):
            draft = self.state.draft_chunk.get(str(verse), "")
            committed = chapter_map.get(verse, "")
            changed = draft != committed if str(verse) in self.state.draft_chunk else False
            verses.append(
                {
                    "verse": verse,
                    "draft": draft,
                    "committed": committed,
                    "state": "Changed" if changed else "Committed",
                }
            )
        return verses

    def editor_client_payload(self) -> list[dict[str, Any]]:
        return self.display_draft_verses()

    def source_text_preview(self) -> list[dict[str, Any]]:
        if not self.has_open_chunk():
            return []
        alias = "LSB" if self.testament() == "old" else "LSB"
        items: list[dict[str, Any]] = []
        for verse in range((self.state.chunk_start or 1), (self.state.chunk_end or 1) + 1):
            items.append(
                {
                    "verse": verse,
                    "text": self.source_repo.verse_text(
                        alias, self.state.book or "", self.state.chapter or 0, verse
                    ),
                }
            )
        return items

    def comparison_sources(self) -> list[str]:
        return [
            alias
            for alias in self.source_repo.list_sources()
            if alias not in ORIGINAL_LANGUAGE_SOURCES
        ]

    def preferred_python(self) -> Path:
        candidate = self.paths.repo_root / ".venv" / "bin" / "python"
        if candidate.exists():
            return candidate
        return Path(sys.executable)

    def safe_list_models(self) -> list[str]:
        return self.refresh_model_cache(force=True)

    def cached_model_names(self, provider: str | None = None) -> list[str]:
        provider_key = (provider or str(self.web_settings.get("endpoint_provider", "local"))).strip().lower()
        if provider_key not in {"local", "cloud"}:
            provider_key = "local"
        cache = self.web_settings.get("model_cache", {})
        if not isinstance(cache, dict):
            cache = {}
        values = cache.get(provider_key, [])
        if not isinstance(values, list):
            values = []
        clean = [str(model).strip() for model in values if str(model).strip()]
        current = str(
            self.web_settings.get("cloud_model" if provider_key == "cloud" else "local_model", "")
        ).strip()
        if current and current not in clean:
            clean.insert(0, current)
        return clean

    def refresh_model_cache(self, force: bool = False) -> list[str]:
        provider = str(self.web_settings.get("endpoint_provider", "local")).strip().lower()
        if provider not in {"local", "cloud"}:
            provider = "local"
        if not force:
            cached = self.cached_model_names(provider)
            if cached:
                return cached
        self.refresh_active_endpoint()
        try:
            models = self.llm.list_models()
        except Exception as exc:
            self.print_error(f"Model discovery failed: {exc}")
            return self.cached_model_names(provider) or [self.model_name]
        clean = [str(model).strip() for model in models if str(model).strip()]
        if clean:
            active = self.active_model_name()
            if provider == "cloud" and active and active not in clean:
                clean.insert(0, active)
            cache = self.web_settings.get("model_cache", {})
            if not isinstance(cache, dict):
                cache = {}
            cache[provider] = clean
            self.web_settings["model_cache"] = cache
            discovered = next((model for model in clean if model != "llama.cpp-model"), clean[0])
            if discovered:
                self.model_name = (
                    active
                    if provider == "cloud" and active and active != "llama.cpp-model"
                    else discovered
                )
                self.model_label = self.compact_model_name(self.model_name)
                if hasattr(self.llm, "model_name"):
                    self.llm.model_name = self.model_name
                if provider == "local" and discovered != "llama.cpp-model":
                    self.web_settings["local_model"] = discovered
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(json.dumps(self.web_settings, indent=2), encoding="utf-8")
            return clean
        return self.cached_model_names(provider) or [self.model_name]

    def commit_history_entries(self) -> list[dict[str, str | bool]]:
        entries: list[dict[str, str | bool]] = []
        valid_paths: list[Path] = []
        for raw_path in reversed(self.state.undo_stack[-12:]):
            path = Path(raw_path)
            if not path.exists() or self._looks_like_fake_snapshot(path):
                continue
            valid_paths.append(path)
        for index, path in enumerate(valid_paths):
            entries.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "latest": index == 0,
                }
            )
        return entries

    def prepare_browser_commit_state(self) -> None:
        if not self.has_open_chunk():
            self.state.pending_verse_updates = []
            self.state.pending_title_updates = []
            return
        self.sync_current_chunk_for_commit()

    def explain_llm_failure(self, raw_error: str) -> str:
        text = raw_error.strip()
        if "nodename nor servname provided" in text or "Name or service not known" in text:
            return (
                f"Model request failed because the configured endpoint `{self.llm.base_url}` "
                "could not be reached. Check Settings and confirm the llama.cpp server is running."
            )
        if "timed out" in text:
            return (
                f"Model request to `{self.llm.base_url}` timed out. "
                "Check that the llama.cpp server is running and responsive."
            )
        return f"Model request failed at `{self.llm.base_url}`. Check Settings and the llama.cpp server."

    def session_context_snapshot(self) -> str:
        blocks = self.chunk_study_blocks()
        lines = [
            f"Chunk session context for {self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}",
        ]
        for block in blocks:
            lines.append(f"{block['label']} ({block['caption']}):")
            block_text = str(block.get("text", "")).strip()
            if not block_text and block.get("verse_texts"):
                block_text = "\n".join(
                    str(item).strip() or "[blank]" for item in block.get("verse_texts", [])
                ).strip()
            lines.append(block_text or "[blank]")
            gloss_lines = block.get("gloss_lines") or []
            if gloss_lines:
                for gloss_line in gloss_lines:
                    gloss_text = " / ".join(
                        str(item.get("gloss", "")).strip()
                        for item in gloss_line.get("tokens", [])
                        if str(item.get("gloss", "")).strip()
                    )
                    if gloss_text:
                        lines.append(f"  {gloss_line.get('verse')}. Literal gloss: {gloss_text}")
            lines.append("")
        return "\n".join(lines).strip()

    def original_language_chat_context_snapshot(self) -> str:
        blocks = [
            block
            for block in self.chunk_study_blocks()
            if str(block.get("kind", "")).strip().lower() in {"hebrew", "greek"}
        ]
        if not blocks:
            return "None."
        lines = ["Original-language context for the current chunk:"]
        for block in blocks:
            label = str(block.get("label", "")).strip() or "Source"
            caption = str(block.get("caption", "")).strip()
            lines.append(f"{label}{f' ({caption})' if caption else ''}:")
            lines.append(str(block.get("text", "")).strip() or "[blank]")
            gloss_lines = block.get("gloss_lines") or []
            for gloss_line in gloss_lines:
                gloss_preview = ", ".join(
                    f"{str(item.get('surface', '')).strip()}={str(item.get('gloss', '')).strip()}"
                    for item in gloss_line.get("tokens", [])[:20]
                    if str(item.get("surface", "")).strip() and str(item.get("gloss", "")).strip()
                )
                if gloss_preview:
                    lines.append(f"Gloss aid {gloss_line.get('verse')}: {gloss_preview}")
            lines.append("")
        return "\n".join(lines).strip()

    def selected_range_draft_text(self) -> str:
        """Return the full draft text for ALL verses in the current chunk."""
        if not self.has_open_chunk():
            return "[blank]"
        start = self.state.chunk_start or 1
        end = self.state.chunk_end or start
        chapter_map = self.chapter_verse_map()
        blocks = [
            self.state.draft_chunk.get(str(verse), chapter_map.get(verse, "")).strip()
            for verse in range(start, end + 1)
        ]
        return "\n\n".join(blocks).strip() or "[blank]"

    def build_browser_chat_prompt(self, user_message: str) -> str:
        return str(user_message or "").strip()

    def browser_auto_generate_draft(self) -> bool:
        self.refresh_active_endpoint()
        payload, response, _attempts = self.llm.complete_json(
            self.build_initial_draft_prompt(),
            required_keys=["reply", "title", "verses"],
            temperature=0.7,
            max_tokens=None,
            max_attempts=3,
        )
        if not isinstance(payload, dict):
            if str(response).startswith("[ERROR]"):
                self.print_error(self.explain_llm_failure(str(response)))
            else:
                self.print_error("The endpoint did not return a valid initial draft JSON response.")
            return False
        for verse in payload.get("verses", []):
            try:
                self.state.draft_chunk[str(int(verse["verse"]))] = verse["text"].strip()
            except Exception:
                continue
        self.state.draft_title = payload.get("title", "").strip()
        self.state.title_alternatives = [
            item for item in payload.get("title_alternatives", []) if isinstance(item, str)
        ]
        reply = str(payload.get("reply", "")).strip()
        if reply:
            self.state.chat_messages.append({"role": "assistant", "content": reply})
        session = self.current_chunk_session()
        session["context_loaded"] = True
        session["context_snapshot"] = self.session_context_snapshot()
        self.persist_current_chunk_session()
        return True

    def browser_chat_turn(self, user_message: str) -> None:
        if not self.require_open_chunk():
            return
        if not self.state.draft_chunk and not self.state.chat_messages and self.chunk_has_committed_text():
            self.notify("Review text is committed. Use Revise in Draft before chatting.")
            return
        if not self.state.draft_chunk and not self.state.chat_messages:
            if not self.browser_auto_generate_draft():
                return
        prompt = self.build_browser_chat_prompt(user_message)
        self.refresh_active_endpoint()
        response = self.llm.complete(
            prompt,
            temperature=0.7,
            max_tokens=None,
        )
        self.state.chat_messages.append({"role": "user", "content": user_message})
        if str(response).startswith("[ERROR]"):
            self.history_entries.append(
                {"title": "Chat error", "body": str(response)[:160], "accent": "red"}
            )
            self.print_error(self.explain_llm_failure(str(response)))
            return
        reply = str(response).strip()
        if reply:
            self.state.chat_messages.append({"role": "assistant", "content": reply})
            self.history_entries.append(
                {"title": "Chat", "body": reply[:160], "accent": "blue"}
            )
        session = self.current_chunk_session()
        session["context_loaded"] = True
        if not session.get("context_snapshot"):
            session["context_snapshot"] = self.session_context_snapshot()
        self.persist_current_chunk_session()
        self.prepare_browser_commit_state()
        self.save_state()

    def sync_current_chunk_for_commit(self) -> None:
        if not self.has_open_chunk() or not self.state.book or not self.state.chapter:
            return
        book = self.state.book
        chapter = self.state.chapter
        start_verse = self.state.chunk_start or 1
        end_verse = self.state.chunk_end or start_verse

        self.state.pending_verse_updates = [
            item
            for item in self.state.pending_verse_updates
            if (
                item.book != book
                or item.chapter != chapter
                or item.end_verse < start_verse
                or item.start_verse > end_verse
            )
        ]
        self.state.pending_title_updates = [
            item
            for item in self.state.pending_title_updates
            if (
                item.book != book
                or item.chapter != chapter
                or item.end_verse < start_verse
                or item.start_verse > end_verse
            )
        ]

        chapter_map = self.chapter_verse_map()
        changed_verses: dict[str, str] = {}
        for verse in range(start_verse, end_verse + 1):
            key = str(verse)
            if key not in self.state.draft_chunk:
                continue
            draft_text = self.state.draft_chunk.get(key, "")
            committed_text = chapter_map.get(verse, "")
            if draft_text != committed_text:
                changed_verses[key] = draft_text
        if changed_verses:
            verse_numbers = sorted(int(key) for key in changed_verses)
            self.state.pending_verse_updates.append(
                PendingVerseUpdate(
                    book=book,
                    chapter=chapter,
                    verses=changed_verses,
                    start_verse=verse_numbers[0],
                    end_verse=verse_numbers[-1],
                )
            )

        draft_title = self.state.draft_title.strip()
        if not draft_title:
            return
        try:
            chapter_doc = self.current_chapter()
            section_index = self.bible_repo.title_section_index(
                chapter_doc,
                start_verse,
                end_verse,
            )
        except ValueError:
            return
        current_title = str(
            chapter_doc.get("sections", [{}])[section_index].get("headline", "")
        ).strip()
        if draft_title == current_title:
            return
        self.state.pending_title_updates.append(
            PendingTitleUpdate(
                book=book,
                chapter=chapter,
                start_verse=start_verse,
                end_verse=end_verse,
                title=draft_title,
            )
        )

    def rollback_latest_commit(self) -> str:
        while self.state.undo_stack:
            snapshot = Path(self.state.undo_stack.pop())
            if snapshot.exists() and not self._looks_like_fake_snapshot(snapshot):
                restored = restore_backup_set(snapshot)
                self.notify("Rolled back files:\n" + "\n".join(restored))
                return snapshot.name
        raise ValueError("No rollback snapshot is available yet.")

    def recent_epubs(self) -> list[Path]:
        return sorted(
            (self.paths.output_dir / "builds").glob("*.epub"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:5]

    def generate_epub_and_return_latest(self) -> tuple[bool, str, Path | None]:
        """Generate EPUB and return (success, message, latest_epub_path)."""
        work_dir = self.paths.repo_root
        cmd = [
            str(self.preferred_python()),
            str(self.paths.repo_root / "src" / "ttt_epub" / "generate_epub.py"),
            "--md",
            "--txt",
        ]
        try:
            result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, check=False)
        except Exception as exc:
            return False, f"EPUB generation failed to start: {exc}", None
        if result.returncode == 0:
            latest = self.recent_epubs()
            latest_path = latest[0] if latest else None
            return True, "EPUB generated successfully.", latest_path
        return False, f"EPUB generation failed with exit code {result.returncode}.\n{result.stderr}", None

    def chunk_session_list(self) -> list[dict[str, Any]]:
        """Return a list of all saved chunk sessions with metadata."""
        sessions: list[dict[str, Any]] = []
        for key, session in self.chunk_sessions.items():
            parts = key.split("|")
            if len(parts) in {4, 5}:
                testament_name, book_key, chapter_num, chunk_range = parts[:4]
                internal_id = parts[4] if len(parts) == 5 else ""
                sessions_map = session.get("sessions") if isinstance(session.get("sessions"), dict) else {}
                active_id = str(session.get("active_session_id", ""))
                if sessions_map:
                    message_count = sum(
                        len(item.get("messages", []))
                        for item in sessions_map.values()
                        if isinstance(item, dict)
                    )
                    chat_count = len(sessions_map)
                    context_loaded = any(
                        bool(item.get("context_loaded"))
                        for item in sessions_map.values()
                        if isinstance(item, dict)
                    )
                else:
                    message_count = len(session.get("messages", []))
                    chat_count = 1 if message_count else 0
                    context_loaded = session.get("context_loaded", False)
                book_display = book_key.replace("_", " ").title()
                sessions.append({
                    "session_key": key,
                    "chunk_internal_id": internal_id,
                    "active_session_id": active_id,
                    "testament": testament_name,
                    "book": book_display,
                    "chapter": int(chapter_num),
                    "chunk_range": chunk_range,
                    "message_count": message_count,
                    "chat_count": chat_count,
                    "context_loaded": context_loaded,
                })
        return sessions

    def current_chunk_chat_sessions(self) -> list[dict[str, Any]]:
        key = self.chunk_session_key()
        if not key:
            return []
        self.current_chunk_session()
        record = self.chunk_sessions.get(key, {})
        active_id = str(record.get("active_session_id", ""))
        sessions = record.get("sessions", {})
        if not isinstance(sessions, dict):
            return []
        items: list[dict[str, Any]] = []
        for index, (session_id, session) in enumerate(sessions.items(), start=1):
            if not isinstance(session, dict):
                continue
            title = str(session.get("title") or "")
            if not title or re.fullmatch(r"Chat\s+\d+", title):
                title = self.chunk_chat_session_title(index)
            items.append(
                {
                    "id": session_id,
                    "title": title,
                    "message_count": len(session.get("messages", [])),
                    "is_active": session_id == active_id,
                }
            )
        return items

    def workspace_payload(self, active_tab: str = "study") -> dict[str, Any]:
        testament = self.state.wizard_testament or self.testament() or "new"
        book = self.state.book or self.state.wizard_book or ""
        chapter = self.state.chapter or self.state.wizard_chapter or 0
        chunk_open = self.has_open_chunk()
        
        # Ensure editor state machine is synchronized
        if chunk_open:
            self.prepare_browser_commit_state()
            self.sync_editor_mode()
        
        editor_mode = self.state.browser_editor_mode or "draft"
        editor_start, editor_end = self.current_editor_range() if chunk_open else (0, 0)
        model_names = self.safe_list_models() if chunk_open else []
        return {
            "show_workspace_topbar": bool(book and chapter),
            "navigator": self.navigator_catalog(),
            "state": self.state,
            "selected_testament": testament,
            "selected_book": book,
            "selected_chapter": chapter,
            "chapter_chunks": self.chapter_chunks(testament, book, chapter) if book and chapter else [],
            "chunk_summary": self.current_chunk_summary(),
            "study_cards": self.build_study_cards() if chunk_open else [],
            "study_blocks": self.chunk_study_blocks() if chunk_open else [],
            "translation_word_analysis": self.chunk_translation_word_analysis() if chunk_open else None,
            "draft_verses": self.display_draft_verses() if chunk_open else [],
            "source_preview": self.source_text_preview() if chunk_open else [],
            "study_provenance": self.study_provenance(),
            "review_lines": self.review_summary_card() if self.state.last_review else [],
            "pending_writes": self.pending_commit_writes(),
            "active_tab": active_tab,
            "flash_messages": self._dedup_flash_messages(),
            "history_entries": list(self.history_entries[-8:]),
            "activity_items": self._dedup_activity_items(),
            "jobs": [
                {
                    "id": job.job_id,
                    "label": job.label,
                    "status": job.status.value,
                    "elapsed": job.elapsed_display,
                }
                for job in self.job_runner.all_jobs()
            ],
            "current_chunk_key": self.current_chunk_key() or "",
            "current_chunk_internal_id": self.current_chunk_internal_id() if chunk_open else "",
            "comparison_sources": self.comparison_sources(),
            "comparison_source_options": self.comparison_source_options(),
            "selected_sources": self.selected_sources(),
            "chat_context_sources": self.chat_context_sources(),
            "commit_history": self.commit_history_entries(),
            "model_label": self.model_label,
            "active_provider_label": self.active_provider_label(),
            "active_model_name": self.active_model_name(),
            "model_names": model_names,
            "settings_config": self.settings_payload(),
            "editor_range_start": editor_start,
            "editor_range_end": editor_end,
            "editor_range_options": self.editor_range_options() if chunk_open else [],
            "draft_editor_verses": self.draft_editor_verses() if chunk_open else [],
            "review_editor_verses": self.review_editor_verses() if chunk_open else [],
            "editor_mode": editor_mode,
            "editor_title": self.editor_title(editor_mode) if chunk_open else "",
            "committed_title": self.committed_chunk_title() if chunk_open else "",
            "has_draft_work": self.has_draft_work() if chunk_open else False,
            "has_committed_text": self.chunk_has_committed_text() if chunk_open else False,
            "chunk_sessions": self.chunk_session_list(),
            "current_chat_sessions": self.current_chunk_chat_sessions() if chunk_open else [],
            "active_chat_session_id": self.active_chat_session_id() if chunk_open else "",
            "justification_entries": self.chunk_justification_entries() if chunk_open else [],
            "footnote_entries": self.chunk_footnote_entries() if chunk_open else [],
            "editorial_prompts": self.editorial_prompts(),
            "editorial_input": self.state.editorial_input,
            "editorial_output": self.state.editorial_output,
            "editorial_output_label": self.state.editorial_output_label,
        }

    def _panel_base_payload(self, *, active_tab: str = "draft") -> dict[str, Any]:
        testament = self.state.wizard_testament or self.testament() or "new"
        book = self.state.book or self.state.wizard_book or ""
        chapter = self.state.chapter or self.state.wizard_chapter or 0
        return {
            "show_workspace_topbar": bool(book and chapter),
            "state": self.state,
            "selected_testament": testament,
            "selected_book": book,
            "selected_chapter": chapter,
            "active_tab": active_tab,
            "current_chunk_key": self.current_chunk_key() or "",
            "settings_config": self.settings_payload(),
        }

    def chat_panel_payload(self) -> dict[str, Any]:
        payload = self._panel_base_payload(active_tab="draft")
        chunk_open = self.has_open_chunk()
        payload.update(
            {
                "active_provider_label": self.active_provider_label(),
                "active_model_name": self.active_model_name(),
                "current_chat_sessions": self.current_chunk_chat_sessions() if chunk_open else [],
                "active_chat_session_id": self.active_chat_session_id() if chunk_open else "",
            }
        )
        return payload

    def editor_panel_payload(self) -> dict[str, Any]:
        payload = self._panel_base_payload(active_tab="draft")
        chunk_open = self.has_open_chunk()
        if chunk_open:
            self.prepare_browser_commit_state()
            self.sync_editor_mode()
        editor_mode = self.state.browser_editor_mode or "draft"
        editor_start, editor_end = self.current_editor_range() if chunk_open else (0, 0)
        payload.update(
            {
                "chunk_summary": self.current_chunk_summary(),
                "editor_range_start": editor_start,
                "editor_range_end": editor_end,
                "draft_editor_verses": self.draft_editor_verses() if chunk_open else [],
                "review_editor_verses": self.review_editor_verses() if chunk_open else [],
                "editor_mode": editor_mode,
                "editor_title": self.editor_title(editor_mode) if chunk_open else "",
            }
        )
        return payload

    def context_panel_payload(self) -> dict[str, Any]:
        payload = self._panel_base_payload(active_tab="study")
        chunk_open = self.has_open_chunk()
        payload.update(
            {
                "comparison_source_options": self.comparison_source_options(),
                "study_blocks": self.chunk_study_blocks() if chunk_open else [],
                "translation_word_analysis": self.chunk_translation_word_analysis() if chunk_open else None,
            }
        )
        return payload

    def json_preview_payload(self) -> dict[str, Any]:
        """Return the committed JSON as it would appear in the output file."""
        if not self.has_open_chunk() or not self.state.book or not self.state.chapter:
            return {"error": "No chunk open"}
        book = self.state.book
        chapter = self.state.chapter
        start = self.state.chunk_start or 1
        end = self.state.chunk_end or start
        chapter_map = self.chapter_verse_map()

        verses = {}
        for verse in range(start, end + 1):
            draft = self.state.draft_chunk.get(str(verse), "")
            committed = chapter_map.get(verse, "")
            verses[str(verse)] = draft or committed

        return {
            "book": book,
            "chapter": chapter,
            "chunk": f"{start}-{end}",
            "title": self.state.draft_title or self.committed_chunk_title(),
            "verses": verses,
        }

    def save_draft(self, title: str, verses: dict[int, str], *, editor_mode: str | None = None) -> None:
        mode = (editor_mode or self.editor_mode()).lower()
        if mode == "review":
            self.history_entries.append(
                {"title": "Review is read-only", "body": "Start a revision before editing committed text.", "accent": "muted"}
            )
            return
        verse_count = len(verses)
        changed = False
        old_title = self.state.draft_title
        self.state.draft_title = title.strip()
        if self.state.draft_title != old_title:
            changed = True
        for verse, text in verses.items():
            key = str(verse)
            old = self.state.draft_chunk.get(key, "")
            if text.strip() != old:
                self.state.draft_chunk[key] = text.strip()
                changed = True
        if changed:
            self.history_entries.append(
                {"title": "Draft saved", "body": f"{verse_count} verse{'s' if verse_count != 1 else ''} saved for {self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}", "accent": "green"}
            )
        else:
            self.history_entries.append(
                {"title": "No changes", "body": f"No new changes to save in {self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}.", "accent": "muted"}
            )
        self.prepare_browser_commit_state()
        self.save_state()

    def clear_current_draft_after_commit(self) -> None:
        if not self.has_open_chunk():
            return
        start = self.state.chunk_start or 1
        end = self.state.chunk_end or start
        for verse in range(start, end + 1):
            self.state.draft_chunk.pop(str(verse), None)
        self.state.draft_title = ""
        self.state.browser_editor_state = "committed"
        self.state.browser_editor_mode = "review"
        self.prepare_browser_commit_state()
        self.save_state()

    def open_or_select_chunk(
        self,
        testament: str,
        book: str,
        chapter: int,
        chunk_key: str,
        *,
        announce: bool = True,
    ) -> None:
        current_book = self.state.book or ""
        current_chunk_key = self.current_chunk_key()
        same_chunk = (
            normalize_book_key(current_book) == normalize_book_key(book)
            and self.state.chapter == chapter
            and current_chunk_key == chunk_key
        )
        if same_chunk:
            self.state.wizard_testament = testament
            self.state.wizard_book = book
            self.state.wizard_chapter = chapter
            # Still refresh the visible title without treating committed text as draft work.
            if not self.state.draft_title.strip():
                self.state.draft_title = self.committed_chunk_title()
                if not self.state.draft_title.strip():
                    self.state.draft_title = self._chunk_catalog_title(book, chapter, chunk_key)
            return

        self.load_workspace(testament, book, chapter, chunk_key)
        self.sync_editor_mode(force_default=True)
        self.save_state()
        # Browser UI shows chunk in banner — skip terminal-style announcement
        return

    def emit_chunk_opened(self, *args, **kwargs) -> None:
        """Suppress terminal-style chunk-opened announcements in the browser."""
        pass

    def merge_chapter_chunks(
        self,
        testament: str,
        book: str,
        chapter: int,
        *,
        start_index: int,
        end_index: int,
        title: str,
        chunk_type: str = "",
        reason: str = "",
    ) -> str:
        merged = self.chunk_catalog_repo.merge_consecutive_chunks(
            testament,
            book,
            chapter,
            start_index=start_index,
            end_index=end_index,
            title=title,
            chunk_type=chunk_type,
            reason=reason,
        )
        merged_key = f"{merged['start_verse']}-{merged['end_verse']}"
        self.open_or_select_chunk(testament, book, chapter, merged_key)
        self.notify(
            f"Merged chunks {start_index}-{end_index} into {merged_key} and updated the saved catalog."
        )
        self.save_state()
        return merged_key

    def activate_tab(self, tab: str) -> None:
        screen_map = {
            "study": "STUDY",
            "draft": "CHAT",
            "review": "REVIEW",
            "commit": "COMMIT_PREVIEW",
        }
        mode_map = {
            "study": "COMMAND",
            "draft": "CHAT",
            "review": "COMMAND",
            "commit": "COMMAND",
        }
        self.set_screen(screen_map.get(tab, "STUDY"), mode=mode_map.get(tab, "COMMAND"))
