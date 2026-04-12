from __future__ import annotations

from io import StringIO
from typing import Iterable

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.box import ROUNDED


class GruvboxTheme:
    COLORS = {
        "bg0_h": "#1d2021",
        "bg0": "#282828",
        "bg1": "#3c3836",
        "bg2": "#504945",
        "bg3": "#665c54",
        "fg0": "#fbf1c7",
        "fg1": "#ebdbb2",
        "fg2": "#d5c4a1",
        "fg3": "#bdae93",
        "yellow": "#fabd2f",
        "orange": "#fe8019",
        "red": "#fb4934",
        "green": "#b8bb26",
        "aqua": "#8ec07c",
        "blue": "#83a598",
        "purple": "#d3869b",
    }

    def __init__(self) -> None:
        self.console = Console(highlight=False, soft_wrap=True)

    def prompt_style(self) -> Style:
        return Style.from_dict(
            {
                "prompt.blue": f"bold {self.COLORS['blue']}",
                "prompt.green": f"bold {self.COLORS['green']}",
                "prompt.yellow": f"bold {self.COLORS['yellow']}",
                "prompt.aqua": f"bold {self.COLORS['aqua']}",
                # Task 016: Better workspace background and visual depth
                "workspace": f"bg:{self.COLORS['bg0']} {self.COLORS['fg1']}",
                "workspace.border": self.COLORS['bg2'],
                "header": f"bg:{self.COLORS['bg0_h']} bold {self.COLORS['orange']}",
                "input-area": f"bg:{self.COLORS['bg0_h']} {self.COLORS['fg0']}",
                "input-area.border": self.COLORS['bg3'],
                "divider": f"fg:{self.COLORS['bg2']}",
                "palette": f"bg:{self.COLORS['bg1']} {self.COLORS['fg1']}",
                "palette.title": f"bold {self.COLORS['aqua']}",
                # Completion menu
                "completion-menu.completion": f"bg:{self.COLORS['bg1']} {self.COLORS['fg1']}",
                "completion-menu.completion.current": f"bg:{self.COLORS['blue']} {self.COLORS['bg0_h']}",
                "completion-menu.completion.current": f"bg:{self.COLORS['blue']} bold {self.COLORS['bg0_h']}",
                "completion-menu.meta.completion": f"bg:{self.COLORS['bg1']} {self.COLORS['fg3']}",
                "completion-menu.meta.completion.current": f"bg:{self.COLORS['blue']} {self.COLORS['fg0']}",
                "completion-menu": f"bg:{self.COLORS['bg1']}",
                "completion-menu.current": f"bg:{self.COLORS['blue']}",
                "scrollbar.background": f"bg:{self.COLORS['bg0']}",
                "scrollbar.button": f"bg:{self.COLORS['bg3']}",
                "bottom-toolbar": f"bg:{self.COLORS['bg0_h']} {self.COLORS['fg3']}",
            }
        )

    def prompt_message(self, mode: str) -> FormattedText:
        style = {
            "COMMAND": "class:prompt.blue",
            "CHAT": "class:prompt.green",
            "JUSTIFY": "class:prompt.yellow",
        }.get(mode.upper(), "class:prompt.aqua")
        return FormattedText([(style, f"{mode.lower()}> ")])

    def print(self, renderable: object) -> None:
        self.console.print(renderable)

    def toolbar_message(self) -> FormattedText:
        return FormattedText([("class:bottom-toolbar", "  ↑↓ move  ·  Enter select  ·  / commands  ")])

    def render_text(self, renderable: object, *, width: int | None = None) -> str:
        if isinstance(renderable, str):
            return renderable
        buffer = StringIO()
        console = Console(file=buffer, highlight=False, soft_wrap=True, width=width or 100, color_system=None, force_terminal=False)
        console.print(renderable)
        return buffer.getvalue().rstrip()

    def render_ansi(self, renderable: object, *, width: int | None = None) -> str:
        if isinstance(renderable, str):
            return renderable
        buffer = StringIO()
        console = Console(
            file=buffer,
            highlight=False,
            soft_wrap=True,
            width=width or 100,
            color_system="truecolor",
            force_terminal=True,
        )
        console.print(renderable)
        return buffer.getvalue().rstrip()

    def render_transcript_text(self, renderable: object, *, width: int | None = None) -> str:
        if isinstance(renderable, Panel):
            title = str(renderable.title).strip() if renderable.title else ""
            body = self.render_text(renderable.renderable, width=width).strip()
            lines: list[str] = []
            if title:
                underline_width = max(8, min(len(title), max(8, (width or 80) // 3)))
                lines.append(title)
                lines.append("─" * underline_width)
            if body:
                lines.append("")  # Task 016: breathing room after title
                lines.extend(body.splitlines())
            return "\n".join(lines).strip()
        if isinstance(renderable, Rule):
            return ""
        return self.render_text(renderable, width=width)

    def _accent(self, name: str) -> str:
        return self.COLORS.get(name, self.COLORS["blue"])

    def banner(self, subtitle: str = "") -> Group:
        title = Text("TTT Workbench", style=f"bold {self.COLORS['orange']}")
        if subtitle:
            title.append("  ", style=f"{self.COLORS['fg1']}")
            title.append(subtitle, style=self.COLORS["fg1"])
        return Group(title, Rule(style=self.COLORS["bg2"]))

    def panel(
        self,
        title: str,
        lines: list[str],
        accent: str = "blue",
        *,
        border_style: str | None = None,
    ) -> Panel:
        body = Text()
        for index, line in enumerate(lines or [""]):
            if index:
                body.append("\n")
            body.append(line, style=self.COLORS["fg1"])
        effective_border = border_style if border_style is not None else self._accent(accent)
        return Panel(
            body,
            title=title,
            title_align="left",
            border_style=effective_border,
            padding=(1, 2),
            box=ROUNDED,
            expand=True,
        )

    def card(self, title: str, body_lines: list[str], accent: str = "blue") -> Panel:
        accent_color = self._accent(accent)
        content = Text()
        content.append(title, style=f"bold {accent_color}")
        content.append("\n\n")
        for idx, line in enumerate(body_lines or [""]):
            if idx:
                content.append("\n")
            content.append(line, style=self.COLORS["fg1"])
        return Panel(
            content,
            border_style=accent_color,
            padding=(1, 2),
            box=ROUNDED,
            expand=True,
        )

    def welcome_banner(self) -> Group:
        title = Text("TTT Workbench", style=f"bold {self.COLORS['orange']}")
        title.append("\n")
        title.append("Theological Truth Translation", style=self.COLORS["fg1"])
        return Group(title, Rule(style=self.COLORS["bg2"]))

    def status_badge(self, label: str, value: str, accent: str) -> Text:
        badge = Text()
        badge.append(f"  {label}  ", style=f"bold {self.COLORS['bg0_h']} on {self._accent(accent)}")
        badge.append(f"  {value}  ", style=f"{self.COLORS['fg0']} on {self.COLORS['bg1']}")
        return badge

    def badge_row(self, badges: Iterable[Text]) -> Text:
        row = Text()
        for index, badge in enumerate(badges):
            if index:
                row.append("  ")
            row.append_text(badge)
        return row
