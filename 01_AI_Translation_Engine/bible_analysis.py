import os
import json
import re
from datetime import datetime

FLAT_BIBLES_DIR = "001_Flat_Bibles"
OUTPUT_DIR = "003_Output"

def parse_verse_range(verse_range):
    m = re.match(r'([1-3]?\s?\w+)\s*(\d+):(\d+)(?:-(\d+))?', verse_range.strip(), re.I)
    if not m:
        raise ValueError("Invalid verse range format. Example: Matthew 18:21-35")
    book = m.group(1).replace(" ", "")
    chapter = int(m.group(2))
    start_verse = int(m.group(3))
    end_verse = int(m.group(4)) if m.group(4) else start_verse
    return book, chapter, start_verse, end_verse

def get_flat_bibles(directory):
    files = []
    for fname in os.listdir(directory):
        if fname.endswith('.json') and not fname.startswith('_'):
            files.append(fname)
    files.sort()
    return files

def get_3letter_code(fname):
    m = re.search(r'([A-Za-z]{3})_Bible_flat\.json', fname)
    if m:
        return m.group(1).upper()
    return fname[:3].upper()

def load_bible(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def filter_verses(bible_data, book, chapter, start_verse, end_verse):
    filtered = {}
    for entry in bible_data:
        if (
            entry['book'].replace(" ", "").lower() == book.lower() and
            int(entry['chapter']) == chapter and
            start_verse <= int(entry['verse']) <= end_verse and
            'text' in entry
        ):
            v = int(entry['verse'])
            filtered[v] = entry['text']
    return filtered

def main():
    print("Enter verse range (e.g., Matthew 18:21-35):")
    verse_range = input().strip()
    book, chapter, start_verse, end_verse = parse_verse_range(verse_range)

    files = get_flat_bibles(FLAT_BIBLES_DIR)
    if not files:
        print("No flat bibles found!")
        return

    print("\nAvailable flat bibles:")
    for idx, fname in enumerate(files, 1):
        print(f"[{idx}] {fname}")
    print("Select ones you need to include (comma separated numbers):")
    choices = input().strip().split(',')
    try:
        selected = [files[int(c.strip())-1] for c in choices]
    except Exception:
        print("Invalid selection.")
        return

    bibles = {}
    for fname in selected:
        code = get_3letter_code(fname)
        path = os.path.join(FLAT_BIBLES_DIR, fname)
        try:
            bibles[code] = load_bible(path)
        except Exception as e:
            print(f"Failed to load {fname}: {e}")

    verses_in_range = range(start_verse, end_verse + 1)
    output_lines = []

    for vnum in verses_in_range:
        for code, data in bibles.items():
            filtered = filter_verses(data, book, chapter, vnum, vnum)
            text = filtered.get(vnum, "")
            line = f"v{vnum}_{code}: {text}"
            print(line)
            output_lines.append(line)
        print("---")
        output_lines.append("---")  # Separator between verse sets

    dt = datetime.now().strftime("%d%m%y%H%M")
    book_part = book.replace(" ", "_")
    vrange_part = f"{chapter}_{start_verse}-{end_verse}"
    filename = f"{book_part}_{vrange_part}_analysis_{dt}.md"
    out_path = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"\nMarkdown output saved to: {out_path}")

if __name__ == "__main__":
    main()
