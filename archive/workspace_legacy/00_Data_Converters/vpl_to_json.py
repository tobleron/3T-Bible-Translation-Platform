import re
import json

# Comprehensive abbreviation mapping including all common alternatives.
BOOK_ABBR_MAP = {
    'GEN': 'Genesis', 'EXO': 'Exodus', 'LEV': 'Leviticus', 'NUM': 'Numbers', 'DEU': 'Deuteronomy',
    'JOS': 'Joshua', 'JDG': 'Judges', 'RUT': 'Ruth', '1SA': '1 Samuel', '2SA': '2 Samuel',
    '1KI': '1 Kings', '2KI': '2 Kings', '1CH': '1 Chronicles', '2CH': '2 Chronicles',
    'EZR': 'Ezra', 'NEH': 'Nehemiah', 'EST': 'Esther', 'JOB': 'Job', 'PSA': 'Psalms',
    'PRO': 'Proverbs', 'ECC': 'Ecclesiastes', 'SNG': 'Song of Solomon', 'SON': 'Song of Solomon',
    'ISA': 'Isaiah', 'JER': 'Jeremiah', 'LAM': 'Lamentations', 'EZK': 'Ezekiel', 'EZE': 'Ezekiel',
    'DAN': 'Daniel', 'HOS': 'Hosea', 'JOL': 'Joel', 'AMO': 'Amos', 'OBA': 'Obadiah',
    'JON': 'Jonah', 'MIC': 'Micah', 'NAH': 'Nahum', 'NAM': 'Nahum', 'HAB': 'Habakkuk',
    'ZEP': 'Zephaniah', 'HAG': 'Haggai', 'ZEC': 'Zechariah', 'MAL': 'Malachi',
    'MAT': 'Matthew', 'MRK': 'Mark', 'MAR': 'Mark', 'LUK': 'Luke', 'JHN': 'John',
    'JOH': 'John', 'ACT': 'Acts', 'ROM': 'Romans', '1CO': '1 Corinthians', '2CO': '2 Corinthians',
    'GAL': 'Galatians', 'EPH': 'Ephesians', 'PHP': 'Philippians', 'PHI': 'Philippians',
    'COL': 'Colossians', '1TH': '1 Thessalonians', '2TH': '2 Thessalonians', '1TI': '1 Timothy',
    '2TI': '2 Timothy', 'TIT': 'Titus', 'PHM': 'Philemon', 'HEB': 'Hebrews', 'JAS': 'James',
    'JAM': 'James', '1PE': '1 Peter', '2PE': '2 Peter',
    '1JN': '1 John', '2JN': '2 John', '3JN': '3 John',
    '1JO': '1 John', '2JO': '2 John', '3JO': '3 John',  # <-- covers your case
    'JUD': 'Jude', 'REV': 'Revelation'
}

def parse_vpl(vpl_path):
    bible = {}
    unmapped = set()
    with open(vpl_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            m = re.match(r'^([A-Z0-9]{3}) (\d+):(\d+)\s+(.+)', line)
            if not m:
                continue
            abbr, chap, verse, text = m.groups()
            book = BOOK_ABBR_MAP.get(abbr)
            if not book:
                unmapped.add(abbr)
                continue
            if book not in bible:
                bible[book] = {}
            if chap not in bible[book]:
                bible[book][chap] = {}
            bible[book][chap][verse] = text
    return bible, unmapped

if __name__ == "__main__":
    input_vpl = "engemtv_vpl.txt"      # Path to your VPL file
    output_json = "EMTV_bible.json"    # Output JSON

    bible_json, unmapped = parse_vpl(input_vpl)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(bible_json, f, ensure_ascii=False, indent=2)

    print("Conversion complete! Output written to", output_json)
    if unmapped:
        print("Warning: Unmapped abbreviations encountered:", ', '.join(sorted(unmapped)))
