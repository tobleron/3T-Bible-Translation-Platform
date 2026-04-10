"""Common utility functions: book codes, parsing, JSON helpers."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

BOOK_REF_CODES = {
    "genesis": "Gen",
    "exodus": "Exod",
    "leviticus": "Lev",
    "numbers": "Num",
    "deuteronomy": "Deut",
    "joshua": "Josh",
    "judges": "Judg",
    "ruth": "Ruth",
    "1samuel": "1Sam",
    "2samuel": "2Sam",
    "1kings": "1Kgs",
    "2kings": "2Kgs",
    "1chronicles": "1Chr",
    "2chronicles": "2Chr",
    "ezra": "Ezra",
    "nehemiah": "Neh",
    "esther": "Esth",
    "job": "Job",
    "psalms": "Ps",
    "psalm": "Ps",
    "proverbs": "Pro",
    "ecclesiastes": "Eccl",
    "songofsongs": "Sng",
    "songofsolomon": "Sng",
    "isaiah": "Isa",
    "jeremiah": "Jer",
    "lamentations": "Lam",
    "ezekiel": "Ezek",
    "daniel": "Dan",
    "hosea": "Hos",
    "joel": "Joel",
    "amos": "Amos",
    "obadiah": "Obad",
    "jonah": "Jonah",
    "micah": "Mic",
    "nahum": "Nah",
    "habakkuk": "Hab",
    "zephaniah": "Zeph",
    "haggai": "Hag",
    "zechariah": "Zech",
    "malachi": "Mal",
    "matthew": "Mat",
    "mark": "Mk",
    "luke": "Luk",
    "john": "Jhn",
    "acts": "Act",
    "romans": "Rom",
    "1corinthians": "1Co",
    "2corinthians": "2Co",
    "galatians": "Gal",
    "ephesians": "Eph",
    "philippians": "Php",
    "colossians": "Col",
    "1thessalonians": "1Th",
    "2thessalonians": "2Th",
    "1timothy": "1Ti",
    "2timothy": "2Ti",
    "titus": "Tit",
    "philemon": "Phm",
    "hebrews": "Heb",
    "james": "Jas",
    "1peter": "1Pe",
    "2peter": "2Pe",
    "1john": "1Jn",
    "2john": "2Jn",
    "3john": "3Jn",
    "jude": "Jud",
    "revelation": "Rev",
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def extract_json_payload(text: str) -> dict | list | None:
    text = text.strip()
    if not text:
        return None
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


def repair_linewise_json_strings(text: str) -> tuple[str, bool]:
    changed = False
    repaired_lines: list[str] = []
    for line in text.splitlines():
        colon = line.find(":")
        if colon == -1:
            repaired_lines.append(line)
            continue
        after = line[colon + 1 :]
        stripped = after.lstrip()
        if not stripped.startswith('"'):
            repaired_lines.append(line)
            continue
        leading_ws = after[: len(after) - len(stripped)]
        trimmed = stripped.rstrip()
        trailing_ws = stripped[len(trimmed) :]
        trailing = ""
        if trimmed.endswith(","):
            trailing = ","
            trimmed = trimmed[:-1].rstrip()
        if len(trimmed) < 2 or not trimmed.startswith('"') or not trimmed.endswith('"'):
            repaired_lines.append(line)
            continue
        inner = trimmed[1:-1]
        escaped_inner = []
        previous = ""
        inner_changed = False
        for char in inner:
            if char == '"' and previous != "\\":
                escaped_inner.append('\\"')
                inner_changed = True
            else:
                escaped_inner.append(char)
            previous = char
        if inner_changed:
            changed = True
            new_value = '"' + "".join(escaped_inner) + '"' + trailing
            repaired_lines.append(
                line[: colon + 1] + leading_ws + new_value + trailing_ws
            )
        else:
            repaired_lines.append(line)
    return "\n".join(repaired_lines), changed


def normalize_book_key(book: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", book.lower())


def book_ref_code(book: str) -> str:
    key = normalize_book_key(book)
    return BOOK_REF_CODES.get(key, book[:3].title())


# STEP Bible abbreviations used in the Hebrew OT lexical database (TAHOT)
# These differ from BOOK_REF_CODES for many books.
HEBREW_OT_BOOK_CODES = {
    "genesis": "Gen",
    "exodus": "Exo",
    "leviticus": "Lev",
    "numbers": "Num",
    "deuteronomy": "Deu",
    "joshua": "Jos",
    "judges": "Jdg",
    "ruth": "Rut",
    "1samuel": "1Sa",
    "2samuel": "2Sa",
    "1kings": "1Ki",
    "2kings": "2Ki",
    "1chronicles": "1Ch",
    "2chronicles": "2Ch",
    "ezra": "Ezr",
    "nehemiah": "Neh",
    "esther": "Est",
    "job": "Job",
    "psalms": "Psa",
    "psalm": "Psa",
    "proverbs": "Pro",
    "ecclesiastes": "Ecc",
    "songofsongs": "Sng",
    "songofsolomon": "Sng",
    "isaiah": "Isa",
    "jeremiah": "Jer",
    "lamentations": "Lam",
    "ezekiel": "Ezk",
    "daniel": "Dan",
    "hosea": "Hos",
    "joel": "Jol",
    "amos": "Amo",
    "obadiah": "Oba",
    "jonah": "Jon",
    "micah": "Mic",
    "nahum": "Nam",
    "habakkuk": "Hab",
    "zephaniah": "Zep",
    "haggai": "Hag",
    "zechariah": "Zec",
    "malachi": "Mal",
}

# LXX (Rahlfs 1935) book abbreviations stored in the lexical database
LXX_BOOK_CODES = {
    "genesis": "Gen",
    "exodus": "Exo",
    "leviticus": "Lev",
    "numbers": "Num",
    "deuteronomy": "Deu",
    "joshua": "Josh",
    "judges": "Judg",
    "ruth": "Ruth",
    "1samuel": "1Sam",
    "2samuel": "2Sam",
    "1kings": "1Kgs",
    "2kings": "2Kgs",
    "1chronicles": "1Chr",
    "2chronicles": "2Chr",
    "ezra": "Ezr",
    "nehemiah": "Neh",
    "esther": "Est",
    "job": "Job",
    "psalms": "Psa",
    "psalm": "Psa",
    "proverbs": "Pro",
    "ecclesiastes": "Ecc",
    "songofsongs": "Sng",
    "songofsolomon": "Sng",
    "isaiah": "Isa",
    "jeremiah": "Jer",
    "lamentations": "Lam",
    "ezekiel": "Ezk",
    "daniel": "Dan",
    "hosea": "Hos",
    "joel": "Joel",
    "amos": "Amos",
    "obadiah": "Obad",
    "jonah": "Jonah",
    "micah": "Mic",
    "nahum": "Nah",
    "habakkuk": "Hab",
    "zephaniah": "Zeph",
    "haggai": "Hag",
    "zechariah": "Zech",
    "malachi": "Mal",
}

# Corpus → book code mapping
_CORPUS_BOOK_CODES = {
    "hebrew_ot": HEBREW_OT_BOOK_CODES,
    "greek_ot_lxx": LXX_BOOK_CODES,
    "greek_nt": BOOK_REF_CODES,  # NT uses standard codes (Mat, Mk, Luk, etc.)
}


def lexical_book_code(book: str, corpus: str) -> str:
    """Return the book code used in the lexical DB for a given corpus."""
    mapping = _CORPUS_BOOK_CODES.get(corpus, BOOK_REF_CODES)
    key = normalize_book_key(book)
    return mapping.get(key, book[:3].title())


def reference_key(book: str, chapter: int, start_verse: int, end_verse: int) -> str:
    return f"{normalize_book_key(book)}:{chapter}:{start_verse}-{end_verse}"


def parse_range(token: str) -> tuple[int, int]:
    cleaned = token.strip()
    if not cleaned:
        raise ValueError("Missing verse or range. Use 5 or 5-12.")
    if re.fullmatch(r"\d+", cleaned):
        verse = int(cleaned)
        return verse, verse
    match = re.fullmatch(r"(\d+)-(\d+)", cleaned)
    if not match:
        raise ValueError("Invalid verse/range. Use 5 or 5-12.")
    start_verse = int(match.group(1))
    end_verse = int(match.group(2))
    if start_verse > end_verse:
        raise ValueError(
            "Invalid verse/range. Start verse cannot be greater than end verse."
        )
    return start_verse, end_verse


def parse_reference(parts: list[str]) -> tuple[str, int, int, int]:
    if not parts:
        raise ValueError("Missing reference. Use /open Matthew 1:1-17")
    if len(parts) == 1 and parts[0].count(":") >= 2:
        book, chapter, verse_range = parts[0].split(":", 2)
        start, end = parse_range(verse_range)
        return book.strip(), int(chapter), start, end
    if len(parts) >= 2 and ":" in parts[-1]:
        book = " ".join(parts[:-1]).strip()
        chapter, verse_range = parts[-1].split(":", 1)
        start, end = parse_range(verse_range)
        return book, int(chapter), start, end
    raise ValueError("Invalid reference. Use /open Matthew 1:1-17")


def make_text_hash(
    book: str, chapter: int, verses: Iterable[int], verse_map: dict[int, str]
) -> str:
    chunks = [f"{book}|{chapter}"]
    for verse in sorted(set(int(v) for v in verses)):
        chunks.append(f"{verse}:{verse_map.get(verse, '')}")
    digest = hashlib.sha1("||".join(chunks).encode("utf-8")).hexdigest()
    return f"sha1:{digest}"


def book_abbrev(book: str) -> str:
    letters = re.sub(r"[^A-Za-z0-9]+", "", book.upper())
    return (letters[:3] or "BOK").ljust(3, "X")


def find_close_command(command: str, choices: list[str]) -> list[str]:
    return difflib.get_close_matches(command, choices, n=3, cutoff=0.45)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
