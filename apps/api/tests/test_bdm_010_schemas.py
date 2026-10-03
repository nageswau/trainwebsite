"""bdm-010 -- request/response schemas (spec §5.1, §12.3 S5; AC1, AC5, AC6)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import BdmTripCreate, BdmTripExpenseCreate, BdmTripReject, BdmTripUpdate

BASE = {"travel_date": "2026-10-10", "return_date": "2026-10-11", "from_place": " Hyderabad ", "to_place": "Vijayawada",
        "purpose": "College visits", "mode": "train", "estimated_cost": "2500.50"}


def _msg(exc: ValidationError) -> str:
    return " | ".join(e["msg"] for e in exc.errors())


def test_create_accepts_every_mode_and_trims_places():
    for mode in ("flight", "train", "bus", "car", "cab", "local"):
        body = BdmTripCreate.model_validate({**BASE, "mode": mode})
        assert body.from_place == "Hyderabad" and body.estimated_cost == Decimal("2500.50")
        assert body.accommodation_required is False and body.remarks is None


@pytest.mark.parametrize("field,value", [("mode", "ship"), ("estimated_cost", "-1"), ("estimated_cost", "1.234"),
                                         ("estimated_cost", "10000000.01"), ("from_place", "   "), ("purpose", "")])
def test_create_refuses_bad_values(field, value):
    with pytest.raises(ValidationError):
        BdmTripCreate.model_validate({**BASE, field: value})


@pytest.mark.parametrize("field", ["code", "bdm_user_id", "approval_status", "travel_status", "currency", "decided_by_user_id"])
def test_create_refuses_server_owned_fields(field):
    with pytest.raises(ValidationError, match="extra"):
        BdmTripCreate.model_validate({**BASE, field: "x"})


def test_estimated_cost_zero_is_allowed_but_expense_zero_is_not():
    assert BdmTripCreate.model_validate({**BASE, "estimated_cost": 0}).estimated_cost == 0
    with pytest.raises(ValidationError) as exc:
        BdmTripExpenseCreate.model_validate({"category": "food", "amount": "0", "expense_date": "2026-10-10"})
    assert "more than ₹0" in _msg(exc.value)


def test_multiline_fields_accept_newlines_but_not_other_controls():
    body = BdmTripCreate.model_validate({**BASE, "purpose": "Line one\nLine two\tend", "remarks": "a\r\nb"})
    assert body.purpose == "Line one\nLine two\tend"
    with pytest.raises(ValidationError) as exc:
        BdmTripCreate.model_validate({**BASE, "purpose": "bad\x07bell"})
    assert "Purpose contains invalid characters" in _msg(exc.value)
    with pytest.raises(ValidationError) as exc:
        BdmTripCreate.model_validate({**BASE, "to_place": "Vija\nyawada"})
    assert "To contains invalid characters" in _msg(exc.value)


def test_update_is_partial_and_refuses_explicit_null_on_required_fields():
    assert BdmTripUpdate.model_validate({"remarks": "Met the dean"}).model_dump(exclude_unset=True) == {"remarks": "Met the dean"}
    assert BdmTripUpdate.model_validate({"remarks": None}).model_dump(exclude_unset=True) == {"remarks": None}
    with pytest.raises(ValidationError):
        BdmTripUpdate.model_validate({"travel_date": None})


def test_reject_needs_a_reason():
    with pytest.raises(ValidationError) as exc:
        BdmTripReject.model_validate({"reason": "   "})
    assert "Reason is required" in _msg(exc.value)
    assert BdmTripReject.model_validate({"reason": " Too costly "}).reason == "Too costly"
