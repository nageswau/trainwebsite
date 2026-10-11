"""rec-035 -- the management dashboard, recruiter business view (DEC-SCOPE MG1-MG8; backlog Appendix B M1-M9; AC: top companies by
joined count, ties by name; top job categories by open requirements). The shared test database is never truncated, so the snapshot totals
are asserted as deltas over a fresh manager's team, and the period figures over one far-past day that no other test writes to."""

import random
import uuid
from datetime import UTC, date, datetime, time, timedelta

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
    RecCandidateSource,
    RecJobCategory,
)
from app.services import candidates as candidate_svc
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import IST, today_ist
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter

URL = "/api/v1/recruiter/management"
TOTALS = ("companies", "active_recruiters", "open_requirements", "candidates_in_pipeline", "interviews", "selected", "joined")


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _now() -> datetime:
    return datetime.now(UTC)


def _quiet_day() -> date:
    """A random day years back: only this test writes period events on it."""
    return date(2012, 1, 1) + timedelta(days=random.randrange(3 * 365))


def _at(day: date) -> datetime:
    return datetime.combine(day, time(11), tzinfo=IST)


async def _company(db, recruiter, **fields) -> Company:
    fields.setdefault("stage", "contacted")
    fields.setdefault("name", f"Acme {_tag()}")
    company = Company(assigned_recruiter_user_id=recruiter.id if recruiter else None, **fields)
    db.add(company)
    await db.flush()
    return company


async def _job(db, company, recruiter=None, **fields) -> Job:
    fields.setdefault("status", "sourcing")
    job = Job(company_id=company.id, title=f"Java {_tag()}", location="Pune", description="", skills=[], assigned_recruiter_user_id=recruiter.id if recruiter else None, **fields)
    db.add(job)
    await db.flush()
    return job


async def _candidate(db, creator) -> Candidate:
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    candidate = Candidate(
        candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=creator.id, name=f"Rahul {_tag()}", email=f"{_tag()}@example.com", preferred_locations=[]
    )
    db.add(candidate)
    await db.flush()
    return candidate


async def _application(db, job, creator, candidate=None, **fields) -> JobApplication:
    candidate = candidate or await _candidate(db, creator)
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, **fields)
    db.add(application)
    await db.flush()
    return application


async def _category(db, name=None) -> RecJobCategory:
    category = RecJobCategory(name=name or f"Cat {_tag()}")
    db.add(category)
    await db.flush()
    return category


async def _read(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _day(day: date) -> dict:
    return {"from": day.isoformat(), "to": day.isoformat()}


async def _team(client, db, size=1):
    manager = await make_pm(db)
    people = [await make_recruiter(db, manager) for _ in range(size)]
    await login(client, manager)
    return manager, people


async def _joined(db, job, creator, day: date) -> JobApplication:
    application = await _application(db, job, creator, status="joined")
    db.add(JobOffer(application_id=application.id, offered_on=day, status="accepted", joining_status="joined", actual_joining_date=day))
    return application


# --- M1-M4: snapshots now, as deltas over a fresh team ---------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_snapshot_totals_follow_their_definitions(client, db_session):
    _, (me,) = await _team(client, db_session)
    db = db_session
    before = (await _read(client))["totals"]

    live = await _company(db, me)  # M1; active (a live requirement)
    await _company(db, me, stage="new_lead")  # not past New Lead -> not M1
    await _company(db, me, archived_at=_now())  # archived -> not M1
    parked = await _company(db, me)  # M1, but its only requirement is On Hold -> not active
    j1 = await _job(db, live, me)  # M3
    await _job(db, live, me, status="new")  # M3: New is open (D5's set)
    await _job(db, live, me, status="closed")
    await _job(db, parked, me, status="on_hold")
    for name, active in (("Asha", True), ("Ravi", True), ("Old", False)):  # M2: two active contacts at the active company
        db.add(CompanyContact(company_id=live.id, name=name, active=active))
    db.add(CompanyContact(company_id=parked.id, name="Meera"))  # a company with no live requirement -> not M2

    twice = await _candidate(db, me)  # M4 once, though in two live applications
    await _application(db, j1, me, candidate=twice)
    await _application(db, await _job(db, live, me), me, candidate=twice)  # (this requirement is M3 too)
    await _application(db, j1, me, status="interview")  # M4
    for status in ("joined", "rejected", "withdrawn"):  # finished -> not M4
        await _application(db, j1, me, status=status)
    await db.commit()

    after = (await _read(client))["totals"]
    delta = {key: after[key] - before[key] for key in ("companies", "active_recruiters", "open_requirements", "candidates_in_pipeline")}
    assert delta == {"companies": 2, "active_recruiters": 2, "open_requirements": 3, "candidates_in_pipeline": 2}


# --- M5-M8: the period ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_period_totals_and_top_companies(client, db_session):
    manager, (a, b) = await _team(client, db_session, size=2)
    db = db_session
    day = _quiet_day()
    big, tie_z, tie_a = await _company(db, a), await _company(db, b, name=f"zeta {_tag()}"), await _company(db, None, name=f"Alpha {_tag()}")
    quiet = await _company(db, a)  # no hires -> not listed
    jb, jz, ja, jq = await _job(db, big, a), await _job(db, tie_z, b), await _job(db, tie_a), await _job(db, quiet, a)
    a1 = await _joined(db, jb, a, day)
    await _joined(db, jb, a, day)
    await _joined(db, jz, b, day)
    await _joined(db, ja, a, day)  # unassigned -> in the manager's scope
    await _joined(db, jb, a, day + timedelta(days=1))  # outside the period
    outsider = await make_recruiter(db, await make_pm(db))
    elsewhere = await _company(db, outsider, name=f"Aaa {_tag()}")
    await _joined(db, await _job(db, elsewhere, outsider), outsider, day)  # another team -> nowhere for this manager
    for status in ("scheduled", "completed", "no_show"):  # M5: every interview scheduled in the period
        db.add(Interview(application_id=a1.id, scheduled_at=_at(day), status=status))
    db.add(Interview(application_id=a1.id, scheduled_at=_at(day - timedelta(days=1)), status="completed"))
    picked = await _application(db, jq, a)
    for _ in range(2):  # M6 counts applications, not rows
        db.add(JobApplicationStatusHistory(application_id=picked.id, from_status="sourced", to_status="selected", created_at=_at(day)))
    await db.commit()

    payload = await _read(client, **_day(day))
    assert (payload["date_from"], payload["date_to"]) == (day.isoformat(), day.isoformat())
    totals = payload["totals"]
    assert (totals["interviews"], totals["selected"], totals["joined"]) == (3, 1, 4)
    assert [(row["id"], row["joined"]) for row in payload["top_companies"]] == [(str(big.id), 2), (str(tie_a.id), 1), (str(tie_z.id), 1)]
    assert payload["top_companies"][0]["name"] == big.name
    performance = (await client.get("/api/v1/recruiter/performance", params=_day(day))).json()["totals"]
    assert (performance["selected"], performance["joined"]) == (totals["selected"], totals["joined"])  # MG2: rec-033's figures

    await as_role(client, db, "super_admin", "global")
    everyone = await _read(client, **_day(day))
    assert str(elsewhere.id) in [row["id"] for row in everyone["top_companies"]]


@pytest.mark.asyncio
async def test_top_companies_stop_at_ten(client, db_session):
    _, (me,) = await _team(client, db_session)
    db = db_session
    day = _quiet_day()
    for _ in range(11):
        await _joined(db, await _job(db, await _company(db, me), me), me, day)
    await db.commit()
    assert len((await _read(client, **_day(day)))["top_companies"]) == 10


@pytest.mark.asyncio
async def test_no_data_is_zeros_and_empty_lists(client, db_session):
    await _team(client, db_session)
    payload = await _read(client, **_day(_quiet_day()))
    assert (payload["totals"]["interviews"], payload["totals"]["selected"], payload["totals"]["joined"]) == (0, 0, 0)
    assert payload["top_companies"] == []
    assert set(payload["totals"]) == set(TOTALS)


# --- M9: top job categories by open requirements ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_top_categories_by_open_requirements_ties_by_name(client, db_session):
    _, (me,) = await _team(client, db_session)
    db = db_session
    tag = _tag()
    most, tie_z, tie_a = await _category(db, f"Mid {tag}"), await _category(db, f"zz {tag}"), await _category(db, f"AA {tag}")
    company = await _company(db, me)
    for category, count in ((most, 7), (tie_z, 6), (tie_a, 6)):
        for _ in range(count):
            await _job(db, company, me, job_category_id=category.id)
    await _job(db, company, me, job_category_id=tie_z.id, status="closed")  # not open
    await _job(db, company, me, job_category_id=tie_z.id, status="on_hold")  # not open
    await db.commit()
    rows = [(row["id"], row["open_requirements"]) for row in (await _read(client))["top_categories"] if row["name"].endswith(tag)]
    assert rows == [(str(most.id), 7), (str(tie_a.id), 6), (str(tie_z.id), 6)]


# --- MG3: the period ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_period_defaults_to_this_month_and_is_validated(client, db_session):
    await _team(client, db_session)
    today = today_ist(_now())
    payload = await _read(client)
    assert (payload["date_from"], payload["date_to"]) == (today.replace(day=1).isoformat(), today.isoformat())
    for params, message in (
        ({"from": today.isoformat(), "to": (today - timedelta(days=1)).isoformat()}, "The start date must not be after the end date"),
        ({"to": (today + timedelta(days=1)).isoformat()}, "The range can't end in the future"),
    ):
        response = await client.get(URL, params=params)
        assert (response.status_code, response.json()["detail"]) == (422, message)
    assert (await client.get(URL, params={"from": "2026-13-01"})).status_code == 422


# --- MG1: roles --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("super_admin", "global"), ("it_admin", "it")])
async def test_administrators_read_it(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert set((await _read(client))["totals"]) == set(TOTALS)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("placement_team", "it"), ("hr_team", "it"), ("bdm", "it"), ("overseas_admin", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_a_recruiter_is_refused_and_anonymous_is_401(client, db_session):
    assert (await client.get(URL)).status_code == 401
    await login(client, await make_recruiter(db_session, await make_pm(db_session)))
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_the_read_is_not_cached(client, db_session):
    await _team(client, db_session)
    assert "no-store" in (await client.get(URL)).headers["cache-control"]


@pytest.mark.asyncio
async def test_the_read_is_a_fixed_number_of_statements(db_session):
    manager = await make_pm(db_session)
    seen: list[str] = []
    engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.bind
    listener = lambda *args: seen.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await metrics.management(db_session, manager, None, None, _now())
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(seen) == 4  # the team, the totals, the top companies, the top categories
