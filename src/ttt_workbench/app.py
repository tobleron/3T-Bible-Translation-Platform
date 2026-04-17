from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

try:
    import readline  # type: ignore
except ImportError:  # pragma: no cover
    readline = None

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.document import Document
    from prompt_toolkit.history import FileHistory
except ImportError:  # pragma: no cover
    Application = None
    Completer = None
    Completion = None
    FileHistory = None
    Document = None

from .ui.menus import MenuNavigationMixin
from .ui.layout import LayoutBuilderMixin
from .ui.screens.home import HomeScreenMixin
from .ui.screens.chunk_picker import ChunkPickerScreenMixin
from .ui.screens.study import StudyScreenMixin
from .ui.screens.chat import ChatScreenMixin
from .ui.screens.review import ReviewScreenMixin
from .ui.screens.justify import JustifyScreenMixin
from .ui.screens.commit_preview import CommitPreviewScreenMixin
from .ui.screens.epub_preview import EpubPreviewScreenMixin
from .ui.screens.tools import ToolsScreenMixin
from .commands.open_chat import OpenChatCommandsMixin
from .commands.study_chat import StudyChatCommandsMixin
from .commands.chunks import ChunkCommandsMixin
from .commands.review import ReviewCommandsMixin
from .commands.justify import JustifyCommandsMixin
from .commands.commit import CommitCommandsMixin
from .commands.epub import EpubCommandsMixin
from .commands.help import HelpCommandsMixin
from .theme import GruvboxTheme
from .background_jobs import Job, JobRunner
from .models import SessionState, BusyState, CommandHistoryEntry
from .repositories import BibleRepository, JustificationRepository, SourceRepository, LexicalRepository, ProjectPaths
from .utils import find_close_command, parse_range, parse_reference
from .llm import LlamaCppClient


class SlashCommandCompleter(Completer):
    def __init__(self, app: "WorkbenchApp") -> None:
        self.app = app

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        if " " in text:
            return
        prefix = text[1:].lower()
        display_width, meta_width = self.app.command_palette_widths()
        for name, spec in self.app.command_specs.items():
            if prefix and not name.startswith(prefix):
                continue
            display = self.app.fit_palette_text(str(spec["display"]), display_width)
            desc = self.app.fit_palette_text(str(spec["desc"]), meta_width)
            yield Completion(
                text="/" + name + (" " if spec.get("trailing_space", True) else ""),
                start_position=-len(text),
                display=display,
                display_meta=desc,
            )


class WorkbenchApp(
    HomeScreenMixin,
    ChunkPickerScreenMixin,
    StudyScreenMixin,
    ChatScreenMixin,
    ReviewScreenMixin,
    JustifyScreenMixin,
    CommitPreviewScreenMixin,
    EpubPreviewScreenMixin,
    ToolsScreenMixin,
    MenuNavigationMixin,
    LayoutBuilderMixin,
    OpenChatCommandsMixin,
    StudyChatCommandsMixin,
    ChunkCommandsMixin,
    ReviewCommandsMixin,
    JustifyCommandsMixin,
    CommitCommandsMixin,
    EpubCommandsMixin,
    HelpCommandsMixin,
):
    def __init__(self, *, llm_override: object | None = None) -> None:
        self.theme = GruvboxTheme()
        self.paths = ProjectPaths()
        self.source_repo = SourceRepository(self.paths)
        self.lexical_repo = LexicalRepository(self.paths)
        self.bible_repo = BibleRepository(
            self.paths,
            source_repository=self.source_repo,
            lexical_repository=self.lexical_repo,
        )
        self.just_repo = JustificationRepository(self.paths, self.bible_repo)
        self.llm = llm_override if llm_override is not None else LlamaCppClient()
        detected_models = self.llm.list_models() if hasattr(self.llm, "list_models") else []
        if detected_models:
            self.model_name = detected_models[0]
        else:
            self.model_name = "llama.cpp-model"
        self.model_label = self.compact_model_name(self.model_name)
        if hasattr(self.llm, "model_name"):
            self.llm.model_name = self.model_name
        self.app_version = "v0.2"
        self.legacy_prompt = self.paths.legacy_prompt_path.read_text(encoding="utf-8") if self.paths.legacy_prompt_path.exists() else ""
        self.state = self._load_state()
        self.history_path = self.paths.state_dir / "history.txt"
        self.prompt_session = None
        self.application = None
        self.transcript_area = None
        self.input_area = None
        self.header_control = None
        self.status_control = None
        self.workspace_control = None
        self.workspace_window = None
        self.history_control = None
        self.palette_control = None
        self.palette_index = 0
        self.workspace_scroll = 0
        self.history_entries: list[dict[str, str]] = []
        self.exit_requested = False
        self.chunk_prompt_version = "v1"
        self.command_specs = self.build_command_specs()
        self._init_line_editing()
        self.commands: dict[str, Callable[[list[str]], None]] = {name: spec["handler"] for name, spec in self.command_specs.items()}
        self.job_runner = JobRunner(max_workers=2)
        self.job_runner.set_change_callback(self._on_job_change)

    def build_command_specs(self) -> dict[str, dict[str, object]]:
        return {
            "help": {"handler": self.cmd_help, "display": "/help <command>", "desc": "Detailed help for one command"},
            "open": {"handler": self.cmd_open, "display": "/open <book> <chapter|range>", "desc": "Guided open or manual chunk override"},
            "status": {"handler": self.cmd_status, "display": "/status", "desc": "Current session overview"},
            "chat": {"handler": self.cmd_chat, "display": "/chat", "desc": "Enter drafting chat mode"},
            "focus": {"handler": self.cmd_focus, "display": "/focus <verse|range>", "desc": "Narrow the active focus inside the chunk"},
            "sources": {"handler": self.cmd_sources, "display": "/sources", "desc": "List comparison sources"},
            "study": {"handler": self.cmd_study, "display": "/study [range]", "desc": "Deterministic original-language study view"},
            "chunk-suggest": {"handler": self.cmd_chunk_suggest, "display": "/chunk-suggest", "desc": "Load cached or model chunk suggestions"},
            "chunk-use": {"handler": self.cmd_chunk_use, "display": "/chunk-use <n>", "desc": "Open a suggested chunk"},
            "chunk-range": {"handler": self.cmd_chunk_range, "display": "/chunk-range <n> <start-end>", "desc": "Edit a suggested range"},
            "chunk-type": {"handler": self.cmd_chunk_type, "display": "/chunk-type <n> <type>", "desc": "Edit a suggested chunk type"},
            "chunk-title": {"handler": self.cmd_chunk_title, "display": "/chunk-title <n> \"Title\"", "desc": "Edit a suggested title"},
            "chunk-preview": {"handler": self.cmd_chunk_preview, "display": "/chunk-preview <n>", "desc": "Preview details for one chunk"},
            "chunk-refresh": {"handler": self.cmd_chunk_refresh, "display": "/chunk-refresh", "desc": "Force new chunk suggestions"},
            "chunk-cache-clear": {"handler": self.cmd_chunk_cache_clear, "display": "/chunk-cache-clear [all]", "desc": "Clear cached chunk suggestions"},
            "peek": {"handler": self.cmd_peek, "display": "/peek <range> <SRC1,SRC2>", "desc": "Show comparison translations"},
            "analysis": {"handler": self.cmd_analysis, "display": "/analysis [show|refresh|local]", "desc": "Deterministic or cached analysis"},
            "finalize": {"handler": self.cmd_finalize, "display": "/finalize <range>", "desc": "Editorial review for the current draft"},
            "stage": {"handler": self.cmd_stage, "display": "/stage <range>", "desc": "Stage reviewed text for commit"},
            "revise": {"handler": self.cmd_revise, "display": "/revise <range>", "desc": "Return review guidance to chat"},
            "title": {"handler": self.cmd_title, "display": "/title show|refresh|set|stage", "desc": "Manage the chunk title"},
            "justify": {"handler": self.cmd_justify, "display": "/justify <range>", "desc": "Open justification mode"},
            "jterm": {"handler": self.cmd_jterm, "display": "/jterm <text>", "desc": "Set justification source term"},
            "jdecision": {"handler": self.cmd_jdecision, "display": "/jdecision <text>", "desc": "Set justification decision wording"},
            "jreason": {"handler": self.cmd_jreason, "display": "/jreason <text>", "desc": "Append justification notes"},
            "jshow": {"handler": self.cmd_jshow, "display": "/jshow", "desc": "Show current justification draft"},
            "jautofill": {"handler": self.cmd_jautofill, "display": "/jautofill", "desc": "Ask Qwen to draft the justification"},
            "jstage": {"handler": self.cmd_jstage, "display": "/jstage", "desc": "Stage the justification draft"},
            "jcancel": {"handler": self.cmd_jcancel, "display": "/jcancel", "desc": "Leave justification mode"},
            "diff": {"handler": self.cmd_diff, "display": "/diff", "desc": "Preview pending file changes"},
            "commit": {"handler": self.cmd_commit, "display": "/commit", "desc": "Write staged changes"},
            "undo": {"handler": self.cmd_undo, "display": "/undo", "desc": "Revert the latest commit"},
            "repair": {"handler": self.cmd_repair, "display": "/repair", "desc": "Inspect queued repairs"},
            "epub-gen": {"handler": self.cmd_epub_gen, "display": "/epub-gen", "desc": "Build EPUB output"},
            "history": {"handler": self.cmd_history, "display": "/history [n]", "desc": "Show recent command history"},
            "jobs": {"handler": self.cmd_jobs, "display": "/jobs", "desc": "Show background job status"},
            "cancel-job": {"handler": self.cmd_cancel_job, "display": "/cancel-job [id]", "desc": "Cancel a running job"},
            "terms": {"handler": self.cmd_terms, "display": "/terms <add|show|approve|reject|clear> ...", "desc": "Manage terminology ledger"},
            "review-history": {"handler": self.cmd_review_history, "display": "/review-history [n]", "desc": "Show recent review decisions"},
            "validate": {"handler": self.cmd_validate, "display": "/validate", "desc": "Validate pending JSON before commit"},
            "discard": {"handler": self.cmd_discard, "display": "/discard <range>", "desc": "Drop uncommitted work"},
            "cancel": {"handler": self.cmd_cancel, "display": "/cancel", "desc": "Leave current mode"},
            "quit": {"handler": self.cmd_quit, "display": "/quit", "desc": "Save and exit", "trailing_space": False},
            "exit": {"handler": self.cmd_quit, "display": "/exit", "desc": "Save and exit", "trailing_space": False},
        }

    def _load_state(self) -> SessionState:
        if self.paths.state_file.exists():
            payload = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
            state = SessionState.from_json(payload)
            state.mode = "COMMAND"
            return state
        from uuid import uuid4
        return SessionState(session_id=uuid4().hex[:8])

    def refresh_active_endpoint(self) -> str:
        """Hook for browser-specific endpoint selection; base app keeps current URL."""
        return getattr(self.llm, "base_url", "")

    def save_state(self) -> None:
        self.paths.state_file.write_text(json.dumps(self.state.to_json(), indent=2), encoding="utf-8")
        self._save_line_history()

    def _init_line_editing(self) -> None:
        if readline is None:
            return
        try:
            readline.parse_and_bind("tab: complete")
            readline.parse_and_bind('"\\e[A": previous-history')
            readline.parse_and_bind('"\\e[B": next-history')
            readline.parse_and_bind("set editing-mode emacs")
            if self.history_path.exists():
                readline.read_history_file(str(self.history_path))
            readline.set_history_length(500)
        except Exception:
            return

    def _save_line_history(self) -> None:
        if readline is None:
            return
        try:
            readline.write_history_file(str(self.history_path))
        except Exception:
            return

    def compact_model_name(self, raw_name: str) -> str:
        lowered = raw_name.lower()
        if "qwen" in lowered and "35b" in lowered and "a3b" in lowered:
            return "Qwen3.5 35B A3B"
        cleaned = re.sub(r"\.gguf$", "", raw_name, flags=re.IGNORECASE)
        cleaned = cleaned.replace("_", "-")
        if len(cleaned) <= 24:
            return cleaned
        return cleaned[:21] + "..."

    def set_screen(self, screen: str, *, mode: str | None = None, reset_menu: bool = True) -> None:
        self.state.screen = screen
        if mode is not None:
            self.state.mode = mode
        if reset_menu:
            self.state.menu_index = 0
        self.workspace_scroll = 0
        self.flush_ui()

    def handle_command(self, text: str) -> None:
        if not text.strip():
            self.show_command_menu()
            return
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            self.print_error(f"Could not parse command: {exc}")
            return
        if not parts:
            self.show_command_menu()
            return
        command, args = parts[0].lower(), parts[1:]
        handler = self.commands.get(command)
        if not handler:
            suggestions = find_close_command(command, sorted(self.commands))
            suffix = f" Try: {', '.join('/' + item for item in suggestions)}" if suggestions else " Use /help."
            self.print_error(f"Unknown command '/{command}'.{suffix}")
            return
        try:
            handler(args)
        except SystemExit:
            raise
        except ValueError as exc:
            self.print_error(str(exc))
        except Exception as exc:
            self.print_error(f"Unexpected internal error while running '/{command}': {exc}")

    def handle_mode_input(self, text: str) -> None:
        if self.state.mode == "CHAT":
            self.chat_turn(text)
        elif self.state.mode == "JUSTIFY":
            if not self.state.justify_draft:
                self.print_error("No active justification draft. Use /justify <range>.")
                self.state.mode = "COMMAND"
                return
            if self.state.justify_draft.reason:
                self.state.justify_draft.reason += "\n"
            self.state.justify_draft.reason += text.strip()
            self.emit(self.theme.panel("Justification Notes", ["Added free-text notes to the current justification draft.", "Use /jshow to inspect or /jautofill to turn notes into a cleaner draft."], accent="yellow"))

    def notify_busy(self, message: str, label: str = "") -> None:
        self.state.busy_state = BusyState(label=label or message, message=message)
        self.emit(self.theme.panel("Working", [message], accent="purple"))
        self.flush_ui()

    def notify_done(self, label: str = "", message: str = "", duration: float = 0.0) -> None:
        self.state.busy_state = None
        entry = CommandHistoryEntry(
            command=label,
            status="success",
            duration_seconds=duration,
            message=message,
        )
        self.state.command_history.append(entry)
        if len(self.state.command_history) > 50:
            self.state.command_history = self.state.command_history[-50:]
        if message:
            self.emit(self.theme.panel("Done", [message], accent="green"))
            self.flush_ui()

    def notify_error(self, label: str = "", message: str = "", duration: float = 0.0) -> None:
        self.state.busy_state = None
        entry = CommandHistoryEntry(
            command=label,
            status="error",
            duration_seconds=duration,
            message=message,
        )
        self.state.command_history.append(entry)
        if len(self.state.command_history) > 50:
            self.state.command_history = self.state.command_history[-50:]
        self.print_error(message)

    def notify(self, message: str) -> None:
        self.state.busy_state = None
        self.emit(self.theme.panel("Notice", [message], accent="aqua"))

    def print_error(self, message: str) -> None:
        self.state.busy_state = None
        self.emit(self.theme.panel("Error", [message], accent="red"))

    def _on_job_change(self) -> None:
        active = self.job_runner.active_jobs()
        if active:
            job = active[0]
            self.state.busy_state = BusyState(
                label=job.label,
                message=f"{job.label}... ({job.elapsed_display})",
            )
        else:
            self.state.busy_state = None
        self.flush_ui()

    def submit_job(self, label: str, target: Callable[[], Any], *,
                   on_done: Callable[[Any], None] | None = None,
                   on_error: Callable[[str], None] | None = None) -> Job:
        import uuid
        def wrapped() -> Any:
            try:
                result = target()
                if on_done:
                    try:
                        on_done(result)
                    except Exception as cb_err:
                        if on_error:
                            on_error(str(cb_err))
                return result
            except Exception as exc:
                if on_error:
                    on_error(str(exc))
                raise
        job = Job(job_id=uuid.uuid4().hex[:8], label=label, target=wrapped)
        return self.job_runner.submit(job)


def main() -> None:
    app = WorkbenchApp()
    app.run()
