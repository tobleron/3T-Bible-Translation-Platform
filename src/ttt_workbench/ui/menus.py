from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import WorkbenchApp


class MenuNavigationMixin:
    """Mixin providing menu navigation and screen action handling."""

    def current_screen_menu_items(self: WorkbenchApp) -> list[dict[str, str]]:
        screen = self.state.screen
        if screen == "HOME":
            items = [
                {"label": "New Session", "desc": "Choose testament, book, chapter, and chunk to work on.", "action": "home:new"},
            ]
            if self.resume_available():
                items.append({"label": "Resume Session", "desc": f"Continue {self.current_chunk_label()}.", "action": "home:resume"})
            items.extend(
                [
                    {"label": "Preview EPUB", "desc": "Open EPUB tools and build from committed JSON.", "action": "home:epub"},
                    {"label": "Tools", "desc": "Show advanced tools, help, and maintenance actions.", "action": "home:tools"},
                    {"label": "Quit", "desc": "Save session state and exit the workbench.", "action": "home:quit"},
                ]
            )
            return items
        if screen == "NEW_SESSION_TESTAMENT":
            labels = {"old": "Old Testament", "new": "New Testament"}
            descs = {
                "old": "Hebrew-first workflow, with LXX shown as a comparison witness.",
                "new": "Greek-first workflow using SBLGNT as the source base.",
            }
            return [{"label": labels.get(item, item.title()), "desc": descs.get(item, ""), "action": f"testament:{item}"} for item in self.available_testaments()]
        if screen == "NEW_SESSION_BOOK":
            testament = self.state.wizard_testament or "new"
            return [{"label": book, "desc": f"{testament.title()} Testament book available for translation work.", "action": f"book:{book}"} for book in self.available_books(testament)]
        if screen == "NEW_SESSION_CHAPTER":
            testament = self.state.wizard_testament or "new"
            book = self.state.wizard_book or ""
            return [{"label": f"Chapter {chapter}", "desc": f"Open guided chunk selection for {book} {chapter}.", "action": f"chapter:{chapter}"} for chapter in self.available_chapters(testament, book)]
        if screen == "CHUNK_PICKER":
            items = []
            for index, chunk in enumerate(self.state.chunk_suggestions, start=1):
                desc = f"{chunk.type} \u00b7 {chunk.title or 'Untitled chunk'}"
                if chunk.reason:
                    desc += f" \u00b7 {chunk.reason}"
                items.append({"label": f"{chunk.start_verse}-{chunk.end_verse}", "desc": desc, "action": f"chunk:{index}"})
            items.extend(
                [
                    {"label": "Refresh Suggestions", "desc": "Ask the model to regenerate chunk suggestions for this chapter window.", "action": "chunk:refresh"},
                    {"label": "Back", "desc": "Return to chapter selection.", "action": "nav:chapter"},
                ]
            )
            return items
        if screen == "STUDY":
            return [
                {"label": "Start Chat", "desc": "Discuss the chunk and shape the translation draft.", "action": "study:chat"},
                {"label": "Refresh Analysis", "desc": "Ask Qwen for a focused analysis of the current chunk.", "action": "study:analysis"},
                {"label": "Back to Chunks", "desc": "Return to the guided chunk picker for this chapter.", "action": "nav:chunks"},
            ]
        if screen == "CHAT":
            has_draft = bool(self.state.draft_chunk)
            return [
                {"label": "Generate Initial Draft" if not has_draft else "Run Review", "desc": "Use the current study context to generate or review the draft.", "action": "chat:generate" if not has_draft else "chat:review"},
                {"label": "Back to Study", "desc": "Leave chat and return to the study screen.", "action": "nav:study"},
            ]
        if screen == "REVIEW":
            return [
                {"label": "Revise in Chat", "desc": "Return review notes to chat and keep refining the draft.", "action": "review:revise"},
                {"label": "Stage Text", "desc": "Stage the reviewed verses for commit.", "action": "review:stage-text"},
                {"label": "Stage Title", "desc": "Stage the current title for commit.", "action": "review:stage-title"},
                {"label": "Add Justification", "desc": "Open justification drafting for the reviewed range.", "action": "review:justify"},
                {"label": "Commit Preview", "desc": "Inspect pending changes before writing JSON.", "action": "review:commit-preview"},
                {"label": "Back to Study", "desc": "Return to the study screen.", "action": "nav:study"},
            ]
        if screen == "JUSTIFY":
            return [
                {"label": "Autofill", "desc": "Ask Qwen to draft the current justification entry.", "action": "justify:autofill"},
                {"label": "Show Draft", "desc": "Display the current justification draft.", "action": "justify:show"},
                {"label": "Stage Justification", "desc": "Stage the justification and return to review.", "action": "justify:stage"},
                {"label": "Back to Review", "desc": "Leave justification mode without staging.", "action": "nav:review"},
            ]
        if screen == "COMMIT_PREVIEW":
            return [
                {"label": "Validate", "desc": "Validate the pending JSON structures before commit.", "action": "commit:validate"},
                {"label": "Commit", "desc": "Write the staged changes to the final JSON files.", "action": "commit:write"},
                {"label": "Generate EPUB", "desc": "Preview the committed result in the EPUB pipeline.", "action": "commit:epub"},
                {"label": "Next Chunk", "desc": "Return to chunk selection for the current chapter.", "action": "nav:chunks"},
                {"label": "Back to Review", "desc": "Return to the review screen.", "action": "nav:review"},
            ]
        if screen == "EPUB_PREVIEW":
            return [
                {"label": "Generate EPUB", "desc": "Build EPUB output from committed JSON files.", "action": "epub:generate"},
                {"label": "Back Home", "desc": "Return to the home screen.", "action": "nav:home"},
            ]
        if screen == "TOOLS":
            return [
                {"label": "Command Help", "desc": "Open the slash-command help reference in the history panel.", "action": "tools:help"},
                {"label": "Command History", "desc": "Show recent command timings and outcomes.", "action": "tools:history"},
                {"label": "Terminology Ledger", "desc": "Show approved consistency decisions.", "action": "tools:terms"},
                {"label": "Repair Queue", "desc": "Inspect pending repair actions for the current chapter.", "action": "tools:repair"},
                {"label": "Back Home", "desc": "Return to the launch screen.", "action": "nav:home"},
            ]
        return []

    def normalize_menu_index(self: WorkbenchApp) -> None:
        items = self.current_screen_menu_items()
        if not items:
            self.state.menu_index = 0
            return
        self.state.menu_index = max(0, min(self.state.menu_index, len(items) - 1))

    def move_menu_selection(self: WorkbenchApp, delta: int) -> None:
        items = self.current_screen_menu_items()
        if not items:
            return
        self.normalize_menu_index()
        self.state.menu_index = (self.state.menu_index + delta) % len(items)
        self.flush_ui()

    def activate_selected_menu_item(self: WorkbenchApp) -> None:
        items = self.current_screen_menu_items()
        if not items:
            return
        self.normalize_menu_index()
        action = items[self.state.menu_index]["action"]
        self.handle_screen_action(action)

    def handle_screen_action(self: WorkbenchApp, action: str) -> None:
        if action == "home:new":
            self.state.wizard_testament = None
            self.state.wizard_book = None
            self.state.wizard_chapter = None
            self.set_screen("NEW_SESSION_TESTAMENT")
            return
        if action == "home:resume":
            if self.resume_available():
                self.set_screen("STUDY")
            return
        if action == "home:epub":
            self.set_screen("EPUB_PREVIEW")
            return
        if action == "home:tools":
            self.set_screen("TOOLS")
            return
        if action == "home:quit":
            self.cmd_quit([])
            return
        if action.startswith("testament:"):
            self.state.wizard_testament = action.split(":", 1)[1]
            self.state.wizard_book = None
            self.state.wizard_chapter = None
            self.set_screen("NEW_SESSION_BOOK")
            return
        if action.startswith("book:"):
            self.state.wizard_book = action.split(":", 1)[1]
            self.state.wizard_chapter = None
            self.set_screen("NEW_SESSION_CHAPTER")
            return
        if action.startswith("chapter:"):
            chapter = int(action.split(":", 1)[1])
            self.state.wizard_chapter = chapter
            self.cmd_open([self.state.wizard_book or "", str(chapter)])
            return
        if action.startswith("chunk:") and action != "chunk:refresh":
            index = action.split(":", 1)[1]
            self.cmd_chunk_use([index])
            return
        if action == "chunk:refresh":
            self.cmd_chunk_refresh([])
            return
        if action == "study:chat":
            self.cmd_chat([])
            return
        if action == "study:analysis":
            start_verse, end_verse = self.current_range()
            self.cmd_analysis(["refresh", f"{start_verse}-{end_verse}"])
            self.set_screen("STUDY", mode="COMMAND", reset_menu=False)
            return
        if action == "chat:generate":
            self.chat_turn("Give me an initial draft for this chunk.")
            self.set_screen("CHAT", mode="CHAT", reset_menu=False)
            return
        if action == "chat:review":
            start_verse, end_verse = self.current_range()
            self.cmd_finalize([f"{start_verse}-{end_verse}"])
            return
        if action == "review:revise":
            start_verse, end_verse = self.current_range()
            self.cmd_revise([f"{start_verse}-{end_verse}"])
            return
        if action == "review:stage-text":
            start_verse, end_verse = self.current_range()
            self.cmd_stage([f"{start_verse}-{end_verse}"])
            return
        if action == "review:stage-title":
            self.cmd_title(["stage"])
            return
        if action == "review:justify":
            start_verse, end_verse = self.current_range()
            self.cmd_justify([f"{start_verse}-{end_verse}"])
            return
        if action == "review:commit-preview":
            self.set_screen("COMMIT_PREVIEW")
            return
        if action == "justify:autofill":
            self.cmd_jautofill([])
            return
        if action == "justify:show":
            self.cmd_jshow([])
            return
        if action == "justify:stage":
            self.cmd_jstage([])
            return
        if action == "commit:validate":
            self.cmd_validate([])
            return
        if action == "commit:write":
            self.cmd_commit([])
            return
        if action == "commit:epub" or action == "epub:generate":
            self.cmd_epub_gen([])
            return
        if action == "tools:help":
            self.cmd_help([])
            return
        if action == "tools:history":
            self.cmd_history([])
            return
        if action == "tools:terms":
            self.cmd_terms(["show"])
            return
        if action == "tools:repair":
            self.cmd_repair([])
            return
        if action == "nav:chapter":
            self.set_screen("NEW_SESSION_CHAPTER")
            return
        if action == "nav:chunks":
            self.set_screen("CHUNK_PICKER")
            return
        if action == "nav:study":
            self.set_screen("STUDY", mode="COMMAND")
            return
        if action == "nav:review":
            self.set_screen("REVIEW", mode="COMMAND")
            return
        if action == "nav:home":
            self.set_screen("HOME", mode="COMMAND")

    def back_screen(self: WorkbenchApp) -> None:
        screen = self.state.screen
        if screen == "HOME":
            return
        if screen == "NEW_SESSION_TESTAMENT":
            self.set_screen("HOME")
            return
        if screen == "NEW_SESSION_BOOK":
            self.set_screen("NEW_SESSION_TESTAMENT")
            return
        if screen == "NEW_SESSION_CHAPTER":
            self.set_screen("NEW_SESSION_BOOK")
            return
        if screen == "CHUNK_PICKER":
            self.set_screen("NEW_SESSION_CHAPTER")
            return
        if screen == "STUDY":
            self.set_screen("CHUNK_PICKER")
            return
        if screen == "CHAT":
            self.set_screen("STUDY", mode="COMMAND")
            return
        if screen == "REVIEW":
            self.set_screen("STUDY", mode="COMMAND")
            return
        if screen == "JUSTIFY":
            self.set_screen("REVIEW", mode="COMMAND")
            return
        if screen == "COMMIT_PREVIEW":
            self.set_screen("REVIEW", mode="COMMAND")
            return
        if screen in {"EPUB_PREVIEW", "TOOLS"}:
            self.set_screen("HOME", mode="COMMAND")
