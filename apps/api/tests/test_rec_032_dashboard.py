"""rec-032 -- the recruiter dashboard (DEC-SCOPE-179 DB1-DB10; backlog Appendix B D1-D14; AC1-AC3). The shared test database is never
truncated, so every figure is asserted for a fresh recruiter whose scope holds only this test's rows."""

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import event, func, select

from app.models import (
    Candidate,
    Company,
    CompanyContact,
    Interview,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobOffer,
    ProfileShare,
    ProfileShareItem,
    RecCandidateSource,
    RecruiterCall,
    RecruiterFollowUp,
    RecruiterMeeting,
)
from app.services import candidates as candidate_svc
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import IST, today_ist
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter

URL = "/api/v1/recruiter/dashboard"
TILE_KEYS = (  # the API contract (§12CT), in EVID-018 §1 order
    "new_leads",
    "contacts_pending",
    "hot_companies",
    "meetings_scheduled",
    "active_companies",
    "new_requirements",
    "candidates_sourced",
    "profiles_shared",
    "interviews_scheduled",
    "candidates_selected",
    "candidates_joined",
    "candidates_rejected",
    "follow_ups_due",
    "requirements_expiring",
    "requirements_expired",
)


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _now() -> datetime:
    return datetime.now(UTC)


def _month_start() -> datetime:
    return datetime.combine(today_ist(_now()).replace(day=1), time.min, tzinfo=IST)


async def _company(db, recruiter, **fields) -> Company:
    company = Company(name=f"Acme {_tag()}", assigned_recruiter_user_id=recruiter.id if recruiter else None, **fields)
    db.add(company)
    await db.flush()
    return company


async def _job(db, company, recruiter=None, **fields) -> Job:
    fields.setdefault("status", "sourcing")
    job = Job(company_id=company.id, title=f"Java {_tag()}", location="Pune", description="", skills=[], assigned_recruiter_user_id=recruiter.id if recruiter else None, **fields)
    db.add(job)
    await db.flush()
    return job


async def _application(db, job, creator, **fields) -> JobApplication:
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    candidate = Candidate(
        candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=creator.id, name=f"Rahul {_tag()}", email=f"{_tag()}@example.com", preferred_locations=[]
    )
    db.add(candidate)
    await db.flush()
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, **fields)
    db.add(application)
    await db.flush()
    return application


def _entered(db, application, status, at=None) -> None:
    db.add(JobApplicationStatusHistory(application_id=application.id, from_status="sourced", to_status=status, **({"created_at": at} if at else {})))


async def _read(client, **params):
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _fresh_recruiter(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


# --- AC1: each tile equals its definition ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_fresh_recruiter_sees_every_tile_at_zero(client, db_session):
    await _fresh_recruiter(client, db_session)
    body = await _read(client)
    assert body["tiles"] == dict.fromkeys(TILE_KEYS, 0)
    assert list(body["tiles"]) == list(TILE_KEYS)
    assert body["recruiter"] is None
    today = today_ist(_now())
    assert body["day"] == today.isoformat()
    assert body["period"] == {"from": today.replace(day=1).isoformat(), "to": today.isoformat()}


@pytest.mark.asyncio
async def test_company_side_tiles_follow_their_definitions(client, db_session):
    _, me = await _fresh_recruiter(client, db_session)
    now, db = _now(), db_session
    # D1/D2: new leads (7 days) and New Lead companies never called
    fresh = await _company(db, me)  # new, never called -> D1 + D2
    called = await _company(db, me)  # new, called -> D1 only
    await _company(db, me, created_at=now - timedelta(days=10))  # old New Lead, never called -> D2 only
    await _company(db, me, archived_at=now)  # archived -> nothing
    await _company(db, me, lost_at=now, lost_reason="No budget")  # lost -> nothing
    await _company(db, me, stage="contacted")  # not New Lead -> nothing
    contact = CompanyContact(company_id=called.id, name="Asha HR")
    db.add(contact)
    await db.flush()
    db.add(RecruiterCall(company_id=called.id, contact_id=contact.id, caller_user_id=me.id, occurred_at=now, direction="outgoing", outcome="connected"))
    # D3: hot, open companies
    await _company(db, me, stage="contacted", priority="hot")
    await _company(db, me, stage="requirement_closed", priority="hot")  # closed -> not hot
    await _company(db, me, stage="contacted", priority="warm")
    # D4: scheduled meetings in the next 7 days
    for starts, status in ((now + timedelta(hours=2), "scheduled"), (now + timedelta(days=8), "scheduled"), (now - timedelta(hours=1), "scheduled")):
        db.add(RecruiterMeeting(meeting_code=f"T{_tag()}", company_id=fresh.id, meeting_type="company_meeting", starts_at=starts, mode="Online", status=status, created_by_user_id=me.id))
    # D5: companies with a live requirement
    live = await _company(db, me, stage="requirement_received")
    await _job(db, live, status="on_hold")
    await _job(db, live, status="sourcing")
    parked = await _company(db, me, stage="requirement_received")
    await _job(db, parked, status="closed")
    # D13: open follow-ups due today (IST) or overdue
    tonight = datetime.combine(today_ist(now) + timedelta(days=1), time.min, tzinfo=IST)
    for due, status in ((tonight - timedelta(minutes=1), "open"), (now - timedelta(days=3), "open"), (tonight, "open"), (now - timedelta(days=1), "cancelled")):
        extra = {"cancelled_at": now, "cancel_reason": "x"} if status == "cancelled" else {}
        db.add(RecruiterFollowUp(company_id=fresh.id, reason="jd", due_at=due, status=status, created_by_user_id=me.id, **extra))
    await db.commit()

    tiles = (await _read(client))["tiles"]
    assert tiles["new_leads"] == 2
    assert tiles["contacts_pending"] == 2
    assert tiles["hot_companies"] == 1
    assert tiles["meetings_scheduled"] == 1
    assert tiles["active_companies"] == 1
    assert tiles["follow_ups_due"] == 2  # 23:59 IST tonight counts; 00:00 IST tomorrow does not (the IST day boundary)


@pytest.mark.asyncio
async def test_requirement_side_tiles_follow_their_definitions(client, db_session):
    _, me = await _fresh_recruiter(client, db_session)
    now, db = _now(), db_session
    before_period = _month_start() - timedelta(hours=1)
    company = await _company(db, me, stage="requirement_received")
    job = await _job(db, company, me)  # D6 (new)
    await _job(db, company, me, created_at=now - timedelta(days=10))  # old -> not D6
    today = today_ist(now)
    await _job(db, company, me, closes_on=today + timedelta(days=3))  # D14 expiring (+ D6)
    await _job(db, company, me, closes_on=today - timedelta(days=1), created_at=now - timedelta(days=30))  # D14 expired
    await _job(db, company, me, status="on_hold", closes_on=today, created_at=now - timedelta(days=30))  # not open -> not D14
    # D7: applications created in the period
    a1 = await _application(db, job, me)
    a2 = await _application(db, job, me)
    a3 = await _application(db, job, me, created_at=before_period)
    # D10/D12: entered Selected / Rejected in the period (distinct applications)
    _entered(db, a1, "selected")
    _entered(db, a1, "selected")
    _entered(db, a3, "selected", before_period)
    _entered(db, a2, "rejected")
    # D8: shared profiles in the period
    share = ProfileShare(job_id=job.id, company_id=company.id, channel="other", shared_by_user_id=me.id)
    db.add(share)
    await db.flush()
    db.add(ProfileShareItem(share_id=share.id, candidate_id=a1.candidate_id, application_id=a1.id))
    db.add(ProfileShareItem(share_id=share.id, candidate_id=a2.candidate_id, application_id=a2.id))
    db.add(ProfileShareItem(share_id=share.id, candidate_id=a3.candidate_id, application_id=a3.id, created_at=before_period))
    # D9: upcoming open interviews
    db.add(Interview(application_id=a1.id, scheduled_at=now + timedelta(days=1), status="scheduled"))
    db.add(Interview(application_id=a2.id, scheduled_at=now + timedelta(days=2), status="confirmed"))
    db.add(Interview(application_id=a3.id, scheduled_at=now - timedelta(hours=1), status="scheduled"))
    db.add(Interview(application_id=a3.id, scheduled_at=now + timedelta(days=1, hours=1), status="completed"))
    # D11: joined this month
    db.add(JobOffer(application_id=a1.id, offered_on=today, status="accepted", joining_status="joined", actual_joining_date=today))
    db.add(JobOffer(application_id=a2.id, offered_on=today, status="accepted", joining_status="joined", actual_joining_date=before_period.astimezone(IST).date()))
    db.add(JobOffer(application_id=a3.id, offered_on=today, status="accepted", joining_status="pending"))
    await db.commit()

    tiles = (await _read(client))["tiles"]
    assert tiles["new_requirements"] == 2
    assert tiles["candidates_sourced"] == 2
    assert tiles["profiles_shared"] == 2
    assert tiles["interviews_scheduled"] == 2
    assert tiles["candidates_selected"] == 1
    assert tiles["candidates_joined"] == 1
    assert tiles["candidates_rejected"] == 1
    assert (tiles["requirements_expiring"], tiles["requirements_expired"]) == (2, 1)


# --- AC2: scope -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiter_sees_only_their_own_figures(client, db_session):
    manager, me = await _fresh_recruiter(client, db_session)
    peer = await make_recruiter(db_session, manager)
    await _company(db_session, peer)
    await _company(db_session, None)  # the unassigned queue is the manager's, not the recruiter's
    await _company(db_session, me)
    await db_session.commit()
    assert (await _read(client))["tiles"]["new_leads"] == 1
    assert (await client.get(URL, params={"recruiter": str(peer.id)})).status_code == 403
    assert (await _read(client, recruiter=str(me.id)))["tiles"]["new_leads"] == 1


@pytest.mark.asyncio
async def test_a_manager_sees_the_team_and_narrows_to_one_recruiter(client, db_session):
    manager = await make_pm(db_session)
    a, b = await make_recruiter(db_session, manager), await make_recruiter(db_session, manager)
    outsider = await make_recruiter(db_session, await make_pm(db_session))
    await _company(db_session, a)
    await _company(db_session, b)
    await _company(db_session, b)
    await _company(db_session, outsider)
    await db_session.commit()
    await login(client, manager)
    team = (await _read(client))["tiles"]["new_leads"]
    assert team >= 3  # + any unassigned New Lead companies other tests left behind
    only_b = await _read(client, recruiter=str(b.id))
    assert only_b["tiles"]["new_leads"] == 2
    assert only_b["recruiter"] == {"id": str(b.id), "full_name": b.full_name}
    assert (await client.get(URL, params={"recruiter": str(outsider.id)})).status_code == 404
    assert (await client.get(URL, params={"recruiter": str(uuid.uuid4())})).status_code == 404
    assert (await client.get(URL, params={"recruiter": "nope"})).status_code == 422


@pytest.mark.asyncio
async def test_super_admin_narrows_to_any_recruiter(client, db_session):
    rec = await make_recruiter(db_session, await make_pm(db_session))
    await _company(db_session, rec)
    await db_session.commit()
    await as_role(client, db_session, "super_admin", "global")
    assert (await _read(client, recruiter=str(rec.id)))["tiles"]["new_leads"] == 1
    assert (await _read(client))["tiles"]["new_leads"] >= 1
    manager = await make_pm(db_session)
    assert (await client.get(URL, params={"recruiter": str(manager.id)})).status_code == 404  # not a recruiter


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("hr_team", "it"), ("bdm", "it"), ("it_admin", "it"), ("it_student", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(URL)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_recruiter_without_a_profile_is_refused_and_anonymous_is_401(client, db_session):
    assert (await client.get(URL)).status_code == 401
    await as_role(client, db_session, "placement_team", "it")
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_the_read_is_not_cached(client, db_session):
    await _fresh_recruiter(client, db_session)
    assert "no-store" in (await client.get(URL)).headers["cache-control"]


# --- performance: a fixed statement count -------------------------------------------------------------------------------------------------
async def _statements(db, user, recruiter_id=None) -> int:
    seen: list[str] = []
    engine = db.bind.sync_engine if hasattr(db.bind, "sync_engine") else db.bind
    listener = lambda *args: seen.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await metrics.dashboard(db, user, recruiter_id, _now())
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(seen)


@pytest.mark.asyncio
async def test_the_dashboard_is_a_fixed_number_of_statements(db_session):
    manager = await make_pm(db_session)
    rec = await make_recruiter(db_session, manager)
    empty = await _statements(db_session, rec)
    company = await _company(db_session, rec)
    job = await _job(db_session, company, rec)
    for _ in range(3):
        await _application(db_session, job, rec)
    await db_session.commit()
    assert await _statements(db_session, rec) == empty == 3  # the profile gate (company + requirement scope) + one aggregate
    assert await _statements(db_session, manager, rec.id) == 4  # the recruiter lookup + their two scope gates + one aggregate
    assert await _statements(db_session, manager) == 1  # a manager's scope is sub-selects only
