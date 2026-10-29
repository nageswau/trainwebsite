"""nehn-017 (DEC-SCOPE-310) -- HR's read-only access to permitted student progress, attendance and documents, and the HR reports.

One fixture: an active-pool IT student (progress 100, 3 of 4 classes attended → 75 %, a paid fee, a Resume and an ID proof), a student
withdrawn from placement (outside the HR population, H1) and an overseas student. Grants are the nehn-005 engine's; a revoked key is a
nehn-007 deny override on the one HR user, so parallel tests keep the role grants."""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.core import rbac
from app.models import Attendance, AuditLog, Payment, PlacementProfile, ProfileDocument, UserPermissionOverride
from tests.bdm001_helpers import login, make_user
from tests.test_nehn_009_reports import _course, _enrol

pytestmark = pytest.mark.asyncio
HR = "/api/v1/hr/students"
REPORTS = "/api/v1/reports"
HR_REPORTS = {"hr-progress", "hr-completions", "hr-attendance"}
HR_KEYS = {f"{resource}.{action}" for resource in ("student_progress", "attendance", "student_documents") for action in ("view", "download")}
MONEY = ("fee", "payment", "discount", "amount", "revenue", "paid")


async def _world(db):
    program, batch, trainer = await _course(db)
    seat, student = await _enrol(db, batch, progress=100, name=f"Hira N017 {uuid.uuid4().hex[:6]}")
    _, withdrawn = await _enrol(db, batch, progress=60, name=f"Wren N017 {uuid.uuid4().hex[:6]}")
    db.add(PlacementProfile(student_id=withdrawn.id, withdrawn=True))
    for day, status in enumerate(("present", "present", "late", "absent")):
        db.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date(2020, 1, 6) + datetime.timedelta(days=day), status=status))
    db.add(Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=seat.id, amount=1000, status="paid"))
    resume = ProfileDocument(user_id=student.id, document_type=" Resume ", file_url="/local-files/uploads/n017-resume.pdf", original_filename="cv.pdf", content_type="application/pdf", file_size=10)
    id_proof = ProfileDocument(user_id=student.id, document_type="ID proof", file_url="/local-files/uploads/n017-id.pdf", original_filename="id.pdf", content_type="application/pdf", file_size=10)
    other = ProfileDocument(user_id=withdrawn.id, document_type="resume", file_url="/local-files/uploads/n017-other.pdf", original_filename="w.pdf", content_type="application/pdf", file_size=10)
    db.add_all([resume, id_proof, other])
    overseas = await make_user(db, "overseas_student", "overseas")
    await db.commit()
    return {"batch": batch, "student": student, "withdrawn": withdrawn, "overseas": overseas, "resume": resume, "id_proof": id_proof, "other": other}


async def _hr(client, db):
    user = await make_user(db, "hr_team", "it")
    await login(client, user)
    return user


async def _deny(db, user, key):
    resource, action = rbac.parse_key(key)
    db.add(UserPermissionOverride(user_id=user.id, resource=resource, action=action, effect="deny", reason="nehn-017 test"))
    await db.commit()


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


# --- catalogue and grants (H3) ------------------------------------------------------------------------------------------------------


def test_the_three_resources_are_in_the_catalogue_and_only_hr_holds_them_by_default():
    for resource in ("student_progress", "attendance", "student_documents"):
        assert rbac.CATALOGUE[resource]["actions"] == ("view", "download")
    assert HR_KEYS <= set(rbac.DEFAULT_GRANTS["hr_team"])
    assert not {key for role, keys in rbac.DEFAULT_GRANTS.items() if role != "hr_team" for key in keys} & HR_KEYS


# --- the student pages (AC1, AC2, AC4, AC5) --------------------------------------------------------------------------------------------


async def test_hr_sees_progress_completion_and_attendance_and_nothing_financial(client, db_session):
    w = await _world(db_session)
    await _hr(client, db_session)
    response = await client.get(f"{HR}/{w['student'].id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"]["full_name"] == w["student"].full_name
    [seat] = body["seats"]
    assert seat["progress"] == 100 and seat["completed"] is True and seat["certificate"] == "Not issued"
    assert seat["attendance"] == {"marked": 4, "present": 2, "absent": 1, "late": 1, "excused": 0, "attendance_pct": 75.0}
    assert body["can"] == {"attendance": True, "documents": True, "download": True}
    assert not {k for k in _keys(body) if any(word in k.lower() for word in MONEY)}
    assert "file_url" not in _keys(body)


async def test_the_list_holds_the_population_only(client, db_session):
    w = await _world(db_session)
    await _hr(client, db_session)
    found = (await client.get(HR, params={"q": w["student"].full_name})).json()
    assert [(i["id"], i["courses"], i["completed"]) for i in found["items"]] == [(str(w["student"].id), 1, 1)]
    assert found["total"] == 1 and found["page"] == 1
    assert (await client.get(HR, params={"q": w["withdrawn"].full_name})).json()["items"] == []
    assert (await client.get(HR, params={"q": "x" * 101})).status_code == 422


async def test_a_student_outside_the_population_is_not_found(client, db_session):
    w = await _world(db_session)
    await _hr(client, db_session)
    for outsider in (w["withdrawn"], w["overseas"]):
        assert (await client.get(f"{HR}/{outsider.id}")).status_code == 404
    assert (await client.get(f"{HR}/{uuid.uuid4()}")).status_code == 404


async def test_only_the_allowed_document_types_are_listed_and_opened(client, db_session):
    w = await _world(db_session)
    hr = await _hr(client, db_session)
    body = (await client.get(f"{HR}/{w['student'].id}")).json()
    assert [(d["id"], d["document_type"]) for d in body["documents"]] == [(str(w["resume"].id), " Resume ")]
    base = f"{HR}/{w['student'].id}/documents"
    opened = await client.get(f"{base}/{w['resume'].id}/download")
    assert opened.status_code == 200, opened.text
    assert opened.json()["url"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == hr.id, AuditLog.action == "hr.student_document_download"))
    assert audit is not None and audit.entity_id == str(w["resume"].id)
    assert (await client.get(f"{base}/{w['id_proof'].id}/download")).status_code == 403
    assert (await client.get(f"{base}/{w['other'].id}/download")).status_code == 404  # another student's document
    assert (await client.get(f"{HR}/{w['withdrawn'].id}/documents/{w['other'].id}/download")).status_code == 404


async def test_revoking_attendance_hides_it_and_refuses_the_report(client, db_session):
    w = await _world(db_session)
    hr = await _hr(client, db_session)
    await _deny(db_session, hr, "attendance.view")
    body = (await client.get(f"{HR}/{w['student'].id}")).json()
    assert "attendance" not in body["seats"][0] and body["can"]["attendance"] is False
    assert (await client.get(f"{REPORTS}/hr-attendance")).status_code == 403
    assert "hr-attendance" not in {i["id"] for i in (await client.get(REPORTS)).json()["items"]}


async def test_revoking_documents_hides_the_list_and_refuses_the_download(client, db_session):
    w = await _world(db_session)
    hr = await _hr(client, db_session)
    await _deny(db_session, hr, "student_documents.view")
    await _deny(db_session, hr, "student_documents.download")
    body = (await client.get(f"{HR}/{w['student'].id}")).json()
    assert "documents" not in body and body["can"]["documents"] is False and body["can"]["download"] is False
    assert (await client.get(f"{HR}/{w['student'].id}/documents/{w['resume'].id}/download")).status_code == 403


async def test_without_progress_view_the_pages_are_refused(client, db_session):
    w = await _world(db_session)
    hr = await _hr(client, db_session)
    await _deny(db_session, hr, "student_progress.view")
    assert (await client.get(HR)).status_code == 403
    assert (await client.get(f"{HR}/{w['student'].id}")).status_code == 403


async def test_another_role_given_the_grant_has_no_hr_scope(client, db_session):
    w = await _world(db_session)
    recruiter = await make_user(db_session, "placement_team", "it")
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="student_progress", action="view", effect="allow", reason="nehn-017 test"))
    await db_session.commit()
    await login(client, recruiter)
    assert (await client.get(HR)).status_code == 403
    assert (await client.get(f"{HR}/{w['student'].id}")).status_code == 403


async def test_super_admin_reads_the_hr_pages(client, db_session):
    w = await _world(db_session)
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.get(f"{HR}/{w['student'].id}")).status_code == 200


# --- the HR reports (AC3) ----------------------------------------------------------------------------------------------------------------


async def test_hr_library_lists_the_hr_reports_only(client, db_session):
    await _hr(client, db_session)
    ids = {i["id"] for i in (await client.get(REPORTS)).json()["items"]}
    assert ids == HR_REPORTS


async def test_hr_reports_hold_the_population_only(client, db_session):
    w = await _world(db_session)
    await _hr(client, db_session)
    for report in HR_REPORTS:
        names = {row["student"] for row in (await client.get(f"{REPORTS}/{report}", params={"student": "N017", "batch_id": str(w["batch"].id)})).json()["items"]}
        assert w["withdrawn"].full_name not in names
        assert w["student"].full_name in names, report


async def test_hr_attendance_download_has_no_financial_column(client, db_session):
    w = await _world(db_session)
    await _hr(client, db_session)
    response = await client.get(f"{REPORTS}/hr-attendance.csv", params={"batch_id": str(w["batch"].id)})
    assert response.status_code == 200, response.text
    header = response.text.lstrip("﻿").splitlines()[0].lower()
    assert "attendance %" in header and not any(word in header for word in MONEY)
    assert w["student"].full_name in response.text and w["withdrawn"].full_name not in response.text


async def test_a_trainer_does_not_see_the_hr_reports(client, db_session):
    _, _, trainer = await _course(db_session)
    await login(client, trainer)
    ids = {i["id"] for i in (await client.get(REPORTS)).json()["items"]}
    assert not ids & HR_REPORTS


# --- the portal (backlog: the HR reports exclusion removed) and a negative --------------------------------------------------------------


async def test_hr_opens_the_placement_reports_section(client, db_session):
    await _hr(client, db_session)
    response = await client.get("/api/v1/portal/it/hr/reports")
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Placement Reports"


async def test_hr_is_refused_admin_payments(client, db_session):
    await _hr(client, db_session)
    assert (await client.get("/api/v1/admin/payments")).status_code == 403
