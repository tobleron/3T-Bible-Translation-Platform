from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class CommitPreviewScreenMixin:
    """Mixin providing Commit Preview screen rendering and commit plan helpers."""

    def build_commit_plan(self) -> list[tuple]:
        import json
        writes: list[tuple] = []
        grouped_text: dict[tuple[str, int], dict[int, str]] = {}
        for pending in self.state.pending_verse_updates:
            bucket = grouped_text.setdefault((pending.book, pending.chapter), {})
            for verse, text in pending.verses.items():
                bucket[int(verse)] = text

        grouped_title: dict[tuple[str, int], dict] = {}
        for pending in self.state.pending_title_updates:
            grouped_title[(pending.book, pending.chapter)] = pending

        translation_docs: dict[tuple[str, int], dict] = {}
        for key, updates in grouped_text.items():
            book, chapter = key
            chapter_file = self.bible_repo.load_chapter(book, chapter)
            doc = json.loads(json.dumps(chapter_file.doc))
            changed = self.bible_repo.apply_verse_updates(doc, updates)
            title_update = grouped_title.get(key)
            if title_update:
                self.bible_repo.apply_title_update(doc, title_update.start_verse, title_update.end_verse, title_update.title)
                changed.append("headline")
            new_text = self.bible_repo.dump(doc)
            translation_docs[key] = doc
            if new_text != chapter_file.original_text:
                writes.append((chapter_file.path, chapter_file.original_text, new_text, changed))

        repair_targets = {(repair.book, repair.chapter): repair for repair in self.state.pending_repairs if repair.kind == "justification"}
        grouped_just: dict[tuple[str, int], list] = {}
        for pending in self.state.pending_justification_updates:
            grouped_just.setdefault((pending.book, pending.chapter), []).append(pending)

        for key in sorted(set(grouped_just) | set(repair_targets)):
            book, chapter = key
            just_file = self.just_repo.load_document(book, chapter)
            doc = json.loads(json.dumps(just_file.doc))
            bible_doc = translation_docs.get(key) or self.bible_repo.load_chapter(book, chapter).doc
            verse_map = self.bible_repo.verse_map(bible_doc)
            if key in grouped_just:
                self.just_repo.apply_updates(doc, grouped_just[key], verse_map, book, chapter)
            new_text = self.just_repo.dump(doc)
            notes = list(just_file.notes)
            if key in grouped_just:
                notes.append(f"{len(grouped_just[key])} justification change(s)")
            if new_text != just_file.original_text:
                writes.append((just_file.path, just_file.original_text, new_text, notes))
        return writes

    def summarize_repair_notes(self, notes: list[str]) -> list[str]:
        if not notes:
            return []
        summary: list[str] = []
        id_count = sum(1 for note in notes if note.startswith("Added missing id"))
        seen = set()
        for note in notes:
            if note.startswith("Added missing id"):
                continue
            if note not in seen:
                summary.append(note)
                seen.add(note)
        if id_count:
            summary.append(f"Added generated ids to {id_count} legacy justification entries.")
        return summary

    def repair_blurb(self, notes: list[str]) -> str:
        if not notes:
            return ""
        parts: list[str] = []
        for note in notes:
            if note.startswith("Escaped stray quotes"):
                parts.append("escaped stray quotes")
            elif note.startswith("Added generated ids to "):
                parts.append(note.replace("Added generated ids to ", "generated ids for ").replace(" legacy justification entries.", " legacy entries"))
            else:
                parts.append(note.rstrip("."))
        return "; ".join(parts)

    def short_file_label(self, path) -> str:
        return path.name

    def commit_preview_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "COMMIT_PREVIEW":
            return busy_prefix + ["Inspect pending writes before committing JSON changes to disk."]
        return []

    def render_commit_preview_body(self):
        writes = self.build_commit_plan()
        if writes:
            lines = [f"Pending files: {len(writes)}"]
            for path, _, _, notes in writes[:6]:
                summary = "; ".join(notes[:2]) if notes else "pending change"
                lines.append(f"- {path.name}: {summary}")
            if len(writes) > 6:
                lines.append("\u2026")
        else:
            lines = ["Nothing is currently staged for commit."]
        return [self.line_block(lines)]
