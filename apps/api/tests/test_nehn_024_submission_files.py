"""nehn-024 -- direct file upload for assignment submissions (DEC-SCOPE-292; spec
docs/superpowers/specs/2026-10-26-nehn-024-submission-file-upload-design.md)."""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.models import Assignment, AuditLog, Batch, Enrollment, Program, Submission, SubmissionFile
from tests.agn001_helpers import client_for, mk_user

PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
SUBMIT = "/api/v1/workflows/it/assignments/{}/submissions"


async def _world(db, *, submission_type: str = "file") -> dict:
    trainer = await mk_user(db, role="trainer", division="it")
    student = await mk_user(db, role="it_student", division="it")
    classmate = await mk_user(db, role="it_student", division="it")
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"nehn-024 {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Cert",
        curriculum=["M1"],
        placement_assistance="Yes",
        trainer_name="T",
        active=True,
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id,
        name=f"B-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
        trainer_id=trainer.id,
    )
    db.add(batch)
    await db.flush()
    for who in (student, classmate):
        db.add(Enrollment(student_id=who.id, batch_id=batch.id, enrollment_code=f"EDU-{uuid.uuid4().hex[:8]}", status="active"))
    assignment = Assignment(
        batch_id=batch.id,
        title=f"Scan {uuid.uuid4().hex[:6]}",
        description="Upload your work.",
        due_date=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3),
        max_score=100,
        assignment_type="assignment",
        submission_type=submission_type,
        published=True,
    )
    db.add(assignment)
    await db.commit()
    return {"trainer": trainer, "student": student, "classmate": classmate, "batch": batch, "assignment": assignment}


async def _upload(c, name: str = "work.pdf", data: bytes = PDF, content_type: str = "application/pdf", purpose: str = "assignment_submission") -> str:
    response = await c.post("/api/v1/files/upload", params={"purpose": purpose}, files={"file": (name, data, content_type)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _trainer_row(c, submission_id: str) -> dict:
    rows = (await c.get("/api/v1/workflows/it/trainer/submissions")).json()
    return next(row for row in rows if row["id"] == submission_id)


@pytest.mark.asyncio
async def test_student_submits_uploaded_files_and_the_trainer_downloads_them(client, db_session):
    w = await _world(db_session)
    big = PDF + b"0" * (3 * 1024 * 1024)  # AC1: a 3 MB PDF
    async with client_for(w["student"].email, "it") as c:
        pdf_id, jpg_id = await _upload(c, "Lösung 1.pdf", big), await _upload(c, "page-2.jpg", JPG, "image/jpeg")
        submitted = await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": [pdf_id, jpg_id, pdf_id]})
        assert submitted.status_code == 201, submitted.text
        submission_id = submitted.json()["id"]
    links = (await db_session.scalars(select(SubmissionFile).where(SubmissionFile.submission_id == uuid.UUID(submission_id)))).all()
    assert {str(link.stored_file_id) for link in links} == {pdf_id, jpg_id}  # a repeated id is attached once
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "assignment.submit", AuditLog.entity_id == submission_id))
    assert audit.metadata_json["file_count"] == 2
    async with client_for(w["trainer"].email, "it") as c:
        row = await _trainer_row(c, submission_id)
        assert row["file_url"] is None
        files = {item["filename"]: item for item in row["files"]}
        assert set(files) == {"Lösung 1.pdf", "page-2.jpg"}
        assert files["Lösung 1.pdf"]["size"] == len(big) and files["Lösung 1.pdf"]["content_type"] == "application/pdf"
        url = files["Lösung 1.pdf"]["url"]
        assert url == f"/api/v1/workflows/it/submissions/{submission_id}/files/{pdf_id}"
        download = await c.get(url)
        assert download.status_code == 200 and download.content == big
        assert download.headers["content-disposition"].startswith("attachment") and download.headers["x-content-type-options"] == "nosniff"
    async with client_for(w["student"].email, "it") as c:
        assert (await c.get(url)).status_code == 200  # the submitter


@pytest.mark.asyncio
async def test_only_the_student_their_trainer_and_admins_can_download(client, db_session):
    w = await _world(db_session)
    other_trainer = await mk_user(db_session, role="trainer", division="it")
    it_admin = await mk_user(db_session, role="it_admin", division="it")
    super_admin = await mk_user(db_session, role="super_admin", division="global")
    async with client_for(w["student"].email, "it") as c:
        file_id = await _upload(c)
        submission_id = (await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": [file_id]})).json()["id"]
    url = f"/api/v1/workflows/it/submissions/{submission_id}/files/{file_id}"
    assert (await client.get(url)).status_code == 401
    for user, division, expected in ((w["classmate"], "it", 403), (other_trainer, "it", 403), (it_admin, "it", 200), (super_admin, "global", 200)):
        async with client_for(user.email, division) as c:
            assert (await c.get(url)).status_code == expected, user.role
    async with client_for(w["trainer"].email, "it") as c:
        assert (await c.get(f"/api/v1/workflows/it/submissions/{uuid.uuid4()}/files/{file_id}")).status_code == 404
        assert (await c.get(f"/api/v1/workflows/it/submissions/{submission_id}/files/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_a_file_that_is_not_yours_or_not_a_submission_upload_cannot_be_attached(client, db_session):
    w = await _world(db_session)
    async with client_for(w["classmate"].email, "it") as c:
        theirs = await _upload(c)
    async with client_for(w["student"].email, "it") as c:
        other_purpose = await _upload(c, purpose="default")
        for ids in ([theirs], [other_purpose], [str(uuid.uuid4())]):
            refused = await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": ids})
            assert refused.status_code == 422 and refused.json()["detail"] == "One or more files cannot be attached to this submission"
        six = [await _upload(c) for _ in range(6)]
        assert (await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": six})).status_code == 422
    assert await db_session.scalar(select(Submission.id).where(Submission.assignment_id == w["assignment"].id)) is None


@pytest.mark.asyncio
async def test_a_file_already_on_another_submission_cannot_be_reused(client, db_session):
    w = await _world(db_session)
    second = Assignment(batch_id=w["batch"].id, title="Second", description="d", due_date=w["assignment"].due_date, max_score=10, submission_type="file", published=True)
    db_session.add(second)
    await db_session.commit()
    async with client_for(w["student"].email, "it") as c:
        file_id = await _upload(c)
        assert (await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": [file_id]})).status_code == 201
        assert (await c.post(SUBMIT.format(second.id), json={"file_ids": [file_id]})).status_code == 422


@pytest.mark.asyncio
async def test_submission_type_rules_count_uploaded_files(client, db_session):
    file_world = await _world(db_session, submission_type="file")
    either = await _world(db_session, submission_type="text_or_file")
    text_only = await _world(db_session, submission_type="text")
    async with client_for(file_world["student"].email, "it") as c:
        assert (await c.post(SUBMIT.format(file_world["assignment"].id), json={"answer": "only text"})).json()["detail"] == "A file is required"
        assert (await c.post(SUBMIT.format(file_world["assignment"].id), json={"file_ids": []})).status_code == 422
    async with client_for(either["student"].email, "it") as c:
        assert (await c.post(SUBMIT.format(either["assignment"].id), json={"file_ids": [await _upload(c)]})).status_code == 201
    async with client_for(either["classmate"].email, "it") as c:
        assert (await c.post(SUBMIT.format(either["assignment"].id), json={"answer": "text"})).status_code == 201
    async with client_for(text_only["student"].email, "it") as c:
        assert (await c.post(SUBMIT.format(text_only["assignment"].id), json={"file_ids": [await _upload(c)]})).json()["detail"] == "A text answer is required"


@pytest.mark.asyncio
async def test_resubmitting_with_files_replaces_them_and_without_keeps_them(client, db_session):
    w = await _world(db_session, submission_type="text_or_file")
    async with client_for(w["student"].email, "it") as c:
        first = await _upload(c, "v1.pdf")
        submission_id = (await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": [first]})).json()["id"]
        assert (await c.post(SUBMIT.format(w["assignment"].id), json={"answer": "added a note"})).status_code == 201
        kept = (await db_session.scalars(select(SubmissionFile.stored_file_id).where(SubmissionFile.submission_id == uuid.UUID(submission_id)))).all()
        assert [str(i) for i in kept] == [first]
        second = await _upload(c, "v2.pdf")
        assert (await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": [second]})).status_code == 201
        assert (await c.post(SUBMIT.format(w["assignment"].id), json={"file_ids": [first]})).status_code == 201  # its own earlier file is free again
    replaced = (await db_session.scalars(select(SubmissionFile.stored_file_id).where(SubmissionFile.submission_id == uuid.UUID(submission_id)).execution_options(populate_existing=True))).all()
    assert [str(i) for i in replaced] == [first]


@pytest.mark.asyncio
async def test_a_link_only_submission_still_works_and_lists_no_files(client, db_session):
    w = await _world(db_session)
    async with client_for(w["student"].email, "it") as c:
        submission_id = (await c.post(SUBMIT.format(w["assignment"].id), json={"file_url": "https://github.com/me/repo"})).json()["id"]
    async with client_for(w["trainer"].email, "it") as c:
        row = await _trainer_row(c, submission_id)
        assert row["file_url"] == "https://github.com/me/repo" and row["files"] == []


@pytest.mark.asyncio
async def test_student_assignment_rows_carry_the_submission_type(client, db_session):
    w = await _world(db_session)
    async with client_for(w["student"].email, "it") as c:
        rows = (await c.get("/api/v1/portal/it/student/assignments")).json()["rows"]
    assert next(row for row in rows if row["id"] == str(w["assignment"].id))["submission_type"] == "file"
