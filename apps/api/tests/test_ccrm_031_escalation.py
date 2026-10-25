"""ccrm-031 (DEC-SCOPE-271, E1-E8): overdue counselor tasks and follow-ups past the threshold reach every active Overseas Admin once, in
one notice per counselor (E3/E5), and the admin's "Overdue by counselor" list (E7). The shared test database is never truncated: every
assertion is about rows the test made. Spec: docs/superpowers/specs/2026-10-25-ccrm-031-overdue-escalation-design.md."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import CounselorReminderLog, CounselorReminderRule, CounselorTask, LeadFollowUp, Notification
from app.services import counselor_reminders as svc
from app.services.bdm_travel import INDIA, india_today
from tests.agn001_helpers import login, mk_user, uniq
from tests.ccrm012_helpers import mk_lead

TITLE = "Overdue work escalated"
LIST_URL = "/api/v1/counselor/tasks/overdue-by-counselor"


def day(offset: int = 0) -> date:
    return india_today() + timedelta(days=offset)


async def run(db) -> dict:
    return await svc.send_counselor_reminders(db, now=datetime.now(UTC))


async def escalated(db, subject_id) -> int:
    stmt = select(func.count()).select_from(CounselorReminderLog).where(CounselorReminderLog.rule_key == "overdue_escalation", CounselorReminderLog.subject_id == subject_id)
    return await db.scalar(stmt)


async def notices(db, user, counselor) -> list[Notification]:
    rows = (await db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.title == TITLE))).all()
    return [n for n in rows if counselor.full_name in n.body]


async def set_rule(db, **values) -> None:
    row = await db.get(CounselorReminderRule, "overdue_escalation")
    for field, value in values.items():
        setattr(row, field, value)
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def default_rules(db_session):
    """Only the escalation rule runs here, at its E1 default -- the other rules have their own tests."""
    for key, rule in svc.RULES.items():
        row = await db_session.get(CounselorReminderRule, key)
        if row is None:
            row = CounselorReminderRule(rule_key=key, offset_days=rule.offset, notify_student=bool(rule.student))
            db_session.add(row)
        row.enabled, row.offset_days = key == "overdue_escalation", rule.offset
    await db_session.commit()
    yield
    for key in svc.RULES:
        (await db_session.get(CounselorReminderRule, key)).enabled = True
    await db_session.commit()


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name=f"Escalation Counselor {uniq()}")
    admin = await mk_user(db_session, role="overseas_admin", full_name=f"Escalation Admin {uniq()}")
    return {"counselor": counselor, "admin": admin}


async def mk_task(db, counselor, due: date, status: str = "open") -> CounselorTask:
    task = CounselorTask(title=f"Call back {uniq()}", due_on=due, priority="medium", status=status, counselor_user_id=counselor.id, created_by_user_id=counselor.id, updated_by_user_id=counselor.id)
    db.add(task)
    await db.commit()
    return task


async def mk_follow_up(db, counselor, due_day: date, status: str = "open") -> LeadFollowUp:
    lead = await mk_lead(db, counselor, status="follow_up")
    done = {"completed_at": datetime.now(UTC), "completed_by_user_id": counselor.id} if status == "done" else {}
    fu = LeadFollowUp(lead_id=lead.id, due_at=datetime.combine(due_day, time(11), INDIA), reason="counselor_call", status=status, created_by_user_id=counselor.id, **done)
    db.add(fu)
    await db.commit()
    return fu


# --- escalation (E2-E5) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overdue_task_and_follow_up_escalate_once_in_one_notice(db_session, world):
    c, admin = world["counselor"], world["admin"]
    task = await mk_task(db_session, c, day(-3))
    fu = await mk_follow_up(db_session, c, day(-5))
    counts = await run(db_session)
    assert await escalated(db_session, task.id) == 1 and await escalated(db_session, fu.id) == 1
    sent = await notices(db_session, admin, c)
    assert len(sent) == 1, [n.body for n in sent]
    assert sent[0].body == f"{c.full_name}: 1 task and 1 follow-up overdue by more than 2 days."
    assert sent[0].action_url == "/overseas/admin/counselor-tasks#overdue" and task.title not in sent[0].body
    assert counts["rules"]["overdue_escalation"] >= 2 and counts["failed"] == 0
    assert await notices(db_session, c, c) == []  # E4: the counselor is not told
    await run(db_session)  # E3: a re-run sends nothing new
    assert await escalated(db_session, task.id) == 1 and len(await notices(db_session, admin, c)) == 1


@pytest.mark.asyncio
async def test_inside_the_threshold_or_closed_never_escalates(db_session, world):
    c = world["counselor"]
    fresh = await mk_task(db_session, c, day(-2))  # overdue by exactly 2 days: not more than the threshold
    done = await mk_task(db_session, c, day(-9), status="done")
    cancelled = await mk_task(db_session, c, day(-9), status="cancelled")
    fu = await mk_follow_up(db_session, c, day(-2))
    closed_fu = await mk_follow_up(db_session, c, day(-9), status="done")
    await run(db_session)
    for item in (fresh, done, cancelled, fu, closed_fu):
        assert await escalated(db_session, item.id) == 0
    assert await notices(db_session, world["admin"], c) == []


@pytest.mark.asyncio
async def test_threshold_is_configurable_and_the_rule_can_be_switched_off(db_session, world):
    c = world["counselor"]
    task = await mk_task(db_session, c, day(-1))
    await set_rule(db_session, enabled=False, offset_days=0)
    await run(db_session)
    assert await escalated(db_session, task.id) == 0
    await set_rule(db_session, enabled=True)
    await run(db_session)
    assert await escalated(db_session, task.id) == 1
    assert (await notices(db_session, world["admin"], c))[0].body == f"{c.full_name}: 1 task overdue by more than 0 days."


@pytest.mark.asyncio
async def test_a_moved_due_date_escalates_again_and_old_items_are_not_capped(db_session, world):
    c = world["counselor"]
    task = await mk_task(db_session, c, day(-90))  # E2: no lookback
    await run(db_session)
    assert await escalated(db_session, task.id) == 1
    task.due_on = day(-4)
    await db_session.commit()
    await run(db_session)
    assert await escalated(db_session, task.id) == 2
    assert len(await notices(db_session, world["admin"], c)) == 2


@pytest.mark.asyncio
async def test_inactive_counselor_still_escalates(db_session, world):
    gone = await mk_user(db_session, role="counselor", full_name=f"Gone Counselor {uniq()}", active=False)
    task = await mk_task(db_session, gone, day(-6))
    await run(db_session)
    assert await escalated(db_session, task.id) == 1 and len(await notices(db_session, world["admin"], gone)) == 1


@pytest.mark.asyncio
async def test_no_active_overseas_admin_skips_without_logging(db_session, world, monkeypatch):
    async def nobody(db):
        return []

    monkeypatch.setattr(svc, "_escalation_admins", nobody)
    task = await mk_task(db_session, world["counselor"], day(-6))
    counts = await run(db_session)
    assert await escalated(db_session, task.id) == 0 and counts["skipped"] >= 1
    monkeypatch.undo()
    await run(db_session)  # escalates once an admin exists
    assert await escalated(db_session, task.id) == 1


@pytest.mark.asyncio
async def test_inactive_and_other_division_admins_are_not_told(db_session, world):
    old = await mk_user(db_session, role="overseas_admin", full_name="Old Admin", active=False)
    it_admin = await mk_user(db_session, role="overseas_admin", division="it", full_name="IT Admin")
    sa = await mk_user(db_session, role="super_admin", full_name="Super Admin")
    await mk_task(db_session, world["counselor"], day(-6))
    await run(db_session)
    for person in (old, it_admin, sa):
        assert await notices(db_session, person, world["counselor"]) == []


@pytest.mark.asyncio
async def test_rule_is_listed_and_configurable(client, db_session, world):
    await login(client, world["admin"].email, "overseas")
    url = "/api/v1/overseas-admin/reminder-rules"
    rule = next(r for r in (await client.get(url)).json()["rules"] if r["key"] == "overdue_escalation")
    assert rule["timing"] == "escalate" and rule["offset_days"] == 2 and rule["max_offset"] == 30 and rule["notify_student"] is None
    assert (await client.put(f"{url}/overdue_escalation", json={"enabled": True, "offset_days": 31})).status_code == 422
    assert (await client.put(f"{url}/overdue_escalation", json={"enabled": True, "offset_days": 2, "notify_student": True})).status_code == 422
    assert (await client.put(f"{url}/overdue_escalation", json={"enabled": True, "offset_days": 5})).json()["offset_days"] == 5


# --- the list (E7) ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overdue_by_counselor_list(client, db_session, world):
    behind, slightly = world["counselor"], await mk_user(db_session, role="counselor", full_name=f"Slightly Late {uniq()}")
    clean = await mk_user(db_session, role="counselor", full_name=f"On Time {uniq()}")
    await mk_task(db_session, behind, day(-10))
    await mk_task(db_session, behind, day(-1))
    await mk_follow_up(db_session, behind, day(-4))
    await mk_task(db_session, behind, day(-20), status="done")
    await mk_task(db_session, slightly, day(-1))
    await mk_task(db_session, clean, day(0))
    await login(client, world["admin"].email, "overseas")
    response = await client.get(LIST_URL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["threshold_days"] == 2 and body["enabled"] is True and body["today"] == day().isoformat()
    rows = {r["counselor"]["id"]: r for r in body["items"]}
    assert str(clean.id) not in rows
    expected = {"active": True, "overdue_tasks": 2, "overdue_follow_ups": 1, "past_threshold": 2, "oldest_due": day(-10).isoformat()}
    assert {k: rows[str(behind.id)][k] for k in expected} == expected
    assert rows[str(slightly.id)]["past_threshold"] == 0 and rows[str(slightly.id)]["overdue_tasks"] == 1
    ids = [r["counselor"]["id"] for r in body["items"]]
    assert ids.index(str(behind.id)) < ids.index(str(slightly.id))  # past the threshold first


@pytest.mark.asyncio
async def test_list_is_for_the_overseas_admin_and_super_admin_only(client, db_session, world):
    sa = await mk_user(db_session, role="super_admin", full_name="Super")
    client.cookies.clear()
    await login(client, sa.email, "overseas")
    assert (await client.get(LIST_URL)).status_code == 200
    for person in (world["counselor"], await mk_user(db_session, role="telecaller")):
        client.cookies.clear()
        await login(client, person.email, person.division)
        assert (await client.get(LIST_URL)).status_code == 403
