"""mgmt-016 -- GET /management/funnel: the §11 student funnel and its breakdowns (spec SF1-SF16).

The stack DB is shared and never emptied. Every figure is read over June of a random year no other test writes in (17xx-18xx), so the
stage counts equal the fixture exactly. Breakdown rows are checked for the fixture's own fresh values; every row set must add up (AC2)."""

import random
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.models import (
    AgentStudent,
    ApplicationStatusHistory,
    Appointment,
    Batch,
    Candidate,
    Certificate,
    Company,
    Enquiry,
    Enrollment,
    Job,
    JobApplication,
    JobOffer,
    LeadCall,
    LeadStageHistory,
    OverseasApplication,
    OverseasCourse,
    Program,
    RecCandidateSource,
    School,
    SchoolStudent,
    VisaCase,
)
from app.services import candidates as candidate_svc
from app.services.bdm_appointments import IST
from tests.agn001_helpers import mk_active_org
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import login, make_user
from tests.bdm025_helpers import org as bdm_organization

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/funnel"
LEAD = ["leads", "telecalling", "counseling", "registration"]
IT = ["training", "it_application", "certification", "placement", "joining"]
ABROAD = ["abroad_education", "abroad_application", "offer", "visa", "enrollment"]
DIMENSIONS = ["country", "course", "agent", "school", "counselor", "source", "bdm", "intake", "branch"]
APPLIES = {
    "country": ABROAD, "course": ["training", "certification", *ABROAD], "agent": ABROAD, "school": ABROAD,
    "counselor": [*LEAD, *ABROAD], "source": LEAD, "bdm": LEAD, "intake": ABROAD, "branch": [],
}  # fmt: skip


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def as_role(client, db, role: str):
    client.cookies.clear()
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def read(client, year: int, by: str | None = None) -> dict:
    params = {"from": f"{year}-06-01", "to": f"{year}-06-30"} | ({"by": by} if by else {})
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def values(body: dict) -> dict:
    return {s["key"]: s["value"] for s in body["stages"]}


def by_value(body: dict) -> dict:
    return {r["value"]: r["counts"] for r in body["breakdown"]["rows"]}


async def add(db, row):
    db.add(row)
    await db.commit()
    return row


# --- access (SF16) -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_the_operational_tier_reads_it(client, db_session, role):
    await as_role(client, db_session, role)
    body = await read(client, 1750)
    assert [s["key"] for s in body["stages"]] == LEAD + IT + ABROAD
    assert [p["key"] for p in body["paths"]] == ["lead", "it", "abroad"]
    assert [s["path"] for s in body["stages"]] == ["lead"] * 4 + ["it"] * 5 + ["abroad"] * 5
    assert all(s["label"] and s["definition"] for s in body["stages"])
    assert {d["key"]: d["stages"] for d in body["dimensions"]} == APPLIES
    assert [d["key"] for d in body["dimensions"]] == DIMENSIONS
    assert {d["key"] for d in body["dimensions"] if not d["tracked"]} == {"branch"}
    assert body["from"] == "1750-06-01" and body["to"] == "1750-06-30" and body["as_of"] and body["breakdown"] is None


@pytest.mark.parametrize(("role", "detail"), [("accountant", "Operational access required"), ("counselor", "Management access required"),
                                              ("overseas_admin", "Management access required")])  # fmt: skip
async def test_everyone_else_is_refused(client, db_session, role, detail):
    await as_role(client, db_session, role)
    response = await client.get(URL)
    assert (response.status_code, response.json()["detail"]) == (403, detail)


async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


# --- period and dimension (SF1, SF16) ----------------------------------------------------------------------------------------------


async def test_the_default_is_this_ist_month(client, db_session):
    await as_role(client, db_session, "partner")
    body = (await client.get(URL)).json()
    today = datetime.now(IST).date()
    assert body["from"] == today.replace(day=1).isoformat() and body["from"] <= body["to"]


@pytest.mark.parametrize("params", [{"from": "2024-06-30", "to": "2024-06-01"}, {"from": "2023-01-01", "to": "2024-06-30"}, {"by": "city"}])
async def test_a_bad_query_is_422(client, db_session, params):
    await as_role(client, db_session, "partner")
    assert (await client.get(URL, params=params)).status_code == 422


async def test_branch_is_not_tracked(client, db_session):
    await as_role(client, db_session, "super_admin")
    breakdown = (await read(client, 1750, "branch"))["breakdown"]
    assert breakdown == {"by": "branch", "label": "Branch", "tracked": False, "stages": [], "rows": [], "unknown": {}}


# --- the fixture -------------------------------------------------------------------------------------------------------------------


async def job_offer(db, student, applied: datetime, offered: date, *, joined: date | None = None) -> None:
    """A job application created at `applied` (student_id may be None: an outside candidate) and its offer."""
    creator = await make_user(db, "placement_team", "global")
    company = await add(db, Company(name=f"Mgmt016 Co {tag()}"))
    job = await add(db, Job(company_id=company.id, title=f"Dev {tag()}", location="Pune", description="", skills=[], status="sourcing"))
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    candidate = await add(db, Candidate(candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=creator.id,
                                        name=f"Cand {tag()}", email=f"{tag()}@example.com", preferred_locations=[]))  # fmt: skip
    application = await add(db, JobApplication(job_id=job.id, candidate_id=candidate.id, student_id=student.id if student else None,
                                               status="selected", created_at=applied))  # fmt: skip
    await add(db, JobOffer(application_id=application.id, offered_on=offered, status="accepted", joining_status="joined" if joined else "pending",
                           actual_joining_date=joined))  # fmt: skip


async def build(db, year: int) -> dict:
    """The fixture of `test_each_stage_counts_its_definition`, commented with what each row contributes to June."""
    d = lambda m, day: date(year, m, day)  # noqa: E731
    at = lambda m, day: datetime(year, m, day, 12, 0, tzinfo=IST)  # noqa: E731
    counselor = await make_user(db, "counselor", "overseas", name=f"Funnel Counselor {tag()}")
    bdm = await make_user(db, "bdm", "global", name=f"Funnel BDM {tag()}")
    telecaller = await make_user(db, "telecaller", "overseas")
    bdm_org = await bdm_organization(db, bdm)  # a lead's BDM attribution names both (ck_enquiries_bdm_attribution)

    async def lead(created, source, owner, *, bdm_user=None) -> Enquiry:
        return await add(db, Enquiry(division="overseas", name=f"Lead {tag()}", email=f"{tag()}@example.local", phone="9876543210", subject="Study",
                                     message="", source=source, status="follow_up", owner_id=owner.id, bdm_user_id=bdm_user.id if bdm_user else None,
                                     bdm_organization_id=bdm_org.id if bdm_user else None, created_at=created))  # fmt: skip

    async def call(row, when):
        await add(db, LeadCall(lead_id=row.id, caller_user_id=telecaller.id, occurred_at=when, duration_seconds=60, call_type="outgoing",
                               outcome="interested"))  # fmt: skip

    async def appointment(row, when, status="completed"):
        await add(db, Appointment(division="overseas", lead_id=row.id, staff_id=counselor.id, scheduled_at=when, appointment_type="Career Counseling",
                                  mode="Online", status=status))  # fmt: skip

    async def convert(row, when, *, still=True):
        db.add(LeadStageHistory(lead_id=row.id, from_stage="application_enrollment", to_stage="converted", event="converted", created_at=when))
        if still:
            row.status = "converted"
        await db.commit()

    # Lead journey (SF3-SF6). L1 does everything in June; L2's appointment is not held and its conversion was undone; L3 arrived in May
    # and was first converted in May; L4 arrives in July.
    l1 = await lead(at(6, 5), "instagram", counselor, bdm_user=bdm)
    await call(l1, at(6, 6))
    await appointment(l1, at(6, 7))
    await convert(l1, at(6, 8))
    l2 = await lead(at(6, 10), "website", telecaller)
    await call(l2, at(6, 11))
    await call(l2, at(6, 12))
    await appointment(l2, at(6, 13), "scheduled")
    await convert(l2, at(6, 14), still=False)
    l3 = await lead(at(5, 20), "instagram", counselor)
    await convert(l3, at(5, 25))
    await call(l3, at(6, 2))
    await appointment(l3, at(6, 3))
    await convert(l3, at(6, 4))
    l4 = await lead(at(7, 1), "instagram", counselor)
    await call(l4, at(7, 1))

    # IT path (SF7-SF11).
    prog = await add(db, Program(slug=f"mgmt016-{tag()}", category="Software", title=f"Funnel Course {tag()}", summary="", duration="3 months",
                                 eligibility="", fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name=""))  # fmt: skip
    running = await add(db, Batch(program_id=prog.id, name=f"B-{tag()}", start_date=d(6, 1), end_date=d(8, 30), schedule="Mon-Fri", status="active"))
    cancelled = await add(db, Batch(program_id=prog.id, name=f"B-{tag()}", start_date=d(6, 1), end_date=d(8, 30), schedule="Mon-Fri", status="cancelled"))
    s1, s2, s3, s4, s5, s6 = [await make_user(db, "it_student", "it") for _ in range(6)]
    for student, b, on, status in (
        (s1, running, d(6, 3), "active"),
        (s2, running, d(6, 4), "withdrawn"),
        (s3, running, d(6, 5), "pending_consent"),
        (s4, running, d(6, 6), "rejected"),
        (s5, cancelled, d(6, 7), "active"),
        (s6, running, d(5, 30), "active"),
    ):
        db.add(Enrollment(student_id=student.id, batch_id=b.id, enrollment_code=f"E-{tag()}", enrolled_on=on, status=status))  # fmt: skip
    for student, on in ((s1, d(6, 20)), (s6, d(7, 1))):
        db.add(Certificate(student_id=student.id, program_id=prog.id, certificate_no=f"C-{tag()}", verification_code=f"V-{tag()}", issued_on=on))
    await db.commit()
    await job_offer(db, s1, at(6, 10), d(6, 15), joined=d(6, 25))
    await job_offer(db, s2, at(5, 1), d(6, 2))
    await job_offer(db, None, at(6, 12), d(6, 13), joined=d(6, 14))  # an outside candidate is not a student

    # Abroad path (SF12-SF15).
    uni, other_uni = await mk_university(db), await mk_university(db)
    course = await add(db, OverseasCourse(university_id=uni.id, title=f"MSc {tag()}", level="masters", category="cs", duration="1y", tuition_fee="x", intake="Sep"))
    org = await mk_active_org(db, name=f"Funnel Agency {tag()}")
    record = await add(db, AgentStudent(agent_id=org["master"].id, full_name="Agency Student"))
    school = await add(db, School(name=f"Funnel School {tag()}", created_by_user_id=bdm.id))
    pupil = await add(db, SchoolStudent(school_id=school.id, student_code=tag().upper(), full_name="Pupil", created_by_user_id=bdm.id))
    overseas = await make_user(db, "overseas_student", "overseas")
    a1 = await add(db, OverseasApplication(university_id=uni.id, student_id=overseas.id, course_id=course.id, counselor_id=counselor.id, intake="Sep 2027",
                                           status="enrolled", enrollment_confirmed_at=at(6, 20), submitted_on=d(6, 5), created_at=at(6, 2)))  # fmt: skip
    a2 = await add(db, OverseasApplication(university_id=other_uni.id, agent_student_id=record.id, agent_id=org["master"].id, intake="",
                                           status="accepted", submitted_on=d(5, 30), created_at=at(6, 3)))  # fmt: skip
    # ccrm-027 (DEC-SCOPE-259, E4): the funnel counts confirmed enrolments only, so both enrolled rows carry their confirmation.
    a3 = await add(db, OverseasApplication(university_id=uni.id, school_student_id=pupil.id, intake="Jan 2028", status="enrolled", submitted_on=d(6, 8),
                                           enrollment_confirmed_at=at(6, 29), created_at=at(4, 1)))  # fmt: skip
    for app, to_status, when in (
        (a1, "offer_received", at(6, 10)),
        (a1, "enrolled", at(6, 20)),
        (a2, "offer", at(5, 31)),
        (a2, "accepted", at(6, 4)),
        (a3, "offer", at(6, 9)),
        (a3, "enrolled", at(6, 29)),
    ):
        db.add(ApplicationStatusHistory(application_id=app.id, to_status=to_status, created_at=when))  # fmt: skip
    db.add(VisaCase(application_id=a1.id, checklist=[], decision="approved", decided_at=at(6, 15)))
    db.add(VisaCase(application_id=a2.id, checklist=[], decision="refused", decided_at=at(6, 6)))
    db.add(VisaCase(application_id=a3.id, checklist=[], decision="approved", decided_at=at(7, 2)))
    await db.commit()
    return {"counselor": counselor, "bdm": bdm, "program": prog, "course": course, "uni": uni, "other_uni": other_uni, "org": org["org"], "school": school}


# --- the stages (SF3-SF15, AC1) ----------------------------------------------------------------------------------------------------


async def test_each_stage_counts_its_definition(client, db_session):
    year = random.randint(1700, 1899)
    await as_role(client, db_session, "partner")
    await build(db_session, year)
    assert values(await read(client, year)) == {
        "leads": 2, "telecalling": 3, "counseling": 2, "registration": 1,
        "training": 2, "it_application": 1, "certification": 1, "placement": 2, "joining": 1,
        "abroad_education": 2, "abroad_application": 2, "offer": 2, "visa": 1, "enrollment": 2,
    }  # fmt: skip


async def test_an_empty_period_counts_zero(client, db_session):
    await as_role(client, db_session, "super_admin")
    assert set(values(await read(client, 1699)).values()) == {0}


# --- the breakdowns (SF16, AC2) ----------------------------------------------------------------------------------------------------


async def test_each_breakdown_adds_up_and_credits_its_values(client, db_session):
    year = random.randint(1700, 1899)
    await as_role(client, db_session, "partner")
    made = await build(db_session, year)
    totals = values(await read(client, year))
    seen = {}
    for dim in DIMENSIONS:
        body = await read(client, year, dim)
        breakdown = body["breakdown"]
        assert breakdown["by"] == dim and breakdown["stages"] == APPLIES[dim]
        for stage in breakdown["stages"]:  # AC2: the rows plus Unknown equal the stage total
            assert sum(r["counts"][stage] for r in breakdown["rows"]) + breakdown["unknown"][stage] == totals[stage], (dim, stage)
        assert all(set(r["counts"]) == set(APPLIES[dim]) for r in breakdown["rows"])
        assert all(r["label"] for r in breakdown["rows"])
        seen[dim] = by_value(body)
        seen[f"{dim}:unknown"] = breakdown["unknown"]

    uni_country, other_country = str(made["uni"].country_id), str(made["other_uni"].country_id)
    assert seen["country"][uni_country] == {"abroad_education": 1, "abroad_application": 2, "offer": 2, "visa": 1, "enrollment": 2}
    assert seen["country"][other_country] == {"abroad_education": 1, "abroad_application": 0, "offer": 0, "visa": 0, "enrollment": 0}
    assert seen["course"][str(made["program"].id)] == {"training": 2, "certification": 1, **dict.fromkeys(ABROAD, 0)}
    assert seen["course"][str(made["course"].id)] == {"training": 0, "certification": 0, "abroad_education": 1, "abroad_application": 1, "offer": 1,
                                                      "visa": 1, "enrollment": 1}  # fmt: skip
    assert seen["agent"][str(made["org"].id)] == {"abroad_education": 1, "abroad_application": 0, "offer": 0, "visa": 0, "enrollment": 0}
    assert seen["school"][str(made["school"].id)] == {"abroad_education": 0, "abroad_application": 1, "offer": 1, "visa": 0, "enrollment": 1}
    # The lead's owner when a counselor (L1, L3; L2 is a telecaller's), and the application's counselor (A1).
    assert seen["counselor"][str(made["counselor"].id)] == {"leads": 1, "telecalling": 2, "counseling": 2, "registration": 1, "abroad_education": 1,
                                                            "abroad_application": 1, "offer": 1, "visa": 1, "enrollment": 1}  # fmt: skip
    assert seen["source"]["instagram"] == {"leads": 1, "telecalling": 2, "counseling": 2, "registration": 1}
    assert seen["source"]["website"] == {"leads": 1, "telecalling": 1, "counseling": 0, "registration": 0}
    assert seen["bdm"][str(made["bdm"].id)] == {"leads": 1, "telecalling": 1, "counseling": 1, "registration": 1}
    assert seen["intake"]["Sep 2027"] == {"abroad_education": 1, "abroad_application": 1, "offer": 1, "visa": 1, "enrollment": 1}
    assert seen["intake:unknown"]["abroad_education"] == 1  # A2's blank intake


async def test_rows_are_labelled(client, db_session):
    year = random.randint(1700, 1899)
    await as_role(client, db_session, "partner")
    made = await build(db_session, year)
    made["counselor"].active = False
    await db_session.commit()
    labels = lambda body: {r["value"]: r["label"] for r in body["breakdown"]["rows"]}  # noqa: E731
    assert labels(await read(client, year, "source"))["instagram"] == "Instagram"
    assert labels(await read(client, year, "counselor"))[str(made["counselor"].id)] == f"{made['counselor'].full_name} (inactive)"
    assert labels(await read(client, year, "agent"))[str(made["org"].id)] == made["org"].name
    assert labels(await read(client, year, "course"))[str(made["course"].id)] == f"{made['course'].title} — {made['uni'].name}"
    assert labels(await read(client, year, "course"))[str(made["program"].id)] == made["program"].title
    assert labels(await read(client, year, "intake"))["Sep 2027"] == "Sep 2027"


async def test_rows_with_the_same_label_are_told_apart(client, db_session):
    """QA16-02: two programs share a title (titles are not unique); each row keeps its own, distinguishable label."""
    year = random.randint(1700, 1899)
    await as_role(client, db_session, "partner")
    title = f"Twin Course {tag()}"
    progs = [await add(db_session, Program(slug=f"mgmt016-{tag()}", category="Software", title=title, summary="", duration="3 months", eligibility="",
                                           fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name="")) for _ in range(2)]  # fmt: skip
    for prog in progs:
        student = await make_user(db_session, "it_student", "it")
        db_session.add(Certificate(student_id=student.id, program_id=prog.id, certificate_no=f"C-{tag()}", verification_code=f"V-{tag()}",
                                   issued_on=date(year, 6, 10)))  # fmt: skip
    await db_session.commit()
    labels = {r["value"]: r["label"] for r in (await read(client, year, "course"))["breakdown"]["rows"]}
    assert labels == {str(p.id): f"{title} ({str(p.id)[:8]})" for p in progs}
