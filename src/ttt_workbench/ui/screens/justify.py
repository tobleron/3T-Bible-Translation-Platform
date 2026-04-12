from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class JustifyScreenMixin:
    """Mixin providing Justify screen rendering and autofill helpers."""

    def build_jautofill_prompt(self) -> str:
        draft = self.state.justify_draft
        verses = self.current_verse_map(include_draft=True)
        relevant = "\n".join(f"{verse}. {verses.get(verse, '')}" for verse in range(draft.start_verse, draft.end_verse + 1))
        return f"""
Draft a concise justification entry for a Bible translation editor.
Return strict JSON only:
{{
  "source_term": "optional source term",
  "decision": "decision wording",
  "reason": "one paragraph natural-language reason"
}}

Passage: {draft.book} {draft.chapter}:{draft.start_verse}-{draft.end_verse}
Verse text:
{relevant}

Current user notes:
Source term: {draft.source_term}
Decision: {draft.decision}
Reason notes: {draft.reason}
""".strip()

    def justify_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "JUSTIFY":
            draft = self.state.justify_draft
            return busy_prefix + [f"Drafting justification for verses {draft.start_verse}-{draft.end_verse}." if draft else "No active justification draft."]
        return []

    def render_justify_body(self):
        draft = self.state.justify_draft
        lines = []
        if draft:
            lines.extend([
                f"Range: {draft.start_verse}-{draft.end_verse}",
                f"Source term: {draft.source_term or '[optional]'}",
                f"Decision: {draft.decision or '[blank]'}",
                "",
                "Reason:",
                draft.reason or "[blank]",
            ])
        else:
            lines.append("No active justification draft.")
        return [self.line_block(lines)]
