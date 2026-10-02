"""bdm-002 -- request models (spec §5.1, §12.3 input validation)."""

import pytest
from pydantic import ValidationError

from app.schemas import BdmContactIn, BdmContactUpdate, BdmOrganizationCreate, BdmOrganizationUpdate

CONTACT = {"name": "Dr Rao", "designation": "Principal", "role": "principal"}


def org(**overrides) -> dict:
    return {"org_type": "college", "name": "  St  Mary's College ", "city": "Kochi", "contacts": [CONTACT], **overrides}


def messages(exc: ValidationError) -> list[str]:
    return [e["msg"].removeprefix("Value error, ") for e in exc.errors()]


def test_create_trims_and_defaults():
    parsed = BdmOrganizationCreate.model_validate(org(state="", email=" Info@Mary.EDU "))
    assert parsed.name == "St  Mary's College" and parsed.state is None and parsed.email == "info@mary.edu"
    assert parsed.existing_partner is False and parsed.confirm_duplicate is False


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"name": "   "}, "Organization name is required"),
        ({"city": ""}, "City is required"),
        ({"contacts": []}, "Add at least one contact"),
        ({"contacts": [CONTACT] * 21}, "An organization can have at most 20 contacts"),
        ({"contacts": [{**CONTACT, "is_primary": True}, {**CONTACT, "is_primary": True}]}, "Only one contact can be primary"),
        ({"website": "javascript:alert(1)"}, "Website must start with http:// or https://"),
        ({"website": "data:text/html,x"}, "Website must start with http:// or https://"),
        ({"email": "not-an-email"}, "Enter a valid email address"),
        ({"phone": "12<script>"}, "Phone may contain only digits, spaces and + - ( )"),
        ({"name": "Bad\x00Name"}, "Organization name contains invalid characters"),
    ],
)
def test_create_rejects_bad_input_with_a_readable_message(overrides, expected):
    with pytest.raises(ValidationError) as exc:
        BdmOrganizationCreate.model_validate(org(**overrides))
    assert expected in messages(exc.value)


@pytest.mark.parametrize("field", ["code", "bdm_type", "assigned_bdm_user_id", "archived_at", "created_by_user_id", "nope"])
def test_server_owned_and_unknown_fields_are_rejected(field):
    with pytest.raises(ValidationError) as exc:
        BdmOrganizationCreate.model_validate(org(**{field: "x"}))
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_bounds_and_enums():
    for bad in ({"student_count": -1}, {"student_count": 1_000_001}, {"org_type": "ngo"}, {"contacts": [{**CONTACT, "role": "ceo"}]}):
        with pytest.raises(ValidationError):
            BdmOrganizationCreate.model_validate(org(**bad))
    assert BdmOrganizationCreate.model_validate(org(student_count=0, website="https://mary.edu")).student_count == 0


def test_update_rejects_null_on_required_fields_and_contacts_key():
    for bad in ({"name": None}, {"city": None}, {"org_type": None}, {"existing_partner": None}, {"contacts": []}):
        with pytest.raises(ValidationError):
            BdmOrganizationUpdate.model_validate(bad)
    assert BdmOrganizationUpdate.model_validate({"state": ""}).model_dump(exclude_unset=True) == {"state": None}


def test_contact_models():
    with pytest.raises(ValidationError) as exc:
        BdmContactIn.model_validate({"name": " "})
    assert "Contact name is required" in messages(exc.value)
    with pytest.raises(ValidationError):
        BdmContactUpdate.model_validate({"name": None})
    assert BdmContactUpdate.model_validate({"is_primary": True}).model_dump(exclude_unset=True) == {"is_primary": True}
