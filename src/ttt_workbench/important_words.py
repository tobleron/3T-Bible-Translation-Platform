from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any
import re
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


def _kept_token_word(token: Any) -> str:
    pos = getattr(token, "pos_", "")
    raw_text = str(getattr(token, "text", "") or "")
    word = raw_text.strip().lower()
    if not word:
        return ""
    if getattr(token, "is_stop", False):
        return ""
    if pos in DROP_POS or pos not in KEEP_POS:
        return ""
    if not getattr(token, "is_alpha", raw_text.isalpha()):
        return ""
    return word


def important_word_positions(text: str, nlp: Any) -> dict[str, int]:
    if not text.strip():
        return {}
    positions: dict[str, int] = {}
    for index, token in enumerate(nlp(text)):
        word = _kept_token_word(token)
        if word and word not in positions:
            positions[word] = index
    return positions


def important_words(text: str, nlp: Any) -> list[str]:
    return list(important_word_positions(text, nlp).keys())


def glossary_word_order(glosses: list[str], nlp: Any) -> dict[str, int]:
    order: dict[str, int] = {}
    ordinal = 0
    for gloss in glosses:
        clean_gloss = str(gloss or "").replace(";", " ")
        words = important_words(clean_gloss, nlp)
        for word in words:
            if word not in order:
                order[word] = ordinal
        for raw_word in re.findall(r"[A-Za-z]+", clean_gloss.lower()):
            if raw_word not in order and words:
                order[raw_word] = ordinal
        if words:
            ordinal += 1
    return order


def translation_word_order(translations: list[dict[str, Any]]) -> dict[str, int]:
    order: dict[str, int] = {}
    for row in translations:
        positions = row.get("word_positions", {})
        if not isinstance(positions, dict):
            continue
        for word, position in positions.items():
            try:
                offset = int(position)
            except (TypeError, ValueError):
                continue
            if word not in order or offset < order[word]:
                order[str(word)] = offset
    return order


def original_order_for_word(word: str, original_order: dict[str, int], nlp: Any | None) -> int | None:
    if word in original_order:
        return original_order[word]
    if nlp is None:
        return None
    try:
        doc = nlp(word)
    except Exception:
        return None
    for token in doc:
        lemma = str(getattr(token, "lemma_", "") or "").strip().lower()
        if lemma in original_order:
            return original_order[lemma]
    return None


SIMILARITY_THRESHOLD = 0.72


def _word_similarity(left: str, right: str, nlp: Any) -> float:
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
        return [{"entries": [item], "related": False, "order": int(item.get("order", 1_000_000))} for item in items]

    for item in items:
        word = str(item.get("word", ""))
        best_group: dict[str, Any] | None = None
        best_score = 0.0
        for group in groups:
            score = max(
                _word_similarity(word, str(entry.get("word", "")), nlp)
                for entry in group["entries"]
            )
            if score >= SIMILARITY_THRESHOLD and score > best_score:
                best_group = group
                best_score = score
        if best_group is None:
            groups.append({"entries": [item], "related": False, "order": int(item.get("order", 1_000_000))})
        else:
            best_group["entries"].append(item)
            best_group["related"] = True
            best_group["score"] = round(best_score, 2)
            best_group["order"] = min(
                int(best_group.get("order", 1_000_000)),
                int(item.get("order", 1_000_000)),
            )

    for group in groups:
        group["entries"].sort(
            key=lambda entry: (
                int(entry.get("order", 1_000_000)),
                -int(entry.get("count", 0)),
                str(entry.get("word", "")),
            )
        )
    groups.sort(
        key=lambda group: (
            int(group.get("order", 1_000_000)),
            str(group["entries"][0].get("word", "")),
        )
    )
    return groups


def verse_word_stats(
    translations: list[dict[str, Any]],
    nlp: Any | None = None,
    original_order: dict[str, int] | None = None,
) -> dict[str, Any]:
    denominator = sum(1 for row in translations if str(row.get("text", "")).strip())
    counts: Counter[str] = Counter()
    aliases_by_word: dict[str, list[str]] = defaultdict(list)
    fallback_order = translation_word_order(translations)
    original_order = original_order or {}
    for row in translations:
        alias = str(row.get("alias", ""))
        for word in set(row.get("words", [])):
            counts[word] += 1
            aliases_by_word[word].append(alias)

    if denominator < 1:
        return {"word_choices": [], "word_groups": []}

    word_choices = []
    for word, count in counts.items():
        source_order = original_order_for_word(word, original_order, nlp)
        word_choices.append(
            {
                "word": word,
                "count": count,
                "percent": round((count / denominator) * 100),
                "aliases": aliases_by_word[word],
                "alias_label": ", ".join(aliases_by_word[word]),
                "order": source_order if source_order is not None else 10_000 + fallback_order.get(word, 1_000_000),
            }
        )
    word_choices.sort(key=lambda item: (int(item["order"]), -int(item["count"]), str(item["word"])))
    return {
        "word_choices": word_choices,
        "word_groups": semantic_groups(word_choices, nlp),
    }
