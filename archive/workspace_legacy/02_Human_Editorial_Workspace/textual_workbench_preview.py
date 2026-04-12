from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, RichLog, Static


class Block(Static):
    def __init__(self, title: str, body: str, *, classes: str = "") -> None:
        super().__init__(classes=f"block {classes}".strip())
        self.title = title
        self.body = body

    def compose(self) -> ComposeResult:
        yield Static(self.title, classes="block-title")
        yield Static(self.body, classes="block-body")


class HeaderBar(Static):
    def compose(self) -> ComposeResult:
        yield Static("TTT Workbench", classes="brand")
        yield Static("v0.2", classes="badge version")
        yield Static("COMMAND", classes="badge mode")
        yield Static("Qwen3 14B Q6-K", classes="badge model")


class TextualWorkbenchPreview(App):
    CSS = """
    Screen {
        background: #0b0b0b;
        color: #ebdbb2;
    }

    #root {
        layout: vertical;
        height: 100%;
        width: 100%;
        padding: 1 1;
        background: #0b0b0b;
    }

    #header {
        height: 3;
        border: round #fe8019;
        padding: 0 1;
        background: #111111;
        layout: horizontal;
        align-vertical: middle;
    }

    .brand {
        color: #fe8019;
        text-style: bold;
        width: 1fr;
    }

    .badge {
        padding: 0 1;
        margin-left: 1;
        background: #1d2021;
        color: #fbf1c7;
        border: round #3c3836;
        text-style: bold;
    }

    .version { border: round #fe8019; }
    .mode { border: round #8ec07c; }
    .model { border: round #d3869b; }

    #main {
        height: 1fr;
        margin-top: 1;
    }

    #left-pane {
        width: 2fr;
        min-width: 56;
        margin-right: 1;
    }

    #right-pane {
        width: 1fr;
        min-width: 40;
    }

    #timeline {
        height: 1fr;
        border: round #83a598;
        padding: 1;
        background: #111111;
    }

    #timeline-label {
        color: #83a598;
        text-style: bold;
        margin-bottom: 1;
    }

    #event-log {
        height: 1fr;
        background: #111111;
        scrollbar-background: #111111;
        scrollbar-color: #665c54;
        scrollbar-color-hover: #8ec07c;
    }

    #references {
        height: 1fr;
        border: round #8ec07c;
        padding: 1;
        background: #111111;
    }

    #ref-label {
        color: #8ec07c;
        text-style: bold;
        margin-bottom: 1;
    }

    #ref-scroll {
        height: 1fr;
        background: #111111;
    }

    .block {
        border: round #504945;
        background: #141414;
        padding: 0 1;
        margin-bottom: 1;
    }

    .block-title {
        color: #fabd2f;
        text-style: bold;
    }

    .block-body {
        color: #ebdbb2;
    }

    .source .block-title { color: #8ec07c; }
    .study .block-title { color: #83a598; }
    .draft .block-title { color: #b8bb26; }
    .terms .block-title { color: #d3869b; }
    .next .block-title { color: #fe8019; }

    #prompt-bar {
        height: 3;
        margin-top: 1;
        border: round #83a598;
        padding: 0 1;
        background: #111111;
        layout: horizontal;
        align-vertical: middle;
    }

    #prompt-label {
        width: 12;
        color: #b8bb26;
        text-style: bold;
    }

    #command-input {
        border: none;
        background: #111111;
        color: #fbf1c7;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            with Horizontal(id="header"):
                yield HeaderBar()
            with Horizontal(id="main"):
                with Vertical(id="left-pane"):
                    yield Static("Activity", id="timeline-label")
                    yield RichLog(id="event-log", markup=True, wrap=True, highlight=True)
                with Vertical(id="right-pane"):
                    yield Static("Reference", id="ref-label")
                    with VerticalScroll(id="ref-scroll"):
                        yield Block(
                            "Current Chunk",
                            "Matthew 1:1-17\nType: genealogy\nTitle draft: Genealogy of Jesus",
                            classes="source",
                        )
                        yield Block(
                            "Source Text",
                            "Greek\n1. Βίβλος γενέσεως Ἰησοῦ Χριστοῦ ...\n\nLiteral English\n1. book / genesis / of Jesus Christ ...",
                            classes="source",
                        )
                        yield Block(
                            "Study Focus",
                            "Impact words\n- γενέσεως: origin, genealogy\n- Χριστοῦ: Messiah, Christ\n- Δαυίδ: David",
                            classes="study",
                        )
                        yield Block(
                            "Current Draft",
                            "1. The genealogy of Jesus Christ, son of David, son of Abraham.",
                            classes="draft",
                        )
                        yield Block(
                            "Terminology",
                            "Approved\n- γεννάω → fathered\n- χριστός → Christ",
                            classes="terms",
                        )
                        yield Block(
                            "Next Decision",
                            "1. Review literal glosses\n2. Chat about wording\n3. Finalize and stage",
                            classes="next",
                        )
            with Horizontal(id="prompt-bar"):
                yield Static("command>", id="prompt-label")
                yield Input(placeholder="/open Matthew 1", id="command-input")

    def on_mount(self) -> None:
        log = self.query_one("#event-log", RichLog)
        log.write("[bold #83a598]Command[/]  /open Matthew 1")
        log.write("[bold #d3869b]Working[/]  Loading chunk suggestions for Matthew 1...")
        log.write("[bold #8ec07c]Chunk Suggestions[/]  1-17 Genealogy of Jesus  |  18-25 Birth of Jesus")
        log.write("[bold #83a598]Command[/]  /chunk-use 1")
        log.write("[bold #8ec07c]Study[/]  Greek, literal English, and impact words loaded.")
        self.query_one("#command-input", Input).focus()


def main() -> None:
    TextualWorkbenchPreview().run()


if __name__ == "__main__":
    main()
