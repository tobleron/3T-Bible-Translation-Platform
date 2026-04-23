from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp


class EpubCommandsMixin:
    """Mixin providing /epub-gen command."""

    def cmd_epub_gen(self: WorkbenchApp, args: list[str]) -> None:
        self.set_screen("EPUB_PREVIEW", mode="COMMAND")
        output_dir = self.paths.output_dir / "builds"
        if (
            self.state.pending_verse_updates
            or self.state.pending_title_updates
            or self.state.pending_justification_updates
        ):
            self.notify(
                "There are staged but uncommitted changes. "
                "/epub-gen uses committed JSON on disk only."
            )
        self.notify_busy("Generating EPUB output from committed JSON...", label="epub-gen")
        result = self._run_epub_build()
        duration = result["duration"]
        stdout = result["stdout"].strip()
        stderr = result["stderr"].strip()
        outputs = sorted(
            output_dir.glob("*.epub"), key=lambda path: path.stat().st_mtime, reverse=True
        )[:2]
        outputs += sorted(
            output_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True
        )[:2]
        outputs += sorted(
            output_dir.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True
        )[:2]
        lines = [
            f"Command: {result['command']}",
            f"Exit code: {result['exit_code']}",
            f"Duration: {duration:.1f}s",
        ]
        if stdout:
            lines.extend(stdout.splitlines()[:12])
        if stderr:
            lines.append("stderr:")
            lines.extend(stderr.splitlines()[:12])
        combined = "\n".join(part for part in (stdout, stderr) if part)
        if "ModuleNotFoundError" in combined:
            missing = ""
            for line in combined.splitlines():
                if "ModuleNotFoundError" in line and "No module named" in line:
                    missing = line.split("No module named", 1)[1].strip().strip('""')
                    break
            if missing:
                lines.append(f"Missing Python package: {missing}")
            lines.append(
                "Install the EPUB builder dependencies listed in "
                "resources/assets/INSTALL.txt before rerunning /epub-gen."
            )
        if outputs:
            lines.append("Recent output files:")
            lines.extend(str(path) for path in outputs)
        accent = "green" if result["ok"] else "red"
        if result["ok"]:
            self.notify_done(
                label="epub-gen",
                message=f"EPUB generated successfully ({duration:.1f}s)",
                duration=duration,
            )
        else:
            self.notify_error(
                label="epub-gen",
                message=f"EPUB generation failed with exit code {result['exit_code']}",
                duration=duration,
            )
        self.emit(self.theme.panel("EPUB Generation", lines, accent=accent))
