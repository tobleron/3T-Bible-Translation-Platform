from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import markdown as md_lib
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from chainlit.utils import mount_chainlit

from ttt_core.utils import normalize_book_key
from ttt_core.models import (
    FootnoteDraft,
    JustificationDraft,
    PendingFootnoteUpdate,
    PendingJustificationUpdate,
)

from .controller import BrowserWorkbench


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def _render_markdown(text: str) -> str:
    """Convert markdown text to safe HTML."""
    if not text:
        return ""
    return md_lib.markdown(text, extensions=["fenced_code", "tables", "nl2br"])


templates.env.filters["markdown"] = _render_markdown

app = FastAPI(title="TTT Browser Workbench")
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
mount_chainlit(app=app, target=str(PACKAGE_DIR / "chainlit_app.py"), path="/chat")
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


def book_json_tree_payload(wb: BrowserWorkbench, testament: str, book: str, chapter: int) -> dict:
    chapters = []
    wb.bible_repo._build_index()
    book_key = normalize_book_key(book)
    indexed = [
        (chapter_num, path)
        for (indexed_book, chapter_num), path in wb.bible_repo._index.items()
        if indexed_book == book_key and wb.bible_repo._path_testament(path) == testament
    ]
    for chapter_num, path in sorted(indexed):
        chapters.append(
            {
                "chapter": chapter_num,
                "path": str(path),
                "selected": chapter_num == chapter,
            }
        )
    return {"ok": True, "testament": testament, "book": book, "chapters": chapters}


def book_json_chapter_payload(wb: BrowserWorkbench, book: str, target_chapter: int) -> JSONResponse:
    try:
        chapter_file = wb.bible_repo.load_chapter(book, target_chapter, allow_scaffold=False)
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=404)
    return JSONResponse(
        {
            "ok": True,
            "book": book,
            "chapter": target_chapter,
            "path": str(chapter_file.path),
            "json": chapter_file.doc,
        }
    )


def render_page(request: Request, template_name: str, context: dict, status_code: int = 200):
    if "settings_config" not in context:
        context["settings_config"] = controller().settings_payload()
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


def render_chat_panel(request: Request, wb: BrowserWorkbench):
    response = render_page(request, "partials/chat_panel.html", wb.workspace_payload(active_tab="draft"))
    wb.clear_flash()
    return response


def render_editor_panel(request: Request, wb: BrowserWorkbench):
    response = render_page(request, "partials/editor_panel.html", wb.workspace_payload(active_tab="draft"))
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


def _parse_verse_selection(raw_value: str, fallback_chunk_key: str) -> list[int]:
    raw = (raw_value or fallback_chunk_key).strip() or fallback_chunk_key
    verses: list[int] = []
    for part in [item.strip() for item in raw.split(",") if item.strip()]:
        if "-" in part:
            left, right = part.split("-", 1)
            start = int(left.strip())
            end = int(right.strip())
            if start > end:
                raise ValueError("Invalid verse selection. Start verse cannot be greater than end verse.")
            verses.extend(range(start, end + 1))
        else:
            verses.append(int(part))
    clean = sorted({verse for verse in verses if verse > 0})
    if clean:
        return clean
    if fallback_chunk_key and fallback_chunk_key != raw:
        return _parse_verse_selection(fallback_chunk_key, "")
    raise ValueError("Invalid verse selection. Use 5, 5-12, or 5, 7, 9-10.")


def _build_justification_draft(
    *,
    book: str,
    chapter: int,
    verse_spec: str,
    fallback_chunk_key: str,
    source_term: str = "",
    decision: str = "",
    reason: str = "",
    entry_id: str | None = None,
) -> JustificationDraft:
    verses = _parse_verse_selection(verse_spec, fallback_chunk_key)
    return JustificationDraft(
        book=book,
        chapter=chapter,
        start_verse=verses[0],
        end_verse=verses[-1],
        verses=verses,
        source_term=source_term,
        decision=decision,
        reason=reason,
        entry_id=entry_id,
    )


def _queue_justification_delete(wb: BrowserWorkbench, book: str, chapter: int, entry_id: str) -> None:
    wb.state.pending_justification_updates = [
        item
        for item in wb.state.pending_justification_updates
        if not (
            item.book == book
            and item.chapter == chapter
            and str(item.entry.get("id", "")).strip() == entry_id
        )
    ]
    wb.state.pending_justification_updates.append(
        PendingJustificationUpdate(
            book=book,
            chapter=chapter,
            entry={"id": entry_id, "_delete": True},
        )
    )


def _queue_footnote_delete(
    wb: BrowserWorkbench, book: str, chapter: int, verse: int, letter: str
) -> None:
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
            entry={"verse": verse, "letter": letter, "_delete": True},
        )
    )


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

    valid_chunks = [
        (f"{item.start_verse}-{item.end_verse}", item)
        for item in wb.chapter_chunks(testament, selected_book, selected_chapter)
    ]
    valid_chunk_keys = {k for k, _ in valid_chunks}
    first_chunk_key = valid_chunks[0][0] if valid_chunks else ""

    if chunk and chunk in valid_chunk_keys:
        wb.open_or_select_chunk(testament, selected_book, selected_chapter, chunk)
        wb.save_state()
        return render_workspace(request, wb, active_tab="study", partial=True)

    # Auto-select first chunk when none specified
    if first_chunk_key:
        wb.open_or_select_chunk(testament, selected_book, selected_chapter, first_chunk_key)
        wb.save_state()
        return render_workspace(request, wb, active_tab="study", partial=True)

    wb.select_chapter(testament, selected_book, selected_chapter)
    return render_workspace(request, wb, active_tab="study", partial=True)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    wb = controller()
    # Allow explicit access to home page via ?home=1
    if request.query_params.get("home") == "1":
        recent_epubs = wb.recent_epubs()
        return render_page(
            request,
            "home.html",
            {
                "navigator": wb.navigator_catalog(),
                "recent_epubs": recent_epubs,
                "latest_epub": recent_epubs[0] if recent_epubs else None,
                "project_summary": wb.project_summary(),
                "history_entries": wb.history_entries[-8:],
                "flash_messages": wb.flash_messages,
                "current_chunk_key": wb.current_chunk_key() or "",
                "state": wb.state,
            },
        )

    # Automatically resume if we have a book, chapter, and a VALID chunk
    if wb.state.book and wb.state.chapter and wb.current_chunk_key():
        testament = wb.state.wizard_testament or wb.testament() or "new"
        book = wb.state.book
        chapter = wb.state.chapter
        stale_key = wb.current_chunk_key()
        valid_chunks = {
            f"{item.start_verse}-{item.end_verse}"
            for item in wb.chapter_chunks(testament, book, chapter)
        }
        if valid_chunks and stale_key in valid_chunks:
            return RedirectResponse(
                url=f"/workspace/{testament}/{normalize_book_key(book)}/{chapter}/{stale_key}",
                status_code=302,
            )
        # Stale chunk — redirect to chapter page instead (will auto-select first chunk)
        return RedirectResponse(
            url=f"/workspace/{testament}/{normalize_book_key(book)}/{chapter}",
            status_code=302,
        )

    recent_epubs = wb.recent_epubs()
    return render_page(
        request,
        "home.html",
        {
            "navigator": wb.navigator_catalog(),
            "recent_epubs": recent_epubs,
            "latest_epub": recent_epubs[0] if recent_epubs else None,
            "project_summary": wb.project_summary(),
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


@app.get("/workspace/{testament}/{book}/{chapter}/json-book-tree", response_class=JSONResponse)
def chapter_json_book_tree(request: Request, testament: str, book: str, chapter: int):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.select_chapter(testament, book, chapter)
    return JSONResponse(book_json_tree_payload(wb, testament, book, chapter))


@app.get("/workspace/{testament}/{book}/{chapter}/json-book-chapter/{target_chapter}", response_class=JSONResponse)
def chapter_json_book_chapter(request: Request, testament: str, book: str, chapter: int, target_chapter: int):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.select_chapter(testament, book, chapter)
    return book_json_chapter_payload(wb, book, target_chapter)


@app.get("/workspace/{testament}/{book}/{chapter}/{chunk_key}", response_class=HTMLResponse)
def workspace(request: Request, testament: str, book: str, chapter: int, chunk_key: str, tab: str = "study"):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    # Validate chunk_key against catalog
    valid_chunks = {
        f"{item.start_verse}-{item.end_verse}"
        for item in wb.chapter_chunks(testament, book, chapter)
    }
    if valid_chunks and chunk_key not in valid_chunks:
        # Redirect to first chunk in catalog
        first_chunk = next(iter(valid_chunks))
        return RedirectResponse(
            url=f"/workspace/{testament}/{normalize_book_key(book)}/{chapter}/{first_chunk}",
            status_code=302,
        )
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
        return render_editor_panel(request, wb)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/draft/autosave", response_class=JSONResponse)
async def autosave_draft(
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
        wb.activate_tab("draft")
        return JSONResponse({"ok": True, "message": "Draft saved."})
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)


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
        return render_editor_panel(request, wb)
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
        action = str(form.get("editor_action", "")).strip().lower()
        if action in ("draft", "review"):
            apply_draft_form(wb, form)
        if action == "seed-draft":
            wb.seed_draft_from_committed()
            wb.history_entries.append(
                {"title": "Draft", "body": f"Committed text loaded as draft for {book} {chapter}:{chunk_key}.", "accent": "blue"}
            )
        elif action in ("draft", "review"):
            wb.set_editor_mode(action)
            wb.history_entries.append(
                {"title": "Editor", "body": f"Switched to {action.title()} mode for {book} {chapter}:{chunk_key}.", "accent": "blue"}
            )
        wb.activate_tab("draft")
        wb.save_state()
        return render_editor_panel(request, wb)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/editor/lock", response_class=HTMLResponse)
async def editor_lock(
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
        wb.lock_editor()
        return render_editor_panel(request, wb)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/editor/unlock", response_class=HTMLResponse)
async def editor_unlock(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.unlock_editor()
        return render_editor_panel(request, wb)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/editor/revise", response_class=HTMLResponse)
async def editor_revise(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.start_revision()
        return render_editor_panel(request, wb)
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
@app.get("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat/prompt-text", response_class=JSONResponse)
async def get_chat_prompt_text(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        
        blocks = wb.chunk_study_blocks()
        payload = {}
        def verse_line_text(lines: list[dict]) -> str:
            formatted = []
            for line in lines:
                verse = line.get("verse")
                text = str(line.get("text", "")).strip()
                if verse and text:
                    formatted.append(f"{verse}. {text}")
            return "\n".join(formatted)

        def clean_gloss_text(text: str) -> str:
            text = re.sub(r"\s*;\s*;\s*", "; ", str(text or ""))
            text = re.sub(r"\s*;\s*$", "", text)
            return re.sub(r"\s+", " ", text).strip()

        for block in blocks:
            kind = str(block.get("kind", "")).lower()
            if kind in {"hebrew", "greek"}:
                verse_lines = block.get("verse_lines") or []
                payload[kind] = verse_line_text(verse_lines) or str(block.get("text", "")).strip()
                
                gloss_lines = block.get("gloss_lines") or []
                en_lines = []
                for gloss_line in gloss_lines:
                    verse = gloss_line.get("verse")
                    words = [
                        gloss
                        for t in gloss_line.get("tokens", [])
                        if (gloss := clean_gloss_text(t.get("gloss", "")))
                    ]
                    if words:
                        en_lines.append(f"{verse}. {' '.join(words)}")
                if en_lines:
                    payload[f"{kind}-en"] = "\n".join(en_lines)

        return JSONResponse(payload)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)



@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat/clear", response_class=HTMLResponse)
async def clear_chat_history(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.clear_current_chunk_session()
        wb.save_state()
        
        # Return the updated panel summary via HTMX or just a success message
        return HTMLResponse(content='<span class="inline-badge">History Cleared</span> <script>window.location.reload();</script>')
    except Exception as exc:
        return HTMLResponse(content=f"Error: {exc}", status_code=500)


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat/session/new", response_class=HTMLResponse)
async def new_chat_session(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.new_current_chunk_chat_session()
        wb.notify("New chat session opened for this chunk.")
        return render_chat_panel(request, wb)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat/session/switch", response_class=HTMLResponse)
async def switch_chat_session(
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
        session_id = str(form.get("chat_session_id", "")).strip()
        if not wb.switch_current_chunk_chat_session(session_id):
            wb.print_error("Chat session not found.")
        return render_chat_panel(request, wb)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat/session/delete", response_class=HTMLResponse)
async def delete_chat_session(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
):
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        wb.delete_current_chunk_chat_session()
        return render_chat_panel(request, wb)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat/model", response_class=HTMLResponse)
async def update_chat_model(
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
        current = wb.settings_payload()
        next_provider = str(form.get("endpoint_provider", current.get("endpoint_provider", "local"))).strip()
        active_model = str(form.get("active_model", current.get("active_model", ""))).strip()
        if next_provider != str(current.get("endpoint_provider", "local")):
            active_model = ""
        wb.save_web_settings(
            {
                "endpoint_provider": next_provider,
                "local_base_url": current.get("local_base_url", ""),
                "local_api_key": current.get("local_api_key", ""),
                "local_model": current.get("local_model", ""),
                "cloud_base_url": current.get("cloud_base_url", "https://api.openai.com/v1"),
                "cloud_api_key": current.get("cloud_api_key", ""),
                "cloud_model": current.get("cloud_model", "gpt-4.1-mini"),
                "active_model": active_model,
            }
        )
        wb.safe_list_models()
        wb.notify(f"Chat endpoint set to {wb.active_provider_label()} / {wb.active_model_name()}.")
        return render_chat_panel(request, wb)
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
        elif action == "delete":
            entry_id = str(form.get("entry_id", "")).strip()
            if not entry_id:
                raise ValueError("Missing justification id for deletion.")
            _queue_justification_delete(wb, book, chapter, entry_id)
            if wb.state.justify_draft and wb.state.justify_draft.entry_id == entry_id:
                wb.state.justify_draft = None
            wb.notify("Justification staged for deletion.")
        elif action == "edit":
            wb.state.justify_draft = _build_justification_draft(
                book=book,
                chapter=chapter,
                verse_spec=str(form.get("justify_range", chunk_key)),
                fallback_chunk_key=chunk_key,
                entry_id=str(form.get("entry_id", "")).strip() or None,
                source_term=str(form.get("source_term", "")).strip(),
                decision=str(form.get("decision", "")).strip(),
                reason=str(form.get("reason", "")).strip(),
            )
            if wb.state.justify_draft:
                wb.state.mode = "JUSTIFY"
                wb.set_screen("JUSTIFY", mode="JUSTIFY")
                wb.notify("Justification loaded for editing.")
        else:
            verse_range = str(form.get("justify_range", chunk_key)).strip() or chunk_key
            wb.state.justify_draft = _build_justification_draft(
                book=book,
                chapter=chapter,
                verse_spec=verse_range,
                fallback_chunk_key=chunk_key,
                entry_id=str(form.get("entry_id", "")).strip() or None,
                source_term=str(form.get("source_term", "")).strip(),
                decision=str(form.get("decision", "")).strip(),
                reason=str(form.get("reason", "")).strip(),
            )
            if wb.state.justify_draft:
                wb.state.mode = "JUSTIFY"
                wb.set_screen("JUSTIFY", mode="JUSTIFY")
                wb.state.justify_custom_prompt = str(
                    form.get("justify_custom_prompt", wb.state.justify_custom_prompt)
                ).strip()
                if action == "stage":
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
        elif action == "delete":
            verse = int(str(form.get("footnote_verse", "0")).strip() or "0")
            letter = str(form.get("footnote_letter", "")).strip()
            if verse <= 0:
                raise ValueError("Missing footnote verse for deletion.")
            _queue_footnote_delete(wb, book, chapter, verse, letter)
            if (
                wb.state.footnote_draft
                and wb.state.footnote_draft.verse == verse
                and wb.state.footnote_draft.letter == letter
            ):
                wb.state.footnote_draft = None
            wb.notify("Footnote staged for deletion.")
        elif action == "edit":
            verse = int(str(form.get("footnote_verse", "0")).strip() or "0")
            letter = str(form.get("footnote_letter", "")).strip()
            content = str(form.get("footnote_content", "")).strip()
            wb.state.footnote_custom_prompt = str(
                form.get("footnote_custom_prompt", wb.state.footnote_custom_prompt)
            ).strip()
            wb.state.footnote_draft = FootnoteDraft(
                book=book,
                chapter=chapter,
                verse=verse,
                letter=letter,
                content=content,
            )
            wb.notify("Footnote loaded for editing.")
        else:
            verse = int(str(form.get("footnote_verse", "0")).strip() or "0")
            letter = str(form.get("footnote_letter", "")).strip()
            content = str(form.get("footnote_content", "")).strip()
            wb.state.footnote_custom_prompt = str(
                form.get("footnote_custom_prompt", wb.state.footnote_custom_prompt)
            ).strip()
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


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/editorial", response_class=HTMLResponse)
async def editorial_assistant(
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
        wb.save_editorial_prompts(
            {
                "grammar": str(form.get("editorial_prompt_grammar", "")).strip(),
                "concise": str(form.get("editorial_prompt_concise", "")).strip(),
                "scholarly": str(form.get("editorial_prompt_scholarly", "")).strip(),
                "copyable": str(form.get("editorial_prompt_copyable", "")).strip(),
            }
        )
        wb.state.editorial_input = str(form.get("editorial_input", "")).strip()
        action = str(form.get("action", "")).strip().lower()
        if action == "clear":
            wb.state.editorial_output = ""
            wb.state.editorial_output_label = ""
        else:
            mode = action or "grammar"
            wb.state.editorial_output = wb.run_editorial_enhancement(
                source_text=wb.state.editorial_input,
                mode=mode,
                context_label="general editorial prose",
                prompt_override=str(form.get(f"editorial_prompt_{mode}", "")).strip(),
            )
            wb.state.editorial_output_label = wb.editorial_mode_label(mode)
            wb.notify(f"{wb.state.editorial_output_label} ready.")
        wb.activate_tab("draft")
        wb.save_state()
        return render_workspace(request, wb, active_tab="draft", partial=True)
    except Exception as exc:
        return render_workspace_error(request, wb, exc, active_tab="draft")


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/editorial/enhance-field", response_class=JSONResponse)
async def enhance_field(
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
        prompt_updates = {
            "grammar": str(form.get("editorial_prompt_grammar", "")).strip(),
            "concise": str(form.get("editorial_prompt_concise", "")).strip(),
            "scholarly": str(form.get("editorial_prompt_scholarly", "")).strip(),
            "copyable": str(form.get("editorial_prompt_copyable", "")).strip(),
        }
        wb.save_editorial_prompts(prompt_updates)
        mode = str(form.get("mode", "")).strip().lower()
        custom_prompt = str(form.get("custom_prompt", "")).strip()
        context_label = str(form.get("context_label", "")).strip() or "editorial prose"
        prompt_override = str(form.get("prompt_override", "")).strip()
        source_text = str(form.get("text", "")).strip()
        result = wb.run_editorial_enhancement(
            source_text=source_text,
            mode=mode,
            context_label=context_label,
            prompt_override=prompt_override,
            custom_prompt=custom_prompt,
        )
        wb.save_state()
        return JSONResponse({"ok": True, "text": result, "label": wb.editorial_mode_label(mode)})
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)


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
        had_writes = bool(wb.build_commit_plan())
        wb.cmd_commit([])
        
        # After cmd_commit, we clear the draft which sets the state to 'committed'
        wb.clear_current_draft_after_commit()
        
        # Double check it is indeed committed
        wb.state.browser_editor_state = "committed"
        wb.state.browser_editor_mode = "review"
        
        wb.save_state()
        return render_editor_panel(request, wb)
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


@app.post("/workspace/{testament}/{book}/{chapter}/{chunk_key}/chat/delete/{index}", response_class=HTMLResponse)
def delete_chat_message(
    request: Request, testament: str, book: str, chapter: int, chunk_key: str, index: int
):
    """Delete a chat message and every later message in the same conversation."""
    wb = controller()
    try:
        book = resolve_book_name(wb, testament, book)
        wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
        messages = wb.state.chat_messages
        if 0 <= index < len(messages):
            role = messages[index].get("role", "")
            removed_count = len(messages) - index
            del messages[index:]
            wb.history_entries.append(
                {
                    "title": "Chat",
                    "body": f"Deleted {role or 'chat'} message and {removed_count - 1} later message(s).",
                    "accent": "blue",
                }
            )
            wb.persist_current_chunk_session()
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


@app.get("/workspace/{testament}/{book}/{chapter}/{chunk_key}/json-book-tree", response_class=JSONResponse)
def json_book_tree(request: Request, testament: str, book: str, chapter: int, chunk_key: str):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
    return JSONResponse(book_json_tree_payload(wb, testament, book, chapter))


@app.get("/workspace/{testament}/{book}/{chapter}/{chunk_key}/json-book-chapter/{target_chapter}", response_class=JSONResponse)
def json_book_chapter(
    request: Request,
    testament: str,
    book: str,
    chapter: int,
    chunk_key: str,
    target_chapter: int,
):
    wb = controller()
    book = resolve_book_name(wb, testament, book)
    wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
    return book_json_chapter_payload(wb, book, target_chapter)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    wb = controller()
    return render_page(
        request,
        "settings.html",
        {
            "settings_config": wb.settings_payload(),
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
        wb.save_web_settings(
            {
                "endpoint_provider": str(form.get("endpoint_provider", "local")).strip(),
                "local_base_url": str(form.get("local_base_url", wb.llm.base_url)).strip(),
                "local_api_key": str(form.get("local_api_key", "")).strip(),
                "local_model": str(form.get("local_model", "")).strip(),
                "cloud_base_url": str(form.get("cloud_base_url", "")).strip(),
                "cloud_api_key": str(form.get("cloud_api_key", "")).strip(),
                "cloud_model": str(form.get("cloud_model", "")).strip(),
            }
        )
        wb.notify("Settings saved.")
    except Exception as exc:
        wb.print_error(str(exc))
    if request.headers.get("hx-request"):
        return render_page(
            request,
            "partials/settings_dialog_body.html",
            {
                "settings_config": wb.settings_payload(),
                "endpoint_url": wb.llm.base_url,
                "flash_messages": wb.flash_messages,
                "model_names": wb.safe_list_models(),
            },
        )
    return render_page(
        request,
        "settings.html",
        {
            "settings_config": wb.settings_payload(),
            "endpoint_url": wb.llm.base_url,
            "flash_messages": wb.flash_messages,
            "model_names": wb.safe_list_models(),
        },
    )


@app.post("/settings/test-endpoint", response_class=HTMLResponse)
def settings_test_endpoint(request: Request):
    wb = controller()
    wb.refresh_active_endpoint()
    models = wb.safe_list_models()
    if models:
        wb.notify(f"Endpoint reachable. Models: {', '.join(models[:3])}")
    return render_page(
        request,
        "settings.html",
        {
            "settings_config": wb.settings_payload(),
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
    work_dir = wb.paths.repo_root
    t0 = time.monotonic()
    cmd = [
        str(wb.preferred_python()),
        str(wb.paths.repo_root / "src" / "ttt_epub" / "generate_epub.py"),
        "--md",
        "--txt",
    ]
    try:
        result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, check=False)
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
