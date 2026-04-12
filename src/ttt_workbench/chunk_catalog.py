from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ttt_core.data.repositories import BibleRepository, ProjectPaths
from ttt_core.models import ChunkSuggestion
from ttt_core.utils import ensure_parent, normalize_book_key, utc_now


class ChunkCatalogRepository:
    """Reads generated chunk catalog files for navigator/book/chapter selection."""

    def __init__(self, paths: ProjectPaths, bible_repo: BibleRepository) -> None:
        self.paths = paths
        self.bible_repo = bible_repo
        self.chapter_dir = (
            self.paths.repo_root / "data" / "final" / "chapter_chunk_catalog" / "chunks"
        )
        self.book_dir = (
            self.paths.repo_root / "data" / "final" / "chapter_chunk_catalog" / "books"
        )
        self._committed_section_cache: dict[tuple[str, str, int], dict[str, Any] | None] = {}

    def _chapter_path(self, testament: str, book: str, chapter: int) -> Path:
        key = normalize_book_key(book)
        return (
            self.chapter_dir
            / testament
            / key
            / f"{key}_{chapter:03d}_chunks.json"
        )

    def _book_path(self, testament: str, book: str) -> Path:
        key = normalize_book_key(book)
        return self.book_dir / testament / f"{key}_chunks.json"

    def chapter_payload_path(self, testament: str, book: str, chapter: int) -> Path:
        return self._chapter_path(testament, book, chapter)

    @staticmethod
    def _default_chunk_title(start_verse: int, end_verse: int) -> str:
        if start_verse == end_verse:
            return f"Verse {start_verse}"
        return f"Verses {start_verse}-{end_verse}"

    def committed_section_payload(
        self, testament: str, book: str, chapter: int
    ) -> dict[str, Any] | None:
        cache_key = (testament, normalize_book_key(book), chapter)
        if cache_key in self._committed_section_cache:
            return self._committed_section_cache[cache_key]
        if not hasattr(self.bible_repo, "load_chapter"):
            self._committed_section_cache[cache_key] = None
            return None
        try:
            chapter_file = self.bible_repo.load_chapter(book, chapter, allow_scaffold=False)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            self._committed_section_cache[cache_key] = None
            return None

        verse_map = self.bible_repo.verse_map(chapter_file.doc)
        if not any(str(text).strip() for text in verse_map.values()):
            self._committed_section_cache[cache_key] = None
            return None

        section_ranges = self.bible_repo.section_ranges(chapter_file.doc)
        if not section_ranges:
            self._committed_section_cache[cache_key] = None
            return None

        chunks: list[dict[str, Any]] = []
        for _index, start_verse, end_verse, headline in section_ranges:
            chunks.append(
                {
                    "start_verse": start_verse,
                    "end_verse": end_verse,
                    "type": "mixed",
                    "title": str(headline).strip()
                    or self._default_chunk_title(start_verse, end_verse),
                    "reason": "Derived from committed section boundaries in the chapter JSON.",
                }
            )

        verses = sorted(verse_map)
        payload = {
            "schema_version": 1,
            "prompt_version": "committed_sections_v1",
            "generated_at": utc_now(),
            "source": "migrated-from-sections",
            "status": "approved",
            "testament": testament,
            "book": book,
            "book_key": normalize_book_key(book),
            "chapter": chapter,
            "verse_start": verses[0],
            "verse_end": verses[-1],
            "verse_count": len(verses),
            "chunks": chunks,
        }
        self._committed_section_cache[cache_key] = payload
        return payload

    def load_chapter_payload(self, testament: str, book: str, chapter: int) -> dict[str, Any]:
        path = self._chapter_path(testament, book, chapter)
        if not path.exists():
            fallback_payload = self.committed_section_payload(testament, book, chapter)
            if fallback_payload is not None:
                return fallback_payload
            raise FileNotFoundError(f"No chapter chunk file found for {book} {chapter}.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}.") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in {path}.")
        return payload

    def save_chapter_payload(
        self, testament: str, book: str, chapter: int, payload: dict[str, Any]
    ) -> Path:
        path = self._chapter_path(testament, book, chapter)
        ensure_parent(path)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def load_chapter_chunks(
        self, testament: str, book: str, chapter: int
    ) -> list[ChunkSuggestion]:
        book_payload = self._load_book_payload(testament, book)
        if book_payload:
            for chapter_item in book_payload.get("chapters", []):
                if int(chapter_item.get("chapter", 0)) != chapter:
                    continue
                return self._parse_chunks(chapter_item.get("chunks", []))
        try:
            payload = self.load_chapter_payload(testament, book, chapter)
        except (FileNotFoundError, ValueError):
            return []
        return self._parse_chunks(payload.get("chunks", []))

    def chunk_status_map(self, testament: str, book: str) -> dict[int, int]:
        chapter_counts: dict[int, int] = {}
        book_payload = self._load_book_payload(testament, book)
        if book_payload:
            chapter_counts.update(
                {
                    int(chapter_item.get("chapter", 0)): len(chapter_item.get("chunks", []))
                    for chapter_item in book_payload.get("chapters", [])
                    if int(chapter_item.get("chapter", 0)) > 0
                }
            )
        chapter_root = self.chapter_dir / testament / normalize_book_key(book)
        if chapter_root.exists():
            for path in sorted(chapter_root.glob("*_chunks.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    chapter = int(payload.get("chapter", 0))
                except Exception:
                    continue
                if chapter > 0:
                    chapter_counts[chapter] = len(payload.get("chunks", []))
        return chapter_counts

    def _load_book_payload(self, testament: str, book: str) -> dict | None:
        path = self._book_path(testament, book)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def merge_consecutive_chunks(
        self,
        testament: str,
        book: str,
        chapter: int,
        *,
        start_index: int,
        end_index: int,
        title: str,
        chunk_type: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        if start_index < 1 or end_index < 1 or start_index > end_index:
            raise ValueError("Choose a valid start/end chunk range.")
        if start_index == end_index:
            raise ValueError("Choose at least two consecutive chunks to merge.")
        title = title.strip()
        if not title:
            raise ValueError("Merged chunk title cannot be blank.")

        payload = self.load_chapter_payload(testament, book, chapter)
        chunks = self._normalize_chunk_payload(payload.get("chunks"), f"{book} {chapter}")
        if end_index > len(chunks):
            raise ValueError("Merge range exceeds the number of chunks in this chapter.")

        first = chunks[start_index - 1]
        last = chunks[end_index - 1]
        merged_chunk = {
            "start_verse": first["start_verse"],
            "end_verse": last["end_verse"],
            "type": chunk_type.strip() or first["type"],
            "title": title,
            "reason": reason.strip()
            or f"Merged consecutive chunks {start_index}-{end_index} in the browser workbench.",
        }
        payload["chunks"] = (
            chunks[: start_index - 1] + [merged_chunk] + chunks[end_index:]
        )
        self.save_chapter_payload(testament, book, chapter, payload)
        self.write_book_payload(testament, book)
        return merged_chunk

    def write_book_payload(self, testament: str, book: str) -> Path:
        chapter_root = self.chapter_dir / testament / normalize_book_key(book)
        if not chapter_root.exists():
            raise FileNotFoundError(f"No chapter chunk directory found for {book}.")

        chapters: list[dict[str, Any]] = []
        for path in sorted(chapter_root.glob("*_chunks.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}.") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Expected a JSON object in {path}.")
            try:
                chapter = int(payload.get("chapter", 0))
            except Exception as exc:
                raise ValueError(f"Missing chapter number in {path}.") from exc
            if chapter <= 0:
                raise ValueError(f"Invalid chapter number in {path}.")
            chapters.append(
                {
                    "chapter": chapter,
                    "chunks": self._normalize_chunk_payload(
                        payload.get("chunks"), f"{book} {chapter}"
                    ),
                }
            )

        if not chapters:
            raise ValueError(f"No chapter chunk files found for {book}.")

        book_payload = {
            "schema_version": 1,
            "generated_at": utc_now(),
            "testament": testament,
            "book": book,
            "book_key": normalize_book_key(book),
            "chapters": sorted(chapters, key=lambda item: item["chapter"]),
        }
        path = self._book_path(testament, book)
        ensure_parent(path)
        path.write_text(
            json.dumps(book_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _normalize_chunk_payload(items: Any, context: str) -> list[dict[str, Any]]:
        if not isinstance(items, list) or not items:
            raise ValueError(f"{context}: expected a non-empty chunk list.")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"{context}: chunk {index} is not an object.")
            try:
                start_verse = int(item["start_verse"])
                end_verse = int(item["end_verse"])
            except Exception as exc:
                raise ValueError(
                    f"{context}: chunk {index} is missing integer verse bounds."
                ) from exc
            if start_verse > end_verse:
                raise ValueError(f"{context}: chunk {index} has start_verse > end_verse.")
            chunk_type = str(item.get("type", "")).strip()
            title = str(item.get("title", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if not chunk_type:
                raise ValueError(f"{context}: chunk {index} has an empty type.")
            if not title:
                raise ValueError(f"{context}: chunk {index} has an empty title.")
            if not reason:
                raise ValueError(f"{context}: chunk {index} has an empty reason.")
            normalized.append(
                {
                    "start_verse": start_verse,
                    "end_verse": end_verse,
                    "type": chunk_type,
                    "title": title,
                    "reason": reason,
                }
            )
        return normalized

    @staticmethod
    def _parse_chunks(items: list[dict]) -> list[ChunkSuggestion]:
        chunks: list[ChunkSuggestion] = []
        for item in items:
            try:
                chunks.append(
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
        return chunks
