"""AGN-013 -- the enrollment body: required date and expected status, bounded optional fields, no extras."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import AgentApplicationEnrollment

OK = {"enrollment_date": "2027-09-20", "expected_status": "offer"}


def test_minimal_body_and_blank_student_id_is_none():
    body = AgentApplicationEnrollment(**OK, university_student_id="   ")
    assert (body.enrollment_date, body.university_student_id, body.notes) == (date(2027, 9, 20), None, None)


def test_student_id_and_notes_are_trimmed():
    body = AgentApplicationEnrollment(**OK, university_student_id="  S-123 ", notes="  Joined  ")
    assert (body.university_student_id, body.notes) == ("S-123", "Joined")


@pytest.mark.parametrize(
    "bad",
    [
        {"expected_status": "offer"},
        {"enrollment_date": "2027-09-20"},
        {**OK, "enrollment_date": None},
        {**OK, "enrollment_date": "1999-12-31"},
        {**OK, "enrollment_date": "2101-01-01"},
        {**OK, "expected_status": "x" * 51},
        {**OK, "university_student_id": "x" * 61},
        {**OK, "university_student_id": "S\u0000"},
        {**OK, "university_student_id": "S‮1"},
        {**OK, "notes": "n" * 2001},
        {**OK, "status": "enrolled"},
        {**OK, "agent_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
def test_rejected(bad):
    with pytest.raises(ValidationError):
        AgentApplicationEnrollment(**bad)
