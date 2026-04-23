"""Tests for the EPUB generation service."""

import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ttt_workbench.services.epub_service import EpubService


class TestEpubServiceRecentEpubs:
    def test_returns_empty_when_builds_dir_missing(self, tmp_path):
        svc = EpubService(repo_root=tmp_path, output_dir=tmp_path)
        assert svc.recent_epubs() == []

    def test_returns_epub_files_sorted_by_mtime(self, tmp_path):
        builds = tmp_path / "builds"
        builds.mkdir()
        (builds / "old.epub").write_bytes(b"old")
        time.sleep(0.01)
        (builds / "new.epub").write_bytes(b"newer")
        svc = EpubService(repo_root=tmp_path, output_dir=tmp_path)
        result = svc.recent_epubs(limit=5)
        assert len(result) == 2
        assert result[0].name == "new.epub"

    def test_respects_limit(self, tmp_path):
        builds = tmp_path / "builds"
        builds.mkdir()
        for i in range(6):
            (builds / f"book_{i}.epub").write_bytes(b"data")
        svc = EpubService(repo_root=tmp_path, output_dir=tmp_path)
        assert len(svc.recent_epubs(limit=3)) == 3


class TestEpubServiceBuildCommand:
    def test_default_command_uses_python3(self):
        svc = EpubService(repo_root=Path("/tmp"), output_dir=Path("/tmp/out"), preferred_python=None)
        cmd = svc.build_command()
        assert cmd[0] == "python3"
        assert "-m" in cmd
        assert "ttt_epub.generate_epub" in cmd

    def test_custom_python_path(self):
        svc = EpubService(repo_root=Path("/tmp"), output_dir=Path("/tmp/out"), preferred_python=["/usr/bin/python3.12"])
        cmd = svc.build_command()
        assert cmd[0] == "/usr/bin/python3.12"

    def test_override_python_path(self):
        svc = EpubService(repo_root=Path("/tmp"), output_dir=Path("/tmp/out"))
        cmd = svc.build_command(python_path="/custom/python")
        assert cmd[0] == "/custom/python"


class TestEpubServiceRunBuild:
    def test_returns_error_on_popen_failure(self, tmp_path):
        svc = EpubService(repo_root=tmp_path, output_dir=tmp_path)
        with patch("ttt_workbench.services.epub_service.subprocess.Popen", side_effect=OSError("no python")):
            result = svc.run_build()
        assert result["ok"] is False
        assert "no python" in result["stderr"]
        assert result["exit_code"] == 1


class TestEpubServiceGenerateAndReturnLatest:
    def test_success_returns_path(self, tmp_path):
        builds = tmp_path / "builds"
        builds.mkdir()
        (builds / "output.epub").write_bytes(b"epub data")
        svc = EpubService(repo_root=tmp_path, output_dir=tmp_path)
        with patch.object(svc, "run_build") as mock_build:
            mock_build.return_value = {
                "ok": True,
                "command": "python -m ttt_epub.generate_epub",
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "duration": 1.0,
                "latest_epub": str(builds / "output.epub"),
            }
            success, msg, path = svc.generate_and_return_latest()
        assert success is True
        assert path is not None
        assert path.name == "output.epub"

    def test_failure_returns_message(self, tmp_path):
        svc = EpubService(repo_root=tmp_path, output_dir=tmp_path)
        with patch.object(svc, "run_build") as mock_build:
            mock_build.return_value = {
                "ok": False,
                "command": "python -m ttt_epub.generate_epub",
                "stdout": "",
                "stderr": "error detail",
                "exit_code": 1,
                "duration": 0.5,
                "latest_epub": None,
            }
            success, msg, path = svc.generate_and_return_latest()
        assert success is False
        assert "exit code 1" in msg
        assert path is None