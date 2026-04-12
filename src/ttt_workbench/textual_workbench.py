from __future__ import annotations

from rich.panel import Panel
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, RichLog, Static

from .app import WorkbenchApp


class TextualController(WorkbenchApp):
    def __init__(self, ui: "TextualWorkbenchApp") -> None:
        self._textual_ui = ui
        super().__init__()

    def echo_command(self, command_line: str) -> None:
        self._textual_ui.call_from_thread(self._textual_ui.set_prompt_processing, command_line)

    def emit(self, renderable: object) -> None:
        title = "Notice"
        body = self.theme.render_transcript_text(renderable, width=96).strip()
        accent = "aqua"
        if isinstance(renderable, Panel):
            title = str(renderable.title or "Notice").strip() or "Notice"
            accent = self.infer_history_accent(title)
        if not body:
            return
        self.history_entries.append({"title": title, "body": body, "accent": accent})
        if len(self.history_entries) > 120:
            self.history_entries = self.history_entries[-120:]
        self._textual_ui.call_from_thread(
            self._textual_ui.append_activity_block, title, body, accent
        )
        self._textual_ui.call_from_thread(self._textual_ui.refresh_reference_pane)

    def flush_ui(self) -> None:
        self._textual_ui.call_from_thread(self._textual_ui.refresh_reference_pane)

    def render_status(self) -> None:
        self.flush_ui()


class TextualWorkbenchApp(App):
    CSS = """
    Screen {
        background: #0b0b0b;
        color: #ebdbb2;
    }

    #root {
        layout: vertical;
        height: 100%;
        width: 100%;
        padding: 1;
        background: #0b0b0b;
    }

    #topbar {
        height: 5;
        width: 100%;
        background: #0b0b0b;
    }

    .topbox {
        min-height: 5;
        background: #111111;
        padding: 0 2;
        content-align: left middle;
    }

    #header-main {
        width: 2fr;
        border: round #fe8019;
        margin-right: 1;
    }

    #header-status {
        width: 1fr;
        border: round #83a598;
    }

    #main {
        height: 1fr;
        margin-top: 1;
    }

    .pane {
        background: #111111;
        border: round #504945;
        padding: 0 1 1 1;
    }

    #activity-pane {
        width: 1fr;
        min-width: 60;
        margin-right: 1;
        border: round #83a598;
    }

    #reference-pane {
        width: 1fr;
        min-width: 40;
        border: round #8ec07c;
    }

    .pane-label {
        height: 1;
        color: #fbf1c7;
        text-style: bold;
        margin: 0 0 1 0;
    }

    #activity-log {
        height: 1fr;
        background: #111111;
        scrollbar-background: #111111;
        scrollbar-color: #665c54;
        scrollbar-color-active: #83a598;
        scrollbar-color-hover: #83a598;
    }

    #reference-scroll {
        height: 1fr;
        background: #111111;
        scrollbar-background: #111111;
        scrollbar-color: #665c54;
        scrollbar-color-active: #8ec07c;
        scrollbar-color-hover: #8ec07c;
    }

    .ref-block {
        margin-bottom: 1;
    }

    #prompt-row {
        height: 3;
        margin-top: 1;
        border: round #83a598;
        background: #111111;
        padding: 0 1;
        layout: horizontal;
        align-vertical: middle;
    }

    #prompt-label {
        width: 14;
        color: #b8bb26;
        text-style: bold;
    }

    #command-input {
        border: none;
        background: #111111;
        color: #fbf1c7;
    }

    #command-input.-disabled {
        color: #928374;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.controller = TextualController(self)
        self._status_title = "Ready"
        self._status_body = "Use /open <book> <chapter> to begin."
        self._status_accent = "aqua"

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            with Horizontal(id="topbar"):
                yield Static(id="header-main", classes="topbox")
                yield Static(id="header-status", classes="topbox")
            with Horizontal(id="main"):
                with Vertical(id="activity-pane", classes="pane"):
                    yield Static("Output", classes="pane-label")
                    yield RichLog(id="activity-log", wrap=True, markup=True, highlight=False)
                with Vertical(id="reference-pane", classes="pane"):
                    yield Static("Material", classes="pane-label")
                    with VerticalScroll(id="reference-scroll"):
                        yield Static(id="ref-source", classes="ref-block")
                        yield Static(id="ref-draft", classes="ref-block")
                        yield Static(id="ref-next", classes="ref-block")
            with Horizontal(id="prompt-row"):
                yield Static("command>", id="prompt-label")
                yield Input(placeholder="/open Matthew 1", id="command-input")

    def on_mount(self) -> None:
        self.refresh_header()
        self.append_activity_block(
            "Ready",
            "Use / or /help to list commands.\nStart with /open Matthew 1 or /open Matthew 1:1-17.",
            "orange",
        )
        self.refresh_reference_pane()
        self.query_one("#command-input", Input).focus()

    def update_prompt_label(self) -> None:
        input_widget = self.query_one("#command-input", Input)
        if input_widget.disabled:
            self.query_one("#prompt-label", Static).update("working…")
        else:
            mode = self.controller.state.mode.lower()
            self.query_one("#prompt-label", Static).update(f"{mode}>")
        self.refresh_header()

    def refresh_header(self) -> None:
        c = self.controller
        if c.state.book and c.state.chapter and c.state.chunk_start and c.state.chunk_end:
            current = (
                f"{c.state.screen}  {c.state.book} {c.state.chapter}:"
                f"{c.state.chunk_start}-{c.state.chunk_end}"
            )
            if c.state.focus_start and c.state.focus_end:
                current += f"  FOCUS {c.state.focus_start}-{c.state.focus_end}"
        elif c.state.book and c.state.chapter:
            current = f"{c.state.screen}  {c.state.book} {c.state.chapter}"
        else:
            current = c.state.screen
        header = "\n".join(
            [
                f"TTT Workbench   v{c.app_version}   {c.state.mode}   {c.model_label}",
                f"Current  {current}",
            ]
        )
        status = "\n".join([self._status_title, self._status_body])
        self.query_one("#header-main", Static).update(header)
        self.query_one("#header-status", Static).update(status)

    def block_panel(self, title: str, body: str, accent: str) -> Panel:
        return Panel(
            Text(body, style="#ebdbb2"),
            title=title,
            title_align="left",
            border_style=self.controller.theme.COLORS.get(accent, self.controller.theme.COLORS["aqua"]),
            padding=(1, 2),
            expand=True,
        )

    def append_activity_block(self, title: str, body: str, accent: str = "aqua") -> None:
        log = self.query_one("#activity-log", RichLog)
        log.write(self.block_panel(title, body, accent))
        self.set_status(title, body, accent)
        self.update_prompt_label()

    def set_status(self, title: str, body: str, accent: str = "aqua") -> None:
        first_line = (body.splitlines()[0].strip() if body else "").strip()
        self._status_title = title.strip() or "Status"
        self._status_body = first_line or "Idle."
        self._status_accent = accent
        self.refresh_header()

    def set_ref_block(self, widget_id: str, title: str, body: str, accent: str) -> None:
        self.query_one(widget_id, Static).update(self.block_panel(title, body, accent))

    def refresh_reference_pane(self) -> None:
        c = self.controller
        source_body = "Open a chunk to load study material."
        if c.state.book and c.state.chapter and c.state.chunk_start and c.state.chunk_end:
            start = c.state.focus_start or c.state.chunk_start
            end = c.state.focus_end or c.state.chunk_end
            if c.lexical_repo.available():
                if c.testament() == "old":
                    lines = c._ot_study_lines(start, end)
                else:
                    lines = c._nt_study_lines(start, end)
                source_body = "\n".join(lines[:22])
        self.set_ref_block("#ref-source", "Study Material", source_body, "aqua")

        draft_body = "No draft yet."
        if c.state.book and c.state.chapter and c.state.chunk_start and c.state.chunk_end:
            draft_lines = []
            if c.state.draft_title:
                draft_lines.append(f"Title: {c.state.draft_title}")
                draft_lines.append("")
            draft_lines.extend(c.open_reference_summary()[:16])
            draft_body = "\n".join(draft_lines) if draft_lines else "No draft yet."
        self.set_ref_block("#ref-draft", "Current Text", draft_body, "green")

        if c.state.mode == "CHAT":
            next_body = "Ask Qwen about wording, then /finalize when the draft is ready."
        elif c.state.mode == "JUSTIFY":
            next_body = "Use /jterm, /jdecision, /jreason, /jautofill, then /jstage."
        elif c.state.book and c.state.chapter and c.state.chunk_start and c.state.chunk_end:
            next_body = "Recommended: /study -> /chat -> /finalize -> /stage -> /commit"
        else:
            next_body = "Recommended: /open <book> <chapter>"
        self.set_ref_block("#ref-next", "Next", next_body, "blue")

        self.update_prompt_label()

    def set_prompt_processing(self, command_text: str = "") -> None:
        input_widget = self.query_one("#command-input", Input)
        if command_text:
            input_widget.placeholder = f"Processing {command_text}"
            self.set_status("Working", f"Processing {command_text}", "purple")
        else:
            input_widget.placeholder = "Processing..."
            self.set_status("Working", "Processing...", "purple")
        self.update_prompt_label()

    def reset_prompt(self) -> None:
        input_widget = self.query_one("#command-input", Input)
        input_widget.placeholder = "/open Matthew 1"
        self.update_prompt_label()

    def dispatch_input(self, text: str) -> None:
        c = self.controller
        line = text.strip()
        if not line:
            return
        if c.state.mode in {"CHAT", "JUSTIFY"} and not line.startswith("/"):
            c.handle_mode_input(line)
            c.save_state()
            return
        if not line.startswith("/"):
            c.print_error("Commands start with '/'. Use / or /help for syntax.")
            c.save_state()
            return
        if line == "/":
            c.show_command_menu()
            c.save_state()
            return
        c.echo_command(line)
        try:
            c.handle_command(line[1:])
        except SystemExit:
            pass
        c.save_state()

    @work(thread=True, exclusive=True)
    def run_user_input(self, text: str) -> None:
        try:
            self.dispatch_input(text)
        finally:
            self.call_from_thread(self.after_command)

    def after_command(self) -> None:
        self.refresh_reference_pane()
        input_widget = self.query_one("#command-input", Input)
        input_widget.disabled = False
        self.reset_prompt()
        input_widget.focus()
        if self.controller.exit_requested:
            self.exit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        event.input.value = ""
        event.input.disabled = True
        self.set_prompt_processing(text.strip())
        self.run_user_input(text)


def main() -> None:
    TextualWorkbenchApp().run()


if __name__ == "__main__":
    main()
