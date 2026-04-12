#!/usr/bin/env python3
"""
Aggregate_Books_TTT v0.8 — Flat verse-by-verse JSON
===================================================
* Scans all chapter JSON files under `data/final/_HOLY_BIBLE`.
* Produces **one single array** of objects in the exact schema:

    {
        "book": "Matthew",
        "chapter": 10,
        "verse": 7,
        "text": "..."          # optional
        "title": "..."         # optional (section headline)
        "footnotes": [ {...} ]  # optional
    }

  Only one of `text`, `title`, or `footnotes` appears in each entry.
* Footnotes with empty / "nan" content are skipped.
* Output saved to `output/builds/TTT_flat_bible_v0.8_<DDMMYYYY_HHMM>.json`.
* Requires **no** command‑line flags — it always exports the flat format.

Run:
    python Aggregate_Books_TTT_v0.8.py
"""

import json
from pathlib import Path
from datetime import datetime
import sys

from ttt_core.config import load_config

# -------------------------------------------------------------
CONFIG      = load_config()
PATHS       = CONFIG["paths"]
HOLY_DIR    = Path(PATHS["bible_dir"])
OUTPUT_DIR  = Path(PATHS["output"]) / 'builds'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STAMP       = datetime.now().strftime('%d%m%Y_%H%M')
OUT_PATH    = OUTPUT_DIR / f'TTT_flat_bible_v0.8_{STAMP}.json'

# -------------------------------------------------------------
# Helper — safe int cast (JSON may store as str)
def safe_int(x):
    try:
        return int(x)
    except (ValueError, TypeError):
        return None

# Validate all JSON files before processing
for p in HOLY_DIR.rglob('*.json'):
    try:
        json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print(f"❌ JSON error in {p} — line {e.lineno}, col {e.colno}: {e.msg}")
        sys.exit(1)

# -------------------------------------------------------------
entries = []  # final flat list

for chapter_path in sorted(HOLY_DIR.rglob('*.json')):
    data = json.loads(chapter_path.read_text(encoding='utf-8'))
    book    = data.get('book')
    chapter = safe_int(data.get('chapter'))
    if not book or chapter is None:
        continue  # malformed

    # 1) Sections & verses
    for section in data.get('sections', []):
        verses = section.get('verses', [])
        if not verses:
            continue

        # Section headline ⇒ title entry
        headline = (section.get('headline') or '').strip()
        if headline:
            first_verse_num = safe_int(verses[0].get('verse') or verses[0].get('verse_number'))
            if first_verse_num is not None:
                entries.append({
                    "book": book,
                    "chapter": chapter,
                    "verse": first_verse_num,
                    "title": headline
                })

        # Individual verses ⇒ text entries
        for v in verses:
            verse_num = safe_int(v.get('verse') or v.get('verse_number'))
            text      = v.get('text', '').strip()
            if verse_num is None or not text:
                continue
            entries.append({
                "book": book,
                "chapter": chapter,
                "verse": verse_num,
                "text": text
            })

    # 2) Footnotes (chapter‑level list)
    for fn in data.get('footnotes', []):
        content = (fn.get('content') or '').strip()
        if not content or content.lower() == 'nan':
            continue
        verse_num = safe_int(fn.get('verse'))
        if verse_num is None:
            continue
        entries.append({
            "book": book,
            "chapter": chapter,
            "verse": verse_num,
            "footnotes": [{
                "letter": fn.get('letter', ''),
                "content": content
            }]
        })

# -------------------------------------------------------------
# Sort entries deterministically: book, chapter, verse, and then by key order
entries.sort(key=lambda e: (e['book'], e['chapter'], e['verse']))

with OUT_PATH.open('w', encoding='utf-8') as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)

print('✓ Flat JSON v0.8 written to', OUT_PATH)
