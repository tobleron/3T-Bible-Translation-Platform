from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any
import warnings


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


SIMILARITY_THRESHOLD = 0.72


def _lemma_similarity(left: str, right: str, nlp: Any) -> float:
    try:
        left_doc = nlp(left)
        right_doc = nlp(right)
        if not left_doc or not right_doc:
            return 0.0
        left_token = left_doc[0]
        right_token = right_doc[0]
        if not getattr(left_token, "has_vector", False) or not getattr(right_token, "has_vector", False):
            return 0.0
        if not getattr(left_token, "vector_norm", 0.0) or not getattr(right_token, "vector_norm", 0.0):
            return 0.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return float(left_token.similarity(right_token))
    except Exception:
        return 0.0


def semantic_groups(items: list[dict[str, Any]], nlp: Any | None) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    if not items:
        return groups
    if nlp is None:
        return [{"entries": [item], "related": False} for item in items]

    for item in items:
        lemma = str(item.get("lemma", ""))
        best_group: dict[str, Any] | None = None
        best_score = 0.0
        for group in groups:
            score = max(
                _lemma_similarity(lemma, str(entry.get("lemma", "")), nlp)
                for entry in group["entries"]
            )
            if score >= SIMILARITY_THRESHOLD and score > best_score:
                best_group = group
                best_score = score
        if best_group is None:
            groups.append({"entries": [item], "related": False})
        else:
            best_group["entries"].append(item)
            best_group["related"] = True
            best_group["score"] = round(best_score, 2)

    for group in groups:
        group["entries"].sort(
            key=lambda entry: (
                -int(entry.get("count", 0)),
                str(entry.get("lemma", "")),
            )
        )
    groups.sort(
        key=lambda group: (
            0 if group.get("related") else 1,
            -len(group["entries"]),
            str(group["entries"][0].get("lemma", "")),
        )
    )
    return groups


def verse_word_stats(translations: list[dict[str, Any]], nlp: Any | None = None) -> dict[str, Any]:
    denominator = sum(1 for row in translations if str(row.get("text", "")).strip())
    counts: Counter[str] = Counter()
    aliases_by_lemma: dict[str, list[str]] = defaultdict(list)
    for row in translations:
        alias = str(row.get("alias", ""))
        for lemma in set(row.get("lemmas", [])):
            counts[lemma] += 1
            aliases_by_lemma[lemma].append(alias)

    if denominator < 1:
        return {"word_choices": [], "word_groups": []}

    word_choices = [
        {
            "lemma": lemma,
            "count": count,
            "percent": round((count / denominator) * 100),
            "aliases": aliases_by_lemma[lemma],
            "alias_label": ", ".join(aliases_by_lemma[lemma]),
        }
        for lemma, count in counts.items()
    ]
    word_choices.sort(key=lambda item: (-int(item["count"]), str(item["lemma"])))
    return {
        "word_choices": word_choices,
        "word_groups": semantic_groups(word_choices, nlp),
    }
