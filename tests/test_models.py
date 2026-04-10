"""Tests for ttt_core data models."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ttt_core.models.state import (
    SessionState,
    ChunkSuggestion,
    JustificationDraft,
    TerminologyEntry,
)


class TestSessionState:
    def test_default_values(self):
        state = SessionState(session_id="test123")
        assert state.mode == "COMMAND"
        assert state.screen == "HOME"
        assert state.book is None
        assert state.chunk_suggestions == []

    def test_to_json_and_back(self):
        state = SessionState(
            session_id="abc",
            mode="CHAT",
            book="Matthew",
            chapter=1,
            chunk_start=1,
            chunk_end=17,
        )
        data = state.to_json()
        restored = SessionState.from_json(data)
        assert restored.session_id == "abc"
        assert restored.mode == "CHAT"
        assert restored.book == "Matthew"
        assert restored.chapter == 1
        assert restored.chunk_start == 1
        assert restored.chunk_end == 17

    def test_busy_state_not_persisted(self):
        from ttt_core.models.state import BusyState
        state = SessionState(session_id="x")
        state.busy_state = BusyState(label="test", message="working")
        data = state.to_json()
        assert "busy_state" not in data


class TestChunkSuggestion:
    def test_creation(self):
        chunk = ChunkSuggestion(
            start_verse=1,
            end_verse=17,
            type="narrative",
            title="The Genealogy",
            reason="Covers the full genealogy section",
        )
        assert chunk.start_verse == 1
        assert chunk.type == "narrative"


class TestJustificationDraft:
    def test_defaults(self):
        draft = JustificationDraft(
            book="Matthew",
            chapter=1,
            start_verse=1,
            end_verse=17,
        )
        assert draft.source_term == ""
        assert draft.decision == ""
        assert draft.target == "verse_text"


class TestTerminologyEntry:
    def test_json_roundtrip(self):
        entry = TerminologyEntry(
            source_term="λόγος",
            translation="word",
            status="approved",
            notes="Test note",
        )
        data = entry.to_json()
        restored = TerminologyEntry.from_json(data)
        assert restored.source_term == "λόγος"
        assert restored.translation == "word"
        assert restored.status == "approved"
