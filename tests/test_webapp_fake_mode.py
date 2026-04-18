from __future__ import annotations

import sqlite3
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

import ttt_core.llm.llama_cpp as llama_cpp
import ttt_workbench.commands.commit as commitmod
from ttt_core.data.repositories import LexicalRepository
import ttt_webapp.app as appmod
import ttt_webapp.controller as controllermod


def reset_controller() -> None:
    appmod._CONTROLLER = None


def test_settings_fake_mode_avoids_model_probe(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("Real model probe should not run in fake mode.")

    monkeypatch.setattr(llama_cpp.urllib.request, "urlopen", fail_urlopen)
    reset_controller()
    with TestClient(appmod.app) as client:
        response = client.get("/settings")
        try:
            assert response.status_code == 200
            assert "Qwen3.5-35B-A3B-Test" in response.text
        finally:
            response.close()
    reset_controller()


def test_home_page_does_not_emit_no_open_chunk_errors(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")
    reset_controller()
    with TestClient(appmod.app) as client:
        response = client.get("/")
        try:
            assert response.status_code == 200
            assert "No open chunk. Use /open Matthew 1:1-17 first." not in response.text
        finally:
            response.close()
    reset_controller()


def test_epub_background_job_endpoint_reports_status(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")
    monkeypatch.setattr(
        appmod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="EPUB ok\n", stderr=""),
    )
    reset_controller()
    with TestClient(appmod.app) as client:
        response = client.post("/epub/jobs/generate")
        try:
            assert response.status_code == 202
            payload = response.json()
            assert payload["ok"] is True
            job_id = payload["job"]["job_id"]
        finally:
            response.close()

        status_response = client.get(f"/jobs/{job_id}")
        try:
            assert status_response.status_code == 200
            payload = status_response.json()
            assert payload["ok"] is True
            assert payload["job"]["label"] == "epub-generate"
            assert payload["job"]["status"] in {"running", "completed"}
        finally:
            status_response.close()
    reset_controller()


def test_background_job_cancel_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")

    def slow_run(*args, **kwargs):
        time.sleep(0.25)
        return SimpleNamespace(returncode=0, stdout="EPUB ok\n", stderr="")

    monkeypatch.setattr(appmod.subprocess, "run", slow_run)
    reset_controller()
    with TestClient(appmod.app) as client:
        response = client.post("/epub/jobs/generate")
        try:
            assert response.status_code == 202
            job_id = response.json()["job"]["job_id"]
        finally:
            response.close()

        cancel_response = client.post(f"/jobs/{job_id}/cancel")
        try:
            assert cancel_response.status_code == 200
            payload = cancel_response.json()
            assert payload["ok"] is True
            assert payload["job"]["status"] in {"cancelled", "completed"}
        finally:
            cancel_response.close()
    reset_controller()


def test_chapter_route_lists_saved_chunks_with_compact_navigator(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")
    reset_controller()
    with TestClient(appmod.app) as client:
        response = client.get("/workspace/old/genesis/1")
        try:
            assert response.status_code == 200
            assert "workspace-shell" in response.text
            assert "Creation of Light and Day One" in response.text
            assert "Merge chunks" in response.text
            assert ">Open<" not in response.text
        finally:
            response.close()
    reset_controller()


def test_chunk_routes_survive_lexical_db_open_failures(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")

    def fail_connect(self) -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(LexicalRepository, "_connect", fail_connect)
    reset_controller()
    with TestClient(appmod.app) as client:
        chunk_response = client.get("/workspace/old/genesis/1/1-5")
        try:
            assert chunk_response.status_code == 200
            assert "Comparison sources and lexical context" in chunk_response.text
            assert "Creation of Light and Day One" in chunk_response.text
            assert "Run review" not in chunk_response.text
            assert "Stage text" not in chunk_response.text
        finally:
            chunk_response.close()

        sources_response = client.post(
            "/workspace/old/genesis/1/1-5/study/sources",
            data={"selected_sources": ["LSB", "ESV"]},
        )
        sources_json_response = client.post(
            "/workspace/old/genesis/1/1-5/study/sources",
            data={"selected_sources": ["LSB", "ESV", "KJV"]},
            headers={"accept": "application/json"},
        )
        try:
            assert sources_response.status_code == 200
            assert "context-panel" in sources_response.text
            assert "LSB" in sources_response.text
            assert 'value="LSB" checked' in sources_response.text
            assert 'value="ESV" checked' in sources_response.text
            assert "Apply sources" not in sources_response.text
            assert sources_json_response.status_code == 200
            sources_json = sources_json_response.json()
            assert sources_json["ok"] is True
            assert sources_json["selected_sources"] == ["LSB", "ESV", "KJV"]
            assert 'data-translation-alias="KJV"' in sources_json["translation_blocks_html"]
        finally:
            sources_response.close()
            sources_json_response.close()
    reset_controller()

def test_primary_fake_mode_feature_routes_render_without_server_errors(monkeypatch) -> None:
    monkeypatch.setenv("TTT_WEBAPP_FAKE_LLM", "1")

    def fake_write_backup_set(backups_dir, writes):
        backup_dir = backups_dir / "browser-test-backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    monkeypatch.setattr(commitmod, "write_backup_set", fake_write_backup_set)
    monkeypatch.setattr(controllermod, "restore_backup_set", lambda backup_dir: ["chapter.json"])
    monkeypatch.setattr(
        appmod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="EPUB ok\n", stderr=""),
    )

    def assert_clean(response) -> str:
        try:
            assert response.status_code == 200 or response.status_code == 302
            text = response.text
            assert "Internal Server Error" not in text
            assert "Traceback" not in text
            return text
        finally:
            response.close()

    reset_controller()
    with TestClient(appmod.app) as client:
        assert_clean(client.get("/"))
        assert_clean(client.get("/settings"))
        assert_clean(client.post("/settings/test-endpoint"))
        assert_clean(client.get("/epub"))
        epub_text = assert_clean(client.post("/epub/generate"))
        assert_clean(client.get("/workspace/old/genesis/1"))
        chunk_text = assert_clean(client.get("/workspace/old/genesis/1/1-5"))
        assert_clean(
            client.post(
                "/workspace/old/genesis/1/1-5/study/sources",
                data={"selected_sources": ["LSB", "ESV"]},
            )
        )
        revision_text = assert_clean(
            client.post(
                "/workspace/old/genesis/1/1-5/editor/mode",
                data={"editor_action": "seed-draft"},
            )
        )
        draft_text = assert_clean(
            client.post(
                "/workspace/old/genesis/1/1-5/draft/autosave",
                data={
                    "editor_mode": "draft",
                    "draft_title": "Creation of Light and Day One",
                    "draft_range_start": "1",
                    "draft_range_end": "5",
                    "draft_range_text": (
                        "1. In the beginning God created the heavens and the earth.\n\n"
                        "2. The earth was formless and void.\n\n"
                        "3. Then God said, Let there be light.\n\n"
                        "4. God saw that the light was good.\n\n"
                        "5. God called the light Day."
                    ),
                },
            )
        )
        range_text = assert_clean(
            client.post(
                "/workspace/old/genesis/1/1-5/draft/range",
                data={
                    "editor_mode": "draft",
                    "draft_title": "Creation of Light and Day One",
                    "draft_range_start": "1",
                    "draft_range_end": "5",
                    "draft_range_text": (
                        "1. In the beginning God created the heavens and the earth.\n\n"
                        "2. The earth was formless and void.\n\n"
                        "3. Then God said, Let there be light.\n\n"
                        "4. God saw that the light was good.\n\n"
                        "5. God called the light Day."
                    ),
                    "editor_target_start": "3",
                    "editor_target_end": "5",
                },
            )
        )
        chat_context_text = assert_clean(
            client.get(
                "/workspace/old/genesis/1/1-5/chat/prompt-text",
            )
        )
        interactive_state_payload = client.get(
            "/workspace/old/genesis/1/1-5/interactive-state"
        ).json()
        json_tree_text = assert_clean(client.get("/workspace/old/genesis/1/1-5/json-book-tree"))
        json_chapter_text = assert_clean(client.get("/workspace/old/genesis/1/1-5/json-book-chapter/1"))
        chapter_json_tree_text = assert_clean(client.get("/workspace/old/genesis/1/json-book-tree"))
        commit_text = assert_clean(
            client.post(
                "/workspace/old/genesis/1/1-5/commit/apply",
                data={
                    "editor_mode": "draft",
                    "draft_title": "Creation of Light and Day One",
                    "draft_range_start": "1",
                    "draft_range_end": "5",
                    "draft_range_text": (
                        "1. Refined verse 1.\n\n"
                        "2. Refined verse 2.\n\n"
                        "3. Refined verse 3.\n\n"
                        "4. Refined verse 4.\n\n"
                        "5. Refined verse 5."
                    ),
                },
            )
        )
        rollback_text = assert_clean(client.post("/workspace/old/genesis/1/1-5/commit/rollback"))
        resume_text = assert_clean(client.get("/resume"))

        assert "EPUB generated successfully" in epub_text
        assert "Comparison sources and lexical context" in chunk_text
        assert "jsonModal" not in chunk_text
        assert "gloss-verse-row" in chunk_text
        assert "gloss-verse-text" in chunk_text
        assert "data-gloss=\"ba.Ra" not in chunk_text
        assert "Creation of Light and Day One" in chunk_text
        assert "data-editor-mode=\"draft\"" in revision_text
        assert '"ok":true' in draft_text.replace(" ", "")
        assert "Save Draft" not in revision_text
        assert "workspace-shell" not in draft_text
        assert "Creation of Light and Day One" in range_text
        assert interactive_state_payload["ok"] is True
        assert interactive_state_payload["workspace"]["chunk_key"] == "1-5"
        assert interactive_state_payload["editor"]["range_start"] == 1
        assert "draft" in interactive_state_payload["chat"]["context_sources"]
        assert '"book":"Genesis"' in json_tree_text.replace(" ", "")
        assert '"chapter":1' in json_chapter_text.replace(" ", "")
        assert '"book":"Genesis"' in chapter_json_tree_text.replace(" ", "")
        assert "editor-panel" in commit_text
        assert "workspace-shell" not in commit_text
        assert "data-editor-mode=\"committed\"" in commit_text
        assert "Start Revision" in commit_text
        assert "workspace-shell" in rollback_text
        assert "Creation of Light and Day One" in resume_text
    reset_controller()
