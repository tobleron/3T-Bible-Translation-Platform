from __future__ import annotations

from types import SimpleNamespace

from ttt_workbench.important_words import important_lemmas, semantic_groups, verse_word_stats


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


def test_verse_word_stats_splits_majority_and_unique_choices() -> None:
    stats = verse_word_stats(
        [
            {"alias": "A", "text": "x", "lemmas": ["create", "earth"]},
            {"alias": "B", "text": "x", "lemmas": ["create", "world"]},
            {"alias": "C", "text": "x", "lemmas": ["create", "land"]},
        ]
    )
    assert stats["majority"] == [{"lemma": "create", "count": 3, "percent": 100}]
    assert {"lemma": "earth", "alias": "A"} in stats["unique"]
    assert {"lemma": "world", "alias": "B"} in stats["unique"]


def test_semantic_groups_stack_related_lemmas() -> None:
    groups = semantic_groups(
        [
            {"lemma": "genealogy", "alias": "A"},
            {"lemma": "ancestry", "alias": "B"},
            {"lemma": "earth", "alias": "C"},
        ],
        SimilarityNlp(),
    )
    assert groups[0]["related"] is True
    assert [entry["lemma"] for entry in groups[0]["entries"]] == ["genealogy", "ancestry"]
    assert groups[1]["entries"] == [{"lemma": "earth", "alias": "C"}]
