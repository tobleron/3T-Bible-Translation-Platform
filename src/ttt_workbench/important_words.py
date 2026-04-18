from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any


KEEP_POS = frozenset({"NOUN", "PROPN", "VERB", "ADJ"})
DROP_POS = frozenset({"DET", "ADP", "CCONJ", "SCONJ", "AUX", "PRON"})


@lru_cache(maxsize=1)
def load_spacy_model() -> tuple[Any | None, str]:
    try:
        import spacy
    except Exception:
        return None, "spaCy is not installed. Install spaCy and the en_core_web_sm model to enable important-word analysis."

    try:
        return spacy.load("en_core_web_sm"), ""
    except Exception:
        return None, "spaCy model en_core_web_sm is not installed. Reinstall the workbench requirements to enable important-word analysis."


def important_lemmas(text: str, nlp: Any) -> list[str]:
    if not text.strip():
        return []
    seen: set[str] = set()
    lemmas: list[str] = []
    for token in nlp(text):
        pos = getattr(token, "pos_", "")
        raw_text = str(getattr(token, "text", "") or "")
        lemma = str(getattr(token, "lemma_", "") or raw_text).strip().lower()
        if not lemma:
            continue
        if getattr(token, "is_stop", False):
            continue
        if pos in DROP_POS or pos not in KEEP_POS:
            continue
        if not getattr(token, "is_alpha", raw_text.isalpha()):
            continue
        if lemma in seen:
            continue
        seen.add(lemma)
        lemmas.append(lemma)
    return lemmas


def verse_word_stats(translations: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = sum(1 for row in translations if str(row.get("text", "")).strip())
    counts: Counter[str] = Counter()
    aliases_by_lemma: dict[str, list[str]] = defaultdict(list)
    for row in translations:
        alias = str(row.get("alias", ""))
        for lemma in set(row.get("lemmas", [])):
            counts[lemma] += 1
            aliases_by_lemma[lemma].append(alias)

    if denominator < 1:
        return {"majority": [], "unique": []}

    majority = [
        {
            "lemma": lemma,
            "count": count,
            "percent": round((count / denominator) * 100),
        }
        for lemma, count in counts.items()
        if count > denominator / 2
    ]
    unique = [
        {
            "lemma": lemma,
            "alias": aliases_by_lemma[lemma][0],
        }
        for lemma, count in counts.items()
        if count == 1 and aliases_by_lemma[lemma]
    ]
    majority.sort(key=lambda item: (-int(item["count"]), str(item["lemma"])))
    unique.sort(key=lambda item: (str(item["alias"]), str(item["lemma"])))
    return {"majority": majority, "unique": unique}
