"""ENH-016 Task 1 -- ENH-012's completion formula as a pure helper, so the scorecard (§28) can compute it in bulk without
drifting from GET /school/students/{id}/portfolio (spec §6.3, AC14)."""

from app.api.portfolio import portfolio_completion
from app.schemas import PORTFOLIO_SECTIONS

BASE = dict(profile_complete=False, has_academic=False, has_psychometric=False, has_career=False, has_language=False, sections=set(), has_statement=False)
TOTAL = 5 + len(PORTFOLIO_SECTIONS) + 1


def test_empty_portfolio_is_zero():
    assert portfolio_completion(**BASE) == 0


def test_everything_present_is_100():
    everything = {**BASE, "profile_complete": True, "has_academic": True, "has_psychometric": True, "has_career": True, "has_language": True, "sections": set(PORTFOLIO_SECTIONS), "has_statement": True}
    assert portfolio_completion(**everything) == 100


def test_each_component_weighs_the_same_and_unknown_sections_are_ignored():
    assert portfolio_completion(**{**BASE, "profile_complete": True}) == round(1 / TOTAL * 100)
    assert portfolio_completion(**{**BASE, "sections": {"project", "not-a-section"}}) == round(1 / TOTAL * 100)
