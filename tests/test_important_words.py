from __future__ import annotations

from types import SimpleNamespace

from ttt_workbench.important_words import (
    glossary_word_order,
    important_word_positions,
    important_words,
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


def test_important_words_keep_unique_content_words_only() -> None:
    assert important_words("ignored", FakeNlp()) == ["spirit", "hovered", "dark", "water"]
    assert important_word_positions("ignored", FakeNlp()) == {
        "spirit": 1,
        "hovered": 2,
        "dark": 4,
        "water": 6,
    }


def test_glossary_word_order_uses_original_gloss_sequence() -> None:
    assert glossary_word_order(["dark water", "spirit hover"], WordNlp()) == {
        "dark": 0,
        "water": 0,
        "spirit": 1,
        "hover": 1,
    }


def test_verse_word_stats_returns_percentages_and_source_aliases() -> None:
    stats = verse_word_stats(
        [
            {"alias": "D", "text": "x", "words": ["created", "earth"]},
            {"alias": "E", "text": "x", "words": ["created", "world"]},
            {"alias": "F", "text": "x", "words": ["created", "land"]},
        ],
        original_order={"earth": 0, "created": 1},
    )
    assert stats["word_choices"][0] == {
        "word": "earth",
        "count": 1,
        "percent": 33,
        "aliases": ["D"],
        "alias_label": "D",
        "order": 0,
    }
    assert stats["word_choices"][1] == {
        "word": "created",
        "count": 3,
        "percent": 100,
        "aliases": ["D", "E", "F"],
        "alias_label": "D, E, F",
        "order": 1,
    }


def test_semantic_groups_stack_related_words() -> None:
    groups = semantic_groups(
        [
            {"word": "genealogy", "count": 1, "alias_label": "A", "order": 2},
            {"word": "ancestry", "count": 1, "alias_label": "B", "order": 1},
            {"word": "earth", "count": 1, "alias_label": "C", "order": 0},
        ],
        SimilarityNlp(),
    )
    assert groups[0]["entries"] == [{"word": "earth", "count": 1, "alias_label": "C", "order": 0}]
    assert groups[1]["related"] is True
    assert [entry["word"] for entry in groups[1]["entries"]] == ["ancestry", "genealogy"]
