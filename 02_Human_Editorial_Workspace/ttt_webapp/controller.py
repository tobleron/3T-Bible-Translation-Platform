from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from rich.panel import Panel

from ttt_core.data.repositories import ProjectPaths
from ttt_core.models import (
    ChunkSuggestion,
    PendingTitleUpdate,
    PendingVerseUpdate,
    SessionState,
)
from ttt_core.utils import normalize_book_key

from ttt_workbench.app import WorkbenchApp
from ttt_workbench.repositories import restore_backup_set

from .chunk_catalog import ChunkCatalogRepository


@dataclass
class PromptSetting:
    key: str
    label: str
    path: Path


class BrowserWorkbench(WorkbenchApp):
    """Headless workbench controller for the browser app."""

    _editor_line_re = re.compile(r"(?m)^\s*(\d+)\s*[\.\):-]\s*")

    def __init__(self) -> None:
        llm_override, fake_mode = self._build_llm_override()
        self.fake_llm_mode = fake_mode
        super().__init__(llm_override=llm_override)
        self._configure_runtime_storage()
        self._sanitize_browser_state()
        self.flash_messages: list[dict[str, str]] = []
        self.chunk_catalog_repo = ChunkCatalogRepository(self.paths, self.bible_repo)
        self.settings_file = self.runtime_state_dir / "web_settings.json"
        self.chunk_sessions_file = self.runtime_state_dir / "chunk_sessions.json"
        self.chunk_sessions = self._load_chunk_sessions()
        self.web_settings = self._load_web_settings()
        self.llm.base_url = self.web_settings.get("base_url", self.llm.base_url)

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
        defaults = {"base_url": self.llm.base_url, "selected_sources": ["LSB", "ESV"]}
        if not self.settings_file.exists():
            return defaults
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except Exception:
            return defaults
        if not isinstance(payload, dict):
            return defaults
        merged = {**defaults, **payload}
        if (
            not self.fake_llm_mode
            and "fake-llm.local" in str(merged.get("base_url", ""))
        ):
            merged["base_url"] = defaults["base_url"]
            self.settings_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return merged

    def save_web_settings(self, payload: dict[str, Any]) -> None:
        self.web_settings = {**self.web_settings, **payload}
        self.settings_file.write_text(
            json.dumps(self.web_settings, indent=2), encoding="utf-8"
        )
        self.llm.base_url = self.web_settings.get("base_url", self.llm.base_url)

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
        return f"{testament_name}|{normalize_book_key(book_name)}|{chapter_number}|{range_key}"

    def current_chunk_session(self) -> dict[str, Any]:
        key = self.chunk_session_key()
        if not key:
            return {}
        if key not in self.chunk_sessions:
            self.chunk_sessions[key] = {
                "messages": [],
                "context_loaded": False,
                "context_snapshot": "",
                "focus_start": self.state.focus_start,
                "focus_end": self.state.focus_end,
            }
        return self.chunk_sessions[key]

    def load_chunk_session(
        self,
        testament: str,
        book: str,
        chapter: int,
        chunk_key: str,
    ) -> None:
        key = self.chunk_session_key(testament, book, chapter, chunk_key)
        session = self.chunk_sessions.get(key or "", {})
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
        self.chunk_sessions[key] = {
            "messages": list(self.state.chat_messages),
            "context_loaded": bool(self.current_chunk_session().get("context_loaded")),
            "context_snapshot": str(self.current_chunk_session().get("context_snapshot", "")),
            "focus_start": self.state.focus_start,
            "focus_end": self.state.focus_end,
        }
        self._save_chunk_sessions()

    def clear_current_chunk_session(self) -> None:
        key = self.chunk_session_key()
        if key and key in self.chunk_sessions:
            self.chunk_sessions.pop(key, None)
            self._save_chunk_sessions()
        self.state.chat_messages = []
        self.notify("Cleared the saved chat session for this chunk.")

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
            if str(item).strip() and str(item).upper() in self.source_repo.catalog
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
        clean = [alias.upper() for alias in aliases if alias.upper() in self.source_repo.catalog]
        self.save_web_settings({"selected_sources": clean})

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

    def load_workspace(self, testament: str, book: str, chapter: int, chunk_key: str) -> None:
        start_verse, end_verse = [int(part) for part in chunk_key.split("-", 1)]
        self.open_chunk(book, chapter, start_verse, end_verse)
        self.state.footnote_draft = None
        self.state.wizard_testament = testament
        self.set_screen("STUDY", mode="COMMAND")
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
        if self.state.draft_title.strip():
            return True
        return any(str(text).strip() for text in self.state.draft_chunk.values())

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
            return "draft"
        if force_default or self.editor_mode() not in {"draft", "review"}:
            return self.set_editor_mode(self.default_editor_mode())
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
        mapping = self.source_repo._load_source(alias)
        has_ot = any(book == normalize_book_key("Genesis") for (book, _chapter, _verse) in mapping)
        has_nt = any(book == normalize_book_key("Matthew") for (book, _chapter, _verse) in mapping)
        if has_ot and has_nt:
            return "OT + NT"
        if has_nt:
            return "NT only"
        if has_ot:
            return "OT only"
        return "Partial"

    def comparison_source_options(self) -> list[dict[str, str | bool]]:
        current_testament = self.state.wizard_testament or self.testament() or "new"
        current_book = self.state.book or ""
        current_chapter = self.state.chapter or 0
        selected = set(self.selected_sources())
        options: list[dict[str, str | bool]] = []
        for alias in self.comparison_sources():
            if alias in {"WLC"}:
                continue
            alias_map = self.source_repo._load_source(alias)
            available_here = bool(
                current_book
                and current_chapter
                and any(
                    key_book == normalize_book_key(current_book) and key_chapter == current_chapter
                    for (key_book, key_chapter, _verse) in alias_map.keys()
                )
            )
            support = self.source_support_label(alias)
            options.append(
                {
                    "alias": alias,
                    "label": alias,
                    "support": support,
                    "selected": alias in selected,
                    "available_here": available_here,
                    "disabled": current_testament == "old" and support == "NT only",
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
                        heb_strongs.add(t["strong_id"])
                for t in lxx.get(self.lexical_ref(verse, corpus="greek_ot_lxx"), []):
                    if t.get("strong_id"):
                        lxx_strongs.add(t["strong_id"])

            # Look up real English from lexicon
            heb_lexicon = self.lexical_repo.fetch_lexicon_glosses("hebrew_ot", list(heb_strongs))
            lxx_lexicon = self.lexical_repo.fetch_lexicon_glosses("greek_ot_lxx", list(lxx_strongs))

            # Build Hebrew block: surface text + per-token gloss data
            heb_surface_parts = []
            heb_gloss_tokens: list[dict[str, str]] = []
            has_hebrew = False
            for verse in range(start_verse, end_verse + 1):
                tokens = hebrew.get(self.lexical_ref(verse, corpus="hebrew_ot"), [])
                surfaces = [t.get("surface", "").strip() for t in tokens if t.get("surface", "").strip()]
                for t in tokens:
                    gloss = heb_lexicon.get(t.get("strong_id", ""), "")
                    if gloss:
                        heb_gloss_tokens.append({"gloss": gloss, "surface": t.get("surface", "").strip()})
                if surfaces:
                    has_hebrew = True
                    heb_surface_parts.append(" ".join(surfaces))
                else:
                    fallback = self._fallback_verse_text(verse)
                    if fallback:
                        has_hebrew = True
                        heb_surface_parts.append(fallback)
                    else:
                        heb_surface_parts.append("[no data]")

            if has_hebrew:
                blocks.append({
                    "label": "Hebrew",
                    "caption": "Masoretic Text (WLC)",
                    "text": self._chunk_join(heb_surface_parts),
                    "gloss_tokens": heb_gloss_tokens,
                    "kind": "hebrew",
                })

            # Build LXX block
            lxx_surface_parts = []
            lxx_gloss_tokens: list[dict[str, str]] = []
            has_lxx = False
            for verse in range(start_verse, end_verse + 1):
                tokens = lxx.get(self.lexical_ref(verse, corpus="greek_ot_lxx"), [])
                surfaces = [t.get("surface", "").strip() for t in tokens if t.get("surface", "").strip()]
                for t in tokens:
                    gloss = lxx_lexicon.get(t.get("strong_id", ""), "")
                    if gloss:
                        lxx_gloss_tokens.append({"gloss": gloss, "surface": t.get("surface", "").strip()})
                if surfaces:
                    has_lxx = True
                    lxx_surface_parts.append(" ".join(surfaces))

            lxx_text = self._chunk_join(lxx_surface_parts) if has_lxx else ""
            if lxx_text and lxx_text != "[missing]":
                blocks.append({
                    "label": "LXX Greek",
                    "caption": "Septuagint (Rahlfs 1935)",
                    "text": lxx_text,
                    "gloss_tokens": lxx_gloss_tokens,
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
                        greek_strongs.add(t["strong_id"])
            greek_lexicon = self.lexical_repo.fetch_lexicon_glosses("greek_nt", list(greek_strongs))

            greek_surface_parts = []
            greek_gloss_tokens: list[dict[str, str]] = []
            for verse in range(start_verse, end_verse + 1):
                tokens = greek.get(self.lexical_ref(verse, corpus="greek_nt"), [])
                surfaces = [t.get("surface", "").strip() for t in tokens if t.get("surface", "").strip()]
                for t in tokens:
                    gloss = greek_lexicon.get(t.get("strong_id", ""), "")
                    if gloss:
                        greek_gloss_tokens.append({"gloss": gloss, "surface": t.get("surface", "").strip()})
                greek_surface_parts.append(" ".join(surfaces) if surfaces else "[no data]")

            blocks.append({
                "label": "SBLGNT Greek",
                "caption": "SBL Greek New Testament",
                "text": self._chunk_join(greek_surface_parts),
                "gloss_tokens": greek_gloss_tokens,
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
            merged[entry_id] = {
                "id": entry_id,
                "verses": verses,
                "verse_label": self._format_verse_label(verses),
                "source_term": str(raw_entry.get("source_term", "")).strip(),
                "decision": str(raw_entry.get("decision", "")).strip(),
                "reason": str(raw_entry.get("reason", "")).strip(),
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
            if verse < start or verse > end:
                return
            letter = str(raw_entry.get("letter", "")).strip()
            content = str(raw_entry.get("content", "")).strip()
            if not content:
                return
            merged[(verse, letter)] = {
                "verse": verse,
                "letter": letter,
                "verse_label": f"{verse}{letter}" if letter else str(verse),
                "content": content,
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
            text = self.state.draft_chunk.get(key, committed)
            verses.append(
                {
                    "verse": verse,
                    "text": (text or "").rstrip(),
                    "committed": committed.rstrip(),
                    "changed": key in self.state.draft_chunk and text.strip() != committed.strip(),
                }
            )
        return verses

    def editor_title(self, mode: str | None = None) -> str:
        current_mode = mode or self.editor_mode()
        if current_mode == "review" and not self.state.draft_title.strip():
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
            if alias not in {"WLC"}
        ]

    def preferred_python(self) -> Path:
        candidate = self.paths.repo_root / ".venv" / "bin" / "python"
        if candidate.exists():
            return candidate
        return Path(sys.executable)

    def safe_list_models(self) -> list[str]:
        try:
            models = self.llm.list_models()
        except Exception as exc:
            self.print_error(f"Model discovery failed: {exc}")
            return [self.model_name]
        if models:
            return models
        return [self.model_name]

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
            lines.append(block["text"])
            if block.get("gloss"):
                lines.append(f"  Literal gloss: {block['gloss']}")
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
        if not self.require_open_chunk():
            return ""
        start = self.state.chunk_start or 1
        end = self.state.chunk_end or start
        history = "\n".join(
            f"{item['role'].upper()}: {item['content']}"
            for item in self.state.chat_messages[-10:]
        )
        ledger = "\n".join(self.ledger_lines()) or "None yet."
        session = self.current_chunk_session()
        include_context = not bool(session.get("context_loaded"))
        context_block = self.session_context_snapshot() if include_context else ""
        return f"""
You are assisting a Bible translator in a browser-based editorial workbench.

Rules:
- Keep the title short, usable as a section heading, and plain English.
- Revise only the verses inside the chunk unless the user explicitly asks for wider changes.
- Output strict JSON only with this shape:
{{
  "reply": "short editor-facing response",
  "title": "short title",
  "verses": [
    {{"verse": 1, "text": "..." }}
  ]
}}

Current chunk: {self.state.book} {self.state.chapter}:{start}-{end}

Current draft title:
{self.state.draft_title or "[untitled]"}

Current draft for the full chunk (verses {start}-{end}):
{self.selected_range_draft_text()}

Approved terminology ledger:
{ledger}

Terminology consistency (approved decisions only):
{self.terminology_prompt_block()}

Conversation so far:
{history or "None"}
{f'''

Load this chunk context now. This context is only provided at session start:
{context_block}
''' if include_context else ""}

User message:
{user_message}
""".strip()

    def browser_auto_generate_draft(self) -> bool:
        payload, response, _attempts = self.llm.complete_json(
            self.build_initial_draft_prompt(),
            required_keys=["reply", "title", "verses"],
            temperature=0.25,
            max_tokens=2600,
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
        payload, response, _attempts = self.llm.complete_json(
            prompt,
            required_keys=["reply", "title", "verses"],
            temperature=0.3,
            max_tokens=2400,
            max_attempts=3,
        )
        self.state.chat_messages.append({"role": "user", "content": user_message})
        if isinstance(payload, dict):
            reply = str(payload.get("reply", "(no reply)")).strip()
            for verse in payload.get("verses", []):
                try:
                    number = int(verse["verse"])
                except Exception:
                    continue
                if "text" in verse:
                    self.state.draft_chunk[str(number)] = verse["text"].strip()
            title = str(payload.get("title", "")).strip()
            if title:
                self.state.draft_title = title
            self.state.title_alternatives = [
                item for item in payload.get("title_alternatives", []) if isinstance(item, str)
            ]
            if reply:
                self.state.chat_messages.append({"role": "assistant", "content": reply})
            self.prepare_browser_commit_state()
            session = self.current_chunk_session()
            session["context_loaded"] = True
            if not session.get("context_snapshot"):
                session["context_snapshot"] = self.session_context_snapshot()
            self.persist_current_chunk_session()
            return
        if str(response).startswith("[ERROR]"):
            self.print_error(self.explain_llm_failure(str(response)))
            return
        self.print_error("The model response was not valid JSON. No draft changes were applied.")

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
            (self.paths.repo_root / "03_EPUB_Production").glob("*.epub"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:5]

    def generate_epub_and_return_latest(self) -> tuple[bool, str, Path | None]:
        """Generate EPUB and return (success, message, latest_epub_path)."""
        output_dir = self.paths.repo_root / "03_EPUB_Production"
        cmd = [str(self.preferred_python()), "generate_epub.py", "--md", "--txt"]
        try:
            result = subprocess.run(cmd, cwd=output_dir, capture_output=True, text=True, check=False)
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
            if len(parts) == 4:
                testament_name, book_key, chapter_num, chunk_range = parts
                book_display = book_key.replace("_", " ").title()
                sessions.append({
                    "session_key": key,
                    "testament": testament_name,
                    "book": book_display,
                    "chapter": int(chapter_num),
                    "chunk_range": chunk_range,
                    "message_count": len(session.get("messages", [])),
                    "context_loaded": session.get("context_loaded", False),
                })
        return sessions

    def workspace_payload(self, active_tab: str = "study") -> dict[str, Any]:
        testament = self.state.wizard_testament or self.testament() or "new"
        book = self.state.book or self.state.wizard_book or ""
        chapter = self.state.chapter or self.state.wizard_chapter or 0
        chunk_open = self.has_open_chunk()
        if chunk_open:
            self.prepare_browser_commit_state()
            editor_mode = self.sync_editor_mode()
        else:
            editor_mode = "draft"
        editor_start, editor_end = self.current_editor_range() if chunk_open else (0, 0)
        return {
            "navigator": self.navigator_catalog(),
            "state": self.state,
            "selected_testament": testament,
            "selected_book": book,
            "selected_chapter": chapter,
            "chapter_chunks": self.chapter_chunks(testament, book, chapter) if book and chapter else [],
            "chunk_summary": self.current_chunk_summary(),
            "study_cards": self.build_study_cards() if chunk_open else [],
            "study_blocks": self.chunk_study_blocks() if chunk_open else [],
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
            "comparison_sources": self.comparison_sources(),
            "comparison_source_options": self.comparison_source_options(),
            "selected_sources": self.selected_sources(),
            "commit_history": self.commit_history_entries(),
            "model_label": self.model_label,
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
            "justification_entries": self.chunk_justification_entries() if chunk_open else [],
            "footnote_entries": self.chunk_footnote_entries() if chunk_open else [],
        }

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
        chapter_map = self.chapter_verse_map()
        if mode == "review":
            committed_title = self.committed_chunk_title()
            cleaned_title = title.strip()
            self.state.draft_title = "" if cleaned_title == committed_title else cleaned_title
            for verse, text in verses.items():
                key = str(verse)
                cleaned = text.strip()
                committed = chapter_map.get(verse, "").strip()
                if cleaned == committed:
                    self.state.draft_chunk.pop(key, None)
                else:
                    self.state.draft_chunk[key] = cleaned
        else:
            self.state.draft_title = title.strip()
            for verse, text in verses.items():
                self.state.draft_chunk[str(verse)] = text.strip()
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
