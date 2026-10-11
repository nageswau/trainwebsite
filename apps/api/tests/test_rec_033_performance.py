"""rec-033 -- the recruiter performance dashboard (DEC-SCOPE-182 PF1-PF9; backlog Appendix B P1-P15; AC1 ratios with "—" on a zero
denominator, AC2 the Total is the sum of the recruiters). The shared test database is never truncated, so every figure is asserted on a
fresh manager's fresh recruiters; the Unassigned row (shared by every test) is only checked through the Total = Σ rows rule."""

import csv
import io
import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import event, func, select

from app.models import (
    AuditLog,
    Candidate,
    Company,
    Interview,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobOffer,
    JobStatusHistory,
    ProfileShare,
    ProfileShareItem,
    RecCandidateSource,
)
from app.services import candidates as candidate_svc
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import IST, today_ist
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter

URL = "/api/v1/recruiter/performance"
COUNTS = ("recruiter_leads", "active_companies", "requirements", "candidates_sourced", "profiles_shared", "interviews", "selected", "joined", "requirements_closed")
RATIOS = ("selection_pct", "joining_pct", "profile_to_interview", "interview_to_selection", "selection_to_joining", "avg_closure_days")


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _now() -> datetime:
    return datetime.now(UTC)


def _month_start() -> datetime:
    return datetime.combine(today_ist(_now()).replace(day=1), time.min, tzinfo=IST)


def _ist_day(at: datetime) -> date:
    return at.astimezone(IST).date()


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


def _job_moved(db, job, status, at) -> None:
    db.add(JobStatusHistory(job_id=job.id, from_status=None, to_status=status, created_at=at))


async def _read(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _row(payload: dict, user) -> dict:
    return next(row for row in payload["items"] if row["user_id"] == str(user.id))


async def _team(client, db, size=1):
    manager = await make_pm(db)
    people = [await make_recruiter(db, manager) for _ in range(size)]
    await login(client, manager)
    return manager, people


# --- AC1: each figure follows its definition; ratios; "—" (null) on a zero denominator -------------------------------------------------
@pytest.mark.asyncio
async def test_each_figure_follows_its_definition(client, db_session):
    _, (me,) = await _team(client, db_session)
    db, now = db_session, _now()
    before = _month_start() - timedelta(hours=1)
    today = today_ist(now)
    c1 = await _company(db, me)  # P1, P2 (a live requirement)
    c2 = await _company(db, me, created_at=before)  # its only requirement is On Hold -> not P2
    c3 = await _company(db, me, created_at=before, archived_at=now - timedelta(days=1))  # archived -> not P2
    j1 = await _job(db, c1, me)  # P3
    await _job(db, c2, me, status="on_hold", created_at=before)
    await _job(db, c3, me, created_at=before)
    a1, a2 = await _application(db, j1, me), await _application(db, j1, me)  # P4
    a3 = await _application(db, j1, me, created_at=before)
    share = ProfileShare(job_id=j1.id, company_id=c1.id, channel="other", shared_by_user_id=me.id)
    db.add(share)
    await db.flush()
    for application, at in ((a1, None), (a2, None), (a3, before)):  # P5 = 2
        db.add(ProfileShareItem(share_id=share.id, candidate_id=application.candidate_id, application_id=application.id, **({"created_at": at} if at else {})))
    db.add(Interview(application_id=a1.id, scheduled_at=now - timedelta(minutes=2), status="completed"))  # P6
    db.add(Interview(application_id=a2.id, scheduled_at=now - timedelta(minutes=3), status="selected"))  # P6
    db.add(Interview(application_id=a2.id, scheduled_at=now - timedelta(minutes=4), status="no_show"))
    db.add(Interview(application_id=a3.id, scheduled_at=before, status="completed"))  # before the period
    db.add(Interview(application_id=a1.id, scheduled_at=now + timedelta(days=1), status="scheduled"))  # not held
    _entered(db, a1, "selected")
    _entered(db, a1, "selected")  # P7 counts applications, not rows
    _entered(db, a2, "selected")
    _entered(db, a3, "selected", before)
    _entered(db, a2, "rejected")
    db.add(JobOffer(application_id=a1.id, offered_on=today, status="accepted", joining_status="joined", actual_joining_date=today))  # P8
    db.add(JobOffer(application_id=a2.id, offered_on=today, status="accepted", joining_status="joined", actual_joining_date=_ist_day(before)))
    closed_at = now - timedelta(minutes=1)
    j4 = await _job(db, c1, me, status="closed", requirement_date=today - timedelta(days=10), created_at=before)
    j5 = await _job(db, c1, me, status="closed", requirement_date=today - timedelta(days=21), created_at=before)
    _job_moved(db, j4, "closed", closed_at)
    _job_moved(db, j5, "closed", closed_at)
    await db.commit()

    row = _row(await _read(client), me)
    assert {key: row[key] for key in COUNTS} == {
        "recruiter_leads": 1, "active_companies": 1, "requirements": 1, "candidates_sourced": 2, "profiles_shared": 2, "interviews": 2,
        "selected": 2, "joined": 1, "requirements_closed": 2,
    }
    expected_days = ((_ist_day(closed_at) - (today - timedelta(days=10))).days + (_ist_day(closed_at) - (today - timedelta(days=21))).days) / 2
    assert row["avg_closure_days"] == round(expected_days, 1)
    assert (row["selection_pct"], row["joining_pct"]) == (100.0, 50.0)  # P7/P4, P8/P7
    assert (row["profile_to_interview"], row["interview_to_selection"], row["selection_to_joining"]) == (1.0, 1.0, 0.5)
    assert (row["full_name"], row["active"], row["status"]) == (me.full_name, True, "Active")


@pytest.mark.asyncio
async def test_an_empty_period_is_zeros_and_every_ratio_is_null(client, db_session):
    _, (me,) = await _team(client, db_session)
    row = _row(await _read(client), me)
    assert all(row[key] == 0 for key in COUNTS)
    assert all(row[key] is None for key in RATIOS)


@pytest.mark.asyncio
async def test_ratios_round_and_a_zero_denominator_is_null(client, db_session):
    _, (me,) = await _team(client, db_session)
    db = db_session
    job = await _job(db, await _company(db, me), me)
    applications = [await _application(db, job, me) for _ in range(3)]
    _entered(db, applications[0], "selected")
    await db.commit()
    row = _row(await _read(client), me)
    assert row["selection_pct"] == 33.3  # 1 / 3
    assert row["joining_pct"] == 0.0  # 0 / 1
    assert row["profile_to_interview"] is None  # 0 shared
    assert row["interview_to_selection"] is None  # 0 interviews


# --- AC2: the Total is the sum of the recruiters; credit (PF2) --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_total_is_the_sum_of_the_rows_and_each_figure_has_one_owner(client, db_session):
    manager, (a, b) = await _team(client, db_session, size=2)
    db = db_session
    company = await _company(db, a)
    await _job(db, company, b)  # assigned to b at a's company -> credited to b only
    await _job(db, company)  # unassigned at a's company -> a
    await _job(db, await _company(db, None))  # nobody -> Unassigned
    outsider = await make_recruiter(db, await make_pm(db))
    await _job(db, await _company(db, outsider), outsider)  # another team -> nowhere
    await db.commit()
    payload = await _read(client)
    assert [row["full_name"] for row in payload["items"]][-1] == "Unassigned"
    assert {row["user_id"] for row in payload["items"][:-1]} == {str(a.id), str(b.id)}
    assert (_row(payload, a)["requirements"], _row(payload, b)["requirements"]) == (1, 1)
    assert (_row(payload, a)["recruiter_leads"], _row(payload, b)["recruiter_leads"]) == (1, 0)
    for key in COUNTS:
        assert payload["totals"][key] == sum(row[key] for row in payload["items"]), key
    assert payload["totals"]["full_name"] == "Total"
    unassigned = payload["items"][-1]["requirements"]
    await _job(db, await _company(db, None))
    await db.commit()
    assert (await _read(client))["items"][-1]["requirements"] == unassigned + 1


@pytest.mark.asyncio
async def test_total_ratios_are_recomputed_from_the_total_counts(client, db_session):
    _, (a, b) = await _team(client, db_session, size=2)
    db = db_session
    for person, sourced, selected in ((a, 1, 1), (b, 3, 0)):
        job = await _job(db, await _company(db, person), person)
        applications = [await _application(db, job, person) for _ in range(sourced)]
        for application in applications[:selected]:
            _entered(db, application, "selected")
    await db.commit()
    payload = await _read(client, recruiter=str(a.id))
    assert payload["totals"]["selection_pct"] == 100.0 == _row(payload, a)["selection_pct"]  # a drill-down: Total = the one row
    assert payload["recruiter"] == {"id": str(a.id), "full_name": a.full_name}
    assert [row["user_id"] for row in payload["items"]] == [str(a.id)]
    team = await _read(client)
    totals = team["totals"]
    assert totals["selection_pct"] == (round(totals["selected"] / totals["candidates_sourced"] * 100, 1) if totals["candidates_sourced"] else None)


# --- PF4: Active Companies at a past period end; PF7: closure ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_active_companies_use_the_status_at_the_period_end(client, db_session):
    _, (me,) = await _team(client, db_session)
    db, now = db_session, _now()
    long_ago, while_ago = now - timedelta(days=60), now - timedelta(days=50)
    first = _month_start().date()
    last_month = ((first - timedelta(days=1)).replace(day=1), first - timedelta(days=1))
    held_now = await _job(db, await _company(db, me, created_at=long_ago), me, status="on_hold", created_at=long_ago)
    _job_moved(db, held_now, "sourcing", long_ago)
    _job_moved(db, held_now, "on_hold", now - timedelta(hours=1))  # live at last month's end, On Hold today
    live_now = await _job(db, await _company(db, me, created_at=long_ago), me, created_at=long_ago)
    _job_moved(db, live_now, "sourcing", long_ago)
    _job_moved(db, live_now, "on_hold", while_ago)
    _job_moved(db, live_now, "sourcing", now - timedelta(hours=1))  # On Hold at last month's end, live today
    newer = await _job(db, await _company(db, me), me)  # created after last month
    _job_moved(db, newer, "sourcing", now)
    await db.commit()
    past = _row(await _read(client, **{"from": last_month[0].isoformat(), "to": last_month[1].isoformat()}), me)
    assert past["active_companies"] == 1
    assert _row(await _read(client), me)["active_companies"] == 2


@pytest.mark.asyncio
async def test_closure_counts_a_requirement_once_from_its_last_close(client, db_session):
    _, (me,) = await _team(client, db_session)
    db, now = db_session, _now()
    today = today_ist(now)
    reopened = await _job(db, await _company(db, me), me, status="closed", requirement_date=today - timedelta(days=30), created_at=_month_start() - timedelta(days=40))
    _job_moved(db, reopened, "closed", _month_start() - timedelta(days=2))  # before the period
    _job_moved(db, reopened, "closed", now - timedelta(hours=3))
    _job_moved(db, reopened, "requirement_received", now - timedelta(hours=2))
    last_close = now - timedelta(minutes=5)
    _job_moved(db, reopened, "closed", last_close)
    await db.commit()
    row = _row(await _read(client), me)
    assert row["requirements_closed"] == 1
    assert row["avg_closure_days"] == float((_ist_day(last_close) - (today - timedelta(days=30))).days)


@pytest.mark.asyncio
async def test_closure_without_a_requirement_date_counts_from_the_created_day(client, db_session):
    _, (me,) = await _team(client, db_session)
    db, now = db_session, _now()
    created = now - timedelta(days=5)
    job = await _job(db, await _company(db, me), me, status="closed", created_at=created)
    _job_moved(db, job, "closed", now)
    await db.commit()
    assert _row(await _read(client), me)["avg_closure_days"] == float((_ist_day(now) - _ist_day(created)).days)


# --- PF3: the period -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_period_defaults_to_this_month_and_is_validated(client, db_session):
    await _team(client, db_session)
    today = today_ist(_now())
    payload = await _read(client)
    assert (payload["date_from"], payload["date_to"], payload["recruiter"]) == (today.replace(day=1).isoformat(), today.isoformat(), None)
    for params, message in (
        ({"from": today.isoformat(), "to": (today - timedelta(days=1)).isoformat()}, "The start date must not be after the end date"),
        ({"to": (today + timedelta(days=1)).isoformat()}, "The range can't end in the future"),
        ({"from": (today - timedelta(days=400)).isoformat()}, "The range can't be longer than 366 days"),
    ):
        response = await client.get(URL, params=params)
        assert (response.status_code, response.json()["detail"]) == (422, message)
    assert (await client.get(URL, params={"from": "2026-13-01"})).status_code == 422
    assert (await _read(client, **{"from": today.isoformat()}))["date_from"] == today.isoformat()  # the alias is honoured


# --- PF1: roles and scope ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_manager_drills_down_only_within_the_team(client, db_session):
    _, (a,) = await _team(client, db_session)
    outsider = await make_recruiter(db_session, await make_pm(db_session))
    other_manager = await make_pm(db_session)
    assert (await _read(client, recruiter=str(a.id)))["recruiter"]["id"] == str(a.id)
    for recruiter in (outsider.id, other_manager.id, uuid.uuid4()):
        assert (await client.get(URL, params={"recruiter": str(recruiter)})).status_code == 404
    assert (await client.get(URL, params={"recruiter": "nope"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "it_admin"])
async def test_administrators_see_every_recruiter(client, db_session, role):
    someone = await make_recruiter(db_session, await make_pm(db_session))
    await _job(db_session, await _company(db_session, someone), someone)
    await db_session.commit()
    await as_role(client, db_session, role, "global" if role == "super_admin" else "it")
    assert _row(await _read(client, recruiter=str(someone.id)), someone)["requirements"] == 1
    assert _row(await _read(client), someone)["requirements"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("placement_team", "it"), ("hr_team", "it"), ("bdm", "it"), ("overseas_admin", "overseas"), ("it_student", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(URL)).status_code == 403
    assert (await client.get(f"{URL}.csv")).status_code == 403


@pytest.mark.asyncio
async def test_a_recruiter_is_refused_and_anonymous_is_401(client, db_session):
    assert (await client.get(URL)).status_code == 401
    manager = await make_pm(db_session)
    await login(client, await make_recruiter(db_session, manager))
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_the_read_is_not_cached(client, db_session):
    await _team(client, db_session)
    assert "no-store" in (await client.get(URL)).headers["cache-control"]


# --- PF9: CSV --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_csv_is_the_table_and_is_audited(client, db_session):
    manager, (me,) = await _team(client, db_session)
    db = db_session
    job = await _job(db, await _company(db, me), me)
    await _application(db, job, me)
    await db.commit()
    today = today_ist(_now())
    response = await client.get(f"{URL}.csv", params={"recruiter": str(me.id)})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert f'recruiter-performance-{today.replace(day=1)}-to-{today}.csv' in response.headers["content-disposition"]
    assert "no-store" in response.headers["cache-control"]
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0][:4] == ["Recruiter", "Status", "Recruiter Leads", "Active Companies"]
    assert len(rows[0]) == 17
    assert rows[1][0] == me.full_name and rows[-1][0] == "Total"
    assert rows[1][rows[0].index("Candidates Sourced")] == "1"
    assert rows[1][rows[0].index("Selection %")] == "0.0"
    assert rows[1][rows[0].index("Average Closure Time (days)")] == ""  # no closures -> blank
    audit = await db.scalar(select(AuditLog).where(AuditLog.user_id == manager.id, AuditLog.action == "recruiter_performance.export"))
    assert audit is not None and audit.metadata_json["rows"] == 1 and audit.metadata_json["recruiter"] == str(me.id)


# --- performance: a fixed statement count -----------------------------------------------------------------------------------------------
async def _statements(db, user, recruiter_id=None) -> int:
    seen: list[str] = []
    engine = db.bind.sync_engine if hasattr(db.bind, "sync_engine") else db.bind
    listener = lambda *args: seen.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        await metrics.performance(db, user, recruiter_id, None, None, _now())
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(seen)


@pytest.mark.asyncio
async def test_the_performance_read_is_a_fixed_number_of_statements(db_session):
    manager = await make_pm(db_session)
    a = await make_recruiter(db_session, manager)
    empty = await _statements(db_session, manager)
    for person in (a, await make_recruiter(db_session, manager)):
        job = await _job(db_session, await _company(db_session, person), person)
        await _application(db_session, job, person)
    await db_session.commit()
    assert await _statements(db_session, manager) == empty == 2  # the team + one aggregate
    assert await _statements(db_session, manager, a.id) == 2  # the recruiter lookup + one aggregate
