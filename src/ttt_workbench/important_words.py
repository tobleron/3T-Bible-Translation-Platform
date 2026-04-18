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


def _kept_token_lemma(token: Any) -> str:
    pos = getattr(token, "pos_", "")
    raw_text = str(getattr(token, "text", "") or "")
    lemma = str(getattr(token, "lemma_", "") or raw_text).strip().lower()
    if not lemma:
        return ""
    if getattr(token, "is_stop", False):
        return ""
    if pos in DROP_POS or pos not in KEEP_POS:
        return ""
    if not getattr(token, "is_alpha", raw_text.isalpha()):
        return ""
    return lemma


def important_lemma_positions(text: str, nlp: Any) -> dict[str, int]:
    if not text.strip():
        return {}
    positions: dict[str, int] = {}
    for index, token in enumerate(nlp(text)):
        lemma = _kept_token_lemma(token)
        if lemma and lemma not in positions:
            positions[lemma] = index
    return positions


def important_lemmas(text: str, nlp: Any) -> list[str]:
    return list(important_lemma_positions(text, nlp).keys())


def glossary_lemma_order(glosses: list[str], nlp: Any) -> dict[str, int]:
    order: dict[str, int] = {}
    ordinal = 0
    for gloss in glosses:
        clean_gloss = str(gloss or "").replace(";", " ")
        lemmas = important_lemmas(clean_gloss, nlp)
        for lemma in lemmas:
            if lemma not in order:
                order[lemma] = ordinal
        for raw_word in re.findall(r"[A-Za-z]+", clean_gloss.lower()):
            if raw_word not in order and lemmas:
                order[raw_word] = ordinal
        if lemmas:
            ordinal += 1
    return order


def translation_lemma_order(translations: list[dict[str, Any]]) -> dict[str, int]:
    order: dict[str, int] = {}
    for row in translations:
        positions = row.get("lemma_positions", {})
        if not isinstance(positions, dict):
            continue
        for lemma, position in positions.items():
            try:
                offset = int(position)
            except (TypeError, ValueError):
                continue
            if lemma not in order or offset < order[lemma]:
                order[str(lemma)] = offset
    return order


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
        return [{"entries": [item], "related": False, "order": int(item.get("order", 1_000_000))} for item in items]

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
                str(entry.get("lemma", "")),
            )
        )
    groups.sort(
        key=lambda group: (
            int(group.get("order", 1_000_000)),
            str(group["entries"][0].get("lemma", "")),
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
    aliases_by_lemma: dict[str, list[str]] = defaultdict(list)
    fallback_order = translation_lemma_order(translations)
    original_order = original_order or {}
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
            "order": original_order[lemma] if lemma in original_order else 10_000 + fallback_order.get(lemma, 1_000_000),
        }
        for lemma, count in counts.items()
    ]
    word_choices.sort(key=lambda item: (int(item["order"]), -int(item["count"]), str(item["lemma"])))
    return {
        "word_choices": word_choices,
        "word_groups": semantic_groups(word_choices, nlp),
    }
