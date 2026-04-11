from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ttt_core.utils import normalize_book_key
from ttt_core.models import FootnoteDraft, PendingFootnoteUpdate

from .controller import BrowserWorkbench


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

app = FastAPI(title="TTT Browser Workbench")
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
_CONTROLLER: BrowserWorkbench | None = None


def controller() -> BrowserWorkbench:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = BrowserWorkbench()
    return _CONTROLLER


def resolve_book_name(wb: BrowserWorkbench, testament: str, raw_book: str) -> str:
    for book in wb.bible_repo.canonical_books(testament):
        if normalize_book_key(book) == normalize_book_key(raw_book):
            return book
    return raw_book


def render_page(request: Request, template_name: str, context: dict, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        template_name,
        {"request": request, **context},
        status_code=status_code,
    )


def render_workspace(request: Request, wb: BrowserWorkbench, active_tab: str = "study", partial: bool = False):
    context = wb.workspace_payload(active_tab=active_tab)
    template_name = "partials/workspace_root.html" if partial else "workspace.html"
    response = render_page(request, template_name, context)
    wb.clear_flash()
    return response


def apply_draft_form(wb: BrowserWorkbench, form) -> None:
    if not form:
        return
    editor_mode = str(form.get("editor_mode", wb.editor_mode())).strip().lower() or wb.editor_mode()
    # Check for per-verse textarea fields (verse_N)
    verse_fields = {
        key: str(value)
        for key, value in form.items()
        if str(key).startswith("verse_")
    }
    if verse_fields:
        start = int(str(form.get("draft_range_start", wb.current_editor_range()[0])))
        end = int(str(form.get("draft_range_end", wb.current_editor_range()[1])))
        verses: dict[int, str] = {}
        for key, text in verse_fields.items():
            try:
                verse_num = int(key.split("_", 1)[1])
                if start <= verse_num <= end:
                    verses[verse_num] = text.strip()
            except (ValueError, IndexError):
                continue
        wb.save_draft(str(form.get("draft_title", "")), verses, editor_mode=editor_mode)
        return
    if "draft_range_text" in form:
        start = int(str(form.get("draft_range_start", wb.current_editor_range()[0])))
        end = int(str(form.get("draft_range_end", wb.current_editor_range()[1])))
        wb.save_range_draft(
            str(form.get("draft_title", "")),
            start,
            end,
            str(form.get("draft_range_text", "")),
        )
        return
    has_draft_payload = "draft_title" in form or any(str(key).startswith("verse_") for key in form.keys())
    if not has_draft_payload:
        return
    verses = {}
    for key, value in form.items():
        if str(key).startswith("verse_"):
            verses[int(str(key).split("_", 1)[1])] = str(value)
    wb.save_draft(str(form.get("draft_title", "")), verses, editor_mode=editor_mode)


def render_workspace_error(
    request: Request,
    wb: BrowserWorkbench,
    exc: Exception,
    *,
    active_tab: str = "draft",
    partial: bool = True,
):
    wb.print_error(str(exc))
    wb.save_state()
    return render_workspace(request, wb, active_tab=active_tab, partial=partial)


@app.get("/workspace/navigate")
@app.post("/workspace/navigate")
async def workspace_navigate(request: Request):
    # Support both GET (query params) and POST (form data from HTMX)
    if request.method == "POST":
        form = await request.form()
        testament = str(form.get("testament", "new"))
        book = str(form.get("book", ""))
        chapter = str(form.get("chapter", ""))
        chunk = str(form.get("chunk", ""))
    else:
        testament = "old" if "testament" in request.query_params and request.query_params.get("testament") == "old" else "new"
        book = request.query_params.get("book", "")
        chapter = request.query_params.get("chapter", "")
        chunk = request.query_params.get("chunk", "")

    wb = controller()
    testament = "old" if testament == "old" else "new"
    book_items = [
        item
        for item in wb.navigator_catalog().get(testament, [])
        if item.get("chapters") or item.get("first_ready_chapter")
    ]
    if not book_items:
        return RedirectResponse(url="/", status_code=302)

    selected_item = next(
        (
            item
            for item in book_items
            if normalize_book_key(str(item.get("name", ""))) == normalize_book_key(book)
        ),
        book_items[0],
    )
    selected_book = str(selected_item.get("name", "")).strip() or str(book_items[0]["name"])
    chapter_options = [int(value) for value in selected_item.get("chapters", []) if isinstance(value, int)]
    first_ready_chapter = selected_item.get("first_ready_chapter")
    if not chapter_options and isinstance(first_ready_chapter, int):
        chapter_options = [first_ready_chapter]
    if not chapter_options:
        return RedirectResponse(url="/", status_code=302)

    try:
        selected_chapter = int(chapter)
    except (TypeError, ValueError):
        selected_chapter = -1
    if selected_chapter not in chapter_options:
        selected_chapter = (
            int(first_ready_chapter)
            if isinstance(first_ready_chapter, int) and first_ready_chapter in chapter_options
            else chapter_options[0]
        )

    valid_chunks = {
        f"{item.start_verse}-{item.end_verse}"
        for item in wb.chapter_chunks(testament, selected_book, selected_chapter)
    }
    if chunk and chunk in valid_chunks:
        wb.open_or_select_chunk(testament, selected_book, selected_chapter, chunk)
        wb.save_state()
        return render_workspace(request, wb, active_tab="study", partial=True)
    wb.select_chapter(testament, selected_book, selected_chapter)
    return render_workspace(request, wb, active_tab="study", partial=True)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    wb = controller()
    return render_page(
        request,
        "home.html",
        {
            "navigator": wb.navigator_catalog(),
            "recent_epubs": wb.recent_epubs(),
            "history_entries": wb.history_entries[-8:],
            "flash_messages": wb.flash_messages,
            "current_chunk_key": wb.current_chunk_key() or "",
            "state": wb.state,
        },
    )


@app.get("/workspace/{testament}/{book}/{chapter}", response_class=HTMLResponse)
def workspace_chapter(request: Request, testament: str, book: str, chapter: int, tab: str = "study"):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.select_chapter(testament, book, chapter)
    return render_workspace(request, wb, active_tab=tab)


@app.get("/workspace/{testament}/{book}/{chapter}/{chunk_key}", response_class=HTMLResponse)
def workspace(request: Request, testament: str, book: str, chapter: int, chunk_key: str, tab: str = "study"):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.open_or_select_chunk(testament, book, chapter, chunk_key)
    wb.activate_tab(tab)
    wb.save_state()
    return render_workspace(request, wb, active_tab=tab)


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/tab", response_class=HTMLResponse)
def workspace_tab(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
    tab: str = Form(...),
):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
    wb.activate_tab(tab)
    wb.save_state()
    return render_workspace(request, wb, active_tab=tab, partial=True)


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/study/sources", response_class=HTMLResponse)
async def study_sources(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    form = await request.form()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        selected = form.getlist("selected_sources")
        wb.set_selected_sources(selected)
        wb.activate_tab("study")
        wb.save_state()
        payload = wb.workspace_payload(active_tab="study")
        return templates.TemplateResponse(
            request,
            "partials/context_panel.html",
            {"request": request, **payload},
        )
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="study")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/draft/save", response_class=HTMLResponse)
async def save_draft(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    form = await request.form()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        apply_draft_form(wb, form)
        wb.notify("Draft saved.")
        wb.activate_tab("draft")
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/draft/range", response_class=HTMLResponse)
async def set_draft_range(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    form = await request.form()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        apply_draft_form(wb, form)
        target_start = int(str(form.get("editor_target_start", wb.current_editor_range()[0])))
        target_end = int(str(form.get("editor_target_end", wb.current_editor_range()[1])))
        wb.set_editor_range(target_start, target_end)
        wb.activate_tab("draft")
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/editor/mode", response_class=HTMLResponse)
async def set_editor_mode(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    form = await request.form()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        apply_draft_form(wb, form)
        action = str(form.get("editor_action", "")).strip().lower()
        if action == "seed-draft":
            wb.seed_draft_from_committed()
        else:
            wb.set_editor_mode(action or "draft")
        wb.activate_tab("draft")
        wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/chunks/merge", response_class=HTMLResponse)
async def merge_chapter_chunks(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
):
    form = await request.form()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        start_index = int(str(form.get("start_index", "0")))
        end_index = int(str(form.get("end_index", "0")))
        title = str(form.get("title", ""))
        chunk_type = str(form.get("chunk_type", ""))
        reason = str(form.get("reason", ""))
        wb.merge_chapter_chunks(
            testament,
            book,
            chapter,
            start_index=start_index,
            end_index=end_index,
            title=title,
            chunk_type=chunk_type,
            reason=reason,
        )
    except ValueError as exc:
        wb.select_chapter(testament, book, chapter)
        wb.print_error(str(exc))
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")
    return render_workspace(request, wb, active_tab="study", partial=True)


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat", response_class=HTMLResponse)
async def chat_turn(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    form = await request.form()
    message = str(form.get("message", "")).strip()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        apply_draft_form(wb, form)
        wb.activate_tab("draft")
        if message:
            wb.state.mode = "CHAT"
            wb.browser_chat_turn(message)
            wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/review/finalize", response_class=HTMLResponse)
def finalize_review(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.cmd_finalize([])
        wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/review/stage-text", response_class=HTMLResponse)
def stage_text(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.cmd_stage([])
        wb.save_state()
        return render_workspace(request, wb, active_tab="commit", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="commit")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/review/title-refresh", response_class=HTMLResponse)
def refresh_title(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.cmd_title(["refresh"])
        wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/review/title-stage", response_class=HTMLResponse)
def stage_title(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.cmd_title(["stage"])
        wb.save_state()
        return render_workspace(request, wb, active_tab="commit", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="commit")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/justify", response_class=HTMLResponse)
async def justify_stage(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    form = await request.form()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        apply_draft_form(wb, form)
        action = str(form.get("action", "")).strip()
        if action == "cancel":
            wb.cmd_jcancel([])
        else:
            verse_range = str(form.get("justify_range", chunk_key)).strip() or chunk_key
            wb.cmd_justify([verse_range])
            if wb.state.justify_draft:
                wb.state.justify_draft.source_term = str(form.get("source_term", "")).strip()
                wb.state.justify_draft.decision = str(form.get("decision", "")).strip()
                wb.state.justify_draft.reason = str(form.get("reason", "")).strip()
                if action == "autofill":
                    wb.cmd_jautofill([])
                elif action == "stage":
                    wb.cmd_jstage([])
        wb.activate_tab("draft")
        wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/footnotes", response_class=HTMLResponse)
async def footnote_stage(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    form = await request.form()
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        apply_draft_form(wb, form)
        action = str(form.get("action", "stage")).strip()
        if action == "cancel":
            wb.state.footnote_draft = None
            wb.notify("Footnote draft cancelled.")
        else:
            verse = int(str(form.get("footnote_verse", "0")).strip() or "0")
            letter = str(form.get("footnote_letter", "")).strip()
            content = str(form.get("footnote_content", "")).strip()
            wb.state.footnote_draft = FootnoteDraft(
                book=book,
                chapter=chapter,
                verse=verse,
                letter=letter,
                content=content,
            )
            if action == "stage":
                if verse <= 0:
                    raise ValueError("Select a verse before staging a footnote.")
                if not content:
                    raise ValueError("Add footnote content before staging it.")
                wb.state.pending_footnote_updates = [
                    item
                    for item in wb.state.pending_footnote_updates
                    if not (
                        item.book == book
                        and item.chapter == chapter
                        and int(item.entry.get("verse", 0)) == verse
                        and str(item.entry.get("letter", "")).strip() == letter
                    )
                ]
                wb.state.pending_footnote_updates.append(
                    PendingFootnoteUpdate(
                        book=book,
                        chapter=chapter,
                        entry={"verse": verse, "letter": letter, "content": content},
                    )
                )
                wb.state.footnote_draft = None
                wb.notify("Footnote staged.")
        wb.activate_tab("draft")
        wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/commit/validate", response_class=HTMLResponse)
def validate_commit(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.cmd_validate([])
        wb.save_state()
        return render_workspace(request, wb, active_tab="commit", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="commit")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/commit/apply", response_class=HTMLResponse)
async def apply_commit(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    wb = controller()
    form = await request.form()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        apply_draft_form(wb, form)
        wb.cmd_commit([])
        wb.save_state()
        return render_workspace(request, wb, active_tab="commit", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="commit")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/commit/rollback", response_class=HTMLResponse)
def rollback_commit(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.rollback_latest_commit()
        wb.save_state()
        return render_workspace(request, wb, active_tab="commit", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="commit")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/session/clear", response_class=HTMLResponse)
def clear_chunk_session(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.clear_current_chunk_session()
        wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.get("/workspace/{testament}/{book}/{chapter}/{chunk_key}/json-preview", response_class=JSONResponse)
def json_preview(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
    return JSONResponse(wb.json_preview_payload())


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    wb = controller()
    return render_page(
        request,
        "settings.html",
        {
            "prompt_payload": wb.prompt_payload(),
            "endpoint_url": wb.llm.base_url,
            "flash_messages": wb.flash_messages,
            "model_names": wb.safe_list_models(),
        },
    )


@app.post("/settings/save", response_class=HTMLResponse)
async def settings_save(request: Request):
    form = await request.form()
    wb = controller()
    try:
        wb.save_web_settings({"base_url": str(form.get("base_url", wb.llm.base_url)).strip()})
        wb.save_prompt_payload(
            {
                "chunk_schema": str(form.get("chunk_schema", "")),
                "ot_chunk": str(form.get("ot_chunk", "")),
                "nt_chunk": str(form.get("nt_chunk", "")),
                "legacy_analysis": str(form.get("legacy_analysis", "")),
            }
        )
        wb.notify("Settings saved.")
    except Exception as exc:
        wb.print_error(str(exc))
    return render_page(
        request,
        "settings.html",
        {
            "prompt_payload": wb.prompt_payload(),
            "endpoint_url": wb.llm.base_url,
            "flash_messages": wb.flash_messages,
            "model_names": wb.safe_list_models(),
        },
    )


@app.post("/settings/test-endpoint", response_class=HTMLResponse)
def settings_test_endpoint(request: Request):
    wb = controller()
    models = wb.safe_list_models()
    if models:
        wb.notify(f"Endpoint reachable. Models: {', '.join(models[:3])}")
    return render_page(
        request,
        "settings.html",
        {
            "prompt_payload": wb.prompt_payload(),
            "endpoint_url": wb.llm.base_url,
            "flash_messages": wb.flash_messages,
            "model_names": models,
        },
    )


@app.get("/epub", response_class=HTMLResponse)
def epub_page(request: Request):
    wb = controller()
    return render_page(
        request,
        "epub.html",
        {
            "recent_epubs": wb.recent_epubs(),
            "flash_messages": wb.flash_messages,
        },
    )


@app.post("/epub/generate", response_class=HTMLResponse)
def epub_generate(request: Request):
    wb = controller()
    output_dir = wb.paths.repo_root / "03_EPUB_Production"
    t0 = time.monotonic()
    cmd = [str(wb.preferred_python()), "generate_epub.py", "--md", "--txt"]
    try:
        result = subprocess.run(cmd, cwd=output_dir, capture_output=True, text=True, check=False)
    except Exception as exc:
        wb.print_error(f"EPUB generation failed to start: {exc}")
        result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
    duration = time.monotonic() - t0
    if result.returncode == 0:
        wb.notify(f"EPUB generated successfully in {duration:.1f}s.")
    else:
        wb.print_error(f"EPUB generation failed with exit code {result.returncode}.")
    return render_page(
        request,
        "epub.html",
        {
            "recent_epubs": wb.recent_epubs(),
            "flash_messages": wb.flash_messages,
            "epub_command": " ".join(cmd),
            "epub_stdout": (result.stdout or "").strip(),
            "epub_stderr": (result.stderr or "").strip(),
            "epub_exit_code": result.returncode,
        },
    )


@app.post("/epub/generate-download")
def epub_generate_download(request: Request):
    """Generate EPUB and trigger a browser download of the latest file."""
    wb = controller()
    success, message, latest_path = wb.generate_epub_and_return_latest()
    if success and latest_path and latest_path.exists():
        wb.notify(message)
        return FileResponse(
            path=str(latest_path),
            filename=latest_path.name,
            media_type="application/epub+zip",
        )
    wb.print_error(message)
    if request.headers.get("x-requested-with", "").lower() == "fetch":
        return JSONResponse({"ok": False, "message": message}, status_code=500)
    return RedirectResponse(url="/epub", status_code=302)


@app.get("/healthz")
def healthz():
    return {"ok": True, "pid": os.getpid()}


@app.get("/resume")
def resume():
    wb = controller()
    if wb.state.book and wb.state.chapter and wb.current_chunk_key():
        testament = wb.state.wizard_testament or wb.testament() or "new"
        return RedirectResponse(
            url=f"/workspace/{testament}/{normalize_book_key(wb.state.book)}/{wb.state.chapter}/{wb.current_chunk_key()}",
            status_code=302,
        )
    return RedirectResponse(url="/", status_code=302)
