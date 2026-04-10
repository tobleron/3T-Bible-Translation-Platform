#!/usr/bin/env python3
"""Batch-generate chapter chunk suggestions with titles for the whole Bible.

This script reuses the existing lexical study context and chunking prompts used
by the TTT workbench, but runs chapter-by-chapter in batch mode with:

- resumable output files
- prompt/response audit files
- strict JSON validation
- light JSON repair attempts
- stop-on-error behavior for unreliable model output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ttt_core.data.repositories import (
    BibleRepository,
    LexicalRepository,
    ProjectPaths,
    SourceRepository,
)
from ttt_core.llm import LlamaCppClient
from ttt_core.utils import (
    ensure_parent,
    extract_json_payload,
    normalize_book_key,
    repair_linewise_json_strings,
    utc_now,
)


ALLOWED_TYPES = {
    "story",
    "speech",
    "dialogue",
    "parable",
    "genealogy",
    "law",
    "oracle",
    "psalm",
    "vision",
    "argument",
    "exhortation",
    "blessing_or_prayer",
    "list_or_catalog",
    "mixed",
}


def strip_think_blocks(text: str) -> str:
    """Remove visible reasoning blocks from raw model output before JSON parsing."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


@dataclass
class ChapterTarget:
    testament: str
    book: str
    chapter: int
    verses: list[int]


class ChapterChunkBatch:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = Path(__file__).resolve().parents[2]
        self.workspace_dir = self.repo_root / "02_Human_Editorial_Workspace"
        self.paths = ProjectPaths(workspace_dir=self.workspace_dir, repo_root=self.repo_root)
        self.source_repo = SourceRepository(self.paths)
        self.lexical_repo = LexicalRepository(self.paths)
        self.bible_repo = BibleRepository(
            self.paths,
            source_repository=self.source_repo,
            lexical_repository=self.lexical_repo,
        )
        self.llm = LlamaCppClient(base_url=args.base_url)
        self.schema_prompt = (
            self.paths.chunking_prompts_dir / "chunk_schema.txt"
        ).read_text(encoding="utf-8")
        self.prompt_version = "chapter_chunk_batch_v1"
        self.output_dir = Path(args.output_dir).resolve()
        self.chunks_dir = self.output_dir / "chunks"
        self.raw_dir = self.output_dir / "raw"
        self.logs_dir = self.output_dir / "logs"
        self.manifest_path = self.output_dir / "manifest.json"
        self.log_path = self.logs_dir / "latest.log"
        ensure_parent(self.log_path)
        self.run_started_at = utc_now()
        self.model_name = self.llm.list_models()[0]
        self.manifest = self._load_manifest()
        self.consecutive_failures = 0

    def _load_manifest(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "prompt_version": self.prompt_version,
            "base_url": self.args.base_url,
            "model_name": self.model_name,
            "chapters": {},
        }

    def save_manifest(self) -> None:
        self.manifest["updated_at"] = utc_now()
        ensure_parent(self.manifest_path)
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def log(self, message: str) -> None:
        line = f"[{utc_now()}] {message}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def chapter_key(self, book: str, chapter: int) -> str:
        return f"{normalize_book_key(book)}:{chapter}"

    def chapter_output_path(self, testament: str, book: str, chapter: int) -> Path:
        safe_book = normalize_book_key(book) or "book"
        return self.chunks_dir / testament / safe_book / f"{safe_book}_{chapter:03d}_chunks.json"

    def chapter_prompt_path(self, testament: str, book: str, chapter: int) -> Path:
        safe_book = normalize_book_key(book) or "book"
        return self.raw_dir / testament / safe_book / f"{safe_book}_{chapter:03d}_prompt.txt"

    def chapter_response_path(self, testament: str, book: str, chapter: int) -> Path:
        safe_book = normalize_book_key(book) or "book"
        return self.raw_dir / testament / safe_book / f"{safe_book}_{chapter:03d}_response.txt"

    def chapter_repaired_response_path(self, testament: str, book: str, chapter: int) -> Path:
        safe_book = normalize_book_key(book) or "book"
        return self.raw_dir / testament / safe_book / f"{safe_book}_{chapter:03d}_response_repaired.json"

    def current_targets(self) -> list[ChapterTarget]:
        requested_books = self._requested_books()
        targets: list[ChapterTarget] = []
        for testament in self._requested_testaments():
            for book in self.bible_repo.canonical_books(testament):
                if requested_books and normalize_book_key(book) not in requested_books:
                    continue
                chapters = self.source_repo.chapters_for_book(book)
                if not chapters:
                    continue
                for chapter in chapters:
                    if requested_books and len(requested_books) == 1:
                        if self.args.start_chapter and chapter < self.args.start_chapter:
                            continue
                        if self.args.end_chapter and chapter > self.args.end_chapter:
                            continue
                    verses = self.source_repo.chapter_verse_numbers(book, chapter)
                    if not verses:
                        continue
                    targets.append(
                        ChapterTarget(
                            testament=testament,
                            book=book,
                            chapter=chapter,
                            verses=verses,
                        )
                    )
        return targets

    def _requested_books(self) -> set[str]:
        if not self.args.book:
            return set()
        return {
            normalize_book_key(piece)
            for piece in self.args.book.split(",")
            if piece.strip()
        }

    def _requested_testaments(self) -> list[str]:
        if self.args.testament == "all":
            return ["old", "new"]
        return [self.args.testament]

    def build_chapter_text_context(
        self, book: str, chapter: int, start_verse: int, end_verse: int
    ) -> str:
        lines: list[str] = []
        for verse in range(start_verse, end_verse + 1):
            text = self.source_repo.verse_text("LSB", book, chapter, verse).strip()
            if not text:
                raise ValueError(f"Missing LSB source text for {book} {chapter}:{verse}")
            lines.append(f"{verse}. {text}")
        return "\n".join(lines)

    def build_prompt(self, target: ChapterTarget) -> str:
        context = self.build_chapter_text_context(
            target.book, target.chapter, target.verses[0], target.verses[-1]
        )
        testament_label = "Old Testament" if target.testament == "old" else "New Testament"
        return f"""Model profile: qwen3.5 35B A3B thinking model.
You are segmenting a {testament_label} chapter into practical translation chunks.

Source text:
- Use only the provided LSB chapter text below.
- Do not rely on memory when verse boundaries or discourse shifts are visible in the provided text.

Goal:
- Suggest chunk ranges that a human translator can work through as coherent units.
- Favor complete story, speech, dialogue, parable, genealogy, law, oracle, psalm, vision, argument, exhortation, prayer, or list units.
- Avoid tiny fragments unless the text naturally breaks there.
- Keep the number of chunks small but practical.
- Titles should be short and plain English.

Chapter to segment: {target.book} {target.chapter}:{target.verses[0]}-{target.verses[-1]}

Chapter text:
{context}

Return strict JSON only with this shape:
{{
  "chunks": [
    {{
      "start_verse": 1,
      "end_verse": 17,
      "type": "genealogy",
      "title": "Genealogy of Jesus",
      "reason": "One concise sentence."
    }}
  ]
}}

Rules:
- Use contiguous, non-overlapping ranges.
- Cover the full chapter from start to end.
- Allowed chunk types only:
  story
  speech
  dialogue
  parable
  genealogy
  law
  oracle
  psalm
  vision
  argument
  exhortation
  blessing_or_prayer
  list_or_catalog
  mixed""".strip()

    def parse_and_repair_json(self, raw_response: str) -> tuple[dict | None, str | None]:
        cleaned = strip_think_blocks(raw_response)
        payload = extract_json_payload(cleaned)
        if isinstance(payload, dict):
            return payload, None

        stripped = cleaned.strip()
        if not stripped:
            return None, None

        opener_positions = [pos for pos in (stripped.find("{"), stripped.find("[")) if pos != -1]
        if not opener_positions:
            return None, None
        start = min(opener_positions)
        end_obj = stripped.rfind("}")
        end_arr = stripped.rfind("]")
        end = max(end_obj, end_arr)
        if end <= start:
            return None, None
        candidate = stripped[start : end + 1]
        repaired, changed = repair_linewise_json_strings(candidate)
        if not changed:
            return None, None
        try:
            payload = json.loads(repaired)
        except json.JSONDecodeError:
            return None, None
        if isinstance(payload, dict):
            return payload, repaired
        return None, None

    def validate_payload(self, payload: dict[str, Any], target: ChapterTarget) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ValueError("Parsed payload is not a JSON object.")
        chunks = payload.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise ValueError("Payload missing non-empty 'chunks' list.")

        expected = list(target.verses)
        cursor = 0
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(chunks, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Chunk {index} is not an object.")
            try:
                start_verse = int(item["start_verse"])
                end_verse = int(item["end_verse"])
            except Exception as exc:
                raise ValueError(f"Chunk {index} is missing integer verse bounds.") from exc
            if start_verse > end_verse:
                raise ValueError(f"Chunk {index} has start_verse > end_verse.")
            chunk_type = str(item.get("type", "")).strip()
            title = str(item.get("title", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if chunk_type not in ALLOWED_TYPES:
                raise ValueError(f"Chunk {index} uses invalid type '{chunk_type}'.")
            if not title:
                raise ValueError(f"Chunk {index} has an empty title.")
            if not reason:
                raise ValueError(f"Chunk {index} has an empty reason.")

            covered = [verse for verse in expected if start_verse <= verse <= end_verse]
            if not covered:
                raise ValueError(f"Chunk {index} does not cover any real verses.")
            if cursor >= len(expected):
                raise ValueError(f"Chunk {index} extends beyond the chapter verse list.")
            expected_slice = expected[cursor : cursor + len(covered)]
            if covered != expected_slice:
                raise ValueError(f"Chunk {index} is not contiguous with the previous chunk.")
            if covered[0] != start_verse or covered[-1] != end_verse:
                raise ValueError(f"Chunk {index} starts or ends on a missing verse number.")

            normalized.append(
                {
                    "start_verse": start_verse,
                    "end_verse": end_verse,
                    "type": chunk_type,
                    "title": title,
                    "reason": reason,
                }
            )
            cursor += len(covered)

        if cursor != len(expected):
            next_verse = expected[cursor] if cursor < len(expected) else "unknown"
            raise ValueError(f"Chunk list does not cover the full chapter. First missing verse: {next_verse}.")
        return normalized

    def generate_one(self, target: ChapterTarget) -> None:
        key = self.chapter_key(target.book, target.chapter)
        output_path = self.chapter_output_path(target.testament, target.book, target.chapter)
        if output_path.exists() and not self.args.force:
            self.log(f"SKIP {target.book} {target.chapter}: output already exists")
            self.manifest["chapters"][key] = {
                "status": "completed",
                "output_path": str(output_path),
                "skipped_existing": True,
                "updated_at": utc_now(),
            }
            self.save_manifest()
            return

        prompt = self.build_prompt(target)
        prompt_path = self.chapter_prompt_path(target.testament, target.book, target.chapter)
        response_path = self.chapter_response_path(target.testament, target.book, target.chapter)
        repaired_response_path = self.chapter_repaired_response_path(
            target.testament, target.book, target.chapter
        )
        ensure_parent(prompt_path)
        prompt_path.write_text(prompt + "\n", encoding="utf-8")
        self.log(f"START {target.book} {target.chapter} ({target.verses[0]}-{target.verses[-1]})")
        self.log(f"PROMPT {prompt_path}")
        self.manifest["chapters"][key] = {
            "status": "running",
            "testament": target.testament,
            "book": target.book,
            "chapter": target.chapter,
            "verse_start": target.verses[0],
            "verse_end": target.verses[-1],
            "prompt_path": str(prompt_path),
            "updated_at": utc_now(),
        }
        self.save_manifest()

        payload, raw_response, attempts = self.llm.complete_json(
            prompt,
            required_keys=["chunks"],
            temperature=self.args.temperature,
            max_tokens=self.args.max_tokens,
            max_attempts=self.args.max_attempts,
            timeout_seconds=self.args.timeout,
        )
        ensure_parent(response_path)
        response_path.write_text(raw_response + ("\n" if raw_response and not raw_response.endswith("\n") else ""), encoding="utf-8")

        repaired_json = False
        cleaned_response = strip_think_blocks(raw_response)
        if not isinstance(payload, dict):
            payload = extract_json_payload(cleaned_response)
        if not isinstance(payload, dict):
            repaired_payload, repaired_text = self.parse_and_repair_json(raw_response)
            if isinstance(repaired_payload, dict):
                payload = repaired_payload
                repaired_json = True
                ensure_parent(repaired_response_path)
                repaired_response_path.write_text(repaired_text + "\n", encoding="utf-8")

        if not isinstance(payload, dict):
            raise ValueError("Model did not return valid JSON after retry/repair.")

        normalized_chunks = self.validate_payload(payload, target)
        output = {
            "prompt_version": self.prompt_version,
            "generated_at": utc_now(),
            "base_url": self.args.base_url,
            "model_name": self.model_name,
            "book": target.book,
            "chapter": target.chapter,
            "testament": target.testament,
            "verse_start": target.verses[0],
            "verse_end": target.verses[-1],
            "verse_count": len(target.verses),
            "attempts_used": attempts,
            "repaired_json": repaired_json,
            "chunks": normalized_chunks,
        }
        ensure_parent(output_path)
        output_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.manifest["chapters"][key] = {
            "status": "completed",
            "testament": target.testament,
            "book": target.book,
            "chapter": target.chapter,
            "attempts_used": attempts,
            "repaired_json": repaired_json,
            "chunk_count": len(normalized_chunks),
            "output_path": str(output_path),
            "response_path": str(response_path),
            "updated_at": utc_now(),
        }
        self.save_manifest()
        self.consecutive_failures = 0
        self.log(
            f"DONE {target.book} {target.chapter}: {len(normalized_chunks)} chunks"
            + (" (repaired)" if repaired_json else "")
            + f" | attempts={attempts}"
        )
        self.log(f"OUTPUT {output_path}")

    def run(self) -> int:
        targets = self.current_targets()
        if not targets:
            self.log("No chapter targets found for the current filter.")
            return 1
        self.log(
            f"Run start: {len(targets)} chapters | model={self.model_name} | endpoint={self.args.base_url}"
        )
        for target in targets:
            try:
                self.generate_one(target)
            except Exception as exc:
                self.consecutive_failures += 1
                key = self.chapter_key(target.book, target.chapter)
                self.manifest["chapters"][key] = {
                    "status": "failed",
                    "testament": target.testament,
                    "book": target.book,
                    "chapter": target.chapter,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "updated_at": utc_now(),
                }
                self.save_manifest()
                self.log(
                    f"FAIL {target.book} {target.chapter}: {exc} | consecutive_failures={self.consecutive_failures}"
                )
                if self.consecutive_failures > self.args.max_consecutive_failures:
                    self.log(
                        "Stopping run because consecutive failures exceeded the allowed threshold "
                        f"({self.args.max_consecutive_failures})."
                    )
                    return 1
        self.log("Run complete.")
        return 0


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Generate chapter chunk/title JSON files in batch mode."
    )
    parser.add_argument("--book", help="Optional single book or comma-separated list.")
    parser.add_argument(
        "--testament",
        choices=["old", "new", "all"],
        default="all",
        help="Limit generation to one testament.",
    )
    parser.add_argument("--start-chapter", type=int, help="Optional start chapter for a single book run.")
    parser.add_argument("--end-chapter", type=int, help="Optional end chapter for a single book run.")
    parser.add_argument(
        "--output-dir",
        default=str(script_dir / "chapter_chunk_catalog"),
        help="Directory for generated chapter chunk files and logs.",
    )
    parser.add_argument("--base-url", default="http://192.168.1.186:8080")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-consecutive-failures", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate chapters even if output files already exist.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    batch = ChapterChunkBatch(args)
    return batch.run()


if __name__ == "__main__":
    sys.exit(main())
