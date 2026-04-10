from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "02_Human_Editorial_Workspace"
    / "scripts"
    / "aggregate_chunk_catalog_books.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("aggregate_chunk_catalog_books", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_chapter_file(path: Path, *, testament: str, book: str, chapter: int, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "prompt_version": "chapter_chunk_batch_v1",
        "generated_at": "2026-04-10T10:30:49Z",
        "base_url": "http://192.168.1.186:8080",
        "model_name": "Qwen",
        "book": book,
        "chapter": chapter,
        "testament": testament,
        "verse_start": chunks[0]["start_verse"],
        "verse_end": chunks[-1]["end_verse"],
        "verse_count": chunks[-1]["end_verse"] - chunks[0]["start_verse"] + 1,
        "attempts_used": 1,
        "repaired_json": False,
        "chunks": chunks,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def test_aggregate_books_writes_minimal_book_payload_and_keeps_unrelated_files(tmp_path: Path) -> None:
    module = load_module()
    source_dir = tmp_path / "chapter_chunk_catalog" / "chunks"
    output_dir = tmp_path / "chapter_chunk_catalog_books"

    write_chapter_file(
        source_dir / "old" / "genesis" / "genesis_002_chunks.json",
        testament="old",
        book="Genesis",
        chapter=2,
        chunks=[
            {
                "start_verse": 1,
                "end_verse": 3,
                "type": "story",
                "title": "The Seventh Day",
                "reason": "A complete unit around God's rest.",
            }
        ],
    )
    write_chapter_file(
        source_dir / "old" / "genesis" / "genesis_001_chunks.json",
        testament="old",
        book="Genesis",
        chapter=1,
        chunks=[
            {
                "start_verse": 1,
                "end_verse": 31,
                "type": "story",
                "title": "Creation",
                "reason": "A complete creation account.",
            }
        ],
    )

    untouched = output_dir / "new" / "matthew_chunks.json"
    untouched.parent.mkdir(parents=True, exist_ok=True)
    untouched.write_text('{"keep": true}\n', encoding="utf-8")

    exit_code = module.main(
        [
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "old" / "genesis_chunks.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["testament"] == "old"
    assert payload["book"] == "Genesis"
    assert payload["book_key"] == "genesis"
    assert [item["chapter"] for item in payload["chapters"]] == [1, 2]
    assert "base_url" not in payload
    assert "prompt_version" not in payload["chapters"][0]
    assert payload["chapters"][0]["chunks"][0]["title"] == "Creation"
    assert untouched.read_text(encoding="utf-8") == '{"keep": true}\n'


def test_aggregate_books_rejects_duplicate_chapter_payloads(tmp_path: Path) -> None:
    module = load_module()
    source_dir = tmp_path / "chapter_chunk_catalog" / "chunks"

    chunk = [
        {
            "start_verse": 1,
            "end_verse": 5,
            "type": "story",
            "title": "Opening",
            "reason": "One coherent unit.",
        }
    ]
    write_chapter_file(
        source_dir / "old" / "genesis" / "genesis_001_chunks.json",
        testament="old",
        book="Genesis",
        chapter=1,
        chunks=chunk,
    )
    write_chapter_file(
        source_dir / "old" / "alias" / "alias_001_chunks.json",
        testament="old",
        book="Genesis",
        chapter=1,
        chunks=chunk,
    )

    try:
        module.aggregate_books(
            source_dir=source_dir,
            testaments=["old"],
            books_filter=set(),
        )
    except ValueError as exc:
        assert "Duplicate chapter entry" in str(exc)
    else:
        raise AssertionError("Expected duplicate chapter aggregation to fail.")
