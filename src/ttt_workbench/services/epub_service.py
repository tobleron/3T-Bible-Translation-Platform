"""EPUB generation service.

Handles building, running, and querying EPUB output files.
Extracted from BrowserWorkbench to reduce controller sprawl.
"""

from __future__ import annotations

import subprocess
import time
import threading
from pathlib import Path
from typing import Any

__all__ = ["EpubService"]


class EpubService:
    """Manages EPUB generation subprocess execution and result retrieval."""

    def __init__(self, *, repo_root: Path, output_dir: Path, preferred_python: list[str] | None = None) -> None:
        self._repo_root = repo_root
        self._output_dir = output_dir
        self._preferred_python = preferred_python

    @property
    def builds_dir(self) -> Path:
        return self._output_dir / "builds"

    def recent_epubs(self, limit: int = 5) -> list[Path]:
        """Return the most recent EPUB files, newest first."""
        builds = self.builds_dir
        if not builds.is_dir():
            return []
        return sorted(
            builds.glob("*.epub"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:limit]

    def build_command(self, python_path: str | None = None) -> list[str]:
        """Return the EPUB generation subprocess command."""
        python = python_path or (self._preferred_python[0] if self._preferred_python else "python3")
        return [
            python,
            "-m", "ttt_epub.generate_epub",
            "--md",
            "--txt",
        ]

    def run_build(
        self,
        *,
        cancel_event: threading.Event | None = None,
        python_path: str | None = None,
    ) -> dict[str, Any]:
        """Run EPUB generation with optional cancellation support.

        Returns a dict with ok, stdout, stderr, exit_code, duration, latest_epub.
        """
        work_dir = self._repo_root
        cmd = self.build_command(python_path=python_path)
        started_at = time.monotonic()
        try:
            proc = subprocess.Popen(cmd, cwd=work_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception as exc:
            return {
                "ok": False,
                "command": " ".join(cmd),
                "stdout": "",
                "stderr": str(exc),
                "exit_code": 1,
                "duration": time.monotonic() - started_at,
                "latest_epub": None,
            }
        try:
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    return {
                        "ok": False,
                        "command": " ".join(cmd),
                        "stdout": (proc.stdout.read() if proc.stdout else ""),
                        "stderr": "Cancelled by user.",
                        "exit_code": -1,
                        "duration": time.monotonic() - started_at,
                        "latest_epub": None,
                    }
                time.sleep(0.2)
            stdout, stderr = proc.communicate()
        except Exception as exc:
            proc.kill()
            stdout, stderr = proc.communicate()
            return {
                "ok": False,
                "command": " ".join(cmd),
                "stdout": stdout or "",
                "stderr": str(exc),
                "exit_code": proc.returncode or 1,
                "duration": time.monotonic() - started_at,
                "latest_epub": None,
            }
        latest = self.recent_epubs()
        return {
            "ok": proc.returncode == 0,
            "command": " ".join(cmd),
            "stdout": stdout or "",
            "stderr": stderr or "",
            "exit_code": proc.returncode,
            "duration": time.monotonic() - started_at,
            "latest_epub": str(latest[0]) if latest else None,
        }

    def generate_and_return_latest(self, *, cancel_event: threading.Event | None = None) -> tuple[bool, str, Path | None]:
        """Generate EPUB and return (success, message, latest_epub_path)."""
        result = self.run_build(cancel_event=cancel_event)
        if result["ok"]:
            latest_path = Path(result["latest_epub"]) if result["latest_epub"] else None
            return True, "EPUB generated successfully.", latest_path
        return False, f"EPUB generation failed with exit code {result['exit_code']}.\n{result['stderr']}", None