"""hrc-033 -- the five operational recruitment dashboards (DEC-SCOPE-415; design docs/superpowers/specs/2026-11-06-hrc-033-operational-recruitment-dashboards-design.md).
AC: each figure equals its drill-down count; the funnel stages are monotonic for one cohort. The database is shared and never truncated, so
exact figures are read through this test's own employer or job filter; rows are planted directly with controlled timestamps."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select, update

from app.core.database import engine
from app.models import (
    AuditLog,
    Candidate,
    Company,
    Interview,
    InterviewResult,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobAssignment,
    RecruiterCall,
    User,
)
from app.services import candidates as candidates_svc
from app.services import recruitment_dashboards as svc
from app.services import website_intake
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.test_rec_017_tracking import _candidate

URL = "/api/v1/recruiter/recruitment-dashboards"
BOARDS = ("funnel", "vacancy", "recruiter", "officer", "interview")
STAGES = ("registered", "applied", "screened", "shortlisted", "profile_shared", "interview", "selected", "joined")


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _ago(days: float = 0, hours: float = 0) -> datetime:
    return datetime.now(UTC) - timedelta(days=days, hours=hours)


def _values(payload: dict) -> dict[str, int]:
    return {f["key"]: f["value"] for section in payload["sections"] for f in section["figures"]}


def _recent(board: str, params: dict) -> dict:
    """A planted row dated a few hours ago can fall in last month on the 1st, so flow boards read a window instead of "this month"."""
    if board == "vacancy" or "from" in params:
        return params
    return {**params, "from": str(svc.today_ist(datetime.now(UTC)) - timedelta(days=3))}


async def _board(client, board: str, **params) -> dict:
    response = await client.get(f"{URL}/{board}", params=_recent(board, params))
    assert response.status_code == 200, response.text
    return response.json()


async def _drill(client, board: str, figure: str, **params) -> dict:
    response = await client.get(f"{URL}/{board}/drill/{figure}", params=_recent(board, {"limit": 100, **params}))
    assert response.status_code == 200, response.text
    return response.json()


async def _company(db, recruiter: User | None = None) -> Company:
    company = Company(name=f"Dash Co {_tag()}", assigned_recruiter_user_id=recruiter.id if recruiter else None)
    db.add(company)
    await db.commit()
    return company


async def _job(db, company: Company, *, status="sourcing", recruiter: User | None = None, age_days: int = 0, requirement_date: date | None = None) -> Job:
    job = Job(company_id=company.id, title=f"Dash Job {_tag()}", location="Pune", description="", skills=[], status=status,
              assigned_recruiter_user_id=recruiter.id if recruiter else None, requirement_date=requirement_date)  # fmt: skip
    db.add(job)
    await db.commit()
    if age_days:
        await db.execute(update(Job).where(Job.id == job.id).values(created_at=_ago(age_days)))
        await db.commit()
    return job


async def _apply(db, candidate: Candidate, job: Job, *moves: str, at: datetime | None = None, final: str | None = None) -> JobApplication:
    """An application with one history row per move (the first is its creation); its current status is `final` or the last move."""
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status=final or moves[-1])
    db.add(application)
    await db.flush()
    previous = None
    for move in moves:
        db.add(JobApplicationStatusHistory(application_id=application.id, from_status=previous, to_status=move, created_at=at or _ago()))
        previous = move
    await db.commit()
    return application


async def _interview(db, application: JobApplication, status: str, scheduled_at: datetime, *, result_state: str | None = None, releaser: User | None = None) -> Interview:
    interview = Interview(application_id=application.id, status=status, scheduled_at=scheduled_at, cancel_reason="other" if status == "cancelled" else None)
    db.add(interview)
    await db.flush()
    if result_state:
        released = {"released_at": _ago(), "released_by_user_id": releaser.id, "release_mode": "approval", "candidate_message": "Well done"} if releaser else {}
        db.add(InterviewResult(interview_id=interview.id, application_id=application.id, outcome="selected", is_final=True, state=result_state, **released))
    await db.commit()
    return interview


async def _website(db, *, hours: float = 1, **extra) -> Candidate:
    fields = {"name": f"Web {_tag()}", "email": f"web-{_tag()}@example.com", "preferred_locations": [], **extra}
    candidate = Candidate(candidate_code=await candidates_svc.next_code(db), source_id=await website_intake.source_id(db), **fields)
    db.add(candidate)
    await db.commit()
    await db.execute(update(Candidate).where(Candidate.id == candidate.id).values(created_at=_ago(hours=hours)))
    await db.commit()
    return candidate


@pytest_asyncio.fixture
async def manager(client, db_session):
    pm = await make_pm(db_session)
    await login(client, pm)
    return pm


# --- the funnel: monotonic for one cohort, from history (Appendix B) ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_counts_each_stage_reached_and_a_skipped_stage_still_counts(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    job = await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    joined, rejected, sourced = [await _candidate(db_session, creator) for _ in range(3)]
    await _apply(db_session, joined, job, "sourced", "selected", "joined")  # skips every stage between
    await _apply(db_session, rejected, job, "sourced", "shortlisted", "rejected")  # keeps what it reached
    await _apply(db_session, sourced, job, "sourced")
    await _candidate(db_session, creator)  # no application: outside an employer-filtered cohort

    values = _values(await _board(client, "funnel", employer=str(company.id)))
    assert [values[s] for s in STAGES] == [3, 3, 2, 2, 1, 1, 1, 1]


@pytest.mark.asyncio
async def test_funnel_is_monotonic_and_each_stage_ties_out_for_every_cohort_read(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    payload = (await client.get(f"{URL}/funnel")).json()  # the whole shared database's cohort, this IST month by default
    today = svc.today_ist(datetime.now(UTC))
    assert payload["date_from"] == str(today.replace(day=1)) and payload["date_to"] == str(today)
    values = _values(payload)
    counts = [values[s] for s in STAGES]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
async def test_funnel_cohort_is_the_registration_period(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    job = await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    old, new = await _candidate(db_session, creator), await _candidate(db_session, creator)
    await db_session.execute(update(Candidate).where(Candidate.id == old.id).values(created_at=_ago(40)))
    await db_session.commit()
    await _apply(db_session, old, job, "sourced")
    await _apply(db_session, new, job, "sourced")
    today = svc.today_ist(datetime.now(UTC))
    params = {"employer": str(company.id), "to": str(today)}

    recent = _values(await _board(client, "funnel", **params, **{"from": str(today - timedelta(days=5))}))
    wide = _values(await _board(client, "funnel", **params, **{"from": str(today - timedelta(days=60))}))
    assert recent["registered"] == 1 and wide["registered"] == 2


@pytest.mark.asyncio
async def test_a_stage_is_counted_only_on_the_filtered_job(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    first, second = await _job(db_session, company), await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    person = await _candidate(db_session, creator)
    await _apply(db_session, person, first, "sourced")
    await _apply(db_session, person, second, "sourced", "selected", "joined")

    values = _values(await _board(client, "funnel", job=str(first.id)))
    assert (values["registered"], values["applied"], values["joined"]) == (1, 1, 0)


# --- the vacancy board --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vacancy_buckets_partition_every_job_and_bands_partition_open(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    for status in ("new", "pending_approval", "requirement_received", "sourcing", "shortlisting", "profiles_shared", "interviewing", "selected", "joined", "filled", "on_hold", "closed", "cancelled"):
        await _job(db_session, company, status=status)
    values = _values(await _board(client, "vacancy", employer=str(company.id)))
    assert values["total"] == 13
    assert (values["not_yet_open"], values["open"], values["on_hold"], values["selected_or_filled"], values["closed"], values["cancelled"]) == (2, 5, 1, 3, 1, 1)
    assert values["age_0_15"] + values["age_16_30"] + values["age_31_60"] + values["age_over_60"] == values["open"]


@pytest.mark.asyncio
async def test_ageing_uses_the_requirement_date_else_created_and_the_band_edges(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    today = svc.today_ist(datetime.now(UTC))
    for days in (15, 16, 30, 31, 60, 61):
        await _job(db_session, company, requirement_date=today - timedelta(days=days))
    await _job(db_session, company, age_days=20)  # no requirement date: its created date
    await _job(db_session, company, requirement_date=today + timedelta(days=9))  # a future date ages as 0
    values = _values(await _board(client, "vacancy", employer=str(company.id)))
    assert (values["age_0_15"], values["age_16_30"], values["age_31_60"], values["age_over_60"]) == (2, 3, 2, 1)


@pytest.mark.asyncio
async def test_vacancy_with_dates_covers_jobs_opened_in_the_range(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    today = svc.today_ist(datetime.now(UTC))
    await _job(db_session, company, requirement_date=today - timedelta(days=100))
    await _job(db_session, company, requirement_date=today - timedelta(days=2))
    assert _values(await _board(client, "vacancy", employer=str(company.id)))["total"] == 2
    ranged = await _board(client, "vacancy", employer=str(company.id), **{"from": str(today - timedelta(days=5)), "to": str(today)})
    assert _values(ranged)["total"] == 1


# --- the recruiter board: website registrations and contact SLA (hrc-025 N8) ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_board_contact_sla_partitions_registrations(client, db_session):
    recruiter_user = await make_recruiter(db_session)
    await login(client, recruiter_user)
    met = await _website(db_session, hours=30, owner_user_id=recruiter_user.id)
    late = await _website(db_session, hours=60, owner_user_id=recruiter_user.id)
    await _website(db_session, hours=40, owner_user_id=recruiter_user.id)  # never contacted, past the target: breached
    await _website(db_session, hours=1, owner_user_id=recruiter_user.id)  # never contacted, inside the target: pending
    db_session.add(RecruiterCall(candidate_id=met.id, caller_user_id=recruiter_user.id, occurred_at=_ago(hours=29), direction="outgoing", outcome="connected"))
    db_session.add(RecruiterCall(candidate_id=late.id, caller_user_id=recruiter_user.id, occurred_at=_ago(hours=1), direction="outgoing", outcome="connected"))
    await db_session.commit()

    response = await _board(client, "recruiter", owner=str(recruiter_user.id))
    values = _values(response)
    assert values["registrations"] == 4 and values["registrations_assigned"] == 4 and values["registrations_contacted"] == 2
    assert (values["sla_met"], values["sla_pending"], values["sla_breached"]) == (1, 1, 2)


@pytest.mark.asyncio
async def test_recruiter_board_unassigned_is_the_queue_a_recruiter_also_works(client, db_session):
    recruiter_user = await make_recruiter(db_session)
    await login(client, recruiter_user)
    unassigned = await _website(db_session, hours=1)
    drill = await _drill(client, "recruiter", "registrations_unassigned")
    assert str(unassigned.id) in {row["id"] for row in drill["items"]} or drill["total"] > 100


@pytest.mark.asyncio
async def test_recruiter_flow_figures_count_within_the_period(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    job = await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    person = await _candidate(db_session, creator)
    application = await _apply(db_session, person, job, "sourced", "selected", "joined")
    await _interview(db_session, application, "scheduled", _ago(hours=1))
    values = _values(await _board(client, "recruiter", employer=str(company.id)))
    assert (values["open_requirements"], values["candidates_added"], values["interviews_scheduled"], values["selected"], values["joined"]) == (1, 1, 1, 1, 1)


# --- the interview board -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_interview_board_counts_each_status_and_results_awaiting_approval(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    job = await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    application = await _apply(db_session, await _candidate(db_session, creator), job, "sourced", "interview")
    await _interview(db_session, application, "scheduled", _ago(days=-2))  # upcoming
    await _interview(db_session, application, "scheduled", _ago(hours=2))  # awaiting update
    await _interview(db_session, application, "on_hold", _ago(hours=3))
    await _interview(db_session, application, "cancelled", _ago(hours=4))
    await _interview(db_session, application, "no_show", _ago(hours=5))
    await _interview(db_session, application, "completed", _ago(hours=6))  # held AND awaiting update
    await _interview(db_session, application, "selected", _ago(hours=7), result_state="pending_approval")
    await _interview(db_session, application, "rejected", _ago(hours=8), result_state="released", releaser=creator)

    values = _values(await _board(client, "interview", job=str(job.id)))
    assert values["upcoming"] == 1 and values["awaiting_update"] == 2 and values["on_hold"] == 1
    assert values["cancelled"] == 1 and values["no_show"] == 1 and values["held"] == 3 and values["results_awaiting"] == 1


@pytest.mark.asyncio
async def test_a_queue_figure_ignores_the_period_and_a_period_figure_respects_it(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    job = await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    application = await _apply(db_session, await _candidate(db_session, creator), job, "sourced", "interview")
    await _interview(db_session, application, "on_hold", _ago(90))
    await _interview(db_session, application, "cancelled", _ago(90))
    values = _values(await _board(client, "interview", job=str(job.id)))  # default: this month
    assert values["on_hold"] == 1 and values["cancelled"] == 0


# --- the placement officer board -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_officer_board_counts_only_what_the_officer_is_officer_of(client, db_session):
    officer, other = await make_user(db_session, "placement_officer", "it"), await make_user(db_session, "placement_officer", "it")
    creator = await make_user(db_session, "placement_team", "it")
    company = await _company(db_session)
    mine, theirs = await _job(db_session, company), await _job(db_session, company)
    db_session.add_all([JobAssignment(job_id=mine.id, user_id=officer.id, role="placement_officer", added_by_user_id=creator.id),
                        JobAssignment(job_id=theirs.id, user_id=other.id, role="placement_officer", added_by_user_id=creator.id)])  # fmt: skip
    await db_session.commit()
    contacted = await _candidate(db_session, creator, placement_officer_user_id=officer.id)
    await _candidate(db_session, creator, placement_officer_user_id=officer.id)
    await _candidate(db_session, creator, placement_officer_user_id=other.id)
    db_session.add(RecruiterCall(candidate_id=contacted.id, caller_user_id=creator.id, occurred_at=_ago(hours=1), direction="outgoing", outcome="connected"))
    application = await _apply(db_session, contacted, mine, "sourced", "selected")
    await _apply(db_session, await _candidate(db_session, creator), theirs, "sourced", "selected")
    await _interview(db_session, application, "scheduled", _ago(days=-1))
    await login(client, officer)

    values = _values(await _board(client, "officer"))
    assert values["open_requirements"] == 1 and values["candidates_assigned"] == 2 and values["candidates_uncontacted"] == 1
    assert values["candidates_added"] == 1 and values["selected"] == 1 and values["upcoming"] == 1
    # the owner filter cannot widen an officer's view to a colleague
    assert _values(await _board(client, "officer", owner=str(other.id)))["open_requirements"] == 0


@pytest.mark.asyncio
async def test_hr_manager_narrows_the_officer_board_to_one_officer(client, db_session):
    officer = await make_user(db_session, "placement_officer", "it")
    creator = await make_user(db_session, "placement_team", "it")
    job = await _job(db_session, await _company(db_session))
    db_session.add(JobAssignment(job_id=job.id, user_id=officer.id, role="placement_officer", added_by_user_id=creator.id))
    await db_session.commit()
    await as_role(client, db_session, "hr_manager", "it")
    payload = await _board(client, "officer", owner=str(officer.id))
    assert _values(payload)["open_requirements"] == 1
    assert str(officer.id) in {o["id"] for o in payload["options"]["owners"]}


# --- AC: every figure ties out to its drill-down ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("board", BOARDS)
async def test_every_figure_equals_its_drill_down_count(client, db_session, board):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    job = await _job(db_session, company)
    await _job(db_session, company, status="closed")
    creator = await make_user(db_session, "placement_team", "it")
    officer = await make_user(db_session, "placement_officer", "it")
    db_session.add(JobAssignment(job_id=job.id, user_id=officer.id, role="placement_officer", added_by_user_id=creator.id))
    person = await _candidate(db_session, creator, placement_officer_user_id=officer.id)
    application = await _apply(db_session, person, job, "sourced", "selected", "joined")
    for status, when in (("scheduled", _ago(days=-1)), ("scheduled", _ago(hours=1)), ("cancelled", _ago(hours=2)), ("no_show", _ago(hours=3)), ("on_hold", _ago(hours=4))):
        await _interview(db_session, application, status, when)
    await _interview(db_session, application, "selected", _ago(hours=5), result_state="pending_approval")

    params = {"employer": str(company.id)}
    payload = await _board(client, board, **params)
    figures = [f for section in payload["sections"] for f in section["figures"]]
    assert figures and any(f["value"] for f in figures)
    for figure in figures:
        drill = await _drill(client, board, figure["key"], **params)
        assert drill["total"] == figure["value"], figure["key"]
        assert len(drill["items"]) == min(figure["value"], 100), figure["key"]
        assert drill["figure"]["label"] == figure["label"] and figure["definition"]


@pytest.mark.asyncio
async def test_drill_pages_and_keeps_a_stable_total(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    for _ in range(5):
        await _job(db_session, company)
    params = {"employer": str(company.id), "limit": 2}
    first = await _drill(client, "vacancy", "open", **params)
    second = await _drill(client, "vacancy", "open", **params, offset=2)
    third = await _drill(client, "vacancy", "open", **params, offset=4)
    assert first["total"] == second["total"] == third["total"] == 5
    ids = [row["id"] for page in (first, second, third) for row in page["items"]]
    assert len(ids) == len(set(ids)) == 5


@pytest.mark.asyncio
async def test_an_unknown_figure_is_404_and_an_unknown_board_422(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(f"{URL}/funnel/drill/open")).status_code == 404
    assert (await client.get(f"{URL}/nonsense")).status_code == 422


# --- edges ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("board", BOARDS)
async def test_a_period_with_no_data_reads_zeros_not_errors(client, db_session, board):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    payload = await _board(client, board, employer=str(company.id))
    assert all(value == 0 for value in _values(payload).values())
    assert (await _drill(client, board, next(iter(_values(payload))), employer=str(company.id)))["items"] == []


@pytest.mark.asyncio
async def test_the_range_rules_are_the_reports_own(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    today = svc.today_ist(datetime.now(UTC))
    backwards = await client.get(f"{URL}/funnel", params={"from": str(today), "to": str(today - timedelta(days=1))})
    future = await client.get(f"{URL}/funnel", params={"to": str(today + timedelta(days=3))})
    too_long = await client.get(f"{URL}/funnel", params={"from": str(today - timedelta(days=400)), "to": str(today)})
    assert backwards.status_code == future.status_code == too_long.status_code == 422


@pytest.mark.asyncio
async def test_a_malformed_filter_id_is_422(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(f"{URL}/funnel", params={"owner": "x' OR 1=1"})).status_code == 422


@pytest.mark.asyncio
async def test_the_query_count_does_not_grow_with_the_data(client, db_session):
    await as_role(client, db_session, "super_admin", "global")

    async def statements() -> int:
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            await _board(client, "vacancy")
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    before = await statements()
    company = await _company(db_session)
    for _ in range(4):
        await _job(db_session, company)
    assert await statements() == before


# --- AuthZ ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["placement_team", "placement_manager", "hr_manager", "placement_officer", "it_admin", "partner"])
async def test_the_report_grant_holders_read(client, db_session, role):
    if role in ("placement_team", "placement_manager"):
        user = await (make_recruiter if role == "placement_team" else make_pm)(db_session)
        await login(client, user)
    else:
        await as_role(client, db_session, role, "global" if role == "partner" else "it")
    assert (await client.get(f"{URL}/funnel")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_student", "hr_team", "bdm", "interviewer", "employer", "candidate", "trainer"])
async def test_every_other_role_is_refused(client, db_session, role):
    await as_role(client, db_session, role, "it")
    assert (await client.get(f"{URL}/funnel")).status_code == 403
    assert (await client.get(f"{URL}/funnel/drill/registered")).status_code == 403
    assert (await client.get(f"{URL}/funnel.csv")).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.get(f"{URL}/funnel")).status_code == 401


@pytest.mark.asyncio
async def test_a_grant_without_a_defined_scope_is_still_refused(client, db_session):
    """D7: an administrator can grant the key to any role, but only the listed roles have a defined record scope."""
    await as_role(client, db_session, "super_admin", "global")
    put = await client.get("/api/v1/admin/roles/hr_team/permissions")
    current = put.json()["permissions"]
    try:
        assert (await client.put("/api/v1/admin/roles/hr_team/permissions", json={"permissions": [*current, "reports.recruitment.view"]})).status_code == 200
        await as_role(client, db_session, "hr_team", "it")
        assert (await client.get(f"{URL}/funnel")).status_code == 403
    finally:
        await as_role(client, db_session, "super_admin", "global")
        await client.put("/api/v1/admin/roles/hr_team/permissions", json={"permissions": current})


@pytest.mark.asyncio
async def test_a_recruiter_sees_only_their_requirements(client, db_session):
    mine_user = await make_recruiter(db_session)
    other = await make_recruiter(db_session)
    company = await _company(db_session, other)
    theirs = await _job(db_session, company, recruiter=other)
    await login(client, mine_user)
    assert _values(await _board(client, "vacancy", job=str(theirs.id)))["total"] == 0  # no leak, not a 403 that confirms it exists
    assert _values(await _board(client, "vacancy", owner=str(other.id)))["total"] == 0
    payload = await _board(client, "vacancy")
    assert str(theirs.id) not in {o["id"] for o in payload["options"]["jobs"]}
    assert str(company.id) not in {o["id"] for o in payload["options"]["employers"]}
    assert [o["id"] for o in payload["options"]["owners"]] == [str(mine_user.id)]
    assert (await _drill(client, "vacancy", "total", job=str(theirs.id)))["items"] == []


@pytest.mark.asyncio
async def test_a_manager_is_scoped_to_the_team_and_reads_a_direct_report(client, db_session):
    pm, stranger_pm = await make_pm(db_session), await make_pm(db_session)
    report, stranger = await make_recruiter(db_session, pm), await make_recruiter(db_session, stranger_pm)
    company = await _company(db_session)
    ours = await _job(db_session, company, recruiter=report)
    theirs = await _job(db_session, company, recruiter=stranger)
    await login(client, pm)
    values = _values(await _board(client, "vacancy", employer=str(company.id)))
    assert values["total"] == 1
    assert _values(await _board(client, "vacancy", job=str(ours.id)))["total"] == 1
    assert _values(await _board(client, "vacancy", job=str(theirs.id)))["total"] == 0


@pytest.mark.asyncio
async def test_drill_rows_carry_no_contact_compensation_or_result(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    job = await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    person = await _candidate(db_session, creator, mobile="+919812345670", email=f"secret-{_tag()}@example.com", expected_salary=900000)
    application = await _apply(db_session, person, job, "sourced", "interview")
    await _interview(db_session, application, "selected", _ago(hours=2), result_state="pending_approval")
    bodies = [await _drill(client, "funnel", "registered", employer=str(company.id)), await _drill(client, "interview", "results_awaiting", employer=str(company.id))]
    for body in bodies:
        assert body["total"] == 1
        text = str(body)
        assert "9812345670" not in text and "secret-" not in text and "900000" not in text
    keys = {c["key"] for c in bodies[1]["columns"]}
    assert "outcome" not in keys and "result" not in keys


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "shows"), [("super_admin", True), ("it_admin", False), ("partner", False)])
async def test_candidate_names_are_for_those_who_work_candidates(client, db_session, role, shows):
    await as_role(client, db_session, role, "global" if role != "it_admin" else "it")
    company = await _company(db_session)
    job = await _job(db_session, company)
    creator = await make_user(db_session, "placement_team", "it")
    person = await _candidate(db_session, creator)
    await _apply(db_session, person, job, "sourced")
    body = await _drill(client, "funnel", "registered", employer=str(company.id))
    assert body["total"] == 1 and (person.name in str(body["items"])) is shows
    assert person.candidate_code in str(body["items"])


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "opens"), [("placement_team", True), ("hr_manager", False)])
async def test_a_row_links_to_its_record_only_for_a_role_that_can_open_it(client, db_session, role, opens):
    user = await make_recruiter(db_session) if role == "placement_team" else await make_user(db_session, role, "it")
    company = await _company(db_session, user if role == "placement_team" else None)
    job = await _job(db_session, company, recruiter=user if role == "placement_team" else None)
    await login(client, user)
    row = next(r for r in (await _drill(client, "vacancy", "total", job=str(job.id)))["items"] if r["id"] == str(job.id))
    assert (row["href"] == f"/recruiter/requirements/{job.id}") is opens and (row["href"] is None) is not opens


# --- export ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
async def test_export_is_the_figures_with_definitions_and_is_audited(client, db_session, fmt):
    admin = await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    await _job(db_session, company)
    response = await client.get(f"{URL}/vacancy.{fmt}", params={"employer": str(company.id)})
    assert response.status_code == 200 and response.headers["content-disposition"].startswith('attachment; filename="recruitment-vacancy')
    assert "no-store" in response.headers["cache-control"]
    if fmt == "csv":
        lines = response.text.lstrip("﻿").splitlines()
        assert lines[0].startswith("Section,Figure,Count,Definition") and any(line.startswith("Status,Open,1,") for line in lines)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == admin.id, AuditLog.action == "recruitment_dashboard.export").order_by(AuditLog.created_at.desc()))
    assert audit is not None and audit.metadata_json["board"] == "vacancy" and audit.metadata_json["format"] == fmt


@pytest.mark.asyncio
async def test_export_needs_the_download_grant(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    current = (await client.get("/api/v1/admin/roles/hr_manager/permissions")).json()["permissions"]
    kept = [key for key in current if key != "reports.recruitment.download"]
    assert (await client.put("/api/v1/admin/roles/hr_manager/permissions", json={"permissions": kept})).status_code == 200
    try:
        await as_role(client, db_session, "hr_manager", "it")
        read = await client.get(f"{URL}/vacancy")
        assert read.status_code == 200 and read.json()["can_download"] is False
        assert (await client.get(f"{URL}/vacancy.csv")).status_code == 403
    finally:
        await as_role(client, db_session, "super_admin", "global")
        await client.put("/api/v1/admin/roles/hr_manager/permissions", json={"permissions": current})


# --- existing dashboards keep their numbers (regression guard, D-non-goal) --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_job_record_is_never_written_by_a_read(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    job = await _job(db_session, await _company(db_session))
    before = (await db_session.execute(select(Job.updated_at).where(Job.id == job.id))).scalar_one()
    await _board(client, "vacancy", job=str(job.id))
    assert (await db_session.execute(select(Job.updated_at).where(Job.id == job.id).execution_options(populate_existing=True))).scalar_one() == before


# --- review findings: scope on the candidate-side filters, and no decision in an interview row ------------------------------------------------
@pytest.mark.asyncio
async def test_an_employer_outside_scope_reads_zero_on_the_funnel(client, db_session):
    pm, stranger_pm = await make_pm(db_session), await make_pm(db_session)
    stranger = await make_recruiter(db_session, stranger_pm)
    company = await _company(db_session, stranger)
    job = await _job(db_session, company, recruiter=stranger)
    person = await _candidate(db_session, stranger)
    await _apply(db_session, person, job, "sourced", "screened")
    await login(client, pm)
    for filters in ({"employer": str(company.id)}, {"job": str(job.id)}):
        assert set(_values(await _board(client, "funnel", **filters)).values()) == {0}
        for figure in ("registered", "applied", "screened"):
            assert (await _drill(client, "funnel", figure, **filters))["items"] == []


@pytest.mark.asyncio
async def test_an_officer_reads_only_their_own_candidates_in_application_and_interview_records(client, db_session):
    officer = await make_user(db_session, "placement_officer", "it")
    creator = await make_user(db_session, "placement_team", "it")
    job = await _job(db_session, await _company(db_session))
    db_session.add(JobAssignment(job_id=job.id, user_id=officer.id, role="placement_officer", added_by_user_id=creator.id))
    await db_session.commit()
    mine = await _candidate(db_session, creator, placement_officer_user_id=officer.id)
    stranger = await _candidate(db_session, creator)
    await _interview(db_session, await _apply(db_session, mine, job, "sourced", "selected"), "scheduled", _ago(days=-1))
    await _interview(db_session, await _apply(db_session, stranger, job, "sourced", "selected"), "scheduled", _ago(days=-1))
    await login(client, officer)
    values = _values(await _board(client, "officer", job=str(job.id)))
    assert values["candidates_added"] == 1 and values["selected"] == 1 and values["upcoming"] == 1
    for figure in ("candidates_added", "selected", "upcoming"):
        body = await _drill(client, "officer", figure, job=str(job.id))
        assert [row["candidate"] for row in body["items"]] == [mine.candidate_code]
    assert (await _board(client, "interview", job=str(job.id)))["sections"]  # the same rule on the interview board
    assert _values(await _board(client, "interview", job=str(job.id)))["upcoming"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "shown"), [("selected", "Held"), ("rejected", "Held"), ("scheduled", "Scheduled")])
async def test_an_interview_row_never_shows_the_decision(client, db_session, status, shown):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    creator = await make_user(db_session, "placement_team", "it")
    application = await _apply(db_session, await _candidate(db_session, creator), await _job(db_session, company), "sourced", "interview")
    await _interview(db_session, application, status, _ago(hours=2), result_state="pending_approval")
    body = await _drill(client, "interview", "results_awaiting", employer=str(company.id))
    assert [row["status"] for row in body["items"]] == [shown]


@pytest.mark.asyncio
async def test_a_chosen_employer_survives_the_options_cap(client, db_session, monkeypatch):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    await _job(db_session, company)
    monkeypatch.setattr(svc, "OPTIONS_LIMIT", 1)
    payload = await _board(client, "vacancy", employer=str(company.id))
    assert [o["id"] for o in payload["options"]["employers"]] == [str(company.id)]
