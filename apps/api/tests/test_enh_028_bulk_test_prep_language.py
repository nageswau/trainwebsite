"""ENH-028 -- Test Prep and Language bulk upload (spec §6.4-6.5): rows create SCH-009 records like the single creates, the tier
is checked per row for the row's own service, duplicates are refused, and parents get the single create's notice."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, SchoolLanguageRecord, SchoolStaffAssignment, SchoolTestPrepRecord
from tests.enh028_helpers import LANGUAGE_URL, TEST_PREP_URL, csv_bytes, login, mk_school, upload, world

TEST_PREP_HEADER = ["student_code", "student_name", "school_name", "test_type", "target_score"]
LANGUAGE_HEADER = ["student_code", "student_name", "school_name", "language", "level"]


async def _with_silver_school(db, w) -> dict:
    """Adds a Silver school (no IELTS/SAT/language services) to the member's portfolio."""
    silver = await mk_school(db, admin=w["admin"], label="Silver", students=1, tier="silver")
    db.add(SchoolStaffAssignment(user_id=w["member"].id, school_id=silver["school"].id, role="academic_team", assigned_by_user_id=w["admin"].id))
    await db.commit()
    return silver


@pytest.mark.asyncio
async def test_test_prep_rows_create_records_and_notify_parents(client, db_session):
    w = await world(db_session)
    first = w["students"][0]
    await login(client, w["member"].email)
    report = (await upload(client, TEST_PREP_URL, csv_bytes(TEST_PREP_HEADER, [{"student_code": first.student_code, "test_type": "IELTS", "target_score": "7.5"}]))).json()
    assert report["accepted_count"] == 1, report
    record = await db_session.scalar(select(SchoolTestPrepRecord).where(SchoolTestPrepRecord.school_student_id == first.id))
    assert (record.test_type, record.target_score, record.status, record.mock_scores, record.academic_team_user_id) == ("ielts", "7.5", "in_progress", [], w["member"].id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.test_prep_record_create", AuditLog.entity_id == str(record.id)))
    assert audit.metadata_json == {"test_type": "ielts", "bulk_batch_id": str(report["id"])}
    titles = (await db_session.scalars(select(Notification.title).where(Notification.user_id == w["parent"].id))).all()
    assert f"IELTS preparation started for {first.full_name}" in titles


@pytest.mark.asyncio
async def test_the_tier_is_checked_per_row_for_the_rows_own_service(client, db_session):
    w = await world(db_session, tier="gold")
    silver = await _with_silver_school(db_session, w)
    await login(client, w["member"].email)
    gold_kid, silver_kid = w["students"][0], silver["students"][0]
    rows = [{"student_code": gold_kid.student_code, "test_type": "sat"}, {"student_code": silver_kid.student_code, "test_type": "ielts"}, {"student_code": silver_kid.student_code, "test_type": "sat"}]
    report = (await upload(client, TEST_PREP_URL, csv_bytes(TEST_PREP_HEADER, rows))).json()
    assert [(r["status"], r["error_message"]) for r in report["rows"]] == [
        ("accepted", None),
        ("rejected", "This school's Silver partnership does not include IELTS coaching (requires Gold or higher)."),
        ("rejected", "This school's Silver partnership does not include SAT coaching (requires Gold or higher)."),
    ]
    denials = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.tier_access_denied", AuditLog.entity_id == str(silver["school"].id)))).all()
    assert sorted(d.metadata_json["service_key"] for d in denials) == ["ielts_coaching", "sat_coaching"]


@pytest.mark.asyncio
async def test_test_prep_duplicates_are_refused(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    code = w["students"][0].student_code
    first = (await upload(client, TEST_PREP_URL, csv_bytes(TEST_PREP_HEADER, [{"student_code": code, "test_type": "sat"}, {"student_code": code, "test_type": "SAT"}]))).json()
    assert [r["error_message"] for r in first["rows"]] == [None, "same student and test_type as row 2 of this file"]
    again = (await upload(client, TEST_PREP_URL, csv_bytes(TEST_PREP_HEADER, [{"student_code": code, "test_type": "sat"}, {"student_code": code, "test_type": "ielts"}]))).json()
    assert [r["error_message"] for r in again["rows"]] == ["this student already has a test preparation record for the same test_type", None]


@pytest.mark.asyncio
async def test_language_rows_create_records_refuse_duplicates_and_notify(client, db_session):
    w = await world(db_session)
    first = w["students"][0]
    await login(client, w["member"].email)
    rows = [{"student_code": first.student_code, "language": "French", "level": "A1"}, {"student_code": first.student_code, "language": " french "}]
    report = (await upload(client, LANGUAGE_URL, csv_bytes(LANGUAGE_HEADER, rows))).json()
    assert [r["error_message"] for r in report["rows"]] == [None, "same student and language as row 2 of this file"]
    record = await db_session.scalar(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id == first.id))
    assert (record.language, record.level, record.classes_attended, record.certification_status) == ("French", "A1", 0, "not_started")
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.language_record_create", AuditLog.entity_id == str(record.id)))
    assert audit.metadata_json == {"language": "French", "bulk_batch_id": str(report["id"])}
    titles = (await db_session.scalars(select(Notification.title).where(Notification.user_id == w["parent"].id))).all()
    assert f"French classes started for {first.full_name}" in titles
    again = (await upload(client, LANGUAGE_URL, csv_bytes(LANGUAGE_HEADER, [{"student_code": first.student_code, "language": "FRENCH"}]))).json()
    assert again["rows"][0]["error_message"] == "this student already has a language record for the same language"


@pytest.mark.asyncio
async def test_language_needs_the_foreign_language_service(client, db_session):
    w = await world(db_session, tier="silver")
    await login(client, w["member"].email)
    report = (await upload(client, LANGUAGE_URL, csv_bytes(LANGUAGE_HEADER, [{"student_code": w["students"][0].student_code, "language": "German"}]))).json()
    assert report["rows"][0]["error_message"] == "This school's Silver partnership does not include Foreign language classes (requires Gold or higher)."


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [TEST_PREP_URL, LANGUAGE_URL])
async def test_only_the_academic_team_may_upload(client, db_session, url):
    w = await world(db_session, role="psychometric_team")
    await login(client, w["member"].email)
    response = await upload(client, url, csv_bytes(["student_code", "test_type", "language"], [{"student_code": w["students"][0].student_code, "test_type": "sat", "language": "x"}]))
    assert response.status_code == 403
    assert response.json()["detail"] == "Academic Team role required"
