#!/usr/bin/env python3
"""Post-process chapter chunk catalogs into approved final catalogs.

This script does two things:

1. Syncs Matthew 1-25 from the manual flat JSON reference so the finalized
   ranges and evocative titles override the raw AI-generated chapter chunks.
2. Applies a deterministic merge pass to the remaining chapter chunk files to
   reduce stutter-splitting and produce larger, more readable chunks.

Outputs are written under ``data/final/chapter_chunk_catalog`` so they can be
treated as approved catalogs independent of the raw AI session artifacts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ttt_core.config import load_config
from ttt_core.utils import ensure_parent, normalize_book_key, utc_now


DENSE_TYPES = {
    "parable",
    "genealogy",
    "law",
    "oracle",
    "psalm",
    "vision",
    "argument",
    "exhortation",
    "blessing_or_prayer",
    "list_or_catalog",
}

GENERIC_TITLE_WORDS = {
    "the",
    "of",
    "and",
    "in",
    "to",
    "a",
    "an",
    "for",
    "on",
    "with",
    "from",
    "at",
    "into",
    "over",
    "under",
    "before",
    "after",
    "jesus",
    "christ",
    "parable",
    "ministry",
    "teaching",
}


@dataclass(frozen=True)
class ChapterRef:
    testament: str
    book: str
    chapter: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    cfg = load_config()
    paths = cfg["paths"]
    parser = argparse.ArgumentParser(
        description="Post-process AI chunk catalogs into approved final catalogs."
    )
    parser.add_argument(
        "--manual-flat-json",
        default=str(Path(paths["processed_bibles"]) / "TTT_flat_bible_v0.8_24052025_2130.json"),
        help="Manual flat JSON used as the authoritative Matthew 1-25 reference.",
    )
    parser.add_argument(
        "--source-dir",
        default=str(Path(paths["ai_sessions"]) / "chapter_chunk_catalog" / "chunks"),
        help="Source directory containing raw chapter chunk JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(paths["final_data"]) / "chapter_chunk_catalog" / "chunks"),
        help="Destination directory for approved per-chapter chunk JSON files.",
    )
    parser.add_argument(
        "--books-dir",
        default=str(Path(paths["final_data"]) / "chapter_chunk_catalog" / "books"),
        help="Destination directory for approved per-book chunk JSON files.",
    )
    parser.add_argument(
        "--manifest-path",
        default=str(Path(paths["final_data"]) / "chapter_chunk_catalog" / "manifest.json"),
        help="Manifest file describing the post-processing pass.",
    )
    parser.add_argument(
        "--only-book",
        help="Optional single book filter for a smaller run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report intended actions without writing files.",
    )
    return parser.parse_args(argv)


def _normalize_chunks(items: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ValueError(f"{context}: expected a non-empty chunk list.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{context}: chunk {index} is not an object.")
        start_verse = int(item["start_verse"])
        end_verse = int(item["end_verse"])
        if start_verse > end_verse:
            raise ValueError(f"{context}: chunk {index} has start_verse > end_verse.")
        normalized.append(
            {
                "start_verse": start_verse,
                "end_verse": end_verse,
                "type": str(item.get("type", "")).strip() or "mixed",
                "title": str(item.get("title", "")).strip() or f"Verses {start_verse}-{end_verse}",
                "reason": str(item.get("reason", "")).strip(),
            }
        )
    return normalized


def _chapter_end_from_payload(payload: dict[str, Any]) -> int:
    if int(payload.get("verse_end", 0)) > 0:
        return int(payload["verse_end"])
    chunks = _normalize_chunks(payload.get("chunks"), f"{payload.get('book', 'book')} {payload.get('chapter', 0)}")
    return max(item["end_verse"] for item in chunks)


def _select_dense_reason(group: list[dict[str, Any]], chunk_type: str) -> str:
    if chunk_type not in DENSE_TYPES:
        return ""
    for item in group:
        reason = str(item.get("reason", "")).strip()
        if reason:
            return reason
    return ""


def _select_chunk_type(group: list[dict[str, Any]]) -> str:
    preferred = [item["type"] for item in group if item["type"] in DENSE_TYPES]
    if preferred:
        return preferred[0]
    if group:
        return group[0]["type"]
    return "mixed"


def _evocative_title(group: list[dict[str, Any]]) -> str:
    titles = [str(item.get("title", "")).strip() for item in group if str(item.get("title", "")).strip()]
    if not titles:
        first = group[0]["start_verse"]
        last = group[-1]["end_verse"]
        return f"Verses {first}-{last}"
    if len(titles) == 1:
        return titles[0]

    token_sets: list[set[str]] = []
    for title in titles:
        tokens = {
            piece.strip(" ,.;:!?()[]{}'\"").lower()
            for piece in title.split()
            if piece.strip(" ,.;:!?()[]{}'\"")
        }
        token_sets.append({token for token in tokens if token not in GENERIC_TITLE_WORDS})
    if token_sets:
        common = set.intersection(*token_sets)
        if common:
            token = sorted(common, key=lambda item: (-len(item), item))[0]
            return f"The {token.title()} Cycle"

    longest = max(titles, key=len)
    return longest


def merge_chunks(chunks: list[dict[str, Any]], chapter_end: int) -> list[dict[str, Any]]:
    """Merge mechanically-split chunks into larger units.

    The algorithm is intentionally deterministic:
    - Prefer chunks of roughly 8-15 verses.
    - For very short chapters, keep a single chunk.
    - Merge undersized adjacent chunks aggressively.
    """
    if not chunks:
        return []
    if chapter_end <= 15:
        groups = [chunks]
    else:
        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_span = 0
        for chunk in chunks:
            chunk_span = chunk["end_verse"] - chunk["start_verse"] + 1
            if not current:
                current = [chunk]
                current_span = chunk_span
                continue
            if current_span < 8:
                current.append(chunk)
                current_span = current[-1]["end_verse"] - current[0]["start_verse"] + 1
                continue
            if current_span < 10 and (chunk["end_verse"] - current[0]["start_verse"] + 1) <= 15:
                current.append(chunk)
                current_span = current[-1]["end_verse"] - current[0]["start_verse"] + 1
                continue
            if chunk_span < 4 and (chunk["end_verse"] - current[0]["start_verse"] + 1) <= 15:
                current.append(chunk)
                current_span = current[-1]["end_verse"] - current[0]["start_verse"] + 1
                continue
            groups.append(current)
            current = [chunk]
            current_span = chunk_span
        if current:
            groups.append(current)

        if len(groups) >= 2:
            last_span = groups[-1][-1]["end_verse"] - groups[-1][0]["start_verse"] + 1
            prev_span = groups[-2][-1]["end_verse"] - groups[-2][0]["start_verse"] + 1
            if last_span < 8 and prev_span + last_span <= 18:
                groups[-2].extend(groups[-1])
                groups.pop()

    merged: list[dict[str, Any]] = []
    for group in groups:
        chunk_type = _select_chunk_type(group)
        merged.append(
            {
                "start_verse": group[0]["start_verse"],
                "end_verse": group[-1]["end_verse"],
                "type": chunk_type,
                "title": _evocative_title(group),
                "reason": _select_dense_reason(group, chunk_type),
            }
        )
    return merged


def load_manual_reference(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chapters: dict[tuple[str, int], dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if str(item.get("book", "")).strip() != "Matthew":
            continue
        try:
            chapter = int(item.get("chapter", 0))
            verse = int(item.get("verse", 0))
        except Exception:
            continue
        if chapter < 1 or chapter > 25 or verse <= 0:
            continue
        key = ("Matthew", chapter)
        record = chapters.setdefault(key, {"titles": [], "max_verse": 0})
        record["max_verse"] = max(record["max_verse"], verse)
        title = str(item.get("title", "")).strip()
        if title:
            record["titles"].append((verse, title))
    return chapters


def build_manual_matthew_payload(
    chapter_payload: dict[str, Any],
    manual_reference: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    book = str(chapter_payload.get("book", "")).strip()
    chapter = int(chapter_payload.get("chapter", 0))
    manual = manual_reference.get((book, chapter))
    if not manual:
        return chapter_payload

    source_chunks = _normalize_chunks(chapter_payload.get("chunks"), f"{book} {chapter}")
    max_verse = int(manual["max_verse"])
    starts = sorted({(int(verse), str(title).strip()) for verse, title in manual["titles"] if str(title).strip()})
    rewritten: list[dict[str, Any]] = []
    for index, (start_verse, title) in enumerate(starts):
        if start_verse > max_verse:
            continue
        end_verse = starts[index + 1][0] - 1 if index + 1 < len(starts) else max_verse
        overlaps = [
            chunk for chunk in source_chunks
            if not (chunk["end_verse"] < start_verse or chunk["start_verse"] > end_verse)
        ]
        chunk_type = _select_chunk_type(overlaps) if overlaps else "mixed"
        rewritten.append(
            {
                "start_verse": start_verse,
                "end_verse": end_verse,
                "type": chunk_type,
                "title": title,
                "reason": _select_dense_reason(overlaps, chunk_type),
            }
        )

    result = dict(chapter_payload)
    result["source"] = "manual-sync"
    result["status"] = "approved"
    result["chunks"] = rewritten
    result["verse_start"] = 1
    result["verse_end"] = max_verse
    result["verse_count"] = max_verse
    result["generated_at"] = utc_now()
    return result


def build_processed_payload(chapter_payload: dict[str, Any]) -> dict[str, Any]:
    source_chunks = _normalize_chunks(
        chapter_payload.get("chunks"),
        f"{chapter_payload.get('book', 'book')} {chapter_payload.get('chapter', 0)}",
    )
    chapter_end = _chapter_end_from_payload(chapter_payload)
    merged = merge_chunks(source_chunks, chapter_end)
    result = dict(chapter_payload)
    result["source"] = "post-processed"
    result["status"] = "approved"
    result["chunks"] = merged
    result["generated_at"] = utc_now()
    return result


def book_payload_from_chapters(testament: str, book: str, chapters: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(chapters, key=lambda item: int(item["chapter"]))
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "testament": testament,
        "book": book,
        "book_key": normalize_book_key(book),
        "chapters": [
            {
                "chapter": int(item["chapter"]),
                "chunks": _normalize_chunks(item.get("chunks"), f"{book} {item['chapter']}"),
            }
            for item in ordered
        ],
    }


def chapter_ref_from_path(root: Path, path: Path) -> ChapterRef:
    rel = path.relative_to(root)
    testament = rel.parts[0]
    book_key = rel.parts[1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    book = str(payload.get("book", book_key)).strip() or book_key.replace("_", " ").title()
    chapter = int(payload["chapter"])
    return ChapterRef(testament=testament, book=book, chapter=chapter)


def run(args: argparse.Namespace) -> int:
    manual_reference = load_manual_reference(Path(args.manual_flat_json))
    source_root = Path(args.source_dir).resolve()
    output_root = Path(args.output_dir).resolve()
    books_root = Path(args.books_dir).resolve()
    manifest_path = Path(args.manifest_path).resolve()

    chapter_paths = sorted(source_root.glob("*/*/*_chunks.json"))
    if args.only_book:
        only = normalize_book_key(args.only_book)
        chapter_paths = [path for path in chapter_paths if path.parent.name == only]
    if not chapter_paths:
        print("No chapter chunk files matched the current filter.")
        return 1

    processed_by_book: dict[tuple[str, str], list[dict[str, Any]]] = {}
    manifest: dict[str, Any] = {
        "generated_at": utc_now(),
        "manual_flat_json": str(Path(args.manual_flat_json).resolve()),
        "source_dir": str(source_root),
        "output_dir": str(output_root),
        "books_dir": str(books_root),
        "chapters": {},
    }

    for chapter_path in chapter_paths:
        chapter_payload = json.loads(chapter_path.read_text(encoding="utf-8"))
        ref = chapter_ref_from_path(source_root, chapter_path)
        if ref.book == "Matthew" and 1 <= ref.chapter <= 25:
            processed = build_manual_matthew_payload(chapter_payload, manual_reference)
            action = "manual_sync"
        else:
            processed = build_processed_payload(chapter_payload)
            action = "merged"

        out_path = output_root / ref.testament / normalize_book_key(ref.book) / chapter_path.name
        manifest["chapters"][f"{normalize_book_key(ref.book)}:{ref.chapter}"] = {
            "testament": ref.testament,
            "book": ref.book,
            "chapter": ref.chapter,
            "action": action,
            "chunk_count": len(processed["chunks"]),
            "output_path": str(out_path),
        }
        processed_by_book.setdefault((ref.testament, ref.book), []).append(processed)
        if args.dry_run:
            continue
        ensure_parent(out_path)
        out_path.write_text(
            json.dumps(processed, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if not args.dry_run:
        for (testament, book), chapters in sorted(
            processed_by_book.items(),
            key=lambda item: (item[0][0], normalize_book_key(item[0][1])),
        ):
            payload = book_payload_from_chapters(testament, book, chapters)
            out_path = books_root / testament / f"{normalize_book_key(book)}_chunks.json"
            ensure_parent(out_path)
            out_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        ensure_parent(manifest_path)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(
        f"Processed {len(chapter_paths)} chapter chunk files into approved catalogs "
        f"for {len(processed_by_book)} books."
    )
    print(f"Chapter outputs: {output_root}")
    print(f"Book outputs: {books_root}")
    print(f"Manifest: {manifest_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
