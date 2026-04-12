from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ChunkPickerScreenMixin:
    """Mixin providing Chunk Picker screen rendering and cache helpers."""

    def chunk_cache_key(self, book: str, chapter: int, window_start: int, window_end: int) -> str:
        from ...utils import normalize_book_key
        return f"{normalize_book_key(book)}_{chapter}_{window_start}_{window_end}_{self.chunk_prompt_version}"

    def chunk_cache_path(self, book: str, chapter: int, window_start: int, window_end: int) -> Path:
        return self.paths.chunk_cache_dir / f"{self.chunk_cache_key(book, chapter, window_start, window_end)}.json"

    def load_chunk_cache(self, book: str, chapter: int, window_start: int, window_end: int) -> dict | None:
        path = self.chunk_cache_path(book, chapter, window_start, window_end)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_chunk_cache(self, book: str, chapter: int, window_start: int, window_end: int, payload: dict) -> None:
        path = self.chunk_cache_path(book, chapter, window_start, window_end)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def load_chunk_prompts(self) -> tuple[str, str, str]:
        schema = (self.paths.chunking_prompts_dir / "chunk_schema.txt").read_text(encoding="utf-8")
        ot = (self.paths.chunking_prompts_dir / "ot_chunk_suggest.txt").read_text(encoding="utf-8")
        nt = (self.paths.chunking_prompts_dir / "nt_chunk_suggest.txt").read_text(encoding="utf-8")
        return schema, ot, nt

    def chapter_window(self, book: str, chapter: int) -> tuple[int, int]:
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

    def build_chunk_prompt(self, book: str, chapter: int, window_start: int, window_end: int) -> str:
        schema, ot_prompt, nt_prompt = self.load_chunk_prompts()
        testament = self.bible_repo.testament_for(book, chapter)
        witness_prompt = ot_prompt if testament == "old" else nt_prompt
        original_context = self.chunk_study_context(
            book, chapter, window_start, window_end, testament
        )
        return f"""/no_think
Model profile: qwen3.5 35B A3B thinking model.
{witness_prompt}

Window to segment: {book} {chapter}:{window_start}-{window_end}

Original-language context:
{original_context}

{schema}
""".strip()

    def chunk_study_context(self, book: str, chapter: int, start_verse: int, end_verse: int, testament: str) -> str:
        from ...utils import book_ref_code
        lines: list[str] = []
        if testament == "old":
            hebrew = self.lexical_repo.fetch_tokens("hebrew_ot", book, chapter, start_verse, end_verse)
            lxx = self.lexical_repo.fetch_tokens("greek_ot_lxx", book, chapter, start_verse, end_verse)
            for verse in range(start_verse, end_verse + 1):
                ref = f"{book_ref_code(book)}.{chapter}.{verse}"
                lines.append(f"{verse} Hebrew: " + " ".join(token.get("surface", "") for token in hebrew.get(ref, [])))
                lines.append(f"{verse} Hebrew literal: " + " / ".join((token.get("gloss") or token.get("english") or "").replace("<br>", "; ") for token in hebrew.get(ref, []) if (token.get("gloss") or token.get("english"))))
                if lxx.get(ref):
                    lines.append(f"{verse} LXX: " + " ".join(token.get("surface", "") for token in lxx.get(ref, [])))
        else:
            greek = self.lexical_repo.fetch_tokens("greek_nt", book, chapter, start_verse, end_verse)
            for verse in range(start_verse, end_verse + 1):
                ref = f"{book_ref_code(book)}.{chapter}.{verse}"
                lines.append(f"{verse} Greek: " + " ".join(token.get("surface", "") for token in greek.get(ref, [])))
                lines.append(f"{verse} Greek literal: " + " / ".join((token.get("gloss") or token.get("english") or "").replace("<br>", "; ") for token in greek.get(ref, []) if (token.get("gloss") or token.get("english"))))
        return "\n".join(lines)

    def set_chunk_suggestions_from_payload(self, book: str, chapter: int, window_start: int, window_end: int, payload: dict) -> None:
        from ...models import ChunkSuggestion
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

    def ensure_chunk_suggestions(self, book: str, chapter: int, *, force_refresh: bool = False) -> tuple[int, int, str]:
        window_start, window_end = self.chapter_window(book, chapter)
        if not force_refresh:
            cached = self.load_chunk_cache(book, chapter, window_start, window_end)
            if isinstance(cached, dict) and isinstance(cached.get("chunks"), list):
                self.set_chunk_suggestions_from_payload(book, chapter, window_start, window_end, cached)
                return window_start, window_end, "cache"
        prompt = self.build_chunk_prompt(book, chapter, window_start, window_end)
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

    def chunk_lines(self, *, with_preview: bool = False) -> list[str]:
        lines: list[str] = []
        testament = (
            self.bible_repo.testament_for(self.state.book, self.state.chapter)
            if self.state.book and self.state.chapter
            else "new"
        )
        for index, chunk in enumerate(self.state.chunk_suggestions, start=1):
            lines.append(f"{index}. {chunk.start_verse}-{chunk.end_verse}  [{chunk.type}]  {chunk.title}")
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
                    lines.append(f"   \u25b6 {preview}")
        return lines or ["No chunk suggestions loaded."]

    def chunk_preview_lines(self, index: int) -> list[str]:
        if not self.state.chunk_suggestions or index < 1 or index > len(self.state.chunk_suggestions):
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
            preview = self.source_repo.verse_text(source, self.state.book, self.state.chapter, chunk.start_verse)
            if preview:
                lines.append(f"  Opening verse ({source} {chunk.start_verse}):")
                lines.append(f"    {preview[:200]}")
            draft_text = self.state.draft_chunk.get(str(chunk.start_verse))
            if draft_text:
                lines.append(f"  Current draft:")
                lines.append(f"    {draft_text[:200]}")
        lines.append("")
        lines.append("Actions: /chunk-use, /chunk-range, /chunk-type, /chunk-title")
        return lines

    def chunk_picker_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "CHUNK_PICKER":
            return busy_prefix + [
                f"Chapter: {self.state.wizard_book or self.state.book} {self.state.wizard_chapter or self.state.chapter}",
                f"Suggestions loaded: {len(self.state.chunk_suggestions)}",
            ]
        return []

    def render_chunk_picker_body(self):
        blocks: list[object] = []
        if self.state.screen == "CHUNK_PICKER":
            lines = [
                f"Chapter: {self.state.wizard_book or self.state.book} {self.state.wizard_chapter or self.state.chapter}",
                f"Suggestions loaded: {len(self.state.chunk_suggestions)}",
                "",
                *self.chunk_lines(),
            ]
            blocks.append(self.line_block(lines))
        return blocks
