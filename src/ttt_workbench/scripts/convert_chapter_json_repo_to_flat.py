#!/usr/bin/env python3
"""Flatten a chapter-per-file Bible JSON repository into study-pane rows.

Expected input layout:

    json/<TRANSLATION>/<testament>/<Book>/<chapter>.json

Each chapter file is expected to contain a mapping of verse numbers to verse
text. The output is a single flat JSON array with ``book``, ``chapter``,
``verse``, and ``text`` keys.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BOOK_ORDER = [
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    "Joshua",
    "Judges",
    "Ruth",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    "1 Chronicles",
    "2 Chronicles",
    "Ezra",
    "Nehemiah",
    "Esther",
    "Job",
    "Psalm",
    "Proverbs",
    "Ecclesiastes",
    "Song of Solomon",
    "Isaiah",
    "Jeremiah",
    "Lamentations",
    "Ezekiel",
    "Daniel",
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    "Matthew",
    "Mark",
    "Luke",
    "John",
    "Acts",
    "Romans",
    "1 Corinthians",
    "2 Corinthians",
    "Galatians",
    "Ephesians",
    "Philippians",
    "Colossians",
    "1 Thessalonians",
    "2 Thessalonians",
    "1 Timothy",
    "2 Timothy",
    "Titus",
    "Philemon",
    "Hebrews",
    "James",
    "1 Peter",
    "2 Peter",
    "1 John",
    "2 John",
    "3 John",
    "Jude",
    "Revelation",
]
BOOK_INDEX = {book: index for index, book in enumerate(BOOK_ORDER)}


def flatten_chapter_repo(repo_root: Path, translation: str) -> list[dict[str, Any]]:
    translation_dir = repo_root / "json" / translation
    if not translation_dir.is_dir():
        raise FileNotFoundError(f"Missing translation directory: {translation_dir}")

    rows: list[dict[str, Any]] = []
    for chapter_path in sorted(translation_dir.rglob("*.json")):
        rel = chapter_path.relative_to(translation_dir)
        if len(rel.parts) != 3:
            continue
        testament, book, chapter_file = rel.parts
        if not chapter_file.endswith(".json"):
            continue
        try:
            chapter = int(Path(chapter_file).stem)
        except ValueError:
            continue

        payload = json.loads(chapter_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        for verse_key, text in payload.items():
            try:
                verse = int(verse_key)
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "book": book.replace("_", " "),
                    "chapter": chapter,
                    "verse": verse,
                    "text": str(text),
                }
            )
    rows.sort(
        key=lambda row: (
            BOOK_INDEX.get(str(row["book"]), len(BOOK_INDEX)),
            int(row["chapter"]),
            int(row["verse"]),
        )
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten a chapter JSON repo.")
    parser.add_argument("repo_root", type=Path, help="Repository root containing json/<translation>/...")
    parser.add_argument("translation", help="Translation code, e.g. TLV")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Destination flat JSON file. Defaults to <translation>_Bible_flat.json in the current directory.",
    )
    args = parser.parse_args()

    output_path = args.output or Path(f"{args.translation}_Bible_flat.json")
    rows = flatten_chapter_repo(args.repo_root, args.translation)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} verse rows to {output_path}")


if __name__ == "__main__":
    main()
