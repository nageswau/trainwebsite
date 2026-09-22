import uuid

import pytest
from enh005_helpers import mk_staff, move_student_directly
from enh011_helpers import BATCHES, ENROLMENTS, create_batch, enrol, login, skills_world
from sqlalchemy import func, select

from app.api import school_skills
from app.models import AuditLog, Notification, SchoolSkillEnrollment, SchoolStaffAssignment

# ENH-011 spec §5.1/§5.4: enrolment, the status transition table, parent notifications after commit. AC-02, AC-05, AC-06,
# AC-07, AC-12.


async def _notifications(db, parent) -> list[Notification]:
    return (await db.scalars(select(Notification).where(Notification.user_id == parent.id).order_by(Notification.created_at.asc()))).all()


async def _enrolment_count(db, batch_id) -> int:
    return await db.scalar(select(func.count()).select_from(SchoolSkillEnrollment).where(SchoolSkillEnrollment.batch_id == batch_id))


@pytest.mark.asyncio
async def test_enrol_creates_rows_and_notifies_linked_parent_once(client, db_session):
    w = await skills_world(db_session)
    kid0, kid1 = w["a"]["students"]
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id, title="Leadership")
    rows = await enrol(client, batch["id"], kid0, kid1)
    assert {r["school_student_id"] for r in rows} == {str(kid0.id), str(kid1.id)}
    assert all(r["status"] == "enrolled" and r["frozen"] is False and r["attendance"] == {"present": 0, "marked": 0} for r in rows)
    notes = await _notifications(db_session, w["a"]["parent"])  # linked to kid0 only
    assert len(notes) == 1 and "Leadership" in notes[0].title and kid0.full_name in notes[0].title
    assert notes[0].action_url == f"/school/parent/children/{kid0.id}"
    detail = (await client.get(f"{BATCHES}/{batch['id']}")).json()
    assert detail["enrolled_count"] == 2 and [e["student_name"] for e in detail["enrollments"]] == sorted([kid0.full_name, kid1.full_name])
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_enrollment_create", AuditLog.entity_id == batch["id"]))).one()
    assert audit.metadata_json == {"count": 2} and kid0.full_name not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_enrol_student_from_other_school_is_422_and_writes_nothing(client, db_session):
    w = await skills_world(db_session)
    kid0 = w["a"]["students"][0]
    other = w["b"]["students"][0]
    # A counselor whose portfolio holds both schools: the B student is in the portfolio but not at the batch's school.
    both = await mk_staff(db_session, w["a"]["school"], w["a"]["admin"], role="career_counselor")
    db_session.add(SchoolStaffAssignment(user_id=both.id, school_id=w["b"]["school"].id, role="career_counselor", assigned_by_user_id=w["a"]["admin"].id))
    await db_session.commit()
    await login(client, both.email)
    batch = await create_batch(client, w["a"]["school"].id)
    response = await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(kid0.id), str(other.id)]})
    assert response.status_code == 422 and "different school" in response.json()["detail"]
    assert await _enrolment_count(db_session, batch["id"]) == 0
    assert await _notifications(db_session, w["a"]["parent"]) == []


@pytest.mark.asyncio
async def test_enrol_student_outside_portfolio_is_403(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    response = await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(w["b"]["students"][0].id)]})
    assert response.status_code == 403
    assert await _enrolment_count(db_session, batch["id"]) == 0


@pytest.mark.asyncio
async def test_unknown_student_is_404_and_unknown_batch_is_404(client, db_session):
    w =await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    assert (await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(uuid.uuid4())]})).status_code == 404
    assert (await client.post(f"{BATCHES}/{uuid.uuid4()}/enrollments", json={"school_student_ids": [str(w["a"]["students"][0].id)]})).status_code == 404


@pytest.mark.asyncio
async def test_duplicate_enrolment_is_409(client, db_session):
    w = await skills_world(db_session)
    kid0 = w["a"]["students"][0]
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    await enrol(client, batch["id"], kid0)
    response = await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(kid0.id)]})
    assert response.status_code == 409 and "already enrolled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_closed_batch_rejects_enrol_409(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    await client.patch(f"{BATCHES}/{batch['id']}", json={"status": "closed"})
    response = await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(w["a"]["students"][0].id)]})
    assert response.status_code == 409 and "closed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cap_is_409(client, db_session, monkeypatch):
    monkeypatch.setattr(school_skills, "MAX_ENROLMENTS_PER_BATCH", 1)
    w = await skills_world(db_session)
    kid0, kid1 = w["a"]["students"]
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    response = await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(kid0.id), str(kid1.id)]})
    assert response.status_code == 409 and "at most 1" in response.json()["detail"]
    await enrol(client, batch["id"], kid0)
    assert (await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(kid1.id)]})).status_code == 409


ALLOWED = {("enrolled", "completed"), ("enrolled", "certified"), ("enrolled", "withdrawn"), ("completed", "certified"), ("completed", "enrolled"), ("withdrawn", "enrolled")}
STATUSES = ["enrolled", "completed", "certified", "withdrawn"]


async def _set_status(db, enrolment_id, status):
    row = await db.get(SchoolSkillEnrollment, enrolment_id)
    row.status = status
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("old,new", [(o, n) for o in STATUSES for n in STATUSES if o != n])
async def test_transitions_follow_the_table(client, db_session, old, new):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    [row] = await enrol(client, batch["id"], w["a"]["students"][1])
    await _set_status(db_session, row["id"], old)
    response = await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": new})
    assert response.status_code == (200 if (old, new) in ALLOWED else 409), response.text
    if (old, new) in ALLOWED:
        assert response.json()["status"] == new


@pytest.mark.asyncio
async def test_same_status_is_noop_without_notification(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    [row] = await enrol(client, batch["id"], w["a"]["students"][0])
    before = len(await _notifications(db_session, w["a"]["parent"]))
    response = await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "enrolled"})
    assert response.status_code == 200 and response.json()["status"] == "enrolled"
    assert len(await _notifications(db_session, w["a"]["parent"])) == before


@pytest.mark.asyncio
async def test_completion_and_certification_notify_and_stamp_dates(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id, module_type="digital_skills", title="Coding")
    [row] = await enrol(client, batch["id"], w["a"]["students"][0])
    completed = (await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "completed"})).json()
    assert completed["completed_at"] and completed["certified_at"] is None
    certified = (await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "certified"})).json()
    assert certified["certified_at"] and certified["completed_at"] == completed["completed_at"]
    titles = [n.title for n in await _notifications(db_session, w["a"]["parent"])]
    assert len(titles) == 3 and "completed" in titles[1].lower() and "certified" in titles[2].lower()
    assert (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_enrollment_status_change", AuditLog.entity_id == row["id"]))).all()


@pytest.mark.asyncio
async def test_status_change_allowed_on_closed_batch(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    [row] = await enrol(client, batch["id"], w["a"]["students"][0])
    await client.patch(f"{BATCHES}/{batch['id']}", json={"status": "closed"})
    assert (await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "certified"})).status_code == 200


@pytest.mark.asyncio
async def test_frozen_enrolment_rejects_status_change_409_and_shows_frozen(client, db_session):
    w = await skills_world(db_session)
    kid0 = w["a"]["students"][0]
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    [row] = await enrol(client, batch["id"], kid0)
    await move_student_directly(db_session, kid0, w["b"]["school"])
    response = await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "completed"})
    assert response.status_code == 409 and "moved to another school" in response.json()["detail"]
    detail = (await client.get(f"{BATCHES}/{batch['id']}")).json()
    assert detail["enrollments"][0]["frozen"] is True


@pytest.mark.asyncio
async def test_enrolment_outside_portfolio_is_404(client, db_session):
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    [row] = await enrol(client, batch["id"], w["a"]["students"][0])
    await login(client, w["counselor_b"].email)
    assert (await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "completed"})).status_code == 404


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_the_write(client, db_session, monkeypatch):
    async def boom(*_args, **_kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(school_skills, "_notify_student_parents", boom)
    w = await skills_world(db_session)
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    [row] = await enrol(client, batch["id"], w["a"]["students"][0])
    assert (await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "certified"})).status_code == 200
    assert (await db_session.get(SchoolSkillEnrollment, row["id"], populate_existing=True)).status == "certified"
