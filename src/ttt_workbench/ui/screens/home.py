from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class HomeScreenMixin:
    """Mixin providing Home screen rendering and navigation helpers."""

    def resume_available(self) -> bool:
        return bool(self.state.book and self.state.chapter and self.state.chunk_start and self.state.chunk_end)

    def has_open_chunk(self) -> bool:
        return self.resume_available()

    def available_testaments(self) -> list[str]:
        catalog = self.bible_repo.catalog()
        return [item for item in ("old", "new") if catalog.get(item)]

    def available_books(self, testament: str | None = None) -> list[str]:
        testament_name = testament or self.state.wizard_testament or "new"
        return self.bible_repo.books_for_testament(testament_name)

    def available_chapters(self, testament: str | None = None, book: str | None = None) -> list[int]:
        testament_name = testament or self.state.wizard_testament or "new"
        book_name = book or self.state.wizard_book or ""
        return self.bible_repo.chapters_for_book(testament_name, book_name)

    def current_chunk_label(self) -> str:
        if self.state.book and self.state.chapter and self.state.chunk_start and self.state.chunk_end:
            return f"{self.state.book} {self.state.chapter}:{self.state.chunk_start}-{self.state.chunk_end}"
        if self.state.wizard_book and self.state.wizard_chapter:
            return f"{self.state.wizard_book} {self.state.wizard_chapter}"
        return "No chunk selected"

    def home_stage_summary_lines(self) -> list[str]:
        screen = self.state.screen
        busy_prefix: list[str] = []
        if self.state.busy_state:
            self.state.busy_state.refresh_elapsed()
            busy_prefix = [self.state.busy_state.message, f"Elapsed: {self.state.busy_state.elapsed_display}", ""]
        if screen == "HOME":
            lines = ["Start a guided translation session or resume the last open chunk."]
            if self.resume_available():
                lines.append(f"Resume available: {self.current_chunk_label()}")
            return busy_prefix + lines
        if screen == "NEW_SESSION_TESTAMENT":
            return busy_prefix + ["Choose which testament workflow to enter for this session."]
        if screen == "NEW_SESSION_BOOK":
            testament = (self.state.wizard_testament or "new").title()
            return busy_prefix + [f"{testament} Testament selected.", "Choose a book from the available source-backed chapters."]
        if screen == "NEW_SESSION_CHAPTER":
            return busy_prefix + [f"Book: {self.state.wizard_book or '[none]'}", "Choose the chapter you want to segment into chunks."]
        return []

    def render_home_body(self):
        screen = self.state.screen
        blocks: list[object] = []

        if screen == "HOME":
            if self.resume_available():
                lines = [
                    "Choose how to begin.",
                    "",
                    f"Resume available: {self.current_chunk_label()}",
                ]
            else:
                lines = ["Choose how to begin."]
            blocks.append(self.line_block(lines))

        elif screen == "NEW_SESSION_TESTAMENT":
            blocks.append(
                self.line_block(
                    [
                        "Choose Testament",
                        "",
                        "Old Testament uses Hebrew first, with LXX as comparison.",
                        "New Testament uses SBLGNT Greek as the source base.",
                    ]
                )
            )
        elif screen == "NEW_SESSION_BOOK":
            testament = (self.state.wizard_testament or "new").title()
            blocks.append(
                self.line_block(
                    [
                        f"{testament} Testament",
                        "",
                        "Choose a book from the available source-backed chapters.",
                    ]
                )
            )
        elif screen == "NEW_SESSION_CHAPTER":
            book_name = self.state.wizard_book or "[none]"
            blocks.append(
                self.line_block(
                    [
                        f"Book: {book_name}",
                        "",
                        "Choose the chapter you want to segment into chunks.",
                    ]
                )
            )

        return blocks
