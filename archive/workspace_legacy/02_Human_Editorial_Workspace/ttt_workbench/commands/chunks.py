from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

from ..utils import parse_range


class ChunkCommandsMixin:
    """Mixin providing /chunk-* commands."""

    def cmd_chunk_suggest(self: WorkbenchApp, args: list[str]) -> None:
        if self.state.book and self.state.chapter:
            book, chapter = self.state.book, self.state.chapter
        else:
            self.print_error(
                "Open a chapter first with /open Matthew 1 or /open Matthew 1:1-17."
            )
            return
        try:
            window_start, window_end, source = self.ensure_chunk_suggestions(
                book, chapter, force_refresh=False
            )
        except ValueError as exc:
            self.print_error(str(exc))
            return
        lines = [
            f"{book} {chapter} chunk suggestions",
            f"Window: {window_start}-{window_end}",
            f"Source: {source}",
            "",
            *self.chunk_lines(),
        ]
        self.set_screen("CHUNK_PICKER", mode="COMMAND", reset_menu=False)
        self.emit(self.theme.panel("Chunk Suggestions", lines, accent="aqua"))

    def cmd_chunk_use(self: WorkbenchApp, args: list[str]) -> None:
        if not args:
            self.print_error("Use /chunk-use <number>.")
            return
        if (
            not self.state.chunk_suggestions
            or not self.state.book
            or not self.state.chapter
        ):
            self.print_error(
                "No chunk suggestions loaded. Use /open Matthew 1 or /chunk-suggest first."
            )
            return
        try:
            index = int(args[0]) - 1
            chunk = self.state.chunk_suggestions[index]
        except Exception:
            self.print_error("Invalid chunk number.")
            return
        self.open_chunk(
            self.state.book, self.state.chapter, chunk.start_verse, chunk.end_verse
        )
        self.state.menu_index = max(0, min(index, len(self.state.chunk_suggestions) - 1))
        self.set_screen("STUDY", mode="COMMAND", reset_menu=False)
        self.emit_chunk_opened(
            self.state.book, self.state.chapter, chunk.start_verse, chunk.end_verse
        )

    def persist_chunk_suggestions(self: WorkbenchApp) -> None:
        if not self.state.book or not self.state.chapter or not self.state.chunk_suggestions:
            return
        window_start = (
            self.state.chunk_suggestion_window_start
            or self.state.chunk_suggestions[0].start_verse
        )
        window_end = (
            self.state.chunk_suggestion_window_end
            or self.state.chunk_suggestions[-1].end_verse
        )
        payload = {
            "chunks": [
                {
                    "start_verse": chunk.start_verse,
                    "end_verse": chunk.end_verse,
                    "type": chunk.type,
                    "title": chunk.title,
                    "reason": chunk.reason,
                }
                for chunk in self.state.chunk_suggestions
            ],
            "prompt_version": self.chunk_prompt_version,
            "window_start": window_start,
            "window_end": window_end,
            "source": "user-edited",
        }
        self.save_chunk_cache(
            self.state.book, self.state.chapter, window_start, window_end, payload
        )

    def cmd_chunk_range(self: WorkbenchApp, args: list[str]) -> None:
        if len(args) < 2:
            self.print_error("Use /chunk-range <number> <start-end>.")
            return
        if not self.state.chunk_suggestions:
            self.print_error("No chunk suggestions loaded.")
            return
        try:
            index = int(args[0]) - 1
            start_verse, end_verse = parse_range(args[1])
            chunk = self.state.chunk_suggestions[index]
        except Exception:
            self.print_error("Invalid chunk number or range.")
            return
        chunk.start_verse = start_verse
        chunk.end_verse = end_verse
        self.persist_chunk_suggestions()
        self.notify(f"Chunk {index + 1} range updated to {start_verse}-{end_verse}.")

    def cmd_chunk_type(self: WorkbenchApp, args: list[str]) -> None:
        if len(args) < 2:
            self.print_error("Use /chunk-type <number> <type>.")
            return
        if not self.state.chunk_suggestions:
            self.print_error("No chunk suggestions loaded.")
            return
        try:
            index = int(args[0]) - 1
            chunk = self.state.chunk_suggestions[index]
        except Exception:
            self.print_error("Invalid chunk number.")
            return
        chunk.type = args[1].strip()
        self.persist_chunk_suggestions()
        self.notify(f"Chunk {index + 1} type updated to {chunk.type}.")

    def cmd_chunk_title(self: WorkbenchApp, args: list[str]) -> None:
        if len(args) < 2:
            self.print_error('Use /chunk-title <number> "Title".')
            return
        if not self.state.chunk_suggestions:
            self.print_error("No chunk suggestions loaded.")
            return
        try:
            index = int(args[0]) - 1
            chunk = self.state.chunk_suggestions[index]
        except Exception:
            self.print_error("Invalid chunk number.")
            return
        chunk.title = " ".join(args[1:]).strip()
        self.persist_chunk_suggestions()
        self.notify(f"Chunk {index + 1} title updated.")

    def chunk_preview_lines(self: WorkbenchApp, index: int) -> list[str]:
        """Task 003: Show a detailed preview for one chunk suggestion."""
        if (
            not self.state.chunk_suggestions
            or index < 1
            or index > len(self.state.chunk_suggestions)
        ):
            return [f"Chunk {index} not found."]
        chunk = self.state.chunk_suggestions[index - 1]
        lines = [
            f"Chunk {index}: {chunk.start_verse}-{chunk.end_verse}",
            f"  Type: {chunk.type}",
            f"  Title: {chunk.title or '[none]'}",
            f"  Reason: {chunk.reason or '[none]'}",
        ]
        if self.state.book and self.state.chapter:
            testament = self.bible_repo.testament_for(self.state.book, self.state.chapter)
            source = "SBLGNT" if testament != "old" else "WLC"
            preview = self.source_repo.verse_text(
                source, self.state.book, self.state.chapter, chunk.start_verse
            )
            if preview:
                lines.append(f"  Opening verse ({source} {chunk.start_verse}):")
                lines.append(f"    {preview[:200]}")
            draft_text = self.state.draft_chunk.get(str(chunk.start_verse))
            if draft_text:
                lines.append("  Current draft:")
                lines.append(f"    {draft_text[:200]}")
        lines.append("")
        lines.append("Actions: /chunk-use, /chunk-range, /chunk-type, /chunk-title")
        return lines

    def cmd_chunk_preview(self: WorkbenchApp, args: list[str]) -> None:
        """Task 003: Show detailed preview for one chunk suggestion."""
        if not args:
            self.print_error("Use /chunk-preview <number>.")
            return
        try:
            index = int(args[0])
        except ValueError:
            self.print_error("Chunk number must be an integer.")
            return
        lines = self.chunk_preview_lines(index)
        self.emit(self.theme.panel(f"Chunk Preview #{index}", lines, accent="aqua"))

    def cmd_chunk_refresh(self: WorkbenchApp, args: list[str]) -> None:
        if not self.state.book or not self.state.chapter:
            self.print_error("Open a chapter first with /open Matthew 1.")
            return
        t0 = time.monotonic()
        self.notify_busy(
            f"Refreshing chunk suggestions for {self.state.book} {self.state.chapter}...",
            label="chunk-refresh",
        )
        try:
            window_start, window_end, source = self.ensure_chunk_suggestions(
                self.state.book, self.state.chapter, force_refresh=True
            )
            duration = time.monotonic() - t0
            self.notify_done(
                label="chunk-refresh",
                message=f"Refreshed {len(self.state.chunk_suggestions)} suggestions from {source} ({duration:.1f}s)",
            )
        except ValueError as exc:
            duration = time.monotonic() - t0
            self.notify_error(label="chunk-refresh", message=str(exc), duration=duration)
            return
        lines = [
            f"{self.state.book} {self.state.chapter}",
            f"Window: {window_start}-{window_end}",
            f"Source: {source}",
            "",
            *self.chunk_lines(),
        ]
        self.set_screen("CHUNK_PICKER", mode="COMMAND", reset_menu=False)
        self.emit(self.theme.panel("Chunk Suggestions Refreshed", lines, accent="aqua"))

    def cmd_chunk_cache_clear(self: WorkbenchApp, args: list[str]) -> None:
        if args and args[0].lower() == "all":
            removed = 0
            for path in self.paths.chunk_cache_dir.glob("*.json"):
                path.unlink(missing_ok=True)
                removed += 1
            self.notify(f"Cleared {removed} chunk cache files.")
            return
        if not self.state.book or not self.state.chapter:
            self.print_error("Open a chapter first with /open Matthew 1.")
            return
        window_start, window_end = self.chapter_window(self.state.book, self.state.chapter)
        path = self.chunk_cache_path(
            self.state.book, self.state.chapter, window_start, window_end
        )
        if path.exists():
            path.unlink()
        self.notify("Cleared chunk cache for the current chapter window.")
