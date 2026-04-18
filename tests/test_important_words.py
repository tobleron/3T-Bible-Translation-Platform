from __future__ import annotations

from types import SimpleNamespace

from ttt_workbench.important_words import (
    glossary_lemma_order,
    important_lemma_positions,
    important_lemmas,
    semantic_groups,
    verse_word_stats,
)


class FakeNlp:
    def __call__(self, text: str):
        del text
        return [
            SimpleNamespace(text="The", lemma_="the", pos_="DET", is_stop=True, is_alpha=True),
            SimpleNamespace(text="Spirit", lemma_="spirit", pos_="NOUN", is_stop=False, is_alpha=True),
            SimpleNamespace(text="hovered", lemma_="hover", pos_="VERB", is_stop=False, is_alpha=True),
            SimpleNamespace(text="over", lemma_="over", pos_="ADP", is_stop=True, is_alpha=True),
            SimpleNamespace(text="dark", lemma_="dark", pos_="ADJ", is_stop=False, is_alpha=True),
            SimpleNamespace(text="Spirit", lemma_="spirit", pos_="NOUN", is_stop=False, is_alpha=True),
            SimpleNamespace(text="water", lemma_="water", pos_="NOUN", is_stop=False, is_alpha=True),
        ]


class WordNlp:
    def __call__(self, text: str):
        return [
            SimpleNamespace(text=word, lemma_=word.lower(), pos_="NOUN", is_stop=False, is_alpha=True)
            for word in text.split()
        ]


class BeginningNlp:
    def __call__(self, text: str):
        del text
        return [
            SimpleNamespace(text="beginning", lemma_="begin", pos_="VERB", is_stop=False, is_alpha=True),
        ]


class SimilarityToken:
    has_vector = True
    vector_norm = 1.0

    def __init__(self, text: str) -> None:
        self.text = text

    def similarity(self, other: "SimilarityToken") -> float:
        related = {frozenset({"genealogy", "ancestry"})}
        return 0.9 if frozenset({self.text, other.text}) in related else 0.1


class SimilarityNlp:
    def __call__(self, text: str):
        return [SimilarityToken(text)]


def test_important_lemmas_keep_unique_content_lemmas_only() -> None:
    assert important_lemmas("ignored", FakeNlp()) == ["spirit", "hover", "dark", "water"]
    assert important_lemma_positions("ignored", FakeNlp()) == {
        "spirit": 1,
        "hover": 2,
        "dark": 4,
        "water": 6,
    }


def test_beginning_surface_is_not_reduced_to_begin() -> None:
    assert important_lemmas("beginning", BeginningNlp()) == ["beginning"]


def test_glossary_lemma_order_uses_original_gloss_sequence() -> None:
    assert glossary_lemma_order(["dark water", "spirit hover"], WordNlp()) == {
        "dark": 0,
        "water": 0,
        "spirit": 1,
        "hover": 1,
    }


def test_verse_word_stats_returns_percentages_and_source_aliases() -> None:
    stats = verse_word_stats(
        [
            {"alias": "A", "text": "x", "lemmas": ["create", "earth"]},
            {"alias": "B", "text": "x", "lemmas": ["create", "world"]},
            {"alias": "C", "text": "x", "lemmas": ["create", "land"]},
        ],
        original_order={"earth": 0, "create": 1},
    )
    assert stats["word_choices"][0] == {
        "lemma": "earth",
        "count": 1,
        "percent": 33,
        "aliases": ["A"],
        "alias_label": "A",
        "order": 0,
    }
    assert stats["word_choices"][1] == {
        "lemma": "create",
        "count": 3,
        "percent": 100,
        "aliases": ["A", "B", "C"],
        "alias_label": "A, B, C",
        "order": 1,
    }


def test_semantic_groups_stack_related_lemmas() -> None:
    groups = semantic_groups(
        [
            {"lemma": "genealogy", "count": 1, "alias_label": "A", "order": 2},
            {"lemma": "ancestry", "count": 1, "alias_label": "B", "order": 1},
            {"lemma": "earth", "count": 1, "alias_label": "C", "order": 0},
        ],
        SimilarityNlp(),
    )
    assert groups[0]["entries"] == [{"lemma": "earth", "count": 1, "alias_label": "C", "order": 0}]
    assert groups[1]["related"] is True
    assert [entry["lemma"] for entry in groups[1]["entries"]] == ["ancestry", "genealogy"]
