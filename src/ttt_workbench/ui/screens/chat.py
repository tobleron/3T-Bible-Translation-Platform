from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ChatScreenMixin:
    """Mixin providing Chat screen rendering and conversation helpers."""

    def ledger_lines(self) -> list[str]:
        if not self.require_open_chunk():
            return []
        lines = []
        approved = [
            e for e in self.state.terminology_ledger.values()
            if e.status == "approved"
        ]
        if approved:
            lines.append("Approved terminology:")
            for entry in approved:
                lines.append(f"  {entry.source_term} \u2192 {entry.translation}")
            lines.append("")
        document = self.just_repo.load_document(self.state.book or "", self.state.chapter or 0).doc
        entries = document.get("justifications", [])
        for entry in entries[:12]:
            decision = entry.get("decision", "").strip()
            source_term = entry.get("source_term", "").strip()
            verses = ",".join(str(v) for v in entry.get("verses", []))
            if decision:
                label = f"{source_term} -> {decision}" if source_term else decision
                lines.append(f"[{verses}] {label}")
        return lines

    def open_reference_summary(self) -> list[str]:
        if not self.require_open_chunk():
            return []
        verse_map = self.bible_repo.verse_map(self.current_chapter())
        lines = []
        for verse in range(self.state.chunk_start or 1, (self.state.chunk_end or 1) + 1):
            draft = self.state.draft_chunk.get(str(verse))
            current = draft if draft is not None else verse_map.get(verse, "")
            prefix = f"{verse}. "
            lines.append(prefix + current)
        return lines

    def terminology_prompt_block(self) -> str:
        approved = [
            e for e in self.state.terminology_ledger.values()
            if e.status == "approved"
        ]
        if not approved:
            return "No approved terminology decisions yet."
        lines = ["Approved terminology (use these consistently):"]
        for entry in approved:
            lines.append(f"- {entry.source_term} \u2192 {entry.translation}")
            if entry.notes:
                lines.append(f"  Note: {entry.notes}")
        return "\n".join(lines)

    def build_chat_prompt(self, user_message: str) -> str:
        start = self.state.chunk_start
        end = self.state.chunk_end
        focus_start, focus_end = self.current_range()
        draft_lines = [f"{verse}. {text}" for verse, text in sorted((int(v), t) for v, t in self.state.draft_chunk.items())]
        history = "\n".join(f"{item['role'].upper()}: {item['content']}" for item in self.state.chat_messages[-8:])
        ledger = "\n".join(self.ledger_lines()) or "None yet."
        testament = self.testament()
        source_rule = "Base the drafting context on SBLGNT Greek only." if testament != "old" else "Base the drafting context on the Hebrew text first, while using the LXX only as a comparison witness when it adds useful insight."
        return f"""
You are assisting a Bible translator in an interactive terminal workbench.

Rules:
- {source_rule}
- Keep the title short, usable as a section heading, and plain English.
- If you update verses, only update the verses that truly need changes.
- Output strict JSON only with this shape:
{{
  "reply": "short editor-facing response",
  "title": "short title",
  "verses": [
    {{"verse": 1, "text": "..." }}
  ]
}}

Current chunk: {self.state.book} {self.state.chapter}:{start}-{end}
Current focus: verses {focus_start}-{focus_end}

Deterministic study context:
{self.study_context_block(start or 1, end or 1)}

Approved terminology ledger:
{ledger}

Terminology consistency (approved decisions only):
{self.terminology_prompt_block()}

Current draft:
{chr(10).join(draft_lines) if draft_lines else "No draft yet."}

Conversation so far:
{history or "None"}

User message:
{user_message}
""".strip()

    def build_initial_draft_prompt(self) -> str:
        start = self.state.chunk_start
        end = self.state.chunk_end
        ledger = "\n".join(self.ledger_lines()) or "None yet."
        testament = self.testament()
        source_rule = "Use SBLGNT as the only source text for this initial draft." if testament != "old" else "Use the Hebrew text as the primary source text for this initial OT draft. Keep the LXX only as a comparison witness, not as the default base."
        return f"""
You are drafting a Bible translation chunk for a human editor.
{source_rule}
Return strict JSON only:
{{
  "reply": "short drafting note",
  "title": "short chunk title",
  "verses": [
    {{"verse": 1, "text": "..." }}
  ],
  "title_alternatives": ["...", "..."]
}}

Chunk reference: {self.state.book} {self.state.chapter}:{start}-{end}

Deterministic study context:
{self.study_context_block(start or 1, end or 1)}

Approved terminology ledger:
{ledger}

Terminology consistency (approved decisions only):
{self.terminology_prompt_block()}
""".strip()

    def chat_turn(self, user_message: str) -> None:
        if not self.require_open_chunk():
            return
        if not self.state.draft_chunk and not self.state.chat_messages:
            self.notify("Generating initial draft from the current study context...")
            self.auto_generate_draft()
        prompt = self.build_chat_prompt(user_message)
        self.refresh_active_endpoint()
        payload, response, attempts = self.llm.complete_json(
            prompt,
            required_keys=["reply", "title", "verses"],
            temperature=0.3,
            max_tokens=2400,
            max_attempts=3,
        )
        self.state.chat_messages.append({"role": "user", "content": user_message})
        if isinstance(payload, dict):
            reply = payload.get("reply", "(no reply)")
            for verse in payload.get("verses", []):
                try:
                    number = int(verse["verse"])
                except Exception:
                    continue
                if "text" in verse:
                    self.state.draft_chunk[str(number)] = verse["text"].strip()
            title = payload.get("title", "").strip()
            if title:
                self.state.draft_title = title
            self.state.chat_messages.append({"role": "assistant", "content": reply})
            lines = [reply]
            updated = sorted(int(v["verse"]) for v in payload.get("verses", []) if isinstance(v, dict) and "verse" in v)
            if updated:
                lines.append("Updated verses: " + ", ".join(str(v) for v in updated))
            if title:
                lines.append(f"Title draft: {title}")
            if attempts > 1:
                lines.append(f"JSON compliance retries: {attempts}")
            self.emit(self.theme.panel("Chat Response", lines, accent="green"))
            return
        self.state.chat_messages.append({"role": "assistant", "content": response})
        self.emit(self.theme.panel("Chat Response", [response], accent="green"))

    def auto_generate_draft(self) -> None:
        self.refresh_active_endpoint()
        payload, response, attempts = self.llm.complete_json(
            self.build_initial_draft_prompt(),
            required_keys=["reply", "title", "verses"],
            temperature=0.25,
            max_tokens=2600,
            max_attempts=3,
        )
        if not isinstance(payload, dict):
            self.print_error("The endpoint did not return a draft in the expected JSON shape.")
            return
        for verse in payload.get("verses", []):
            try:
                self.state.draft_chunk[str(int(verse["verse"]))] = verse["text"].strip()
            except Exception:
                continue
        self.state.draft_title = payload.get("title", "").strip()
        self.state.title_alternatives = [item for item in payload.get("title_alternatives", []) if isinstance(item, str)]
        self.state.chat_messages.append({"role": "assistant", "content": payload.get("reply", "Initial draft generated.")})
        lines = [payload.get("reply", "Initial draft generated.")]
        if self.state.draft_title:
            lines.append(f"Title draft: {self.state.draft_title}")
        if self.state.title_alternatives:
            lines.append("Alternatives: " + " | ".join(self.state.title_alternatives[:3]))
        if attempts > 1:
            lines.append(f"JSON compliance retries: {attempts}")
        self.emit(self.theme.panel("Initial Draft", lines, accent="green"))

    def chat_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "CHAT":
            return busy_prefix + [f"Chunk: {self.current_chunk_label()}", "Type plain text below to talk to Qwen, or press Enter on an action when the input is empty."]
        return []

    def render_chat_body(self):
        lines = []
        if self.state.draft_title:
            lines.append(f"Draft title: {self.state.draft_title}")
        if self.state.chat_messages:
            lines.append("Recent conversation:")
            for item in self.state.chat_messages[-4:]:
                prefix = "You" if item["role"] == "user" else "Qwen"
                lines.append(f"{prefix}: {item['content']}")
        else:
            lines.append("No chat messages yet. Start by asking for a draft, a revision, or a wording explanation.")
        if self.state.draft_chunk:
            lines.append("")
            lines.append("Draft snapshot:")
            for verse in sorted(int(v) for v in self.state.draft_chunk.keys())[:6]:
                lines.append(f"{verse}. {self.state.draft_chunk[str(verse)]}")
            if len(self.state.draft_chunk) > 6:
                lines.append("\u2026")
        return [self.line_block(lines)]
