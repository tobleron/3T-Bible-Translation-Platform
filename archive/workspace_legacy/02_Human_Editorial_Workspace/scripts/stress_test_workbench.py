from __future__ import annotations

from ttt_workbench.app import WorkbenchApp
from ttt_workbench.models import SessionState
from ttt_workbench.test_support import FakeLLM, install_safe_patches


def main() -> None:
    install_safe_patches()
    app = WorkbenchApp()
    app.state = SessionState(session_id="smoke-test")
    app.llm = FakeLLM()
    app.model_label = app.compact_model_name(app.llm.list_models()[0])
    transcript: list[str] = []

    def capture(renderable: object) -> None:
        text = app.theme.render_transcript_text(renderable, width=110)
        if text.strip():
            transcript.append(text.strip())

    app.emit = capture  # type: ignore[method-assign]
    app.render_status = lambda: None  # type: ignore[method-assign]

    results: list[tuple[str, str]] = []

    def run_step(name: str, fn) -> None:
        try:
            fn()
            results.append((name, "PASS"))
        except Exception as exc:  # pragma: no cover - smoke test summary
            results.append((name, f"FAIL: {exc}"))

    run_step("help", lambda: app.cmd_help([]))
    run_step("open-guided", lambda: app.cmd_open(["Matthew", "1"]))
    run_step("chunk-suggest", lambda: app.cmd_chunk_suggest([]))
    run_step("chunk-range", lambda: app.cmd_chunk_range(["1", "1-17"]))
    run_step("chunk-type", lambda: app.cmd_chunk_type(["1", "genealogy"]))
    run_step("chunk-title", lambda: app.cmd_chunk_title(["1", "Genealogy of Jesus"]))
    run_step("chunk-use", lambda: app.cmd_chunk_use(["1"]))
    run_step("status", lambda: app.cmd_status([]))
    run_step("sources", lambda: app.cmd_sources([]))
    run_step("study", lambda: app.cmd_study([]))
    run_step("peek", lambda: app.cmd_peek(["1", "ESV,NET"]))
    run_step("analysis-local", lambda: app.cmd_analysis([]))
    run_step("analysis-local-sources", lambda: app.cmd_analysis(["local", "1-3", "ESV,NET"]))
    run_step("analysis-refresh", lambda: app.cmd_analysis(["refresh", "1-3", "ESV,NET"]))
    run_step("analysis-show", lambda: app.cmd_analysis(["show", "1-3", "ESV,NET"]))
    run_step("chat-enter", lambda: app.cmd_chat([]))
    run_step("chat-turn", lambda: app.handle_mode_input("Give me an initial draft for the chunk."))
    run_step("focus", lambda: app.cmd_focus(["1-17"]))
    run_step("finalize", lambda: app.cmd_finalize(["1-17"]))
    run_step("stage", lambda: app.cmd_stage(["1-17"]))
    run_step("revise", lambda: app.cmd_revise(["1-17"]))
    run_step("cancel-after-revise", lambda: app.cmd_cancel([]))
    run_step("title-show", lambda: app.cmd_title(["show"]))
    run_step("title-refresh", lambda: app.cmd_title(["refresh"]))
    run_step("title-stage", lambda: app.cmd_title(["stage"]))
    run_step("justify", lambda: app.cmd_justify(["2-3"]))
    run_step("jterm", lambda: app.cmd_jterm(["γεννάω"]))
    run_step("jdecision", lambda: app.cmd_jdecision(["fathered"]))
    run_step("jreason", lambda: app.cmd_jreason(["Repeated", "genealogy", "formula", "kept", "consistent."]))
    run_step("jautofill", lambda: app.cmd_jautofill([]))
    run_step("jshow", lambda: app.cmd_jshow([]))
    run_step("jstage", lambda: app.cmd_jstage([]))
    run_step("diff", lambda: app.cmd_diff([]))
    run_step("repair", lambda: app.cmd_repair([]))
    run_step("commit", lambda: app.cmd_commit([]))
    run_step("undo", lambda: app.cmd_undo([]))
    run_step("epub-gen", lambda: app.cmd_epub_gen([]))
    run_step("open-manual", lambda: app.cmd_open(["Matthew", "1:1-17"]))
    app.state.draft_chunk["1"] = "Scratch verse."
    run_step("discard", lambda: app.cmd_discard(["1"]))
    run_step("chunk-refresh", lambda: app.cmd_chunk_refresh([]))
    run_step("chunk-cache-clear", lambda: app.cmd_chunk_cache_clear([]))
    run_step("chunk-cache-clear-all", lambda: app.cmd_chunk_cache_clear(["all"]))
    run_step("quit-save", lambda: app.save_state())

    width = max(len(name) for name, _ in results) + 2
    print("Workbench smoke test")
    print("====================")
    for name, status in results:
        print(f"{name.ljust(width)} {status}")

    failures = [item for item in results if not item[1].startswith("PASS")]
    print()
    print(f"Transcript entries captured: {len(transcript)}")
    if failures:
        print(f"Failures: {len(failures)}")
        raise SystemExit(1)
    print("All scripted command checks passed.")


if __name__ == "__main__":
    main()
