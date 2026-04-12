#!/usr/bin/env python3
"""
convert_Bible_to_flat.py
────────────────────────
Flatten a nested-book-chapter-verse Bible JSON into a simple list of rows.

USAGE
-----
    # Typical: auto-names output <stem>_flat.json
    python convert_Bible_to_flat.py Genesis.json

    # Optional: explicit output filename
    python convert_Bible_to_flat.py Genesis.json custom_output.json
"""

import json
import sys
from pathlib import Path

def convert_nested_to_flat(input_path: Path, output_path: Path) -> None:
    """Read nested JSON from *input_path* and write flattened JSON to *output_path*."""
    with input_path.open("r", encoding="utf-8") as f:
        nested_data = json.load(f)

    flat_output = []
    for book, chapters in nested_data.items():
        for chapter_str, verses in chapters.items():
            chapter = int(chapter_str)
            for verse_str, text in verses.items():
                verse = int(verse_str)
                flat_output.append({
                    "book": book,
                    "chapter": chapter,
                    "verse": verse,
                    "text": text
                })

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(flat_output, f, ensure_ascii=False, indent=2)

    print(f"✅ Conversion complete → {output_path}")

# ----------------------------------------------------------------------
if __name__ == "__main__":
    # ------------------------------------------------------------------
    # Parse CLI arguments
    # ------------------------------------------------------------------
    if not (2 <= len(sys.argv) <= 3):
        sys.exit("Usage: python convert_Bible_to_flat.py <input.json> [output.json]")

    input_file = Path(sys.argv[1])

    if not input_file.exists():
        sys.exit(f"❌ Input file does not exist: {input_file}")

    # Derive default output name if not supplied
    if len(sys.argv) == 3:
        output_file = Path(sys.argv[2])
    else:
        output_file = input_file.with_name(f"{input_file.stem}_flat.json")

    convert_nested_to_flat(input_file, output_file)
