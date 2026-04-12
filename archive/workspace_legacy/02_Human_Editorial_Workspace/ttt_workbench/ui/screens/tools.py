from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ToolsScreenMixin:
    """Mixin providing Tools screen rendering."""

    def tools_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "TOOLS":
            return busy_prefix + ["Advanced actions and reference views live here."]
        return []

    def render_tools_body(self):
        return [self.line_block(["Use the actions below for advanced views.", "Slash commands remain available everywhere via / ."])]
