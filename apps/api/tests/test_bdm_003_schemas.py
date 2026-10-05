"""bdm-003 -- profile schemas and the multi-line rule (spec §5.1, P14; AC3, AC4, AC10)."""

from typing import get_args

import pytest
from pydantic import ValidationError

from app import models
from app.schemas import (
    BdmCollegeType,
    BdmOrganizationCreate,
    BdmOrganizationOut,
    BdmOrganizationUpdate,
    BdmOrgProfileIn,
    BdmOrgSource,
    BdmSchoolBoard,
    BdmSchoolType,
)

CONTACT = {"name": "Dr Rao"}


def org(**overrides) -> dict:
    return {"org_type": "school", "name": "St Mary", "city": "Kochi", "contacts": [CONTACT], **overrides}


def messages(exc: ValidationError) -> str:
    return " | ".join(e["msg"] for e in exc.errors())


def test_literals_equal_the_model_tuples():
    assert get_args(BdmOrgSource) == models.BDM_ORG_SOURCES
    assert get_args(BdmSchoolBoard) == models.BDM_SCHOOL_BOARDS
    assert get_args(BdmSchoolType) == models.BDM_SCHOOL_TYPES
    assert get_args(BdmCollegeType) == models.BDM_COLLEGE_TYPES


def test_profile_accepts_every_field_and_keeps_unset_apart_from_null():
    full = {
        "country": "India", "territory": " South ", "source": "referral", "staff_count": 12, "board": "CBSE", "school_type": "private",
        "grade_from": -2, "grade_to": 12, "affiliation": "VTU", "college_type": "arts_science", "courses": "B.Tech CSE",
    }
    parsed = BdmOrgProfileIn.model_validate(full)
    assert parsed.territory == "South" and parsed.grade_from == -2
    assert BdmOrgProfileIn.model_validate({"board": None}).model_dump(exclude_unset=True) == {"board": None}
    assert BdmOrgProfileIn.model_validate({}).model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("key", ["commission", "students", "applications", "enrollments", "master_login", "bdm_type", "nope"])
def test_live_metrics_and_unknown_keys_are_rejected_in_profile_and_at_top_level(key):
    with pytest.raises(ValidationError) as exc:
        BdmOrgProfileIn.model_validate({key: 1})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"
    with pytest.raises(ValidationError) as exc:
        BdmOrganizationCreate.model_validate(org(**{key: 1}))
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"source": "tv"}, "Input should be"),
        ({"board": "cbse"}, "Input should be"),
        ({"school_type": "charter"}, "Input should be"),
        ({"college_type": "law"}, "Input should be"),
        ({"staff_count": -1}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"staff_count": 100_001}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"staff_count": "12"}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"staff_count": 1.5}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"grade_from": -3}, "Grade must be Nursery, LKG, UKG or 1 to 12"),
        ({"grade_to": 13}, "Grade must be Nursery, LKG, UKG or 1 to 12"),
        ({"country": "x" * 121}, "at most 120"),
        ({"affiliation": "x" * 201}, "at most 200"),
        ({"courses": "x" * 1001}, "at most 1000"),
        ({"territory": "Bad\x00"}, "Territory contains invalid characters"),
    ],
)
def test_profile_rejects_bad_values_readably(value, expected):
    with pytest.raises(ValidationError) as exc:
        BdmOrgProfileIn.model_validate(value)
    assert expected in messages(exc.value)


def test_multiline_rule():
    """P14 (Review Focus 5): \\r\\n and \\r become \\n before the length check; \\n is kept; every other control character is rejected."""
    parsed = BdmOrganizationCreate.model_validate(org(address="1 Main Rd\r\nKochi\rKerala", courses_interested="MBA\nBBA", profile={"courses": "A\r\nB"}))
    assert parsed.address == "1 Main Rd\nKochi\nKerala" and parsed.courses_interested == "MBA\nBBA" and parsed.profile.courses == "A\nB"
    long = "a\r\n" * 249 + "ab"  # 500 characters once each \r\n is one \n; 749 before
    assert len(BdmOrganizationCreate.model_validate(org(address=long)).address) == 500
    for bad in ("tab\there", "esc\x1b", "nul\x00"):
        with pytest.raises(ValidationError, match="Address contains invalid characters"):
            BdmOrganizationCreate.model_validate(org(address=bad))
    with pytest.raises(ValidationError, match="Organization name contains invalid characters"):  # single-line fields keep the old rule
        BdmOrganizationCreate.model_validate(org(name="St\nMary"))
    with pytest.raises(ValidationError, match="at most 500"):
        BdmOrganizationCreate.model_validate(org(address="x" * 501))


def test_create_and_update_profile_and_address():
    created = BdmOrganizationCreate.model_validate(org(address="", profile={"board": "CBSE"}))
    assert created.address is None and created.profile.board == "CBSE"
    assert BdmOrganizationCreate.model_validate(org()).profile is None
    assert BdmOrganizationUpdate.model_validate({"profile": {"grade_to": 10}}).model_dump(exclude_unset=True) == {"profile": {"grade_to": 10}}
    with pytest.raises(ValidationError):
        BdmOrganizationUpdate.model_validate({"profile": None})


def test_output_profile_is_discriminated_on_kind():
    base = {
        "id": "00000000-0000-0000-0000-000000000001", "code": "ORG-000001", "name": "A", "org_type": "school", "bdm_type": "school", "city": "K",
        "state": None, "existing_partner": False, "assigned_bdm": {"id": "00000000-0000-0000-0000-000000000002", "full_name": "B", "active": True},
        "primary_contact": None, "archived": False, "last_meeting_at": None, "next_meeting_at": None,
        "permissions": {"can_edit": True, "can_archive": True, "can_restore": False, "can_reassign": False}, "phone": None, "email": None,
        "website": None, "courses_interested": None, "student_count": None, "contacts": [], "created_by_name": "B", "archived_at": None,
        "created_at": "2026-10-03T00:00:00Z", "updated_at": "2026-10-03T00:00:00Z", "address": None,
    }
    school = BdmOrganizationOut.model_validate({**base, "profile": {"kind": "school", "board": "CBSE", "school_type": None, "grade_from": 6, "grade_to": 12}})
    assert school.model_dump(mode="json")["profile"] == {"kind": "school", "board": "CBSE", "school_type": None, "grade_from": 6, "grade_to": 12}
    assert BdmOrganizationOut.model_validate({**base, "profile": None}).profile is None
