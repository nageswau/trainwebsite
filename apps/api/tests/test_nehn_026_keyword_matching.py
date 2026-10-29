"""nehn-026 -- the keyword rule itself (app.services.keyword_scoring): matching K2, the 80% / proportional marks K3."""

import pytest

from app.services.keyword_scoring import KEYWORD_THRESHOLD_PERCENT, score_answer

KEYWORDS = ["alpha", "beta", "gamma", "delta", "epsilon"]


def test_the_threshold_is_80_percent():
    assert KEYWORD_THRESHOLD_PERCENT == 80


def test_four_of_five_keywords_meet_the_threshold_and_get_full_marks():
    result = score_answer("Epsilon and BETA, then alpha... finally gamma.", KEYWORDS, 10)
    assert result.matched == ["alpha", "beta", "gamma", "epsilon"]
    assert result.percent == 80.0
    assert result.score == 10.0


def test_below_the_threshold_marks_are_proportional():
    result = score_answer("alpha beta gamma", KEYWORDS, 10)
    assert result.percent == 60.0
    assert result.score == 6.0


def test_no_keyword_scores_zero():
    assert score_answer("nothing relevant here", KEYWORDS, 5).score == 0.0


def test_proportional_marks_round_to_two_places():
    assert score_answer("alpha", ["alpha", "beta", "gamma"], 1).score == 0.33


@pytest.mark.parametrize(
    ("answer", "keyword", "hit"),
    [
        ("We call the REST endpoint", "rest", True),
        ("Interest rates", "rest", False),  # whole words only
        ("several APIs", "api", True),  # plural s
        ("two classes", "class", True),  # plural es
        ("a primary key, then a foreign key", "foreign key", True),  # multi-word phrase
        ("the key is foreign", "foreign key", False),  # a phrase keeps its word order
        ("an iteration over items", "loop|iteration", True),  # synonyms
        ("Ünïcode Straße", "straße", True),
        ("idempotent-request handling", "idempotent request", True),  # punctuation is a word break
    ],
)
def test_matching(answer, keyword, hit):
    assert (score_answer(answer, [keyword], 1).matched == [keyword]) is hit


def test_a_keyword_counts_once_however_often_it_repeats():
    assert score_answer("alpha alpha alpha alpha", KEYWORDS, 10).score == 2.0


def test_a_non_text_answer_scores_zero():
    assert score_answer(None, KEYWORDS, 10).score == 0.0
    assert score_answer(["alpha", "beta"], KEYWORDS, 10).score == 0.0
