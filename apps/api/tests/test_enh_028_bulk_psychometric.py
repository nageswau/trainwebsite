"""ENH-028 -- Psychometric bulk upload (spec §6.3): rows create SCH-005/ENH-027 records exactly like the single create, parents get
the same notice after the batch commits, and a school without the service is refused row by row with one audit entry."""

import datetime

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Notification, SchoolPsychometricRecord
from app.schemas import PSYCHOMETRIC_RESULT_KEYS
from tests.enh028_helpers import PSYCH_URL, csv_bytes, login, upload, world

PSYCH_HEADER = ["student_code", "student_name", "school_name", "assessment_type", "report_url", *PSYCHOMETRIC_RESULT_KEYS]


def _row(student, assessment_type: str = "Aptitude", **over) -> dict:
    return {"student_code": student.student_code, "assessment_type": assessment_type, **over}


async def _records(db, student):
    return list((await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id == student.id))).all())


async def _notices(db, parent) -> list[str]:
    return list((await db.scalars(select(Notification.title).where(Notification.user_id == parent.id))).all())


@pytest.mark.asyncio
async def test_rows_create_records_with_status_and_result_fields(client, db_session):
    w = await world(db_session, role="psychometric_team")
    await login(client, w["member"].email)
    first, second, _ = w["students"]
    rows = [
        _row(first, report_url="https://reports.example/a.pdf", test_date="2026-09-01", strengths="Logic; Maths", counsellor_remarks="Strong\nfoundation"),
        _row(second, assessment_type="Interest Inventory"),
    ]
    response = await upload(client, PSYCH_URL, csv_bytes(PSYCH_HEADER, rows))
    assert response.status_code == 201, response.text
    assert response.json()["accepted_count"] == 2

    [done] = await _records(db_session, first)
    assert (done.status, done.report_url, done.test_date, done.strengths, done.counsellor_remarks) == (
        "completed",
        "https://reports.example/a.pdf",
        datetime.date(2026, 9, 1),
        ["Logic", "Maths"],
        "Strong\nfoundation",
    )
    assert done.psychometric_team_user_id == w["member"].id
    [assigned] = await _records(db_session, second)
    assert (assigned.status, assigned.assessment_type, assigned.report_url) == ("assigned", "Interest Inventory", None)

    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.psychometric_record_create", AuditLog.entity_id == str(done.id)))
    assert audit.metadata_json["assessment_type"] == "Aptitude"
    assert audit.metadata_json["bulk_batch_id"] == str(response.json()["id"])
    assert set(audit.metadata_json["fields"]) == {"test_date", "strengths", "counsellor_remarks"}


@pytest.mark.asyncio
async def test_parents_get_the_single_create_notice_and_rejected_rows_notify_nobody(client, db_session):
    w = await world(db_session, role="psychometric_team")
    first = w["students"][0]  # the only student with a linked parent
    await login(client, w["member"].email)
    rows = [_row(first, report_url="https://r.example/x.pdf"), _row(first, assessment_type="Interest"), _row(first, assessment_type="Bad", report_url="ftp://x")]
    await upload(client, PSYCH_URL, csv_bytes(PSYCH_HEADER, rows))
    assert sorted(await _notices(db_session, w["parent"])) == sorted([f"Psychometric report ready for {first.full_name}", f"Psychometric assessment assigned to {first.full_name}"])


@pytest.mark.asyncio
async def test_a_school_without_the_service_is_refused_per_row_with_one_audit_entry(client, db_session):
    w = await world(db_session, role="psychometric_team", tier=None)
    await login(client, w["member"].email)
    rows = [_row(w["students"][0]), _row(w["students"][1])]
    report = (await upload(client, PSYCH_URL, csv_bytes(PSYCH_HEADER, rows))).json()
    assert report["accepted_count"] == 0
    assert {r["error_message"] for r in report["rows"]} == {"This school has no active partnership tier."}  # NO_ACTIVE_TIER, unchanged
    denials = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.tier_access_denied", AuditLog.entity_id == str(w["school"].id)))
    assert denials == 1


@pytest.mark.asyncio
async def test_a_failed_notification_keeps_every_record(client, db_session, monkeypatch):
    async def _broken(*args, **kwargs):
        raise RuntimeError("mail relay down")

    monkeypatch.setattr("app.api.school_bulk._notify_student_parents", _broken)
    w = await world(db_session, role="psychometric_team")
    await login(client, w["member"].email)
    response = await upload(client, PSYCH_URL, csv_bytes(PSYCH_HEADER, [_row(s) for s in w["students"]]))
    assert response.status_code == 201
    assert response.json()["accepted_count"] == 3
    for student in w["students"]:
        assert len(await _records(db_session, student)) == 1


@pytest.mark.asyncio
async def test_duplicates_use_type_and_test_date(client, db_session):
    w = await world(db_session, role="psychometric_team")
    await login(client, w["member"].email)
    student = w["students"][0]
    rows = [
        _row(student, test_date="2026-09-01"),
        _row(student, assessment_type="APTITUDE", test_date="2026-09-01"),
        _row(student, test_date="2026-10-01"),
        _row(student),
        _row(student, assessment_type=" aptitude "),
    ]
    report = (await upload(client, PSYCH_URL, csv_bytes(PSYCH_HEADER, rows))).json()
    assert [r["status"] for r in report["rows"]] == ["accepted", "rejected", "accepted", "accepted", "rejected"]
    assert report["rows"][1]["error_message"] == "same student and assessment_type and test_date as row 2 of this file"
    again = (await upload(client, PSYCH_URL, csv_bytes(PSYCH_HEADER, [_row(student, test_date="2026-10-01")]))).json()
    assert again["rows"][0]["error_message"] == "this student already has an assessment for the same assessment_type and test_date"


@pytest.mark.asyncio
async def test_only_the_psychometric_team_may_upload(client, db_session):
    w = await world(db_session, role="academic_team")
    await login(client, w["member"].email)
    response = await upload(client, PSYCH_URL, csv_bytes(PSYCH_HEADER, [_row(w["students"][0])]))
    assert response.status_code == 403
    assert response.json()["detail"] == "Psychometric Team role required"
