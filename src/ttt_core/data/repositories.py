"""Data repositories for Bible JSON, justifications, sources, and lexical data."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ttt_core.models.state import PendingJustificationUpdate
from ttt_core.utils.common import (
    book_abbrev,
    book_ref_code,
    ensure_parent,
    extract_json_payload,
    lexical_book_code,
    make_text_hash,
    normalize_book_key,
    repair_linewise_json_strings,
    utc_now,
)

OT_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi",
]

NT_BOOKS = [
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
    "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians",
    "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus",
    "Philemon", "Hebrews", "James", "1 Peter", "2 Peter", "1 John",
    "2 John", "3 John", "Jude", "Revelation",
]


def _safe_book_component(book: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", book.strip()).strip("_") or "Book"


@dataclass
class ChapterFile:
    path: Path
    doc: dict[str, Any]
    original_text: str


@dataclass
class JustificationFile:
    path: Path
    doc: dict[str, Any]
    original_text: str
    normalized_text: str
    notes: list[str]


from ttt_core.config import load_config

class ProjectPaths:
    """Resolves all data directory locations relative to the workspace."""

    def __init__(
        self,
        workspace_dir: Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        # Load unified configuration
        config = load_config(repo_root)
        paths = config["paths"]

        self.repo_root = Path(paths["root"])
        self.data_dir = Path(paths["data"])
        self.output_dir = Path(paths["output"])
        self.resources_dir = Path(paths["resources"])

        self.bible_dir = Path(paths["bible_dir"])
        self.justifications_dir = Path(paths["justifications_dir"])
        self.source_dirs = [
            Path(paths["processed_bibles"]),
        ]
        self.prompts_dir = Path(paths["prompts"])
        self.legacy_prompt_path = (
            self.prompts_dir / "instructions_bible_crafter_prompt.txt"
        )
        self.state_dir = self.repo_root / ".ttt_workbench"
        self.sessions_dir = Path(paths["ai_sessions"])
        self.reports_dir = Path(paths["reports"])
        self.backups_dir = self.state_dir / "backups"
        self.chunk_cache_dir = self.state_dir / "chunk_cache"
        self.state_file = self.state_dir / "active_session.json"
        self.lexical_db_path = Path(paths["lexical_db"])
        self.chunking_prompts_dir = self.prompts_dir / "chunking"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_cache_dir.mkdir(parents=True, exist_ok=True)


class BibleRepository:
    """Reads and writes chapter-level Bible JSON files."""

    def __init__(
        self,
        paths: ProjectPaths,
        source_repository: "SourceRepository | None" = None,
        lexical_repository: "LexicalRepository | None" = None,
    ) -> None:
        self.paths = paths
        self.source_repository = source_repository
        self.lexical_repository = lexical_repository
        self._index: dict[tuple[str, int], Path] = {}
        self._catalog: dict[str, dict[str, list[int]]] | None = None

    def _build_index(self) -> None:
        if self._index:
            return
        for path in self.paths.bible_dir.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            book = payload.get("book")
            chapter = payload.get("chapter")
            if isinstance(book, str) and isinstance(chapter, int):
                self._index[(normalize_book_key(book), chapter)] = path

    def _path_testament(self, path: Path) -> str:
        rel = path.relative_to(self.paths.bible_dir).as_posix().lower()
        if "_1_old_testament" in rel:
            return "old"
        if "_2_new_testament" in rel:
            return "new"
        return "other"

    def chapter_exists(self, book: str, chapter: int) -> bool:
        self._build_index()
        key = (normalize_book_key(book), chapter)
        if key in self._index:
            return True
        try:
            path = self._scaffold_target_path(book, chapter)
        except FileNotFoundError:
            return False
        if path.exists():
            self._index[key] = path
            self._catalog = None
            return True
        return False

    def canonical_books(self, testament: str) -> list[str]:
        if testament == "old":
            return list(OT_BOOKS)
        if testament == "new":
            return list(NT_BOOKS)
        return []

    def canonical_testament_for(self, book: str) -> str:
        key = normalize_book_key(book)
        for candidate in OT_BOOKS:
            if normalize_book_key(candidate) == key:
                return "old"
        for candidate in NT_BOOKS:
            if normalize_book_key(candidate) == key:
                return "new"
        return "other"

    def _chapter_numbers_from_backing_sources(self, book: str, testament: str) -> list[int]:
        chapters: set[int] = set()
        if self.lexical_repository is not None:
            corpus = "hebrew_ot" if testament == "old" else "greek_nt"
            chapters.update(self.lexical_repository.chapters_for_book(corpus, book))
        if self.source_repository is not None:
            chapters.update(self.source_repository.chapters_for_book(book))
        return sorted(chapters)

    def chapter_verse_numbers(self, book: str, chapter: int) -> list[int]:
        if self.chapter_exists(book, chapter):
            doc = self.load_chapter(book, chapter, allow_scaffold=False).doc
            return sorted(self.verse_map(doc))
        testament = self.canonical_testament_for(book)
        if testament in {"old", "new"} and self.lexical_repository is not None:
            corpus = "hebrew_ot" if testament == "old" else "greek_nt"
            verses = self.lexical_repository.chapter_verse_numbers(corpus, book, chapter)
            if verses:
                return verses
        if self.source_repository is not None:
            verses = self.source_repository.chapter_verse_numbers(book, chapter)
            if verses:
                return verses
        return []

    def _scaffold_target_path(self, book: str, chapter: int) -> Path:
        testament = self.canonical_testament_for(book)
        books = self.canonical_books(testament)
        if not books:
            raise FileNotFoundError(f"No chapter JSON found for {book} {chapter}")
        index = next(
            (i for i, candidate in enumerate(books, start=1)
             if normalize_book_key(candidate) == normalize_book_key(book)),
            None,
        )
        if index is None:
            raise FileNotFoundError(f"No chapter JSON found for {book} {chapter}")
        testament_dir = "_1_Old_Testament" if testament == "old" else "_2_New_Testament"
        testament_prefix = "1_OT" if testament == "old" else "2_NT"
        safe_book = _safe_book_component(book)
        directory = self.paths.bible_dir / testament_dir / f"_{index}_{safe_book}"
        return directory / f"{testament_prefix}_{safe_book}_{chapter:03d}.json"

    def target_chapter_path(self, book: str, chapter: int) -> Path:
        if self.chapter_exists(book, chapter):
            return self.chapter_path(book, chapter, allow_scaffold=False)
        return self._scaffold_target_path(book, chapter)

    def scaffold_document(
        self, book: str, chapter: int, verse_numbers: list[int] | None = None
    ) -> dict[str, Any]:
        verses = verse_numbers or self.chapter_verse_numbers(book, chapter)
        if not verses:
            raise FileNotFoundError(f"No chapter JSON found for {book} {chapter}")
        testament = "OT" if self.canonical_testament_for(book) == "old" else "NT"
        return {
            "testament": testament,
            "book": book,
            "chapter": chapter,
            "sections": [
                {
                    "headline": "",
                    "verses": [{"verse": verse, "text": ""} for verse in verses],
                }
            ],
            "footnotes": [],
        }

    def catalog(self) -> dict[str, dict[str, list[int]]]:
        self._build_index()
        if self._catalog is None:
            entries: dict[str, dict[str, list[int]]] = {"old": {}, "new": {}, "other": {}}
            ordered = sorted(
                self._index.items(), key=lambda item: item[1].relative_to(self.paths.bible_dir).as_posix()
            )
            for (_book_key, chapter), path in ordered:
                payload = json.loads(path.read_text(encoding="utf-8"))
                book = str(payload.get("book", "")).strip()
                if not book:
                    continue
                testament = self._path_testament(path)
                entries.setdefault(testament, {}).setdefault(book, []).append(chapter)
            for testament_books in entries.values():
                for book, chapters in testament_books.items():
                    testament_books[book] = sorted(set(chapters))
            self._catalog = entries
        entries = json.loads(json.dumps(self._catalog))
        for testament in ("old", "new"):
            for book in self.canonical_books(testament):
                chapters = set(entries.get(testament, {}).get(book, []))
                chapters.update(self._chapter_numbers_from_backing_sources(book, testament))
                if chapters:
                    entries.setdefault(testament, {})[book] = sorted(chapters)
        return entries

    def books_for_testament(self, testament: str) -> list[str]:
        books = self.catalog().get(testament, {})
        canonical = self.canonical_books(testament)
        return [book for book in canonical if books.get(book)] or list(books.keys())

    def chapters_for_book(self, testament: str, book: str) -> list[int]:
        return list(self.catalog().get(testament, {}).get(book, []))

    def testament_for(self, book: str, chapter: int) -> str:
        if self.chapter_exists(book, chapter):
            return self._path_testament(self.chapter_path(book, chapter, allow_scaffold=False))
        return self.canonical_testament_for(book)

    def chapter_path(self, book: str, chapter: int, *, allow_scaffold: bool = False) -> Path:
        self._build_index()
        key = (normalize_book_key(book), chapter)
        if key not in self._index:
            scaffold_path = self._scaffold_target_path(book, chapter)
            if scaffold_path.exists():
                self._index[key] = scaffold_path
                self._catalog = None
                return scaffold_path
            if allow_scaffold:
                return scaffold_path
            raise FileNotFoundError(f"No chapter JSON found for {book} {chapter}")
        return self._index[key]

    def load_chapter(
        self, book: str, chapter: int, *, allow_scaffold: bool = True
    ) -> ChapterFile:
        path = self.chapter_path(book, chapter, allow_scaffold=allow_scaffold)
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return ChapterFile(path=path, doc=json.loads(raw), original_text=raw)
        doc = self.scaffold_document(book, chapter)
        return ChapterFile(path=path, doc=doc, original_text="")

    def verse_map(self, doc: dict[str, Any]) -> dict[int, str]:
        mapping: dict[int, str] = {}
        for section in doc.get("sections", []):
            for verse in section.get("verses", []):
                if isinstance(verse.get("verse"), int):
                    mapping[verse["verse"]] = verse.get("text", "")
        return mapping

    def section_ranges(self, doc: dict[str, Any]) -> list[tuple[int, int, int, str]]:
        results: list[tuple[int, int, int, str]] = []
        for idx, section in enumerate(doc.get("sections", [])):
            verses = [
                item.get("verse")
                for item in section.get("verses", [])
                if isinstance(item.get("verse"), int)
            ]
            if verses:
                results.append((idx, min(verses), max(verses), section.get("headline", "")))
        return results

    def title_section_index(
        self, doc: dict[str, Any], start_verse: int, end_verse: int
    ) -> int:
        matches = [
            idx
            for idx, low, high, _ in self.section_ranges(doc)
            if start_verse >= low and end_verse <= high
        ]
        if len(matches) != 1:
            raise ValueError(
                "Chunk spans multiple sections. Open a section-sized chunk before staging a title."
            )
        return matches[0]

    def apply_verse_updates(
        self, doc: dict[str, Any], updates: dict[int, str]
    ) -> list[str]:
        changed: list[str] = []
        for section in doc.get("sections", []):
            for verse in section.get("verses", []):
                verse_number = verse.get("verse")
                if verse_number in updates and verse.get("text") != updates[verse_number]:
                    verse["text"] = updates[verse_number]
                    changed.append(f"verse {verse_number}")
        return changed

    def apply_title_update(
        self, doc: dict[str, Any], start_verse: int, end_verse: int, title: str
    ) -> str:
        idx = self.title_section_index(doc, start_verse, end_verse)
        current = doc["sections"][idx].get("headline", "")
        doc["sections"][idx]["headline"] = title
        return current

    def apply_footnote_updates(
        self, doc: dict[str, Any], updates: list[dict[str, Any]]
    ) -> list[str]:
        footnotes = doc.setdefault("footnotes", [])
        changed: list[str] = []
        index = {
            (int(entry.get("verse", 0)), str(entry.get("letter", "")).strip()): pos
            for pos, entry in enumerate(footnotes)
            if isinstance(entry, dict) and str(entry.get("content", "")).strip()
        }
        for raw_entry in updates:
            verse = int(raw_entry.get("verse", 0))
            letter = str(raw_entry.get("letter", "")).strip()
            delete_flag = bool(raw_entry.get("_delete"))
            content = str(raw_entry.get("content", "")).strip()
            key = (verse, letter)
            note_label = f"footnote {verse}{letter}" if letter else f"footnote {verse}"
            if delete_flag:
                if key in index:
                    footnotes.pop(index[key])
                    changed.append(f"deleted {note_label}")
                    index = {
                        (int(entry.get("verse", 0)), str(entry.get("letter", "")).strip()): pos
                        for pos, entry in enumerate(footnotes)
                        if isinstance(entry, dict) and str(entry.get("content", "")).strip()
                    }
                continue
            if verse <= 0 or not content:
                continue
            entry = {"verse": verse, "letter": letter, "content": content}
            if key in index:
                if footnotes[index[key]] != entry:
                    footnotes[index[key]] = entry
                    changed.append(note_label)
            else:
                footnotes.append(entry)
                index[key] = len(footnotes) - 1
                changed.append(note_label)
        footnotes.sort(key=lambda item: (int(item.get("verse", 0)), str(item.get("letter", "")).strip()))
        return changed

    def dump(self, doc: dict[str, Any]) -> str:
        return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


class JustificationRepository:
    """Reads, writes, and normalizes justification JSON files."""

    def __init__(self, paths: ProjectPaths, bible_repository: BibleRepository) -> None:
        self.paths = paths
        self.bible_repository = bible_repository

    def resolve_path(self, book: str, chapter: int) -> Path:
        bible_path = self.bible_repository.target_chapter_path(book, chapter)
        relative = bible_path.relative_to(self.paths.bible_dir)
        directory = self.paths.justifications_dir / relative.parent
        chapter_part = f"{chapter:03d}"
        matches = (
            sorted(directory.glob(f"*_{chapter_part}_*justification*.json"))
            + sorted(directory.glob(f"*_{chapter_part}_*Justification*.json"))
            + sorted(directory.glob(f"*_{chapter_part}_*Justifications.json"))
        )
        if matches:
            return matches[0]
        stem = bible_path.stem + "_justifications"
        return directory / f"{stem}.json"

    def _empty_document(self, book: str, chapter: int) -> dict[str, Any]:
        return {
            "metadata": {
                "translator": "Arto",
                "date": utc_now().split("T")[0],
                "version": "1.0",
                "language_target": "Modern English",
                "book_name": book,
                "chapter": chapter,
                "schema_version": 2,
            },
            "justifications": [],
        }

    def load_document(self, book: str, chapter: int) -> JustificationFile:
        path = self.resolve_path(book, chapter)
        notes: list[str] = []
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            payload = None
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                candidate = extract_json_payload(raw)
                if candidate is not None:
                    payload = candidate
                    notes.append("Stray non-JSON text was removed from the justification file.")
                else:
                    start = raw.find("{")
                    end = raw.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        repaired_text, changed = repair_linewise_json_strings(
                            raw[start : end + 1]
                        )
                        if changed:
                            try:
                                payload = json.loads(repaired_text)
                                notes.append(
                                    "Escaped stray quotes inside string values in the justification file."
                                )
                            except json.JSONDecodeError:
                                payload = None
            if not isinstance(payload, dict):
                payload = self._empty_document(book, chapter)
                notes.append(
                    "Justification file was unreadable and has been reinitialized."
                )
        else:
            raw = ""
            payload = self._empty_document(book, chapter)
            notes.append("Created a new justification file scaffold.")

        normalized, migration_notes = self._normalize_document(payload, book, chapter)
        notes.extend(migration_notes)
        normalized_text = json.dumps(normalized, indent=2, ensure_ascii=False) + "\n"
        return JustificationFile(
            path=path,
            doc=normalized,
            original_text=raw,
            normalized_text=normalized_text,
            notes=notes,
        )

    def _normalize_document(
        self, payload: dict[str, Any], book: str, chapter: int
    ) -> tuple[dict[str, Any], list[str]]:
        notes: list[str] = []
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            notes.append("Missing metadata was recreated.")
        metadata.setdefault("translator", "Arto")
        metadata.setdefault("date", utc_now().split("T")[0])
        metadata.setdefault("version", "1.0")
        metadata.setdefault("language_target", "Modern English")
        metadata["book_name"] = metadata.get("book_name") or book
        metadata["chapter"] = chapter
        metadata["schema_version"] = 2

        verses_text = self.bible_repository.verse_map(
            self.bible_repository.load_chapter(book, chapter).doc
        )
        entries = payload.get("justifications")
        if not isinstance(entries, list):
            entries = []
            notes.append("Missing justifications list was recreated.")

        normalized_entries: list[dict[str, Any]] = []
        existing_ids: set[str] = set()
        for idx, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                notes.append(f"Non-object justification entry #{idx} was skipped.")
                continue
            chapter_value = int(entry.get("chapter", entry.get("chapter_number", chapter)))
            verse_numbers = entry.get("verses", entry.get("verse_number", []))
            if isinstance(verse_numbers, int):
                verse_numbers = [verse_numbers]
            verses = sorted(
                {int(item) for item in verse_numbers if str(item).strip().isdigit()}
            )
            if chapter_value != chapter:
                chapter_value = chapter
            source_term = entry.get("source_term", entry.get("original", ""))
            decision = entry.get("decision", entry.get("translated", ""))
            reason = entry.get("reason", "")
            target = entry.get("target", "verse_text")
            created_at = entry.get("created_at", utc_now())
            updated_at = entry.get("updated_at", created_at)
            entry_id = entry.get("id")
            if not entry_id:
                entry_id = self._next_entry_id(existing_ids, book, chapter)
                notes.append(
                    f"Added missing id to a justification covering verses {verses or ['?']}."
                )
            existing_ids.add(entry_id)
            text_hash = entry.get("text_hash") or make_text_hash(
                book, chapter, verses, verses_text
            )
            normalized_entries.append(
                {
                    "id": entry_id,
                    "chapter": chapter_value,
                    "verses": verses,
                    "target": target,
                    "source_term": source_term,
                    "decision": decision,
                    "reason": reason,
                    "text_hash": text_hash,
                    "status": entry.get("status", "active"),
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )

        normalized_entries.sort(
            key=lambda item: (
                item["verses"][0] if item["verses"] else 10**9,
                item["id"],
            )
        )
        return {"metadata": metadata, "justifications": normalized_entries}, notes

    def _next_entry_id(self, existing_ids: set[str], book: str, chapter: int) -> str:
        prefix = f"{book_abbrev(book)}-{chapter:03d}-J"
        index = 1
        while True:
            candidate = f"{prefix}{index:04d}"
            if candidate not in existing_ids:
                return candidate
            index += 1

    def build_entry(
        self,
        book: str,
        chapter: int,
        start_verse: int,
        end_verse: int,
        verses: list[int] | None,
        source_term: str,
        decision: str,
        reason: str,
        verse_map: dict[int, str],
        existing_ids: set[str],
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        clean_verses = sorted({int(item) for item in (verses or []) if int(item) > 0})
        if not clean_verses:
            clean_verses = list(range(start_verse, end_verse + 1))
        now = utc_now()
        return {
            "id": entry_id or self._next_entry_id(existing_ids, book, chapter),
            "chapter": chapter,
            "verses": clean_verses,
            "target": "verse_text",
            "source_term": source_term,
            "decision": decision,
            "reason": reason,
            "text_hash": make_text_hash(book, chapter, clean_verses, verse_map),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }

    def apply_updates(
        self,
        document: dict[str, Any],
        updates: list[PendingJustificationUpdate],
        verse_map: dict[int, str],
        book: str,
        chapter: int,
    ) -> None:
        entries = document.setdefault("justifications", [])
        index = {
            entry["id"]: pos
            for pos, entry in enumerate(entries)
            if isinstance(entry, dict) and "id" in entry
        }
        for update in updates:
            entry = dict(update.entry)
            if entry.get("_delete"):
                entry_id = str(entry.get("id", "")).strip()
                if entry_id in index:
                    entries.pop(index[entry_id])
                    index = {
                        saved_entry["id"]: pos
                        for pos, saved_entry in enumerate(entries)
                        if isinstance(saved_entry, dict) and "id" in saved_entry
                    }
                continue
            entry["text_hash"] = make_text_hash(
                book, chapter, entry.get("verses", []), verse_map
            )
            entry["updated_at"] = utc_now()
            if entry["id"] in index:
                entries[index[entry["id"]]] = entry
            else:
                entries.append(entry)
        entries.sort(
            key=lambda item: (
                item["verses"][0] if item.get("verses") else 10**9,
                item["id"],
            )
        )

    def stale_entries(
        self,
        document: dict[str, Any],
        verse_map: dict[int, str],
        book: str,
        chapter: int,
        scope: range,
    ) -> list[str]:
        warnings: list[str] = []
        verses_set = set(scope)
        for entry in document.get("justifications", []):
            covered = set(entry.get("verses", []))
            if not covered.intersection(verses_set):
                continue
            expected = make_text_hash(book, chapter, covered, verse_map)
            if entry.get("text_hash") != expected:
                label = ",".join(str(v) for v in sorted(covered))
                warnings.append(
                    f"Justification {entry.get('id', '?')} for verses {label} may be stale."
                )
        return warnings

    def dump(self, doc: dict[str, Any]) -> str:
        return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


class SourceRepository:
    """Reads source translation JSON files for comparison."""

    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths
        self.catalog: dict[str, Path] = {}
        self.display_names: dict[str, str] = {}
        self._cache: dict[str, dict[tuple[str, int, int], str]] = {}
        self._scan_sources()

    def _alias_for_path(self, path: Path) -> str:
        stem = path.stem
        stem = re.sub(r"_Bible_flat$", "", stem, flags=re.IGNORECASE)
        if "SBLGNT" in stem.upper():
            return "SBLGNT"
        if stem.upper().startswith("GREEK"):
            return re.sub(r"^GREEK", "", stem, flags=re.IGNORECASE) or stem.upper()
        return stem.upper().replace("_", "")

    def _scan_sources(self) -> None:
        for directory in self.paths.source_dirs:
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*_Bible_flat.json")):
                alias = self._alias_for_path(path)
                self.catalog.setdefault(alias, path)
                self.display_names.setdefault(alias, path.name)

    def list_sources(self) -> list[str]:
        return sorted(self.catalog)

    def resolve_sources(self, tokens: list[str]) -> list[str]:
        if not tokens:
            return []
        results: list[str] = []
        for token in tokens:
            for piece in token.split(","):
                alias = piece.strip().upper()
                if alias:
                    if alias not in self.catalog:
                        raise KeyError(f"Unknown source '{piece}'. Use /sources.")
                    results.append(alias)
        return results

    def _load_source(self, alias: str) -> dict[tuple[str, int, int], str]:
        if alias in self._cache:
            return self._cache[alias]
        path = self.catalog[alias]
        payload = json.loads(path.read_text(encoding="utf-8"))
        mapping: dict[tuple[str, int, int], str] = {}
        for item in payload:
            try:
                key = (normalize_book_key(item["book"]), int(item["chapter"]), int(item["verse"]))
            except Exception:
                continue
            mapping[key] = item.get("text", "")
        self._cache[alias] = mapping
        return mapping

    def verse_text(self, alias: str, book: str, chapter: int, verse: int) -> str:
        return self._load_source(alias).get((normalize_book_key(book), chapter, verse), "")

    def verse_range(
        self, alias: str, book: str, chapter: int, start_verse: int, end_verse: int
    ) -> dict[int, str]:
        return {
            verse: self.verse_text(alias, book, chapter, verse)
            for verse in range(start_verse, end_verse + 1)
            if self.verse_text(alias, book, chapter, verse)
        }

    def _preferred_aliases(self) -> list[str]:
        preferred = ["ESV", "NET", "LSB", "NIV", "NKJV", "CSB", "LEB", "BSB", "SBLGNT"]
        ordered = [alias for alias in preferred if alias in self.catalog]
        ordered.extend(alias for alias in self.list_sources() if alias not in ordered)
        return ordered

    def chapter_verse_numbers(self, book: str, chapter: int) -> list[int]:
        book_key = normalize_book_key(book)
        for alias in self._preferred_aliases():
            mapping = self._load_source(alias)
            verses = sorted(
                verse
                for (mapped_book, mapped_chapter, verse) in mapping
                if mapped_book == book_key and mapped_chapter == chapter
            )
            if verses:
                return verses
        return []

    def chapters_for_book(self, book: str) -> list[int]:
        book_key = normalize_book_key(book)
        for alias in self._preferred_aliases():
            mapping = self._load_source(alias)
            chapters = sorted(
                {
                    chapter
                    for (mapped_book, chapter, _verse) in mapping
                    if mapped_book == book_key
                }
            )
            if chapters:
                return chapters
        return []


class LexicalRepository:
    """Accesses the lexical index SQLite database."""

    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    def available(self) -> bool:
        return self.paths.lexical_db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.paths.lexical_db_path)

    def refs_for_range(
        self, book: str, chapter: int, start_verse: int, end_verse: int, *, corpus: str = ""
    ) -> list[str]:
        code = lexical_book_code(book, corpus) if corpus else book_ref_code(book)
        return [f"{code}.{chapter}.{verse}" for verse in range(start_verse, end_verse + 1)]

    def fetch_tokens(
        self, corpus: str, book: str, chapter: int, start_verse: int, end_verse: int
    ) -> dict[str, list[dict[str, str]]]:
        if not self.available():
            return {}
        refs = self.refs_for_range(book, chapter, start_verse, end_verse, corpus=corpus)
        placeholders = ",".join("?" for _ in refs)
        query = f"""
            SELECT ref, ordinal, surface, transliteration, english, strong_id, morph, lemma, gloss, lexical_id
            FROM tagged_tokens
            WHERE corpus = ? AND ref IN ({placeholders})
            ORDER BY ref, ordinal
        """
        result: dict[str, list[dict[str, str]]] = {ref: [] for ref in refs}
        try:
            with self._connect() as conn:
                for row in conn.execute(query, [corpus, *refs]):
                    ref, ordinal, surface, transliteration, english, strong_id, morph, lemma, gloss, lexical_id = row
                    result.setdefault(ref, []).append(
                        {
                            "ordinal": str(ordinal),
                            "surface": surface or "",
                            "transliteration": transliteration or "",
                            "english": english or "",
                            "strong_id": strong_id or "",
                            "morph": morph or "",
                            "lemma": lemma or "",
                            "gloss": gloss or "",
                            "lexical_id": lexical_id or "",
                        }
                    )
        except sqlite3.Error:
            return {}
        return result

    def fetch_lexicon_glosses(self, corpus: str, strong_ids: list[str]) -> dict[str, str]:
        """Look up English glosses from the lexicon by Strong's numbers.
        
        The corpus determines which lexicon to use:
          - 'hebrew_ot' → hebrew_bible (TBESH)
          - 'greek_nt' / 'greek_ot_lxx' → greek_bible (TBESG)
        """
        import re as _re
        lexicon_map = {
            "hebrew_ot": "hebrew_bible",
            "greek_nt": "greek_bible",
            "greek_ot_lxx": "greek_bible",
        }
        # Grammatical/artifact glosses that should be filtered out
        _SKIP_GLOSSES = frozenset({
            "[obj.]", "[obj]", "[dir.]", "[dir]", "[?]", "[-]", "[.]", "[ ]",
            "[¶]", "[emph.?]", "[emph]", "[the]", "[to]",
        })
        lex_corpus = lexicon_map.get(corpus, corpus.replace("_ot", "_bible").replace("_nt", "_bible"))
        if not strong_ids:
            return {}
        clean_ids = list({sid for sid in strong_ids if sid and sid.strip()})
        if not clean_ids:
            return {}
        placeholders = ",".join("?" for _ in clean_ids)
        query = f"""
            SELECT strong_id, gloss
            FROM lexicon_entries
            WHERE corpus = ? AND strong_id IN ({placeholders})
        """
        result: dict[str, str] = {}
        try:
            with self._connect() as conn:
                for row in conn.execute(query, [lex_corpus, *clean_ids]):
                    sid, gloss = row
                    if gloss:
                        # Strip HTML tags, normalize whitespace
                        clean = _re.sub(r'<[^>]+>', '; ', gloss)
                        clean = clean.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                        # Take first sense (before first semicolon or slash)
                        clean = clean.split(';')[0].split('/')[0].strip()
                        clean = _re.sub(r'\s+', ' ', clean)
                        # Filter out grammatical artifacts (no real English meaning)
                        if clean and clean.lower() not in _SKIP_GLOSSES and sid not in result:
                            result[sid] = clean
        except sqlite3.Error:
            pass
        return result

    def chapter_verse_numbers(self, corpus: str, book: str, chapter: int) -> list[int]:
        if not self.available():
            return []
        code = book_ref_code(book)
        pattern = f"{code}.{chapter}.%"
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT DISTINCT ref
                    FROM tagged_tokens
                    WHERE corpus = ? AND ref LIKE ?
                    ORDER BY ref
                    """,
                    (corpus, pattern),
                ).fetchall()
        except sqlite3.Error:
            return []
        verses = []
        for (ref,) in rows:
            try:
                verses.append(int(str(ref).rsplit(".", 1)[-1]))
            except Exception:
                continue
        return sorted(set(verses))

    def chapters_for_book(self, corpus: str, book: str) -> list[int]:
        if not self.available():
            return []
        code = book_ref_code(book)
        pattern = f"{code}.%"
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT DISTINCT ref
                    FROM tagged_tokens
                    WHERE corpus = ? AND ref LIKE ?
                    ORDER BY ref
                    """,
                    (corpus, pattern),
                ).fetchall()
        except sqlite3.Error:
            return []
        chapters = []
        for (ref,) in rows:
            parts = str(ref).split(".")
            if len(parts) < 3:
                continue
            try:
                chapters.append(int(parts[1]))
            except Exception:
                continue
        return sorted(set(chapters))


def write_backup_set(
    backups_dir: Path, writes: list[tuple[Path, str, str]]
) -> Path:
    """Write a backup set and apply new text to target paths atomically."""
    timestamp = utc_now().replace(":", "").replace("-", "")
    backup_dir = backups_dir / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for path, old_text, new_text in writes:
        relative = path.as_posix().lstrip("/")
        backup_path = backup_dir / relative
        ensure_parent(backup_path)
        if path.exists():
            backup_path.write_text(old_text, encoding="utf-8")
        else:
            backup_path.write_text("", encoding="utf-8")
        manifest.append(
            {
                "path": str(path),
                "backup": str(backup_path),
                "had_original": path.exists(),
            }
        )
        temp_path = path.with_suffix(path.suffix + ".tmp")
        ensure_parent(temp_path)
        temp_path.write_text(new_text, encoding="utf-8")
        temp_path.replace(path)
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return backup_dir


def restore_backup_set(backup_dir: Path) -> list[str]:
    """Restore files from a backup set manifest."""
    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[str] = []
    for item in manifest:
        path = Path(item["path"])
        backup = Path(item["backup"])
        if item.get("had_original"):
            ensure_parent(path)
            shutil.copyfile(backup, path)
        elif path.exists():
            path.unlink()
        restored.append(str(path))
    return restored
