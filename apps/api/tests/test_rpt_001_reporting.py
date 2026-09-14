"""RPT-001 -- Domestic/Employer reporting.

Neither the existing `GET /admin/reports/summary` (Super Admin's own cross-division
console, users/leads/revenue only) nor the portal dispatcher's per-role "reports" section
actually covered this feature's named scope ("enrolment funnel, course performance,
student progress, employer job activity, placement outcomes"). Confirmed directly:
`PORTAL_NAV["it/admin"]` and `PORTAL_NAV["it/placement"]` both list "Reports", but no
handler existed for either role at all -- the exact same 404 bug class `CNS-001`/
`UNI-001` found and fixed for their own roles this session, just never caught here.

Added two real, data-derived report handlers in `services/portal.py`:
- IT Admin (+ Super Admin, who can do everything IT Admin can): enrolment funnel
  (Enquiry -> Enrollment -> Certificate), per-course enrollment/progress figures from
  real `Enrollment.progress_percent` data.
- Placement Team: employer job activity and placement outcomes from real Job/
  JobApplication/JobOffer rows.

Both deliberately exclude roles outside `RPT-001-AC03`'s named RBAC scope
("IT Admin, Placement Team") -- `overseas_admin`'s own "Reports" link is left 404ing
(that's `RPT-002`'s unscheduled scope, not invented here), and `hr_team` (which shares
every other section in the same outer role block as Placement Team) does not get this
handler either, confirmed directly rather than assumed.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    Batch,
    Certificate,
    Company,
    Enrollment,
    Enquiry,
    Job,
    JobApplication,
    JobOffer,
    Program,
    User,
)


async def _create_user(db_session, *, role: str, division: str, **overrides) -> User:
    defaults = dict(
        email=f"rpt001-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role.title()}",
        role=role,
        division=division,
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, email: str, division: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_it_admin_reports_renders_a_real_funnel_instead_of_404ing(db_session, client):
    # RAID.md I-25: `title`/`name` were plain hardcoded strings here (only `slug` was
    # uuid-suffixed) -- the same "uuid-suffix every human-readable identifying field, not
    # just the machine key" gap already documented once for `AGT-002`'s own fixtures
    # (RAID.md I-09). Every run of this file left a real, permanently-visible "RPT-001
    # Test Program / Batch A" pair in the shared dev DB, since `start_date`/`end_date`
    # here also predate "now" by the time a long session gets here -- surfaced directly
    # by a user screenshot of the student's own slot picker showing many identical cards.
    unique = uuid.uuid4().hex[:6]
    admin = await _create_user(db_session, role="it_admin", division="it")
    program = Program(slug=f"rpt001-prog-{unique}", category="Test", title=f"RPT-001 Test Program {unique}", summary="", duration="3 months", eligibility="", fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name="Test Trainer")
    db_session.add(program)
    await db_session.flush()
    batch = Batch(program_id=program.id, name=f"Batch A {unique}", schedule="Mon-Fri", capacity=20, status="active", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
    db_session.add(batch)
    await db_session.flush()
    student = await _create_user(db_session, role="it_student", division="it")
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"RPT001-{uuid.uuid4().hex[:8]}", status="active", progress_percent=40)
    db_session.add(enrollment)
    db_session.add(Enquiry(division="it", name="Test Lead", email=f"lead-{uuid.uuid4().hex[:8]}@example.local", subject="Interest", message="Test enquiry message.", status="new"))
    await db_session.commit()

    await _login(client, admin.email, "it")
    response = await client.get("/api/v1/portal/it/admin/reports")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "IT Reports"
    metrics = {m["label"]: m["value"] for m in body["metrics"]}
    assert metrics["Enrolments"] >= 1
    course_row = next(row for row in body["rows"] if row["course"] == f"RPT-001 Test Program {unique}")
    assert course_row["enrollments"] == 1
    assert course_row["avg_progress"] == 40


@pytest.mark.asyncio
async def test_it_admin_reports_shows_an_honest_zero_not_a_fabrication_when_a_course_has_no_enrollments(db_session, client):
    unique = uuid.uuid4().hex[:6]
    admin = await _create_user(db_session, role="it_admin", division="it")
    program = Program(slug=f"rpt001-empty-{unique}", category="Test", title=f"RPT-001 Empty Program {unique}", summary="", duration="3 months", eligibility="", fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name="Test Trainer")
    db_session.add(program)
    await db_session.commit()

    await _login(client, admin.email, "it")
    response = await client.get("/api/v1/portal/it/admin/reports")
    assert response.status_code == 200
    course_row = next(row for row in response.json()["rows"] if row["course"] == f"RPT-001 Empty Program {unique}")
    assert course_row["enrollments"] == 0
    assert course_row["avg_progress"] == 0


@pytest.mark.asyncio
async def test_super_admin_can_also_view_it_reports(db_session, client):
    admin = await _create_user(db_session, role="super_admin", division="global")
    await _login(client, admin.email, "global")
    response = await client.get("/api/v1/portal/it/admin/reports")
    assert response.status_code == 200
    assert response.json()["title"] == "IT Reports"


@pytest.mark.asyncio
async def test_overseas_admin_reports_now_renders_instead_of_404ing(db_session, client):
    # This 404 was RPT-001's own deliberate scope boundary at the time (RPT-002 was
    # unscheduled) -- superseded 2026-09-05 when RPT-002 was built (tester feedback
    # 2026-09-04, RAID.md I-14). See test_rpt_002_overseas_reporting.py for full coverage
    # of this role's own report; kept here only to confirm the old 404 boundary is gone.
    admin = await _create_user(db_session, role="overseas_admin", division="overseas")
    await _login(client, admin.email, "overseas")
    response = await client.get("/api/v1/portal/overseas/admin/reports")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_placement_team_reports_renders_real_job_activity_instead_of_404ing(db_session, client):
    placement = await _create_user(db_session, role="placement_team", division="it")
    company = Company(name=f"RPT-001 Test Co {uuid.uuid4().hex[:6]}", website=None, partner_type="recruiter")
    db_session.add(company)
    await db_session.flush()
    job = Job(company_id=company.id, title="Backend Engineer", location="Remote", description="", skills=[], status="open")
    db_session.add(job)
    await db_session.flush()
    student = await _create_user(db_session, role="it_student", division="it")
    application = JobApplication(job_id=job.id, student_id=student.id, status="applied")
    db_session.add(application)
    await db_session.flush()
    db_session.add(JobOffer(application_id=application.id, status="offered"))
    await db_session.commit()

    await _login(client, placement.email, "it")
    response = await client.get("/api/v1/portal/it/placement/reports")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Placement Reports"
    metrics = {m["label"]: m["value"] for m in body["metrics"]}
    assert metrics["Job requirements"] >= 1
    assert metrics["Offers made"] >= 1
    company_row = next(row for row in body["rows"] if row["company"] == company.name)
    assert company_row["open_requirements"] == 1


@pytest.mark.asyncio
async def test_hr_team_cannot_reach_the_placement_reports_handler(db_session, client):
    hr = await _create_user(db_session, role="hr_team", division="it")
    await _login(client, hr.email, "it")
    response = await client.get("/api/v1/portal/it/hr/reports")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_non_admin_role_cannot_view_it_reports(db_session, client):
    student = await _create_user(db_session, role="it_student", division="it")
    await _login(client, student.email, "it")
    response = await client.get("/api/v1/portal/it/admin/reports")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reports_requires_authentication(client):
    response = await client.get("/api/v1/portal/it/admin/reports")
    assert response.status_code == 401
