from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

from ..models import PendingTitleUpdate, PendingVerseUpdate, ReviewState
from ..utils import parse_range


class ReviewCommandsMixin:
    """Mixin providing /finalize, /stage, /revise, /title, /diff, and review-related methods."""

    def cmd_finalize(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        if args:
            start_verse, end_verse = parse_range(args[0])
        else:
            start_verse, end_verse = self.current_range()
        missing = [
            verse
            for verse in range(start_verse, end_verse + 1)
            if not self.state.draft_chunk.get(str(verse), "").strip()
        ]
        if missing:
            self.print_error(
                "Draft text is missing for verses: " + ", ".join(str(v) for v in missing)
            )
            return
        self.notify_busy(
            f"Running editorial review for verses {start_verse}-{end_verse}...",
            label="finalize",
        )
        t0 = time.monotonic()
        payload, review_raw, attempts = self.llm.complete_json(
            self.build_finalize_prompt(start_verse, end_verse),
            required_keys=["summary", "issues", "verdict", "title_review"],
            temperature=0.15,
            max_tokens=1200,
            max_attempts=3,
        )
        duration = time.monotonic() - t0
        if not isinstance(payload, dict):
            self.notify_error(
                label="finalize",
                message="The endpoint did not return a valid finalize review.",
                duration=duration,
            )
            return
        candidate_map = self.current_verse_map(include_draft=True)
        just_file = self.just_repo.load_document(
            self.state.book or "", self.state.chapter or 0
        )
        watch = self.just_repo.stale_entries(
            just_file.doc,
            candidate_map,
            self.state.book or "",
            self.state.chapter or 0,
            range(start_verse, end_verse + 1),
        )
        review = ReviewState(
            start_verse=start_verse,
            end_verse=end_verse,
            summary=payload.get("summary", ""),
            issues=[str(item) for item in payload.get("issues", [])],
            verdict=str(payload.get("verdict", "revise")),
            title_review=str(payload.get("title_review", "")),
            justification_watch=watch,
        )
        self.state.last_review = review
        self.set_screen("REVIEW", mode="COMMAND")
        self.record_review_event()
        lines = self.review_summary_card()
        if attempts > 1:
            lines.append(f"JSON compliance retries: {attempts}")
        self.notify_done(
            label="finalize",
            message=f"Review complete: {review.verdict} ({duration:.1f}s)",
            duration=duration,
        )
        self.emit(
            self.theme.panel(
                "Finalize Review",
                lines,
                accent="yellow" if review.verdict == "ready" else "orange",
            )
        )

    def cmd_stage(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        if args:
            start_verse, end_verse = parse_range(args[0])
        else:
            start_verse, end_verse = self.current_range()
        review = self.state.last_review
        if (
            not review
            or review.start_verse != start_verse
            or review.end_verse != end_verse
        ):
            self.print_error("Run /finalize on the same range before staging it.")
            return
        verses = {
            str(verse): self.state.draft_chunk[str(verse)]
            for verse in range(start_verse, end_verse + 1)
        }
        self.state.pending_verse_updates = [
            item
            for item in self.state.pending_verse_updates
            if not (
                item.book == self.state.book
                and item.chapter == self.state.chapter
                and item.start_verse == start_verse
                and item.end_verse == end_verse
            )
        ]
        self.state.pending_verse_updates.append(
            PendingVerseUpdate(
                book=self.state.book or "",
                chapter=self.state.chapter or 0,
                verses=verses,
                start_verse=start_verse,
                end_verse=end_verse,
            )
        )
        self.set_screen("COMMIT_PREVIEW", mode="COMMAND")
        self.notify(f"Staged verses {start_verse}-{end_verse}. Use /commit when ready.")

    def cmd_revise(self: WorkbenchApp, args: list[str]) -> None:
        if not self.state.last_review:
            self.print_error("There is no active review to revise from.")
            return
        review = self.state.last_review
        guidance = [review.summary] + review.issues
        self.state.chat_messages.append(
            {
                "role": "system",
                "content": "Editorial review guidance: "
                + " | ".join(item for item in guidance if item),
            }
        )
        self.state.mode = "CHAT"
        self.set_screen("CHAT", mode="CHAT")
        self.emit(
            self.theme.panel(
                "Revision Guidance",
                ["Review notes were added to chat context.", "You are back in chat mode."],
                accent="green",
            )
        )

    def cmd_title(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        if not args or args[0] == "show":
            lines = [f"Draft title: {self.state.draft_title or '[none]'}"]
            if self.state.title_alternatives:
                lines.append(
                    "Alternatives: " + " | ".join(self.state.title_alternatives[:3])
                )
            staged = [
                item.title
                for item in self.state.pending_title_updates
                if item.book == self.state.book and item.chapter == self.state.chapter
            ]
            if staged:
                lines.append("Staged title: " + staged[-1])
            self.emit(self.theme.panel("Title", lines, accent="aqua"))
            return
        action = args[0]
        if action == "refresh":
            self.notify_busy("Refreshing chunk title suggestions...", label="title")
            t0 = time.monotonic()
            payload, raw, attempts = self.llm.complete_json(
                self.build_title_prompt(),
                required_keys=["title", "alternatives", "reason"],
                temperature=0.2,
                max_tokens=900,
                max_attempts=3,
            )
            duration = time.monotonic() - t0
            if not isinstance(payload, dict):
                self.notify_error(
                    label="title",
                    message="The endpoint did not return a valid title response.",
                    duration=duration,
                )
                return
            self.state.draft_title = payload.get("title", "").strip()
            self.state.title_alternatives = [
                item for item in payload.get("alternatives", []) if isinstance(item, str)
            ]
            lines = [f"Title draft: {self.state.draft_title or '[none]'}"]
            if self.state.title_alternatives:
                lines.append(
                    "Alternatives: " + " | ".join(self.state.title_alternatives[:3])
                )
            if payload.get("reason"):
                lines.append(payload["reason"])
            if attempts > 1:
                lines.append(f"JSON compliance retries: {attempts}")
            self.notify_done(
                label="title",
                message=f"Title refreshed ({duration:.1f}s)",
                duration=duration,
            )
            self.emit(self.theme.panel("Title Refreshed", lines, accent="aqua"))
            return
        if action == "set":
            title = " ".join(args[1:]).strip()
            if not title:
                self.print_error("Use /title set <text>.")
                return
            self.state.draft_title = title
            self.notify(f"Title draft set to: {title}")
            return
        if action == "stage":
            if not self.state.draft_title:
                self.print_error(
                    "No draft title is available. Use /title refresh or /title set first."
                )
                return
            try:
                self.bible_repo.title_section_index(
                    self.current_chapter(),
                    self.state.chunk_start or 1,
                    self.state.chunk_end or 1,
                )
            except ValueError as exc:
                self.print_error(str(exc))
                return
            self.state.pending_title_updates = [
                item
                for item in self.state.pending_title_updates
                if not (item.book == self.state.book and item.chapter == self.state.chapter)
            ]
            self.state.pending_title_updates.append(
                PendingTitleUpdate(
                    book=self.state.book or "",
                    chapter=self.state.chapter or 0,
                    start_verse=self.state.chunk_start or 1,
                    end_verse=self.state.chunk_end or 1,
                    title=self.state.draft_title,
                )
            )
            self.set_screen("COMMIT_PREVIEW", mode="COMMAND")
            self.notify("Title staged.")
            return
        if action == "discard":
            self.state.draft_title = ""
            self.state.title_alternatives = []
            self.state.pending_title_updates = [
                item
                for item in self.state.pending_title_updates
                if not (item.book == self.state.book and item.chapter == self.state.chapter)
            ]
            self.notify("Uncommitted title draft and staged title were discarded.")
            return
        self.print_error("Use /title show|refresh|set|stage|discard")

    def cmd_diff(self: WorkbenchApp, args: list[str]) -> None:
        writes = self.build_commit_plan()
        if not writes:
            self.notify("There are no pending file changes.")
            return
        self.set_screen("COMMIT_PREVIEW", mode="COMMAND")
        lines = []
        for path, old_text, new_text, notes in writes:
            lines.append(str(path))
            for note in notes:
                lines.append(f"  - {note}")
            old_lines = old_text.splitlines()
            new_lines = new_text.splitlines()
            preview = []
            import difflib

            for line in difflib.unified_diff(
                old_lines, new_lines, fromfile="old", tofile="new", lineterm=""
            ):
                preview.append(line)
                if len(preview) >= 12:
                    break
            lines.extend("    " + item for item in preview)
            lines.append("")
        self.emit(self.theme.panel("Pending Diff", lines[:-1], accent="orange"))

    def record_review_event(self: WorkbenchApp) -> None:
        """Record a review event to the review history."""
        review = self.state.last_review
        if not review:
            return
        self.state.review_history.append(
            {
                "book": self.state.book,
                "chapter": self.state.chapter,
                "start_verse": review.start_verse,
                "end_verse": review.end_verse,
                "verdict": review.verdict,
                "summary": review.summary,
                "timestamp": time.time(),
            }
        )
        if len(self.state.review_history) > 20:
            self.state.review_history = self.state.review_history[-20:]

    def review_state_label(self: WorkbenchApp, verse: int) -> str:
        """Return a state label for a verse: DRAFT, REVIEWED, STAGED, COMMITTED."""
        chapter_doc = self.current_chapter()
        verse_map = self.bible_repo.verse_map(chapter_doc)
        if verse_map.get(verse, "").strip():
            return "COMMITTED"
        for update in self.state.pending_verse_updates:
            if update.book == self.state.book and update.chapter == self.state.chapter:
                if str(verse) in update.verses:
                    return "STAGED"
        if (
            self.state.last_review
            and self.state.last_review.start_verse <= verse <= self.state.last_review.end_verse
        ):
            return "REVIEWED"
        if self.state.draft_chunk.get(str(verse)):
            return "DRAFT"
        return "—"

    def review_summary_card(self: WorkbenchApp) -> list[str]:
        """Task 007: Clearer review summary with verdict and next actions."""
        review = self.state.last_review
        if not review:
            return ["No active review. Use /finalize to review the current draft."]
        lines = [
            f"Scope: {self.state.book} {self.state.chapter}:{review.start_verse}-{review.end_verse}",
            f"Verdict: {review.verdict.upper()}",
            f"Summary: {review.summary}",
        ]
        if review.issues:
            lines.append("Issues:")
            lines.extend(f"  • {issue}" for issue in review.issues)
        if review.title_review:
            lines.append(f"Title note: {review.title_review}")
        if review.justification_watch:
            lines.append("Justification watch:")
            lines.extend(f"  • {item}" for item in review.justification_watch)
        if review.verdict == "ready":
            lines.append("")
            lines.append(
                "Next actions: /stage → /commit, or /justify for individual verses"
            )
        else:
            lines.append("")
            lines.append(
                "Next actions: /revise to return to chat, /chat to edit, "
                "or /finalize to re-review"
            )
        return lines
