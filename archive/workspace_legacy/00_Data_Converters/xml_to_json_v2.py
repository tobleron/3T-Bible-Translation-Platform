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

# ––– 2. Parser  –––
def parse_xml(xml_path: str) -> dict:
    """
    Return a nested dict:  {Book → {Chapter → {Verse → text}}}
    Handles both LSB-style and NJB-style XML structures.
    """
    from collections import defaultdict
    import xml.etree.ElementTree as ET

    bible = defaultdict(lambda: defaultdict(dict))

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # --- detect flavour -----------------------------------------------------
    if root.tag.lower() == 'xmlbible':          # New Jerusalem Bible
        book_tag, chap_tag, verse_tag = 'BIBLEBOOK', 'CHAPTER', 'VERS'
        book_attr, chap_attr, verse_attr = 'bnumber', 'cnumber', 'vnumber'
    else:                                       # LSB - style (default)
        book_tag, chap_tag, verse_tag = 'book', 'chapter', 'verse'
        book_attr = chap_attr = verse_attr = 'number'

    # --- iterate -----------------------------------------------------------
    for book_el in root.iter(book_tag):
        num = int(book_el.attrib.get(book_attr, '0'))
        if not (1 <= num < len(BOOKS)):      # allow books >66 but skip unknown
            print(f'⚠︎ Skipping unknown book number {num} in {xml_path}')
            continue
        book_name = BOOKS[num]

        for ch_el in book_el.iter(chap_tag):
            chap = ch_el.attrib[chap_attr]
            for v_el in ch_el.iter(verse_tag):
                verse = v_el.attrib[verse_attr]
                text = (v_el.text or '').strip()
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
