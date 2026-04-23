import chainlit as cl
import sys
import time
import re

from ttt_core.llm.token_budget import estimate_tokens, pack_messages


def _ensure_active_chunk(wb) -> bool:
    if wb.require_open_chunk():
        return True

    try:
        testament = wb.state.wizard_testament or wb.testament() or "new"
        book = wb.state.book or ""
        chapter = wb.state.chapter or 0
        chunk_key = wb.current_chunk_key()
        if book and chapter:
            valid_chunks = {
                f"{item.start_verse}-{item.end_verse}"
                for item in wb.chapter_chunks(testament, book, chapter)
            }
            if chunk_key and (not valid_chunks or chunk_key in valid_chunks):
                wb.open_or_select_chunk(testament, book, chapter, chunk_key, announce=False)
                wb.save_state()
                return wb.require_open_chunk()
            first_chunk = wb.first_chunk_key(testament, book, chapter)
            if first_chunk:
                wb.open_or_select_chunk(testament, book, chapter, first_chunk, announce=False)
                wb.save_state()
                return wb.require_open_chunk()
            wb.select_chapter(testament, book, chapter)
            wb.save_state()
            return wb.require_open_chunk()

        catalog = wb.navigator_catalog()
        for nav_testament in ("old", "new"):
            books = catalog.get(nav_testament, [])
            if not isinstance(books, list):
                continue
            for entry in books:
                if not isinstance(entry, dict):
                    continue
                nav_book = str(entry.get("name", "")).strip()
                if not nav_book:
                    continue
                chapter_value = entry.get("first_ready_chapter")
                if chapter_value is None:
                    chapter_value = entry.get("first_chapter")
                try:
                    nav_chapter = int(chapter_value)
                except (TypeError, ValueError):
                    continue
                nav_chunk = wb.first_chunk_key(nav_testament, nav_book, nav_chapter)
                if nav_chunk:
                    wb.open_or_select_chunk(nav_testament, nav_book, nav_chapter, nav_chunk, announce=False)
                else:
                    wb.select_chapter(nav_testament, nav_book, nav_chapter)
                wb.save_state()
                return wb.require_open_chunk()
    except Exception:
        return False

    return wb.require_open_chunk()


def _format_thinking_duration(seconds: float | int | None) -> str:
    total = max(0, int(round(float(seconds or 0))))
    if total >= 60:
        minutes, secs = divmod(total, 60)
        minute_label = "minute" if minutes == 1 else "minutes"
        second_label = "second" if secs == 1 else "seconds"
        return f"{minutes} {minute_label} {secs} {second_label}"
    second_label = "second" if total == 1 else "seconds"
    return f"{total} {second_label}"


def _thinking_summary_html(streaming: bool = False, duration_seconds: float | int | None = None) -> str:
    classes = ' class="ttt-thinking-summary is-streaming"' if streaming else ' class="ttt-thinking-summary"'
    if streaming:
        return f"<summary{classes}><span class=\"ttt-thinking-pipe\">|</span><span> Thinking</span><span class=\"ttt-thinking-dots\">...</span></summary>"
    duration = _format_thinking_duration(duration_seconds or 0)
    return f"<summary{classes}><span class=\"ttt-thinking-pipe\">|</span><span> Thought for {duration}</span></summary>"


def _thinking_block(content: str, duration_seconds: float | int | None = None) -> str:
    return f"<details class=\"ttt-thinking-block\">{_thinking_summary_html(duration_seconds=duration_seconds)}\n\n{content.strip()}\n\n</details>"


def _streaming_thinking_block(content: str) -> str:
    return f"<details class=\"ttt-thinking-block\">{_thinking_summary_html(streaming=True)}\n\n{content.strip()}\n\n</details>"


_THINK_OPEN_RE = re.compile(r"<think(?:\s+duration=\"(?P<duration>[0-9.]+)\")?>")


def _annotate_thinking_durations(text: str, durations: list[float]) -> str:
    index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal index
        if match.group("duration") is not None:
            return match.group(0)
        if index >= len(durations):
            return match.group(0)
        duration = max(0.0, float(durations[index]))
        index += 1
        return f'<think duration="{duration:.3f}">'

    return _THINK_OPEN_RE.sub(replace, text or "")


def _reply_display_parts(text: str):
    token = text or ""
    while token:
        match = _THINK_OPEN_RE.search(token)
        if not match:
            if token:
                yield "answer", token
            break
        before = token[: match.start()]
        if before:
            yield "answer", before
        duration = float(match.group("duration")) if match.group("duration") is not None else None
        after = token[match.end():]
        thinking, end_marker, token = after.partition("</think>")
        if thinking:
            yield "thinking", thinking, duration
        if not end_marker:
            break


async def _stream_model_reply(wb, messages):
    full_reply = []
    assistant_msg = None
    thinking_msg = None
    error_occurred = False
    is_thinking = False
    thinking_tokens = []
    thinking_started_at = None
    thinking_durations: list[float] = []

    async def ensure_assistant_msg():
        nonlocal assistant_msg
        if assistant_msg is None:
            assistant_msg = cl.Message(content="")
            await assistant_msg.send()
        return assistant_msg

    async def ensure_thinking_msg():
        nonlocal thinking_msg, thinking_started_at
        if thinking_msg is None:
            thinking_started_at = time.monotonic()
            thinking_msg = cl.Message(content=_streaming_thinking_block(""))
            await thinking_msg.send()
        return thinking_msg

    async def update_thinking_msg():
        msg = await ensure_thinking_msg()
        msg.content = _streaming_thinking_block("".join(thinking_tokens))
        await msg.update()

    async def finalize_thinking_msg():
        nonlocal thinking_msg, thinking_started_at
        if thinking_msg is None:
            return
        duration = time.monotonic() - thinking_started_at if thinking_started_at is not None else None
        if duration is not None:
            thinking_durations.append(duration)
        thinking_msg.content = _thinking_block("".join(thinking_tokens), duration)
        await thinking_msg.update()
        thinking_msg = None
        thinking_started_at = None

    try:
        for raw_token in wb.llm.stream_generation(
            wb.active_model_name(),
            messages,
            temperature=0.7,
            max_tokens=None,
        ):
            if raw_token.startswith("[ERROR]"):
                full_reply.append(raw_token)
                error_occurred = True
                break

            full_reply.append(raw_token)
            token = raw_token

            while token:
                if is_thinking:
                    before, marker, after = token.partition("</think>")
                    if before:
                        thinking_tokens.append(before)
                        await update_thinking_msg()
                    if marker:
                        is_thinking = False
                        await finalize_thinking_msg()
                        thinking_tokens = []
                        token = after
                        continue
                    break

                before, marker, after = token.partition("<think>")
                if before:
                    msg = await ensure_assistant_msg()
                    await msg.stream_token(before)
                if marker:
                    is_thinking = True
                    await ensure_thinking_msg()
                    token = after
                    continue
                break

        if is_thinking and thinking_tokens:
            await finalize_thinking_msg()

    except Exception as exc:
        print(f"[CHAINLIT ERROR] {exc}", file=sys.stderr)
        full_reply.append(f"\n[ERROR] {exc}")
        error_occurred = True

    return _annotate_thinking_durations("".join(full_reply).strip(), thinking_durations), error_occurred, assistant_msg


@cl.on_chat_start
async def on_chat_start():
    from ttt_workbench.webapp import controller
    chainlit_session_id = cl.user_session.get("id")
    # Use a dedicated controller per Chainlit session so chat state is isolated
    wb = controller(session_id=chainlit_session_id)
    current = wb.current_chunk_session()
    current["chainlit_session_id"] = chainlit_session_id
    wb.persist_current_chunk_session()
    cl.user_session.set("workbench_chat_session_id", wb.active_chat_session_id())
    
    # Send existing messages to the Chainlit UI
    if wb.state.chat_messages:
        for msg in wb.state.chat_messages:
            author = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            if msg["role"] != "assistant" or "<think" not in content:
                msg_type = "user_message" if msg["role"] == "user" else "assistant_message"
                await cl.Message(content=content, author=author, type=msg_type).send()
                continue
            for part in _reply_display_parts(content):
                part_type, part_content, *meta = part
                if part_type == "thinking":
                    duration = meta[0] if meta else None
                    await cl.Message(content=_thinking_block(part_content, duration), author=author).send()
                elif part_content.strip():
                    await cl.Message(content=part_content.strip(), author=author).send()

@cl.on_message
async def on_message(message: cl.Message):
    from ttt_workbench.webapp import controller
    chainlit_session_id = cl.user_session.get("id")
    wb = controller(session_id=chainlit_session_id)

    if not _ensure_active_chunk(wb):
        await cl.Message(content="Error: No active chunk is open in the workbench.").send()
        return

    # Assemble server-side chat context from persisted selections on the first message.
    session = wb.current_chunk_session()
    user_content = message.content
    if not session.get("context_loaded"):
        context_prompt = wb.build_chat_context_prompt()
        if context_prompt:
            user_content = context_prompt + "\n\n" + user_content

    prior_messages = [
        {"role": item["role"], "content": item["content"]}
        for item in wb.state.chat_messages
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    current_msg = {"role": "user", "content": user_content}
    from ttt_core.llm.provider import _infer_profile
    model_profile = _infer_profile(wb.llm.model_name)
    context_overhead = estimate_tokens(context_prompt) if (not session.get("context_loaded") and context_prompt) else 0
    messages = pack_messages(
        prior_messages,
        current_msg,
        context_window=model_profile.context_window,
        system_overhead=context_overhead,
    )

    wb.state.chat_messages.append({"role": "user", "content": user_content})
    wb.save_state()
    wb.refresh_active_endpoint()

    reply, error_occurred, msg = await _stream_model_reply(wb, messages)

    if error_occurred:
        if msg is None:
            msg = cl.Message(content="")
            await msg.send()
        wb.history_entries.append({"title": "Chat error", "body": reply[:160], "accent": "red"})
        wb.print_error(wb.explain_llm_failure(reply))
        await msg.stream_token(f"\n\n**Error:** {wb.explain_llm_failure(reply)}")
    elif reply:
        wb.state.chat_messages.append({"role": "assistant", "content": reply})
        wb.history_entries.append({"title": "Chat", "body": reply[:160], "accent": "blue"})

    wb.save_state()

    session["context_loaded"] = True
    if not session.get("context_snapshot"):
        session["context_snapshot"] = wb.session_context_snapshot()
    wb.persist_current_chunk_session()
    wb.prepare_browser_commit_state()
    wb.save_state()

    if msg is not None:
        await msg.update()
