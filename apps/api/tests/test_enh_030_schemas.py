"""ENH-030 -- request validation and the roster response contract (spec §5.2, §11 A1/A2, AC05)."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas import SchoolAttendanceIn, SchoolAttendanceRosterOut


def _mark(status="present"):
    return {"student_id": str(uuid.uuid4()), "status": status}


def _body(records=None, **over):
    return {"session_date": "2026-09-30", "records": records if records is not None else [_mark()], **over}


def test_accepts_all_four_statuses():
    parsed = SchoolAttendanceIn.model_validate(_body([_mark(s) for s in ("present", "absent", "late", "excused")]))
    assert [r.status for r in parsed.records] == ["present", "absent", "late", "excused"]


@pytest.mark.parametrize(
    "body",
    [
        _body([_mark("sick")]),
        _body([]),
        _body([_mark() for _ in range(501)]),
        _body(extra="x"),
        _body([{**_mark(), "note": "x"}]),
        {"records": [_mark()]},
    ],
    ids=["bad-status", "empty", "over-500", "extra-field", "extra-record-field", "no-date"],
)
def test_rejects_invalid_bodies(body):
    with pytest.raises(ValidationError):
        SchoolAttendanceIn.model_validate(body)


def test_rejects_a_repeated_student():
    sid = str(uuid.uuid4())
    with pytest.raises(ValidationError, match="must not repeat an id"):
        SchoolAttendanceIn.model_validate(_body([{"student_id": sid, "status": "present"}, {"student_id": sid, "status": "absent"}]))


def test_accepts_exactly_500():
    assert len(SchoolAttendanceIn.model_validate(_body([_mark() for _ in range(500)])).records) == 500


def test_roster_out_types_status_as_the_four_values_or_none():
    student = {"id": str(uuid.uuid4()), "full_name": "A", "grade_or_class": None}
    roster = {"session_date": "2026-09-30", "today": "2026-09-30"}
    assert SchoolAttendanceRosterOut.model_validate({**roster, "students": [{**student, "status": None}]}).students[0].status is None
    with pytest.raises(ValidationError):
        SchoolAttendanceRosterOut.model_validate({**roster, "students": [{**student, "status": "sick"}]})
