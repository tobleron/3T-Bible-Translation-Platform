from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

from ..utils import book_ref_code, parse_range, parse_reference, reference_key


class StudyChatCommandsMixin:
    """Mixin providing /chat, /study, /focus, /analysis commands."""

    def cmd_chat(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        self.state.mode = "CHAT"
        self.set_screen("CHAT", mode="CHAT")
        lines = [
            "Chat mode is active.",
            "Plain text now goes to the endpoint with the current study context.",
            "If no draft exists yet, the first chat turn will ask Qwen for an initial draft.",
            "Use /cancel to leave chat mode.",
        ]
        self.emit(self.theme.panel("Chat Mode", lines, accent="green"))

    def cmd_focus(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        if not args:
            self.print_error("Use /focus <verse|range>.")
            return
        start_verse, end_verse = parse_range(args[0])
        self.state.focus_start = start_verse
        self.state.focus_end = end_verse
        self.notify(f"Focus set to verses {start_verse}-{end_verse}.")

    def cmd_study(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        self.set_screen("STUDY", mode="COMMAND")
        start_verse, end_verse = self.current_range()
        if args:
            start_verse, end_verse = parse_range(args[0])
        if not self.lexical_repo.available():
            self.print_error("Lexical database not found. Run ./ttt.sh prep-data first.")
            return
        testament = self.testament()
        lines = [
            f"Scope: {self.state.book} {self.state.chapter}:{start_verse}-{end_verse}",
            f"Chunk authority: user-selected range",
            "",
        ]
        if testament == "old":
            lines.extend(self._ot_study_lines(start_verse, end_verse))
        else:
            lines.extend(self._nt_study_lines(start_verse, end_verse))
        lines.append("")
        lines.append(
            "Next: /chat to draft, /peek for comparison translations, "
            "/chunk-suggest for section ranges."
        )
        if self.application is None:
            self.emit(self.theme.panel("Study", lines, accent="orange"))

    def _ot_study_lines(self: WorkbenchApp, start_verse: int, end_verse: int) -> list[str]:
        """OT layout: Hebrew first, LXX directly below each verse. Compact impact words."""
        hebrew = self.lexical_repo.fetch_tokens(
            "hebrew_ot", self.state.book or "", self.state.chapter or 0, start_verse, end_verse
        )
        lxx = self.lexical_repo.fetch_tokens(
            "greek_ot_lxx", self.state.book or "", self.state.chapter or 0, start_verse, end_verse
        )
        lines = [
            "── Old Testament Study ──",
            "Primary: Hebrew (WLC)  |  Comparison: LXX (Vamvas)",
            "",
        ]
        for verse in range(start_verse, end_verse + 1):
            ref = self.lexical_ref(verse)
            heb_tokens = hebrew.get(ref, [])
            lxx_tokens = lxx.get(ref, [])
            heb_surface = " ".join(
                t.get("surface", "").strip() for t in heb_tokens if t.get("surface", "").strip()
            )
            heb_literal = " / ".join(
                (t.get("english") or t.get("gloss") or "")
                .replace("<br>", "; ")
                .strip()
                for t in heb_tokens
                if (t.get("english") or t.get("gloss"))
            )
            lines.append(f"{verse}. Heb: {heb_surface or '[missing]'}")
            if heb_literal:
                lines.append(f"    ↳ {heb_literal[:160]}")
            if lxx_tokens:
                lxx_surface = " ".join(
                    t.get("surface", "").strip() for t in lxx_tokens if t.get("surface", "").strip()
                )
                lxx_literal = " / ".join(
                    (t.get("gloss") or t.get("english") or "")
                    .replace("<br>", "; ")
                    .strip()
                    for t in lxx_tokens
                    if (t.get("gloss") or t.get("english"))
                )
                lines.append(f"    LXX: {lxx_surface or '[missing]'}")
                if lxx_literal:
                    lines.append(f"    ↳ {lxx_literal[:160]}")
            lines.append("")
        all_hebrew = [t for ref in hebrew.values() for t in ref]
        impact = self.important_words(all_hebrew, limit=5)
        if impact:
            lines.append(f"Impact: {'  |  '.join(impact)}")
            lines.append("")
        return lines

    def _nt_study_lines(self: WorkbenchApp, start_verse: int, end_verse: int) -> list[str]:
        """NT layout: Greek and literal English grouped tightly per verse."""
        greek = self.lexical_repo.fetch_tokens(
            "greek_nt", self.state.book or "", self.state.chapter or 0, start_verse, end_verse
        )
        lines = [
            "── New Testament Study ──",
            "Primary: SBLGNT Greek",
            "",
        ]
        collected: list[dict[str, str]] = []
        for verse in range(start_verse, end_verse + 1):
            ref = self.lexical_ref(verse)
            tokens = greek.get(ref, [])
            collected.extend(tokens)
            surface = " ".join(
                t.get("surface", "").strip() for t in tokens if t.get("surface", "").strip()
            )
            literal = " / ".join(
                (t.get("gloss") or t.get("english") or "")
                .replace("<br>", "; ")
                .strip()
                for t in tokens
                if (t.get("gloss") or t.get("english"))
            )
            lines.append(f"{verse}. {surface or '[missing]'}")
            if literal:
                lines.append(f"    ↳ {literal[:160]}")
            lines.append("")
        impact = self.important_words(collected, limit=5)
        if impact:
            lines.append(f"Impact: {'  |  '.join(impact)}")
            lines.append("")
        return lines

    def local_analysis_lines(
        self: WorkbenchApp, start_verse: int, end_verse: int, compare_sources: list[str]
    ) -> list[str]:
        chapter_doc = self.current_chapter()
        final_map = self.bible_repo.verse_map(chapter_doc)
        lines = [
            f"Scope: {self.state.book} {self.state.chapter}:{start_verse}-{end_verse}",
            "Mode: deterministic local analysis only",
            "",
            "SBLGNT:",
        ]
        for verse in range(start_verse, end_verse + 1):
            greek = self.source_repo.verse_text(
                "SBLGNT", self.state.book or "", self.state.chapter or 0, verse
            )
            lines.append(f"{verse}. {greek or '[missing]'}")
        lines.append("")
        lines.append("Current final text:")
        for verse in range(start_verse, end_verse + 1):
            text = self.state.draft_chunk.get(str(verse), final_map.get(verse, ""))
            lines.append(f"{verse}. {text or '[blank]'}")

        if compare_sources:
            lines.append("")
            for alias in compare_sources:
                lines.append(f"{alias}:")
                for verse in range(start_verse, end_verse + 1):
                    text = self.source_repo.verse_text(
                        alias, self.state.book or "", self.state.chapter or 0, verse
                    )
                    lines.append(f"{verse}. {text or '[missing]'}")

        just_doc = self.just_repo.load_document(
            self.state.book or "", self.state.chapter or 0
        ).doc
        relevant = [
            entry
            for entry in just_doc.get("justifications", [])
            if set(entry.get("verses", [])).intersection(range(start_verse, end_verse + 1))
        ]
        lines.append("")
        lines.append(
            f"Existing justifications touching this scope: {len(relevant)}"
        )
        lines.append(
            "Use /analysis refresh only when you want Qwen to generate "
            "fresh linguistic/editorial analysis."
        )
        return lines

    def sanitize_analysis_text(self: WorkbenchApp, text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"^\s*/no_think\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        if not cleaned:
            return ""
        if (
            "Observations:" not in cleaned
            and "Wording options:" not in cleaned
            and "Cautions:" not in cleaned
            and "Direction:" not in cleaned
        ):
            cleaned = "Analysis:\n" + cleaned
        return cleaned

    def cmd_analysis(self: WorkbenchApp, args: list[str]) -> None:
        if not self.require_open_chunk():
            return
        self.set_screen("STUDY", mode="COMMAND", reset_menu=False)
        if not args:
            start_verse, end_verse = self.current_range()
            self.emit(
                self.theme.panel(
                    "Local Analysis",
                    self.local_analysis_lines(start_verse, end_verse, []),
                    accent="orange",
                )
            )
            return
        action = args[0]
        if action == "local":
            start_verse, end_verse, source_args = self.parse_scope_tokens(
                args[1:],
                allow_reference=True,
                command_hint="/analysis local 1-17 or /analysis local Matthew 1:1-17",
            )
            compare_sources = []
            if source_args:
                try:
                    compare_sources = self.source_repo.resolve_sources(source_args)
                except KeyError as exc:
                    self.print_error(str(exc))
                    return
            self.emit(
                self.theme.panel(
                    "Local Analysis",
                    self.local_analysis_lines(start_verse, end_verse, compare_sources),
                    accent="orange",
                )
            )
            return
        if action not in {"show", "refresh"}:
            self.print_error(
                "Use /analysis, /analysis local <verse|range> [SRC1,SRC2], "
                "/analysis show <verse|range>, or /analysis refresh <verse|range> [SRC1,SRC2]"
            )
            return
        start_verse, end_verse, source_args = self.parse_scope_tokens(
            args[1:],
            allow_reference=True,
            command_hint="/analysis show 1-17 or /analysis show Matthew 1:1-17",
        )
        compare_sources = []
        if source_args:
            try:
                compare_sources = self.source_repo.resolve_sources(source_args)
            except KeyError as exc:
                self.print_error(str(exc))
                return
        key = (
            reference_key(self.state.book or "", self.state.chapter or 0, start_verse, end_verse)
            + "|"
            + ",".join(compare_sources)
        )
        if action == "show":
            cached = self.state.analysis_cache.get(key)
            if not cached:
                self.print_error("No cached analysis for that scope. Run /analysis refresh first.")
                return
            self.emit(self.theme.panel("Cached Analysis", cached.splitlines(), accent="orange"))
            return
        self.notify_busy(
            f"Refreshing analysis for {self.state.book} {self.state.chapter}:{start_verse}-{end_verse}...",
            label="analysis",
        )
        t0 = time.monotonic()
        prompt = self.build_analysis_prompt(start_verse, end_verse, compare_sources)
        raw_analysis = self.llm.complete(prompt, temperature=0.2, max_tokens=1800)
        analysis = self.sanitize_analysis_text(raw_analysis)
        duration = time.monotonic() - t0
        if not analysis or analysis.startswith("[ERROR]"):
            self.notify_error(
                label="analysis",
                message=(
                    "Qwen did not return usable analysis text. "
                    "Use /analysis for local deterministic context, then retry "
                    "/analysis refresh if needed."
                ),
                duration=duration,
            )
            return
        self.state.analysis_cache[key] = analysis
        self.state.analysis_meta[key] = {"sources": compare_sources, "range": [start_verse, end_verse]}
        self.notify_done(
            label="analysis",
            message=f"Analysis refreshed for {self.state.book} {self.state.chapter}:{start_verse}-{end_verse} ({duration:.1f}s)",
            duration=duration,
        )
        self.emit(self.theme.panel("Analysis Refreshed", analysis.splitlines(), accent="orange"))
