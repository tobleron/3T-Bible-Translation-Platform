from __future__ import annotations

import ttt_webapp.app as appmod


def reset_controller() -> None:
    appmod._CONTROLLER = None


def test_project_summary_counts_translated_from_cataloged_chunk_activity(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")
    reset_controller()
    wb = appmod.controller()

    monkeypatch.setattr(
        wb.bible_repo,
        "canonical_books",
        lambda testament: ["Genesis"] if testament == "old" else [],
    )
    monkeypatch.setattr(
        wb.source_repo,
        "chapters_for_book",
        lambda book: [1, 2, 3],
    )
    monkeypatch.setattr(
        wb.chunk_catalog_repo,
        "chunk_status_map",
        lambda testament, book: {1: 0, 2: 2, 3: 1},
    )
    monkeypatch.setattr(wb.source_repo, "list_sources", lambda: [])

    summary = wb.project_summary()
    assert summary["total_chapters"] == 3
    assert summary["cataloged_chapters"] == 2
    assert summary["translated_chapters"] == 2
    assert summary["total_chunks"] == 3
    assert summary["translation_percent"] == 66.7
    assert summary["sources"] == []

    reset_controller()
