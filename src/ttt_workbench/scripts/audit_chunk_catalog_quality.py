#!/usr/bin/env python3
"""Audit generated chapter chunk catalogs without rewriting source data."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ttt_core.config import load_config
from ttt_core.utils import normalize_book_key, utc_now


GENERIC_TITLES = {
    "account",
    "beginning",
    "conclusion",
    "context",
    "events",
    "history",
    "instructions",
    "introduction",
    "judgment",
    "law",
    "narrative",
    "oracle",
    "prophecy",
    "summary",
    "teaching",
    "warning",
}

VERSE_REF_RE = re.compile(r"\bverses?\s+(\d+)(?:\s*[-–]\s*(\d+))?", re.IGNORECASE)


@dataclass
class ChapterAudit:
    path: str
    testament: str
    book: str
    chapter: int
    verse_start: int
    verse_end: int
    chunk_count: int
    issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "needs_review" if self.issues else "safe"

    def add_issue(self, severity: str, kind: str, message: str, chunk_index: int | None = None) -> None:
        issue: dict[str, Any] = {"severity": severity, "kind": kind, "message": message}
        if chunk_index is not None:
            issue["chunk_index"] = chunk_index
        self.issues.append(issue)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    cfg = load_config()
    default_source = Path(cfg["paths"]["final_data"]) / "chapter_chunk_catalog" / "chunks"
    default_report = Path(cfg["paths"]["final_data"]) / "chapter_chunk_catalog" / "quality_audit_report.json"
    parser = argparse.ArgumentParser(description="Audit generated chapter chunk boundary and label quality.")
    parser.add_argument("--source-dir", default=str(default_source), help="Per-chapter chunk catalog directory.")
    parser.add_argument("--report-path", default=str(default_report), help="JSON report path to write.")
    parser.add_argument("--only-book", help="Optional book filter.")
    parser.add_argument("--max-chapters", type=int, default=0, help="Optional limit for quick review batches.")
    return parser.parse_args(argv)


def iter_chapter_files(source_dir: Path, only_book: str | None = None) -> list[Path]:
    files = sorted(source_dir.glob("*/*/*_chunks.json"))
    if only_book:
        book_key = normalize_book_key(only_book)
        files = [path for path in files if path.parent.name == book_key]
    return files


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def chunk_title_is_weak(title: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", title.lower()).strip()
    words = [word for word in normalized.split() if word]
    if not words:
        return True
    if len(words) <= 2 and any(word in GENERIC_TITLES for word in words):
        return True
    return normalized.startswith(("introduction", "conclusion", "summary", "historical context"))


def audit_chapter(path: Path) -> ChapterAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chunks = payload.get("chunks") or []
    verse_start = as_int(payload.get("verse_start"), as_int(chunks[0].get("start_verse"), 1) if chunks else 1)
    verse_end = as_int(payload.get("verse_end"), as_int(chunks[-1].get("end_verse"), verse_start) if chunks else verse_start)
    audit = ChapterAudit(
        path=display_path(path),
        testament=str(payload.get("testament") or path.parents[1].name),
        book=str(payload.get("book") or path.parent.name),
        chapter=as_int(payload.get("chapter")),
        verse_start=verse_start,
        verse_end=verse_end,
        chunk_count=len(chunks),
    )

    if not chunks:
        audit.add_issue("high", "empty", "Chapter has no chunk entries.")
        return audit

    expected_start = verse_start
    covered: set[int] = set()
    for index, chunk in enumerate(chunks, start=1):
        start = as_int(chunk.get("start_verse"))
        end = as_int(chunk.get("end_verse"))
        title = str(chunk.get("title") or "").strip()
        chunk_type = str(chunk.get("type") or "").strip()
        reason = str(chunk.get("reason") or "").strip()

        if start != expected_start:
            audit.add_issue("high", "boundary_gap", f"Expected chunk to start at verse {expected_start}, found {start}.", index)
        if end < start:
            audit.add_issue("high", "boundary_order", f"Chunk ends before it starts ({start}-{end}).", index)
        if start < verse_start or end > verse_end:
            audit.add_issue("high", "boundary_range", f"Chunk {start}-{end} falls outside chapter range {verse_start}-{verse_end}.", index)
        for verse in range(max(start, verse_start), min(end, verse_end) + 1):
            if verse in covered:
                audit.add_issue("high", "boundary_overlap", f"Verse {verse} is covered more than once.", index)
            covered.add(verse)
        expected_start = end + 1

        if not chunk_type:
            audit.add_issue("medium", "missing_type", "Chunk type is blank.", index)
        if chunk_title_is_weak(title):
            audit.add_issue("medium", "weak_title", f"Chunk title looks generic or blank: {title!r}.", index)
        if len(reason) < 20:
            audit.add_issue("low", "weak_reason", "Chunk reason is too short to explain the boundary.", index)
        for match in VERSE_REF_RE.finditer(reason):
            ref_start = as_int(match.group(1))
            ref_end = as_int(match.group(2), ref_start)
            if ref_start < start or ref_end > end:
                audit.add_issue(
                    "medium",
                    "reason_range",
                    f"Reason references verses {ref_start}-{ref_end} outside chunk range {start}-{end}.",
                    index,
                )

    missing = [verse for verse in range(verse_start, verse_end + 1) if verse not in covered]
    if missing:
        audit.add_issue("high", "coverage_missing", f"Missing verse coverage: {missing[:12]}.")

    tail = chunks[-1]
    tail_start = as_int(tail.get("start_verse"))
    tail_end = as_int(tail.get("end_verse"))
    if tail_start == tail_end and len(chunks) > 1:
        previous = chunks[-2]
        previous_len = as_int(previous.get("end_verse")) - as_int(previous.get("start_verse")) + 1
        if previous_len >= 4:
            audit.add_issue("medium", "one_verse_tail", f"Final one-verse chunk follows a {previous_len}-verse chunk.", len(chunks))

    verse_count = max(0, verse_end - verse_start + 1)
    if verse_count and len(chunks) > max(8, verse_count // 2 + 1):
        audit.add_issue("low", "chunk_count_outlier", f"{len(chunks)} chunks for {verse_count} verses looks unusually granular.")
    if verse_count >= 30 and len(chunks) <= 1:
        audit.add_issue("low", "chunk_count_outlier", f"One chunk for {verse_count} verses may be too broad.")

    return audit


def build_report(source_dir: Path, only_book: str | None = None, max_chapters: int = 0) -> dict[str, Any]:
    files = iter_chapter_files(source_dir, only_book)
    if max_chapters > 0:
        files = files[:max_chapters]
    audits = [audit_chapter(path) for path in files]
    needs_review = [audit for audit in audits if audit.issues]
    safe = [audit for audit in audits if not audit.issues]
    return {
        "generated_at": utc_now(),
        "source_dir": display_path(source_dir),
        "summary": {
            "chapters_scanned": len(audits),
            "chapters_safe": len(safe),
            "chapters_needing_review": len(needs_review),
        },
        "needs_review": [audit.__dict__ | {"status": audit.status} for audit in needs_review],
        "safe_chapters": [
            {
                "path": audit.path,
                "testament": audit.testament,
                "book": audit.book,
                "chapter": audit.chapter,
                "chunk_count": audit.chunk_count,
                "status": audit.status,
            }
            for audit in safe
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_dir = Path(args.source_dir)
    report = build_report(source_dir, only_book=args.only_book, max_chapters=args.max_chapters)
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "Scanned {chapters_scanned} chapter(s); {chapters_needing_review} need review; "
        "{chapters_safe} are safe.".format(**report["summary"])
    )
    print(f"Wrote {report_path}")
    return 1 if report["summary"]["chapters_needing_review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
