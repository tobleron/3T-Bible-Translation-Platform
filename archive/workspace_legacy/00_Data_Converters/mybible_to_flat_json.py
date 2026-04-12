#!/usr/bin/env python3
"""
mybible_to_flat_json.py
────────────────────────────
Convert a MyBible .bbl.mybible SQLite database (with `bible` table) to a flat JSON for analysis.

USAGE
-----
    python mybible_to_flat_json.py MLV_bbl.mybible
    # Optional output filename:
    python mybible_to_flat_json.py MLV_bbl.mybible output.json
"""

import sys
import sqlite3
import json
from pathlib import Path

# Map book numbers to standard names (adjust if needed for your analyzer)
MYBIBLE_BOOKS = [
    None, "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles",
    "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations", "Ezekiel",
    "Daniel", "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum",
    "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi", "Matthew", "Mark",
    "Luke", "John", "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians",
    "Ephesians", "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James", "1 Peter",
    "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation"
]

def convert_mybible_to_flat(input_path: Path, output_path: Path):
    conn = sqlite3.connect(str(input_path))
    cursor = conn.cursor()
    cursor.execute("SELECT book, chapter, verse, scripture FROM bible ORDER BY book, chapter, verse")
    flat_output = []
    for book_num, chapter, verse, text in cursor.fetchall():
        book_name = MYBIBLE_BOOKS[book_num] if 0 < book_num < len(MYBIBLE_BOOKS) else f"Book{book_num}"
        flat_output.append({
            "book": book_name,
            "chapter": chapter,
            "verse": verse,
            "text": text
        })
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(flat_output, f, ensure_ascii=False, indent=2)
    print(f"✅ Conversion complete → {output_path}")
    conn.close()

if __name__ == "__main__":
    if not (2 <= len(sys.argv) <= 3):
        sys.exit("Usage: python mybible_to_flat_json.py <input.bbl.mybible> [output.json]")
    input_file = Path(sys.argv[1])
    if not input_file.exists():
        sys.exit(f"❌ Input file does not exist: {input_file}")
    output_file = Path(sys.argv[2]) if len(sys.argv) == 3 else input_file.with_suffix('.json')
    convert_mybible_to_flat(input_file, output_file)
