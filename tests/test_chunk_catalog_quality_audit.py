from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "src" / "ttt_workbench" / "scripts" / "audit_chunk_catalog_quality.py"


def load_module():
    spec = importlib.util.spec_from_file_location("audit_chunk_catalog_quality", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_payload(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "testament": "old",
        "book": "Genesis",
        "chapter": 1,
        "verse_start": 1,
        "verse_end": 5,
        "chunks": chunks,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_quality_audit_flags_boundary_and_label_issues(tmp_path: Path) -> None:
    module = load_module()
    source_dir = tmp_path / "chunks"
    write_payload(
        source_dir / "old" / "genesis" / "genesis_001_chunks.json",
        [
            {"start_verse": 1, "end_verse": 2, "type": "story", "title": "Introduction", "reason": "Opening."},
            {"start_verse": 4, "end_verse": 5, "type": "", "title": "Events", "reason": "Covers verses 3-5."},
        ],
    )

    report = module.build_report(source_dir)

    assert report["summary"]["chapters_scanned"] == 1
    assert report["summary"]["chapters_needing_review"] == 1
    kinds = {issue["kind"] for issue in report["needs_review"][0]["issues"]}
    assert {"boundary_gap", "coverage_missing", "weak_title", "missing_type", "reason_range"} <= kinds


def test_quality_audit_accepts_contiguous_specific_chunks(tmp_path: Path) -> None:
    module = load_module()
    source_dir = tmp_path / "chunks"
    write_payload(
        source_dir / "old" / "genesis" / "genesis_001_chunks.json",
        [
            {
                "start_verse": 1,
                "end_verse": 2,
                "type": "creation",
                "title": "God Forms the Heavens and Earth",
                "reason": "The opening unit establishes God's creative action.",
            },
            {
                "start_verse": 3,
                "end_verse": 5,
                "type": "creation",
                "title": "Light Divides Day from Night",
                "reason": "The next unit focuses on the creation and naming of light.",
            },
        ],
    )

    report = module.build_report(source_dir)

    assert report["summary"] == {
        "chapters_scanned": 1,
        "chapters_safe": 1,
        "chapters_needing_review": 0,
    }
    assert report["safe_chapters"][0]["book"] == "Genesis"
