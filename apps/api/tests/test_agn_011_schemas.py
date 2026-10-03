"""AGN-011 -- request schemas (spec §4.2, §4.7): the agency's deposit save and the Overseas Admin remit/refund bodies."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import AgentDepositSave, DepositRefund, DepositRemit


def test_a_required_deposit_keeps_amount_and_due_date():
    body = AgentDepositSave(required=True, amount="50000.5", due_date=date(2026, 11, 1))
    assert body.amount == Decimal("50000.5") and body.due_date == date(2026, 11, 1)


def test_not_required_needs_no_amount():
    assert AgentDepositSave(required=False).amount is None


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"required": True}, "Enter the deposit amount"),
        ({"required": False, "amount": "10"}, "A deposit that is not required has no amount or due date"),
        ({"required": False, "due_date": "2026-11-01"}, "A deposit that is not required has no amount or due date"),
        ({"required": True, "amount": "0"}, "The amount must be more than ₹0"),
        ({"required": True, "amount": "10.005"}, "Enter an amount in rupees with up to 2 decimals, for example 50000.50"),
        ({"required": True, "amount": "abc"}, "Enter an amount in rupees with up to 2 decimals, for example 50000.50"),
        ({"required": True, "amount": "100000000"}, "The amount can be at most ₹99,999,999.99"),
        ({"required": True, "amount": "10", "currency": "USD"}, None),  # D1: the server owns the currency
        ({"required": True, "amount": "10", "status": "paid"}, None),  # only the paid hook sets paid
        ({"required": True, "amount": "10", "due_date": "1999-01-01"}, "Dates must be between 2000 and 2100"),
    ],
)
def test_invalid_deposit_bodies(body, message):
    with pytest.raises(ValidationError) as err:
        AgentDepositSave(**body)
    if message:
        assert message in str(err.value)


def test_remit_cleans_its_reference():
    assert DepositRemit(remitted_on=date(2026, 10, 1), reference="  UTR 1234  ").reference == "UTR 1234"


@pytest.mark.parametrize(
    "body",
    [
        {"remitted_on": "2026-10-01", "reference": "   "},
        {"remitted_on": "2026-10-01", "reference": "x" * 101},
        {"remitted_on": "2026-10-01"},
        {"remitted_on": "2026-10-01", "reference": "R", "extra": 1},
    ],
)
def test_invalid_remit_bodies(body):
    with pytest.raises(ValidationError):
        DepositRemit(**body)


@pytest.mark.parametrize(
    "body",
    [
        {"refunded_on": "2026-10-01", "amount": "0", "reason": "Visa refused"},
        {"refunded_on": "2026-10-01", "amount": "10", "reason": " "},
        {"refunded_on": "2026-10-01", "amount": "10", "reason": "x" * 501},
        {"refunded_on": "2026-10-01", "amount": "10.001", "reason": "Visa refused"},
    ],
)
def test_invalid_refund_bodies(body):
    with pytest.raises(ValidationError):
        DepositRefund(**body)


def test_refund_amount_errors_are_plain_words():
    """QA11-07: the admin sees the same plain wording as the agency, not the validator's."""
    with pytest.raises(ValidationError) as err:
        DepositRefund(refunded_on="2026-10-01", amount="abc", reason="Visa refused")
    assert "Enter an amount in rupees with up to 2 decimals, for example 50000.50" in str(err.value)
