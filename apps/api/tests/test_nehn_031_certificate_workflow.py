"""nehn-031 -- the coordinator certificate workflow (DEC-ROLE-003; DEC-SCOPE-297; spec
docs/superpowers/specs/2026-10-27-nehn-031-coordinator-certificate-workflow-design.md, RBAC_MATRIX §2.208): issuance is the coordinator's
(AC1), the override is its own grant and needs a reason (AC2), thresholds are configurable (AC3), bulk issue (AC4), the trainer's
recommendation in the queue (AC5) and duplicate issue (AC6)."""

import datetime
import uuid

import pytest
from sqlalchemy import delete, select

from app.core import rbac
from app.models import Attendance, AuditLog, Batch, Certificate, CertificateRequest, Enrollment, Program, RolePermission, User
from tests.bdm001_helpers import make_user
from tests.upc001_helpers import as_role, login

BASE = "/api/v1/workflows/it/certificates"


async def _enrollment(db, *, progress: int = 100, present: int = 4, batch: Batch | None = None) -> Enrollment:
    """A fresh student, in a fresh programme/batch unless `batch` is given. With the defaults the learner is eligible: progress 100,
    attendance 100%, nothing else due. Batches start in the past, so they never crowd the seeded ones off the admin's batch list."""
    tag = uuid.uuid4().hex[:8]
    if batch is None:
        trainer = await make_user(db, "trainer", "it")
        program = Program(
            slug=f"n031-{tag}", title=f"N031 Programme {tag}", category="Testing", summary="-", duration="1 month", eligibility="-", fees=1000,
            certification="-", placement_assistance="-", trainer_name="-",
        )
        db.add(program)
        await db.flush()
        batch = Batch(
            program_id=program.id, trainer_id=trainer.id, name=f"N031-{tag}", start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 2, 1), schedule="-", capacity=40, enrollment_open=True, status="active",
        )
        db.add(batch)
        await db.flush()
    student = await make_user(db, "it_student", "it", name=f"Learner {tag}")
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N031-{tag}", status="active", progress_percent=progress)
    db.add(enrollment)
    for day in range(present):
        db.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date(2026, 1, 1) + datetime.timedelta(days=day), status="present"))
    await db.commit()
    await db.refresh(enrollment)
    return enrollment



# --- the matrix -------------------------------------------------------------------------------------------------------------------


def test_catalogue_and_default_grants():
    assert rbac.CATALOGUE["certificates"]["actions"] == ("view", "issue", "override", "configure", "manage")  # nehn-032 adds manage
    assert set(rbac.DEFAULT_GRANTS["coordinator"]) == {"certificates.view", "certificates.issue", "certificates.override"}
    assert {key for key in rbac.DEFAULT_GRANTS["it_admin"] if key.startswith("certificates.")} == {"certificates.configure"}
    assert not any(key.startswith("certificates.") for key in rbac.DEFAULT_GRANTS.get("trainer", ()))  # nehn-009 gave trainers reports only


# --- AC1: only the coordinator issues ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["trainer", "it_admin", "it_student", "counselor"])
async def test_other_roles_cannot_issue(client, db_session, role):
    enrollment = await _enrollment(db_session)
    if role == "trainer":
        batch = await db_session.get(Batch, enrollment.batch_id)
        await login(client, await db_session.get(User, batch.trainer_id))  # even the batch's own trainer
    else:
        await as_role(client, db_session, role, "it")
    assert (await client.post(f"{BASE}/{enrollment.id}/issue", json={})).status_code == 403
    assert (await client.post(f"{BASE}/issue", json={"enrollment_ids": [str(enrollment.id)]})).status_code == 403
    assert (await client.get(f"{BASE}/queue")).status_code == 403
    assert await db_session.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id)) is None


@pytest.mark.asyncio
async def test_coordinator_issues_an_eligible_learner(client, db_session):
    enrollment = await _enrollment(db_session)
    coordinator = await as_role(client, db_session, "coordinator", "it")
    response = await client.post(f"{BASE}/{enrollment.id}/issue", json={})
    assert response.status_code == 201, response.text
    certificate = await db_session.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id))
    assert certificate.approved_by_id == coordinator.id and certificate.criteria_snapshot["eligible"] is True
    assert certificate.criteria_snapshot["rules"] == {"min_progress_percent": 100, "min_attendance_percent": 75}


@pytest.mark.asyncio
async def test_revoking_the_issue_grant_closes_issuance(client, db_session):
    enrollment = await _enrollment(db_session)
    await as_role(client, db_session, "coordinator", "it")
    await db_session.execute(delete(RolePermission).where(RolePermission.role == "coordinator", RolePermission.action == "issue"))
    await db_session.commit()
    try:
        assert (await client.post(f"{BASE}/{enrollment.id}/issue", json={})).status_code == 403
    finally:
        db_session.add(RolePermission(role="coordinator", resource="certificates", action="issue"))
        await db_session.commit()


# --- AC2: the override ------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_eligible_needs_override_and_a_reason(client, db_session):
    enrollment = await _enrollment(db_session, progress=40)
    coordinator = await as_role(client, db_session, "coordinator", "it")
    url = f"{BASE}/{enrollment.id}/issue"
    assert (await client.post(url, json={})).status_code == 409
    assert (await client.post(url, json={"override": True})).status_code == 422
    assert (await client.post(url, json={"override": True, "override_reason": "   "})).status_code == 422
    assert (await client.post(url, json={"override": True, "override_reason": "x" * 1001})).status_code == 422
    response = await client.post(url, json={"override": True, "override_reason": "Equivalent industry certification."})
    assert response.status_code == 201
    certificate = await db_session.get(Certificate, uuid.UUID(response.json()["id"]))
    assert certificate.criteria_snapshot["override_reason"] == "Equivalent industry certification."
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_type == "certificate", AuditLog.entity_id == str(certificate.id)))
    assert audit.user_id == coordinator.id and audit.metadata_json["override"] is True
    assert audit.metadata_json["override_reason"] == "Equivalent industry certification."


@pytest.mark.asyncio
async def test_override_without_the_override_grant_is_403(client, db_session):
    enrollment = await _enrollment(db_session, progress=40)
    await as_role(client, db_session, "coordinator", "it")
    await db_session.execute(delete(RolePermission).where(RolePermission.role == "coordinator", RolePermission.action == "override"))
    await db_session.commit()
    try:
        body = {"override": True, "override_reason": "Manager said so."}
        assert (await client.post(f"{BASE}/{enrollment.id}/issue", json=body)).status_code == 403
        assert (await client.post(f"{BASE}/issue", json={"enrollment_ids": [str(enrollment.id)], **body})).status_code == 403
        assert (await client.get(f"{BASE}/queue")).json()["can_override"] is False
    finally:
        db_session.add(RolePermission(role="coordinator", resource="certificates", action="override"))
        await db_session.commit()
    assert await db_session.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id)) is None


# --- AC3: thresholds --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_threshold_change_applies_to_the_next_evaluation(client, db_session):
    enrollment = await _enrollment(db_session, progress=80)
    await as_role(client, db_session, "coordinator", "it")
    assert (await client.get(f"{BASE}/eligibility/{enrollment.id}")).json()["eligible"] is False
    assert (await client.put(f"{BASE}/rules", json={"min_progress_percent": 80, "min_attendance_percent": 75})).status_code == 403

    admin = await as_role(client, db_session, "it_admin", "it")
    assert (await client.put(f"{BASE}/rules", json={"min_progress_percent": 101, "min_attendance_percent": 75})).status_code == 422
    assert (await client.put(f"{BASE}/rules", json={"min_progress_percent": 80, "min_attendance_percent": 75, "x": 1})).status_code == 422
    try:
        response = await client.put(f"{BASE}/rules", json={"min_progress_percent": 80, "min_attendance_percent": 75})
        assert response.status_code == 200 and response.json()["min_progress_percent"] == 80
        audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "certificate_rules.update", AuditLog.user_id == admin.id))
        assert audit.metadata_json["after"] == {"min_progress_percent": 80, "min_attendance_percent": 75}

        eligibility = (await client.get(f"{BASE}/eligibility/{enrollment.id}")).json()
        assert eligibility["eligible"] is True and eligibility["rules"]["min_progress_percent"] == 80
        assert (await client.get(f"{BASE}/rules")).json()["min_progress_percent"] == 80
    finally:  # the row is shared by every test
        assert (await client.put(f"{BASE}/rules", json={"min_progress_percent": 100, "min_attendance_percent": 75})).status_code == 200


# --- AC4: bulk issue --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_issue_of_thirty_creates_thirty_unique_certificates(client, db_session):
    first = await _enrollment(db_session)  # one class of 30, as at the end of a course
    batch = await db_session.get(Batch, first.batch_id)
    enrollments = [first] + [await _enrollment(db_session, batch=batch) for _ in range(29)]
    await as_role(client, db_session, "coordinator", "it")
    response = await client.post(f"{BASE}/issue", json={"enrollment_ids": [str(e.id) for e in enrollments]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["failed"] == [] and len(body["issued"]) == 30
    certificates = (await db_session.scalars(select(Certificate).where(Certificate.enrollment_id.in_([e.id for e in enrollments])))).all()
    assert len(certificates) == 30 and len({c.certificate_no for c in certificates}) == 30 and all(c.file_url for c in certificates)


@pytest.mark.asyncio
async def test_bulk_reports_each_failure_and_issues_the_rest(client, db_session):
    good, unready = await _enrollment(db_session), await _enrollment(db_session, progress=10)
    await as_role(client, db_session, "coordinator", "it")
    missing = uuid.uuid4()
    body = (await client.post(f"{BASE}/issue", json={"enrollment_ids": [str(good.id), str(unready.id), str(missing)]})).json()
    assert [item["enrollment_id"] for item in body["issued"]] == [str(good.id)]
    assert {item["enrollment_id"]: item["status_code"] for item in body["failed"]} == {str(unready.id): 409, str(missing): 404}


@pytest.mark.asyncio
async def test_bulk_validation(client, db_session):
    await as_role(client, db_session, "coordinator", "it")
    assert (await client.post(f"{BASE}/issue", json={"enrollment_ids": []})).status_code == 422
    assert (await client.post(f"{BASE}/issue", json={"enrollment_ids": [str(uuid.uuid4()) for _ in range(51)]})).status_code == 422


# --- AC5: recommendation ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trainer_recommendation_is_visible_in_the_queue(client, db_session):
    enrollment = await _enrollment(db_session, progress=50)  # not eligible, so only the recommendation brings it into the queue
    batch = await db_session.get(Batch, enrollment.batch_id)
    trainer = await db_session.get(User, batch.trainer_id)
    await login(client, trainer)
    url = f"{BASE}/{enrollment.id}/recommend"
    assert (await client.post(url, json={"status": "not_ready"})).status_code == 422  # a not-ready flag needs a comment
    assert (await client.post(url, json={"status": "maybe"})).status_code == 422
    assert (await client.post(url, json={"status": "not_ready", "comment": "Two labs missing."})).status_code == 200
    response = await client.post(url, json={"status": "recommended", "comment": "Strong final project."})
    assert response.status_code == 200 and response.json()["status"] == "recommended"
    assert len((await db_session.scalars(select(CertificateRequest).where(CertificateRequest.enrollment_id == enrollment.id))).all()) == 1

    await as_role(client, db_session, "coordinator", "it")
    queue = (await client.get(f"{BASE}/queue")).json()
    assert queue["can_override"] is True
    item = next(i for i in queue["items"] if i["enrollment_id"] == str(enrollment.id))
    assert item["eligible"] is False and item["program"].startswith("N031 Programme")
    assert item["recommendation"] == {"status": "recommended", "comment": "Strong final project.", "by": trainer.full_name, "at": item["recommendation"]["at"]}

    await client.post(f"{BASE}/{enrollment.id}/issue", json={"override": True, "override_reason": "Trainer recommended."})
    request = await db_session.scalar(select(CertificateRequest.status).where(CertificateRequest.enrollment_id == enrollment.id))
    assert request == "issued"
    assert str(enrollment.id) not in {i["enrollment_id"] for i in (await client.get(f"{BASE}/queue")).json()["items"]}
    await login(client, trainer)
    assert (await client.post(url, json={"status": "recommended"})).status_code == 409  # already issued


@pytest.mark.asyncio
async def test_eligible_learner_is_in_the_queue_without_a_recommendation(client, db_session):
    enrollment = await _enrollment(db_session)
    await as_role(client, db_session, "coordinator", "it")
    item = next(i for i in (await client.get(f"{BASE}/queue")).json()["items"] if i["enrollment_id"] == str(enrollment.id))
    assert item["eligible"] is True and item["recommendation"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["other_trainer", "it_admin", "coordinator", "it_student"])
async def test_only_the_batch_trainer_recommends(client, db_session, role):
    enrollment = await _enrollment(db_session)
    await as_role(client, db_session, "trainer" if role == "other_trainer" else role, "it")
    assert (await client.post(f"{BASE}/{enrollment.id}/recommend", json={"status": "recommended"})).status_code == 403


# --- AC6: duplicates --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_issue_is_409(client, db_session):
    enrollment = await _enrollment(db_session)
    await as_role(client, db_session, "coordinator", "it")
    assert (await client.get(f"{BASE}/eligibility/{enrollment.id}")).json()["certificate_issued"] is False
    assert (await client.post(f"{BASE}/{enrollment.id}/issue", json={})).status_code == 201
    assert (await client.get(f"{BASE}/eligibility/{enrollment.id}")).json()["certificate_issued"] is True  # QA31-04
    assert (await client.post(f"{BASE}/{enrollment.id}/issue", json={})).status_code == 409
    failed = (await client.post(f"{BASE}/issue", json={"enrollment_ids": [str(enrollment.id)]})).json()["failed"]
    assert failed == [{"enrollment_id": str(enrollment.id), "status_code": 409, "detail": "A certificate has already been issued for this enrolment"}]


@pytest.mark.asyncio
async def test_routes_require_authentication(client):
    assert (await client.get(f"{BASE}/queue")).status_code == 401
    assert (await client.post(f"{BASE}/issue", json={"enrollment_ids": [str(uuid.uuid4())]})).status_code == 401
    assert (await client.post(f"{BASE}/{uuid.uuid4()}/recommend", json={"status": "recommended"})).status_code == 401
    assert (await client.put(f"{BASE}/rules", json={"min_progress_percent": 1, "min_attendance_percent": 1})).status_code == 401
