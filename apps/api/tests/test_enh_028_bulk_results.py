"""ENH-028 -- Academic Results bulk upload (spec §6.2): each valid row is a Draft identical to SCH-006's single create; bad,
out-of-portfolio and duplicate rows are rejected one by one; nothing reaches a parent; DEC-ROLE-007 still applies."""

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Notification, SchoolAcademicResult, SchoolResultStatusHistory
from tests.enh005_helpers import mk_result, mk_student
from tests.enh028_helpers import RESULT_HEADER, RESULTS_URL, csv_bytes, login, mk_staff, result_row, upload, world


async def _results(db, student):
    return list((await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id == student.id).order_by(SchoolAcademicResult.subject))).all())


@pytest.mark.asyncio
async def test_forty_marks_become_forty_drafts_like_the_single_create(client, db_session):
    w = await world(db_session, students=10)
    await login(client, w["member"].email)
    subjects = ("Mathematics", "Science", "English", "History")
    rows = [result_row(s, subject=subject, obtained="77", grade="B", teacher_remarks="Steady") for s in w["students"] for subject in subjects]
    response = await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))
    assert response.status_code == 201, response.text
    report = response.json()
    assert (report["total_rows"], report["accepted_count"], report["rejected_count"]) == (40, 40, 0)

    created = [r["created_record_id"] for r in report["rows"]]
    results = (await db_session.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.id.in_(created)))).all()
    assert len(results) == 40
    for result in results:
        assert (result.status, result.uploaded_by_user_id, float(result.max_marks), float(result.marks_obtained), result.grade, result.teacher_remarks) == ("draft", w["member"].id, 100.0, 77.0, "B", "Steady")
    history = (await db_session.scalars(select(SchoolResultStatusHistory).where(SchoolResultStatusHistory.result_id.in_(created)))).all()
    assert len(history) == 40 and {(h.from_status, h.to_status) for h in history} == {("none", "draft")}
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.result_create", AuditLog.entity_id.in_([str(c) for c in created])))).all()
    assert len(audits) == 40 and {a.metadata_json["bulk_batch_id"] for a in audits} == {str(report["id"])}
    batch_audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.bulk_upload", AuditLog.entity_id == str(report["id"])))
    assert batch_audit.metadata_json["target_type"] == "academic_result" and batch_audit.metadata_json["accepted"] == 40


@pytest.mark.asyncio
async def test_a_bad_row_never_blocks_the_good_rows(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    first, second, third = w["students"]
    rows = [result_row(first), result_row(second, max_marks="100", obtained="150"), result_row(third, subject="S" * 81)]
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))).json()
    assert [(r["status"], r["error_message"]) for r in report["rows"]] == [
        ("accepted", None),
        ("rejected", "marks_obtained must not exceed max_marks"),
        ("rejected", "subject must be at most 80 characters"),
    ]
    assert len(await _results(db_session, first)) == 1
    assert await _results(db_session, second) == [] and await _results(db_session, third) == []


@pytest.mark.asyncio
async def test_unknown_and_out_of_portfolio_students_are_rejected_row_by_row(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    rows = [result_row(w["outsider"]), {**result_row(w["students"][0]), "student_code": "ZZZZZZZZ"}, {**result_row(w["students"][0]), "student_code": ""}, result_row(w["students"][1])]
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))).json()
    assert [(r["status"], r["error_message"]) for r in report["rows"]] == [
        ("rejected", "This student is at a school outside your own portfolio"),
        ("rejected", "student_code does not match a student"),
        ("rejected", "student_code is required"),
        ("accepted", None),
    ]
    assert await _results(db_session, w["outsider"]) == []
    # The report names only what the uploader typed: nothing about the outsider beyond its code.
    assert w["outsider"].full_name not in str(report)


@pytest.mark.asyncio
async def test_duplicates_in_the_file_and_in_the_database_are_rejected(client, db_session):
    w = await world(db_session)
    await mk_result(db_session, w["students"][0], w["member"], subject="Maths")  # 2026-27 / Term 1 / Maths
    await login(client, w["member"].email)
    rows = [
        result_row(w["students"][0], subject="MATHS", academic_year="2026-27", term="term 1"),
        result_row(w["students"][1], subject="Science"),
        result_row(w["students"][1], subject=" science "),
    ]
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))).json()
    assert [(r["status"], r["error_message"]) for r in report["rows"]] == [
        ("rejected", "this student already has a result for the same academic_year, term and subject"),
        ("accepted", None),
        ("rejected", "same student and academic_year, term and subject as row 3 of this file"),
    ]


@pytest.mark.asyncio
async def test_same_student_different_subject_both_accepted(client, db_session):
    """Review Focus 4: only an identical natural key clashes."""
    w = await world(db_session)
    await login(client, w["member"].email)
    rows = [result_row(w["students"][0], subject="Maths"), result_row(w["students"][0], subject="Physics"), result_row(w["students"][0], subject="Maths", term="Term 2")]
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))).json()
    assert report["accepted_count"] == 3


@pytest.mark.asyncio
async def test_untouched_template_rows_are_skipped_and_not_counted(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    rows = [{"student_code": w["students"][0].student_code, "student_name": "untouched"}, result_row(w["students"][1])]
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))).json()
    assert (report["total_rows"], report["accepted_count"]) == (1, 1)
    assert report["rows"][0]["row_number"] == 3


@pytest.mark.asyncio
async def test_a_results_upload_notifies_nobody(client, db_session):
    w = await world(db_session)
    before = await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == w["parent"].id))
    await login(client, w["member"].email)
    await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][0])]))
    after = await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == w["parent"].id))
    assert after == before


@pytest.mark.asyncio
async def test_the_uploader_cannot_verify_a_bulk_draft_but_a_peer_can(client, db_session):
    w = await world(db_session)
    peer = await mk_staff(db_session, w["school"], w["admin"], "academic_team")
    await login(client, w["member"].email)
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][0])]))).json()
    result_id = report["rows"][0]["created_record_id"]
    assert (await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")).status_code == 403
    await login(client, peer.email)
    assert (await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")).status_code == 200


@pytest.mark.asyncio
async def test_a_student_added_after_lookup_does_not_matter_and_codes_are_case_insensitive(client, db_session):
    w = await world(db_session)
    late = await mk_student(db_session, w["school"], w["coordinator"], "Late")
    await db_session.commit()
    await login(client, w["member"].email)
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [{**result_row(late), "student_code": late.student_code.lower()}]))).json()
    assert report["accepted_count"] == 1
    assert report["rows"][0]["student_code"] == late.student_code
