#!/usr/bin/env python3
"""Refine approved chunk titles with a Matthew-shaped style pass.

This script preserves the existing chunk verse ranges and reasons while
rewriting weak or mechanical titles into more evocative, theologically-aware
 labels. Matthew 1-25 remains the gold-standard reference and is not edited.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ttt_core.config import load_config
from ttt_core.data.repositories import ProjectPaths, SourceRepository
from ttt_core.llm.llama_cpp import LlamaCppClient
from ttt_core.utils import ensure_parent, normalize_book_key, utc_now
from ttt_workbench.scripts.post_process_chunk_merging import book_payload_from_chapters


CURATED_EXAMPLE_REFS = (
    ("Matthew", 1, 1, 17),
    ("Matthew", 1, 18, 25),
    ("Matthew", 2, 1, 12),
    ("Matthew", 2, 16, 18),
    ("Matthew", 4, 1, 11),
    ("Matthew", 5, 3, 12),
    ("Matthew", 6, 19, 24),
    ("Matthew", 7, 13, 14),
    ("Matthew", 18, 1, 9),
    ("Matthew", 26, 36, 46),
)

MAX_CHUNK_CONTEXT_CHARS = 700

GENERIC_REVIEW_WORDS = {
    "account",
    "acts",
    "announcement",
    "answer",
    "appeal",
    "argument",
    "background",
    "blessing",
    "blessings",
    "call",
    "command",
    "commands",
    "conclusion",
    "context",
    "cycle",
    "decree",
    "description",
    "discourse",
    "division",
    "events",
    "exhortation",
    "genealogy",
    "history",
    "instructions",
    "introduction",
    "judgment",
    "judgments",
    "lament",
    "law",
    "laws",
    "list",
    "lists",
    "message",
    "ministry",
    "narrative",
    "oracle",
    "oracles",
    "parable",
    "petition",
    "plot",
    "prayer",
    "preparation",
    "prophecy",
    "rebellion",
    "rebuke",
    "refusal",
    "report",
    "restoration",
    "return",
    "song",
    "teaching",
    "teachings",
    "vision",
    "warning",
    "warnings",
    "woe",
}

LOW_SIGNAL_PREFIXES = (
    "introduction",
    "conclusion",
    "summary",
    "historical context",
    "final instructions",
    "closing instructions",
    "opening ",
    "first ",
    "second ",
    "third ",
)

FORBIDDEN_TITLE_PATTERNS = (
    re.compile(r":"),
    re.compile(r"\bverses?\b", re.IGNORECASE),
    re.compile(r"\bpart\s+\d+\b", re.IGNORECASE),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    cfg = load_config()
    paths = cfg["paths"]
    parser = argparse.ArgumentParser(
        description="Refine approved chapter chunk titles without changing ranges."
    )
    parser.add_argument(
        "--source-dir",
        default=str(Path(paths["final_data"]) / "chapter_chunk_catalog" / "chunks"),
        help="Per-chapter approved chunk catalog directory.",
    )
    parser.add_argument(
        "--books-dir",
        default=str(Path(paths["final_data"]) / "chapter_chunk_catalog" / "books"),
        help="Per-book approved chunk catalog directory to rebuild after refinement.",
    )
    parser.add_argument(
        "--manifest-path",
        default=str(Path(paths["final_data"]) / "chapter_chunk_catalog" / "title_refinement_manifest.json"),
        help="Manifest file describing the title-refinement pass.",
    )
    parser.add_argument(
        "--source-alias",
        default="LSB",
        help="Bible source alias used to provide passage text to the LLM.",
    )
    parser.add_argument(
        "--selection",
        choices=("suspect", "all"),
        default="suspect",
        help="Refine only chapters with weak titles, or every non-manual chapter.",
    )
    parser.add_argument(
        "--only-book",
        help="Optional single book filter.",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=0,
        help="Optional limit for smaller batches.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="LLM temperature.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Per-chapter LLM timeout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report intended edits without writing files.",
    )
    return parser.parse_args(argv)


def title_review_score(title: str) -> int:
    text = title.strip()
    if not text:
        return 99
    lowered = text.lower()
    if any(pattern.search(text) for pattern in FORBIDDEN_TITLE_PATTERNS):
        return 99
    words = [piece.strip(" ,.;:!?()[]{}'\"") for piece in text.split()]
    normalized = [piece.lower() for piece in words if piece]
    score = 0
    if lowered.startswith(LOW_SIGNAL_PREFIXES):
        score += 2
    if "cycle" in normalized:
        score += 3
    if "'s" not in lowered and "'S" in title:
        score += 3
    if normalized and normalized[-1] in {
        "context",
        "instructions",
        "teaching",
        "judgment",
        "argument",
        "appeal",
        "preparation",
        "report",
        "warning",
        "warnings",
    }:
        score += 2
    if len(normalized) <= 4 and any(word in GENERIC_REVIEW_WORDS for word in normalized):
        score += 1
    if len(normalized) >= 5:
        generic_count = sum(1 for word in normalized if word in GENERIC_REVIEW_WORDS)
        if generic_count >= max(2, len(normalized) // 2):
            score += 2
    roots = [word[:5] for word in normalized if len(word) >= 5]
    if len(roots) != len(set(roots)):
        score += 3
    return score


def title_needs_review(title: str) -> bool:
    return title_review_score(title) >= 3


def title_is_valid(title: str) -> bool:
    text = title.strip()
    if not text:
        return False
    if len(text) > 72:
        return False
    words = [piece for piece in text.split() if piece]
    if len(words) > 8:
        return False
    if any(pattern.search(text) for pattern in FORBIDDEN_TITLE_PATTERNS):
        return False
    return True


def load_curated_examples(books_dir: Path) -> list[dict[str, Any]]:
    matthew_path = books_dir / "new" / "matthew_chunks.json"
    payload = json.loads(matthew_path.read_text(encoding="utf-8"))
    index = {
        (payload["book"], int(chapter["chapter"]), int(chunk["start_verse"]), int(chunk["end_verse"])): chunk["title"]
        for chapter in payload["chapters"]
        for chunk in chapter["chunks"]
    }
    examples: list[dict[str, Any]] = []
    for ref in CURATED_EXAMPLE_REFS:
        title = index.get(ref)
        if title:
            examples.append(
                {
                    "book": ref[0],
                    "chapter": ref[1],
                    "start_verse": ref[2],
                    "end_verse": ref[3],
                    "title": title,
                }
            )
    if not examples:
        raise FileNotFoundError(f"Unable to load curated Matthew examples from {matthew_path}")
    return examples


def chapter_passage_context(
    source_repo: SourceRepository,
    alias: str,
    chapter_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for chunk in chapter_payload.get("chunks", []):
        start_verse = int(chunk["start_verse"])
        end_verse = int(chunk["end_verse"])
        verse_map = source_repo.verse_range(alias, chapter_payload["book"], int(chapter_payload["chapter"]), start_verse, end_verse)
        text = " ".join(f"{verse}. {content}" for verse, content in verse_map.items()).strip()
        if len(text) > MAX_CHUNK_CONTEXT_CHARS:
            text = text[: MAX_CHUNK_CONTEXT_CHARS - 4].rstrip() + " ..."
        context.append(
            {
                "start_verse": start_verse,
                "end_verse": end_verse,
                "type": str(chunk.get("type", "")).strip() or "mixed",
                "current_title": str(chunk.get("title", "")).strip(),
                "needs_review": title_needs_review(str(chunk.get("title", "")).strip()),
                "text": text,
            }
        )
    return context


def build_prompt(
    chapter_payload: dict[str, Any],
    review_context: list[dict[str, Any]],
    examples: list[dict[str, Any]],
) -> str:
    prompt = (
        "Refine Bible chunk titles to match the tone of curated Matthew titles.\n\n"
        "Rules:\n"
        "- Keep the exact same start_verse and end_verse values.\n"
        "- Return JSON with key \"titles\" only.\n"
        "- Each title must be concise, evocative, reverent, and natural English.\n"
        "- Prefer 1-7 words.\n"
        "- Avoid flat labels like \"Introduction\", \"Historical Context\", \"Instructions\", \"Judgment\", "
        "\"Prophecy\", or \"Teaching\" unless the passage truly demands them.\n"
        "- Favor titles that capture the heart, image, or spiritual weight of the passage.\n"
        "- Do not invent events, names, or theology not present in the text.\n"
        "- If a current title is already strong, you may keep it.\n\n"
        "Curated examples:\n"
    )
    prompt += json.dumps(examples, indent=2, ensure_ascii=False)
    prompt += "\n\nPassage to refine:\n"
    prompt += json.dumps(
        {
            "book": chapter_payload["book"],
            "chapter": int(chapter_payload["chapter"]),
            "chunks_to_retitle": review_context,
        },
        indent=2,
        ensure_ascii=False,
    )
    prompt += (
        "\n\nReturn JSON in this shape only:\n"
        '{"titles":[{"start_verse":1,"end_verse":17,"title":"..."}]}'
    )
    return prompt


def validate_title_payload(
    review_context: list[dict[str, Any]],
    payload: dict[str, Any] | list[Any] | None,
) -> list[dict[str, Any]] | None:
    if not isinstance(payload, dict):
        return None
    items = payload.get("titles")
    if not isinstance(items, list):
        return None
    if len(items) != len(review_context):
        return None
    validated: list[dict[str, Any]] = []
    for original, item in zip(review_context, items):
        if not isinstance(item, dict):
            return None
        start_verse = int(item.get("start_verse", 0))
        end_verse = int(item.get("end_verse", 0))
        if start_verse != int(original["start_verse"]) or end_verse != int(original["end_verse"]):
            return None
        title = str(item.get("title", "")).strip()
        if not title_is_valid(title):
            return None
        validated.append(
            {
                "start_verse": start_verse,
                "end_verse": end_verse,
                "title": title,
            }
        )
    return validated


def should_refine_chapter(chapter_payload: dict[str, Any], selection: str) -> bool:
    if str(chapter_payload.get("source", "")).strip() == "manual-sync":
        return False
    if selection == "all":
        return True
    return any(title_needs_review(str(chunk.get("title", "")).strip()) for chunk in chapter_payload.get("chunks", []))


def apply_titles(chapter_payload: dict[str, Any], titles: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    updated = json.loads(json.dumps(chapter_payload))
    changed = 0
    replacement_map = {
        (int(item["start_verse"]), int(item["end_verse"])): str(item["title"]).strip()
        for item in titles
    }
    for chunk in updated["chunks"]:
        key = (int(chunk["start_verse"]), int(chunk["end_verse"]))
        if key not in replacement_map:
            continue
        new_title = replacement_map[key]
        if str(chunk.get("title", "")).strip() != new_title:
            chunk["title"] = new_title
            changed += 1
    updated["generated_at"] = utc_now()
    updated["title_refined_at"] = utc_now()
    if changed:
        updated["source"] = "post-processed-title-refined"
    return updated, changed


def write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    ensure_parent(manifest_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    source_root = Path(args.source_dir).resolve()
    books_root = Path(args.books_dir).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    source_repo = SourceRepository(ProjectPaths())
    if args.source_alias.upper() not in source_repo.catalog:
        raise KeyError(f"Unknown source alias '{args.source_alias}'. Available: {', '.join(source_repo.list_sources())}")
    client = LlamaCppClient()
    examples = load_curated_examples(books_root)

    chapter_paths = sorted(source_root.glob("*/*/*_chunks.json"))
    if args.only_book:
        only = normalize_book_key(args.only_book)
        chapter_paths = [path for path in chapter_paths if path.parent.name == only]
    selected_paths: list[Path] = []
    retained_by_book: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for path in chapter_paths:
        chapter_payload = json.loads(path.read_text(encoding="utf-8"))
        testament = path.relative_to(source_root).parts[0]
        book = str(chapter_payload["book"]).strip()
        retained_by_book.setdefault((testament, book), []).append(chapter_payload)
        if should_refine_chapter(chapter_payload, args.selection):
            selected_paths.append(path)

    if args.max_chapters > 0:
        selected_paths = selected_paths[: args.max_chapters]

    manifest: dict[str, Any] = {
        "generated_at": utc_now(),
        "selection": args.selection,
        "source_alias": args.source_alias.upper(),
        "source_dir": str(source_root),
        "books_dir": str(books_root),
        "llm_base_url": client.base_url,
        "chapters": {},
    }

    changed_titles = 0
    changed_chapters = 0
    for index, path in enumerate(selected_paths, start=1):
        chapter_payload = json.loads(path.read_text(encoding="utf-8"))
        testament = path.relative_to(source_root).parts[0]
        book = str(chapter_payload["book"]).strip()
        chapter = int(chapter_payload["chapter"])
        chunk_context = chapter_passage_context(source_repo, args.source_alias.upper(), chapter_payload)
        review_context = [item for item in chunk_context if item["needs_review"]]
        if not review_context:
            continue
        prompt = build_prompt(chapter_payload, review_context, examples)
        payload, _raw, attempts = client.complete_json(
            prompt,
            required_keys=["titles"],
            temperature=args.temperature,
            max_tokens=1200,
            timeout_seconds=args.timeout_seconds,
        )
        validated = validate_title_payload(review_context, payload)
        manifest_key = f"{normalize_book_key(book)}:{chapter}"
        if validated is None:
            manifest["chapters"][manifest_key] = {
                "book": book,
                "chapter": chapter,
                "testament": testament,
                "status": "invalid_response",
                "attempts": attempts,
                "path": str(path),
            }
            continue
        updated_payload, changed = apply_titles(chapter_payload, validated)
        manifest["chapters"][manifest_key] = {
            "book": book,
            "chapter": chapter,
            "testament": testament,
            "status": "updated" if changed else "unchanged",
            "attempts": attempts,
            "path": str(path),
            "changed_titles": changed,
        }
        if changed:
            changed_titles += changed
            changed_chapters += 1
            retained = retained_by_book[(testament, book)]
            retained_by_book[(testament, book)] = [
                updated_payload if int(item["chapter"]) == chapter else item
                for item in retained
            ]
            if not args.dry_run:
                path.write_text(
                    json.dumps(updated_payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
        if not args.dry_run:
            write_manifest(manifest_path, manifest)
        print(f"[{index}/{len(selected_paths)}] {book} {chapter}: {changed} title(s) changed", flush=True)

    if not args.dry_run:
        for (testament, book), chapters in sorted(
            retained_by_book.items(),
            key=lambda item: (item[0][0], normalize_book_key(item[0][1])),
        ):
            payload = book_payload_from_chapters(testament, book, chapters)
            out_path = books_root / testament / f"{normalize_book_key(book)}_chunks.json"
            ensure_parent(out_path)
            out_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        write_manifest(manifest_path, manifest)

    print(
        f"Reviewed {len(selected_paths)} chapter files; updated {changed_titles} titles across {changed_chapters} chapters.",
        flush=True,
    )
    print(f"Updated chapter catalogs: {source_root}", flush=True)
    print(f"Rebuilt book catalogs: {books_root}", flush=True)
    print(f"Manifest: {manifest_path}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
