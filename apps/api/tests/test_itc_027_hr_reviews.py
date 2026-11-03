"""itc-027 (DEC-SCOPE-354) -- the HR resume-review task: one per IT student, opened by a resume version shared with HR (itc-026), owned
by the programme's HR reviewer or round-robin, worked through the HR stages by its owner only, read by the linked counselor (no internal
fields) and by the student as a student-safe label; the IT Admin reassigns and keeps the rules; a withdrawal closes it."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Batch, Enrollment, HrAssignmentRule, HrReviewStageHistory, HrReviewTask, ItStudentCounselor, Notification, PlacementProfile, User
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, enrol, make_counselor, make_student
from tests.test_itc_026_student_resumes import ME, upload

pytestmark = pytest.mark.asyncio

QUEUE = "/api/v1/hr/review-tasks"
ADMIN_TASKS = "/api/v1/admin/it/hr-review-tasks"
RULES = "/api/v1/admin/it/hr-assignment-rules"
MY_REVIEW = "/api/v1/it/me/hr-review"
SECRET = "Needs SQL joins and a stronger project section"


def hr_url(student_id) -> str:
    return f"/api/v1/hr/students/{student_id}/review"


def staff_review_url(portal: str, student_id) -> str:
    return f"/api/v1/{'counselor' if portal == 'counselor' else 'admin'}/it/students/{student_id}/hr-review"


async def make_hr(db, *, active: bool = True) -> User:
    return await make_user(db, "hr_team", "it", active=active)


async def make_admin(db) -> User:
    return await make_user(db, "it_admin", "it")


async def program_of(db, enrollment: Enrollment):
    return await db.scalar(select(Batch.program_id).where(Batch.id == enrollment.batch_id))


async def ruled_student(db, hr: User, counselor: User | None = None) -> User:
    """An IT student enrolled in a programme whose rule names `hr` (and linked to `counselor` when given)."""
    student = await make_student(db)
    program_id = await program_of(db, await enrol(db, student))
    db.add(HrAssignmentRule(program_id=program_id, hr_user_id=hr.id))
    if counselor:
        db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return student


async def task_of(db, student: User) -> HrReviewTask | None:
    return await db.scalar(select(HrReviewTask).where(HrReviewTask.student_user_id == student.id).execution_options(populate_existing=True))


async def notices(db, user: User, event: str) -> int:
    return await db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id, Notification.event_type == event))


# --- AC1 / AC2 / AC3: a shared upload opens exactly one task, assigned by the rule, and notifies -------------------------------------


async def test_a_shared_upload_opens_one_task_for_the_rule_owner_and_notifies_hr_and_the_counselor(client, db_session):
    hr, counselor = await make_hr(db_session), await make_counselor(db_session, "it")
    student = await ruled_student(db_session, hr, counselor)
    await as_user(client, student)
    assert (await client.get(MY_REVIEW)).json() == {"status": None}

    assert (await upload(client, ME)).status_code == 201
    task = await task_of(db_session, student)
    assert task.owner_user_id == hr.id and task.stage == "resume_received" and task.resume_version == 1 and task.assigned_at is not None
    assert await notices(db_session, hr, "it.resume.uploaded") == 1 and await notices(db_session, counselor, "it.resume.uploaded") == 1

    assert (await upload(client, ME)).status_code == 201  # version 2 updates the same task (AC1)
    assert await db_session.scalar(select(func.count(HrReviewTask.id)).where(HrReviewTask.student_user_id == student.id)) == 1
    assert (await task_of(db_session, student)).resume_version == 2


async def test_a_private_upload_opens_no_task(client, db_session):
    student = await ruled_student(db_session, await make_hr(db_session))
    await as_user(client, student)
    assert (await upload(client, ME, visibility="private")).status_code == 201
    assert await task_of(db_session, student) is None


async def test_a_student_withdrawn_from_placement_gets_no_task(client, db_session):
    student = await ruled_student(db_session, await make_hr(db_session))
    db_session.add(PlacementProfile(student_id=student.id, withdrawn=True))
    await db_session.commit()
    await as_user(client, student)
    assert (await upload(client, ME)).status_code == 201
    assert await task_of(db_session, student) is None


async def test_without_a_rule_round_robin_spreads_tasks_over_active_hr_users(client, db_session):
    await make_hr(db_session), await make_hr(db_session)
    owners = []
    for _ in range(2):
        student = await make_student(db_session)
        await as_user(client, student)
        assert (await upload(client, ME)).status_code == 201
        owners.append(await db_session.get(User, (await task_of(db_session, student)).owner_user_id))
    assert all(o.role == "hr_team" and o.active for o in owners) and owners[0].id != owners[1].id


async def test_a_rule_naming_a_deactivated_hr_user_falls_back_to_round_robin(client, db_session):
    gone = await make_hr(db_session, active=False)
    student = await ruled_student(db_session, gone)
    await as_user(client, student)
    assert (await upload(client, ME)).status_code == 201
    owner = await db_session.get(User, (await task_of(db_session, student)).owner_user_id)
    assert owner.id != gone.id and owner.role == "hr_team" and owner.active


# --- AC4: the owner works the task; the stage move is audited and visible to the counselor --------------------------------------------


async def opened(client, db, hr: User, counselor: User | None = None) -> User:
    student = await ruled_student(db, hr, counselor)
    await as_user(client, student)
    assert (await upload(client, ME)).status_code == 201
    await as_user(client, hr)
    return student


async def test_the_owner_moves_the_stage_and_fills_the_review(client, db_session):
    hr, counselor = await make_hr(db_session), await make_counselor(db_session, "it")
    student = await opened(client, db_session, hr, counselor)

    queue = (await client.get(QUEUE)).json()
    assert queue["total"] == 1 and queue["items"][0]["student"]["id"] == str(student.id) and queue["counts"]["resume_received"] == 1

    body = {"stage": "under_review", "screening_date": "2026-11-20", "role_preferences": "Backend developer", "skill_gap_notes": SECRET, "checklist": ["skills", "contact", "skills"]}
    response = await client.patch(hr_url(student.id), json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["stage"] == "under_review" and data["skill_gap_notes"] == SECRET and data["checklist"] == ["contact", "skills"]
    assert [h["to_stage"] for h in data["history"]] == ["under_review", "resume_received"]

    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.hr_review.update", AuditLog.entity_id == data["id"]))
    assert audit.metadata_json["changes"]["stage"] == ["resume_received", "under_review"] and audit.metadata_json["changes"]["skill_gap_notes"] == "changed"
    assert await notices(db_session, student, "it.placement.updated") == 1 and await notices(db_session, counselor, "it.hr_review.updated") == 1

    await as_user(client, counselor)
    view = (await client.get(staff_review_url("counselor", student.id))).json()["task"]
    assert view["stage"] == "under_review" and view["owner"]["full_name"] == hr.full_name and view["screening_date"] == "2026-11-20"
    assert view["next_action"]
    flat = str(view)
    assert SECRET not in flat and "Backend developer" not in flat and "checklist" not in flat


async def test_saving_without_a_stage_change_writes_no_history(client, db_session):
    hr = await make_hr(db_session)
    student = await opened(client, db_session, hr)
    assert (await client.patch(hr_url(student.id), json={"role_preferences": "QA"})).status_code == 200
    task = await task_of(db_session, student)
    assert await db_session.scalar(select(func.count(HrReviewStageHistory.id)).where(HrReviewStageHistory.task_id == task.id)) == 1


@pytest.mark.parametrize(
    "body", [{"stage": "withdrawn"}, {"stage": "hired"}, {"stage": None}, {"checklist": ["vibes"]}, {"owner_user_id": None}, {"role_preferences": "x" * 301}, {"skill_gap_notes": "x" * 4001}]
)
async def test_invalid_review_input_is_422(client, db_session, body):
    student = await opened(client, db_session, await make_hr(db_session))
    assert (await client.patch(hr_url(student.id), json=body)).status_code == 422


async def test_a_completed_review_takes_no_change_until_a_new_shared_version_reopens_it(client, db_session):
    hr = await make_hr(db_session)
    student = await opened(client, db_session, hr)
    assert (await client.patch(hr_url(student.id), json={"stage": "completed"})).json()["closed_at"] is not None
    assert (await client.patch(hr_url(student.id), json={"stage": "under_review"})).status_code == 409

    await as_user(client, student)
    assert (await upload(client, ME)).status_code == 201
    task = await task_of(db_session, student)
    assert task.stage == "resume_received" and task.closed_at is None and task.owner_user_id == hr.id


# --- AC5: the student sees only the safe label ----------------------------------------------------------------------------------------


async def test_the_student_sees_action_required_and_never_internal_fields(client, db_session):
    hr = await make_hr(db_session)
    student = await opened(client, db_session, hr)
    assert (await client.patch(hr_url(student.id), json={"stage": "changes_requested", "skill_gap_notes": SECRET, "role_preferences": "Data analyst"})).status_code == 200

    await as_user(client, student)
    body = (await client.get(MY_REVIEW)).json()
    assert body["status"]["label"] == "Action required: update your resume" and body["status"]["action"]
    assert set(body["status"]) == {"label", "action", "updated_at"}
    assert SECRET not in str(body) and "Data analyst" not in str(body) and "changes_requested" not in str(body)
    note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id, Notification.event_type == "it.placement.updated"))
    assert SECRET not in note.body and "Action required" not in note.body

    assert (await upload(client, ME)).status_code == 201  # the student acted: back to "Resume received"
    assert (await client.get(MY_REVIEW)).json()["status"]["label"] == "Resume received"


# --- AC6: scope ------------------------------------------------------------------------------------------------------------------------


async def test_another_hr_user_gets_404_and_a_student_or_trainer_gets_403(client, db_session):
    student = await opened(client, db_session, await make_hr(db_session))
    await as_user(client, await make_hr(db_session))
    assert (await client.get(hr_url(student.id))).status_code == 404
    assert (await client.patch(hr_url(student.id), json={"stage": "under_review"})).status_code == 404
    assert (await client.get(QUEUE)).json()["total"] == 0

    for outsider in (student, await make_user(db_session, "trainer", "it")):
        await as_user(client, outsider)
        assert (await client.get(QUEUE)).status_code == 403
        assert (await client.get(hr_url(student.id))).status_code == 403
        assert (await client.get(ADMIN_TASKS)).status_code == 403
        assert (await client.get(RULES)).status_code == 403


async def test_an_unlinked_counselor_gets_404_and_the_student_feed_is_students_only(client, db_session):
    student = await opened(client, db_session, await make_hr(db_session))
    await as_user(client, await make_counselor(db_session, "it"))
    assert (await client.get(staff_review_url("counselor", student.id))).status_code == 404
    assert (await client.get(MY_REVIEW)).status_code == 403


# --- AC7 / H5 / H9: the IT Admin reassigns and keeps the rules; withdrawal closes the task -------------------------------------------


async def test_the_admin_reassigns_a_deactivated_owners_task(client, db_session):
    hr = await make_hr(db_session)
    student = await opened(client, db_session, hr)
    hr.active = False
    await db_session.commit()
    task = await task_of(db_session, student)

    admin, replacement = await make_admin(db_session), await make_hr(db_session)
    await as_user(client, admin)
    listed = (await client.get(ADMIN_TASKS, params={"unassigned": "true", "limit": 200})).json()
    assert str(task.id) in [i["id"] for i in listed["items"]]
    assert (await client.put(f"{ADMIN_TASKS}/{task.id}/owner", json={"hr_user_id": str(hr.id)})).status_code == 422  # inactive
    assert (await client.put(f"{ADMIN_TASKS}/{task.id}/owner", json={"hr_user_id": str(uuid.uuid4())})).status_code == 422
    moved = await client.put(f"{ADMIN_TASKS}/{task.id}/owner", json={"hr_user_id": str(replacement.id)})
    assert moved.status_code == 200 and moved.json()["owner"]["id"] == str(replacement.id)
    assert await notices(db_session, replacement, "it.hr_review.assigned") == 1
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.hr_review.assign", AuditLog.entity_id == str(task.id)))
    assert (await client.get(staff_review_url("admin", student.id))).json()["task"]["owner"]["full_name"] == replacement.full_name

    await as_user(client, replacement)
    assert (await client.get(hr_url(student.id))).status_code == 200


async def test_the_admin_sets_and_removes_a_programme_rule(client, db_session):
    admin, hr = await make_admin(db_session), await make_hr(db_session)
    student = await make_student(db_session)
    program_id = await program_of(db_session, await enrol(db_session, student))
    await as_user(client, admin)
    assert (await client.put(f"{RULES}/{program_id}", json={"hr_user_id": str(admin.id)})).status_code == 422  # not HR
    assert (await client.put(f"{RULES}/{uuid.uuid4()}", json={"hr_user_id": str(hr.id)})).status_code == 404
    saved = await client.put(f"{RULES}/{program_id}", json={"hr_user_id": str(hr.id)})
    assert saved.status_code == 200 and saved.json()["hr_user"]["id"] == str(hr.id)
    listing = (await client.get(RULES)).json()
    assert any(p["program_id"] == str(program_id) and p["hr_user"]["id"] == str(hr.id) for p in listing["programs"])
    assert str(hr.id) in [u["id"] for u in listing["hr_users"]]

    await as_user(client, student)
    assert (await upload(client, ME)).status_code == 201
    assert (await task_of(db_session, student)).owner_user_id == hr.id

    await as_user(client, admin)
    assert (await client.put(f"{RULES}/{program_id}", json={"hr_user_id": None})).json()["hr_user"] is None
    assert await db_session.get(HrAssignmentRule, program_id, populate_existing=True) is None


async def test_opting_out_of_the_placement_pool_closes_the_task(client, db_session):
    hr = await make_hr(db_session)
    student = await opened(client, db_session, hr)
    await as_user(client, student)
    assert (await client.post("/api/v1/account/placement-pool/opt-in", json={"consent_version": "v1"})).status_code == 200
    assert (await task_of(db_session, student)).stage == "resume_received"  # opting in changes nothing
    assert (await client.post("/api/v1/account/placement-pool/opt-out")).status_code == 200
    task = await task_of(db_session, student)
    assert task.stage == "withdrawn" and task.closed_at is not None
    history = (await db_session.scalars(select(HrReviewStageHistory).where(HrReviewStageHistory.task_id == task.id).order_by(HrReviewStageHistory.created_at.desc()))).first()
    assert history.reason == "withdrawn" and history.actor_user_id is None


async def test_placement_marking_the_student_withdrawn_closes_the_task(client, db_session):
    hr = await make_hr(db_session)
    student = await opened(client, db_session, hr)
    await as_user(client, await make_admin(db_session))
    response = await client.put(f"/api/v1/workflows/it/placement/profiles/{student.id}", json={"withdrawn": True})
    assert response.status_code == 200, response.text
    task = await task_of(db_session, student)
    assert task.stage == "withdrawn" and task.closed_at is not None
    await as_user(client, student)
    assert (await client.get(MY_REVIEW)).json()["status"]["label"] == "Review closed"
