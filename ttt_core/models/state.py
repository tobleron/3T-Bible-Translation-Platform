from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BusyState:
    """Tracks an in-progress long-running command for UI feedback."""

    label: str  # e.g. "chunk-suggest", "analysis", "finalize"
    message: str  # user-visible description
    start_time: float = field(default_factory=time.monotonic)
    elapsed_seconds: float = 0.0

    def refresh_elapsed(self) -> None:
        self.elapsed_seconds = time.monotonic() - self.start_time

    @property
    def elapsed_display(self) -> str:
        self.refresh_elapsed()
        secs = int(self.elapsed_seconds)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"


@dataclass
class CommandHistoryEntry:
    """Record of a completed command with timing info."""

    command: str
    status: str  # "success" | "error"
    duration_seconds: float
    message: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class TerminologyEntry:
    """One approved/rejected translation decision for a key term."""

    source_term: str  # e.g. "λόγος", "בְּרֵאשִׁית"
    translation: str  # approved English rendering
    status: str = "approved"  # "approved" | "rejected" | "pending"
    notes: str = ""
    added_at: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TerminologyEntry":
        return cls(**data)


@dataclass
class ReviewState:
    start_verse: int
    end_verse: int
    summary: str
    issues: list[str] = field(default_factory=list)
    verdict: str = "revise"
    title_review: str = ""
    justification_watch: list[str] = field(default_factory=list)


@dataclass
class PendingVerseUpdate:
    book: str
    chapter: int
    verses: dict[str, str]
    start_verse: int
    end_verse: int


@dataclass
class PendingTitleUpdate:
    book: str
    chapter: int
    start_verse: int
    end_verse: int
    title: str


@dataclass
class PendingJustificationUpdate:
    book: str
    chapter: int
    entry: dict[str, Any]


@dataclass
class PendingRepair:
    kind: str
    book: str
    chapter: int
    path: str
    notes: list[str] = field(default_factory=list)


@dataclass
class JustificationDraft:
    book: str
    chapter: int
    start_verse: int
    end_verse: int
    source_term: str = ""
    decision: str = ""
    reason: str = ""
    target: str = "verse_text"
    entry_id: str | None = None


@dataclass
class ChunkSuggestion:
    start_verse: int
    end_verse: int
    type: str
    title: str
    reason: str = ""


@dataclass
class ChunkSuggestionSet:
    book: str
    chapter: int
    window_start: int
    window_end: int
    prompt_version: str
    source: str = "model"
    generated_at: str = ""
    chunks: list[ChunkSuggestion] = field(default_factory=list)


@dataclass
class SessionState:
    session_id: str
    mode: str = "COMMAND"
    screen: str = "HOME"
    book: str | None = None
    chapter: int | None = None
    wizard_testament: str | None = None
    wizard_book: str | None = None
    wizard_chapter: int | None = None
    chunk_start: int | None = None
    chunk_end: int | None = None
    focus_start: int | None = None
    focus_end: int | None = None
    menu_index: int = 0
    history_panel_open: bool = False
    draft_chunk: dict[str, str] = field(default_factory=dict)
    draft_title: str = ""
    title_alternatives: list[str] = field(default_factory=list)
    chat_messages: list[dict[str, str]] = field(default_factory=list)
    analysis_cache: dict[str, str] = field(default_factory=dict)
    analysis_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_review: ReviewState | None = None
    pending_verse_updates: list[PendingVerseUpdate] = field(default_factory=list)
    pending_title_updates: list[PendingTitleUpdate] = field(default_factory=list)
    pending_justification_updates: list[PendingJustificationUpdate] = field(
        default_factory=list
    )
    pending_repairs: list[PendingRepair] = field(default_factory=list)
    justify_draft: JustificationDraft | None = None
    notifications: list[str] = field(default_factory=list)
    undo_stack: list[str] = field(default_factory=list)
    chunk_suggestion_window_start: int | None = None
    chunk_suggestion_window_end: int | None = None
    chunk_suggestions: list[ChunkSuggestion] = field(default_factory=list)
    # Task 001: Async command feedback
    busy_state: BusyState | None = field(default=None, repr=False, compare=False)
    command_history: list[CommandHistoryEntry] = field(
        default_factory=list, repr=False, compare=False
    )
    # Task 005: Terminology memory
    terminology_ledger: dict[str, TerminologyEntry] = field(default_factory=dict)
    # Task 007: Review history
    review_history: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        # Do not persist transient busy_state
        data.pop("busy_state", None)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SessionState":
        review = data.get("last_review")
        justify = data.get("justify_draft")
        # Task 005: Restore terminology ledger
        ledger_data = data.get("terminology_ledger", {})
        ledger = {}
        for key, entry_data in ledger_data.items():
            if isinstance(entry_data, dict):
                ledger[key] = TerminologyEntry.from_json(entry_data)
        return cls(
            session_id=data["session_id"],
            mode=data.get("mode", "COMMAND"),
            screen=data.get("screen", "HOME"),
            book=data.get("book"),
            chapter=data.get("chapter"),
            wizard_testament=data.get("wizard_testament"),
            wizard_book=data.get("wizard_book"),
            wizard_chapter=data.get("wizard_chapter"),
            chunk_start=data.get("chunk_start"),
            chunk_end=data.get("chunk_end"),
            focus_start=data.get("focus_start"),
            focus_end=data.get("focus_end"),
            menu_index=data.get("menu_index", 0),
            history_panel_open=data.get("history_panel_open", False),
            draft_chunk=data.get("draft_chunk", {}),
            draft_title=data.get("draft_title", ""),
            title_alternatives=data.get("title_alternatives", []),
            chat_messages=data.get("chat_messages", []),
            analysis_cache=data.get("analysis_cache", {}),
            analysis_meta=data.get("analysis_meta", {}),
            last_review=ReviewState(**review) if review else None,
            pending_verse_updates=[
                PendingVerseUpdate(**item)
                for item in data.get("pending_verse_updates", [])
            ],
            pending_title_updates=[
                PendingTitleUpdate(**item)
                for item in data.get("pending_title_updates", [])
            ],
            pending_justification_updates=[
                PendingJustificationUpdate(**item)
                for item in data.get("pending_justification_updates", [])
            ],
            pending_repairs=[
                PendingRepair(**item) for item in data.get("pending_repairs", [])
            ],
            justify_draft=JustificationDraft(**justify) if justify else None,
            notifications=data.get("notifications", []),
            undo_stack=data.get("undo_stack", []),
            chunk_suggestion_window_start=data.get("chunk_suggestion_window_start"),
            chunk_suggestion_window_end=data.get("chunk_suggestion_window_end"),
            chunk_suggestions=[
                ChunkSuggestion(**item) for item in data.get("chunk_suggestions", [])
            ],
            terminology_ledger=ledger,
        )
