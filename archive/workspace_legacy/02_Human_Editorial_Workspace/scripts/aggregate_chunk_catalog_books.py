#!/usr/bin/env python3
"""Aggregate chapter chunk files into per-book chunk catalog files.

This script reads the existing chapter-level chunk outputs under
``chapter_chunk_catalog/chunks`` and writes one aggregate JSON file per book to
``chapter_chunk_catalog_books``. The source chapter files remain untouched so
the aggregation can be rerun safely after partial or full chunk-generation
passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ttt_core.utils.common import ensure_parent, normalize_book_key, utc_now


VALID_TESTAMENTS = {"old", "new"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Aggregate chapter chunk JSON files into per-book catalog files."
    )
    parser.add_argument(
        "--source-dir",
        default=str(script_dir / "chapter_chunk_catalog" / "chunks"),
        help="Directory containing per-chapter chunk JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(script_dir / "chapter_chunk_catalog_books"),
        help="Directory for per-book aggregate chunk JSON files.",
    )
    parser.add_argument(
        "--testament",
        choices=["old", "new", "all"],
        default="all",
        help="Limit aggregation to one testament.",
    )
    parser.add_argument(
        "--book",
        help="Optional single book or comma-separated list of books to aggregate.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize without writing aggregate files.",
    )
    return parser.parse_args(argv)


def requested_testaments(value: str) -> list[str]:
    if value == "all":
        return ["old", "new"]
    return [value]


def requested_books(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        normalize_book_key(piece)
        for piece in value.split(",")
        if piece.strip()
    }


def chapter_file_paths(source_dir: Path, testaments: list[str]) -> list[Path]:
    paths: list[Path] = []
    for testament in testaments:
        root = source_dir / testament
        if not root.exists():
            continue
        paths.extend(sorted(root.glob("*/*_chunks.json")))
    return paths


def normalize_chunks(items: Any, path: Path) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ValueError(f"{path}: expected a non-empty 'chunks' list.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: chunk {index} is not an object.")
        try:
            start_verse = int(item["start_verse"])
            end_verse = int(item["end_verse"])
        except Exception as exc:
            raise ValueError(f"{path}: chunk {index} is missing integer verse bounds.") from exc
        if start_verse > end_verse:
            raise ValueError(f"{path}: chunk {index} has start_verse > end_verse.")
        chunk_type = str(item.get("type", "")).strip()
        title = str(item.get("title", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not chunk_type:
            raise ValueError(f"{path}: chunk {index} has an empty type.")
        if not title:
            raise ValueError(f"{path}: chunk {index} has an empty title.")
        if not reason:
            raise ValueError(f"{path}: chunk {index} has an empty reason.")
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


def load_chapter_payload(path: Path) -> tuple[str, str, int, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a top-level JSON object.")

    testament = str(payload.get("testament", "")).strip().lower()
    if testament not in VALID_TESTAMENTS:
        raise ValueError(f"{path}: invalid or missing testament '{testament}'.")

    book = str(payload.get("book", "")).strip()
    if not book:
        raise ValueError(f"{path}: missing book name.")

    try:
        chapter = int(payload.get("chapter"))
    except Exception as exc:
        raise ValueError(f"{path}: invalid or missing chapter.") from exc
    if chapter <= 0:
        raise ValueError(f"{path}: chapter must be positive.")

    normalized = {
        "chapter": chapter,
        "chunks": normalize_chunks(payload.get("chunks"), path),
    }
    return testament, book, chapter, normalized


def aggregate_books(
    *,
    source_dir: Path,
    testaments: list[str],
    books_filter: set[str],
) -> dict[tuple[str, str], dict[int, dict[str, Any]]]:
    grouped: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
    for path in chapter_file_paths(source_dir, testaments):
        testament, book, chapter, chapter_payload = load_chapter_payload(path)
        book_key = normalize_book_key(book)
        if books_filter and book_key not in books_filter:
            continue
        group_key = (testament, book)
        chapter_map = grouped.setdefault(group_key, {})
        if chapter in chapter_map:
            raise ValueError(
                f"Duplicate chapter entry for {book} {chapter} in testament '{testament}'."
            )
        chapter_map[chapter] = chapter_payload
    return grouped


def write_book_payloads(
    grouped: dict[tuple[str, str], dict[int, dict[str, Any]]],
    *,
    output_dir: Path,
    dry_run: bool,
) -> list[Path]:
    written: list[Path] = []
    timestamp = utc_now()
    for testament, book in sorted(grouped.keys(), key=lambda item: (item[0], normalize_book_key(item[1]))):
        book_key = normalize_book_key(book)
        payload = {
            "schema_version": 1,
            "generated_at": timestamp,
            "testament": testament,
            "book": book,
            "book_key": book_key,
            "chapters": [
                grouped[(testament, book)][chapter]
                for chapter in sorted(grouped[(testament, book)].keys())
            ],
        }
        output_path = output_dir / testament / f"{book_key}_chunks.json"
        written.append(output_path)
        if dry_run:
            continue
        ensure_parent(output_path)
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_dir = Path(args.source_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    grouped = aggregate_books(
        source_dir=source_dir,
        testaments=requested_testaments(args.testament),
        books_filter=requested_books(args.book),
    )
    if not grouped:
        print("No chapter chunk files matched the current filter.")
        return 1

    written = write_book_payloads(grouped, output_dir=output_dir, dry_run=args.dry_run)
    chapter_total = sum(len(chapters) for chapters in grouped.values())
    action = "Would write" if args.dry_run else "Wrote"
    print(f"{action} {len(written)} aggregate book files from {chapter_total} chapter files.")
    for path in written:
        testament = path.parent.name
        print(f" - {testament}/{path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
