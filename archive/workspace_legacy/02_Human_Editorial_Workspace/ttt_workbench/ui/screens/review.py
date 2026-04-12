from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ReviewScreenMixin:
    """Mixin providing Review screen rendering and editorial analysis helpers."""

    def build_analysis_prompt(self, start_verse: int, end_verse: int, compare_sources: list[str]) -> str:
        sblgnt = self.source_repo.verse_range("SBLGNT", self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
        compare_blocks = []
        for alias in compare_sources:
            data = self.source_repo.verse_range(alias, self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
            if data:
                compare_blocks.append(f"{alias}:\n" + "\n".join(f"{verse}. {text}" for verse, text in data.items()))
        compare_text = "\n\n".join(compare_blocks) if compare_blocks else "No comparison translations were supplied."
        return f"""
/no_think
You are producing original-language analysis for a Bible translation editor.
Use the legacy analysis prompt as style guidance, but adapt it to the current task.
When comparison translations are provided, summarize their variant choices; otherwise focus on Greek/Hebrew detail.

Constraints:
- Do not include visible reasoning or <think> tags.
- Be concise and concrete.
- Use exactly these section headings:
  Observations:
  Wording options:
  Cautions:
  Direction:
- Under the first three headings, use short bullet points.
- Under Direction, give one short paragraph.

Legacy prompt:
{self.legacy_prompt}

Passage: {self.state.book} {self.state.chapter}:{start_verse}-{end_verse}

SBLGNT:
{chr(10).join(f"{verse}. {text}" for verse, text in sblgnt.items())}

Comparison translations:
{compare_text}

Return concise but useful analysis with:
1. Original-language observations
2. Important wording options
3. Translation cautions
4. Recommended direction
""".strip()

    def sanitize_analysis_text(self, text: str) -> str:
        cleaned = re.sub(r"<\|begin_of_thought\|>.*?<\|end_of_thought\|>", "", text, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"^\s*/no_think\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        if not cleaned:
            return ""
        if "Observations:" not in cleaned and "Wording options:" not in cleaned and "Cautions:" not in cleaned and "Direction:" not in cleaned:
            cleaned = "Analysis:\n" + cleaned
        return cleaned

    def build_finalize_prompt(self, start_verse: int, end_verse: int) -> str:
        candidate_lines = []
        for verse in range(start_verse, end_verse + 1):
            text = self.state.draft_chunk.get(str(verse))
            if text:
                candidate_lines.append(f"{verse}. {text}")
        title = self.state.draft_title or "(no title draft)"
        return f"""
You are acting as an English Bible editor reviewing a candidate translation.
Return strict JSON only:
{{
  "summary": "short summary",
  "issues": ["issue 1", "issue 2"],
  "verdict": "ready" or "revise",
  "title_review": "brief note"
}}

Passage: {self.state.book} {self.state.chapter}:{start_verse}-{end_verse}
Candidate title: {title}
Candidate text:
{chr(10).join(candidate_lines)}
""".strip()

    def build_title_prompt(self) -> str:
        start = self.state.chunk_start
        end = self.state.chunk_end
        draft = "\n".join(self.open_reference_summary())
        return f"""
Suggest a short Bible chunk title.

Rules:
- 2 to 6 words
- plain English
- suitable as a section heading
- avoid devotional embellishment
- return strict JSON only

JSON shape:
{{
  "title": "main title",
  "alternatives": ["alt 1", "alt 2", "alt 3"],
  "reason": "short rationale"
}}

Passage: {self.state.book} {self.state.chapter}:{start}-{end}
Current draft:
{draft}
""".strip()

    def review_state_label(self, verse: int) -> str:
        chapter_doc = self.current_chapter()
        verse_map = self.bible_repo.verse_map(chapter_doc)
        if verse_map.get(verse, "").strip():
            return "COMMITTED"
        for update in self.state.pending_verse_updates:
            if update.book == self.state.book and update.chapter == self.state.chapter:
                if str(verse) in update.verses:
                    return "STAGED"
        if self.state.last_review and self.state.last_review.start_verse <= verse <= self.state.last_review.end_verse:
            return "REVIEWED"
        if self.state.draft_chunk.get(str(verse)):
            return "DRAFT"
        return "\u2014"

    def review_summary_card(self) -> list[str]:
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
            lines.extend(f"  \u2022 {issue}" for issue in review.issues)
        if review.title_review:
            lines.append(f"Title note: {review.title_review}")
        if review.justification_watch:
            lines.append("Justification watch:")
            lines.extend(f"  \u2022 {item}" for item in review.justification_watch)
        if review.verdict == "ready":
            lines.append("")
            lines.append("Next actions: /stage \u2192 /commit, or /justify for individual verses")
        else:
            lines.append("")
            lines.append("Next actions: /revise to return to chat, /chat to edit, or /finalize to re-review")
        return lines

    def record_review_event(self) -> None:
        import time
        review = self.state.last_review
        if not review:
            return
        self.state.review_history.append({
            "book": self.state.book,
            "chapter": self.state.chapter,
            "start_verse": review.start_verse,
            "end_verse": review.end_verse,
            "verdict": review.verdict,
            "summary": review.summary,
            "timestamp": time.time(),
        })
        if len(self.state.review_history) > 20:
            self.state.review_history = self.state.review_history[-20:]

    def render_status(self) -> None:
        if self.application is not None:
            self.application.invalidate()
            return
        badges = [
            self.theme.status_badge("MODE", self.state.mode, {"COMMAND": "blue", "CHAT": "green", "JUSTIFY": "yellow"}.get(self.state.mode, "aqua")),
            self.theme.status_badge("MODEL", self.model_label, "purple"),
        ]
        if self.state.book and self.state.chapter and self.state.chunk_start and self.state.chunk_end:
            badges.append(self.theme.status_badge("CHUNK", f"{self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}", "aqua"))
        self.emit(self.theme.badge_row(badges))
        lines = []
        if self.state.book:
            focus_start, focus_end = self.current_range()
            lines.append(f"Focus {focus_start}-{focus_end} | Draft {len(self.state.draft_chunk)} | Pending text {len(self.state.pending_verse_updates)} | Justifications {len(self.state.pending_justification_updates)} | Repairs {len(self.state.pending_repairs)}")
            if self.state.draft_title:
                lines.append(f"Draft title: {self.state.draft_title}")
            lines.append("Type / for commands")
            if self.state.pending_repairs:
                lines.append("Repairs queued. Use /repair to inspect or /commit to apply them.")
        else:
            lines.append("Use /open Matthew 1:1-17 to begin.")
            lines.append("Type / for commands")
        self.emit(self.theme.panel("Status", lines, accent="blue"))

    def review_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "REVIEW":
            return busy_prefix + [f"Chunk: {self.current_chunk_label()}", "Review the editorial verdict and stage what is ready."]
        return []

    def render_review_body(self):
        return [self.line_block(self.review_summary_card())]
