import chainlit as cl
import sys

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
            # We skip thinking blocks in the history load for simplicity, 
            # or we could try to parse them back. For now, just the text.
            await cl.Message(content=msg["content"], author=author).send()

@cl.on_message
async def on_message(message: cl.Message):
    from ttt_workbench.webapp import controller
    # Retrieve the state from global app controller
    wb = controller()
    
    if not wb.require_open_chunk():
        await cl.Message(content="Error: No active chunk is open in the workbench.").send()
        return

    # Validations from the original chat implementation
    if not wb.state.draft_chunk and not wb.state.chat_messages and wb.chunk_has_committed_text():
        await cl.Message(content="Review text is committed. Use Revise in Draft before chatting.").send()
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

    # We will use Chainlit's streaming mechanism
    msg = cl.Message(content="")
    await msg.send()

    full_reply = []
    error_occurred = False
    
    try:
        is_thinking = False
        thinking_step = None
        
        for token in wb.llm.stream_generation(
            wb.active_model_name(),
            messages,
            temperature=0.7,
            max_tokens=None,
        ):
            if token.startswith("[ERROR]"):
                full_reply.append(token)
                error_occurred = True
                break
            
            full_reply.append(token)
            
            # Map <think> / </think> boundaries to Chainlit Steps
            if "<think>" in token:
                if not is_thinking:
                    is_thinking = True
                    thinking_step = cl.Step(name="Thinking Process", type="run")
                    await thinking_step.send()
                token = token.replace("<think>", "")
                if not token:
                    continue
            elif "</think>" in token:
                if is_thinking:
                    is_thinking = False
                    if thinking_step:
                        parts = token.split("</think>")
                        if parts[0]:
                            await thinking_step.stream_token(parts[0])
                        await thinking_step.update()
                        token = parts[1] if len(parts) > 1 else ""
                else:
                    token = token.replace("</think>", "")
                if not token:
                    continue
            
            if is_thinking and thinking_step:
                await thinking_step.stream_token(token)
            else:
                await msg.stream_token(token)
            
    except Exception as exc:
        print(f"[CHAINLIT ERROR] {exc}", file=sys.stderr)
        full_reply.append(f"\n[ERROR] {exc}")
        error_occurred = True

    reply = "".join(full_reply).strip()

    if error_occurred:
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

    await msg.update()
