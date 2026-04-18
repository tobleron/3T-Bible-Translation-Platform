from __future__ import annotations

from types import SimpleNamespace

from ttt_workbench.important_words import important_lemmas, verse_word_stats


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
