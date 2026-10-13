"""mgmt-017 -- GET /management/training: the §12 training KPIs and the trainer table (spec TR1-TR16).

The stack DB is shared and never emptied. The period figures are read over a random month of a year no other test writes in (19xx), so
they equal the fixture exactly; the "now" figures (courses, active batches, trainers, placement-ready) are checked as deltas."""

import random
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.models import (
    Assessment,
    AssessmentAttempt,
    Attendance,
    Batch,
    Candidate,
    Certificate,
    Company,
    CourseFeedback,
    Enrollment,
    Job,
    JobApplication,
    JobOffer,
    PlacementProfile,
    Program,
    RecCandidateSource,
)
from app.services import candidates as candidate_svc
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_user

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/training"
KPIS = ["total_courses", "active_batches", "students", "trainers", "attendance_pct", "completion_pct", "dropouts", "assessments",
        "certifications", "placement_ready", "placements"]  # fmt: skip
TRAINER_FIGURES = ["students_trained", "attendance_pct", "completion_pct", "feedback_avg", "assessment_pass_pct", "batch_performance", "placements"]
NOW_KPIS = ["total_courses", "active_batches", "trainers", "placement_ready"]


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def as_role(client, db, role: str):
    client.cookies.clear()
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def read(client, year: int) -> dict:
    response = await client.get(URL, params={"from": f"{year}-06-01", "to": f"{year}-06-30"})
    assert response.status_code == 200, response.text
    return response.json()


def kpis(body: dict) -> dict:
    return {k["key"]: k["value"] for k in body["kpis"]}


def row(body: dict, user) -> dict:
    return next(r for r in body["trainers"] if r["id"] == str(user.id))


# --- builders ----------------------------------------------------------------------------------------------------------------------


async def program(db) -> Program:
    p = Program(slug=f"mgmt017-{tag()}", category="Software", title=f"Course {tag()}", summary="", duration="3 months", eligibility="",
                fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name="")  # fmt: skip
    db.add(p)
    await db.commit()
    return p


async def batch(db, prog, trainer, start: date, end: date, *, status: str = "completed") -> Batch:
    b = Batch(program_id=prog.id, trainer_id=trainer.id if trainer else None, name=f"B-{tag()}", start_date=start, end_date=end,
              schedule="Mon-Fri", status=status)  # fmt: skip
    db.add(b)
    await db.commit()
    return b


async def enrol(db, student, b, *, status: str = "active", progress: int = 0) -> None:
    db.add(Enrollment(student_id=student.id, batch_id=b.id, enrollment_code=f"E-{tag()}", status=status, progress_percent=progress))
    await db.commit()


async def mark(db, student, b, day: date, status: str) -> None:
    db.add(Attendance(student_id=student.id, batch_id=b.id, session_date=day, status=status))
    await db.commit()


async def assessment(db, b, at: datetime, *, pass_percent: int = 50, status: str = "scheduled") -> Assessment:
    a = Assessment(batch_id=b.id, title=f"A-{tag()}", scheduled_at=at, pass_percent=pass_percent, status=status)
    db.add(a)
    await db.commit()
    return a


async def attempt(db, a, student, no: int, percentage, *, status: str = "graded") -> None:
    db.add(AssessmentAttempt(assessment_id=a.id, student_id=student.id, attempt_no=no, status=status, percentage=percentage))
    await db.commit()


async def joined(db, student, on: date) -> None:
    """The student's job offer, joined on `on` (rec-023)."""
    creator = await make_user(db, "placement_team", "global")
    company = Company(name=f"Mgmt017 Co {tag()}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=f"Dev {tag()}", location="Pune", description="", skills=[], status="sourcing")
    db.add(job)
    await db.flush()
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    candidate = Candidate(candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=creator.id,
                          name=f"Cand {tag()}", email=f"{tag()}@example.com", preferred_locations=[])  # fmt: skip
    db.add(candidate)
    await db.flush()
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, student_id=student.id, status="joined")
    db.add(application)
    await db.flush()
    db.add(JobOffer(application_id=application.id, offered_on=on, status="accepted", joining_status="joined", actual_joining_date=on))
    await db.commit()


# --- access (TR16) -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_the_operational_tier_reads_it(client, db_session, role):
    await as_role(client, db_session, role)
    body = await read(client, 1950)
    assert [k["key"] for k in body["kpis"]] == KPIS
    assert [f["key"] for f in body["trainer_figures"]] == TRAINER_FIGURES
    assert all(k["label"] and k["definition"] for k in body["kpis"] + body["trainer_figures"])
    assert body["from"] == "1950-06-01" and body["to"] == "1950-06-30" and body["as_of"]


@pytest.mark.parametrize(("role", "detail"), [("accountant", "Operational access required"), ("trainer", "Management access required"),
                                              ("it_admin", "Management access required")])  # fmt: skip
async def test_everyone_else_is_refused(client, db_session, role, detail):
    await as_role(client, db_session, role)
    response = await client.get(URL)
    assert (response.status_code, response.json()["detail"]) == (403, detail)


async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


# --- period (TR1) ------------------------------------------------------------------------------------------------------------------


async def test_the_default_is_this_ist_month(client, db_session):
    await as_role(client, db_session, "partner")
    body = (await client.get(URL)).json()
    today = datetime.now(IST).date()
    assert body["from"] == today.replace(day=1).isoformat() and body["from"] <= body["to"]


@pytest.mark.parametrize("params", [{"from": "2024-06-30", "to": "2024-06-01"}, {"from": "2023-01-01", "to": "2024-06-30"}])
async def test_a_bad_period_is_422(client, db_session, params):
    await as_role(client, db_session, "partner")
    assert (await client.get(URL, params=params)).status_code == 422


# --- the figures (TR2-TR15) --------------------------------------------------------------------------------------------------------


async def test_the_kpis_and_each_trainers_figures(client, db_session):
    db = db_session
    year = random.randint(1901, 1999)
    d = lambda m, day: date(year, m, day)  # noqa: E731
    at = lambda m, day: datetime(year, m, day, 10, 0, tzinfo=IST)  # noqa: E731
    await as_role(client, db, "partner")
    before = kpis(await read(client, year))

    a, b, c = await make_user(db, "trainer", "it"), await make_user(db, "trainer", "it"), await make_user(db, "trainer", "it")
    b.active = False
    await db.commit()
    prog = await program(db)
    # TR2: b1/b2 overlap June; b3 ran before it; b4 is cancelled; b5 is B's.
    b1 = await batch(db, prog, a, d(5, 15), d(7, 15), status="active")
    b2 = await batch(db, prog, a, d(6, 10), d(6, 20))
    b3 = await batch(db, prog, a, d(1, 1), d(3, 31))
    b4 = await batch(db, prog, a, d(6, 1), d(6, 30), status="cancelled")
    b5 = await batch(db, prog, b, d(6, 1), d(6, 30))
    s1, s2, s3, s4, s5, s6, s7, s8 = [await make_user(db, "it_student", "it") for _ in range(8)]
    # TR3: only taken seats count; s1 sits in two of A's batches and is one student.
    await enrol(db, s1, b1, progress=100)
    await enrol(db, s2, b1, progress=50)
    await enrol(db, s3, b1, status="pending_consent", progress=100)
    await enrol(db, s4, b1, status="rejected")
    await enrol(db, s5, b1, status="withdrawn")  # TR10 dropout
    await enrol(db, s1, b2, progress=80)
    await enrol(db, s6, b3, progress=100)
    await enrol(db, s7, b5, progress=20)
    await enrol(db, s8, b5, status="dropped")  # TR10 dropout
    await enrol(db, s2, b4, progress=100)  # cancelled batch: nothing
    # TR8: attended = present/late/excused over marked rows dated in the period.
    await mark(db, s1, b1, d(6, 3), "present")
    await mark(db, s2, b1, d(6, 3), "absent")
    await mark(db, s1, b1, d(6, 4), "late")
    await mark(db, s2, b1, d(6, 4), "excused")
    await mark(db, s1, b1, d(5, 20), "absent")  # before the period
    # TR15 feedback: A's period batches only.
    for student, bt, rating in ((s1, b1, 5), (s2, b1, 4), (s1, b2, 3), (s6, b3, 1)):
        db.add(CourseFeedback(student_id=student.id, batch_id=bt.id, rating=rating))
    await db.commit()
    # TR11 / TR15 assessments: best graded attempt against the pass mark; drafts and later ones are out.
    as1 = await assessment(db, b1, at(6, 5), pass_percent=50)
    await attempt(db, as1, s1, 1, 40)
    await attempt(db, as1, s1, 2, 70)
    await attempt(db, as1, s2, 1, 30)
    as2 = await assessment(db, b2, at(6, 15), pass_percent=60)
    await attempt(db, as2, s1, 1, 60)
    await attempt(db, as2, s2, 1, None, status="in_progress")
    draft = await assessment(db, b1, at(6, 6), status="draft")
    await attempt(db, draft, s2, 1, 10)
    later = await assessment(db, b1, at(7, 2))
    await attempt(db, later, s2, 1, 10)
    # TR12
    db.add(Certificate(student_id=s1.id, program_id=prog.id, certificate_no=f"C-{tag()}", verification_code=f"V-{tag()}", issued_on=d(6, 20)))
    db.add(Certificate(student_id=s6.id, program_id=prog.id, certificate_no=f"C-{tag()}", verification_code=f"V-{tag()}", issued_on=d(7, 1)))
    # TR13: available and not withdrawn.
    db.add(PlacementProfile(student_id=s1.id, available=True, withdrawn=False, readiness_status="ready"))
    db.add(PlacementProfile(student_id=s2.id, available=True, withdrawn=True))
    db.add(PlacementProfile(student_id=s7.id, available=False, withdrawn=False))
    await db.commit()
    # TR14: s6 (A's earlier batch) joined in June; s2 after it; s3 never took a seat.
    await joined(db, s6, d(6, 10))
    await joined(db, s2, d(7, 5))
    await joined(db, s3, d(6, 12))

    body = await read(client, year)
    after = kpis(body)
    assert {k: after[k] - before[k] for k in NOW_KPIS} == {"total_courses": 1, "active_batches": 1, "trainers": 2, "placement_ready": 1}
    assert {k: after[k] for k in KPIS if k not in NOW_KPIS} == {
        "students": 3, "attendance_pct": 75.0, "completion_pct": 25.0, "dropouts": 2, "assessments": 2, "certifications": 1, "placements": 1,
    }  # fmt: skip

    assert row(body, a) == {
        "id": str(a.id), "full_name": a.full_name, "active": True, "batches": 2, "students_trained": 2, "attendance_pct": 75.0,
        "completion_pct": 33.3, "feedback_avg": 4.0, "feedback_count": 3, "assessment_pass_pct": 66.7, "batch_performance": 76.7,
        "placements": 1,
    }  # fmt: skip
    assert row(body, b) == {
        "id": str(b.id), "full_name": b.full_name, "active": False, "batches": 1, "students_trained": 1, "attendance_pct": None,
        "completion_pct": 0.0, "feedback_avg": None, "feedback_count": 0, "assessment_pass_pct": None, "batch_performance": 20.0,
        "placements": 0,
    }  # fmt: skip
    assert row(body, c) == {
        "id": str(c.id), "full_name": c.full_name, "active": True, "batches": 0, "students_trained": 0, "attendance_pct": None,
        "completion_pct": None, "feedback_avg": None, "feedback_count": 0, "assessment_pass_pct": None, "batch_performance": None,
        "placements": 0,
    }  # fmt: skip


async def test_an_empty_period_says_so_not_zero_shares(client, db_session):
    await as_role(client, db_session, "super_admin")
    figures = kpis(await read(client, 1900))
    assert figures["attendance_pct"] is None and figures["completion_pct"] is None
    assert figures["students"] == 0 and figures["placements"] == 0


async def test_trainers_equal_the_snapshot(client, db_session):
    await as_role(client, db_session, "partner")
    snapshot = {k["key"]: k["value"] for k in (await client.get("/api/v1/management/snapshot")).json()["kpis"]}
    assert kpis(await read(client, 1950))["trainers"] == snapshot["trainers"]
