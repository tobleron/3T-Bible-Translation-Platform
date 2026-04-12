from __future__ import annotations

import threading
import time

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from .app import WorkbenchApp
from ttt_workbench.models import SessionState
from ttt_workbench.test_support import FakeLLM


def wait_for(predicate, *, timeout: float = 3.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def make_app() -> WorkbenchApp:
    app = WorkbenchApp()
    app.state = SessionState(session_id="ui-test")
    app.llm = FakeLLM()
    app.model_label = app.compact_model_name(app.llm.list_models()[0])
    return app


def run_open_study_quit_sequence(*, quit_command: str) -> None:
    app = make_app()

    with create_pipe_input() as pipe_input:
        app.build_fullscreen(input=pipe_input, output=DummyOutput())
        thread = threading.Thread(target=app.application.run, daemon=True)
        thread.start()

        if not wait_for(lambda: "Home" in app.workspace_debug_text() and "New Session" in app.workspace_debug_text()):
            raise SystemExit("UI did not reach the initial home screen.")

        pipe_input.send_text("/open Matthew 1\r")
        if not wait_for(lambda: any(item["title"] == "Command" and "/open Matthew 1" in item["body"] for item in app.history_entries)):
            raise SystemExit("Guided /open did not record the command feedback.")
        if not wait_for(lambda: any(item["title"] == "Working" and "Loading chunk suggestions for Matthew 1..." in item["body"] for item in app.history_entries)):
            raise SystemExit("Guided /open did not show a visible working state.")
        if not wait_for(lambda: "Choose Chunk" in app.workspace_debug_text() and "1-17" in app.workspace_debug_text()):
            raise SystemExit("Guided /open did not render the chunk picker.")

        pipe_input.send_text("/chunk-use 1\r")
        if not wait_for(lambda: "Study Chunk" in app.workspace_debug_text() and "Chunk: Matthew 1:1-17" in app.workspace_debug_text()):
            raise SystemExit("/chunk-use did not open the selected chunk.")

        pipe_input.send_text("/study\r")
        if not wait_for(lambda: "New Testament Study" in app.workspace_debug_text() and "Primary: SBLGNT Greek" in app.workspace_debug_text()):
            raise SystemExit("/study did not render deterministic study output.")

        pipe_input.send_text(f"{quit_command}\r")
        thread.join(timeout=3.0)
        if thread.is_alive():
            raise SystemExit(f"{quit_command} did not terminate the fullscreen app.")


def run_guided_wizard_sequence() -> None:
    app = make_app()

    with create_pipe_input() as pipe_input:
        app.build_fullscreen(input=pipe_input, output=DummyOutput())
        thread = threading.Thread(target=app.application.run, daemon=True)
        thread.start()

        if not wait_for(lambda: "Home" in app.workspace_debug_text() and "New Session" in app.workspace_debug_text()):
            raise SystemExit("Guided wizard did not start on the home screen.")

        pipe_input.send_text("\r")
        if not wait_for(lambda: "Choose Testament" in app.workspace_debug_text()):
            raise SystemExit("Home Enter did not open the testament picker.")

        pipe_input.send_text("\r")
        if not wait_for(lambda: "Choose Book" in app.workspace_debug_text() and "Matthew" in app.workspace_debug_text()):
            raise SystemExit("Testament selection did not open the book picker.")

        pipe_input.send_text("\r")
        if not wait_for(lambda: "Choose Chapter" in app.workspace_debug_text() and "Chapter 1" in app.workspace_debug_text()):
            raise SystemExit("Book selection did not open the chapter picker.")

        pipe_input.send_text("\r")
        if not wait_for(lambda: "Choose Chunk" in app.workspace_debug_text() and "1-17" in app.workspace_debug_text()):
            raise SystemExit("Chapter selection did not open the chunk picker.")

        pipe_input.send_text("\r")
        if not wait_for(lambda: "Study Chunk" in app.workspace_debug_text() and "Chunk: Matthew 1:1-17" in app.workspace_debug_text()):
            raise SystemExit("Chunk selection did not open the study screen.")

        pipe_input.send_text("/quit\r")
        thread.join(timeout=3.0)
        if thread.is_alive():
            raise SystemExit("Guided wizard sequence did not exit cleanly.")


def run_exit_only_sequence() -> None:
    app = make_app()

    with create_pipe_input() as pipe_input:
        app.build_fullscreen(input=pipe_input, output=DummyOutput())
        thread = threading.Thread(target=app.application.run, daemon=True)
        thread.start()
        if not wait_for(lambda: "Home" in app.workspace_debug_text()):
            raise SystemExit("UI did not reach the initial ready state for /exit.")
        pipe_input.send_text("/exit\r")
        thread.join(timeout=3.0)
        if thread.is_alive():
            raise SystemExit("/exit did not terminate the fullscreen app.")


def main() -> None:
    run_guided_wizard_sequence()
    run_open_study_quit_sequence(quit_command="/quit")
    run_exit_only_sequence()

    print("Workbench UI integration test")
    print("=============================")
    print("wizard        PASS")
    print("open-guided   PASS")
    print("chunk-use     PASS")
    print("study         PASS")
    print("quit          PASS")
    print("exit          PASS")


if __name__ == "__main__":
    main()
