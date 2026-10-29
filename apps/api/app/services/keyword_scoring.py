"""nehn-026: the keyword score of a written answer (DEC-SCOPE-331 K1-K3; the rule is a builder's default, NEEDS_CONFIRMATION -- D-09 §4).

A keyword is one or more words; `|` separates synonyms (`loop|iteration`), any of which counts. Matching is case-insensitive,
order-independent and whole-word: both sides are casefolded and every non-letter/digit is a word break, a keyword's words must appear
together and in order, and a trailing `s` / `es` on the answer's word is ignored (`api` matches `apis`). At or above
KEYWORD_THRESHOLD_PERCENT of the keywords the answer gets full marks; below it, marks in proportion to the keywords matched."""

import re
from dataclasses import dataclass

KEYWORD_THRESHOLD_PERCENT = 80
MAX_KEYWORDS = 30
MAX_KEYWORD_LENGTH = 100
_WORD_BREAK = re.compile(r"[\W_]+")


@dataclass(frozen=True)
class KeywordScore:
    matched: list[str]
    percent: float
    score: float


def _words(text: str) -> list[str]:
    return _WORD_BREAK.sub(" ", text.casefold()).split()


def _same(answer_word: str, keyword_word: str) -> bool:
    return answer_word in (keyword_word, keyword_word + "s", keyword_word + "es")


def _contains(answer: list[str], phrase: list[str]) -> bool:
    size = len(phrase)
    return bool(phrase) and any(all(_same(answer[i + n], phrase[n]) for n in range(size)) for i in range(len(answer) - size + 1))


def score_answer(answer: object, keywords: list[str], max_score: int) -> KeywordScore:
    if not keywords:
        return KeywordScore(matched=[], percent=0.0, score=0.0)
    words = _words(answer) if isinstance(answer, str) else []
    matched = [keyword for keyword in keywords if any(_contains(words, _words(synonym)) for synonym in keyword.split("|"))]
    percent = round(len(matched) * 100 / len(keywords), 2)
    score = float(max_score) if percent >= KEYWORD_THRESHOLD_PERCENT else round(max_score * len(matched) / len(keywords), 2)
    return KeywordScore(matched=matched, percent=percent, score=score)
