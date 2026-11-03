"""itc-029 (DEC-SCOPE-358) -- the IT student 360 for the IT counselor, HR and the IT Admin (spec docs/superpowers/specs/2026-11-03-itc-029-
it-student-360-design.md). One role-scoped read, GET /it/students/{id}/360, with a per-role section allow-list (S3: HR's omits fee,
profile, lead, risk and notifications); every section is read live from its own record (AC1); out of scope is 404 (AC2); a fixed number
of queries whatever the number of enrolments (AC3)."""

import datetime
import uuid

import pytest
from sqlalchemy import event

from app.core import rbac
from app.models import (
    Assignment,
    Attendance,
    Batch,
    Enquiry,
    ItStudentCounselor,
    ItStudentNote,
    ItStudentProfile,
    Notification,
    PlacementProfile,
    StudentResume,
    StudentRiskFlag,
    Submission,
    UserPermissionOverride,
)
from tests.bdm001_helpers import make_user
from tests.tel018_helpers import enrol, make_student
from tests.tel026_helpers import headers
from tests.test_itc_013_fee_account import enrolled

pytestmark = pytest.mark.asyncio
ALL = {"contact", "profile", "lead", "enrollments", "fee", "risk", "feedback", "resumes", "hr_review", "notes", "notifications"}
HR_HIDDEN = {"fee", "profile", "lead", "risk", "notifications"}


def url(student_id, tail: str = "") -> str:
    return f"/api/v1/it/students/{student_id}/360{tail}"


async def _world(db, *, fee: float | None = 45000):
    """A student (billed enrolment, in the HR pool) linked to a counselor; the IT Admin, HR and an unrelated student."""
    student, seat = await enrolled(db, fee)
    counselor = await make_user(db, "counselor", "it")
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return {
        "student": student, "seat": seat, "counselor": counselor, "hr": await make_user(db, "hr_team", "it"),
        "admin": await make_user(db, "it_admin", "it"), "other": await make_student(db),
    }  # fmt: skip


async def _get(client, user, student, tail: str = ""):
    return await client.get(url(student.id, tail), headers=headers(user))


# --- scope (AC2) -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["counselor", "hr", "admin"])
async def test_each_reader_opens_a_student_in_scope(client, db_session, role):
    w = await _world(db_session)
    response = await _get(client, w[role], w["student"])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"  # AC1: never a cached copy
    body = response.json()
    assert body["student"]["id"] == str(w["student"].id) and body["viewer"] == role
    assert set(body["sections"]) == (ALL - HR_HIDDEN if role == "hr" else ALL)
    assert set(body["sections"]) <= set(body)


async def test_out_of_scope_is_404_and_other_roles_403(client, db_session):
    w = await _world(db_session)
    other_counselor = await make_user(db_session, "counselor", "it")
    assert (await _get(client, other_counselor, w["student"])).status_code == 404  # not their linked student
    assert (await _get(client, w["counselor"], w["other"])).status_code == 404
    assert (await client.get(url(uuid.uuid4()), headers=headers(w["admin"]))).status_code == 404
    assert (await _get(client, w["admin"], w["counselor"])).status_code == 404  # not an IT student
    db_session.add(PlacementProfile(student_id=w["other"].id, withdrawn=True))  # outside the HR pool
    await db_session.commit()
    assert (await _get(client, w["hr"], w["other"])).status_code == 404
    trainer = await make_user(db_session, "trainer", "it")
    (await db_session.get(Batch, w["seat"].batch_id)).trainer_id = trainer.id
    await db_session.commit()
    assert (await _get(client, trainer, w["student"])).status_code == 403  # S1: no trainer 360, even for their own student
    for role, division in (("counselor", "overseas"), ("placement_team", "it"), ("super_admin", "it"), ("overseas_admin", "overseas")):
        assert (await _get(client, await make_user(db_session, role, division), w["student"])).status_code == 403, role
    assert (await _get(client, w["student"], w["student"])).status_code == 403
    assert (await client.get(url(w["student"].id))).status_code == 401


async def test_hr_without_the_progress_grant_is_refused(client, db_session):
    w = await _world(db_session)
    resource, action = rbac.parse_key("student_progress.view")
    db_session.add(UserPermissionOverride(user_id=w["hr"].id, resource=resource, action=action, effect="deny", reason="itc-029 test"))
    await db_session.commit()
    assert (await _get(client, w["hr"], w["student"])).status_code == 403


# --- sections ----------------------------------------------------------------------------------------------------------------------


async def test_the_counselor_sees_every_section_from_its_source(client, db_session):
    w = await _world(db_session)
    student, seat, counselor = w["student"], w["seat"], w["counselor"]
    student.phone = "+919876543210"
    db_session.add(ItStudentProfile(student_user_id=student.id, city="Hyderabad", emergency_contact_name="Ravi", emergency_contact_phone="+919812345678"))
    lead = Enquiry(division="it", name=student.full_name, email=student.email, subject="Python", message="", source="website", status="converted",
                   owner_id=counselor.id, converted_user_id=student.id, converted_at=datetime.datetime.now(datetime.UTC), converted_by_user_id=counselor.id)  # fmt: skip
    db_session.add(lead)
    batch = await db_session.get(Batch, seat.batch_id)
    seat.progress_percent = 40
    for day, status in ((1, "present"), (2, "present"), (3, "absent"), (4, "present")):
        db_session.add(Attendance(student_id=student.id, batch_id=batch.id, session_date=datetime.date(2026, 2, day), status=status))
    task = Assignment(batch_id=batch.id, title="SQL joins", description="-", due_date=datetime.datetime(2026, 2, 5, tzinfo=datetime.UTC))
    db_session.add(task)
    await db_session.flush()
    db_session.add(Submission(assignment_id=task.id, student_id=student.id, score=72, feedback="Good joins; revise GROUP BY.", status="graded",
                              graded_by_id=batch.trainer_id, graded_at=datetime.datetime.now(datetime.UTC)))  # fmt: skip
    db_session.add(StudentRiskFlag(enrollment_id=seat.id, student_id=student.id, batch_id=batch.id, reasons=["attendance"], attendance_percent=60,
                                   raised_at=datetime.datetime.now(datetime.UTC)))  # fmt: skip
    db_session.add(StudentResume(student_user_id=student.id, version=1, storage_key=f"k/{uuid.uuid4().hex}", content_type="application/pdf",
                                 file_name="cv.pdf", size_bytes=1000, visibility="private", uploaded_by_user_id=counselor.id))  # fmt: skip
    db_session.add(ItStudentNote(student_user_id=student.id, author_user_id=counselor.id, body="Wants a data role."))
    db_session.add(Notification(user_id=student.id, title="Payment received", body="Secret body text", read=False, event_type="it.fee.payment_received"))
    await db_session.commit()

    body = (await _get(client, counselor, student)).json()
    assert body["contact"] == {"email": student.email, "phone": "+919876543210", "counselor": {"id": str(counselor.id), "full_name": counselor.full_name}}
    assert body["profile"]["city"] == "Hyderabad" and body["profile"]["emergency_contact_name"] == "Ravi"
    assert body["lead"]["id"] == str(lead.id) and body["lead"]["href"] == f"/it/counselor/leads/{lead.id}"
    [row] = body["enrollments"]
    assert row["enrollment_code"] == seat.enrollment_code and row["trainer"] and row["progress_percent"] == 40
    assert row["attendance_percent"] == 75.0  # itc-021's attended / counted
    assert body["fee"]["balance"] == 45000.0 and body["fee"]["accounts"][0]["enrollment_id"] == str(seat.id)
    assert body["risk"][0]["reasons"] == ["attendance"] and body["risk"][0]["batch"] == batch.name
    assert body["feedback"][0]["title"] == "SQL joins" and body["feedback"][0]["feedback"].startswith("Good joins")
    assert body["resumes"]["items"][0]["version"] == 1
    assert body["notes"]["total"] == 1 and body["notes"]["items"][0]["body"] == "Wants a data role."
    assert body["notifications"][0]["title"] == "Payment received" and "body" not in body["notifications"][0]  # S4
    assert body["hr_review"] == {"task": None}


async def test_hr_sees_only_its_sections_and_hr_resume_versions(client, db_session):
    w = await _world(db_session)
    db_session.add(ItStudentProfile(student_user_id=w["student"].id, emergency_contact_name="Ravi"))
    for version, visibility in ((1, "private"), (2, "hr")):
        db_session.add(StudentResume(student_user_id=w["student"].id, version=version, storage_key=f"k/{uuid.uuid4().hex}", content_type="application/pdf",
                                     file_name="cv.pdf", size_bytes=1000, visibility=visibility, uploaded_by_user_id=w["counselor"].id))  # fmt: skip
    await db_session.commit()
    response = await _get(client, w["hr"], w["student"])
    body = response.json()
    assert not HR_HIDDEN & set(body)  # S3 (Q-28): omitted, not null
    assert "Ravi" not in response.text and "45000" not in response.text  # no emergency contact, nothing financial
    assert [r["version"] for r in body["resumes"]["items"]] == [2]


async def test_hr_without_the_attendance_grant_gets_no_attendance_figure(client, db_session):
    w = await _world(db_session)
    resource, action = rbac.parse_key("attendance.view")
    db_session.add(UserPermissionOverride(user_id=w["hr"].id, resource=resource, action=action, effect="deny", reason="itc-029 test"))
    await db_session.commit()
    [row] = (await _get(client, w["hr"], w["student"])).json()["enrollments"]
    assert "attendance_percent" not in row and "progress_percent" in row


async def test_a_student_with_no_enrolment_yet(client, db_session):
    student = await make_student(db_session)
    admin = await make_user(db_session, "it_admin", "it")
    body = (await _get(client, admin, student)).json()
    assert body["enrollments"] == [] and body["fee"] == {"accounts": [], "balance": None}
    assert body["lead"] is None and body["risk"] == [] and body["feedback"] == [] and body["contact"]["counselor"] is None


# --- live (AC1, the + scenario) ----------------------------------------------------------------------------------------------------


async def test_a_recorded_payment_shows_on_the_counselors_next_read(client, db_session):
    w = await _world(db_session)
    assert (await _get(client, w["counselor"], w["student"])).json()["fee"]["balance"] == 45000.0
    recorded = await client.post(f"/api/v1/it/enrollments/{w['seat'].id}/payments", headers=headers(w["admin"]), json={"amount": 15000, "payment_mode": "cash"})
    assert recorded.status_code == 201, recorded.text
    assert (await _get(client, w["counselor"], w["student"])).json()["fee"]["balance"] == 30000.0


# --- query count (AC3) -------------------------------------------------------------------------------------------------------------


async def _count(client, db, user, student) -> int:
    queries = []
    engine = db.bind.sync_engine
    listener = lambda *_: queries.append(1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        assert (await _get(client, user, student)).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(queries)


async def test_the_query_count_is_fixed_whatever_the_enrolments(client, db_session):
    w = await _world(db_session)
    one = await _count(client, db_session, w["admin"], w["student"])
    for _ in range(2):
        await enrolled(db_session, 1000, student=w["student"])
    await enrol(db_session, w["student"])
    assert await _count(client, db_session, w["admin"], w["student"]) == one
    assert one <= 22


# --- the lead timeline ---------------------------------------------------------------------------------------------------------------


async def test_the_lead_timeline_follows_the_lead_sections_audience(client, db_session):
    w = await _world(db_session)
    lead = Enquiry(division="it", name="L", email=w["student"].email, subject="Python", message="", source="website", status="converted",
                   owner_id=w["counselor"].id, converted_user_id=w["student"].id,
                   converted_at=datetime.datetime.now(datetime.UTC), converted_by_user_id=w["counselor"].id)  # fmt: skip
    db_session.add(lead)
    await db_session.commit()
    page = (await _get(client, w["counselor"], w["student"], "/lead-timeline")).json()
    assert "created" in {item["kind"] for item in page["items"]}  # the tel-015 timeline of the student's lead
    assert (await _get(client, w["admin"], w["student"], "/lead-timeline")).status_code == 200
    assert (await _get(client, w["hr"], w["student"], "/lead-timeline")).status_code == 403
    no_lead = (await _get(client, w["admin"], w["other"], "/lead-timeline")).json()
    assert no_lead == {"items": [], "total": 0, "limit": 20, "offset": 0}
    other_counselor = await make_user(db_session, "counselor", "it")
    assert (await _get(client, other_counselor, w["student"], "/lead-timeline")).status_code == 404


# --- entry points ------------------------------------------------------------------------------------------------------------------


async def test_the_counselor_and_admin_student_tables_open_the_360(client, db_session):
    w = await _world(db_session)
    sid = str(w["student"].id)
    mine = (await client.get("/api/v1/portal/it/counselor/students", headers=headers(w["counselor"]))).json()
    assert {"key": "open", "label": "", "type": "student_360"} in mine["columns"]
    assert next(r for r in mine["rows"] if r["id"] == sid)["open"] == f"/it/counselor/students/{sid}"
    admin = (await client.get(f"/api/v1/portal/it/admin/students?q={w['student'].email}", headers=headers(w["admin"]))).json()
    assert {"key": "open", "label": "", "type": "student_360"} in admin["columns"]
    row = next((r for r in admin["rows"] if r["id"] == sid), None)
    assert row is None or row["open"] == f"/it/admin/students/{sid}"
