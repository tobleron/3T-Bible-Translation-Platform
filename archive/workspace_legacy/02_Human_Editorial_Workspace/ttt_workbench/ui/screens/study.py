from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class StudyScreenMixin:
    """Mixin providing Study screen rendering and lexical analysis helpers."""

    def current_chapter(self) -> dict:
        return self.bible_repo.load_chapter(self.state.book or "", self.state.chapter or 0).doc

    def current_verse_map(self, include_draft: bool = False) -> dict[int, str]:
        verse_map = self.bible_repo.verse_map(self.current_chapter())
        if include_draft:
            for verse, text in self.state.draft_chunk.items():
                verse_map[int(verse)] = text
        return verse_map

    def testament(self) -> str:
        if not self.require_open_chunk():
            return ""
        return self.bible_repo.testament_for(self.state.book or "", self.state.chapter or 0)

    def lexical_ref(self, verse: int) -> str:
        from ...utils import book_ref_code
        return f"{book_ref_code(self.state.book or '')}.{self.state.chapter}.{verse}"

    def important_words(self, tokens: list[dict[str, str]], *, limit: int = 8) -> list[str]:
        stopwords = {
            "and", "the", "of", "to", "in", "on", "for", "with", "by", "from", "at", "a", "an",
            "he", "she", "it", "they", "him", "her", "them", "his", "its", "their", "be", "is",
            "was", "were", "are", "that", "this", "who", "which", "as", "into", "upon", "above",
            "under", "through", "or", "but", "if", "then", "there", "here", "one", "each",
        }
        scored: list[tuple[int, str]] = []
        seen: set[str] = set()
        for token in tokens:
            gloss = (token.get("gloss") or token.get("english") or "").replace("<br>", "; ").strip(" ;")
            lemma = (token.get("lemma") or token.get("surface") or "").strip()
            morph = (token.get("morph") or "").upper()
            if not gloss or not lemma:
                continue
            first_gloss = gloss.split(";")[0].split("/")[0].strip().lower()
            if not first_gloss or first_gloss in stopwords:
                continue
            key = f"{lemma}|{first_gloss}"
            if key in seen:
                continue
            seen.add(key)
            score = 1
            if morph.startswith(("N", "V", "A")) or "N-" in morph or "V-" in morph or "A-" in morph:
                score += 2
            if any(ch in gloss for ch in [";", "/", "\u00bb", ":"]):
                score += 1
            if len(first_gloss) >= 6:
                score += 1
            scored.append((score, f"{lemma}: {gloss}"))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[1] for item in scored[:limit]]

    def study_lines_for_tokens(self, label: str, tokens_by_ref: dict[str, list[dict[str, str]]], start_verse: int, end_verse: int, *, surface_key: str = "surface", english_mode: str = "gloss") -> list[str]:
        lines = [label]
        collected: list[dict[str, str]] = []
        for verse in range(start_verse, end_verse + 1):
            ref = self.lexical_ref(verse)
            tokens = tokens_by_ref.get(ref, [])
            collected.extend(tokens)
            surface_line = " ".join(token.get(surface_key, "").strip() for token in tokens if token.get(surface_key, "").strip())
            lines.append(f"{verse}. {surface_line or '[missing]'}")
        lines.append("")
        lines.append("Literal English")
        for verse in range(start_verse, end_verse + 1):
            ref = self.lexical_ref(verse)
            tokens = tokens_by_ref.get(ref, [])
            parts = []
            for token in tokens:
                value = (token.get(english_mode) or token.get("english") or token.get("gloss") or "").replace("<br>", "; ").strip()
                if value:
                    parts.append(value)
            lines.append(f"{verse}. {' / '.join(parts) if parts else '[missing]'}")
        impact = self.important_words(collected)
        if impact:
            lines.append("")
            lines.append("Impact Words")
            lines.extend(f"- {item}" for item in impact)
        return lines

    def _ot_study_lines(self, start_verse: int, end_verse: int) -> list[str]:
        hebrew = self.lexical_repo.fetch_tokens("hebrew_ot", self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
        lxx = self.lexical_repo.fetch_tokens("greek_ot_lxx", self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
        lines = [
            "\u2500\u2500 Old Testament Study \u2500\u2500",
            "Primary: Hebrew (WLC)  |  Comparison: LXX (Vamvas)",
            "",
        ]
        for verse in range(start_verse, end_verse + 1):
            ref = self.lexical_ref(verse)
            heb_tokens = hebrew.get(ref, [])
            lxx_tokens = lxx.get(ref, [])
            heb_surface = " ".join(t.get("surface", "").strip() for t in heb_tokens if t.get("surface", "").strip())
            heb_literal = " / ".join(
                (t.get("english") or t.get("gloss") or "").replace("<br>", "; ").strip()
                for t in heb_tokens if (t.get("english") or t.get("gloss"))
            )
            lines.append(f"{verse}. Heb: {heb_surface or '[missing]'}")
            if heb_literal:
                lines.append(f"    \u21b3 {heb_literal[:160]}")
            if lxx_tokens:
                lxx_surface = " ".join(t.get("surface", "").strip() for t in lxx_tokens if t.get("surface", "").strip())
                lxx_literal = " / ".join(
                    (t.get("gloss") or t.get("english") or "").replace("<br>", "; ").strip()
                    for t in lxx_tokens if (t.get("gloss") or t.get("english"))
                )
                lines.append(f"    LXX: {lxx_surface or '[missing]'}")
                if lxx_literal:
                    lines.append(f"    \u21b3 {lxx_literal[:160]}")
            lines.append("")
        all_hebrew = [t for ref in hebrew.values() for t in ref]
        impact = self.important_words(all_hebrew, limit=5)
        if impact:
            lines.append(f"Impact: {'  |  '.join(impact)}")
            lines.append("")
        return lines

    def _nt_study_lines(self, start_verse: int, end_verse: int) -> list[str]:
        greek = self.lexical_repo.fetch_tokens("greek_nt", self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
        lines = [
            "\u2500\u2500 New Testament Study \u2500\u2500",
            "Primary: SBLGNT Greek",
            "",
        ]
        collected: list[dict[str, str]] = []
        for verse in range(start_verse, end_verse + 1):
            ref = self.lexical_ref(verse)
            tokens = greek.get(ref, [])
            collected.extend(tokens)
            surface = " ".join(t.get("surface", "").strip() for t in tokens if t.get("surface", "").strip())
            literal = " / ".join(
                (t.get("gloss") or t.get("english") or "").replace("<br>", "; ").strip()
                for t in tokens if (t.get("gloss") or t.get("english"))
            )
            lines.append(f"{verse}. {surface or '[missing]'}")
            if literal:
                lines.append(f"    \u21b3 {literal[:160]}")
            lines.append("")
        impact = self.important_words(collected, limit=5)
        if impact:
            lines.append(f"Impact: {'  |  '.join(impact)}")
            lines.append("")
        return lines

    def study_context_block(self, start_verse: int, end_verse: int) -> str:
        from ...utils import book_ref_code
        if not self.lexical_repo.available():
            return "Lexical database unavailable."
        testament = self.testament()
        lines: list[str] = []
        if testament == "old":
            hebrew = self.lexical_repo.fetch_tokens("hebrew_ot", self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
            lxx = self.lexical_repo.fetch_tokens("greek_ot_lxx", self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
            lines.append("Primary witness: Hebrew")
            for verse in range(start_verse, end_verse + 1):
                ref = self.lexical_ref(verse)
                lines.append(f"{verse} Hebrew: " + " ".join(token.get("surface", "") for token in hebrew.get(ref, [])))
                lines.append(f"{verse} Hebrew literal: " + " / ".join((token.get("english") or token.get("gloss") or "").replace("<br>", "; ") for token in hebrew.get(ref, []) if (token.get("english") or token.get("gloss"))))
                if lxx.get(ref):
                    lines.append(f"{verse} LXX: " + " ".join(token.get("surface", "") for token in lxx.get(ref, [])))
                    lines.append(f"{verse} LXX literal: " + " / ".join((token.get("gloss") or token.get("english") or "").replace("<br>", "; ") for token in lxx.get(ref, []) if (token.get("gloss") or token.get("english"))))
            hebrew_words = self.important_words([token for ref in hebrew.values() for token in ref])
            if hebrew_words:
                lines.append("Hebrew impact words: " + " | ".join(hebrew_words))
            lxx_words = self.important_words([token for ref in lxx.values() for token in ref])
            if lxx_words:
                lines.append("LXX impact words: " + " | ".join(lxx_words))
        else:
            greek = self.lexical_repo.fetch_tokens("greek_nt", self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
            lines.append("Primary witness: SBLGNT Greek")
            for verse in range(start_verse, end_verse + 1):
                ref = f"{book_ref_code(self.state.book or '')}.{self.state.chapter}.{verse}"
                lines.append(f"{verse} Greek: " + " ".join(token.get("surface", "") for token in greek.get(ref, [])))
                lines.append(f"{verse} Greek literal: " + " / ".join((token.get("gloss") or token.get("english") or "").replace("<br>", "; ") for token in greek.get(ref, []) if (token.get("gloss") or token.get("english"))))
            greek_words = self.important_words([token for ref in greek.values() for token in ref])
            if greek_words:
                lines.append("Greek impact words: " + " | ".join(greek_words))
        return "\n".join(line for line in lines if line.strip())

    def study_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "STUDY":
            return busy_prefix + [f"Chunk: {self.current_chunk_label()}", "Review the deterministic source study before drafting."]
        return []

    def render_study_body(self):
        if not self.has_open_chunk():
            return []
        start_verse, end_verse = self.current_range()
        lines = self._ot_study_lines(start_verse, end_verse) if self.testament() == "old" else self._nt_study_lines(start_verse, end_verse)
        if len(lines) > 28:
            lines = lines[:28] + ["", "\u2026 Use /focus or /study <range> to narrow the view."]
        return [self.line_block(lines)]
