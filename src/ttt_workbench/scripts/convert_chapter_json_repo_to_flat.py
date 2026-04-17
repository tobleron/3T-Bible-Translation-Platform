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
