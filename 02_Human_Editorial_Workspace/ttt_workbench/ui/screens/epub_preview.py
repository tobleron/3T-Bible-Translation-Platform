from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class EpubPreviewScreenMixin:
    """Mixin providing EPUB Preview screen rendering."""

    def epub_preview_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "EPUB_PREVIEW":
            return busy_prefix + ["Generate and inspect the latest EPUB output from committed files."]
        return []

    def render_epub_preview_body(self):
        output_dir = self.paths.repo_root / "03_EPUB_Production"
        outputs = sorted(output_dir.glob("*.epub"), key=lambda path: path.stat().st_mtime, reverse=True)[:3]
        lines = ["Committed JSON only is used for EPUB generation."]
        if outputs:
            lines.append("")
            lines.append("Recent EPUB files:")
            lines.extend(f"- {path.name}" for path in outputs)
        return [self.line_block(lines)]
