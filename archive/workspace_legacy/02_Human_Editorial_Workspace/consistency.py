import argparse
import json
import os
import re

# FULL book mapping
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

# SBLGNT file code by book name (mapping lowercased book to file prefix)
SBLGNT_FILE_MAP = {
    "matthew": "61-Mt-morphgnt.txt", "matt": "61-Mt-morphgnt.txt",
    "mark": "62-Mk-morphgnt.txt", "mk": "62-Mk-morphgnt.txt",
    "luke": "63-Lk-morphgnt.txt", "lk": "63-Lk-morphgnt.txt",
    "john": "64-Jn-morphgnt.txt", "jn": "64-Jn-morphgnt.txt",
    "acts": "65-Ac-morphgnt.txt",
    "romans": "66-Ro-morphgnt.txt", "rom": "66-Ro-morphgnt.txt",
    "1 corinthians": "67-1Co-morphgnt.txt", "1corinthians": "67-1Co-morphgnt.txt", "1 cor": "67-1Co-morphgnt.txt", "1co": "67-1Co-morphgnt.txt",
    "2 corinthians": "68-2Co-morphgnt.txt", "2corinthians": "68-2Co-morphgnt.txt", "2 cor": "68-2Co-morphgnt.txt", "2co": "68-2Co-morphgnt.txt",
    "galatians": "69-Ga-morphgnt.txt", "gal": "69-Ga-morphgnt.txt",
    "ephesians": "70-Eph-morphgnt.txt", "eph": "70-Eph-morphgnt.txt",
    "philippians": "71-Php-morphgnt.txt", "php": "71-Php-morphgnt.txt", "phil": "71-Php-morphgnt.txt",
    "colossians": "72-Col-morphgnt.txt", "col": "72-Col-morphgnt.txt",
    "1 thessalonians": "73-1Th-morphgnt.txt", "1thessalonians": "73-1Th-morphgnt.txt", "1 thess": "73-1Th-morphgnt.txt", "1th": "73-1Th-morphgnt.txt",
    "2 thessalonians": "74-2Th-morphgnt.txt", "2thessalonians": "74-2Th-morphgnt.txt", "2 thess": "74-2Th-morphgnt.txt", "2th": "74-2Th-morphgnt.txt",
    "1 timothy": "75-1Ti-morphgnt.txt", "1timothy": "75-1Ti-morphgnt.txt", "1 tim": "75-1Ti-morphgnt.txt", "1ti": "75-1Ti-morphgnt.txt",
    "2 timothy": "76-2Ti-morphgnt.txt", "2timothy": "76-2Ti-morphgnt.txt", "2 tim": "76-2Ti-morphgnt.txt", "2ti": "76-2Ti-morphgnt.txt",
    "titus": "77-Tit-morphgnt.txt", "tit": "77-Tit-morphgnt.txt",
    "philemon": "78-Phm-morphgnt.txt", "phlm": "78-Phm-morphgnt.txt",
    "hebrews": "79-Heb-morphgnt.txt", "heb": "79-Heb-morphgnt.txt",
    "james": "80-Jas-morphgnt.txt", "jas": "80-Jas-morphgnt.txt",
    "1 peter": "81-1Pe-morphgnt.txt", "1peter": "81-1Pe-morphgnt.txt", "1pe": "81-1Pe-morphgnt.txt", "1pet": "81-1Pe-morphgnt.txt",
    "2 peter": "82-2Pe-morphgnt.txt", "2peter": "82-2Pe-morphgnt.txt", "2pe": "82-2Pe-morphgnt.txt", "2pet": "82-2Pe-morphgnt.txt",
    "1 john": "83-1Jn-morphgnt.txt", "1john": "83-1Jn-morphgnt.txt", "1jn": "83-1Jn-morphgnt.txt",
    "2 john": "84-2Jn-morphgnt.txt", "2john": "84-2Jn-morphgnt.txt", "2jn": "84-2Jn-morphgnt.txt",
    "3 john": "85-3Jn-morphgnt.txt", "3john": "85-3Jn-morphgnt.txt", "3jn": "85-3Jn-morphgnt.txt",
    "jude": "86-Jud-morphgnt.txt", "jud": "86-Jud-morphgnt.txt",
    "revelation": "87-Re-morphgnt.txt", "rev": "87-Re-morphgnt.txt"
}

def parse_reference(ref_str):
    """Parse reference string, e.g. 'Matthew 1:1-5'"""
    m = re.match(r"([1-3]?\s?[A-Za-z]+)\s+(\d+):(\d+)(?:-(\d+))?", ref_str.strip())
    if not m:
        raise ValueError("Reference not in 'Book Chapter:Verse[-Verse]' format")
    book = m.group(1).strip().lower()
    chapter = int(m.group(2))
    startv = int(m.group(3))
    endv = int(m.group(4)) if m.group(4) else startv
    return book, chapter, startv, endv

def get_morph_file(book):
    """Get morphgnt filename for book"""
    if book in SBLGNT_FILE_MAP:
        return os.path.join("sblgnt", SBLGNT_FILE_MAP[book])
    # e.g. fallback for '1corinthians' when user enters '1 corinthians'
    book_spaces_no = book.replace(" ", "")
    if book_spaces_no in SBLGNT_FILE_MAP:
        return os.path.join("sblgnt", SBLGNT_FILE_MAP[book_spaces_no])
    raise ValueError(f"Unknown book name '{book}' (no morphgnt file)")

def load_morphgnt_verses(morph_filename, chapter, startv, endv):
    """Return a dict: {verse_num: {'lemmas': [...], 'words': [...]}}"""
    verses = {}
    if not os.path.exists(morph_filename):
        raise FileNotFoundError(f"Could not find {morph_filename}")
    with open(morph_filename, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ref = line[:6]
            chap = int(ref[2:4])
            verse = int(ref[4:6])
            if chap == chapter and startv <= verse <= endv:
                parts = line.strip().split()
                word = parts[3]
                lemma = parts[-1]
                if verse not in verses:
                    verses[verse] = {'lemmas': [], 'words': []}
                verses[verse]['lemmas'].append(lemma)
                verses[verse]['words'].append(word)
    return verses

def load_english_json(filename, book, chapter, startv, endv):
    """Return a dict: {verse_num: english-text}"""
    with open(filename, encoding="utf-8") as f:
        all = json.load(f)
    out = {}
    for obj in all:
        if (
            obj.get("book", "").strip().lower() == book
            and obj.get("chapter") == chapter
            and startv <= obj.get("verse", 0) <= endv
        ):
            out[obj["verse"]] = obj.get("text", "")
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", help="Scripture range (e.g. 'Matthew 1:1-5')")
    parser.add_argument("--eng", default="english_hb.json", help="English translation JSON")
    args = parser.parse_args()

    # Parse and get file
    book, chapter, startv, endv = parse_reference(args.reference)
    morph_file = get_morph_file(book)
    verses = load_morphgnt_verses(morph_file, chapter, startv, endv)
    english = load_english_json(args.eng, book, chapter, startv, endv)
    # Output title
    prompt = f"**Translation Analysis: {args.reference}**\n\n"

    for v in range(startv, endv + 1):
        prompt += f"## {book.title()} {chapter}:{v}\n"
        prompt += f"ENGLISH: {english.get(v, 'TRANSLATION NOT FOUND')}\n"
        prompt += f"GREEK: {' '.join(verses.get(v, {}).get('words', []))}\n"
        prompt += f"LEMMAS: {', '.join(verses.get(v, {}).get('lemmas', []))}\n\n"

    # Add task instructions
    prompt += "**Analysis Tasks:**\n"
    prompt += "1. ACCURACY: Compare English translations to Greek lemmas\n"
    prompt += "2. CONSISTENCY: Track word choices for recurring lemmas\n"
    prompt += "3. OUTPUT: JSON mapping of lemmas to your translations\n"
    prompt += "   Format: {lemma: {'translations': [list], 'recommended': 'most_consistent_word'}}\n"

    # Write to file
    safe_ref = args.reference.replace(" ", "_").replace(":", "-")
    outfile = f"prompt_{safe_ref}.txt"
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"Success! Output saved to '{outfile}'")

if __name__ == "__main__":
    main()
