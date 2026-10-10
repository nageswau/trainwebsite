"""upc-015 (DEC-SCOPE-162, spec §2 AL1-AL11, §6 AC1-AC7) -- the partnership alerts beat: agreement expiry at 90/60/30/7 days, newly
delayed milestones and the overdue digest, each once per recipient (notifications.dedupe_key), in-app + email. Rows are dated 2034 so other
tests' rows (the database is shared and never truncated) stay out of the windows; every assertion is about this test's own users."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.models import Notification, NotificationDelivery, PartnershipTask, University, UniversityAgreement, UniversityDocument, UniversityMilestone, User
from app.services import partnership_alerts
from tests.upc003_helpers import catalogue_country, create, login, make_application, make_head, make_pm

IST = ZoneInfo("Asia/Kolkata")
D = date(2034, 6, 1)


def ist(day: date, hour: int = 9, minute: int = 30) -> datetime:
    return datetime.combine(day, time(hour, minute), IST).astimezone(UTC)


async def run(db, day: date = D, hour: int = 9, minute: int = 30) -> dict:
    return await partnership_alerts.send_partnership_alerts(db, now=ist(day, hour, minute))


async def team(db):
    head = await make_head(db)
    return head, await make_pm(db, head), await make_pm(db, head)


async def uni(client, db, head, primary: User | None = None, backup: User | None = None, **values) -> University:
    await login(client, head)
    made = await create(client, (await catalogue_country(db)).id)
    fields = {"primary_manager_user_id": primary.id if primary else None, "backup_manager_user_id": backup.id if backup else None} | values
    await db.execute(update(University).where(University.id == uuid.UUID(made["id"])).values(**fields))
    await db.commit()
    return await db.get(University, uuid.UUID(made["id"]))


async def agreement(db, u: University, head: User, expiry: date, status: str = "active") -> UniversityAgreement:
    signed = status in ("signed", "active", "renewed")
    doc = UniversityDocument(university_id=u.id, kind="mou", title=f"MoU {uuid.uuid4().hex[:8]}", shareable=False, created_by_user_id=head.id)
    db.add(doc)
    await db.flush()
    start = expiry - timedelta(days=365)
    row = UniversityAgreement(
        mou_number=f"T-{uuid.uuid4().hex[:10]}", university_id=u.id, agreement_type="mou", status=status, start_date=start, expiry_date=expiry,
        exclusivity="exclusive", document_id=doc.id, created_by_user_id=head.id,
        **({"edusphere_signatory_user_id": head.id, "edusphere_signed_on": start, "university_signatory_name": "Dr Rao", "university_signed_on": start} if signed else {}),
    )  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def milestone(db, u: University, head: User, kind: str, target: date, achieved: date | None = None) -> UniversityMilestone:
    row = UniversityMilestone(university_id=u.id, kind=kind, target_date=target, achieved_on=achieved, updated_by_user_id=head.id)
    db.add(row)
    await db.commit()
    return row


async def task(db, u: University, assignee: User, due: date, status: str = "open") -> PartnershipTask:
    row = PartnershipTask(university_id=u.id, kind="follow_up", title="Follow up on proposal", assignee_user_id=assignee.id, created_by_user_id=assignee.id,
                          due_on=due, status=status, source="manual", completed_at=ist(due) if status == "done" else None)  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def alerts(db, user: User, kind: str | None = None) -> list[Notification]:
    prefix = f"upc015:{kind}:" if kind else "upc015:"
    stmt = select(Notification).where(Notification.user_id == user.id, Notification.dedupe_key.like(f"{prefix}%")).order_by(Notification.created_at)
    return list((await db.scalars(stmt)).all())


# --- agreement expiry (§14) -------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac1_thirty_days_before_expiry_alerts_each_recipient_once_with_the_source_text(client, db_session):
    head, pm, backup = await team(db_session)
    u = await uni(client, db_session, head, pm, backup)
    a = await agreement(db_session, u, head, D + timedelta(days=30))
    await run(db_session)
    for user in (pm, backup, head):  # AL9: primary, backup and the primary's reporting head
        [note] = await alerts(db_session, user, "agreement_expiry")
        assert note.title == "Agreement expires in 30 days"
        assert note.body.startswith(f"⚠️ {u.name} partnership expires in 30 days. Renewal action required.")
        assert a.mou_number in note.body and "01 Jul 2034" in note.body
        assert note.action_url == f"/partnership/universities/{u.id}#uni-agreements"
        [delivery] = (await db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note.id))).all()
        assert delivery.channel == "email"  # AL10: in-app + email only


@pytest.mark.asyncio
async def test_ac2_rerunning_the_job_sends_nothing_new(client, db_session):
    head, pm, backup = await team(db_session)
    u = await uni(client, db_session, head, pm, backup)
    await agreement(db_session, u, head, D + timedelta(days=30))
    await run(db_session)
    await run(db_session)
    await run(db_session, hour=15)
    assert len(await alerts(db_session, pm)) == 1


@pytest.mark.asyncio
async def test_the_ninety_day_alert_then_the_sixty_day_alert(client, db_session):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    await agreement(db_session, u, head, D + timedelta(days=90))
    await run(db_session)
    await run(db_session, D + timedelta(days=1))
    await run(db_session, D + timedelta(days=30))
    assert [n.title for n in await alerts(db_session, pm)] == ["Agreement expires in 90 days", "Agreement expires in 60 days"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("expiry_in", "status"), [(-1, "active"), (0, "active"), (30, "draft"), (30, "approved"), (30, "renewed")])
async def test_expired_unsigned_and_renewed_agreements_raise_no_alert(client, db_session, expiry_in, status):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    await agreement(db_session, u, head, D + timedelta(days=expiry_in), status)
    await run(db_session)
    assert await alerts(db_session, pm) == []


@pytest.mark.asyncio
async def test_an_agreement_signed_inside_thirty_days_gets_only_the_thresholds_ahead(client, db_session):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    await agreement(db_session, u, head, D + timedelta(days=20), "signed")
    await run(db_session)
    await run(db_session, D + timedelta(days=13))
    assert [n.title for n in await alerts(db_session, pm)] == ["Agreement expires in 7 days"]


@pytest.mark.asyncio
async def test_nothing_is_sent_before_nine_in_the_morning_ist(client, db_session):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    await agreement(db_session, u, head, D + timedelta(days=30))
    await run(db_session, hour=8, minute=59)
    assert await alerts(db_session, pm) == []
    await run(db_session, hour=9, minute=0)
    assert len(await alerts(db_session, pm)) == 1


@pytest.mark.asyncio
async def test_inactive_recipients_and_inactive_universities_are_skipped(client, db_session):
    head = await make_head(db_session)
    gone, backup = await make_pm(db_session, head, active=False), await make_pm(db_session, head)
    u = await uni(client, db_session, head, gone, backup)
    await agreement(db_session, u, head, D + timedelta(days=30))
    other_pm = await make_pm(db_session, head)
    archived = await uni(client, db_session, head, other_pm, active=False)
    await agreement(db_session, archived, head, D + timedelta(days=30))
    await run(db_session)
    assert await alerts(db_session, gone) == []
    assert len(await alerts(db_session, backup)) == 1
    assert await alerts(db_session, other_pm) == []


@pytest.mark.asyncio
async def test_an_unowned_university_alerts_nobody(client, db_session):
    head = await make_head(db_session)
    u = await uni(client, db_session, head)
    await agreement(db_session, u, head, D + timedelta(days=30))
    counts = await run(db_session)
    assert counts["skipped"] >= 1
    assert await alerts(db_session, head) == []


# --- delayed milestones (§6, Q-11) -------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_milestone_delayed_since_yesterday_alerts_the_primary_and_backup_once(client, db_session):
    head, pm, backup = await team(db_session)
    u = await uni(client, db_session, head, pm, backup)
    await milestone(db_session, u, head, "presentation", D - timedelta(days=1))
    await run(db_session)
    await run(db_session)
    for user in (pm, backup):
        [note] = await alerts(db_session, user, "milestone_delayed")
        assert note.title == "Milestone delayed"
        assert note.body == f"{u.name}: the Presentation milestone was due on 31 May 2034 and is not complete."
        assert note.action_url == f"/partnership/universities/{u.id}#timeline-{u.id}-heading"
    assert await alerts(db_session, head) == []


@pytest.mark.asyncio
async def test_moving_a_delayed_target_rearms_the_alert(client, db_session):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    row = await milestone(db_session, u, head, "presentation", D - timedelta(days=1))
    await run(db_session)
    row.target_date = D + timedelta(days=2)
    await db_session.commit()
    await run(db_session, D + timedelta(days=4))
    assert len(await alerts(db_session, pm, "milestone_delayed")) == 2


@pytest.mark.asyncio
async def test_achieved_old_or_event_completed_milestones_raise_no_alert(client, db_session):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    await milestone(db_session, u, head, "presentation", D - timedelta(days=1), achieved=D - timedelta(days=2))  # done by hand
    await milestone(db_session, u, head, "documents", D - timedelta(days=8))  # delayed long ago: not "newly" (AL6)
    await milestone(db_session, u, head, "first_application", D - timedelta(days=1))
    await make_application(db_session, u.id)  # achieved by the event (MS4), the timeline's own rule
    await run(db_session)
    assert await alerts(db_session, pm) == []


# --- overdue digest (§20) ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_overdue_digest_goes_to_the_assignee_once_a_day(client, db_session):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    await task(db_session, u, pm, D - timedelta(days=2))
    await task(db_session, u, pm, D - timedelta(days=5))
    await task(db_session, u, pm, D - timedelta(days=9), status="done")
    await task(db_session, u, pm, D)  # due today: not overdue
    await run(db_session)
    await run(db_session)
    [note] = await alerts(db_session, pm, "overdue_digest")
    assert note.title == "Overdue follow-ups"
    assert note.body == "You have 2 overdue follow-ups or tasks. The oldest was due on 27 May 2034."
    assert note.action_url == "/partnership/tasks?band=overdue"
    await run(db_session, D + timedelta(days=1))
    assert len(await alerts(db_session, pm, "overdue_digest")) == 2


@pytest.mark.asyncio
async def test_a_single_overdue_item_reads_in_the_singular(client, db_session):
    head, pm, _ = await team(db_session)
    u = await uni(client, db_session, head, pm)
    await task(db_session, u, pm, D - timedelta(days=1))
    await run(db_session)
    [note] = await alerts(db_session, pm, "overdue_digest")
    assert note.body == "You have 1 overdue follow-up or task. It was due on 31 May 2034."


@pytest.mark.asyncio
async def test_an_inactive_assignee_gets_no_digest(client, db_session):
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    u = await uni(client, db_session, head, pm)
    await task(db_session, u, pm, D - timedelta(days=1))
    pm.active = False
    await db_session.commit()
    await run(db_session)
    assert await alerts(db_session, pm) == []


# --- wiring ------------------------------------------------------------------------------------------------------------------


def test_the_beat_runs_the_job_every_ist_hour():
    from celery.schedules import crontab

    from app.worker import celery

    entry = celery.conf.beat_schedule["upc015-alerts"]
    assert entry["task"] == "app.worker.send_partnership_alerts_task"
    assert entry["schedule"] == crontab(minute=30)  # UTC :30 = IST :00; the service waits for 09:00 IST (AL3)
    assert "app.worker.send_partnership_alerts_task" in celery.tasks
