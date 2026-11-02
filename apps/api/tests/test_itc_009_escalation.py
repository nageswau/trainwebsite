"""itc-009 (DEC-SCOPE-342) -- overdue follow-up escalation. Once a follow-up is overdue by the team's `escalate_after_hours`, the
telecaller's reporting manager (an inactive one: the division admins) or, for an IT counselor's follow-up, every active IT admin gets
one `it.followup.overdue` notice, once per follow-up (AC1); a completed follow-up never escalates (AC2) and 0 turns it off (AC3).
Rows are dated 2034 so other tests' rows (the database is shared and never truncated) stay outside the 24-hour guard window; every
assertion is about this test's own users."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.models import LeadFollowUp, Notification, TelSetting, User
from app.services import follow_up_escalations
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user
from tests.tel016_helpers import make_counselor
from tests.test_tel_020_alerts import follow_up, mk_lead
from tests.test_tel_020_settings import reset_settings

NOW = datetime(2034, 3, 15, 6, 0, tzinfo=UTC)
EVENT = "it.followup.overdue"


async def set_hours(db, team: str, hours: int) -> None:
    await db.execute(update(TelSetting).where(TelSetting.team == team).values(escalate_after_hours=hours))
    await db.commit()


@pytest_asyncio.fixture
async def world(db_session):
    await reset_settings(db_session)
    await set_hours(db_session, "it", 24)
    await set_hours(db_session, "overseas", 24)
    manager = await make_tl_manager(db_session)
    yield manager, await make_telecaller(db_session, manager)
    await reset_settings(db_session)


async def escalations(db, user: User) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user.id, Notification.event_type == EVENT)
    return list(await db.scalars(query.execution_options(populate_existing=True)))


async def run(db, now: datetime = NOW) -> dict:
    return await follow_up_escalations.escalate_overdue_follow_ups(db, now=now)


@pytest.mark.asyncio
async def test_overdue_past_the_threshold_escalates_to_the_manager_exactly_once(db_session, world):
    manager, tel = world
    fu = await follow_up(db_session, await mk_lead(db_session, tel), NOW - timedelta(hours=25))
    await run(db_session)
    await run(db_session, NOW + timedelta(minutes=15))  # a later beat run: no second notice
    notes = await escalations(db_session, manager)
    assert len(notes) == 1
    note = notes[0]
    assert (note.entity_type, note.entity_id, note.action_url) == ("lead_follow_up", str(fu.id), f"/telecaller/manager/leads/{fu.lead_id}")
    assert "9876543210" not in note.title + note.body  # the preview never carries the lead's phone
    row = await db_session.get(LeadFollowUp, fu.id, populate_existing=True)
    assert row.escalated_at is not None
    assert await escalations(db_session, tel) == []  # the owner is not the escalation's recipient


@pytest.mark.asyncio
async def test_inside_the_threshold_nothing_escalates(db_session, world):
    manager, tel = world
    await follow_up(db_session, await mk_lead(db_session, tel), NOW - timedelta(hours=23))
    await run(db_session)
    assert await escalations(db_session, manager) == []


@pytest.mark.asyncio
async def test_a_completed_follow_up_never_escalates(db_session, world):
    manager, tel = world
    await follow_up(db_session, await mk_lead(db_session, tel), NOW - timedelta(hours=30), status="done")
    await run(db_session)
    assert await escalations(db_session, manager) == []


@pytest.mark.asyncio
async def test_zero_hours_turns_escalation_off_for_that_team(db_session, world):
    manager, tel = world
    await set_hours(db_session, "it", 0)
    await follow_up(db_session, await mk_lead(db_session, tel), NOW - timedelta(hours=30))
    await run(db_session)
    assert await escalations(db_session, manager) == []


@pytest.mark.asyncio
async def test_a_nurture_lead_never_escalates(db_session, world):
    manager, tel = world
    await follow_up(db_session, await mk_lead(db_session, tel, status="nurture"), NOW - timedelta(hours=30))
    await run(db_session)
    assert await escalations(db_session, manager) == []


@pytest.mark.asyncio
async def test_a_follow_up_older_than_the_guard_window_is_not_escalated(db_session, world):
    manager, tel = world
    await follow_up(db_session, await mk_lead(db_session, tel), NOW - timedelta(hours=24 + 24 + 1))
    await run(db_session)
    assert await escalations(db_session, manager) == []


@pytest.mark.asyncio
async def test_an_inactive_manager_falls_back_to_the_division_admins(db_session, world):
    manager, tel = world
    admin = await make_user(db_session, "it_admin", "it")
    await db_session.execute(update(User).where(User.id == manager.id).values(active=False))
    await db_session.commit()
    fu = await follow_up(db_session, await mk_lead(db_session, tel), NOW - timedelta(hours=25))
    await run(db_session)
    assert await escalations(db_session, manager) == []
    notes = await escalations(db_session, admin)
    assert [(n.entity_id, n.action_url) for n in notes] == [(str(fu.id), None)]


@pytest.mark.asyncio
async def test_an_overseas_telecaller_follow_up_uses_the_overseas_threshold(db_session, world):
    manager, _ = world
    tel = await make_telecaller(db_session, manager, team="overseas")
    await set_hours(db_session, "it", 0)
    await follow_up(db_session, await mk_lead(db_session, tel, division="overseas"), NOW - timedelta(hours=25))
    await run(db_session)
    assert len(await escalations(db_session, manager)) == 1


@pytest.mark.asyncio
async def test_an_it_counselor_follow_up_escalates_to_the_it_admins(db_session, world):
    _, tel = world
    admin = await make_user(db_session, "it_admin", "it")
    counselor = await make_counselor(db_session, "it")
    lead = await mk_lead(db_session, tel, owner_id=counselor.id, status="counselling_scheduled")
    fu = LeadFollowUp(lead_id=lead.id, due_at=NOW - timedelta(hours=25), reason="fee_details", created_by_user_id=counselor.id)
    db_session.add(fu)
    await db_session.commit()
    await run(db_session)
    assert [n.entity_id for n in await escalations(db_session, admin)] == [str(fu.id)]


@pytest.mark.asyncio
async def test_an_overseas_counselor_follow_up_is_left_to_ccrm_031(db_session, world):
    _, tel = world
    admin = await make_user(db_session, "overseas_admin", "overseas")
    counselor = await make_counselor(db_session, "overseas")
    lead = await mk_lead(db_session, tel, division="overseas", owner_id=counselor.id)
    db_session.add(LeadFollowUp(lead_id=lead.id, due_at=NOW - timedelta(hours=25), reason="fee_details", created_by_user_id=counselor.id))
    await db_session.commit()
    await run(db_session)
    assert await escalations(db_session, admin) == []


@pytest.mark.asyncio
async def test_no_recipient_leaves_the_follow_up_unclaimed_for_a_later_run(db_session, world):
    manager, tel = world
    admins = list(await db_session.scalars(select(User.id).where(User.role == "overseas_admin", User.active.is_(True))))
    await db_session.execute(update(User).where(User.id.in_([manager.id, *admins])).values(active=False))
    await db_session.commit()
    overseas = await make_telecaller(db_session, manager, team="overseas")
    fu = await follow_up(db_session, await mk_lead(db_session, overseas, division="overseas"), NOW - timedelta(hours=25))
    try:
        counts = await run(db_session)
        assert counts["skipped"] >= 1
        assert (await db_session.get(LeadFollowUp, fu.id, populate_existing=True)).escalated_at is None
    finally:
        await db_session.execute(update(User).where(User.id.in_(admins)).values(active=True))
        await db_session.commit()


def test_beat_runs_the_escalation_job_every_fifteen_minutes():
    from app.worker import celery

    entry = celery.conf.beat_schedule["itc009-escalations"]
    assert (entry["task"], entry["schedule"]) == ("app.worker.escalate_overdue_follow_ups_task", 900.0)


@pytest.mark.asyncio
async def test_the_it_admin_portal_has_a_notifications_section(client, db_session):
    from tests.bdm017_helpers import as_user

    await as_user(client, await make_user(db_session, "it_admin", "it"))
    response = await client.get("/api/v1/portal/it/admin/notifications")
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Notifications"
