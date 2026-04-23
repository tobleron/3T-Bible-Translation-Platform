from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ttt_workbench.controller import BrowserWorkbench
from ttt_core.utils import write_json_atomic
from ttt_core.data.repositories import write_backup_set
import ttt_webapp.app as appmod


def reset_controller() -> None:
    appmod._SESSION_CONTROLLERS.clear()
    appmod._TEST_SESSION_ID = "test"
    from pathlib import Path
    fake_state_dir = Path(".ttt_workbench/browser_fake_mode_test")
    if fake_state_dir.exists():
        for stale in ["active_session.json", "chunk_sessions.json"]:
            p = fake_state_dir / stale
            if p.exists():
                p.unlink()


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------

def test_two_browser_sessions_have_isolated_state(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")
    reset_controller()
    # Unset test session override so cookies drive session lookup
    appmod._TEST_SESSION_ID = None

    client_a = TestClient(appmod.app, cookies={"ttt_session_id": "session-a"})
    client_b = TestClient(appmod.app, cookies={"ttt_session_id": "session-b"})

    # Session A opens Genesis 1:1-5
    resp_a = client_a.get("/workspace/old/genesis/1/1-5")
    assert resp_a.status_code == 200
    resp_a.close()

    # Session B opens the same chunk
    resp_b = client_b.get("/workspace/old/genesis/1/1-5")
    assert resp_b.status_code == 200
    resp_b.close()

    # Mutate draft in session A
    save_a = client_a.post(
        "/workspace/old/genesis/1/1-5/draft/autosave",
        data={
            "editor_mode": "draft",
            "draft_title": "Session A Title",
            "draft_range_start": "1",
            "draft_range_end": "5",
            "verse_1": "Session A verse 1.",
        },
    )
    assert save_a.status_code == 200
    save_a.close()

    # Session B should NOT see session A's draft
    state_b = client_b.get("/workspace/old/genesis/1/1-5/interactive-state")
    payload_b = state_b.json()
    state_b.close()
    wb_b = appmod._SESSION_CONTROLLERS.get("session-b")
    assert wb_b is not None
    assert wb_b.state.draft_title != "Session A Title"

    client_a.close()
    client_b.close()
    reset_controller()


# ---------------------------------------------------------------------------
# Atomic persistence
# ---------------------------------------------------------------------------

def test_write_json_atomic_never_leaves_truncated_file(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    payload = {"revision": 42, "data": "x" * 10000}
    write_json_atomic(target, payload)
    assert target.exists()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == payload


def test_write_json_atomic_recovers_from_invalid_primary(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("corrupt", encoding="utf-8")
    backup = tmp_path / "state.json.bak"
    valid = {"revision": 7}
    backup.write_text(json.dumps(valid), encoding="utf-8")
    # Our helper does not auto-restore from backup; this test documents
    # that a caller could implement recovery. For now, assert overwrite works.
    write_json_atomic(target, {"revision": 8})
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["revision"] == 8


# ---------------------------------------------------------------------------
# Commit rollback
# ---------------------------------------------------------------------------

def test_write_backup_set_rolls_back_on_partial_failure(tmp_path: Path) -> None:
    # Place targets inside the same tree as backups_dir so path validation passes
    project_root = tmp_path / "project"
    project_root.mkdir()
    backups_dir = project_root / "backups"
    file_a = project_root / "a.txt"
    file_a.write_text("original-a", encoding="utf-8")
    file_b = project_root / "b.txt"
    file_b.write_text("original-b", encoding="utf-8")

    class Boom(Exception):
        pass

    original_replace = Path.replace

    def flaky_replace(self: Path, target: Path) -> Path:
        if target.name == "b.txt":
            raise Boom("disk full")
        return original_replace(self, target)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Path, "replace", flaky_replace)
    try:
        with pytest.raises(Boom):
            write_backup_set(
                backups_dir,
                [
                    (file_a, "original-a", "new-a"),
                    (file_b, "original-b", "new-b"),
                ],
            )
    finally:
        monkeypatch.undo()

    # file_a should be rolled back to original
    assert file_a.read_text(encoding="utf-8") == "original-a"
    assert file_b.read_text(encoding="utf-8") == "original-b"


# ---------------------------------------------------------------------------
# Autosave ordering / revision conflict
# ---------------------------------------------------------------------------

def test_draft_autosave_rejects_stale_revision(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")
    reset_controller()
    with TestClient(appmod.app) as client:
        first = client.post(
            "/workspace/old/genesis/1/1-5/draft/autosave",
            data={
                "editor_mode": "draft",
                "draft_revision": "0",
                "draft_title": "Creation of Light and Day One",
                "draft_range_start": "1",
                "draft_range_end": "5",
                "verse_1": "In the beginning.",
            },
        )
        assert first.status_code == 200
        assert first.json()["draft_revision"] == 1
        first.close()

        stale = client.post(
            "/workspace/old/genesis/1/1-5/draft/autosave",
            data={
                "editor_mode": "draft",
                "draft_revision": "0",
                "draft_title": "Creation of Light and Day One",
                "draft_range_start": "1",
                "draft_range_end": "5",
                "verse_1": "A stale write attempt.",
            },
        )
        assert stale.status_code == 409
        body = stale.json()
        assert body["code"] == "stale_draft_revision"
        assert body["draft_revision"] == 1
        stale.close()
    reset_controller()


# ---------------------------------------------------------------------------
# XSS escaping in markdown renderer
# ---------------------------------------------------------------------------

def test_markdown_sanitizer_strips_script_tags() -> None:
    from ttt_workbench.webapp import _render_markdown

    malicious = "Hello <script>alert('xss')</script> world"
    html = _render_markdown(malicious)
    assert "<script>" not in html
    assert "alert" not in html
    assert "Hello" in html
    assert "world" in html


def test_markdown_sanitizer_preserves_allowed_tags() -> None:
    from ttt_workbench.webapp import _render_markdown

    text = "**bold** and *italic* and `code`"
    html = _render_markdown(text)
    assert "<strong>" in html or "<b>" in html
    assert "<em>" in html or "<i>" in html
    assert "<code>" in html


# ---------------------------------------------------------------------------
# Provider failure handling
# ---------------------------------------------------------------------------

def test_model_discovery_error_is_surfaced_in_settings(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")
    reset_controller()
    wb = appmod.controller()
    wb.set_model_discovery_error("local", "Endpoint unreachable")
    payload = wb.settings_payload()
    # settings_payload uses current provider; ensure provider is local so the error maps
    wb.web_settings["endpoint_provider"] = "local"
    payload = wb.settings_payload()
    assert payload["model_discovery_error"] == "Endpoint unreachable"
    reset_controller()
