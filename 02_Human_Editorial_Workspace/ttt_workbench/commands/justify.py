from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

from ..models import JustificationDraft, PendingJustificationUpdate
from ..utils import parse_range


class JustifyCommandsMixin:
    """Mixin providing /justify, /jterm, /jdecision, /jreason, /jshow, /jautofill, /jstage, /jcancel."""

    def cmd_justify(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        if not args:
            self.print_error("Use /justify <verse|range>.")
            return
        start_verse, end_verse = parse_range(args[0])
        self.state.justify_draft = JustificationDraft(
            book=self.state.book or "",
            chapter=self.state.chapter or 0,
            start_verse=start_verse,
            end_verse=end_verse,
            verses=list(range(start_verse, end_verse + 1)),
        )
        self.state.mode = "JUSTIFY"
        self.set_screen("JUSTIFY", mode="JUSTIFY")
        lines = [
            f"Justification mode for verses {start_verse}-{end_verse}",
            "Use /jterm, /jdecision, /jreason, /jautofill, /jshow, /jstage, /jcancel.",
            "Plain text will append to the reason notes.",
        ]
        self.emit(self.theme.panel("Justification Mode", lines, accent="yellow"))

    def cmd_jterm(self: WorkbenchApp, args: list[str]) -> None:
        if not self.state.justify_draft:
            self.print_error("No active justification draft.")
            return
        self.state.justify_draft.source_term = " ".join(args).strip()
        self.notify("Updated justification source term.")

    def cmd_jdecision(self: WorkbenchApp, args: list[str]) -> None:
        if not self.state.justify_draft:
            self.print_error("No active justification draft.")
            return
        self.state.justify_draft.decision = " ".join(args).strip()
        self.notify("Updated justification decision.")

    def cmd_jreason(self: WorkbenchApp, args: list[str]) -> None:
        if not self.state.justify_draft:
            self.print_error("No active justification draft.")
            return
        self.state.justify_draft.reason = " ".join(args).strip()
        self.notify("Updated justification reason.")

    def cmd_jshow(self: WorkbenchApp, args: list[str]) -> None:
        draft = self.state.justify_draft
        if not draft:
            self.print_error("No active justification draft.")
            return
        lines = [
            f"Range: {', '.join(str(verse) for verse in (draft.verses or list(range(draft.start_verse, draft.end_verse + 1))))}",
            f"Source term: {draft.source_term or '[optional]'}",
            f"Decision: {draft.decision or '[blank]'}",
            "Reason:",
            draft.reason or "[blank]",
        ]
        self.emit(self.theme.panel("Justification Draft", lines, accent="yellow"))

    def cmd_jautofill(self: WorkbenchApp, args: list[str]) -> None:
        if not self.state.justify_draft:
            self.print_error("No active justification draft.")
            return
        self.notify_busy("Drafting justification text...", label="jautofill")
        t0 = time.monotonic()
        payload, raw, attempts = self.llm.complete_json(
            self.build_jautofill_prompt(),
            required_keys=["source_term", "decision", "reason"],
            temperature=0.25,
            max_tokens=900,
            max_attempts=3,
        )
        duration = time.monotonic() - t0
        if not isinstance(payload, dict):
            self.notify_error(
                label="jautofill",
                message="The endpoint did not return a valid justification draft.",
                duration=duration,
            )
            return
        self.state.justify_draft.source_term = payload.get(
            "source_term", self.state.justify_draft.source_term
        ).strip()
        self.state.justify_draft.decision = payload.get(
            "decision", self.state.justify_draft.decision
        ).strip()
        self.state.justify_draft.reason = payload.get(
            "reason", self.state.justify_draft.reason
        ).strip()
        self.notify_done(
            label="jautofill",
            message=f"Justification draft generated ({duration:.1f}s)",
            duration=duration,
        )
        self.cmd_jshow([])

    def cmd_jstage(self: WorkbenchApp, args: list[str]) -> None:
        draft = self.state.justify_draft
        if not draft:
            self.print_error("No active justification draft.")
            return
        if not draft.decision or not draft.reason:
            self.print_error(
                "A justification needs at least a decision and a reason before it can be staged."
            )
            return
        just_file = self.just_repo.load_document(draft.book, draft.chapter)
        existing_ids = {
            entry["id"]
            for entry in just_file.doc.get("justifications", [])
            if isinstance(entry, dict) and "id" in entry
        }
        verse_map = self.current_verse_map(include_draft=True)
        entry = self.just_repo.build_entry(
            draft.book,
            draft.chapter,
            draft.start_verse,
            draft.end_verse,
            draft.verses,
            draft.source_term,
            draft.decision,
            draft.reason,
            verse_map,
            existing_ids,
            entry_id=draft.entry_id,
        )
        self.state.pending_justification_updates = [
            item
            for item in self.state.pending_justification_updates
            if not (
                item.book == draft.book
                and item.chapter == draft.chapter
                and str(item.entry.get("id", "")).strip() == str(entry.get("id", "")).strip()
            )
        ]
        self.state.pending_justification_updates.append(
            PendingJustificationUpdate(book=draft.book, chapter=draft.chapter, entry=entry)
        )
        self.state.mode = "COMMAND"
        self.state.justify_draft = None
        self.set_screen("REVIEW", mode="COMMAND")
        self.notify("Justification staged.")

    def cmd_jcancel(self: WorkbenchApp, args: list[str]) -> None:
        if self.state.justify_draft:
            self.state.justify_draft = None
            self.state.mode = "COMMAND"
            self.set_screen("REVIEW", mode="COMMAND")
            self.notify("Justification draft cancelled.")
            return
        self.print_error("No active justification draft.")
