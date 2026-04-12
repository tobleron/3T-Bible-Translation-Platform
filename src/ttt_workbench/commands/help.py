from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

from ..utils import parse_range


class HelpCommandsMixin:
    """Mixin providing /help, /history, /jobs, /cancel-job, /terms, /review-history, /quit."""

    def cmd_help(self: WorkbenchApp, args: list[str]) -> None:
        if not args:
            lines = [
                "Guide: docs/WORKBENCH_GUIDE.md",
                "",
                "/open Matthew 1         guided open with cached/model chunk suggestions",
                "/open Matthew 1:1-17    manual chunk override",
                "/chunk-suggest          load chunk suggestions for the current chapter window",
                "/chunk-use 1            open suggested chunk 1",
                "/chunk-range 1 1-17     edit a suggested range",
                "/chunk-type 1 story     edit a suggested type",
                '/chunk-title 1 "..."    edit a suggested title',
                "/chunk-refresh          force a new model chunking run",
                "/chunk-cache-clear      clear cached chunk suggestions for the current window",
                "/study                   deterministic chunk study view from lexical data",
                "/chat                    enter chat mode and auto-draft if needed",
                "/peek 2 ESV,NET,SBLGNT   inspect chosen source translations for one verse",
                "/analysis                deterministic local analysis for current focus",
                "/analysis show 2         show cached LLM analysis for a verse/range",
                "/analysis refresh 2 ESV,NET   rerun LLM analysis with optional comparison sources",
                "/finalize 1-17           run editorial review on the current draft",
                "/stage 1-17              stage reviewed text for commit",
                "/title show|refresh|set|stage|discard",
                "/justify 2-16            open justification mode",
                "/diff                    preview file changes",
                "/commit                  write staged changes",
                "/undo                    revert the latest commit",
                "/repair                  queue detected file repairs for commit",
                "/epub-gen                build the EPUB/MD/TXT outputs from committed JSON",
                "/discard 2               discard uncommitted draft/staged work for verse 2",
                "/cancel                  leave the current mode or clear the current review",
            ]
            self.emit(self.theme.panel("Help", lines, accent="yellow"))
            return
        topic = args[0].lower()
        topics = {
            "open": [
                "/open Matthew 1",
                "/open Matthew 1:1-17",
                "Book + chapter opens a guided chunk picker using cached/model suggestions. "
                "Book + chapter:range remains a manual override.",
            ],
            "chunk-suggest": [
                "/chunk-suggest",
                "Uses cached chunk suggestions when present, otherwise asks Qwen for "
                "chapter-window chunking based on the chunk taxonomy prompts.",
            ],
            "chunk-use": [
                "/chunk-use 1",
                "Opens one of the currently loaded chunk suggestions by number.",
            ],
            "chunk-range": [
                "/chunk-range 1 18-25",
                "Edits one suggested chunk range in memory. "
                "This also updates the chunk cache for the current window.",
            ],
            "chunk-type": [
                "/chunk-type 1 story",
                "Edits one suggested chunk type in memory and updates the cache.",
            ],
            "chunk-title": [
                '/chunk-title 1 "Birth of Jesus"',
                "Edits one suggested chunk title in memory and updates the cache.",
            ],
            "chunk-refresh": [
                "/chunk-refresh",
                "Forces Qwen to regenerate chunk suggestions for the current chapter window "
                "and overwrites the cache.",
            ],
            "chunk-cache-clear": [
                "/chunk-cache-clear",
                "/chunk-cache-clear all",
                "Clears cached chunk suggestions for the current window or for all windows.",
            ],
            "study": [
                "/study",
                "/study 1-17",
                "Shows a deterministic chunk study view. OT shows Hebrew first and LXX beside it. "
                "NT shows Greek. Literal English lines and impact words come from offline lexical data.",
            ],
            "chat": [
                "/chat",
                "Enters chat mode. If no draft exists, the workbench asks the endpoint "
                "for an SBLGNT-only initial draft and title.",
            ],
            "peek": [
                "/peek 2 ESV,NET,LSB",
                "Shows selected source texts for the chosen verse or range without feeding "
                "them back into /chat.",
            ],
            "analysis": [
                "/analysis",
                "/analysis local 1-17 ESV,NET",
                "/analysis show 1-17",
                "/analysis refresh 1-17 ESV,NET",
                "Default/local is deterministic and does no LLM calls. "
                "show reads cached LLM output. refresh forces a new LLM run.",
            ],
            "finalize": [
                "/finalize 1-17",
                "Runs an English/editorial review on the current draft. "
                "It does not stage or write.",
            ],
            "stage": [
                "/stage 1-17",
                "Moves the last reviewed draft text into the pending commit queue. "
                "Use /title separately for chunk titles.",
            ],
            "revise": [
                "/revise 1-17",
                "Returns to chat mode and carries the review notes forward as guidance.",
            ],
            "justify": [
                "/justify 2-16",
                "Opens justification mode. Use /jterm, /jdecision, /jreason, "
                "/jautofill, /jshow, /jstage, /jcancel.",
            ],
            "epub-gen": [
                "/epub-gen",
                "Runs the EPUB builder from src/ttt_epub using committed JSON "
                "files only. Commit staged changes first if you want them reflected in the output.",
            ],
            "discard": [
                "/discard 2",
                "/discard 1-17",
                "Deletes only uncommitted draft or staged work in the current session. "
                "It never erases committed JSON text.",
            ],
            "cancel": [
                "/cancel",
                "Leaves chat/justify mode or clears the active review without changing files.",
            ],
        }
        lines = topics.get(topic)
        if not lines:
            self.print_error(f"No help topic for '{topic}'.")
            return
        self.emit(self.theme.panel(f"Help: {topic}", lines, accent="yellow"))

    def cmd_history(self: WorkbenchApp, args: list[str]) -> None:
        limit = 10
        if args:
            try:
                limit = int(args[0])
            except ValueError:
                self.print_error("Use /history [n] where n is a number.")
                return
        entries = self.state.command_history[-limit:]
        if not entries:
            self.notify("No command history yet.")
            return
        lines = []
        for entry in reversed(entries):
            status_icon = "✓" if entry.status == "success" else "✗"
            lines.append(
                f"{status_icon} /{entry.command}  {entry.duration_seconds:.1f}s  {entry.message or ''}"
            )
        self.emit(self.theme.panel("Command History", lines, accent="purple"))

    def cmd_jobs(self: WorkbenchApp, args: list[str]) -> None:
        active = self.job_runner.active_jobs()
        recent = self.job_runner.recent_jobs(5)
        lines = []
        if active:
            lines.append("Active jobs:")
            for job in active:
                lines.append(f"  {job.job_id[:6]}  {job.label}  {job.elapsed_display}")
        else:
            lines.append("No active jobs.")
        if recent:
            lines.append("")
            lines.append("Recent jobs:")
            for job in recent:
                icon = {"completed": "✓", "failed": "✗", "cancelled": "○"}.get(
                    job.status.value, "?"
                )
                lines.append(
                    f"  {icon} {job.job_id[:6]}  {job.label}  {job.status.value}  {job.elapsed_display}"
                )
        self.emit(self.theme.panel("Background Jobs", lines, accent="purple"))

    def cmd_cancel_job(self: WorkbenchApp, args: list[str]) -> None:
        active = self.job_runner.active_jobs()
        if not active:
            self.notify("No active jobs to cancel.")
            return
        if args:
            job_id = args[0]
            matched = [j for j in active if j.job_id.startswith(job_id)]
            if len(matched) == 1:
                matched[0].cancel()
                self.notify(
                    f"Job {matched[0].job_id[:6]} ({matched[0].label}) cancelled."
                )
            elif len(matched) > 1:
                self.print_error("Ambiguous job ID prefix.")
            else:
                self.print_error("Job not found.")
            return
        count = self.job_runner.cancel_all()
        self.notify(f"Cancelled {count} active job(s).")

    def cmd_terms(self: WorkbenchApp, args: list[str]) -> None:
        """Task 005: Manage the terminology ledger."""
        if not args:
            lines = self.terminology_ledger_lines()
            self.emit(self.theme.panel("Terminology Ledger", lines, accent="aqua"))
            return
        action = args[0].lower()
        if action == "show":
            lines = self.terminology_ledger_lines()
            self.emit(self.theme.panel("Terminology Ledger", lines, accent="aqua"))
            return
        if action == "add":
            if len(args) < 3:
                self.print_error("Use /terms add <source_term> <translation> [notes]")
                return
            source_term = args[1]
            translation = args[2]
            notes = " ".join(args[3:]) if len(args) > 3 else ""
            key = source_term.lower()
            entry = TerminologyEntry(
                source_term=source_term,
                translation=translation,
                status="approved",
                notes=notes,
                added_at=time.time(),
            )
            self.state.terminology_ledger[key] = entry
            self.notify(f"Added to ledger: {source_term} → {translation}")
            return
        if action == "approve":
            if len(args) < 2:
                self.print_error("Use /terms approve <source_term>")
                return
            key = args[1].lower()
            entry = self.state.terminology_ledger.get(key)
            if not entry:
                self.print_error(f"Term '{args[1]}' not found in ledger.")
                return
            entry.status = "approved"
            self.notify(f"Approved: {entry.source_term} → {entry.translation}")
            return
        if action == "reject":
            if len(args) < 2:
                self.print_error("Use /terms reject <source_term>")
                return
            key = args[1].lower()
            entry = self.state.terminology_ledger.get(key)
            if not entry:
                self.print_error(f"Term '{args[1]}' not found in ledger.")
                return
            entry.status = "rejected"
            self.notify(f"Rejected: {entry.source_term}")
            return
        if action == "clear":
            count = len(self.state.terminology_ledger)
            self.state.terminology_ledger.clear()
            self.notify(f"Cleared {count} term(s) from the ledger.")
            return
        self.print_error("Use /terms show|add|approve|reject|clear")

    def cmd_review_history(self: WorkbenchApp, args: list[str]) -> None:
        """Task 007: Show recent review decisions."""
        limit = 10
        if args:
            try:
                limit = int(args[0])
            except ValueError:
                self.print_error("Use /review-history [n].")
                return
        entries = self.state.review_history[-limit:]
        if not entries:
            self.notify("No review history yet. Use /finalize to review a draft.")
            return
        lines = []
        for entry in reversed(entries):
            icon = "✓" if entry["verdict"] == "ready" else "○"
            lines.append(
                f"{icon} {entry['book']} {entry['chapter']}:"
                f"{entry['start_verse']}-{entry['end_verse']}  "
                f"{entry['verdict'].upper()}  {entry['summary'][:80]}"
            )
        self.emit(self.theme.panel("Review History", lines, accent="orange"))

    def cmd_quit(self: WorkbenchApp, args: list[str]) -> None:
        self.exit_requested = True
        self.save_state()
        if self.application is not None:
            self.application.exit()
            return
        self.emit(self.theme.panel("Exit", ["Session saved."], accent="blue"))
        raise SystemExit(0)

    def terminology_ledger_lines(self: WorkbenchApp) -> list[str]:
        """Return formatted lines showing the approved terminology ledger."""
        if not self.state.terminology_ledger:
            return ["No terms in the ledger yet."]
        lines = []
        for key, entry in sorted(self.state.terminology_ledger.items()):
            icon = {"approved": "✓", "rejected": "✗", "pending": "?"}.get(
                entry.status, "·"
            )
            line = f"{icon} {entry.source_term} → {entry.translation}"
            if entry.notes:
                line += f"  ({entry.notes})"
            lines.append(line)
        return lines

    def terminology_prompt_block(self: WorkbenchApp) -> str:
        """Build a prompt injection block with only approved terms."""
        approved = [
            e for e in self.state.terminology_ledger.values() if e.status == "approved"
        ]
        if not approved:
            return "No approved terminology decisions yet."
        lines = ["Approved terminology (use these consistently):"]
        for entry in approved:
            lines.append(f"- {entry.source_term} → {entry.translation}")
            if entry.notes:
                lines.append(f"  Note: {entry.notes}")
        return "\n".join(lines)
