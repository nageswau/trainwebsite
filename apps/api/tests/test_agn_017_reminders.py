"""AGN-017 AC4-AC6 -- the daily job: deadline reminders at 3/1/0 days by IST date, one overdue-task digest per recipient per IST day,
never twice, a failure counted and never raised. The job scans the shared test database, so every assertion is about this test's own
agency; deadlines sit in 2031 to keep other tests' rows out of the windows."""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

from app.services import agent_notifications as notices_svc
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world, mk_application
from tests.agn016_helpers import due, mk_task
from tests.agn017_helpers import channels_of, deactivate, notices, set_org_status, titled

D = date(2031, 3, 10)
MORNING = datetime(2031, 3, 10, 2, 30, tzinfo=UTC)  # 08:00 IST on D


@pytest_asyncio.fixture
async def world(db_session):
    return await agency_world(db_session)


async def _run(db, now=MORNING):
    return await notices_svc.send_daily_reminders(db, now=now)


async def _app(db, world, **fields):
    return await mk_application(db, agent=world["master"], university=world["university"], record=fields.pop("record", world["record"]), **fields)


def _titles(items) -> list[str]:
    return sorted(n.title for n in items)


def test_beat_runs_the_reminders_daily_at_0800_ist_and_keeps_the_sweeper():
    from celery.schedules import crontab

    from app.worker import celery

    entry = celery.conf.beat_schedule["agn017-daily-reminders"]
    assert entry["task"] == "app.worker.send_daily_reminders_task"
    assert entry["schedule"] == crontab(hour=2, minute=30)  # the worker runs in UTC: 02:30 UTC is 08:00 IST
    assert celery.conf.beat_schedule["enh014-sweep-stale-deliveries"]["schedule"] == 300.0
    assert "app.worker.send_daily_reminders_task" in celery.tasks


@pytest.mark.asyncio
async def test_the_partial_deadline_indexes_are_usable_by_the_deadline_query(db_session):
    """Final review M1 (refuted by this plan): the inner join on agent_student_id is enough for Postgres to prove the indexes'
    `agent_student_id IS NOT NULL` predicate, so no extra WHERE clause is needed. Whether the deadline columns become index conditions is
    the planner's choice from table statistics (on this small database it filters instead)."""
    from sqlalchemy import text

    query = notices_svc.deadline_query(D, None)
    sql = str(query.compile(dialect=db_session.bind.dialect, compile_kwargs={"literal_binds": True}))
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(row[0] for row in (await db_session.execute(text(f"EXPLAIN {sql}"))).all())
    await db_session.rollback()
    assert "ix_overseas_applications_agent_application_deadline" in plan or "ix_overseas_applications_agent_offer_deadline" in plan, plan


@pytest.mark.parametrize(("days", "title"), [(3, "Deadline in 3 days"), (1, "Deadline tomorrow"), (0, "Deadline today")])
@pytest.mark.asyncio
async def test_an_application_deadline_in_a_window_reminds_the_assignee(db_session, world, days, title):
    await _app(db_session, world, application_deadline=D + timedelta(days=days))
    await _run(db_session)
    [item] = await notices(db_session, world["staff"]["user"])
    assert (item.title, item.action_url) == (title, "/overseas/agent/applications")
    assert item.body == f"{world['university'].name}: application deadline {(D + timedelta(days=days)):%d %b %Y}."
    assert item.dedupe_key and item.dedupe_key.startswith("agn017:deadline:")
    assert await channels_of(db_session, item) == ["email"]


@pytest.mark.asyncio
async def test_a_deadline_outside_the_windows_reminds_nobody(db_session, world):
    await _app(db_session, world, application_deadline=D + timedelta(days=2))
    await _app(db_session, world, application_deadline=D - timedelta(days=1))
    await _run(db_session)
    assert await notices(db_session, world["staff"]["user"]) == []


@pytest.mark.asyncio
async def test_from_the_offer_stage_only_the_offer_deadline_counts(db_session, world):
    await _app(db_session, world, status="offer", application_deadline=D, offer_deadline=D + timedelta(days=3))
    await _run(db_session)
    [item] = await notices(db_session, world["staff"]["user"])
    assert item.title == "Deadline in 3 days" and "offer deadline" in item.body


@pytest.mark.asyncio
async def test_before_the_offer_stage_both_deadlines_remind(db_session, world):
    await _app(db_session, world, application_deadline=D, offer_deadline=D + timedelta(days=1))
    await _run(db_session)
    assert _titles(await notices(db_session, world["staff"]["user"])) == ["Deadline today", "Deadline tomorrow"]


@pytest.mark.parametrize("status", ["withdrawn", "enrolled"])
@pytest.mark.asyncio
async def test_a_closed_application_reminds_nobody(db_session, world, status):
    await _app(db_session, world, status=status, application_deadline=D, offer_deadline=D)
    await _run(db_session)
    assert await notices(db_session, world["staff"]["user"]) == []


@pytest.mark.asyncio
async def test_an_archived_student_or_an_inactive_agency_is_never_reminded(db_session, world):
    archived = await mk_record(db_session, agent=world["master"], full_name="Archived", assigned_member=world["staff"]["member"], status="archived")
    await _app(db_session, world, record=archived, application_deadline=D)
    await mk_task(db_session, record=archived, author=world["master"], due_at=MORNING - timedelta(days=1))
    await _run(db_session)
    assert await notices(db_session, world["staff"]["user"]) == []
    await _app(db_session, world, application_deadline=D)
    await set_org_status(db_session, world["org"], "suspended")
    await _run(db_session)
    assert await notices(db_session, world["staff"]["user"]) == []
    assert await notices(db_session, world["master"]) == []


@pytest.mark.asyncio
async def test_a_deactivated_assignee_sends_the_reminder_to_the_masters(db_session, world):
    await _app(db_session, world, application_deadline=D)
    await deactivate(db_session, world["staff"]["member"])
    await _run(db_session)
    assert [n.title for n in await notices(db_session, world["master"])] == ["Deadline today"]


@pytest.mark.asyncio
async def test_a_second_run_the_same_day_sends_nothing_new(db_session, world):
    await _app(db_session, world, application_deadline=D)
    await mk_task(db_session, record=world["record"], author=world["master"], due_at=MORNING - timedelta(days=1))
    first = await _run(db_session)
    second = await _run(db_session, now=MORNING + timedelta(hours=5))
    assert first["created"] >= 2
    assert second["created"] == 0 and second["duplicate"] >= 2
    assert _titles(await notices(db_session, world["staff"]["user"])) == ["Deadline today", "Overdue tasks"]


@pytest.mark.asyncio
async def test_a_moved_deadline_is_reminded_again_for_its_new_date(db_session, world):
    app = await _app(db_session, world, application_deadline=D + timedelta(days=3))
    await _run(db_session)
    app.application_deadline = D + timedelta(days=1)
    await db_session.commit()
    await _run(db_session)
    assert _titles(await notices(db_session, world["staff"]["user"])) == ["Deadline in 3 days", "Deadline tomorrow"]


@pytest.mark.asyncio
async def test_the_day_is_the_india_date(db_session, world):
    await _app(db_session, world, application_deadline=D)
    await _run(db_session, now=datetime(2031, 3, 9, 18, 29, tzinfo=UTC))  # 23:59 IST on 9 March
    await _run(db_session, now=datetime(2031, 3, 9, 18, 31, tzinfo=UTC))  # 00:01 IST on 10 March
    assert _titles(await notices(db_session, world["staff"]["user"])) == ["Deadline today", "Deadline tomorrow"]


@pytest.mark.asyncio
async def test_overdue_tasks_become_one_digest_per_recipient(db_session, world):
    for _ in range(3):
        await mk_task(db_session, record=world["record"], author=world["master"], due_at=due(days=-2), title="Call rahul@example.com")
    await mk_task(db_session, record=world["record"], author=world["master"], due_at=due(days=-2), status="done")
    await mk_task(db_session, record=world["record"], author=world["master"], due_at=due(days=2))
    await _run(db_session, now=datetime.now(UTC))
    [item] = await notices(db_session, world["staff"]["user"])
    assert (item.title, item.body, item.action_url) == ("Overdue tasks", "You have 3 overdue tasks.", "/overseas/agent/tasks")
    assert await titled(db_session, world["master"], "Overdue tasks") == []


@pytest.mark.asyncio
async def test_one_failing_reminder_is_counted_and_the_rest_still_go(db_session, world, monkeypatch):
    await _app(db_session, world, application_deadline=D)
    await _app(db_session, world, application_deadline=D + timedelta(days=1))
    real = notices_svc.queue_deliveries
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("broker down")
        return await real(*args, **kwargs)

    monkeypatch.setattr(notices_svc, "queue_deliveries", flaky)
    counts = await _run(db_session)
    assert counts["failed"] == 1
    assert len(await notices(db_session, world["staff"]["user"])) == 1  # the failed one rolled back to its savepoint; the other stands
