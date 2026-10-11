"""rec-034 -- Recruiter/BDM performance per recruiter (DEC-SCOPE-183 BP1-BP8; backlog Appendix B B1-B12; AC: each column equals its
definition and credit after reassignment follows the actor of the event). The shared test database is never truncated, so every figure
is asserted on a fresh manager's fresh recruiters."""

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select

from app.models import (
    Candidate,
    Company,
    CompanyContact,
    CompanyStageHistory,
    Interview,
    InterviewEvent,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobOffer,
    JobOfferEvent,
    ProfileShare,
    ProfileShareItem,
    RecCandidateSource,
    RecruiterCall,
    RecruiterContract,
    RecruiterContractEvent,
    RecruiterMeeting,
    RecruiterMessage,
)
from app.services import candidates as candidate_svc
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import IST, today_ist
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter

URL = "/api/v1/recruiter/performance/by-recruiter"
FIGURES = (
    "companies_contacted", "meetings", "new_leads", "new_companies", "new_contracts", "new_requirements",
    "candidates_sourced", "profiles_shared", "interviews", "selections", "joining",
)


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _now() -> datetime:
    return datetime.now(UTC)


def _before() -> datetime:
    """An instant just before this month's period starts."""
    return datetime.combine(today_ist(_now()).replace(day=1), time.min, tzinfo=IST) - timedelta(hours=1)


async def _company(db, assigned=None, creator=None, **fields) -> Company:
    company = Company(
        name=f"Acme {_tag()}", assigned_recruiter_user_id=assigned.id if assigned else None, created_by_user_id=creator.id if creator else None, **fields
    )
    db.add(company)
    await db.flush()
    return company


async def _contact(db, company) -> CompanyContact:
    contact = CompanyContact(company_id=company.id, name=f"Anita {_tag()}")
    db.add(contact)
    await db.flush()
    return contact


async def _call(db, company, caller, at=None) -> None:
    contact = await _contact(db, company)
    db.add(RecruiterCall(company_id=company.id, contact_id=contact.id, caller_user_id=caller.id, occurred_at=at or _now(), direction="outgoing", outcome="connected"))


async def _message(db, company, sender, at=None) -> None:
    contact = await _contact(db, company)
    db.add(RecruiterMessage(company_id=company.id, contact_id=contact.id, sender_user_id=sender.id, channel="whatsapp", body="Hello", sent_at=at or _now()))


def _meeting(db, company, creator, completed_by=None, at=None) -> None:
    done = {"status": "completed", "completed_at": at or _now(), "completed_by_user_id": completed_by.id, "outcome": "Good"} if completed_by else {}
    db.add(RecruiterMeeting(
        meeting_code=f"MTG-{_tag()}", company_id=company.id, meeting_type="company_meeting", starts_at=_now() - timedelta(hours=1), mode="Online",
        created_by_user_id=creator.id, **done,
    ))


def _moved(db, company, from_stage, to_stage, actor, at=None) -> None:
    db.add(CompanyStageHistory(company_id=company.id, from_stage=from_stage, to_stage=to_stage, event="manual", actor_user_id=actor.id, **({"created_at": at} if at else {})))


async def _contract(db, company, creator, events, **fields) -> RecruiterContract:
    """`events` = [(to_status, actor, at)]; the contract ends at the last status."""
    status = events[-1][0]
    contract = RecruiterContract(
        company_id=company.id, created_by_user_id=creator.id, status=status, contract_document_key=f"k/{_tag()}", contract_document_content_type="application/pdf",
        **({"start_date": today_ist(_now()), "end_date": today_ist(_now()) + timedelta(days=365)} if status == "active" else {}), **fields,
    )
    db.add(contract)
    await db.flush()
    previous = None
    for to_status, actor, at in events:
        db.add(RecruiterContractEvent(contract_id=contract.id, actor_user_id=actor.id, kind="created" if previous is None else "status", from_status=previous, to_status=to_status, created_at=at))
        previous = to_status
    return contract


async def _job(db, company, assigned=None, creator=None, **fields) -> Job:
    fields.setdefault("status", "sourcing")
    job = Job(
        company_id=company.id, title=f"Java {_tag()}", location="Pune", description="", skills=[], assigned_recruiter_user_id=assigned.id if assigned else None,
        created_by_user_id=creator.id if creator else None, **fields,
    )
    db.add(job)
    await db.flush()
    return job


async def _application(db, job, adder, **fields) -> JobApplication:
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    candidate = Candidate(
        candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=adder.id, name=f"Rahul {_tag()}", email=f"{_tag()}@example.com", preferred_locations=[]
    )
    db.add(candidate)
    await db.flush()
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, added_by_user_id=adder.id, **fields)
    db.add(application)
    await db.flush()
    return application


async def _interview(db, application, status, actors=(), creator=None, at=None) -> None:
    """`actors` record status events in order; the last one is the outcome's recorder."""
    interview = Interview(application_id=application.id, scheduled_at=at or _now() - timedelta(minutes=5), status=status, created_by_user_id=creator.id if creator else None)
    db.add(interview)
    await db.flush()
    for actor in actors:
        db.add(InterviewEvent(interview_id=interview.id, event="status", from_status="scheduled", to_status=status, actor_user_id=actor.id))
        await db.flush()


def _selected(db, application, actor, at=None) -> None:
    db.add(JobApplicationStatusHistory(application_id=application.id, from_status="sourced", to_status="selected", changed_by_user_id=actor.id, **({"created_at": at} if at else {})))


async def _joined(db, application, actor, compensation=None, joined_on=None) -> None:
    offer = JobOffer(
        application_id=application.id, offered_on=today_ist(_now()), status="accepted", joining_status="joined", actual_joining_date=joined_on or today_ist(_now()),
        compensation=compensation, currency="INR",
    )
    db.add(offer)
    await db.flush()
    db.add(JobOfferEvent(offer_id=offer.id, event="joined", to_status="accepted", actor_user_id=actor.id))


async def _read(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _row(payload: dict, user) -> dict:
    return next(row for row in payload["items"] if row["user_id"] == str(user.id))


def _figures(row: dict) -> dict:
    return {key: row[key] for key in FIGURES if row[key]}


async def _team(client, db, size=1):
    manager = await make_pm(db)
    people = [await make_recruiter(db, manager) for _ in range(size)]
    await login(client, manager)
    return manager, people


# --- AC: each column equals its definition -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_business_development_figures_follow_their_definitions(client, db_session):
    _, (me, peer) = await _team(client, db_session, size=2)
    db, before = db_session, _before()
    mine = await _company(db, me, creator=me)  # B3
    old = await _company(db, me, creator=me, created_at=before)  # created before the period
    theirs = await _company(db, peer, creator=peer)  # B3 for peer
    await _call(db, mine, me)
    await _call(db, mine, me)  # B1 counts companies, not calls
    await _call(db, theirs, me, at=before)  # before the period
    await _message(db, old, me)  # B1
    _meeting(db, theirs, peer, completed_by=me)  # B1 + B2 for me, though peer booked it
    _meeting(db, mine, me, completed_by=me, at=before)  # completed before the period
    _meeting(db, mine, me)  # still scheduled
    db.add(RecruiterCall(candidate_id=(await _application(db, await _job(db, mine), me)).candidate_id, caller_user_id=me.id, occurred_at=_now(), direction="outgoing", outcome="busy"))
    _moved(db, mine, "interested", "meeting_scheduled", me)  # B4: past Interested
    _moved(db, theirs, "new_lead", "contacted", me)  # not past Interested
    _moved(db, old, "contacted", "requirement_discussion", peer, at=before)  # first crossing before the period ...
    _moved(db, old, "interested", "requirement_discussion", me)  # ... so a second crossing is not new
    await _contract(db, mine, me, [("discussion", me, before), ("signed", me, _now())])  # B5
    await _contract(db, old, me, [("signed", me, before), ("active", me, _now())])  # signed before the period
    await _contract(db, theirs, peer, [("negotiation", peer, _now())])  # not signed
    await _job(db, mine, peer, creator=me)  # B6 for me, though assigned to peer
    await _job(db, mine, me, creator=me, created_at=before)
    await db.commit()

    payload = await _read(client)
    assert {key: _row(payload, me)[key] for key in FIGURES[:6]} == {
        "companies_contacted": 3, "meetings": 1, "new_leads": 1, "new_companies": 1, "new_contracts": 1, "new_requirements": 1,
    }
    assert {key: _row(payload, peer)[key] for key in FIGURES[:6]} == {
        "companies_contacted": 0, "meetings": 0, "new_leads": 1, "new_companies": 0, "new_contracts": 0, "new_requirements": 0,
    }


@pytest.mark.asyncio
async def test_recruitment_figures_follow_their_definitions(client, db_session):
    _, (me, peer) = await _team(client, db_session, size=2)
    db, before = db_session, _before()
    job = await _job(db, await _company(db, peer), peer)  # peer's requirement: credit still follows the actor
    a1, a2 = await _application(db, job, me), await _application(db, job, me)  # B7
    a3 = await _application(db, job, me, created_at=before)
    a4 = await _application(db, job, peer)
    share = ProfileShare(job_id=job.id, company_id=job.company_id, channel="other", shared_by_user_id=me.id)
    db.add(share)
    await db.flush()
    for application, at in ((a1, None), (a2, None), (a3, before)):  # B8 = 2
        db.add(ProfileShareItem(share_id=share.id, candidate_id=application.candidate_id, application_id=application.id, **({"created_at": at} if at else {})))
    await _interview(db, a1, "completed", actors=[me])  # B9
    await _interview(db, a2, "selected", actors=[peer, me])  # the last outcome is mine
    await _interview(db, a3, "completed", creator=me)  # no status event: its creator
    await _interview(db, a4, "rejected", actors=[me], at=before)  # held before the period
    await _interview(db, a4, "no_show", actors=[me])  # not held
    await _interview(db, a4, "completed", actors=[peer])  # peer's
    _selected(db, a1, me, at=_now() - timedelta(minutes=2))  # B10
    _selected(db, a1, peer)  # a later row for the same application: still mine, once
    _selected(db, a2, peer)  # peer's
    _selected(db, a3, me, at=before)
    await _joined(db, a1, me)  # B11
    await _joined(db, a2, peer)
    await _joined(db, a3, me, joined_on=today_ist(_now()).replace(day=1) - timedelta(days=1))  # joined before the period
    await db.commit()

    payload = await _read(client)
    assert {key: _row(payload, me)[key] for key in FIGURES[6:]} == {"candidates_sourced": 2, "profiles_shared": 2, "interviews": 3, "selections": 1, "joining": 1}
    assert {key: _row(payload, peer)[key] for key in FIGURES[6:]} == {"candidates_sourced": 1, "profiles_shared": 0, "interviews": 1, "selections": 1, "joining": 1}


@pytest.mark.asyncio
async def test_revenue_is_the_fee_per_hire_of_the_period_joinings(client, db_session):
    _, (me,) = await _team(client, db_session)
    db = db_session
    percent = await _job(db, await _company(db, me), me, fee_basis="percent_of_ctc", fee_value=Decimal("8.33"))  # the requirement override
    priced = await _company(db, me)
    await _contract(db, priced, me, [("signed", me, _before())], fee_basis="fixed", fee_value=Decimal("50000"))
    fixed = await _job(db, priced, me)  # the company's current contract
    await _joined(db, await _application(db, percent, me), me, compensation=Decimal("1000000"))  # 83,300.00
    await _joined(db, await _application(db, percent, me), me)  # no compensation: unpriced, adds nothing
    await _joined(db, await _application(db, fixed, me), me, compensation=Decimal("1"))  # 50,000.00
    await _joined(db, await _application(db, await _job(db, await _company(db, me), me), me), me)  # no fee at all
    await db.commit()
    row = _row(await _read(client), me)
    assert (row["joining"], row["revenue"]) == (4, "133300.00")


# --- AC: credit after reassignment follows the actor of the event --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_credit_stays_with_the_actor_after_a_reassignment(client, db_session):
    _, (me, peer) = await _team(client, db_session, size=2)
    db = db_session
    company = await _company(db, me, creator=me)
    await _call(db, company, me)
    job = await _job(db, company, me, creator=me)
    await _application(db, job, me)
    await db.commit()
    company.assigned_recruiter_user_id = peer.id  # reassigned after the work was done
    job.assigned_recruiter_user_id = peer.id
    await db.commit()
    payload = await _read(client)
    assert _figures(_row(payload, me)) == {"companies_contacted": 1, "new_leads": 1, "new_requirements": 1, "candidates_sourced": 1}
    assert _figures(_row(payload, peer)) == {}


# --- BP3 / BP4: rows and the Total --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_total_is_the_sum_of_the_team_rows(client, db_session):
    manager, (a, b) = await _team(client, db_session, size=2)
    db = db_session
    outsider = await make_recruiter(db, await make_pm(db))
    for person in (a, b, b, outsider, manager):  # the manager's and the outsider's work is in no row
        await _call(db, await _company(db, creator=person), person)
    await db.commit()
    payload = await _read(client)
    assert sorted(row["user_id"] for row in payload["items"]) == sorted([str(a.id), str(b.id)])
    assert (_row(payload, a)["new_leads"], _row(payload, b)["new_leads"]) == (1, 2)
    for key in FIGURES:
        assert payload["totals"][key] == sum(row[key] for row in payload["items"]), key
    assert (payload["totals"]["full_name"], payload["totals"]["revenue"], payload["recruiter"]) == ("Total", "0.00", None)


@pytest.mark.asyncio
async def test_an_inactive_recruiter_appears_only_with_figures_in_the_period(client, db_session):
    manager, (active,) = await _team(client, db_session)
    db = db_session
    gone = await make_recruiter(db, manager, active=False)
    left_mid_period = await make_recruiter(db, manager, active=False)
    await _company(db, creator=left_mid_period)
    await db.commit()
    payload = await _read(client)
    assert {row["user_id"] for row in payload["items"]} == {str(active.id), str(left_mid_period.id)}
    assert (_row(payload, left_mid_period)["active"], _row(payload, left_mid_period)["new_leads"]) == (False, 1)
    assert str(gone.id) not in {row["user_id"] for row in payload["items"]}


@pytest.mark.asyncio
async def test_an_empty_period_is_all_zeros(client, db_session):
    _, (me,) = await _team(client, db_session)
    row = _row(await _read(client), me)
    assert _figures(row) == {} and row["revenue"] == "0.00"


# --- BP1: roles and scope --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiter_sees_only_their_own_row(client, db_session):
    manager = await make_pm(db_session)
    me, peer = await make_recruiter(db_session, manager), await make_recruiter(db_session, manager)
    await _company(db_session, creator=me)
    await db_session.commit()
    await login(client, me)
    for params in ({}, {"recruiter": str(me.id)}):
        payload = await _read(client, **params)
        assert [row["user_id"] for row in payload["items"]] == [str(me.id)]
        assert (payload["items"][0]["new_leads"], payload["totals"]) == (1, None)
    response = await client.get(URL, params={"recruiter": str(peer.id)})
    assert (response.status_code, response.json()["detail"]) == (403, metrics.OWN_ROW_ONLY)


@pytest.mark.asyncio
async def test_a_manager_narrows_only_within_the_team(client, db_session):
    _, (a, b) = await _team(client, db_session, size=2)
    outsider = await make_recruiter(db_session, await make_pm(db_session))
    payload = await _read(client, recruiter=str(a.id))
    assert [row["user_id"] for row in payload["items"]] == [str(a.id)]
    assert payload["recruiter"] == {"id": str(a.id), "full_name": a.full_name}
    assert payload["totals"]["new_leads"] == _row(payload, a)["new_leads"]
    for recruiter in (outsider.id, uuid.uuid4()):
        assert (await client.get(URL, params={"recruiter": str(recruiter)})).status_code == 404
    assert (await client.get(URL, params={"recruiter": "nope"})).status_code == 422


@pytest.mark.asyncio
async def test_super_admin_sees_every_recruiter(client, db_session):
    someone = await make_recruiter(db_session, await make_pm(db_session))
    await _company(db_session, creator=someone)
    await db_session.commit()
    await as_role(client, db_session, "super_admin", "global")
    assert _row(await _read(client, recruiter=str(someone.id)), someone)["new_leads"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("hr_team", "it"), ("bdm", "it"), ("overseas_admin", "overseas"), ("it_student", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(URL)
    assert (response.status_code, response.json()["detail"]) == (403, metrics.BY_RECRUITER_REFUSED)  # QA34-02: not "for administrators"


@pytest.mark.asyncio
async def test_anonymous_is_401_and_the_read_is_not_cached(client, db_session):
    assert (await client.get(URL)).status_code == 401
    await _team(client, db_session)
    assert "no-store" in (await client.get(URL)).headers["cache-control"]


@pytest.mark.asyncio
async def test_the_period_defaults_to_this_month_and_is_validated(client, db_session):
    await _team(client, db_session)
    today = today_ist(_now())
    payload = await _read(client)
    assert (payload["date_from"], payload["date_to"]) == (today.replace(day=1).isoformat(), today.isoformat())
    response = await client.get(URL, params={"from": today.isoformat(), "to": (today - timedelta(days=1)).isoformat()})
    assert (response.status_code, response.json()["detail"]) == (422, "The start date must not be after the end date")
    assert (await _read(client, **{"from": today.isoformat()}))["date_from"] == today.isoformat()


# --- performance: a fixed statement count -----------------------------------------------------------------------------------------------
async def _statements(db, user, recruiter_id=None) -> int:
    seen: list[str] = []
    engine = db.bind.sync_engine if hasattr(db.bind, "sync_engine") else db.bind
    listener = lambda *args: seen.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await metrics.by_recruiter(db, user, recruiter_id, None, None, _now())
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(seen)


@pytest.mark.asyncio
async def test_the_read_is_a_fixed_number_of_statements(db_session):
    manager = await make_pm(db_session)
    a = await make_recruiter(db_session, manager)
    empty = await _statements(db_session, manager)
    for person in (a, await make_recruiter(db_session, manager)):
        job = await _job(db_session, await _company(db_session, person, creator=person), person, creator=person)
        await _joined(db_session, await _application(db_session, job, person), person)
    await db_session.commit()
    assert await _statements(db_session, manager) == empty == 3  # the team + one aggregate + the hires
    assert await _statements(db_session, a) == 2  # a recruiter: no lookup
