"""nehn-026 -- keyword-based auto-scoring of written answers.

AC1 keywords [a..e] at the 80% threshold: 4 matched -> full marks, 3 -> proportional; AC2 a trainer override replaces the keyword score,
keeps the suggestion and is audited; AC3 no student payload carries the keywords; AC4 questions without keywords stay manual."""

import datetime
import json
import uuid

import pytest
from sqlalchemy import select
from test_nehn_025_question_import import _import, _row, _xlsx

from app.core.security import hash_password
from app.models import Assessment, AssessmentAnswer, AssessmentQuestion, AuditLog, Batch, Enrollment, Program, User

PASSWORD = "Sup3r-Secret-Pass!"
BASE = "/api/v1/workflows/it/trainer/assessments"
KEYWORDS = ["alpha", "beta", "gamma", "delta", "epsilon"]


async def _user(db, role: str, division: str = "it") -> User:
    user = User(email=f"n026-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=f"N026 {role}", role=role, division=division, active=True)
    db.add(user)
    await db.commit()
    return user


async def _batch(db, trainer: User) -> Batch:
    program = Program(
        slug=f"n026-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"N026 Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=0,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"N026-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db.add(batch)
    await db.commit()
    return batch


async def _login(client, user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": user.division})
    assert response.status_code == 200, response.text


async def _world(db, client):
    """A trainer's scheduled assessment: a keyword text question (10 marks), a plain text question (5) and an MCQ (2)."""
    trainer = await _user(db, "trainer")
    student = await _user(db, "it_student")
    batch = await _batch(db, trainer)
    db.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N026-{uuid.uuid4().hex[:6]}", status="active"))
    assessment = Assessment(batch_id=batch.id, title=f"N026 Quiz {uuid.uuid4().hex[:6]}", scheduled_at=datetime.datetime.now(datetime.UTC), status="scheduled")
    db.add(assessment)
    await db.commit()
    await _login(client, trainer)
    payload = [
        {"question_type": "text", "prompt": "Name the five letters", "keywords": KEYWORDS, "max_score": 10, "position": 1},
        {"question_type": "text", "prompt": "Describe your week", "max_score": 5, "position": 2},
        {"question_type": "mcq_single", "prompt": "2 + 2?", "options": ["3", "4"], "correct_answers": ["4"], "max_score": 2, "position": 3},
    ]
    response = await client.post(f"{BASE}/{assessment.id}/questions/bulk", json=payload)
    assert response.status_code == 201, response.text
    keyword_q, plain_q, mcq_q = response.json()["ids"]
    return trainer, student, assessment, keyword_q, plain_q, mcq_q


async def _submit(client, student, assessment, answers: dict) -> tuple[str, dict]:
    await _login(client, student)
    started = await client.post(f"/api/v1/workflows/it/assessments/{assessment.id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["id"]
    submitted = await client.post(f"/api/v1/workflows/it/assessment-attempts/{attempt_id}/submit", json={"answers": [{"question_id": q, "value": v} for q, v in answers.items()]})
    assert submitted.status_code == 200, submitted.text
    return attempt_id, {"start": started.json(), "submit": submitted.json()}


async def _answers(db, attempt_id) -> dict[str, AssessmentAnswer]:
    rows = (await db.scalars(select(AssessmentAnswer).where(AssessmentAnswer.attempt_id == uuid.UUID(attempt_id)).execution_options(populate_existing=True))).all()
    return {str(a.question_id): a for a in rows}


# --- question authoring ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_keywords_are_saved_trimmed_and_listed_to_the_trainer(db_session, client):
    trainer, _, assessment, keyword_q, plain_q, _ = await _world(db_session, client)
    response = await client.post(f"{BASE}/{assessment.id}/questions", json={"question_type": "text", "prompt": "Loops?", "keywords": ["  for loop ", "", "loop|iteration"], "position": 4})
    assert response.status_code == 201, response.text
    listed = {q["id"]: q for q in (await client.get(f"{BASE}/{assessment.id}/questions")).json()}
    assert listed[keyword_q]["keywords"] == KEYWORDS
    assert listed[plain_q]["keywords"] == []
    assert listed[response.json()["id"]]["keywords"] == ["for loop", "loop|iteration"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,extra", [("file", {}), ("mcq_single", {"options": ["a", "b"], "correct_answers": ["a"]})])
async def test_keywords_are_refused_on_non_text_questions(db_session, client, kind, extra):
    _, _, assessment, *_ = await _world(db_session, client)
    response = await client.post(f"{BASE}/{assessment.id}/questions", json={"question_type": kind, "prompt": "Nope", "keywords": ["x"], **extra})
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Keywords can only be set on a written-answer (text) question"  # QA-01: no "Value error, "


@pytest.mark.asyncio
async def test_too_many_or_too_long_keywords_are_refused(db_session, client):
    _, _, assessment, *_ = await _world(db_session, client)
    many = await client.post(f"{BASE}/{assessment.id}/questions", json={"question_type": "text", "prompt": "Many", "keywords": [f"k{n}" for n in range(31)]})
    long = await client.post(f"{BASE}/{assessment.id}/questions", json={"question_type": "text", "prompt": "Long", "keywords": ["x" * 101]})
    assert many.status_code == 422 and long.status_code == 422
    # QA-02: the messages name the keywords, not a bare "String should have at most 100 characters"
    assert many.json()["detail"][0]["msg"] == "At most 30 keywords"
    assert long.json()["detail"][0]["msg"] == "Each keyword can be at most 100 characters"


# --- AC1 / AC4: submit ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_four_of_five_keywords_get_full_marks_and_the_attempt_still_awaits_review(db_session, client):
    _, student, assessment, keyword_q, plain_q, mcq_q = await _world(db_session, client)
    attempt_id, bodies = await _submit(client, student, assessment, {keyword_q: "Alpha, beta and gamma -- then epsilon.", plain_q: "Busy", mcq_q: "4"})
    answers = await _answers(db_session, attempt_id)
    assert float(answers[keyword_q].score) == 10.0 and float(answers[keyword_q].auto_score) == 10.0 and answers[keyword_q].score_source == "keyword"
    assert answers[mcq_q].score_source == "mcq" and float(answers[mcq_q].score) == 2.0
    # AC4: a written question without keywords stays manual
    assert answers[plain_q].score is None and answers[plain_q].auto_score is None and answers[plain_q].score_source is None
    assert bodies["submit"]["status"] == "submitted"  # K4: trainer-reviewed, never auto-published
    assert bodies["submit"]["score"] == 12.0


@pytest.mark.asyncio
async def test_ac1_below_the_threshold_marks_are_proportional(db_session, client):
    _, student, assessment, keyword_q, plain_q, mcq_q = await _world(db_session, client)
    attempt_id, _ = await _submit(client, student, assessment, {keyword_q: "alpha beta gamma", plain_q: "x", mcq_q: "3"})
    assert float((await _answers(db_session, attempt_id))[keyword_q].score) == 6.0


@pytest.mark.asyncio
async def test_an_mcq_only_assessment_still_grades_itself(db_session, client):
    trainer = await _user(db_session, "trainer")
    student = await _user(db_session, "it_student")
    batch = await _batch(db_session, trainer)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N026-{uuid.uuid4().hex[:6]}", status="active"))
    assessment = Assessment(batch_id=batch.id, title="MCQ only", scheduled_at=datetime.datetime.now(datetime.UTC), status="scheduled")
    db_session.add(assessment)
    await db_session.flush()
    question = AssessmentQuestion(assessment_id=assessment.id, question_type="mcq_single", prompt="1+1?", options=["1", "2"], correct_answers=["2"], max_score=1)
    db_session.add(question)
    await db_session.commit()
    _, bodies = await _submit(client, student, assessment, {str(question.id): "2"})
    assert bodies["submit"]["status"] == "graded"


# --- AC3: students never see the keywords ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac3_no_student_payload_carries_the_keywords(db_session, client):
    _, student, assessment, keyword_q, plain_q, mcq_q = await _world(db_session, client)
    _, bodies = await _submit(client, student, assessment, {keyword_q: "alpha", plain_q: "x", mcq_q: "4"})
    learning = await client.get("/api/v1/workflows/it/student/learning")
    assert learning.status_code == 200, learning.text
    for text in (json.dumps(bodies), learning.text):
        assert "epsilon" not in text and "keywords" not in text and "auto_score" not in text and "matched_keywords" not in text
    assert all(set(q) == {"id", "question_type", "prompt", "options", "max_score", "required"} for q in bodies["start"]["questions"])
    assert (await client.get(f"{BASE}/{assessment.id}/questions")).status_code == 403


# --- trainer review + AC2 override ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_trainer_sees_the_score_breakdown(db_session, client):
    trainer, student, assessment, keyword_q, plain_q, mcq_q = await _world(db_session, client)
    attempt_id, _ = await _submit(client, student, assessment, {keyword_q: "ALPHA and Delta", plain_q: "x", mcq_q: "4"})
    await _login(client, trainer)
    detail = (await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}")).json()
    by_question = {a["question_id"]: a for a in detail["answers"]}
    keyword = by_question[keyword_q]
    assert keyword["keywords"] == KEYWORDS and keyword["matched_keywords"] == ["alpha", "delta"] and keyword["match_percent"] == 40.0
    assert keyword["score_source"] == "keyword" and keyword["auto_score"] == 4.0 and keyword["score"] == 4.0 and keyword["auto_graded"] is False
    assert by_question[plain_q]["keywords"] == [] and by_question[plain_q]["matched_keywords"] == [] and by_question[plain_q]["score_source"] is None
    assert by_question[mcq_q]["score_source"] == "mcq" and by_question[mcq_q]["auto_graded"] is True


@pytest.mark.asyncio
async def test_ac2_the_trainer_override_replaces_the_score_keeps_the_suggestion_and_is_audited(db_session, client):
    trainer, student, assessment, keyword_q, plain_q, mcq_q = await _world(db_session, client)
    attempt_id, _ = await _submit(client, student, assessment, {keyword_q: "alpha beta gamma delta", plain_q: "x", mcq_q: "4"})
    answers = await _answers(db_session, attempt_id)
    await _login(client, trainer)
    graded = await client.patch(
        f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}",
        json={"answer_scores": {str(answers[keyword_q].id): 3, str(answers[plain_q].id): 5}, "feedback": "Keyword stuffing"},
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["score"] == 10.0 and graded.json()["status"] == "graded"
    answers = await _answers(db_session, attempt_id)
    assert float(answers[keyword_q].score) == 3.0 and float(answers[keyword_q].auto_score) == 10.0 and answers[keyword_q].score_source == "trainer"
    assert answers[plain_q].score_source == "trainer" and answers[mcq_q].score_source == "mcq"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == attempt_id, AuditLog.action == "assessment.attempt_grade"))).one()
    assert audit.metadata_json["overrides"] == [{"answer_id": str(answers[keyword_q].id), "auto_score": 10.0, "score": 3.0}]


@pytest.mark.asyncio
async def test_accepting_the_keyword_score_unchanged_keeps_its_source(db_session, client):
    trainer, student, assessment, keyword_q, plain_q, mcq_q = await _world(db_session, client)
    attempt_id, _ = await _submit(client, student, assessment, {keyword_q: "alpha beta gamma delta", plain_q: "x", mcq_q: "4"})
    answers = await _answers(db_session, attempt_id)
    await _login(client, trainer)
    graded = await client.patch(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}", json={"answer_scores": {str(answers[keyword_q].id): 10, str(answers[plain_q].id): 1}})
    assert graded.json()["score"] == 13.0
    answers = await _answers(db_session, attempt_id)
    assert answers[keyword_q].score_source == "keyword"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == attempt_id, AuditLog.action == "assessment.attempt_grade"))).one()
    assert audit.metadata_json["overrides"] == []


@pytest.mark.asyncio
async def test_another_trainer_cannot_see_the_breakdown(db_session, client):
    _, student, assessment, keyword_q, plain_q, mcq_q = await _world(db_session, client)
    attempt_id, _ = await _submit(client, student, assessment, {keyword_q: "alpha", plain_q: "x", mcq_q: "4"})
    await _login(client, await _user(db_session, "trainer"))
    assert (await client.get(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}")).status_code == 403


# --- the nehn-025 import saves the keywords column ---------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_import_saves_the_keywords_column_and_shows_it_in_the_preview(db_session, client):
    _, _, assessment, *_ = await _world(db_session, client)
    rows = [_row("text", "Explain loops", marks=4, keywords="for loop, loop|iteration , ,while")]
    preview = (await _import(client, assessment.id, _xlsx(rows))).json()
    assert preview["errors"] == [] and preview["warnings"] == []
    assert preview["questions"][0]["keywords"] == ["for loop", "loop|iteration", "while"]
    committed = await _import(client, assessment.id, _xlsx(rows), commit=True)
    assert committed.status_code == 201, committed.text
    saved = await db_session.scalar(select(AssessmentQuestion.keywords).where(AssessmentQuestion.assessment_id == assessment.id, AssessmentQuestion.prompt == "Explain loops"))
    assert saved == ["for loop", "loop|iteration", "while"]


@pytest.mark.asyncio
async def test_the_import_refuses_keywords_on_non_text_rows_and_too_many_keywords(db_session, client):
    _, _, assessment, *_ = await _world(db_session, client)
    rows = [
        _row("mcq_single", "Pick one", ["a", "b"], 1, keywords="a"),
        _row("file", "Upload it", keywords="diagram"),
        _row("text", "Too many", keywords=",".join(f"k{n}" for n in range(31))),
        _row("text", "Too long", keywords="x" * 101),
    ]
    errors = (await _import(client, assessment.id, _xlsx(rows))).json()["errors"]
    assert errors == [
        {"row": 2, "message": "Keywords can only be set on a text question"},
        {"row": 3, "message": "Keywords can only be set on a text question"},
        {"row": 4, "message": "At most 30 keywords, separated by commas"},
        {"row": 5, "message": "Each keyword can be at most 100 characters"},
    ]
