import re
import json
import sqlite3
from pathlib import Path
from typing import Dict, Tuple, List, Optional, Set

"""
bbli_to_json.py (2025‑05‑18 rev‑B)
=================================
Drop‑in converter that accepts either

1. **Plain UTF‑8** VPL Bible — lines like `GEN 1:1 In the beginning…`
2. **.bbli** databases used by the *AndBible* Android app (plain SQLite‑3).
   The schema varies wildly, so this revision adds **adaptive heuristics** that
   recognise the common patterns *and* the ultra‑minimal `Bible(Book,Chapter,
   Verse,Scripture)` layout you just met.

It produces **exactly** the nested‑dict JSON required by `vpl_to_json.py`:

```json
{
  "Genesis": {"1": {"1": "In the beginning …",  "2": "…"}},
  "Exodus" : { … }
}
```

Run:

```bash
python bbli_to_json.py lsv.bbli            # → lsv.json
python bbli_to_json.py some.vpl out.json
python bbli_to_json.py other.bbli --debug  # dump full schema on failure
```
"""

# ──────────────────────────────────────────────────────────────────────────────
# 0) Helpers & constants
# ──────────────────────────────────────────────────────────────────────────────
BOOK_ABBR_MAP = {  # 3‑letter → canonical
    'GEN': 'Genesis', 'EXO': 'Exodus', 'LEV': 'Leviticus', 'NUM': 'Numbers',
    'DEU': 'Deuteronomy', 'JOS': 'Joshua', 'JDG': 'Judges', 'RUT': 'Ruth',
    '1SA': '1 Samuel', '2SA': '2 Samuel', '1KI': '1 Kings', '2KI': '2 Kings',
    '1CH': '1 Chronicles', '2CH': '2 Chronicles', 'EZR': 'Ezra', 'NEH': 'Nehemiah',
    'EST': 'Esther', 'JOB': 'Job', 'PSA': 'Psalms', 'PRO': 'Proverbs',
    'ECC': 'Ecclesiastes', 'SNG': 'Song of Solomon', 'SON': 'Song of Solomon',
    'ISA': 'Isaiah', 'JER': 'Jeremiah', 'LAM': 'Lamentations', 'EZK': 'Ezekiel',
    'EZE': 'Ezekiel', 'DAN': 'Daniel', 'HOS': 'Hosea', 'JOL': 'Joel', 'AMO': 'Amos',
    'OBA': 'Obadiah', 'JON': 'Jonah', 'MIC': 'Micah', 'NAH': 'Nahum', 'NAM': 'Nahum',
    'HAB': 'Habakkuk', 'ZEP': 'Zephaniah', 'HAG': 'Haggai', 'ZEC': 'Zechariah',
    'MAL': 'Malachi', 'MAT': 'Matthew', 'MRK': 'Mark', 'MAR': 'Mark', 'LUK': 'Luke',
    'JHN': 'John', 'JOH': 'John', 'ACT': 'Acts', 'ROM': 'Romans', '1CO': '1 Corinthians',
    '2CO': '2 Corinthians', 'GAL': 'Galatians', 'EPH': 'Ephesians', 'PHP': 'Philippians',
    'PHI': 'Philippians', 'COL': 'Colossians', '1TH': '1 Thessalonians',
    '2TH': '2 Thessalonians', '1TI': '1 Timothy', '2TI': '2 Timothy', 'TIT': 'Titus',
    'PHM': 'Philemon', 'HEB': 'Hebrews', 'JAS': 'James', 'JAM': 'James',
    '1PE': '1 Peter', '2PE': '2 Peter', '1JN': '1 John', '2JN': '2 John',
    '3JN': '3 John', '1JO': '1 John', '2JO': '2 John', '3JO': '3 John',
    'JUD': 'Jude', 'REV': 'Revelation'
}
# canonical Protestant order → reverse‑lookup for numeric Book column
BOOK_ORDER = [
    'Genesis','Exodus','Leviticus','Numbers','Deuteronomy','Joshua','Judges','Ruth',
    '1 Samuel','2 Samuel','1 Kings','2 Kings','1 Chronicles','2 Chronicles','Ezra','Nehemiah',
    'Esther','Job','Psalms','Proverbs','Ecclesiastes','Song of Solomon','Isaiah','Jeremiah',
    'Lamentations','Ezekiel','Daniel','Hosea','Joel','Amos','Obadiah','Jonah','Micah','Nahum',
    'Habakkuk','Zephaniah','Haggai','Zechariah','Malachi','Matthew','Mark','Luke','John','Acts',
    'Romans','1 Corinthians','2 Corinthians','Galatians','Ephesians','Philippians','Colossians',
    '1 Thessalonians','2 Thessalonians','1 Timothy','2 Timothy','Titus','Philemon','Hebrews',
    'James','1 Peter','2 Peter','1 John','2 John','3 John','Jude','Revelation'
]
NUM2BOOK = {str(i+1): n for i, n in enumerate(BOOK_ORDER)}

VERSE_RX = re.compile(r'^([A-Za-z0-9]{3})\s+(\d+):(\d+)\s+(.+)$')

# ──────────────────────────────────────────────────────────────────────────────
# 1) Plain VPL parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_vpl(path: Path) -> Tuple[Dict, Set[str]]:
    bible, unmapped = {}, set()
    with path.open(encoding='utf-8') as fh:
        for raw in fh:
            m = VERSE_RX.match(raw.strip())
            if not m:
                continue
            abbr, ch, vs, txt = m.groups()
            book = BOOK_ABBR_MAP.get(abbr.upper())
            if not book:
                unmapped.add(abbr); continue
            bible.setdefault(book, {}).setdefault(ch, {})[vs] = txt
    return bible, unmapped

# ──────────────────────────────────────────────────────────────────────────────
# 2) Flexible .bbli (SQLite‑3) parser
# ──────────────────────────────────────────────────────────────────────────────

def looks_like_sqlite(fp: Path) -> bool:
    with fp.open('rb') as f:
        return f.read(16).startswith(b'SQLite format 3')

def columns(cur: sqlite3.Cursor, table: str) -> List[str]:
    return [c[1] for c in cur.execute(f'PRAGMA table_info("{table}")')]

def parse_bbli(path: Path, debug=False) -> Dict:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    # 2‑A) ultra‑minimal common table?
    if 'Bible' in {t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}:  
        cols = [c.lower() for c in columns(cur, 'Bible')]
        wanted = {'book','chapter','verse'}
        if wanted.issubset(set(cols)):
            txt_col = next((c for c in cols if c in {'text','content','scripture'}), None)
            if txt_col:
                sql = f"SELECT Book,Chapter,Verse,{txt_col} FROM Bible ORDER BY Book,Chapter,Verse"
                bible: Dict[str,Dict[str,Dict[str,str]]] = {}
                for b,ch,vs,tx in cur.execute(sql):
                    book = NUM2BOOK.get(str(b), str(b))  # numeric → name
                    bible.setdefault(book, {}).setdefault(str(ch), {})[str(vs)] = tx
                conn.close()
                return bible
    # 2‑B) generic adaptive discovery (fallback) -------------- #
    tbls = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    best_tbl = None; best_cols = set()
    text_cands = {'text','content','scripture'}
    for t in tbls:
        cols = {c.lower() for c in columns(cur,t)}
        if 'verse' in cols and cols & text_cands:
            best_tbl,best_cols = t, cols; break
    if not best_tbl:
        if debug:
            print("\nSchema dump:"); 
            for t in tbls: print('•', t, columns(cur,t))
        raise RuntimeError('Could not locate verse table')
    text_col = next(c for c in best_cols if c in text_cands)
    sql = f"SELECT Book,Chapter,Verse,{text_col} FROM {best_tbl} ORDER BY Book,Chapter,Verse"
    bible = {}
    for b,ch,vs,tx in cur.execute(sql):
        bk = NUM2BOOK.get(str(b), str(b)) if isinstance(b,(int,str)) else str(b)
        bible.setdefault(bk, {}).setdefault(str(ch), {})[str(vs)] = tx
    conn.close()
    return bible

# ──────────────────────────────────────────────────────────────────────────────
# 3) orchestrator
# ──────────────────────────────────────────────────────────────────────────────

def convert(src: Path, debug=False):
    if looks_like_sqlite(src):
        print('• Detected SQLite‑based BBLI → adaptive parsing …')
        return parse_bbli(src, debug), set()
    else:
        print('• Treating as UTF‑8 plain VPL …')
        return parse_vpl(src)

def main(src: str|Path, dst: str|Path|None=None, debug=False):
    srcp = Path(src)
    if not srcp.exists():
        raise FileNotFoundError(srcp)
    dstp = Path(dst) if dst else srcp.with_suffix('.json')
    bible, unmapped = convert(srcp, debug)
    dstp.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✅ Saved → {dstp}  (books: {len(bible)})")
    if unmapped:
        print('⚠️  Unmapped abbreviations:',','.join(sorted(unmapped)))

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Convert VPL / .bbli → nested JSON')
    p.add_argument('src', help='input file (.txt or .bbli)')
    p.add_argument('dst', nargs='?', help='output .json path')
    p.add_argument('--debug', action='store_true', help='dump schema details on failure')
    a = p.parse_args()
    main(a.src, a.dst, a.debug)
