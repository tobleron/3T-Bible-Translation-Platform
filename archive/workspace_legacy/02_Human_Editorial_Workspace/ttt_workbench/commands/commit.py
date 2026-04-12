from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

from ..models import (
    PendingFootnoteUpdate,
    PendingJustificationUpdate,
    PendingRepair,
    PendingTitleUpdate,
    PendingVerseUpdate,
)
from ..repositories import restore_backup_set, write_backup_set
from ..utils import parse_range


class CommitCommandsMixin:
    """Mixin providing /commit, /undo, /repair, /validate, /discard, /cancel."""

    def build_commit_plan(
        self: WorkbenchApp,
    ) -> list[tuple[Path, str, str, list[str]]]:
        writes: list[tuple[Path, str, str, list[str]]] = []
        grouped_text: dict[tuple[str, int], dict[int, str]] = {}
        for pending in self.state.pending_verse_updates:
            bucket = grouped_text.setdefault((pending.book, pending.chapter), {})
            for verse, text in pending.verses.items():
                bucket[int(verse)] = text

        grouped_title: dict[tuple[str, int], PendingTitleUpdate] = {}
        for pending in self.state.pending_title_updates:
            grouped_title[(pending.book, pending.chapter)] = pending

        grouped_footnotes: dict[tuple[str, int], list[PendingFootnoteUpdate]] = {}
        for pending in self.state.pending_footnote_updates:
            grouped_footnotes.setdefault((pending.book, pending.chapter), []).append(pending)

        translation_docs: dict[tuple[str, int], dict] = {}
        chapter_keys = set(grouped_text) | set(grouped_title) | set(grouped_footnotes)
        for key in sorted(chapter_keys):
            book, chapter = key
            chapter_file = self.bible_repo.load_chapter(book, chapter)
            doc = json.loads(json.dumps(chapter_file.doc))
            changed: list[str] = []
            if key in grouped_text:
                changed.extend(self.bible_repo.apply_verse_updates(doc, grouped_text[key]))
            title_update = grouped_title.get(key)
            if title_update:
                self.bible_repo.apply_title_update(
                    doc, title_update.start_verse, title_update.end_verse, title_update.title
                )
                changed.append("headline")
            if key in grouped_footnotes:
                changed.extend(
                    self.bible_repo.apply_footnote_updates(
                        doc,
                        [pending.entry for pending in grouped_footnotes[key]],
                    )
                )
            new_text = self.bible_repo.dump(doc)
            translation_docs[key] = doc
            if new_text != chapter_file.original_text:
                writes.append((chapter_file.path, chapter_file.original_text, new_text, changed))

        repair_targets = {
            (repair.book, repair.chapter): repair
            for repair in self.state.pending_repairs
            if repair.kind == "justification"
        }
        grouped_just: dict[tuple[str, int], list[PendingJustificationUpdate]] = {}
        for pending in self.state.pending_justification_updates:
            grouped_just.setdefault((pending.book, pending.chapter), []).append(pending)

        for key in sorted(set(grouped_just) | set(repair_targets)):
            book, chapter = key
            just_file = self.just_repo.load_document(book, chapter)
            doc = json.loads(json.dumps(just_file.doc))
            bible_doc = (
                translation_docs.get(key)
                or self.bible_repo.load_chapter(book, chapter).doc
            )
            verse_map = self.bible_repo.verse_map(bible_doc)
            if key in grouped_just:
                self.just_repo.apply_updates(
                    doc, grouped_just[key], verse_map, book, chapter
                )
            new_text = self.just_repo.dump(doc)
            notes = list(just_file.notes)
            if key in grouped_just:
                notes.append(f"{len(grouped_just[key])} justification change(s)")
            if new_text != just_file.original_text:
                writes.append(
                    (just_file.path, just_file.original_text, new_text, notes)
                )
        return writes

    def cmd_commit(self: WorkbenchApp, args: list[str]) -> None:
        writes = self.build_commit_plan()
        if not writes:
            self.notify("Nothing to commit.")
            return
        for path, old_text, new_text, notes in writes:
            try:
                json.loads(new_text)
            except json.JSONDecodeError as exc:
                self.notify_error(
                    label="commit",
                    message=f"JSON validation failed for {path.name}: {exc}",
                )
                return
        self.notify_busy(f"Writing {len(writes)} file(s) to disk...")
        backup_dir = write_backup_set(
            self.paths.backups_dir,
            [(path, old_text, new_text) for path, old_text, new_text, _ in writes],
        )
        self.state.undo_stack.append(str(backup_dir))
        summary_lines = []
        for path, old_text, new_text, notes in writes:
            old_lines_count = len(old_text.splitlines())
            new_lines_count = len(new_text.splitlines())
            summary_lines.append(
                f"✓ {path.name} ({old_lines_count} → {new_lines_count} lines)"
            )
            for note in notes:
                summary_lines.append(f"  • {note}")
        summary_lines.append("")
        summary_lines.append(f"Undo snapshot: {backup_dir.name}")
        summary_lines.append("Verify with: /diff (should show no pending changes)")
        self.state.pending_verse_updates = []
        self.state.pending_title_updates = []
        self.state.pending_justification_updates = []
        self.state.pending_footnote_updates = []
        self.state.pending_repairs = []
        self.state.last_review = None
        self.set_screen("CHUNK_PICKER", mode="COMMAND")
        self.notify_done(
            label="commit", message=f"Wrote {len(writes)} file(s) successfully"
        )
        self.emit(self.theme.panel("Commit Complete", summary_lines, accent="green"))

    def cmd_undo(self: WorkbenchApp, args: list[str]) -> None:
        if not self.state.undo_stack:
            self.print_error("No undo snapshot is available.")
            return
        backup_dir = Path(self.state.undo_stack.pop())
        restored = restore_backup_set(backup_dir)
        self.notify("Restored files:\n" + "\n".join(restored))

    def cmd_repair(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        just_file = self.just_repo.load_document(
            self.state.book or "", self.state.chapter or 0
        )
        if not just_file.notes:
            self.notify("No repair is needed for the current justification file.")
            return
        summary_notes = self.summarize_repair_notes(just_file.notes)
        repair = PendingRepair(
            kind="justification",
            book=self.state.book or "",
            chapter=self.state.chapter or 0,
            path=str(just_file.path),
            notes=summary_notes,
        )
        self.state.pending_repairs = [
            item
            for item in self.state.pending_repairs
            if not (
                item.kind == repair.kind
                and item.book == repair.book
                and item.chapter == repair.chapter
            )
        ]
        self.state.pending_repairs.append(repair)
        self.set_screen("TOOLS", mode="COMMAND")
        self.emit(self.theme.panel("Repair Queued", summary_notes, accent="orange"))

    def cmd_validate(self: WorkbenchApp, args: list[str]) -> None:
        """Task 008: Pre-commit structural validation of pending changes."""
        writes = self.build_commit_plan()
        if not writes:
            self.notify("No pending changes to validate.")
            return
        lines = []
        errors = []
        for path, old_text, new_text, notes in writes:
            lines.append(f"File: {path.name}")
            lines.extend(f"  • {note}" for note in notes)
            try:
                parsed = json.loads(new_text)
                lines.append(f"  ✓ Valid JSON")
                if isinstance(parsed, dict):
                    if "chapters" in parsed:
                        lines.append(f"  ✓ Has chapters key")
                    if "justifications" in parsed:
                        lines.append(
                            f"  ✓ Has justifications key ({len(parsed['justifications'])} entries)"
                        )
                    for chapter in parsed.get("chapters", []):
                        verses = chapter.get("verses", [])
                        verse_nums = [
                            v.get("verse") for v in verses if isinstance(v, dict)
                        ]
                        if verse_nums:
                            lines.append(
                                f"  ✓ Chapter {chapter.get('chapter')}: {len(verses)} verses ({min(verse_nums)}-{max(verse_nums)})"
                            )
            except json.JSONDecodeError as exc:
                errors.append(f"✗ JSON error in {path.name}: {exc}")
                lines.append(f"  ✗ JSON error: {exc}")
            lines.append("")
        if errors:
            lines.insert(0, f"Found {len(errors)} error(s):")
            self.emit(self.theme.panel("Validation FAILED", lines, accent="red"))
        else:
            lines.insert(0, f"All {len(writes)} file(s) pass structural validation.")
            self.emit(self.theme.panel("Validation OK", lines, accent="green"))

    def cmd_discard(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        if not args:
            start_verse, end_verse = self.current_range()
        else:
            start_verse, end_verse = parse_range(args[0])
        removed_any = False
        for verse in range(start_verse, end_verse + 1):
            if str(verse) in self.state.draft_chunk:
                self.state.draft_chunk.pop(str(verse), None)
                removed_any = True
        new_pending: list[PendingVerseUpdate] = []
        for item in self.state.pending_verse_updates:
            if (
                item.book != self.state.book
                or item.chapter != self.state.chapter
                or item.end_verse < start_verse
                or item.start_verse > end_verse
            ):
                new_pending.append(item)
                continue
            remaining = {
                verse: text
                for verse, text in item.verses.items()
                if not (start_verse <= int(verse) <= end_verse)
            }
            if len(remaining) != len(item.verses):
                removed_any = True
            if remaining:
                kept = sorted(int(verse) for verse in remaining)
                new_pending.append(
                    PendingVerseUpdate(
                        book=item.book,
                        chapter=item.chapter,
                        verses=remaining,
                        start_verse=kept[0],
                        end_verse=kept[-1],
                    )
                )
        self.state.pending_verse_updates = new_pending
        if self.state.last_review and not (
            self.state.last_review.end_verse < start_verse
            or self.state.last_review.start_verse > end_verse
        ):
            self.state.last_review = None
            removed_any = True
        if not removed_any:
            self.print_error(
                "There was no uncommitted draft or staged work in that range to discard."
            )
            return
        self.notify(
            f"Discarded uncommitted work for verses {start_verse}-{end_verse}. "
            "Committed JSON files were not touched."
        )

    def cmd_cancel(self: WorkbenchApp, args: list[str]) -> None:
        if self.state.mode == "CHAT":
            self.state.mode = "COMMAND"
            self.set_screen("STUDY", mode="COMMAND")
            self.notify("Left chat mode.")
            return
        if self.state.mode == "JUSTIFY":
            self.state.justify_draft = None
            self.state.mode = "COMMAND"
            self.set_screen("REVIEW", mode="COMMAND")
            self.notify("Left justification mode.")
            return
        if self.state.last_review:
            self.state.last_review = None
            self.set_screen("STUDY", mode="COMMAND")
            self.notify("Cleared the active review.")
            return
        self.notify("Nothing is currently active to cancel.")
