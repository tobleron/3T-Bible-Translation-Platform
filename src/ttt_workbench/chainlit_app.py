import chainlit as cl
import sys


def _thinking_block(content: str) -> str:
    return f"<details><summary>Thinking..</summary>\n\n{content.strip()}\n\n</details>"


def _streaming_thinking_block(content: str) -> str:
    return f"<details open><summary>Thinking..</summary>\n\n{content.strip()}\n\n</details>"


def _reply_display_parts(text: str):
    token = text or ""
    while token:
        before, marker, after = token.partition("<think>")
        if before:
            yield "answer", before
        if not marker:
            break
        thinking, end_marker, token = after.partition("</think>")
        if thinking:
            yield "thinking", thinking
        if not end_marker:
            break


async def _stream_model_reply(wb, messages):
    full_reply = []
    assistant_msg = None
    thinking_msg = None
    error_occurred = False
    is_thinking = False
    thinking_tokens = []

    async def ensure_assistant_msg():
        nonlocal assistant_msg
        if assistant_msg is None:
            assistant_msg = cl.Message(content="")
            await assistant_msg.send()
        return assistant_msg

    async def ensure_thinking_msg():
        nonlocal thinking_msg
        if thinking_msg is None:
            thinking_msg = cl.Message(content=_streaming_thinking_block(""))
            await thinking_msg.send()
        return thinking_msg

    async def update_thinking_msg():
        msg = await ensure_thinking_msg()
        msg.content = _streaming_thinking_block("".join(thinking_tokens))
        await msg.update()

    async def finalize_thinking_msg():
        nonlocal thinking_msg
        if thinking_msg is None:
            return
        thinking_msg.content = _thinking_block("".join(thinking_tokens))
        await thinking_msg.update()
        thinking_msg = None

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

    return "".join(full_reply).strip(), error_occurred, assistant_msg


@cl.on_chat_start
async def on_chat_start():
    from ttt_workbench.webapp import controller
    # Retrieve the state from global app controller
    wb = controller()
    chainlit_session_id = cl.user_session.get("id")
    current = wb.current_chunk_session()
    current["chainlit_session_id"] = chainlit_session_id
    wb.persist_current_chunk_session()
    cl.user_session.set("workbench_chat_session_id", wb.active_chat_session_id())
    
    # Send existing messages to the Chainlit UI
    if wb.state.chat_messages:
        for msg in wb.state.chat_messages:
            author = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            if msg["role"] != "assistant" or "<think>" not in content:
                await cl.Message(content=content, author=author).send()
                continue
            for part_type, part_content in _reply_display_parts(content):
                if part_type == "thinking":
                    await cl.Message(content=_thinking_block(part_content), author=author).send()
                elif part_content.strip():
                    await cl.Message(content=part_content.strip(), author=author).send()

@cl.on_message
async def on_message(message: cl.Message):
    from ttt_workbench.webapp import controller
    # Retrieve the state from global app controller
    wb = controller()
    
    if not wb.require_open_chunk():
        await cl.Message(content="Error: No active chunk is open in the workbench.").send()
        return

    # Send only the visible chat session history plus the user's current message.
    # Translation context belongs in the user-authored prompt, usually via Prompt Engineering injection.
    prior_messages = [
        {"role": item["role"], "content": item["content"]}
        for item in wb.state.chat_messages
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    messages = prior_messages[-20:] + [{"role": "user", "content": message.content}]

    wb.state.chat_messages.append({"role": "user", "content": message.content})
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
    
    session = wb.current_chunk_session()
    session["context_loaded"] = True
    if not session.get("context_snapshot"):
        session["context_snapshot"] = wb.session_context_snapshot()
    wb.persist_current_chunk_session()
    wb.prepare_browser_commit_state()
    wb.save_state()

    if msg is not None:
        await msg.update()
