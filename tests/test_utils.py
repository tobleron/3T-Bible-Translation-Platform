"""Tests for ttt_core utility functions."""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ttt_core.utils.common import (
    book_abbrev,
    book_ref_code,
    extract_json_payload,
    normalize_book_key,
    parse_range,
    parse_reference,
    repair_linewise_json_strings,
    utc_now,
)


class TestBookCodes:
    def test_matthew_ref_code(self):
        assert book_ref_code("Matthew") == "Mat"

    def test_genesis_ref_code(self):
        assert book_ref_code("Genesis") == "Gen"

    def test_unknown_book(self):
        assert book_ref_code("UnknownBook") == "Unk"

    def test_book_abbrev(self):
        assert book_abbrev("Matthew") == "MAT"
        assert book_abbrev("1 Corinthians") == "1CO"

    def test_normalize_book_key(self):
        assert normalize_book_key("1 Corinthians") == "1corinthians"
        assert normalize_book_key("Song of Songs") == "songofsongs"


class TestParseRange:
    def test_single_verse(self):
        assert parse_range("5") == (5, 5)

    def test_verse_range(self):
        assert parse_range("3-17") == (3, 17)

    def test_invalid_range(self):
        with pytest.raises(ValueError):
            parse_range("17-3")

    def test_empty_input(self):
        with pytest.raises(ValueError):
            parse_range("")

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_range("abc")


class TestParseReference:
    def test_combined_format(self):
        book, chapter, start, end = parse_reference(["Matthew:1:1-17"])
        assert book == "Matthew"
        assert chapter == 1
        assert start == 1
        assert end == 17

    def test_split_format(self):
        book, chapter, start, end = parse_reference(["Matthew", "1:1-17"])
        assert book == "Matthew"
        assert chapter == 1
        assert start == 1
        assert end == 17

    def test_missing_input(self):
        with pytest.raises(ValueError):
            parse_reference([])


class TestExtractJsonPayload:
    def test_simple_object(self):
        result = extract_json_payload('{"key": "value"}')
        assert result == {"key": "value"}

    def test_simple_array(self):
        result = extract_json_payload('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_text_with_json(self):
        result = extract_json_payload('Here is the data:\n{"key": "value"}\nDone.')
        assert result == {"key": "value"}

    def test_empty_input(self):
        assert extract_json_payload("") is None

    def test_invalid_json(self):
        assert extract_json_payload("{not valid json") is None


class TestRepairJsonStrings:
    def test_no_unescaped_quotes(self):
        text = '"key": "value"'
        repaired, changed = repair_linewise_json_strings(text)
        assert changed is False
        assert repaired == text

    def test_escapes_inner_quotes(self):
        text = '"key": "He said "hello""'
        repaired, changed = repair_linewise_json_strings(text)
        assert changed is True
        assert r'\"hello\"' in repaired

    def test_multiline(self):
        text = '"key1": "value1"\n"key2": "He said "hi""'
        repaired, changed = repair_linewise_json_strings(text)
        assert changed is True
        lines = repaired.splitlines()
        assert lines[0] == '"key1": "value1"'
        assert r'\"hi\"' in lines[1]


class TestUtcNow:
    def test_returns_iso_format(self):
        result = utc_now()
        assert result.endswith("Z")
        assert "T" in result
