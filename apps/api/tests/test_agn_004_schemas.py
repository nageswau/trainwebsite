"""AGN-004 -- request schemas for students with no login (spec §5.5)."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import AgentStudentAssign, AgentStudentRecordCreate, AgentStudentRecordUpdate


def test_minimal_create_needs_only_a_name():
    rec = AgentStudentRecordCreate(full_name="  Asha Rao  ")
    assert rec.full_name == "Asha Rao" and rec.confirm_duplicate is False


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "   "},
        {"full_name": "A" * 161},
        {"full_name": "Asha", "email": "not-an-email"},
        {"full_name": "Asha", "date_of_birth": (date.today() + timedelta(days=1)).isoformat()},
        {"full_name": "Asha", "date_of_birth": "1899-12-31"},
        {"full_name": "Asha", "graduation_year": 1949},
        {"full_name": "Asha", "graduation_year": date.today().year + 7},
        {"full_name": "Asha", "notes": "x" * 2001},
        {"full_name": "Asha‮evil"},
        {"full_name": "Asha", "institution": "Bad\x00Uni"},
        {"full_name": "Asha", "phone": "9" * 41},
        {"full_name": "Asha", "status": "archived"},
        {"full_name": "Asha", "assigned_member_id": "00000000-0000-0000-0000-000000000000"},
        {"full_name": "Asha", "agent_id": "00000000-0000-0000-0000-000000000000"},
        {"full_name": "Asha", "student_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
def test_create_rejects_bad_or_server_owned_input(payload):
    with pytest.raises(ValidationError):
        AgentStudentRecordCreate(**payload)


def test_email_is_lowercased_and_blank_optional_fields_become_none():
    rec = AgentStudentRecordCreate(full_name="Asha", email=" Asha@Example.COM ", phone="  ", preferred_country="")
    assert rec.email == "asha@example.com" and rec.phone is None and rec.preferred_country is None


def test_notes_keep_line_breaks():
    assert AgentStudentRecordCreate(full_name="Asha", notes="line one\nline two").notes == "line one\nline two"


def test_update_tracks_only_sent_fields_and_refuses_clearing_the_name():
    upd = AgentStudentRecordUpdate(phone=None)
    assert upd.model_fields_set == {"phone"}
    with pytest.raises(ValidationError):
        AgentStudentRecordUpdate(full_name=None)
    with pytest.raises(ValidationError):
        AgentStudentRecordUpdate(full_name="  ")
    with pytest.raises(ValidationError):
        AgentStudentRecordUpdate(student_id="00000000-0000-0000-0000-000000000000")


def test_assign_accepts_a_member_or_null_but_needs_the_key():
    assert AgentStudentAssign(member_id=None).member_id is None
    with pytest.raises(ValidationError):
        AgentStudentAssign()
