from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp

try:
    from prompt_toolkit import Application
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.formatted_text import ANSI, to_formatted_text
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.document import Document
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import ConditionalContainer, Float, FloatContainer, HSplit, VSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.widgets import Box, Frame, TextArea
except ImportError:  # pragma: no cover
    Application = None
    Condition = None
    ANSI = None
    to_formatted_text = None
    FileHistory = None
    Document = None
    KeyBindings = None
    Layout = None
    ConditionalContainer = None
    Float = None
    FloatContainer = None
    HSplit = None
    VSplit = None
    Window = None
    FormattedTextControl = None
    Dimension = None
    Box = None
    Frame = None
    TextArea = None

from rich.align import Align
from rich.box import ROUNDED
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class LayoutBuilderMixin:
    """Mixin providing fullscreen UI layout, rendering, and display helpers."""

    def transcript_placeholder_lines(self: WorkbenchApp) -> list[str]:
        if self.state.book and self.state.chapter and self.state.chunk_start and self.state.chunk_end:
            return [
                f"Ready: {self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}",
                "Type / for commands.",
            ]
        return [
            "Ready.",
            "Type / for commands.",
            "Use /open Matthew 1 to begin.",
        ]

    def refresh_transcript_area(self: WorkbenchApp) -> None:
        if self.transcript_area is None:
            return
        if self.transcript_entries:
            text = "\n\n".join(self.transcript_entries)
            cursor = len(text)
        else:
            text = "\n".join(self.transcript_placeholder_lines())
            cursor = 0
        self.transcript_area.buffer.set_document(Document(text=text, cursor_position=cursor), bypass_readonly=True)
        if self.application is not None:
            self.application.invalidate()

    def scroll_transcript(self: WorkbenchApp, direction: int, *, lines: int = 12) -> None:
        if self.transcript_area is None or not self.transcript_area.buffer.text:
            return
        document = self.transcript_area.buffer.document
        total_lines = max(1, document.line_count)
        current_row = document.cursor_position_row
        target_row = max(0, min(total_lines - 1, current_row + (direction * lines)))
        target_col = min(document.cursor_position_col, len(document.lines[target_row]))
        position = document.translate_row_col_to_index(target_row, target_col)
        self.transcript_area.buffer.cursor_position = position
        if self.application is not None:
            self.application.invalidate()

    def palette_visible(self: WorkbenchApp) -> bool:
        return self.input_area is not None and self.input_area.text.startswith("/") and " " not in self.input_area.text

    def palette_has_exact_match(self: WorkbenchApp) -> bool:
        if self.input_area is None:
            return False
        text = self.input_area.text.strip()
        if not text.startswith("/") or " " in text:
            return False
        return text[1:].lower() in self.command_specs

    def palette_candidates(self: WorkbenchApp) -> list[tuple[str, dict[str, object]]]:
        if self.input_area is None:
            return []
        prefix = self.input_area.text[1:].lower() if self.input_area.text.startswith("/") else ""
        results = [(name, spec) for name, spec in self.command_specs.items() if not prefix or name.startswith(prefix)]
        results.sort(key=lambda item: item[0])
        if self.palette_index >= len(results):
            self.palette_index = max(0, len(results) - 1)
        return results

    def fit_palette_text(self: WorkbenchApp, text: str, width: int) -> str:
        if width < 4:
            return text[:width]
        if len(text) <= width:
            return text
        return text[: width - 1].rstrip() + "\u2026"

    def command_palette_widths(self: WorkbenchApp) -> tuple[int, int]:
        total = shutil.get_terminal_size(fallback=(100, 30)).columns
        available = max(48, total - 14)
        display_width = min(40, max(20, available // 2))
        meta_width = max(18, available - display_width - 4)
        return display_width, meta_width

    def command_palette_fragments(self: WorkbenchApp):
        candidates = self.palette_candidates()
        display_width, meta_width = self.command_palette_widths()
        visible_rows = 8
        if not candidates:
            return [(self.theme.COLORS["fg1"], "No matching commands.")]
        start = min(max(self.palette_index - visible_rows // 2, 0), max(0, len(candidates) - visible_rows))
        end = min(len(candidates), start + visible_rows)
        fragments: list[tuple[str, str]] = []
        for idx in range(start, end):
            name, spec = candidates[idx]
            selected = idx == self.palette_index
            syntax = self.fit_palette_text(str(spec["display"]), display_width)
            desc = self.fit_palette_text(str(spec["desc"]), meta_width)
            style = f"fg:{self.theme.COLORS['bg0_h']} bg:{self.theme.COLORS['blue']}" if selected else f"fg:{self.theme.COLORS['fg1']} bg:{self.theme.COLORS['bg1']}"
            meta_style = style if selected else f"fg:{self.theme.COLORS['bg3']} bg:{self.theme.COLORS['bg1']}"
            prefix = "\u203a " if selected else "  "
            line = prefix + syntax.ljust(display_width + 2)
            if fragments:
                fragments.append(("", "\n"))
            fragments.append((style, line))
            fragments.append((meta_style, desc))
        return fragments

    def select_palette_command(self: WorkbenchApp) -> None:
        candidates = self.palette_candidates()
        if not candidates or self.input_area is None:
            return
        name, _ = candidates[self.palette_index]
        self.input_area.buffer.text = f"/{name} "
        self.input_area.buffer.cursor_position = len(self.input_area.buffer.text)
        if self.application is not None:
            self.application.invalidate()

    def submit_current_input(self: WorkbenchApp) -> None:
        if self.input_area is None:
            return
        line = self.input_area.text.strip()
        if not line:
            if self.state.mode == "CHAT":
                self.activate_selected_menu_item()
                return
            if self.state.mode == "JUSTIFY":
                self.activate_selected_menu_item()
                return
            if self.current_screen_menu_items():
                self.activate_selected_menu_item()
            return
        self.input_area.buffer.text = ""
        self.palette_index = 0
        if self.state.mode in {"CHAT", "JUSTIFY"} and not line.startswith("/"):
            self.handle_mode_input(line)
            self.save_state()
            self.render_status()
            return
        if not line.startswith("/"):
            self.print_error("Commands start with '/'. Use / for the command palette.")
            self.render_status()
            return
        if line.strip() == "/":
            self.show_command_menu()
            return
        self.echo_command(line)
        self.handle_command(line[1:])
        if self.exit_requested:
            return
        self.save_state()
        self.render_status()

    def prompt_label_fragments(self: WorkbenchApp):
        mode = self.state.mode.upper()
        color = {"COMMAND": "#83a598", "CHAT": "#b8bb26", "JUSTIFY": "#fabd2f"}.get(mode, "#8ec07c")
        return [("bold " + color, f"{mode.lower()}> ")]

    def badge_fragments(self: WorkbenchApp, label: str, value: str, accent: str) -> list[tuple[str, str]]:
        accent_hex = self.theme.COLORS.get(accent, self.theme.COLORS["blue"])
        return [
            (f"bold fg:{self.theme.COLORS['bg0_h']} bg:{accent_hex}", f"  {label}  "),
            (f"fg:{self.theme.COLORS['fg0']} bg:{self.theme.COLORS['bg1']}", f"  {value}  "),
        ]

    def header_fragments(self: WorkbenchApp):
        fragments = [(f"bold {self.theme.COLORS['orange']}", "TTT Workbench")]
        badges = [
            [("", "   ")],
            self.badge_fragments("VERSION", self.app_version, "orange"),
            [("", "  ")],
            self.badge_fragments("MODE", self.state.mode, {"COMMAND": "blue", "CHAT": "green", "JUSTIFY": "yellow"}.get(self.state.mode, "aqua")),
            [("", "  ")],
            self.badge_fragments("MODEL", self.model_label, "purple"),
        ]
        for part in badges:
            fragments.extend(part)
        return fragments

    def status_fragments(self: WorkbenchApp):
        mode_color = {"COMMAND": "blue", "CHAT": "green", "JUSTIFY": "yellow"}.get(self.state.mode, "aqua")
        mode_hex = self.theme.COLORS.get(mode_color, self.theme.COLORS["blue"])
        return [(f"bold {mode_hex}", f"  \u25cf {self.state.mode.lower()}  ")]

    def footer_fragments(self: WorkbenchApp):
        return self.theme.toolbar_message()

    def dashboard_widths(self: WorkbenchApp) -> tuple[int, int]:
        total = shutil.get_terminal_size(fallback=(120, 36)).columns
        history_width = 36 if self.state.history_panel_open else 0
        workspace_width = max(60, total - history_width - 8)
        return workspace_width, history_width

    def workspace_fragments(self: WorkbenchApp):
        width, _ = self.dashboard_widths()
        ansi = self.theme.render_ansi(self.build_workspace_renderable(), width=width)
        return to_formatted_text(ANSI(ansi))

    def workspace_debug_text(self: WorkbenchApp) -> str:
        width, _ = self.dashboard_widths()
        return self.theme.render_text(self.build_workspace_renderable(), width=width)

    def history_fragments(self: WorkbenchApp):
        _, history_width = self.dashboard_widths()
        ansi = self.theme.render_ansi(self.build_history_renderable(), width=max(28, history_width - 2))
        return to_formatted_text(ANSI(ansi))

    def input_title(self: WorkbenchApp) -> str:
        return "Prompt"

    def screen_accent(self: WorkbenchApp) -> str:
        return {
            "HOME": "orange",
            "NEW_SESSION_TESTAMENT": "aqua",
            "NEW_SESSION_BOOK": "blue",
            "NEW_SESSION_CHAPTER": "blue",
            "CHUNK_PICKER": "blue",
            "STUDY": "aqua",
            "CHAT": "green",
            "REVIEW": "yellow",
            "JUSTIFY": "yellow",
            "COMMIT_PREVIEW": "orange",
            "EPUB_PREVIEW": "purple",
            "TOOLS": "purple",
        }.get(self.state.screen, "blue")

    def stage_title(self: WorkbenchApp) -> str:
        return {
            "HOME": "Home",
            "NEW_SESSION_TESTAMENT": "Choose Testament",
            "NEW_SESSION_BOOK": "Choose Book",
            "NEW_SESSION_CHAPTER": "Choose Chapter",
            "CHUNK_PICKER": "Choose Chunk",
            "STUDY": "Study Chunk",
            "CHAT": "Draft With Qwen",
            "REVIEW": "Editorial Review",
            "JUSTIFY": "Justification",
            "COMMIT_PREVIEW": "Commit Preview",
            "EPUB_PREVIEW": "EPUB Preview",
            "TOOLS": "Tools",
        }.get(self.state.screen, "Workspace")

    def stage_summary_lines(self: WorkbenchApp) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "HOME":
            lines = ["Start a guided translation session or resume the last open chunk."]
            if self.resume_available():
                lines.append(f"Resume available: {self.current_chunk_label()}")
            return busy_prefix + lines
        if screen == "NEW_SESSION_TESTAMENT":
            return busy_prefix + ["Choose which testament workflow to enter for this session."]
        if screen == "NEW_SESSION_BOOK":
            testament = (self.state.wizard_testament or "new").title()
            return busy_prefix + [f"{testament} Testament selected.", "Choose a book from the available JSON targets."]
        if screen == "NEW_SESSION_CHAPTER":
            return busy_prefix + [f"Book: {self.state.wizard_book or '[none]'}", "Choose the chapter you want to segment into chunks."]
        if screen == "CHUNK_PICKER":
            return busy_prefix + [
                f"Chapter: {self.state.wizard_book or self.state.book} {self.state.wizard_chapter or self.state.chapter}",
                f"Suggestions loaded: {len(self.state.chunk_suggestions)}",
            ]
        if screen == "STUDY":
            return busy_prefix + [f"Chunk: {self.current_chunk_label()}", "Review the deterministic source study before drafting."]
        if screen == "CHAT":
            return busy_prefix + [f"Chunk: {self.current_chunk_label()}", "Type plain text below to talk to Qwen, or press Enter on an action when the input is empty."]
        if screen == "REVIEW":
            return busy_prefix + [f"Chunk: {self.current_chunk_label()}", "Review the editorial verdict and stage what is ready."]
        if screen == "JUSTIFY":
            draft = self.state.justify_draft
            return busy_prefix + [f"Drafting justification for verses {draft.start_verse}-{draft.end_verse}." if draft else "No active justification draft."]
        if screen == "COMMIT_PREVIEW":
            return busy_prefix + ["Inspect pending writes before committing JSON changes to disk."]
        if screen == "EPUB_PREVIEW":
            return busy_prefix + ["Generate and inspect the latest EPUB output from committed files."]
        if screen == "TOOLS":
            return busy_prefix + ["Advanced actions and reference views live here."]
        return []

    def line_block(self: WorkbenchApp, lines: list[str]) -> Text:
        text = Text()
        for idx, line in enumerate(lines):
            if idx:
                text.append("\n")
            if line.startswith("Impact:"):
                text.append(line, style=f"bold {self.theme.COLORS['yellow']}")
            elif line.endswith("Study \u2500\u2500") or line.startswith("Primary:"):
                text.append(line, style=f"bold {self.theme.COLORS['aqua']}")
            elif line.strip().startswith("Next:"):
                text.append(line, style=self.theme.COLORS["green"])
            elif line.startswith("Scope:") or line.startswith("Chunk:") or line.startswith("Book:") or line.startswith("Chapter:"):
                text.append(line, style=f"bold {self.theme.COLORS['fg0']}")
            else:
                text.append(line, style=self.theme.COLORS["fg1"])
        return text

    def menu_table(self: WorkbenchApp, items: list[dict[str, str]]) -> Table:
        self.normalize_menu_index()
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=4, no_wrap=True)
        table.add_column(ratio=2, min_width=16)
        table.add_column(ratio=3, min_width=24)
        for index, item in enumerate(items):
            selected = index == self.state.menu_index
            num_style = f"bold {self.theme.COLORS['bg0_h']} on {self.theme.COLORS['blue']}" if selected else self.theme.COLORS["blue"]
            label_style = f"bold {self.theme.COLORS['fg0']} on {self.theme.COLORS['bg1']}" if selected else f"bold {self.theme.COLORS['fg0']}"
            desc_style = f"{self.theme.COLORS['fg1']} on {self.theme.COLORS['bg1']}" if selected else self.theme.COLORS["fg3"]
            row_style = f"bg:{self.theme.COLORS['bg0_h']}" if selected else ""
            pointer = "\u203a" if selected else f"{index + 1}."
            table.add_row(
                Text(pointer, style=num_style, end=row_style),
                Text(item["label"], style=label_style, end=row_style),
                Text(item["desc"], style=desc_style, end=row_style),
            )
        return table

    def main_body_renderable(self: WorkbenchApp):
        screen = self.state.screen
        accent = self.screen_accent()

        # Route to screen-specific renderers when available
        if screen in ("HOME", "NEW_SESSION_TESTAMENT", "NEW_SESSION_BOOK", "NEW_SESSION_CHAPTER"):
            screen_blocks = self.render_home_body()
        elif screen == "CHUNK_PICKER":
            screen_blocks = self.render_chunk_picker_body()
        elif screen == "STUDY":
            screen_blocks = self.render_study_body()
        elif screen == "CHAT":
            screen_blocks = self.render_chat_body()
        elif screen == "REVIEW":
            screen_blocks = self.render_review_body()
        elif screen == "JUSTIFY":
            screen_blocks = self.render_justify_body()
        elif screen == "COMMIT_PREVIEW":
            screen_blocks = self.render_commit_preview_body()
        elif screen == "EPUB_PREVIEW":
            screen_blocks = self.render_epub_preview_body()
        elif screen == "TOOLS":
            screen_blocks = self.render_tools_body()
        else:
            screen_blocks = []

        summary_lines = self.stage_summary_lines()
        stage_parts: list[object] = []
        if summary_lines:
            stage_parts.append(self.line_block(summary_lines))
        if screen_blocks:
            if stage_parts:
                stage_parts.append(Text(""))
            stage_parts.extend(screen_blocks)
        if not stage_parts:
            stage_parts.append(Text("No content yet.", style=self.theme.COLORS["fg3"]))
        stage_body = Group(*stage_parts)
        blocks: list[object] = [
            Panel(
                stage_body,
                title=self.stage_title(),
                title_align="left",
                border_style=self.theme.COLORS[accent],
                padding=(1, 2),
                box=ROUNDED,
                expand=True,
            )
        ]
        items = self.current_screen_menu_items()
        if items:
            blocks.append(
                Panel(
                    self.menu_table(items),
                    title="Actions",
                    title_align="left",
                    border_style=self.theme.COLORS["orange"],
                    padding=(0, 1),
                    box=ROUNDED,
                    expand=True,
                )
            )
        for entry in self.history_entries[-6:]:
            blocks.append(
                Panel(
                    Text(entry["body"], style=self.theme.COLORS["fg1"]),
                    title=entry["title"],
                    title_align="left",
                    border_style=self.theme.COLORS.get(entry["accent"], self.theme.COLORS["aqua"]),
                    padding=(0, 1),
                    box=ROUNDED,
                    expand=True,
                )
            )
        return Group(*blocks)

    def build_workspace_renderable(self: WorkbenchApp):
        return Align.left(self.main_body_renderable())

    def build_history_renderable(self: WorkbenchApp):
        return Align.left(Text("", style=self.theme.COLORS["fg3"]))

    def workspace_line_count(self: WorkbenchApp) -> int:
        width, _ = self.dashboard_widths()
        rendered = self.theme.render_text(self.build_workspace_renderable(), width=width)
        return max(1, len(rendered.splitlines()))

    def adjust_workspace_scroll(self: WorkbenchApp, delta: int) -> None:
        total_lines = self.workspace_line_count()
        max_scroll = max(0, total_lines - 12)
        self.workspace_scroll = max(0, min(max_scroll, self.workspace_scroll + delta))
        self.flush_ui()

    def set_workspace_scroll(self: WorkbenchApp, position: int) -> None:
        total_lines = self.workspace_line_count()
        max_scroll = max(0, total_lines - 12)
        self.workspace_scroll = max(0, min(max_scroll, position))
        self.flush_ui()

    def infer_history_accent(self: WorkbenchApp, title: str) -> str:
        lowered = title.lower()
        if "error" in lowered:
            return "red"
        if "working" in lowered:
            return "purple"
        if "done" in lowered or "complete" in lowered:
            return "green"
        if "review" in lowered or "study" in lowered:
            return "yellow"
        if "command" in lowered:
            return "blue"
        return "aqua"

    def emit(self: WorkbenchApp, renderable: object) -> None:
        if self.application is not None:
            title = "Notice"
            body = self.theme.render_transcript_text(renderable, width=90).strip()
            accent = "aqua"
            if isinstance(renderable, Panel):
                title = str(renderable.title or "Notice").strip() or "Notice"
                body = self.theme.render_transcript_text(renderable, width=90).strip()
                accent = self.infer_history_accent(title)
            if body:
                self.history_entries.append({"title": title, "body": body, "accent": accent})
                if len(self.history_entries) > 120:
                    self.history_entries = self.history_entries[-120:]
            self.flush_ui()
            return
        self.theme.print(renderable)

    def flush_ui(self: WorkbenchApp) -> None:
        if self.application is None:
            return
        try:
            self.application.invalidate()
            if hasattr(self.application, "_redraw"):
                self.application._redraw()
        except Exception:
            return

    def render_status(self: WorkbenchApp) -> None:
        self.flush_ui()

    def show_command_menu(self: WorkbenchApp) -> None:
        if self.input_area is not None:
            self.input_area.buffer.text = "/"
            self.input_area.buffer.cursor_position = len(self.input_area.buffer.text)
            self.palette_index = 0
            self.flush_ui()
            return
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(
            style=f"bold {self.theme.COLORS['fg0']}",
            ratio=2,
            min_width=30,
            no_wrap=True,
        )
        table.add_column(style=self.theme.COLORS["fg3"], ratio=3, min_width=24)
        for _, spec in self.command_specs.items():
            table.add_row(str(spec["display"]), str(spec["desc"]))
        body = Group(
            Text("Use /help <command> for details.", style=self.theme.COLORS["fg3"]),
            Text(""),
            table,
        )
        self.emit(
            Panel(
                body,
                title="Commands",
                title_align="left",
                border_style=self.theme.COLORS["yellow"],
                padding=(1, 2),
                box=ROUNDED,
                expand=True,
            )
        )

    def echo_command(self: WorkbenchApp, command_line: str) -> None:
        self.emit(self.theme.panel("Command", [command_line], accent="blue"))
        self.flush_ui()

    def build_fullscreen(self: WorkbenchApp, *, input=None, output=None) -> None:
        history = FileHistory(str(self.history_path))
        self.state.mode = "COMMAND"
        self.state.screen = "HOME"
        self.header_control = FormattedTextControl(self.header_fragments, focusable=False)
        self.workspace_control = FormattedTextControl(self.workspace_fragments, focusable=False, show_cursor=False)
        self.history_control = FormattedTextControl(self.history_fragments, focusable=False, show_cursor=False)
        self.palette_control = FormattedTextControl(self.command_palette_fragments, focusable=False, show_cursor=False)
        self.input_area = TextArea(
            text="",
            multiline=False,
            history=history,
            wrap_lines=False,
            scrollbar=False,
            style=f"bg:{self.theme.COLORS['bg0_h']} {self.theme.COLORS['fg0']}",
        )
        self.input_area.buffer.on_text_changed += lambda _: self.flush_ui()

        palette_filter = Condition(lambda: self.palette_visible())
        bindings = KeyBindings()

        @bindings.add("/")
        def _(event) -> None:
            buffer = self.input_area.buffer
            buffer.insert_text("/")
            self.palette_index = 0
            event.app.invalidate()

        @bindings.add("c-space")
        def _(event) -> None:
            buffer = self.input_area.buffer
            if not buffer.text:
                buffer.insert_text("/")
            self.palette_index = 0
            event.app.invalidate()

        @bindings.add("f2")
        def _(event) -> None:
            return

        @bindings.add("down", filter=palette_filter)
        def _(event) -> None:
            candidates = self.palette_candidates()
            if candidates:
                self.palette_index = min(self.palette_index + 1, len(candidates) - 1)
                event.app.invalidate()

        @bindings.add("up", filter=palette_filter)
        def _(event) -> None:
            candidates = self.palette_candidates()
            if candidates:
                self.palette_index = max(self.palette_index - 1, 0)
                event.app.invalidate()

        @bindings.add("down")
        def _(event) -> None:
            if self.input_area.buffer.text:
                return
            self.move_menu_selection(1)

        @bindings.add("up")
        def _(event) -> None:
            if self.input_area.buffer.text:
                return
            self.move_menu_selection(-1)

        @bindings.add("tab", filter=palette_filter)
        def _(event) -> None:
            self.select_palette_command()

        @bindings.add("enter")
        def _(event) -> None:
            if self.palette_visible() and not self.palette_has_exact_match():
                self.select_palette_command()
                return
            self.submit_current_input()

        @bindings.add("escape")
        def _(event) -> None:
            if self.palette_visible():
                self.input_area.buffer.text = ""
                self.palette_index = 0
                event.app.invalidate()
                return
            if self.input_area.buffer.text:
                self.input_area.buffer.text = ""
                event.app.invalidate()
                return
            self.back_screen()
            event.app.invalidate()

        @bindings.add("c-c")
        def _(event) -> None:
            self.cmd_quit([])

        @bindings.add("pageup")
        def _(event) -> None:
            self.adjust_workspace_scroll(-12)

        @bindings.add("pagedown")
        def _(event) -> None:
            self.adjust_workspace_scroll(12)

        @bindings.add("home")
        def _(event) -> None:
            if self.input_area.buffer.text:
                return
            self.set_workspace_scroll(0)

        @bindings.add("end")
        def _(event) -> None:
            if self.input_area.buffer.text:
                return
            self.set_workspace_scroll(10**9)

        header_window = Window(
            self.header_control,
            height=1,
            dont_extend_height=True,
            style=f"bg:{self.theme.COLORS['bg0_h']}",
        )
        header_frame = Frame(header_window, style=f"bg:{self.theme.COLORS['bg0_h']}")
        self.workspace_window = Window(
            self.workspace_control,
            wrap_lines=True,
            always_hide_cursor=True,
            get_vertical_scroll=lambda w: self.workspace_scroll,
        )
        workspace_frame = Frame(self.workspace_window, title="Workspace", style=f"bg:{self.theme.COLORS['bg0']}")
        prompt_label = Window(
            FormattedTextControl(self.prompt_label_fragments),
            width=10,
            dont_extend_width=True,
        )
        input_row = VSplit([prompt_label, self.input_area], padding=1)
        input_window = Frame(input_row, title=self.input_title(), style=f"bg:{self.theme.COLORS['bg0_h']}")
        palette_frame = Frame(
            HSplit([Window(self.palette_control, height=Dimension(min=8, max=8), dont_extend_height=True)]),
            title="Commands",
            width=Dimension(preferred=94, max=108),
            style=f"bg:{self.theme.COLORS['bg0_h']}",
        )
        overlay = ConditionalContainer(
            content=HSplit([Window(), VSplit([Window(), palette_frame, Window()]), Window()]),
            filter=palette_filter,
        )
        body = HSplit(
            [
                header_frame,
                workspace_frame,
                input_window,
            ]
        )
        root = FloatContainer(content=body, floats=[Float(content=overlay)])
        self.application = Application(
            layout=Layout(root, focused_element=self.input_area),
            full_screen=True,
            style=self.theme.prompt_style(),
            key_bindings=bindings,
            mouse_support=True,
            input=input,
            output=output,
        )
        self.flush_ui()

    def run_fullscreen(self: WorkbenchApp, *, input=None, output=None) -> None:
        self.build_fullscreen(input=input, output=output)
        self.application.run()

    def run_legacy(self: WorkbenchApp) -> None:
        self.state.mode = "COMMAND"
        header_lines = [
            f"Version: {self.app_version}",
            f"Model: {self.model_label}",
            "",
            "Use / or /help to list commands.",
            "Start with /open Matthew 1 or /open Matthew 1:1-17.",
        ]
        if self.state.book and self.state.chapter and self.state.chunk_start and self.state.chunk_end:
            header_lines.append(
                f"Resume available: {self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}"
            )
        self.emit(self.theme.panel("TTT Workbench", header_lines, accent="orange"))
        while True:
            try:
                line = input(f"{self.state.mode.lower()}> ")
            except (EOFError, KeyboardInterrupt):
                self.emit("")
                self.cmd_quit([])
                return
            if not line.strip():
                continue
            if self.state.mode in {"CHAT", "JUSTIFY"} and not line.startswith("/"):
                self.handle_mode_input(line)
                self.save_state()
                continue
            if not line.startswith("/"):
                self.print_error("Commands start with '/'. Use /help for syntax.")
                continue
            if line.strip() == "/":
                self.show_command_menu()
                self.save_state()
                continue
            self.echo_command(line)
            self.handle_command(line[1:])
            if self.exit_requested:
                return
            self.save_state()

    def run(self: WorkbenchApp) -> None:
        if (
            os.environ.get("TTT_FULLSCREEN") == "1"
            and all(item is not None for item in (Application, Condition, Layout, FloatContainer, Float, HSplit, VSplit, Window, FormattedTextControl, Dimension, TextArea, Frame, Box, FileHistory, KeyBindings))
        ):
            self.run_fullscreen()
            return
        self.run_legacy()
