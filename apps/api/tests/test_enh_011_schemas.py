import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import (
    SkillAssessmentCreate,
    SkillAttendanceIn,
    SkillBatchCreate,
    SkillBatchUpdate,
    SkillEnrollCreate,
    SkillEnrollmentUpdate,
    SkillScoresIn,
    SkillSessionCreate,
    TransferRequestCreate,
)

# ENH-011: the typed request boundary (docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §5.1). No database.


def _batch(**over):
    return {"school_id": uuid.uuid4(), "module_type": "soft_skills", "title": "Public speaking, term 1", "start_date": "2026-10-01", **over}


def test_batch_create_accepts_minimal_valid_payload():
    batch = SkillBatchCreate(**_batch(title="  Coding club  "))
    assert batch.module_type == "soft_skills" and batch.title == "Coding club"
    assert batch.topic is None and batch.trainer_name is None and batch.end_date is None
    assert SkillBatchCreate(**_batch(module_type="digital_skills", end_date="2026-10-01")).end_date == date(2026, 10, 1)


@pytest.mark.parametrize(
    "over", [{"module_type": "ielts"}, {"status": "closed"}, {"created_by_user_id": str(uuid.uuid4())}, {"title": ""}, {"title": "x" * 161}, {"topic": "t" * 121}, {"trainer_name": "a‮b"}]
)
def test_batch_create_rejects_bad_values_and_server_fields(over):
    with pytest.raises(ValidationError):
        SkillBatchCreate(**_batch(**over))


def test_batch_create_rejects_end_before_start():
    with pytest.raises(ValidationError):
        SkillBatchCreate(**_batch(end_date="2026-09-30"))


@pytest.mark.parametrize("extra", ["school_id", "module_type", "created_by_user_id"])
def test_batch_update_forbids_school_and_module(extra):
    with pytest.raises(ValidationError):
        SkillBatchUpdate(**{extra: "soft_skills"})


def test_batch_update_is_partial_and_status_is_open_or_closed():
    update = SkillBatchUpdate(status="closed")
    assert update.model_dump(exclude_unset=True) == {"status": "closed"}
    with pytest.raises(ValidationError):
        SkillBatchUpdate(status="archived")
    with pytest.raises(ValidationError):
        SkillBatchUpdate(start_date="2026-10-02", end_date="2026-10-01")


def test_enroll_requires_1_to_100_unique_ids():
    one = uuid.uuid4()
    assert SkillEnrollCreate(school_student_ids=[one]).school_student_ids == [one]
    for bad in ([], [one, one], [uuid.uuid4() for _ in range(101)], ["not-a-uuid"]):
        with pytest.raises(ValidationError):
            SkillEnrollCreate(school_student_ids=bad)


def test_enrollment_status_is_one_of_four():
    assert SkillEnrollmentUpdate(status="certified").status == "certified"
    with pytest.raises(ValidationError):
        SkillEnrollmentUpdate(status="passed")


def test_session_topic_limit():
    assert SkillSessionCreate(session_date="2026-10-01").topic is None
    with pytest.raises(ValidationError):
        SkillSessionCreate(session_date="2026-10-01", topic="t" * 161)


def test_attendance_and_scores_reject_duplicate_enrollment_ids_and_empty_lists():
    e = uuid.uuid4()
    with pytest.raises(ValidationError):
        SkillAttendanceIn(records=[{"enrollment_id": e, "present": True}, {"enrollment_id": e, "present": False}])
    with pytest.raises(ValidationError):
        SkillAttendanceIn(records=[])
    with pytest.raises(ValidationError):
        SkillScoresIn(scores=[{"enrollment_id": e, "score": 1}, {"enrollment_id": e, "score": 2}])
    with pytest.raises(ValidationError):
        SkillAttendanceIn(records=[{"enrollment_id": uuid.uuid4(), "present": True} for _ in range(201)])


def test_score_bounds_and_remarks_text_rules():
    ok = SkillScoresIn(scores=[{"enrollment_id": uuid.uuid4(), "score": "17.5", "remarks": "  Improve eye contact\nand pace  "}])
    assert ok.scores[0].score == Decimal("17.5") and ok.scores[0].remarks == "Improve eye contact\nand pace"
    assert SkillScoresIn(scores=[{"enrollment_id": uuid.uuid4(), "score": 0, "remarks": "   "}]).scores[0].remarks is None
    for bad in ({"score": -1}, {"score": "1.234"}, {"score": 1, "remarks": "a\x00b"}, {"score": 1, "remarks": "a‮b"}, {"score": 1, "remarks": "x" * 2001}):
        with pytest.raises(ValidationError):
            SkillScoresIn(scores=[{"enrollment_id": uuid.uuid4(), **bad}])


def test_max_score_bounds():
    assert SkillAssessmentCreate(name="Presentation", max_score=1000).max_score == Decimal("1000")
    for bad in ({"name": "P", "max_score": 0}, {"name": "P", "max_score": "1000.01"}, {"name": "", "max_score": 10}, {"name": "n" * 121, "max_score": 10}):
        with pytest.raises(ValidationError):
            SkillAssessmentCreate(**bad)


def test_existing_transfer_free_text_rule_unchanged():
    assert TransferRequestCreate(to_school_id=uuid.uuid4(), reason="x" * 500).reason == "x" * 500
    with pytest.raises(ValidationError):
        TransferRequestCreate(to_school_id=uuid.uuid4(), reason="x" * 501)
