"""upc-022 -- GET /partnership/dashboard (spec DB1-DB16; Appendix B D1-D14, §20 bands). Figures are asserted in a fresh manager's scope:
the test database is shared and never truncated, so a head's (team + unowned) or super_admin's totals include other tests' rows. The month
figures are read through the service for a fixed past IST month (March 2025), with every event dated there by hand."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, update

from app.core.database import engine
from app.models import (
    PartnershipTask,
    University,
    UniversityAgreement,
    UniversityAgreementEvent,
    UniversityMeeting,
    UniversityStageHistory,
    UniversityVisit,
    UniversityVisitEvent,
)
from app.services.bdm_appointments import IST
from app.services.partnership_metrics import dashboard_figures, scope_filter
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url

DASHBOARD = "/api/v1/partnership/dashboard"
TODAY = date(2025, 3, 15)
IN_MARCH = datetime(2025, 3, 10, 6, tzinfo=UTC)
FEB = datetime(2025, 2, 10, 6, tzinfo=UTC)
MARCH_FIRST_IST = datetime(2025, 3, 1, 0, 0, tzinfo=IST)  # the first instant of the month
FEB_LAST_IST = datetime(2025, 2, 28, 23, 59, tzinfo=IST)  # the last minute before it


async def _university(client, db, head, manager=None, **values) -> University:
    await login(client, head)
    made = await create(client, (await catalogue_country(db)).id)
    if manager is not None:
        response = await client.post(url(made["id"], "assign"), json={"primary_manager_user_id": str(manager.id)})
        assert response.status_code == 200, response.text
    if values:
        await db.execute(update(University).where(University.id == uuid.UUID(made["id"])).values(**values))
        await db.commit()
    return await db.get(University, uuid.UUID(made["id"]))


def _move(db, uni, to_stage: str, when: datetime, from_stage: str = "target_university") -> None:
    db.add(UniversityStageHistory(university_id=uni.id, kind="move", from_stage=from_stage, to_stage=to_stage, actor_user_id=uni.primary_manager_user_id, created_at=when))


def _meeting(db, uni, actor, completed_at: datetime | None) -> None:
    db.add(
        UniversityMeeting(
            code=f"T-{uuid.uuid4().hex[:10]}", university_id=uni.id, meeting_type="introduction", starts_at=completed_at or IN_MARCH, mode="online",
            responsible_user_id=actor.id, created_by_user_id=actor.id, status="completed" if completed_at else "scheduled", completed_at=completed_at,
            completed_by_user_id=actor.id if completed_at else None,
        )
    )  # fmt: skip


async def _visit(db, uni, actor, completed_at: datetime | None) -> None:
    visit = UniversityVisit(
        code=f"T-{uuid.uuid4().hex[:10]}", university_id=uni.id, city="London", purpose="Partnership review", lead_user_id=actor.id,
        created_by_user_id=actor.id, proposed_date=TODAY, status="visit_completed" if completed_at else "approved",
    )  # fmt: skip
    db.add(visit)
    await db.flush()
    if completed_at:
        db.add(UniversityVisitEvent(visit_id=visit.id, action="complete", from_status="travel_booked", to_status="visit_completed", actor_user_id=actor.id, created_at=completed_at))


async def _agreement(db, uni, actor, status: str, signed_at: datetime | None = None) -> None:
    a = UniversityAgreement(
        mou_number=f"T-{uuid.uuid4().hex[:10]}", university_id=uni.id, agreement_type="mou", status=status, start_date=date(2025, 1, 1),
        expiry_date=date(2027, 1, 1), exclusivity="exclusive", created_by_user_id=actor.id,
    )  # fmt: skip
    db.add(a)
    await db.flush()
    if signed_at:
        db.add(UniversityAgreementEvent(agreement_id=a.id, kind="status", from_status="approved", to_status="signed", actor_user_id=actor.id, created_at=signed_at))


def _task(db, uni, assignee, due_on: date, status: str = "open") -> None:
    done = datetime.now(UTC) if status == "done" else None
    db.add(PartnershipTask(university_id=uni.id, kind="follow_up", title="Follow up on proposal", assignee_user_id=assignee.id, created_by_user_id=assignee.id,
                           due_on=due_on, status=status, source="manual", completed_at=done))  # fmt: skip


async def _figures(db, user, today: date = TODAY) -> dict:
    return await dashboard_figures(db, user, frozenset(), today)


# --- access (DB15) ---


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(DASHBOARD)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("overseas_admin", "overseas"), ("bdm", "overseas"), ("agent", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(DASHBOARD)).status_code == 403


@pytest.mark.asyncio
async def test_a_manager_without_a_profile_is_refused(client, db_session):
    await login(client, await make_user(db_session, "partnership_manager", "overseas"))
    assert (await client.get(DASHBOARD)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partnership_head", "super_admin"])
async def test_head_and_super_admin_read_it(client, db_session, role):
    if role == "partnership_head":
        await login(client, await make_head(db_session))
    else:
        await as_role(client, db_session, "super_admin", "global")
    body = (await client.get(DASHBOARD)).json()
    assert set(body) == {"today", "month", "overview", "this_month", "followups"}


# --- the figures (D1-D14) ---


@pytest.mark.asyncio
async def test_a_new_manager_sees_zero_everywhere(client, db_session):
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    await login(client, manager)
    response = await client.get(DASHBOARD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["overview"].values()) == {0} and set(body["followups"].values()) == {0}
    assert body["this_month"] == {k: 0 for k in body["this_month"]} and body["this_month"]["expected_weighted"] == 0
    today = date.fromisoformat(body["today"])
    assert body["month"]["first"] == today.replace(day=1).isoformat()


@pytest.mark.asyncio
async def test_overview_groups_lost_inactive_and_at_risk(client, db_session):
    """D1-D5 (DB4-DB6): total = partners + in progress + targets + lost; inactive universities are not counted at all."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    await _university(client, db_session, head, manager)  # target_university -> G3
    await _university(client, db_session, head, manager, stage="interested", relationship_strength="at_risk")  # G2, at risk
    await _university(client, db_session, head, manager, stage="agreement_signed")  # G2 (PS3)
    await _university(client, db_session, head, manager, stage="active_partner", relationship_strength="strong")  # G1
    await _university(client, db_session, head, manager, stage="proposal_sent", lost_at=datetime.now(UTC), lost_reason="Closed")  # lost
    await _university(client, db_session, head, manager, stage="active_partner", active=False)  # not counted
    figures = await _figures(db_session, manager)
    assert figures["overview"] == {"total": 5, "partners": 1, "in_progress": 2, "targets": 1, "at_risk": 1, "lost": 1}


@pytest.mark.asyncio
async def test_month_figures_count_this_months_events_only(client, db_session):
    """D6-D12 (DB7-DB12) for March 2025: February events and unfinished items are not counted; one university entering a stage twice
    counts once."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    a = await _university(client, db_session, head, manager)
    b = await _university(client, db_session, head, manager)
    old = await _university(client, db_session, head, manager)
    _move(db_session, a, "initial_contact", IN_MARCH)  # D6
    _move(db_session, a, "proposal_sent", IN_MARCH, "initial_contact")  # D9
    _move(db_session, a, "proposal_sent", IN_MARCH + timedelta(days=1), "commercial_discussion")  # re-entry: still one university
    _move(db_session, b, "proposal_sent", IN_MARCH)  # D6 (later than contact) + D9
    _move(db_session, b, "partner_activated", IN_MARCH, "agreement_signed")  # D12
    _move(db_session, old, "initial_contact", FEB)  # first contact in February: not new this month
    _move(db_session, old, "interested", IN_MARCH, "initial_contact")
    _meeting(db_session, a, manager, IN_MARCH)  # D7
    _meeting(db_session, a, manager, FEB)
    _meeting(db_session, b, manager, None)
    await _visit(db_session, a, manager, IN_MARCH)  # D8
    await _visit(db_session, b, manager, FEB)
    await _visit(db_session, b, manager, None)
    await _agreement(db_session, a, manager, "sent")  # D10
    await _agreement(db_session, a, manager, "under_review")  # D10
    await _agreement(db_session, b, manager, "negotiation")  # D10
    await _agreement(db_session, b, manager, "draft")
    await _agreement(db_session, b, manager, "approved", IN_MARCH)  # D11 (the event counts; a signed row needs a document)
    await _agreement(db_session, old, manager, "approved", FEB)
    await db_session.commit()
    month = (await _figures(db_session, manager))["this_month"]
    assert month == {"contacted": 2, "meetings": 1, "visits": 1, "proposals": 2, "mous_negotiating": 3, "mous_signed": 1, "activated": 1}


@pytest.mark.asyncio
async def test_month_boundary_is_ist(client, db_session):
    """Edge case: 00:00 IST on the 1st is this month; 23:59 IST on the last day of February is not."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    inside = await _university(client, db_session, head, manager)
    outside = await _university(client, db_session, head, manager)
    _move(db_session, inside, "proposal_sent", MARCH_FIRST_IST)
    _move(db_session, outside, "proposal_sent", FEB_LAST_IST)
    _meeting(db_session, inside, manager, MARCH_FIRST_IST)
    _meeting(db_session, outside, manager, FEB_LAST_IST)
    await db_session.commit()
    month = (await _figures(db_session, manager))["this_month"]
    assert (month["proposals"], month["contacted"], month["meetings"]) == (1, 1, 1)
    assert (await _figures(db_session, manager, date(2025, 2, 28)))["this_month"]["proposals"] == 1  # February sees only its own


@pytest.mark.asyncio
async def test_followup_bands_are_ist_days_for_open_tasks(client, db_session):
    """§20 bands and D14 (DB14): open tasks only; a manager counts their own."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    uni = await _university(client, db_session, head, manager)
    for due in (TODAY - timedelta(days=3), TODAY - timedelta(days=1), TODAY, TODAY + timedelta(days=1), TODAY + timedelta(days=2), TODAY + timedelta(days=30)):
        _task(db_session, uni, manager, due)
    _task(db_session, uni, manager, TODAY - timedelta(days=5), status="done")
    _task(db_session, uni, head, TODAY - timedelta(days=5))  # the head's own: not the manager's
    await db_session.commit()
    assert (await _figures(db_session, manager))["followups"] == {"overdue": 2, "today": 1, "tomorrow": 1, "upcoming": 2}


@pytest.mark.asyncio
async def test_scope_manager_sees_own_head_sees_team(client, db_session):
    """DB1 / DB14 (AC): a manager sees universities they own (primary or backup); the head their team's and unowned ones, not another
    head's; the head's bands cover their own and their reports' tasks."""
    head, other_head = await make_head(db_session), await make_head(db_session)
    manager, colleague, stranger = await make_pm(db_session, head), await make_pm(db_session, head), await make_pm(db_session, other_head)
    await _university(client, db_session, head, manager, relationship_strength="at_risk")
    theirs = await _university(client, db_session, head, colleague, relationship_strength="at_risk")
    await _university(client, db_session, head, colleague, backup_manager_user_id=manager.id, relationship_strength="at_risk")
    hidden = await _university(client, db_session, other_head, stranger, relationship_strength="at_risk")
    _task(db_session, theirs, colleague, TODAY - timedelta(days=1))
    _task(db_session, theirs, head, TODAY - timedelta(days=1))
    _task(db_session, hidden, stranger, TODAY - timedelta(days=1))
    await db_session.commit()
    mine = await _figures(db_session, manager)
    assert mine["overview"]["at_risk"] == 2 and mine["followups"]["overdue"] == 0
    team = frozenset({manager.id, colleague.id})
    head_view = await dashboard_figures(db_session, head, team, TODAY)
    assert head_view["followups"]["overdue"] == 2  # own + colleague's, not the stranger's
    assert head_view["overview"]["at_risk"] >= 3  # the team's three (+ unowned rows other tests left)
    await db_session.execute(update(University).where(University.id == hidden.id).values(relationship_strength="good"))
    await db_session.commit()
    assert (await dashboard_figures(db_session, head, team, TODAY))["overview"]["at_risk"] == head_view["overview"]["at_risk"]  # another head's: unseen
    assert len(scope_filter(head, team)) == 1  # the head's scope is a filter, never "everything"
    await db_session.execute(update(University).where(University.id == hidden.id).values(relationship_strength="at_risk"))
    await db_session.commit()
    stranger_view = await _figures(db_session, stranger)
    assert stranger_view["overview"]["at_risk"] == 1


@pytest.mark.asyncio
async def test_expected_figure_equals_the_expected_page(client, db_session):
    """D13 (DB13) is upc-023's E1: the same count and weighted figure as /partnership/expected's this-month window."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    today = datetime.now(IST).date()
    for stage in ("interested", "meeting_completed"):  # 40% + 60%
        await _university(client, db_session, head, manager, stage=stage, expected_agreement_date=today)
    await _university(client, db_session, head, manager, stage="agreement_signed", expected_agreement_date=today)  # signed: not expected
    await login(client, manager)
    body = (await client.get(DASHBOARD)).json()
    expected = (await client.get("/api/v1/partnership/expected")).json()
    this_month = next(w for w in expected["windows"] if w["key"] == "this_month")
    assert (body["this_month"]["expected_count"], body["this_month"]["expected_weighted"]) == (this_month["count"], this_month["weighted"]) == (2, 1.0)


@pytest.mark.asyncio
async def test_a_fixed_number_of_statements_whatever_the_data(client, db_session):
    """Performance: no N+1 -- adding universities, events and tasks does not add statements."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)

    async def statements() -> int:
        await login(client, manager)
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            assert (await client.get(DASHBOARD)).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    small = await statements()
    for _ in range(3):
        uni = await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=datetime.now(IST).date())
        _meeting(db_session, uni, manager, datetime.now(UTC))
        _task(db_session, uni, manager, datetime.now(IST).date())
    await db_session.commit()
    assert await statements() == small
