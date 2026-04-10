from __future__ import annotations

import json
from pathlib import Path

from ttt_core.data.repositories import ProjectPaths
from ttt_webapp.chunk_catalog import ChunkCatalogRepository


def write_chapter_payload(
    path: Path,
    *,
    testament: str,
    book: str,
    chapter: int,
    chunks: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "prompt_version": "chapter_chunk_batch_v1",
        "generated_at": "2026-04-10T10:30:49Z",
        "book": book,
        "chapter": chapter,
        "testament": testament,
        "verse_start": chunks[0]["start_verse"],
        "verse_end": chunks[-1]["end_verse"],
        "verse_count": int(chunks[-1]["end_verse"]) - int(chunks[0]["start_verse"]) + 1,
        "attempts_used": 1,
        "repaired_json": False,
        "chunks": chunks,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def test_merge_consecutive_chunks_updates_chapter_and_book_bundle(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    workspace_dir = repo_root / "02_Human_Editorial_Workspace"
    paths = ProjectPaths(workspace_dir=workspace_dir, repo_root=repo_root)
    repository = ChunkCatalogRepository(paths, bible_repo=object())  # type: ignore[arg-type]

    chapter_path = (
        workspace_dir
        / "scripts"
        / "chapter_chunk_catalog"
        / "chunks"
        / "old"
        / "genesis"
        / "genesis_001_chunks.json"
    )
    write_chapter_payload(
        chapter_path,
        testament="old",
        book="Genesis",
        chapter=1,
        chunks=[
            {
                "start_verse": 1,
                "end_verse": 5,
                "type": "story",
                "title": "Creation of Light",
                "reason": "Opening movement.",
            },
            {
                "start_verse": 6,
                "end_verse": 8,
                "type": "story",
                "title": "Creation of Sky",
                "reason": "Second movement.",
            },
            {
                "start_verse": 9,
                "end_verse": 13,
                "type": "story",
                "title": "Creation of Land",
                "reason": "Third movement.",
            },
        ],
    )

    merged = repository.merge_consecutive_chunks(
        "old",
        "Genesis",
        1,
        start_index=1,
        end_index=2,
        title="Days One and Two",
        reason="These chunks read better as one larger unit.",
    )

    assert merged["start_verse"] == 1
    assert merged["end_verse"] == 8
    assert merged["title"] == "Days One and Two"

    chapter_payload = json.loads(chapter_path.read_text(encoding="utf-8"))
    assert [item["title"] for item in chapter_payload["chunks"]] == [
        "Days One and Two",
        "Creation of Land",
    ]

    book_path = (
        workspace_dir
        / "scripts"
        / "chapter_chunk_catalog_books"
        / "old"
        / "genesis_chunks.json"
    )
    book_payload = json.loads(book_path.read_text(encoding="utf-8"))
    assert book_payload["schema_version"] == 1
    assert book_payload["book"] == "Genesis"
    assert book_payload["chapters"][0]["chapter"] == 1
    assert [item["title"] for item in book_payload["chapters"][0]["chunks"]] == [
        "Days One and Two",
        "Creation of Land",
    ]
