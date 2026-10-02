"""AGN-006 -- AgentStudentCounselingSave (spec §5.1): normalisation, the budget pair rule, bounds, mass assignment."""

from decimal import Decimal
from typing import get_args

import pytest
from pydantic import ValidationError

from app.models import COUNSELING_CURRENCIES
from app.schemas import AgentStudentCounselingSave, CounselingCurrency


def test_literal_matches_the_model_list():
    assert get_args(CounselingCurrency) == COUNSELING_CURRENCIES


def test_text_is_trimmed_and_blank_becomes_null():
    body = AgentStudentCounselingSave(counseling_completed=False, career_interest="  Law  ", course_preference="   ", remarks="Line one\nLine two")
    assert body.career_interest == "Law" and body.course_preference is None and body.remarks == "Line one\nLine two"


def test_an_amount_alone_defaults_to_inr_and_a_numeric_string_is_accepted():
    body = AgentStudentCounselingSave(counseling_completed=False, budget_amount="1500.5")
    assert body.budget_amount == Decimal("1500.5") and body.budget_currency == "INR"


def test_omitted_fields_dump_as_null():
    assert AgentStudentCounselingSave(counseling_completed=True).model_dump() == {
        "counseling_completed": True, "career_interest": None, "course_preference": None, "country_preference": None,
        "budget_amount": None, "budget_currency": None, "remarks": None,
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"budget_amount": -1},
        {"budget_amount": "100000000"},
        {"budget_amount": "10.123"},
        {"budget_amount": "NaN"},
        {"budget_amount": "Infinity"},
        {"budget_amount": 5, "budget_currency": "JPY"},
        {"budget_currency": "USD"},
        {"completed_at": "2026-10-01T00:00:00Z"},
        {"career_interest": "x" * 201},
        {"country_preference": "x" * 121},
        {"remarks": "x" * 2001},
        {"remarks": "bad\x00byte"},
    ],
    ids=["negative", "over-max", "three-decimals", "nan", "infinity", "unknown-currency", "currency-alone", "server-owned", "career-long", "country-long", "remarks-long", "nul"],
)
def test_invalid_input_is_refused(fields):
    with pytest.raises(ValidationError):
        AgentStudentCounselingSave(**({"counseling_completed": False} | fields))


def test_counseling_completed_is_required():
    with pytest.raises(ValidationError):
        AgentStudentCounselingSave(career_interest="Law")


def test_the_maximum_is_accepted():
    assert AgentStudentCounselingSave(counseling_completed=False, budget_amount="99999999.99", budget_currency="NZD").budget_amount == Decimal("99999999.99")
