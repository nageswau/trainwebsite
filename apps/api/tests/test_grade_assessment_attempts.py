"""Fix for the "blind grading" bug (RAID.md, Trainer assessments page): the trainer
grading UI never showed a student's actual submitted answer, so `PATCH
/workflows/it/trainer/assessment-attempts/{id}` was called against a bare "total score"
field with no visibility into what was actually written. The per-question data
(`AssessmentAnswer`) already existed and the PATCH endpoint already accepted per-question
`answer_scores` -- the real gap was that nothing ever returned those answers to the
trainer. Adds `GET /workflows/it/trainer/assessment-attempts/{id}` (this file's own new
coverage) and confirms per-question grading via the pre-existing `answer_scores` field
now actually reaches the UI-visible data this endpoint surfaces.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Enrollment, Program, User


async def _create_trainer(db_session, *, email_prefix: str = "grade-trainer") -> User:
    trainer = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Grading Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_student(db_session) -> User:
    student = User(
        email=f"grade-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Attempt Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_batch(db_session, trainer: User) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Grading Test Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


async def _submitted_attempt(client, db_session, trainer: User):
    """Creates a batch/student/assessment with one auto-graded MCQ and one manually
    graded written question, has the student start and submit an attempt, and returns
    the attempt id plus the raw question ids."""
    batch = await _create_batch(db_session, trainer)
    student = await _create_student(db_session)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await _login(client, trainer.email)
    created = await client.post(
        "/api/v1/workflows/it/trainer/assessments",
        json={"batch_id": str(batch.id), "title": "Grading Fix Quiz", "scheduled_at": "2027-01-10T10:00:00Z", "status": "scheduled"},
    )
    assert created.status_code == 201
    assessment_id = created.json()["id"]

    mcq = await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "mcq_single", "prompt": "2 + 2 = ?", "options": ["3", "4", "5"], "correct_answers": ["4"], "max_score": 5, "position": 1},
    )
    assert mcq.status_code == 201
    written = await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "text", "prompt": "Explain the FastAPI dependency system.", "max_score": 10, "position": 2},
    )
    assert written.status_code == 201

    await _login(client, student.email)
    start = await client.post(f"/api/v1/workflows/it/assessments/{assessment_id}/attempts")
    assert start.status_code == 201
    attempt_id = start.json()["id"]

    submit = await client.post(
        f"/api/v1/workflows/it/assessment-attempts/{attempt_id}/submit",
        json={"answers": [
            {"question_id": mcq.json()["id"], "value": "4"},
            {"question_id": written.json()["id"], "value": "Dependencies are resolved per-request via Depends()."},
        ]},
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted"  # manual grading still pending

    return attempt_id, mcq.json()["id"], written.json()["id"], student, trainer


@pytest.mark.asyncio
async def test_trainer_sees_the_students_real_answers_not_a_blind_form(client, db_session):
    trainer = await _create_trainer(db_session)
    attempt_id, _mcq_id, _written_id, _student, _trainer = await _submitted_attempt(client, db_session, trainer)

    await _login(client, trainer.email)
    detail = await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "submitted"

    answers = {a["prompt"]: a for a in body["answers"]}
    assert answers["2 + 2 = ?"]["auto_graded"] is True
    assert answers["2 + 2 = ?"]["value"] == "4"
    assert answers["2 + 2 = ?"]["score"] == 5  # auto-graded correct, full marks

    written_answer = answers["Explain the FastAPI dependency system."]
    assert written_answer["auto_graded"] is False
    assert written_answer["value"] == "Dependencies are resolved per-request via Depends()."
    assert written_answer["score"] is None  # not blind data -- the real text is visible, not yet manually scored


@pytest.mark.asyncio
async def test_file_response_question_answer_is_a_real_uploaded_file_url(client, db_session):
    """RAID.md I-18 sub-item 2: a `file`-response question previously fell back to a plain
    textarea on the student side, so nothing was ever actually uploaded. Confirms the real
    fix -- the student uploads a real file via the existing `/files/local-upload` endpoint
    first, then submits its returned URL as the answer value, and the trainer's own
    (bug #1) detail endpoint reports it as a real, openable file URL, not free text."""
    trainer = await _create_trainer(db_session, email_prefix="grade-file-trainer")
    batch = await _create_batch(db_session, trainer)
    student = await _create_student(db_session)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()

    await _login(client, trainer.email)
    created = await client.post(
        "/api/v1/workflows/it/trainer/assessments",
        json={"batch_id": str(batch.id), "title": "File Response Quiz", "scheduled_at": "2027-01-10T10:00:00Z", "status": "scheduled"},
    )
    assessment_id = created.json()["id"]
    question = await client.post(
        f"/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions",
        json={"question_type": "file", "prompt": "Upload your worked-out solution.", "max_score": 10, "position": 1},
    )
    assert question.status_code == 201

    await _login(client, student.email)
    start = await client.post(f"/api/v1/workflows/it/assessments/{assessment_id}/attempts")
    attempt_id = start.json()["id"]

    upload = await client.post("/api/v1/files/local-upload", files={"file": ("solution.pdf", b"%PDF-1.4 fake content", "application/pdf")})
    assert upload.status_code == 200
    file_url = upload.json()["url"]
    assert file_url  # a real, server-issued key/URL -- not a client-typed string

    submit = await client.post(
        f"/api/v1/workflows/it/assessment-attempts/{attempt_id}/submit",
        json={"answers": [{"question_id": question.json()["id"], "value": file_url}]},
    )
    assert submit.status_code == 200

    await _login(client, trainer.email)
    detail = await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}")
    assert detail.status_code == 200
    answer = detail.json()["answers"][0]
    assert answer["question_type"] == "file"
    assert answer["value"] == file_url  # the real uploaded file's URL, not placeholder/empty text


@pytest.mark.asyncio
async def test_trainer_grades_per_question_and_total_reflects_it(client, db_session):
    trainer = await _create_trainer(db_session)
    attempt_id, _mcq_id, _written_id, _student, _trainer = await _submitted_attempt(client, db_session, trainer)

    await _login(client, trainer.email)
    detail = await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}")
    written_answer_id = next(a["id"] for a in detail.json()["answers"] if not a["auto_graded"])

    grade = await client.patch(
        f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}",
        json={"answer_scores": {written_answer_id: 8}, "feedback": "Solid explanation, missed scoping."},
    )
    assert grade.status_code == 200
    assert grade.json()["status"] == "graded"
    assert grade.json()["score"] == 13  # 5 (auto MCQ) + 8 (manually scored written answer)
    assert grade.json()["percentage"] == round(13 * 100 / 15, 2)  # 5+10 possible across both questions, backend rounds to 2dp

    recheck = await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}")
    assert recheck.status_code == 200
    written_answer = next(a for a in recheck.json()["answers"] if a["id"] == written_answer_id)
    assert written_answer["score"] == 8
    assert recheck.json()["feedback"] == "Solid explanation, missed scoping."


@pytest.mark.asyncio
async def test_trainer_cannot_view_an_attempt_outside_their_batch(client, db_session):
    owner = await _create_trainer(db_session, email_prefix="grade-owner")
    outsider = await _create_trainer(db_session, email_prefix="grade-outsider")
    attempt_id, *_ = await _submitted_attempt(client, db_session, owner)

    await _login(client, outsider.email)
    response = await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_viewing_an_unknown_attempt_404s(client, db_session):
    trainer = await _create_trainer(db_session)
    await _login(client, trainer.email)
    response = await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_viewing_attempt_detail_requires_authentication(client):
    response = await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{uuid.uuid4()}")
    assert response.status_code == 401
