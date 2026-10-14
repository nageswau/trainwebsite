"""mgmt-026 -- the plan KPI catalogue (spec PN5/PN6): each count KPI counts a row inside the plan's IST month and not one a moment before.

Each test reads a random far-future month, so rows other tests leave in the shared database never land in it."""

import random
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models import AgentOrg, ApplicationStatusHistory, Batch, BdmMou, BdmMouEvent, CompanyStageHistory, Enrollment, OverseasApplication, UniversityStageHistory
from app.partnership_stages import GROUPS
from app.services import management_metrics as metrics
from app.services.bdm_appointments import IST
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.enh005_helpers import mk_school, mk_student
from tests.test_bdm_023_dashboard import org_of
from tests.test_mgmt_003_snapshot import batch
from tests.test_rec_035_management import _company, _job, _joined


def month() -> tuple[date, date]:
    year = random.randint(2200, 2900)
    return date(year, 6, 1), date(year, 7, 1)


def first_instant(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=IST)


def inside_and_before(start: date) -> tuple[datetime, datetime]:
    """The month's first IST instant and the second before it (the previous month's last IST day)."""
    at = first_instant(start)
    return at, at - timedelta(seconds=1)


async def actual(db, key: str, start: date, end: date) -> int:
    return (await metrics.plan_actuals(db, {key}, start, end))[key]


def test_the_catalogue_has_the_eleven_kpis_with_revenue_in_rupees():
    assert list(metrics.PLAN_KPIS) == [
        "agents", "applications", "enrollments", "school_mous", "school_students", "universities", "it_students", "batches", "companies",
        "placements", "revenue",
    ]  # fmt: skip
    assert {key for key, (_, unit, _) in metrics.PLAN_KPIS.items() if unit == "inr"} == {metrics.REVENUE_KPI}


@pytest.mark.asyncio
async def test_no_keys_is_no_query(db_session):
    start, end = month()
    assert await metrics.plan_actuals(db_session, set(), start, end) == {}
    assert await metrics.plan_actuals(db_session, {metrics.REVENUE_KPI}, start, end) == {}  # revenue is the P&L's, read elsewhere


@pytest.mark.asyncio
async def test_agents_are_active_organisations_created_in_the_month(db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    for at, status in ((inside, "active"), (inside, "suspended"), (before, "active")):
        db_session.add(AgentOrg(name="Plan Agency", prefix=uuid.uuid4().hex[:6].upper(), status=status, created_at=at))
    await db_session.commit()
    assert await actual(db_session, "agents", start, end) == 1


async def _application(db, university, at: datetime) -> OverseasApplication:
    student = await make_user(db, "overseas_student", "overseas")
    app = OverseasApplication(university_id=university.id, student_id=student.id, intake="Fall 2027", status="enquiry", created_at=at)
    db.add(app)
    await db.flush()
    return app


@pytest.mark.asyncio
async def test_applications_created_in_the_month(db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    university = await mk_university(db_session)
    await _application(db_session, university, inside)
    await _application(db_session, university, before)
    await db_session.commit()
    assert await actual(db_session, "applications", start, end) == 1


@pytest.mark.asyncio
async def test_enrollments_are_applications_moved_to_enrolled_in_the_month(db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    university = await mk_university(db_session)
    moved, early = await _application(db_session, university, before), await _application(db_session, university, before)
    for app, from_status, at in ((moved, "visa_approved", inside), (moved, "enrolled", inside), (early, "visa_approved", before)):
        db_session.add(ApplicationStatusHistory(application_id=app.id, from_status=from_status, to_status="enrolled", created_at=at))
    await db_session.commit()
    assert await actual(db_session, "enrollments", start, end) == 1  # the re-save of Enrolled is not a move; the early one is last month


@pytest.mark.asyncio
async def test_school_mous_are_school_mous_moved_to_signed_in_the_month(client, db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    manager = await make_manager(db_session)
    school_bdm, agent_bdm = await make_bdm(db_session, manager, "school"), await make_bdm(db_session, manager, "agent")
    school_org, earlier_org = await org_of(client, school_bdm, org_type="school"), await org_of(client, school_bdm, org_type="school")
    agent_org = await org_of(client, agent_bdm, org_type="agent")
    for org, bdm, at in ((school_org, school_bdm, inside), (earlier_org, school_bdm, before), (agent_org, agent_bdm, inside)):
        mou = BdmMou(organization_id=org["id"], created_by_user_id=bdm.id, status="signed", signed_on=start)
        db_session.add(mou)
        await db_session.flush()
        db_session.add(BdmMouEvent(mou_id=mou.id, actor_user_id=bdm.id, kind="status", from_status="proposal_sent", to_status="signed", changed=[], created_at=at))
    await db_session.commit()
    assert await actual(db_session, "school_mous", start, end) == 1


@pytest.mark.asyncio
async def test_school_students_added_in_the_month(db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    ctx = await mk_school(db_session, students=0)
    for at in (inside, before):
        student = await mk_student(db_session, ctx["school"], ctx["coordinator"])
        student.created_at = at
    await db_session.commit()
    assert await actual(db_session, "school_students", start, end) == 1


@pytest.mark.asyncio
async def test_universities_moved_into_a_partner_stage_in_the_month(db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    actor = await make_user(db_session, "partnership_manager", "global")
    partner = metrics.UNIVERSITY_PARTNER_STAGES[0]
    prospect = next(key for key, group in GROUPS.items() if group != "partner")
    rows = ((prospect, partner, inside), (partner, partner, inside), (prospect, partner, before))
    for from_stage, to_stage, at in rows:
        university = await mk_university(db_session)
        db_session.add(UniversityStageHistory(university_id=university.id, actor_user_id=actor.id, kind="move", from_stage=from_stage, to_stage=to_stage, created_at=at))
    await db_session.commit()
    assert await actual(db_session, "universities", start, end) == 1


@pytest.mark.asyncio
async def test_it_students_are_taken_up_enrolments_created_in_the_month(db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    on = await batch(db_session, "active")
    for at, status in ((inside, "active"), (inside, "pending_consent"), (before, "active")):
        student = await make_user(db_session, "it_student", "it")
        db_session.add(Enrollment(student_id=student.id, batch_id=on.id, enrollment_code=f"MG26-{uuid.uuid4().hex[:10]}", status=status, created_at=at))
    await db_session.commit()
    assert await actual(db_session, "it_students", start, end) == 1


@pytest.mark.asyncio
async def test_batches_starting_in_the_month_except_cancelled(db_session):
    start, end = month()
    for day, status in ((start, "upcoming"), (start, "cancelled"), (start - timedelta(days=1), "upcoming")):
        on = await batch(db_session, status)
        on.start_date, on.end_date = day, day + timedelta(days=60)
    await db_session.commit()
    assert await actual(db_session, "batches", start, end) == 1


@pytest.mark.asyncio
async def test_companies_first_moved_past_interested_in_the_month(db_session):
    start, end = month()
    inside, before = inside_and_before(start)
    past = metrics.PARTNER_COMPANY_STAGES[0]
    for at in (inside, before):
        company = await _company(db_session, None, stage=past)
        db_session.add(CompanyStageHistory(company_id=company.id, from_stage="interested", to_stage=past, event="moved", created_at=at))
    await db_session.commit()
    assert await actual(db_session, "companies", start, end) == 1


@pytest.mark.asyncio
async def test_placements_are_offers_joined_in_the_month(db_session):
    start, end = month()
    creator = await make_user(db_session, "placement_team", "it")
    job = await _job(db_session, await _company(db_session, None))
    await _joined(db_session, job, creator, start)
    await _joined(db_session, job, creator, start - timedelta(days=1))
    await db_session.commit()
    assert await actual(db_session, "placements", start, end) == 1


@pytest.mark.asyncio
async def test_all_count_kpis_are_one_statement(db_session):
    start, end = month()
    keys = set(metrics.PLAN_KPIS) - {metrics.REVENUE_KPI}
    assert set(await metrics.plan_actuals(db_session, keys, start, end)) == keys
