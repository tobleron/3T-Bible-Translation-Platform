import os
import re
from datetime import datetime
from pathlib import Path

from ttt_core.data.repositories import ProjectPaths, SourceRepository

PATHS = ProjectPaths()
SOURCE_REPO = SourceRepository(PATHS)
OUTPUT_DIR = PATHS.reports_dir / "analysis"

def parse_verse_range(verse_range):
    m = re.match(r'([1-3]?\s?\w+)\s*(\d+):(\d+)(?:-(\d+))?', verse_range.strip(), re.I)
    if not m:
        raise ValueError("Invalid verse range format. Example: Matthew 18:21-35")
    book = m.group(1).replace(" ", "")
    chapter = int(m.group(2))
    start_verse = int(m.group(3))
    end_verse = int(m.group(4)) if m.group(4) else start_verse
    return book, chapter, start_verse, end_verse

def main():
    print("Enter verse range (e.g., Matthew 18:21-35):")
    verse_range_input = input().strip()
    try:
        book, chapter, start_verse, end_verse = parse_verse_range(verse_range_input)
    except ValueError as e:
        print(e)
        return

    available_sources = SOURCE_REPO.list_sources()
    if not available_sources:
        print("No source translations found!")
        return

    print("\nAvailable Source Translations:")
    for idx, alias in enumerate(available_sources, 1):
        print(f"[{idx}] {alias}")
    print("Select ones you need to include (comma separated numbers, or 'all'):")
    
    selection = input().strip().lower()
    if selection == 'all' or selection == '':
        selected_aliases = available_sources
    else:
        try:
            choices = selection.split(',')
            selected_aliases = [available_sources[int(c.strip())-1] for c in choices]
        except Exception:
            print("Invalid selection.")
            return

    verses_in_range = range(start_verse, end_verse + 1)
    output_lines = []

    for vnum in verses_in_range:
        for alias in selected_aliases:
            text = SOURCE_REPO.verse_text(alias, book, chapter, vnum)
            line = f"v{vnum}_{alias}: {text}"
            print(line)
            output_lines.append(line)
        print("---")
        output_lines.append("---")  # Separator between verse sets

    dt = datetime.now().strftime("%d%m%y%H%M")
    book_part = book.replace(" ", "_")
    vrange_part = f"{chapter}_{start_verse}-{end_verse}"
    filename = f"{book_part}_{vrange_part}_analysis_{dt}.md"
    out_path = OUTPUT_DIR / filename

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(output_lines), encoding='utf-8')

    print(f"\nMarkdown output saved to: {out_path}")

if __name__ == "__main__":
    main()
