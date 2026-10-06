"""bdm-005 -- request schemas (spec §6.1; AC3 'expired is not settable', Review Focus 2)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import BdmMouCreate, BdmMouUpdate


def _errors(model, body: dict) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(body)
    return {str(e["loc"][-1]) if e["loc"] else "": e["msg"] for e in caught.value.errors()}


def test_create_defaults_to_prospect_and_parses_dates():
    mou = BdmMouCreate.model_validate({"signed_on": "2026-01-05"})
    assert mou.status == "prospect" and mou.signed_on == date(2026, 1, 5) and mou.valid_until is None


@pytest.mark.parametrize("field", ["created_by_user_id", "is_current", "document_key", "organization_id", "id"])
def test_server_owned_fields_are_refused(field):
    assert field in _errors(BdmMouCreate, {field: "x"})
    assert field in _errors(BdmMouUpdate, {field: "x"})


def test_expired_is_not_a_settable_status():
    assert "status" in _errors(BdmMouCreate, {"status": "expired"})
    assert "status" in _errors(BdmMouUpdate, {"status": "expired", "from_status": "active"})
    assert "status" in _errors(BdmMouCreate, {"status": "Signed"})  # keys, not labels


def test_a_status_change_needs_the_status_the_form_was_showing():
    assert "from_status" in _errors(BdmMouUpdate, {"status": "signed"})
    assert "status" in _errors(BdmMouUpdate, {"status": None, "from_status": "prospect"})
    ok = BdmMouUpdate.model_validate({"status": "under_negotiation", "from_status": "expired"})  # an Expired form may send it (409 later)
    assert (ok.status, ok.from_status) == ("under_negotiation", "expired")


def test_omitted_and_null_are_different():
    update = BdmMouUpdate.model_validate({"notes": None})
    assert update.model_fields_set == {"notes"} and update.notes is None


@pytest.mark.parametrize("value", ["2026-13-01", "20266-01-01", "05/01/2026", "tomorrow"])
def test_dates_get_plain_words(value):
    assert _errors(BdmMouCreate, {"valid_until": value})["valid_until"] == "Enter a valid valid-until date"


def test_blank_dates_clear():
    assert BdmMouUpdate.model_validate({"valid_until": ""}).valid_until is None


def test_reference_is_one_line_and_at_most_100():
    assert BdmMouCreate.model_validate({"reference": "  MOU-2026-014  "}).reference == "MOU-2026-014"
    assert BdmMouCreate.model_validate({"reference": "   "}).reference is None
    assert "reference" in _errors(BdmMouCreate, {"reference": "x" * 101})
    assert "invalid characters" in _errors(BdmMouCreate, {"reference": "MOU\n14"})["reference"]


def test_notes_keep_line_breaks_and_at_most_2000():
    assert BdmMouCreate.model_validate({"notes": "Line one\r\nLine two"}).notes == "Line one\nLine two"
    assert "notes" in _errors(BdmMouCreate, {"notes": "x" * 2001})
    assert "invalid characters" in _errors(BdmMouCreate, {"notes": "bell\x07"})["notes"]
