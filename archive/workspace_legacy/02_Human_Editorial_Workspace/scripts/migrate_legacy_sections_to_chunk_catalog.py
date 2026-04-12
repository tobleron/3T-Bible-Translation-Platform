#!/usr/bin/env python3
"""Migrate committed chapter section boundaries into approved chunk catalogs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = REPO_ROOT / "02_Human_Editorial_Workspace"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from ttt_core.data.repositories import BibleRepository, ProjectPaths
from ttt_core.utils import normalize_book_key

from ttt_webapp.chunk_catalog import ChunkCatalogRepository


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write approved chunk catalog files from committed chapter section boundaries."
    )
    parser.add_argument(
        "--testament",
        choices=["old", "new", "all"],
        default="all",
        help="Limit migration to one testament.",
    )
    parser.add_argument("--book", help="Optional single book or comma-separated list.")
    parser.add_argument("--start-chapter", type=int, help="Optional first chapter to migrate.")
    parser.add_argument("--end-chapter", type=int, help="Optional last chapter to migrate.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing chapter chunk files instead of skipping them.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Summarize the migration without writing files.",
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


def chapter_in_range(args: argparse.Namespace, chapter: int) -> bool:
    if args.start_chapter and chapter < args.start_chapter:
        return False
    if args.end_chapter and chapter > args.end_chapter:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = ProjectPaths(workspace_dir=WORKSPACE_DIR, repo_root=REPO_ROOT)
    bible_repo = BibleRepository(paths)
    chunk_repo = ChunkCatalogRepository(paths, bible_repo)

    book_filter = requested_books(args.book)
    touched_books: set[tuple[str, str]] = set()
    migrated_paths: list[Path] = []
    skipped_existing = 0
    skipped_without_committed_sections = 0

    for testament in requested_testaments(args.testament):
        for book in bible_repo.books_for_testament(testament):
            if book_filter and normalize_book_key(book) not in book_filter:
                continue
            for chapter in bible_repo.chapters_for_book(testament, book):
                if not chapter_in_range(args, chapter):
                    continue
                payload = chunk_repo.committed_section_payload(testament, book, chapter)
                if payload is None:
                    skipped_without_committed_sections += 1
                    continue

                output_path = chunk_repo.chapter_payload_path(testament, book, chapter)
                if output_path.exists() and not args.force:
                    skipped_existing += 1
                    continue

                migrated_paths.append(output_path)
                touched_books.add((testament, book))
                if args.dry_run:
                    continue
                chunk_repo.save_chapter_payload(testament, book, chapter, payload)

    if args.dry_run:
        action = "Would migrate"
    else:
        for testament, book in sorted(touched_books, key=lambda item: (item[0], normalize_book_key(item[1]))):
            chunk_repo.write_book_payload(testament, book)
        action = "Migrated"

    print(
        f"{action} {len(migrated_paths)} chapters into approved chunk catalogs. "
        f"Skipped {skipped_existing} existing files and {skipped_without_committed_sections} chapters without committed section text."
    )
    for path in migrated_paths:
        print(f" - {path.relative_to(WORKSPACE_DIR)}")
    if not args.dry_run and touched_books:
        print(f"Updated {len(touched_books)} aggregate book catalog files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
