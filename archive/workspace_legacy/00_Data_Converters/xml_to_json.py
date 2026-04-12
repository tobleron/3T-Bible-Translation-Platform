#!/usr/bin/env python3
"""
xml_to_json.py  – Convert an English CSB-style XML Bible into a nested-dict JSON.

Usage (from a shell):
    python xml_to_json.py EnglishCSBBible.xml CSB_bible.json
"""

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

# ------------------------------------------------------------
# 1. Canonical book-name list (1-based index matches <book number="…">)
# ------------------------------------------------------------
BOOKS = [
    None,  # pad so index == book number
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah",
    "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum",
    "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John",
    "3 John", "Jude", "Revelation",
]

# Quick sanity check
if len(BOOKS) != 67:
    raise RuntimeError("BOOKS list must have 66 names (+1 dummy at index 0)")

# ------------------------------------------------------------
# 2. Parser
# ------------------------------------------------------------
def parse_xml(xml_path: str) -> dict:
    """
    Return a nested dict:  {Book → {Chapter → {Verse → text}}}
    """
    bible = defaultdict(lambda: defaultdict(dict))

    tree = ET.parse(xml_path)
    root = tree.getroot()

    for book_el in root.iter("book"):
        num = int(book_el.attrib["number"])
        if not (1 <= num <= 66):
            raise ValueError(f"Book number {num} out of range 1-66")
        book_name = BOOKS[num]

        for ch_el in book_el.iter("chapter"):
            chap = ch_el.attrib["number"]
            for v_el in ch_el.iter("verse"):
                verse = v_el.attrib["number"]
                text = (v_el.text or "").strip()
                bible[book_name][chap][verse] = text

    return bible

# ------------------------------------------------------------
# 3. Script entry-point
# ------------------------------------------------------------
def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        sys.exit("Usage: python xml_to_json.py <input.xml> <output.json>")

    in_xml, out_json = argv
    bible_dict = parse_xml(in_xml)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(bible_dict, f, ensure_ascii=False, indent=2)

    print(f"Conversion complete!  Output written to {out_json}")

if __name__ == "__main__":
    main()
