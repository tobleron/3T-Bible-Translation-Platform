#!/usr/bin/env python3
"""Convert archived Bible JSON into flat verse rows for the study picker.

The archived Bible databases in this repo use a nested structure:

    {
      "translation": "...",
      "books": [
        {"name": "Genesis", "chapters": [{"chapter": 1, "verses": [...]}]}
      ]
    }

The study pane expects flat verse rows:

    [{"book": "Genesis", "chapter": 1, "verse": 1, "text": "..."}]

This script bridges the two formats and writes the output as UTF-8 JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def flatten_archive_bible(payload: dict[str, Any]) -> list[dict[str, Any]]:
    books = payload.get("books", [])
    if not isinstance(books, list):
        raise ValueError("Expected 'books' to be a list.")

    flat_rows: list[dict[str, Any]] = []
    for book_entry in books:
        if not isinstance(book_entry, dict):
            continue
        book_name = str(book_entry.get("name", "")).strip()
        chapters = book_entry.get("chapters", [])
        if not book_name or not isinstance(chapters, list):
            continue
        for chapter_entry in chapters:
            if not isinstance(chapter_entry, dict):
                continue
            chapter = int(chapter_entry.get("chapter", 0))
            verses = chapter_entry.get("verses", [])
            if chapter <= 0 or not isinstance(verses, list):
                continue
            for verse_entry in verses:
                if not isinstance(verse_entry, dict):
                    continue
                verse = int(verse_entry.get("verse", 0))
                text = str(verse_entry.get("text", ""))
                if verse <= 0:
                    continue
                flat_rows.append(
                    {
                        "book": book_name,
                        "chapter": chapter,
                        "verse": verse,
                        "text": text,
                    }
                )
    return flat_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten archived Bible JSON.")
    parser.add_argument("input", type=Path, help="Archived nested Bible JSON")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Destination flat JSON. Defaults to <input>_flat.json",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    output_path: Path = args.output or input_path.with_name(f"{input_path.stem}_flat.json")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    flat_rows = flatten_archive_bible(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(flat_rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(flat_rows)} verse rows to {output_path}")


if __name__ == "__main__":
    main()
