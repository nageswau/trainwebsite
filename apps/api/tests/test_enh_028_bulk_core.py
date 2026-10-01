"""ENH-028 -- the shared bulk-upload routine (spec §5.1, §7), exercised through the Results endpoint: idempotency key rules, file
shape errors that write nothing, replay, concurrent duplicates, parsing of real spreadsheet exports, and log hygiene."""

import asyncio
import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import SchoolAcademicResult
from tests.enh028_helpers import RESULT_HEADER, RESULTS_URL, batches_of, csv_bytes, login, mk_staff, result_row, upload, world


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Alembic's fileConfig disables existing loggers when a migration test runs in-process (see test_enh_030_mark.py)."""
    logging.getLogger("app.school.bulk").disabled = False
    yield


async def _results_of(db, students) -> int:
    return await db.scalar(select(func.count()).select_from(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id.in_([s.id for s in students])))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "detail"),
    [
        ({}, "Idempotency-Key header is required"),
        ({"Idempotency-Key": "has space"}, "Idempotency-Key must be 1-120 letters, digits or . _ : -"),
        ({"Idempotency-Key": "k" * 121}, "Idempotency-Key must be 1-120 letters, digits or . _ : -"),
    ],
)
async def test_a_missing_or_malformed_key_is_422_and_writes_nothing(client, db_session, headers, detail):
    w = await world(db_session)
    await login(client, w["member"].email)
    data = csv_bytes(RESULT_HEADER, [result_row(w["students"][0])])
    response = await client.post(RESULTS_URL, files={"file": ("bulk.csv", data, "text/csv")}, headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"] == detail
    assert await batches_of(db_session, w["member"]) == []


@pytest.mark.asyncio
async def test_the_wrong_role_is_403(client, db_session):
    w = await world(db_session, role="psychometric_team")
    await login(client, w["member"].email)
    response = await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][0])]))
    assert response.status_code == 403
    assert response.json()["detail"] == "Academic Team role required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "status", "detail"),
    [
        (b"student_code,academic_year\n" + b"x" * (1024 * 1024), 413, "The file is larger than 1 MB"),
        ("student_code,subject\n\xe9".encode("latin-1"), 422, "The file must be a UTF-8 CSV"),
        (b"student_code,academic_year,term,subject,max_marks,marks_obtained\nAB\x00,2026,T1,M,100,1\n", 422, "The file must be a UTF-8 CSV"),
        (b'student_code,academic_year,term,subject,max_marks,marks_obtained\nA,"2026"x,T1,M,100,1\n', 422, "The file must be a UTF-8 CSV"),
        (b"student_code,academic_year,term,max_marks,marks_obtained\nA,2026,T1,100,1\n", 422, "Missing required column: subject"),
        (b"", 422, "Missing required column: student_code"),
        (b"student_code,academic_year,term,subject,max_marks,marks_obtained\n", 422, "The file has no filled-in rows"),
    ],
    ids=["too-large", "not-utf8", "nul", "malformed", "missing-header", "empty", "header-only"],
)
async def test_whole_file_errors_write_nothing(client, db_session, data, status, detail):
    w = await world(db_session)
    await login(client, w["member"].email)
    response = await upload(client, RESULTS_URL, data)
    assert response.status_code == status, response.text
    assert response.json()["detail"] == detail
    assert await batches_of(db_session, w["member"]) == []


@pytest.mark.asyncio
async def test_more_than_500_filled_rows_is_422(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    rows = [result_row(w["students"][0], subject=f"S{i}") for i in range(501)]
    response = await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))
    assert response.status_code == 422
    assert response.json()["detail"] == "The file has more than 500 filled-in rows"
    assert await batches_of(db_session, w["member"]) == []


@pytest.mark.asyncio
async def test_an_untouched_template_is_422(client, db_session):
    """Review Focus 2: template rows with only the student columns are not 'filled in'."""
    w = await world(db_session)
    await login(client, w["member"].email)
    rows = [{"student_code": s.student_code, "student_name": s.full_name, "school_name": "Mine"} for s in w["students"]]
    response = await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))
    assert response.status_code == 422
    assert response.json()["detail"] == "The file has no filled-in rows"


@pytest.mark.asyncio
async def test_a_repeated_key_with_the_same_file_replays_the_report_and_creates_nothing(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    data = csv_bytes(RESULT_HEADER, [result_row(w["students"][0]), result_row(w["students"][1], obtained="900")])
    first = await upload(client, RESULTS_URL, data, key="retry-1")
    again = await upload(client, RESULTS_URL, data, key="retry-1")
    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert await _results_of(db_session, w["students"]) == 1
    assert len(await batches_of(db_session, w["member"])) == 1


@pytest.mark.asyncio
async def test_a_repeated_key_with_a_different_file_is_422(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    assert (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][0])]), key="k-1")).status_code == 201
    response = await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][1])]), key="k-1")
    assert response.status_code == 422
    assert response.json()["detail"] == "Idempotency-Key was already used for a different file"
    assert await _results_of(db_session, w["students"]) == 1


@pytest.mark.asyncio
async def test_another_users_key_never_replays(client, db_session):
    """Review Focus 5: keys are scoped to the uploader."""
    w = await world(db_session)
    peer = await mk_staff(db_session, w["school"], w["admin"], "academic_team")
    key = f"shared-{uuid.uuid4().hex[:6]}"
    await login(client, w["member"].email)
    mine = await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][0])]), key=key)
    await login(client, peer.email)
    theirs = await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][0], subject="Science")]), key=key)
    assert mine.status_code == theirs.status_code == 201
    assert mine.json()["id"] != theirs.json()["id"]
    assert theirs.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_concurrent_requests_with_one_key_create_once(client, db_session):
    w = await world(db_session)
    data = csv_bytes(RESULT_HEADER, [result_row(s) for s in w["students"]])
    clients = [client, AsyncClient(transport=ASGITransport(app=app), base_url="http://test")]
    try:
        for c in clients:
            await login(c, w["member"].email)
        first, second = await asyncio.gather(*(upload(c, RESULTS_URL, data, key="race-1") for c in clients))
    finally:
        await clients[1].aclose()
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert await _results_of(db_session, w["students"]) == len(w["students"])


@pytest.mark.asyncio
async def test_an_excel_style_csv_parses(client, db_session):
    """Review Focus 1: UTF-8 BOM, CRLF row endings, quoted cells containing commas and line breaks. Excel ends rows with CRLF
    but writes a line break inside a cell as a bare LF (Alt+Enter), which the house free-text rule accepts."""
    w = await world(db_session)
    await login(client, w["member"].email)
    code = w["students"][0].student_code
    text = "﻿student_code,academic_year,term,subject,max_marks,marks_obtained,teacher_remarks\r\n" f'{code},2026,Term 1,"Maths, Paper 2",100,75,"Line one\nline two"\r\n'
    response = await upload(client, RESULTS_URL, text.encode("utf-8"))
    assert response.status_code == 201, response.text
    assert response.json()["accepted_count"] == 1, response.json()
    result = await db_session.scalar(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id == w["students"][0].id))
    assert (result.subject, result.teacher_remarks) == ("Maths, Paper 2", "Line one\nline two")


@pytest.mark.asyncio
async def test_header_names_are_trimmed_and_case_insensitive(client, db_session):
    """Review Focus 3."""
    w = await world(db_session)
    await login(client, w["member"].email)
    code = w["students"][0].student_code.lower()
    text = f" Student_Code ,ACADEMIC_YEAR,Term,Subject,Max_Marks,Marks_Obtained\n{code},2026,Term 1,Maths,100,75\n"
    response = await upload(client, RESULTS_URL, text.encode())
    assert response.status_code == 201, response.text
    assert response.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_the_report_numbers_rows_by_file_line_and_adds_up(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    rows = [result_row(w["students"][0]), {"student_code": w["students"][1].student_code}, result_row(w["students"][1], obtained="x"), result_row(w["students"][2])]
    report = (await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, rows))).json()
    assert report["target_type"] == "academic_result" and report["status"] == "completed"
    assert (report["total_rows"], report["accepted_count"], report["rejected_count"]) == (3, 2, 1)
    assert [(r["row_number"], r["status"]) for r in report["rows"]] == [(2, "accepted"), (4, "rejected"), (5, "accepted")]
    assert report["rows"][1] == {"row_number": 4, "status": "rejected", "error_message": "marks_obtained must be a number", "student_code": w["students"][1].student_code, "created_record_id": None}
    assert all(r["created_record_id"] for r in report["rows"] if r["status"] == "accepted")


@pytest.mark.asyncio
async def test_the_completion_log_carries_counts_but_no_cell_values(client, db_session, caplog):
    w = await world(db_session)
    await login(client, w["member"].email)
    caplog.set_level(logging.INFO, logger="app.school.bulk")
    await upload(client, RESULTS_URL, csv_bytes(RESULT_HEADER, [result_row(w["students"][0], subject="SecretSubject")]), key="log-key-1")
    done = [r for r in caplog.records if r.getMessage() == "bulk_upload_completed"]
    assert len(done) == 1
    fields = done[0].__dict__["extra_fields"]
    assert (fields["target_type"], fields["total"], fields["accepted"], fields["rejected"]) == ("academic_result", 1, 1, 0)
    dumped = repr(done[0].__dict__)
    for secret in ("SecretSubject", w["students"][0].student_code, "log-key-1"):
        assert secret not in dumped
