from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR = DATA_DIR / "lexical_sources"
BUILD_DIR = DATA_DIR / "lexical_index"
LOG_PREFIX = "[prepare-lexical-data]"


@dataclass(frozen=True)
class SourceSpec:
    corpus: str
    family: str
    name: str
    relative_path: str
    url: str
    kind: str
    format: str
    license: str
    notes: str = ""


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        corpus="greek_nt",
        family="step",
        name="TBESG",
        relative_path="step/lexicons/tbesg.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Lexicons/TBESG%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Greek%20-%20STEPBible.org%20CC%20BY.txt",
        kind="lexicon",
        format="tsv",
        license="CC BY 4.0",
        notes="Brief Greek lexicon covering NT, LXX, Apocrypha, and variants.",
    ),
    SourceSpec(
        corpus="hebrew_ot",
        family="step",
        name="TBESH",
        relative_path="step/lexicons/tbesh.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Lexicons/TBESH%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Hebrew%20-%20STEPBible.org%20CC%20BY.txt",
        kind="lexicon",
        format="tsv",
        license="CC BY 4.0",
        notes="Brief Hebrew lexicon keyed by Extended Strongs.",
    ),
    SourceSpec(
        corpus="greek_nt",
        family="step",
        name="TAGNT Mat-Jhn",
        relative_path="step/tagged/tagnt_mat_jhn.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Translators%20Amalgamated%20OT%2BNT/TAGNT%20Mat-Jhn%20-%20Translators%20Amalgamated%20Greek%20NT%20-%20STEPBible.org%20CC-BY.txt",
        kind="tagged_text",
        format="tsv",
        license="CC BY 4.0",
    ),
    SourceSpec(
        corpus="greek_nt",
        family="step",
        name="TAGNT Act-Rev",
        relative_path="step/tagged/tagnt_act_rev.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Translators%20Amalgamated%20OT%2BNT/TAGNT%20Act-Rev%20-%20Translators%20Amalgamated%20Greek%20NT%20-%20STEPBible.org%20CC-BY.txt",
        kind="tagged_text",
        format="tsv",
        license="CC BY 4.0",
    ),
    SourceSpec(
        corpus="hebrew_ot",
        family="step",
        name="TAHOT Gen-Deu",
        relative_path="step/tagged/tahot_gen_deu.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Translators%20Amalgamated%20OT%2BNT/TAHOT%20Gen-Deu%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
        kind="tagged_text",
        format="tsv",
        license="CC BY 4.0",
    ),
    SourceSpec(
        corpus="hebrew_ot",
        family="step",
        name="TAHOT Jos-Est",
        relative_path="step/tagged/tahot_jos_est.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Translators%20Amalgamated%20OT%2BNT/TAHOT%20Jos-Est%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
        kind="tagged_text",
        format="tsv",
        license="CC BY 4.0",
    ),
    SourceSpec(
        corpus="hebrew_ot",
        family="step",
        name="TAHOT Job-Sng",
        relative_path="step/tagged/tahot_job_sng.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Translators%20Amalgamated%20OT%2BNT/TAHOT%20Job-Sng%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
        kind="tagged_text",
        format="tsv",
        license="CC BY 4.0",
    ),
    SourceSpec(
        corpus="hebrew_ot",
        family="step",
        name="TAHOT Isa-Mal",
        relative_path="step/tagged/tahot_isa_mal.txt",
        url="https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Translators%20Amalgamated%20OT%2BNT/TAHOT%20Isa-Mal%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
        kind="tagged_text",
        format="tsv",
        license="CC BY 4.0",
    ),
    SourceSpec(
        corpus="greek_ot_lxx",
        family="lxx_rahlfs_1935",
        name="LXX text accented",
        relative_path="lxx_rahlfs_1935/12_marvel_bible/01_text_accented.csv.zip",
        url="https://raw.githubusercontent.com/eliranwong/LXX-Rahlfs-1935/master/12-Marvel.Bible/01-text_accented.csv.zip",
        kind="tagged_text",
        format="zip_csv",
        license="Repository license on GitHub",
        notes="Marvel.Bible export with token ids, lex ids, and morphology.",
    ),
    SourceSpec(
        corpus="greek_ot_lxx",
        family="lxx_rahlfs_1935",
        name="LXX gloss",
        relative_path="lxx_rahlfs_1935/12_marvel_bible/06_gloss.csv",
        url="https://raw.githubusercontent.com/eliranwong/LXX-Rahlfs-1935/master/12-Marvel.Bible/06-gloss.csv",
        kind="token_map",
        format="csv",
        license="Repository license on GitHub",
    ),
    SourceSpec(
        corpus="greek_ot_lxx",
        family="lxx_rahlfs_1935",
        name="LXX lexemes",
        relative_path="lxx_rahlfs_1935/12_marvel_bible/09_lexemes.csv",
        url="https://raw.githubusercontent.com/eliranwong/LXX-Rahlfs-1935/master/12-Marvel.Bible/09-lexemes.csv",
        kind="token_map",
        format="csv",
        license="Repository license on GitHub",
    ),
    SourceSpec(
        corpus="greek_ot_lxx",
        family="lxx_rahlfs_1935",
        name="LXX Strongs",
        relative_path="lxx_rahlfs_1935/07_strong_number/final_strongs.csv",
        url="https://raw.githubusercontent.com/eliranwong/LXX-Rahlfs-1935/master/07_StrongNumber/final_Strongs.csv",
        kind="token_map",
        format="csv",
        license="Repository license on GitHub",
    ),
    SourceSpec(
        corpus="greek_ot_lxx",
        family="lxx_rahlfs_1935",
        name="LXX versification",
        relative_path="lxx_rahlfs_1935/12_marvel_bible/00_versification_original.csv",
        url="https://raw.githubusercontent.com/eliranwong/LXX-Rahlfs-1935/master/12-Marvel.Bible/00-versification_original.csv",
        kind="versification",
        format="csv",
        license="Repository license on GitHub",
    ),
    SourceSpec(
        corpus="greek_ot_lxx",
        family="lxx_rahlfs_1935",
        name="LXX book maps",
        relative_path="lxx_rahlfs_1935/08_versification/book_maps.csv",
        url="https://raw.githubusercontent.com/eliranwong/LXX-Rahlfs-1935/master/08_versification/book_maps.csv",
        kind="metadata",
        format="csv",
        license="Repository license on GitHub",
    ),
)


STEP_REF_RE = re.compile(r"^(?P<ref>[A-Za-z0-9]{3,}\.\d+\.\d+)#(?P<ord>\d+)(?:=(?P<variant>.*))?$")
SURFACE_TRANSLIT_RE = re.compile(r"^(?P<surface>.*?)\s*\((?P<translit>[^()]*)\)\s*$")
LXX_TEXT_RE = re.compile(r"<grk id=\"(?P<id>[^\"]+)\" lex=\"(?P<lex>[^\"]+)\" morph=\"(?P<morph>[^\"]+)\">(?P<surface>.*?)</grk>")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    print(f"{LOG_PREFIX} {message}", flush=True)


def download_sources(force: bool = False) -> list[dict[str, str]]:
    ensure_dirs()
    manifest_rows: list[dict[str, str]] = []
    for spec in SOURCES:
        target = RAW_DIR / spec.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            data = target.read_bytes()
            status = "cached"
        else:
            log(f"downloading {spec.name}")
            with urllib.request.urlopen(spec.url, timeout=120) as response:
                data = response.read()
            target.write_bytes(data)
            status = "downloaded"
        manifest_rows.append(
            {
                "corpus": spec.corpus,
                "family": spec.family,
                "name": spec.name,
                "kind": spec.kind,
                "format": spec.format,
                "license": spec.license,
                "notes": spec.notes,
                "path": str(target.relative_to(DATA_DIR)),
                "url": spec.url,
                "sha256": sha256_bytes(data),
                "status": status,
                "downloaded_at": now_iso(),
            }
        )
    manifest_path = BUILD_DIR / "sources_manifest.json"
    manifest_path.write_text(json.dumps(manifest_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_rows


def connect_db() -> sqlite3.Connection:
    db_path = BUILD_DIR / "lexical.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE sources (
            corpus TEXT,
            family TEXT,
            name TEXT,
            kind TEXT,
            format TEXT,
            license TEXT,
            notes TEXT,
            path TEXT,
            url TEXT,
            sha256 TEXT,
            downloaded_at TEXT
        );
        CREATE TABLE lexicon_entries (
            corpus TEXT,
            strong_id TEXT,
            dstrong_id TEXT,
            ustrong_id TEXT,
            lemma TEXT,
            transliteration TEXT,
            morph TEXT,
            gloss TEXT,
            definition TEXT,
            source_name TEXT
        );
        CREATE INDEX idx_lexicon_entries_strong ON lexicon_entries (corpus, strong_id);
        CREATE TABLE tagged_tokens (
            corpus TEXT,
            ref TEXT,
            ordinal INTEGER,
            token_id TEXT,
            surface TEXT,
            transliteration TEXT,
            english TEXT,
            strong_id TEXT,
            morph TEXT,
            lemma TEXT,
            gloss TEXT,
            lexical_id TEXT,
            source_name TEXT,
            raw_line TEXT
        );
        CREATE INDEX idx_tagged_tokens_ref ON tagged_tokens (corpus, ref, ordinal);
        CREATE INDEX idx_tagged_tokens_strong ON tagged_tokens (corpus, strong_id);
        """
    )
    return conn


def iter_non_comment_lines(path: Path) -> Iterable[str]:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        if line.startswith("!"):
            continue
        yield line


def parse_step_lexicon(path: Path, corpus: str, source_name: str, conn: sqlite3.Connection) -> int:
    header: list[str] | None = None
    count = 0
    for line in iter_non_comment_lines(path):
        columns = line.split("\t")
        if header is None:
            if columns[:4] == ["eStrong", "dStrong", "uStrong", "Greek"] or columns[:4] == ["eStrong#", "dStrong", "uStrong", "Hebrew"]:
                header = columns
            continue
        if len(columns) < len(header):
            columns.extend([""] * (len(header) - len(columns)))
        row = dict(zip(header, columns))
        strong_id = row.get("eStrong") or row.get("eStrong#")
        if not strong_id:
            continue
        conn.execute(
            """
            INSERT INTO lexicon_entries (
                corpus, strong_id, dstrong_id, ustrong_id, lemma, transliteration, morph, gloss, definition, source_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                corpus,
                strong_id.strip(),
                (row.get("dStrong") or "").strip(),
                (row.get("uStrong") or "").strip(),
                (row.get("Greek") or row.get("Hebrew") or "").strip(),
                (row.get("Transliteration") or "").strip(),
                (row.get("Morph") or "").strip(),
                (row.get("Gloss") or "").strip(),
                (row.get("Abbott-Smith lexicon (AS), with gaps occationally filled from edited versions of  Middle LSJ ") or row.get("Meaning") or "").strip(),
                source_name,
            ),
        )
        count += 1
    return count


def split_surface_and_translit(value: str) -> tuple[str, str]:
    match = SURFACE_TRANSLIT_RE.match(value.strip())
    if not match:
        return value.strip(), ""
    return match.group("surface").strip(), match.group("translit").strip()


def parse_step_tagged(path: Path, corpus: str, source_name: str, conn: sqlite3.Connection) -> int:
    count = 0
    for line in iter_non_comment_lines(path):
        columns = line.split("\t")
        if len(columns) < 5:
            continue
        match = STEP_REF_RE.match(columns[0].strip())
        if not match:
            continue
        ref = match.group("ref")
        ordinal = int(match.group("ord"))
        surface, transliteration = split_surface_and_translit(columns[1])
        english = columns[2].strip() if len(columns) > 2 else ""
        strong_id = ""
        morph = ""
        lemma = ""
        gloss = ""
        if corpus == "hebrew_ot":
            strong_id = (columns[8].strip() if len(columns) > 8 else "") or (columns[4].strip() if len(columns) > 4 else "")
            morph = columns[5].strip() if len(columns) > 5 else ""
            lexical = columns[11].strip() if len(columns) > 11 else ""
            inner_matches = re.findall(r"\{([^=]+)=([^=]+)=:([^}]+)\}", lexical)
            if inner_matches:
                strong_id, lemma, gloss = inner_matches[-1]
                gloss = gloss.split("»", 1)[0].strip()
            elif "=" in lexical:
                left, right = lexical.split("=", 1)
                strong_id = strong_id or left.strip()
                lemma = right.strip()
        else:
            if "=" in columns[3]:
                strong_id, morph = columns[3].split("=", 1)
            if "=" in columns[4]:
                lemma, gloss = columns[4].split("=", 1)
        conn.execute(
            """
            INSERT INTO tagged_tokens (
                corpus, ref, ordinal, token_id, surface, transliteration, english, strong_id, morph, lemma, gloss, lexical_id, source_name, raw_line
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                corpus,
                ref,
                ordinal,
                f"{ref}#{ordinal:02d}",
                surface,
                transliteration,
                english,
                strong_id.strip(),
                morph.strip(),
                lemma.strip(),
                gloss.strip(),
                "",
                source_name,
                line,
            ),
        )
        count += 1
    return count


def read_simple_id_map(path: Path) -> dict[int, str]:
    mapping: dict[int, str] = {}
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if len(row) < 2 or not row[0].strip().isdigit():
                continue
            mapping[int(row[0])] = row[1].strip()
    return mapping


def parse_book_maps(path: Path) -> dict[int, str]:
    mapping: dict[int, str] = {}
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if len(row) < 3:
                continue
            canon = row[2].strip()
            if canon.isdigit():
                mapping[int(canon)] = row[1].strip()
    return mapping


def parse_lxx_versification(path: Path, book_map: dict[int, str]) -> list[tuple[int, str]]:
    starts: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if len(row) < 2 or not row[0].strip().isdigit():
                continue
            token_start = int(row[0].strip())
            raw_ref = row[1].strip().lstrip("\ufeff")
            raw_ref = raw_ref.lstrip("†‡")
            parts = raw_ref.split(".")
            if len(parts) != 3:
                continue
            book_num, chapter, verse = parts
            if not book_num.isdigit():
                continue
            book_name = book_map.get(int(book_num), f"Book{book_num}")
            chapter_label = str(int(chapter)) if chapter.isdigit() else chapter
            starts.append((token_start, f"{book_name}.{chapter_label}.{verse}"))
    starts.sort(key=lambda item: item[0])
    return starts


def iter_lxx_text_rows(path: Path) -> Iterable[tuple[int, str, str, str]]:
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".csv") and not name.startswith("__MACOSX/"))
        with archive.open(member) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            reader = csv.reader(text, delimiter="\t")
            for row in reader:
                if len(row) < 2 or not row[0].strip().isdigit():
                    continue
                token_id = int(row[0].strip())
                match = LXX_TEXT_RE.search(row[1])
                if not match:
                    continue
                yield token_id, match.group("surface").strip(), match.group("lex").strip(), match.group("morph").strip()


def verse_for_token(token_id: int, starts: list[tuple[int, str]]) -> str:
    current = starts[0][1]
    for start, ref in starts:
        if token_id < start:
            break
        current = ref
    return current


def parse_lxx_tokens(raw_root: Path, conn: sqlite3.Connection) -> int:
    book_map = parse_book_maps(raw_root / "lxx_rahlfs_1935" / "08_versification" / "book_maps.csv")
    starts = parse_lxx_versification(raw_root / "lxx_rahlfs_1935" / "12_marvel_bible" / "00_versification_original.csv", book_map)
    glosses = read_simple_id_map(raw_root / "lxx_rahlfs_1935" / "12_marvel_bible" / "06_gloss.csv")
    lexemes = read_simple_id_map(raw_root / "lxx_rahlfs_1935" / "12_marvel_bible" / "09_lexemes.csv")
    strongs = read_simple_id_map(raw_root / "lxx_rahlfs_1935" / "07_strong_number" / "final_strongs.csv")
    count = 0
    ordinal_cache: dict[str, int] = {}
    for token_id, surface, lexical_id, morph in iter_lxx_text_rows(raw_root / "lxx_rahlfs_1935" / "12_marvel_bible" / "01_text_accented.csv.zip"):
        ref = verse_for_token(token_id, starts)
        ordinal_cache[ref] = ordinal_cache.get(ref, 0) + 1
        conn.execute(
            """
            INSERT INTO tagged_tokens (
                corpus, ref, ordinal, token_id, surface, transliteration, english, strong_id, morph, lemma, gloss, lexical_id, source_name, raw_line
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "greek_ot_lxx",
                ref,
                ordinal_cache[ref],
                str(token_id),
                surface,
                "",
                "",
                strongs.get(token_id, ""),
                morph,
                lexemes.get(token_id, ""),
                glosses.get(token_id, ""),
                lexical_id,
                "LXX-Rahlfs-1935 Marvel.Bible",
                "",
            ),
        )
        count += 1
    return count


def write_summary(conn: sqlite3.Connection, manifest_rows: list[dict[str, str]]) -> None:
    for row in manifest_rows:
        conn.execute(
            """
            INSERT INTO sources (
                corpus, family, name, kind, format, license, notes, path, url, sha256, downloaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["corpus"],
                row["family"],
                row["name"],
                row["kind"],
                row["format"],
                row["license"],
                row["notes"],
                row["path"],
                row["url"],
                row["sha256"],
                row["downloaded_at"],
            ),
        )
    conn.commit()
    summary = {
        "built_at": now_iso(),
        "database": "lexical.db",
        "sources": len(manifest_rows),
        "lexicon_entries": conn.execute("SELECT COUNT(*) FROM lexicon_entries").fetchone()[0],
        "tagged_tokens": conn.execute("SELECT COUNT(*) FROM tagged_tokens").fetchone()[0],
        "corpora": {
            row[0]: row[1]
            for row in conn.execute("SELECT corpus, COUNT(*) FROM tagged_tokens GROUP BY corpus ORDER BY corpus")
        },
    }
    (BUILD_DIR / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_indexes(manifest_rows: list[dict[str, str]]) -> None:
    log("building sqlite index")
    conn = connect_db()
    raw_root = RAW_DIR
    try:
        log("indexing STEPBible Greek lexicon")
        greek_lex_count = parse_step_lexicon(raw_root / "step" / "lexicons" / "tbesg.txt", "greek_bible", "TBESG", conn)
        log("indexing STEPBible Hebrew lexicon")
        hebrew_lex_count = parse_step_lexicon(raw_root / "step" / "lexicons" / "tbesh.txt", "hebrew_bible", "TBESH", conn)
        nt_count = 0
        log("indexing STEPBible Greek NT tokens")
        for name in ["tagnt_mat_jhn.txt", "tagnt_act_rev.txt"]:
            nt_count += parse_step_tagged(raw_root / "step" / "tagged" / name, "greek_nt", name, conn)
        hot_count = 0
        log("indexing STEPBible Hebrew OT tokens")
        for name in ["tahot_gen_deu.txt", "tahot_jos_est.txt", "tahot_job_sng.txt", "tahot_isa_mal.txt"]:
            hot_count += parse_step_tagged(raw_root / "step" / "tagged" / name, "hebrew_ot", name, conn)
        log("indexing LXX Greek OT tokens")
        lxx_count = parse_lxx_tokens(raw_root, conn)
        write_summary(conn, manifest_rows)
    finally:
        conn.close()
    log(f"indexed lexicon entries: greek={greek_lex_count} hebrew={hebrew_lex_count}")
    log(f"indexed tagged tokens: nt={nt_count} hebrew_ot={hot_count} lxx={lxx_count}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and build offline lexical datasets for the TTT workbench.")
    parser.add_argument("--force-download", action="store_true", help="Redownload source files even if they are already cached.")
    parser.add_argument("--download-only", action="store_true", help="Only download raw sources; skip SQLite/index building.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    ensure_dirs()
    manifest_rows = download_sources(force=args.force_download)
    if args.download_only:
        log("download-only complete")
        return 0
    build_indexes(manifest_rows)
    log(f"ready: {BUILD_DIR / 'lexical.db'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
