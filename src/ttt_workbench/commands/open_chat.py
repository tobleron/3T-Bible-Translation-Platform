from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

from ..models import PendingRepair
from ..utils import normalize_book_key, parse_range, parse_reference


class OpenChatCommandsMixin:
    """Mixin providing /open, /status, /sources, /peek, and chunk-opening commands."""

    def parse_open_target(self: WorkbenchApp, args: list[str]) -> tuple[str, int, int | None, int | None]:
        if not args:
            raise ValueError("Missing reference. Use /open Matthew 1 or /open Matthew 1:1-17")
        if len(args) >= 2 and args[-1].isdigit():
            return " ".join(args[:-1]).strip(), int(args[-1]), None, None
        book, chapter, start_verse, end_verse = parse_reference(args)
        return book, chapter, start_verse, end_verse

    def require_open_chunk(self: WorkbenchApp) -> bool:
        if not self.state.book or not self.state.chapter or not self.state.chunk_start or not self.state.chunk_end:
            self.print_error("No open chunk. Use /open Matthew 1:1-17 first.")
            return False
        return True

    def current_range(self: WorkbenchApp) -> tuple[int, int]:
        start = self.state.focus_start or self.state.chunk_start or 1
        end = self.state.focus_end or self.state.chunk_end or start
        return start, end

    def parse_scope_tokens(
        self: WorkbenchApp,
        tokens: list[str],
        *,
        allow_reference: bool = False,
        command_hint: str = "",
    ) -> tuple[int, int, list[str]]:
        if not tokens:
            start_verse, end_verse = self.current_range()
            return start_verse, end_verse, []

        if allow_reference:
            if len(tokens) >= 2 and ":" in tokens[1]:
                try:
                    book, chapter, start_verse, end_verse = parse_reference(tokens[:2])
                except ValueError as exc:
                    hint = f" Use {command_hint}." if command_hint else ""
                    raise ValueError(f"{exc}{hint}")
                if (book or "").lower() != (self.state.book or "").lower() or chapter != (self.state.chapter or 0):
                    raise ValueError(
                        "That reference is outside the current open chunk. "
                        "Open it first, or use a local range like 1-17."
                    )
                return start_verse, end_verse, tokens[2:]
            if ":" in tokens[0]:
                try:
                    book, chapter, start_verse, end_verse = parse_reference(tokens[:1])
                except ValueError as exc:
                    hint = f" Use {command_hint}." if command_hint else ""
                    raise ValueError(f"{exc}{hint}")
                if (book or "").lower() != (self.state.book or "").lower() or chapter != (self.state.chapter or 0):
                    raise ValueError(
                        "That reference is outside the current open chunk. "
                        "Open it first, or use a local range like 1-17."
                    )
                return start_verse, end_verse, tokens[1:]

        start_verse, end_verse = parse_range(tokens[0])
        return start_verse, end_verse, tokens[1:]

    def cmd_open(self: WorkbenchApp, args: list[str]) -> None:
        try:
            book, chapter, start_verse, end_verse = self.parse_open_target(args)
        except ValueError as exc:
            self.print_error(str(exc))
            return
        try:
            self.bible_repo.load_chapter(book, chapter)
        except FileNotFoundError as exc:
            self.print_error(str(exc))
            return
        self.state.wizard_book = book
        self.state.wizard_chapter = chapter
        self.state.wizard_testament = self.bible_repo.testament_for(book, chapter)
        self.state.chunk_suggestions = []
        self.state.chunk_suggestion_window_start = None
        self.state.chunk_suggestion_window_end = None
        if start_verse is None or end_verse is None:
            self.state.book = book
            self.state.chapter = chapter
            self.state.chunk_start = None
            self.state.chunk_end = None
            self.state.focus_start = None
            self.state.focus_end = None
            self.state.chat_messages = []
            self.state.draft_chunk = {}
            self.state.draft_title = ""
            self.state.title_alternatives = []
            self.state.last_review = None
            self.state.justify_draft = None
            self.state.mode = "COMMAND"
            self.set_screen("CHUNK_PICKER", mode="COMMAND")
            t0 = time.monotonic()
            self.notify_busy(f"Loading chunk suggestions for {book} {chapter}...", label="chunk-suggest")
            try:
                window_start, window_end, source = self.ensure_chunk_suggestions(book, chapter, force_refresh=False)
                duration = time.monotonic() - t0
                self.notify_done(
                    label="chunk-suggest",
                    message=f"Loaded {len(self.state.chunk_suggestions)} chunk suggestions from {source} ({duration:.1f}s)",
                )
            except ValueError as exc:
                duration = time.monotonic() - t0
                self.notify_error(label="chunk-suggest", message=str(exc), duration=duration)
                return
            lines = [
                f"{book} {chapter} guided open",
                f"Window: {window_start}-{window_end}",
                f"Chunk suggestions source: {source}",
                "",
                *self.chunk_lines(),
                "",
                "Next: /chunk-use <n> to open one, /chunk-refresh to regenerate, /chunk-range to edit.",
            ]
            self.emit(self.theme.panel("Chunk Suggestions", lines, accent="aqua"))
            return

        self.open_chunk(book, chapter, start_verse, end_verse)
        self.set_screen("STUDY", mode="COMMAND")
        self.emit_chunk_opened(book, chapter, start_verse, end_verse)

    def cmd_status(self: WorkbenchApp, args: list[str]) -> None:
        self.render_status()
        if self.require_open_chunk() and self.application is None:
            self.emit(self.theme.panel("Current Draft", self.open_reference_summary(), accent="blue"))

    def cmd_sources(self: WorkbenchApp, args: list[str]) -> None:
        lines = [
            f"{alias}  {self.source_repo.display_names.get(alias, '')}"
            for alias in self.source_repo.list_sources()
        ]
        self.emit(self.theme.panel("Available Sources", lines, accent="purple"))

    def cmd_peek(self: WorkbenchApp, args: list[str]) -> None:
        """Task 006: Source comparison matrix view."""
        if not self.require_open_chunk():
            return
        if len(args) < 2:
            self.print_error("Use /peek <verse|range> <SRC1,SRC2,...>")
            return
        start_verse, end_verse = parse_range(args[0])
        try:
            aliases = self.source_repo.resolve_sources(args[1:])
        except KeyError as exc:
            self.print_error(str(exc))
            return
        col_width = 50
        header = f"{'Verse':>5}  " + "  │  ".join(
            f"{alias:<{min(col_width, 30)}}" for alias in aliases
        )
        separator = "─" * min(120, 7 + len(aliases) * (col_width + 4))
        lines = [
            f"Source Comparison Matrix — {self.state.book} {self.state.chapter}:{start_verse}-{end_verse}",
            "",
            header,
            separator,
        ]
        verse_texts: dict[int, dict[str, str]] = {}
        for verse in range(start_verse, end_verse + 1):
            row_data = {}
            for alias in aliases:
                text = self.source_repo.verse_text(
                    alias, self.state.book or "", self.state.chapter or 0, verse
                )
                row_data[alias] = text or "[missing]"
            verse_texts[verse] = row_data
            cells = []
            for alias in aliases:
                text = row_data[alias]
                display = text[:col_width] + ("…" if len(text) > col_width else "")
                cells.append(f"{display:<{min(col_width, 30)}}")
            lines.append(f"{verse:>5}  " + "  │  ".join(cells))
        if 2 <= len(aliases) <= 3 and end_verse - start_verse + 1 <= 5:
            lines.append("")
            lines.append("Notable term differences:")
            for verse in range(start_verse, end_verse + 1):
                diffs = self._find_term_diffs(verse_texts[verse], aliases)
                if diffs:
                    lines.append(f"  v{verse}: {'; '.join(diffs[:3])}")
        self.emit(
            self.theme.panel(
                f"Peek {self.state.book} {self.state.chapter}:{start_verse}-{end_verse}",
                lines,
                accent="purple",
            )
        )

    def _find_term_diffs(self: WorkbenchApp, verse_data: dict[str, str], aliases: list[str]) -> list[str]:
        """Task 006: Find simple term differences between sources for one verse."""
        if len(aliases) < 2:
            return []
        texts = [verse_data.get(a, "") for a in aliases]
        if len(set(texts)) <= 1:
            return []
        diffs = []
        for i, alias in enumerate(aliases):
            text = texts[i].lower()
            for j, other in enumerate(aliases):
                if i == j:
                    continue
                other_text = texts[j].lower()
                words_this = set(text.replace(".", "").replace(",", "").replace(";", "").split())
                words_other = set(other_text.replace(".", "").replace(",", "").replace(";", "").split())
                unique = words_this - words_other
                if unique:
                    sample = ", ".join(sorted(unique)[:3])
                    diffs.append(f"{alias} has: {sample}")
        return diffs[:5]

    def open_chunk(self: WorkbenchApp, book: str, chapter: int, start_verse: int, end_verse: int) -> None:
        self.state.book = book
        self.state.chapter = chapter
        self.state.wizard_book = book
        self.state.wizard_chapter = chapter
        self.state.wizard_testament = self.bible_repo.testament_for(book, chapter)
        self.state.chunk_start = start_verse
        self.state.chunk_end = end_verse
        self.state.focus_start = start_verse
        self.state.focus_end = end_verse
        self.state.mode = "COMMAND"
        self.state.chat_messages = []
        self.state.draft_chunk = {}
        self.state.draft_title = ""
        self.state.title_alternatives = []
        self.state.last_review = None
        self.state.justify_draft = None

    def emit_chunk_opened(self: WorkbenchApp, book: str, chapter: int, start_verse: int, end_verse: int) -> None:
        chapter_file = self.bible_repo.load_chapter(book, chapter)
        verse_map = self.bible_repo.verse_map(chapter_file.doc)
        missing = [verse for verse in range(start_verse, end_verse + 1) if not verse_map.get(verse, "").strip()]
        try:
            just_file = self.just_repo.load_document(book, chapter)
        except Exception as exc:
            self.print_error(f"Failed to load justification file: {exc}")
            return
        summary_notes = self.summarize_repair_notes(just_file.notes)
        if summary_notes:
            repair = PendingRepair(
                kind="justification", book=book, chapter=chapter,
                path=str(just_file.path), notes=summary_notes,
            )
            if not any(
                item.kind == repair.kind and item.book == book and item.chapter == chapter
                for item in self.state.pending_repairs
            ):
                self.state.pending_repairs.append(repair)
        lines = [
            f"{book} {chapter}:{start_verse}-{end_verse} ready",
            f"Bible: {self.short_file_label(chapter_file.path)}",
            f"Justifications: {self.short_file_label(just_file.path)}",
        ]
        if not chapter_file.original_text:
            lines.append("Chapter scaffold pending: final JSON will be created on first commit.")
        if missing:
            lines.append("Untranslated in final JSON: " + ", ".join(str(v) for v in missing))
        if summary_notes:
            lines.append("Repairs queued: " + self.repair_blurb(summary_notes))
        lines.append("Next: /chat to draft, /study to inspect sources, /analysis refresh for model analysis.")
        self.emit(self.theme.panel("Chunk Opened", lines, accent="aqua"))

    def chunk_cache_key(
        self: WorkbenchApp, book: str, chapter: int, window_start: int, window_end: int
    ) -> str:
        return f"{normalize_book_key(book)}_{chapter}_{window_start}_{window_end}_{self.chunk_prompt_version}"

    def chunk_cache_path(
        self: WorkbenchApp, book: str, chapter: int, window_start: int, window_end: int
    ) -> Path:
        return self.paths.chunk_cache_dir / f"{self.chunk_cache_key(book, chapter, window_start, window_end)}.json"

    def load_chunk_cache(
        self: WorkbenchApp, book: str, chapter: int, window_start: int, window_end: int
    ) -> dict | None:
        path = self.chunk_cache_path(book, chapter, window_start, window_end)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_chunk_cache(
        self: WorkbenchApp, book: str, chapter: int, window_start: int, window_end: int, payload: dict
    ) -> None:
        path = self.chunk_cache_path(book, chapter, window_start, window_end)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def load_chunk_prompts(self: WorkbenchApp) -> tuple[str, str, str]:
        schema = (self.paths.chunking_prompts_dir / "chunk_schema.txt").read_text(encoding="utf-8")
        ot = (self.paths.chunking_prompts_dir / "ot_chunk_suggest.txt").read_text(encoding="utf-8")
        nt = (self.paths.chunking_prompts_dir / "nt_chunk_suggest.txt").read_text(encoding="utf-8")
        return schema, ot, nt

    def chapter_window(self: WorkbenchApp, book: str, chapter: int) -> tuple[int, int]:
        chapter_doc = self.bible_repo.load_chapter(book, chapter).doc
        verse_map = self.bible_repo.verse_map(chapter_doc)
        verses = sorted(verse_map)
        if not verses:
            return 1, 1
        first_unfinished = None
        for verse in verses:
            if not str(verse_map.get(verse, "")).strip():
                first_unfinished = verse
                break
        start = first_unfinished or verses[0]
        end = min(verses[-1], start + 39)
        return start, end

    def build_chunk_prompt(
        self: WorkbenchApp, book: str, chapter: int, window_start: int, window_end: int
    ) -> str:
        schema, ot_prompt, nt_prompt = self.load_chunk_prompts()
        testament = self.bible_repo.testament_for(book, chapter)
        witness_prompt = ot_prompt if testament == "old" else nt_prompt
        original_context = self.chunk_study_context(book, chapter, window_start, window_end, testament)
        return f"""/no_think
Model profile: qwen3.5 35B A3B thinking model.
{witness_prompt}

Window to segment: {book} {chapter}:{window_start}-{window_end}

Original-language context:
{original_context}

{schema}
""".strip()

    def chunk_study_context(
        self: WorkbenchApp, book: str, chapter: int, start_verse: int, end_verse: int, testament: str
    ) -> str:
        lines: list[str] = []
        if testament == "old":
            hebrew = self.lexical_repo.fetch_tokens("hebrew_ot", book, chapter, start_verse, end_verse)
            lxx = self.lexical_repo.fetch_tokens("greek_ot_lxx", book, chapter, start_verse, end_verse)
            for verse in range(start_verse, end_verse + 1):
                ref = f"{book_ref_code(book)}.{chapter}.{verse}"
                lines.append(
                    f"{verse} Hebrew: "
                    + " ".join(token.get("surface", "") for token in hebrew.get(ref, []))
                )
                lines.append(
                    f"{verse} Hebrew literal: "
                    + " / ".join(
                        (token.get("gloss") or token.get("english") or "")
                        .replace("<br>", "; ")
                        for token in hebrew.get(ref, [])
                        if (token.get("gloss") or token.get("english"))
                    )
                )
                if lxx.get(ref):
                    lines.append(
                        f"{verse} LXX: "
                        + " ".join(token.get("surface", "") for token in lxx.get(ref, []))
                    )
        else:
            greek = self.lexical_repo.fetch_tokens("greek_nt", book, chapter, start_verse, end_verse)
            for verse in range(start_verse, end_verse + 1):
                ref = f"{book_ref_code(book)}.{chapter}.{verse}"
                lines.append(
                    f"{verse} Greek: "
                    + " ".join(token.get("surface", "") for token in greek.get(ref, []))
                )
                lines.append(
                    f"{verse} Greek literal: "
                    + " / ".join(
                        (token.get("gloss") or token.get("english") or "")
                        .replace("<br>", "; ")
                        for token in greek.get(ref, [])
                        if (token.get("gloss") or token.get("english"))
                    )
                )
        return "\n".join(lines)

    def set_chunk_suggestions_from_payload(
        self: WorkbenchApp, book: str, chapter: int, window_start: int, window_end: int, payload: dict
    ) -> None:
        suggestions: list[ChunkSuggestion] = []
        for item in payload.get("chunks", []):
            try:
                suggestions.append(
                    ChunkSuggestion(
                        start_verse=int(item["start_verse"]),
                        end_verse=int(item["end_verse"]),
                        type=str(item.get("type", "mixed")).strip() or "mixed",
                        title=str(item.get("title", "")).strip(),
                        reason=str(item.get("reason", "")).strip(),
                    )
                )
            except Exception:
                continue
        self.state.chunk_suggestion_window_start = window_start
        self.state.chunk_suggestion_window_end = window_end
        self.state.chunk_suggestions = suggestions

    def ensure_chunk_suggestions(
        self: WorkbenchApp, book: str, chapter: int, *, force_refresh: bool = False
    ) -> tuple[int, int, str]:
        window_start, window_end = self.chapter_window(book, chapter)
        if not force_refresh:
            cached = self.load_chunk_cache(book, chapter, window_start, window_end)
            if isinstance(cached, dict) and isinstance(cached.get("chunks"), list):
                self.set_chunk_suggestions_from_payload(book, chapter, window_start, window_end, cached)
                return window_start, window_end, "cache"
        prompt = self.build_chunk_prompt(book, chapter, window_start, window_end)
        self.refresh_active_endpoint()
        payload, _, attempts = self.llm.complete_json(
            prompt,
            required_keys=["chunks"],
            temperature=0.2,
            max_tokens=1800,
            max_attempts=2,
            timeout_seconds=75,
        )
        if not isinstance(payload, dict):
            raise ValueError("Qwen did not return valid chunk suggestions in time.")
        payload["prompt_version"] = self.chunk_prompt_version
        payload["window_start"] = window_start
        payload["window_end"] = window_end
        payload["generated_at"] = self.state.session_id
        self.save_chunk_cache(book, chapter, window_start, window_end, payload)
        self.set_chunk_suggestions_from_payload(book, chapter, window_start, window_end, payload)
        if not self.state.chunk_suggestions:
            raise ValueError("Qwen returned chunk JSON, but no usable chunk ranges were parsed.")
        return window_start, window_end, f"model ({attempts} attempt{'s' if attempts != 1 else ''})"

    def chunk_lines(self: WorkbenchApp, *, with_preview: bool = False) -> list[str]:
        lines: list[str] = []
        testament = (
            self.bible_repo.testament_for(self.state.book, self.state.chapter)
            if self.state.book and self.state.chapter
            else "new"
        )
        for index, chunk in enumerate(self.state.chunk_suggestions, start=1):
            lines.append(
                f"{index}. {chunk.start_verse}-{chunk.end_verse}  [{chunk.type}]  {chunk.title}"
            )
            if chunk.reason:
                lines.append(f"   {chunk.reason}")
            if with_preview and self.state.book and self.state.chapter:
                preview_text = self.source_repo.verse_text(
                    "SBLGNT" if testament != "old" else "WLC",
                    self.state.book,
                    self.state.chapter,
                    chunk.start_verse,
                )
                if preview_text:
                    preview = preview_text[:100] + ("..." if len(preview_text) > 100 else "")
                    lines.append(f"   ▶ {preview}")
        return lines or ["No chunk suggestions loaded."]
