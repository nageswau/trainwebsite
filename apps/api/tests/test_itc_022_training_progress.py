"""itc-022 -- modules/topics, computed progress, override, labs and remediation plans (DEC-SCOPE-365).

AC1 computed progress matches the formula; AC2 the manual override is audited; AC3 a remediation plan only for an enrolled student.
+ bulk topic completion for many students; - weights not summing to 100 -> 422; E a programme with no modules stays manual."""

import datetime
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import (
    Assessment,
    AssessmentAttempt,
    Assignment,
    AuditLog,
    Enrollment,
    ItStudentCounselor,
    ProgramTopic,
    RemediationPlan,
    StudentRiskFlag,
    Submission,
    TopicCompletion,
)
from app.services import it_progress
from tests.test_nehn_023_attendance_corrections import _login, _user, _world

PLANS = "/api/v1/admin/it/progress-plans"
TODAY = datetime.date.today()


def _plan(modules: list[tuple[str, list[str]]], weights: dict | None = None) -> dict:
    return {"modules": [{"title": t, "topics": [{"title": x} for x in topics]} for t, topics in modules], "weights": weights}


@pytest_asyncio.fixture
async def world(db_session):
    trainer = await _user(db_session, "trainer", "Progress Trainer")
    admin = await _user(db_session, "it_admin", "Progress Admin")
    counselor = await _user(db_session, "counselor", "Progress Counselor")
    student, batch, _ = await _world(db_session, trainer=trainer)
    enrollment = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == student.id))
    db_session.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=admin.id))
    await db_session.commit()
    return {"trainer": trainer, "admin": admin, "counselor": counselor, "student": student, "batch": batch, "enrollment": enrollment}


async def _save_plan(client, w, body) -> dict:
    await _login(client, w["admin"])
    response = await client.put(f"{PLANS}/{w['batch'].program_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _topic_ids(db, w) -> list:
    plan = await it_progress.read_plan(db, w["batch"].program_id)
    return [t["id"] for m in plan["modules"] for t in m["topics"]]


async def _another_student(db, w, status="active") -> Enrollment:
    student = await _user(db, "it_student", "Second Student")
    e = Enrollment(student_id=student.id, batch_id=w["batch"].id, enrollment_code=f"I022-{uuid.uuid4().hex[:10]}", status=status, progress_percent=0)
    db.add(e)
    await db.commit()
    return e


async def _progress(db, enrollment) -> int:
    await db.refresh(enrollment)
    return enrollment.progress_percent


# --- the formula (pure) --------------------------------------------------------------------------------------------------------------
def test_formula_weights_each_component_and_rounds_half_up():
    w = {"topics": 50, "assignments": 30, "assessments": 20}
    assert it_progress.formula(w, {"topics": (2, 4), "assignments": (1, 2), "assessments": (0, 1)}) == 40  # 25 + 15 + 0
    assert it_progress.formula(w, {"topics": (1, 3), "assignments": (0, 1), "assessments": (0, 1)}) == 17  # 16.67 -> 17
    assert it_progress.formula({"topics": 50, "assignments": 50, "assessments": 0}, {"topics": (1, 8), "assignments": (0, 1), "assessments": (5, 5)}) == 6  # 6.25


def test_a_component_with_nothing_in_the_batch_drops_out_and_the_rest_are_reweighted():
    w = {"topics": 50, "assignments": 30, "assessments": 20}
    assert it_progress.formula(w, {"topics": (4, 4), "assignments": (0, 0), "assessments": (0, 0)}) == 100
    assert it_progress.formula({"topics": 0, "assignments": 100, "assessments": 0}, {"topics": (1, 1), "assignments": (0, 0), "assessments": (0, 0)}) is None


# --- plans (IT Admin) ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_weights_that_do_not_sum_to_100_are_rejected(client, world):
    await _login(client, world["admin"])
    response = await client.put(f"{PLANS}/{world['batch'].program_id}", json=_plan([("Basics", ["OOP"])], {"topics": 50, "assignments": 30, "assessments": 10}))
    assert response.status_code == 422
    assert "add up to 100" in response.text


@pytest.mark.asyncio
async def test_saving_keeps_ids_renames_and_deletes_missing_topics_with_their_completions(client, db_session, world):
    plan = await _save_plan(client, world, _plan([("Basics", ["Syntax", "OOP"]), ("Web", ["HTTP"])], {"topics": 100, "assignments": 0, "assessments": 0}))
    basics, web = plan["modules"]
    syntax, oop = basics["topics"]
    db_session.add(TopicCompletion(topic_id=uuid.UUID(syntax["id"]), enrollment_id=world["enrollment"].id, completed_by_id=world["trainer"].id))
    await db_session.commit()

    body = {"modules": [{"id": basics["id"], "title": "Foundations", "topics": [{"id": oop["id"], "title": "Objects"}, {"title": "Testing"}]}],
            "weights": {"topics": 100, "assignments": 0, "assessments": 0}}  # fmt: skip
    plan = await _save_plan(client, world, body)
    assert [(m["id"], m["title"]) for m in plan["modules"]] == [(basics["id"], "Foundations")]
    assert [t["title"] for t in plan["modules"][0]["topics"]] == ["Objects", "Testing"] and plan["modules"][0]["topics"][0]["id"] == oop["id"]
    assert await db_session.scalar(select(TopicCompletion).where(TopicCompletion.topic_id == uuid.UUID(syntax["id"]))) is None
    assert await db_session.get(ProgramTopic, uuid.UUID(web["topics"][0]["id"])) is None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.progress_plan.update").order_by(AuditLog.created_at.desc()).limit(1))
    assert audit.metadata_json["changes"]["modules"] == [2, 1]


@pytest.mark.asyncio
async def test_an_id_from_another_programme_is_rejected(client, db_session, world):
    _, other_batch, _ = await _world(db_session, trainer=world["trainer"])
    await _login(client, world["admin"])
    other = await client.put(f"{PLANS}/{other_batch.program_id}", json=_plan([("Other", ["X"])]))
    foreign = other.json()["modules"][0]["id"]
    response = await client.put(f"{PLANS}/{world['batch'].program_id}", json={"modules": [{"id": foreign, "title": "Stolen", "topics": []}], "weights": None})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_only_the_it_admin_manages_plans(client, world):
    await _login(client, world["trainer"])
    assert (await client.get(PLANS)).status_code == 403
    assert (await client.put(f"{PLANS}/{world['batch'].program_id}", json=_plan([]))).status_code == 403


@pytest.mark.asyncio
async def test_the_plan_offers_the_curriculum_to_copy(client, world):
    await _login(client, world["admin"])
    body = (await client.get(f"{PLANS}/{world['batch'].program_id}")).json()
    assert body["copy_source"] == [{"title": "Module 1", "topics": []}] and body["computed"] is False and body["weights"] is None


# --- AC1 computed progress, bulk completion, refresh -------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bulk_marking_a_topic_for_many_students_recomputes_their_progress(client, db_session, world):
    second = await _another_student(db_session, world)
    await _save_plan(client, world, _plan([("Basics", ["Syntax", "OOP", "Testing", "Git"])], {"topics": 100, "assignments": 0, "assessments": 0}))
    syntax, oop, *_ = await _topic_ids(db_session, world)

    await _login(client, world["trainer"])
    url = f"/api/v1/it/batches/{world['batch'].id}/topics/{oop}/completions"
    ids = [str(world["enrollment"].id), str(second.id)]
    response = await client.put(url, json={"enrollment_ids": ids, "completed": True})
    assert response.status_code == 200, response.text
    assert sorted(response.json()["completed_enrollment_ids"]) == sorted(ids)
    assert (await client.put(url, json={"enrollment_ids": ids, "completed": True})).status_code == 200  # idempotent
    assert await _progress(db_session, world["enrollment"]) == 25 and await _progress(db_session, second) == 25

    await client.put(f"/api/v1/it/batches/{world['batch'].id}/topics/{syntax}/completions", json={"enrollment_ids": ids[:1], "completed": True})
    assert await _progress(db_session, world["enrollment"]) == 50
    await client.put(url, json={"enrollment_ids": ids, "completed": False})
    assert await _progress(db_session, world["enrollment"]) == 25 and await _progress(db_session, second) == 0

    topics = (await client.get(f"/api/v1/it/batches/{world['batch'].id}/topics")).json()
    assert topics["computed"] is True and topics["modules"][0]["topics"][0]["completed_enrollment_ids"] == ids[:1]


@pytest.mark.asyncio
async def test_completion_rejects_inactive_students_and_other_trainers(client, db_session, world):
    await _save_plan(client, world, _plan([("Basics", ["OOP"])], {"topics": 100, "assignments": 0, "assessments": 0}))
    [oop] = await _topic_ids(db_session, world)
    dropped = await _another_student(db_session, world, status="dropped")
    url = f"/api/v1/it/batches/{world['batch'].id}/topics/{oop}/completions"
    await _login(client, world["trainer"])
    response = await client.put(url, json={"enrollment_ids": [str(world["enrollment"].id), str(dropped.id)], "completed": True})
    assert response.status_code == 422 and "1 of the selected students is not an active student" in response.text
    assert await db_session.scalar(select(TopicCompletion.id).where(TopicCompletion.topic_id == uuid.UUID(oop))) is None  # nothing half-done

    stranger = await _user(db_session, "trainer", "Other Trainer")
    await _login(client, stranger)
    assert (await client.put(url, json={"enrollment_ids": [str(world["enrollment"].id)], "completed": True})).status_code == 403
    await _login(client, world["student"])
    assert (await client.get(f"/api/v1/it/batches/{world['batch'].id}/topics")).status_code == 403


@pytest.mark.asyncio
async def test_grading_moves_the_computed_progress_with_labs_counted_as_assignments(client, db_session, world):
    await _save_plan(client, world, _plan([("Basics", ["OOP"])], {"topics": 40, "assignments": 40, "assessments": 20}))
    due = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3)
    await _login(client, world["trainer"])
    created = await client.post(
        "/api/v1/workflows/it/trainer/assignments",
        json={"batch_id": str(world["batch"].id), "title": "Lab 1", "description": "d", "due_date": due.isoformat(), "max_score": 10, "assignment_type": "lab"},
    )
    assert created.status_code == 201, created.text
    lab = await db_session.get(Assignment, uuid.UUID(created.json()["id"]))
    assert lab.assignment_type == "lab"
    submission = Submission(assignment_id=lab.id, student_id=world["student"].id, answer="done", status="submitted")
    db_session.add(submission)
    await db_session.commit()
    # one assignment (ungraded), no assessment: topics 0/1 and assignments 0/1 weigh 40/40 -> 0
    assert (await client.patch(f"/api/v1/workflows/it/trainer/submissions/{submission.id}", json={"score": 8, "feedback": "ok", "status": "graded"})).status_code == 200
    assert await _progress(db_session, world["enrollment"]) == 50  # (40*0 + 40*1) / 80

    body = (await client.get(f"/api/v1/workflows/it/batches/{world['batch'].id}/progress")).json()
    row = body["students"][0]
    assert body["progress_mode"] == "computed"
    assert (row["labs_graded"], row["labs_total"], row["topics_completed"], row["topics_total"], row["computed_percent"]) == (1, 1, 0, 1, 50)


@pytest.mark.asyncio
async def test_a_graded_assessment_attempt_counts_through_the_trainer_grade(client, db_session, world):
    await _save_plan(client, world, _plan([("Basics", ["OOP"])], {"topics": 50, "assignments": 0, "assessments": 50}))
    assessment = Assessment(batch_id=world["batch"].id, title="Quiz", scheduled_at=datetime.datetime.now(datetime.UTC), status="published", pass_percent=50)
    db_session.add(assessment)
    await db_session.flush()
    attempt = AssessmentAttempt(assessment_id=assessment.id, student_id=world["student"].id, status="submitted", submitted_at=datetime.datetime.now(datetime.UTC))
    db_session.add(attempt)
    await db_session.commit()
    await _login(client, world["trainer"])
    response = await client.patch(f"/api/v1/workflows/it/trainer/assessment-attempts/{attempt.id}", json={"score": 90, "feedback": "Good"})
    assert response.status_code == 200, response.text  # 90 of the default max 100: passed (pass mark 50)
    assert await _progress(db_session, world["enrollment"]) == 50  # topics 0/1, assessments 1/1


@pytest.mark.asyncio
async def test_a_programme_without_modules_stays_manual(client, db_session, world):
    await _save_plan(client, world, _plan([], {"topics": 100, "assignments": 0, "assessments": 0}))
    await _login(client, world["trainer"])
    response = await client.patch(f"/api/v1/workflows/it/trainer/enrollments/{world['enrollment'].id}/progress", json={"progress_percent": 42})
    assert response.status_code == 200 and response.json()["override_reason"] is None
    assert await _progress(db_session, world["enrollment"]) == 42
    assert (await client.get(f"/api/v1/workflows/it/batches/{world['batch'].id}/progress")).json()["progress_mode"] == "manual"


# --- AC2 the override ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_override_needs_a_reason_is_audited_survives_refresh_and_can_be_cleared(client, db_session, world):
    await _save_plan(client, world, _plan([("Basics", ["OOP", "Git"])], {"topics": 100, "assignments": 0, "assessments": 0}))
    [oop, _git] = await _topic_ids(db_session, world)
    url = f"/api/v1/workflows/it/trainer/enrollments/{world['enrollment'].id}/progress"
    await _login(client, world["trainer"])
    assert (await client.patch(url, json={"progress_percent": 80})).status_code == 422
    assert (await client.patch(url, json={"progress_percent": 80, "reason": "   "})).status_code == 422
    response = await client.patch(url, json={"progress_percent": 80, "reason": "Completed the advanced track offline"})
    assert response.status_code == 200 and response.json()["override_reason"] == "Completed the advanced track offline"

    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "enrollment.progress_override", AuditLog.entity_id == str(world["enrollment"].id)))
    assert audit.metadata_json["changes"]["progress_percent"] == [0, 80]

    await client.put(f"/api/v1/it/batches/{world['batch'].id}/topics/{oop}/completions", json={"enrollment_ids": [str(world["enrollment"].id)], "completed": True})
    assert await _progress(db_session, world["enrollment"]) == 80  # the override sticks

    cleared = await client.delete(f"{url}/override")
    assert cleared.status_code == 200 and cleared.json()["progress_percent"] == 50
    audits = list(await db_session.scalars(select(AuditLog).where(AuditLog.action == "enrollment.progress_override", AuditLog.entity_id == str(world["enrollment"].id))))
    assert len(audits) == 2


# --- AC3 remediation plans -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_plan_is_created_for_an_active_student_linked_to_the_open_flag(client, db_session, world):
    flag = StudentRiskFlag(enrollment_id=world["enrollment"].id, student_id=world["student"].id, batch_id=world["batch"].id, reasons=["attendance"], raised_at=datetime.datetime.now(datetime.UTC))
    db_session.add(flag)
    await db_session.commit()
    await _login(client, world["trainer"])
    url = f"/api/v1/it/enrollments/{world['enrollment'].id}/remediation-plans"
    response = await client.post(url, json={"actions": "Two extra lab sessions", "due_date": str(TODAY + datetime.timedelta(days=7)), "owner_user_id": str(world["counselor"].id)})
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["status"] == "open" and plan["risk_flag_id"] == str(flag.id) and plan["owner_name"] == "Progress Counselor"
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "it.remediation_plan.create", AuditLog.entity_id == plan["id"]))


@pytest.mark.asyncio
async def test_a_plan_cannot_be_created_for_a_student_who_is_not_actively_enrolled(client, db_session, world):
    dropped = await _another_student(db_session, world, status="dropped")
    await _login(client, world["trainer"])
    response = await client.post(f"/api/v1/it/enrollments/{dropped.id}/remediation-plans", json={"actions": "Catch up", "due_date": str(TODAY)})
    assert response.status_code == 422 and "actively enrolled" in response.text
    assert await db_session.scalar(select(RemediationPlan.id).where(RemediationPlan.enrollment_id == dropped.id)) is None


@pytest.mark.asyncio
async def test_plan_rules_past_due_bad_owner_other_trainer(client, db_session, world):
    url = f"/api/v1/it/enrollments/{world['enrollment'].id}/remediation-plans"
    await _login(client, world["trainer"])
    assert (await client.post(url, json={"actions": "x", "due_date": str(TODAY - datetime.timedelta(days=2))})).status_code == 422
    stranger = await _user(db_session, "trainer", "Stranger Trainer")
    assert (await client.post(url, json={"actions": "x", "due_date": str(TODAY), "owner_user_id": str(stranger.id)})).status_code == 422
    await _login(client, stranger)
    assert (await client.post(url, json={"actions": "x", "due_date": str(TODAY)})).status_code == 404
    await _login(client, world["counselor"])
    assert (await client.post(url, json={"actions": "x", "due_date": str(TODAY)})).status_code == 403


@pytest.mark.asyncio
async def test_plan_updates_owner_status_only_closed_final_and_reads_scoped(client, db_session, world):
    await _login(client, world["trainer"])
    created = await client.post(f"/api/v1/it/enrollments/{world['enrollment'].id}/remediation-plans",
                                json={"actions": "Weekly check-in", "due_date": str(TODAY + datetime.timedelta(days=3)), "owner_user_id": str(world["counselor"].id)})  # fmt: skip
    plan_url = f"/api/v1/it/remediation-plans/{created.json()['id']}"

    await _login(client, world["counselor"])  # the owner: status only
    assert (await client.patch(plan_url, json={"actions": "changed"})).status_code == 403
    assert (await client.patch(plan_url, json={"status": "in_progress"})).json()["status"] == "in_progress"
    listing = (await client.get(f"/api/v1/it/students/{world['student'].id}/remediation-plans")).json()
    assert [p["status"] for p in listing["items"]] == ["in_progress"] and listing["enrollments"] == []  # the counselor reads, cannot create

    await _login(client, world["trainer"])
    assert (await client.patch(plan_url, json={"status": "completed"})).status_code == 200
    assert (await client.patch(plan_url, json={"status": "open"})).status_code == 409

    hr = await _user(db_session, "hr_team", "HR Person")
    await _login(client, hr)
    assert (await client.get(f"/api/v1/it/students/{world['student'].id}/remediation-plans")).status_code == 403
    stranger = await _user(db_session, "trainer", "Stranger Trainer")
    await _login(client, stranger)
    assert (await client.get(f"/api/v1/it/students/{world['student'].id}/remediation-plans")).status_code == 404
    assert (await client.patch(plan_url, json={"status": "cancelled"})).status_code == 404


# --- the student's view --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_student_sees_their_progress_topics_and_plans_without_internal_fields(client, db_session, world):
    await _save_plan(client, world, _plan([("Basics", ["OOP", "Git"])], {"topics": 100, "assignments": 0, "assessments": 0}))
    [oop, _] = await _topic_ids(db_session, world)
    await _login(client, world["trainer"])
    await client.put(f"/api/v1/it/batches/{world['batch'].id}/topics/{oop}/completions", json={"enrollment_ids": [str(world["enrollment"].id)], "completed": True})
    await client.post(f"/api/v1/it/enrollments/{world['enrollment'].id}/remediation-plans", json={"actions": "Revise Git", "due_date": str(TODAY)})

    await _login(client, world["student"])
    body = (await client.get("/api/v1/it/me/progress")).json()
    [course] = body["courses"]
    assert course["progress_percent"] == 50 and course["mode"] == "computed" and course["weights"]["topics"] == 100
    assert course["modules"] == [{"title": "Basics", "topics": [{"title": "OOP", "completed": True}, {"title": "Git", "completed": False}]}]
    [plan] = body["remediation_plans"]
    assert plan["actions"] == "Revise Git" and "owner_user_id" not in plan and "risk_flag_id" not in plan

    await _login(client, world["trainer"])
    assert (await client.get("/api/v1/it/me/progress")).status_code == 403
