"""itc-016 (DEC-SCOPE-357) -- overdue marking and fee reminders: the daily sweep (AC1-AC5), the IT Admin's schedule (AC6) and the
installments with their reminder history on the itc-013 fee account (AC7). "Overdue" is derived (F1), never stored."""

import datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.models import AuditLog, FeeReminderLog, FeeReminderSetting, ItStudentCounselor, Notification, NotificationDelivery, Payment
from app.notifications.events import EVENTS
from app.services import fee_accounts, fee_reminders
from tests.bdm001_helpers import make_user
from tests.enh014_helpers import set_prefs
from tests.test_itc_013_fee_account import account_url, as_admin, enrolled
from tests.upc001_helpers import login

TODAY = datetime.date(2026, 11, 10)
SETTINGS = "/api/v1/admin/it/fee-reminder-settings"
MINE = "/api/v1/it/student/fee-accounts"


@pytest_asyncio.fixture(autouse=True)
async def default_schedule(db_session):
    """The schedule is one shared row: every test starts and ends on the defaults (no row)."""
    await db_session.execute(delete(FeeReminderSetting))
    await db_session.commit()
    yield
    await db_session.execute(delete(FeeReminderSetting))
    await db_session.commit()


async def run(today: datetime.date = TODAY) -> dict:
    """The sweep in its own session, as the beat task runs it (its rollbacks never expire the test's objects)."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await fee_reminders.sweep(db, today=today)


async def bill(db, due: datetime.date | None, fee: float = 20000, *, status: str = "pending", student=None):
    """An enrolled IT student whose one fee row is due on `due`."""
    student, enrollment = await enrolled(db, fee, student=student)
    payment = await db.scalar(select(Payment).where(Payment.reference_id == enrollment.id))
    payment.due_date, payment.status = due, status
    await db.commit()
    return student, enrollment, payment


async def logs(db, payment) -> list[tuple[str, int, datetime.date]]:
    rows = await db.execute(select(FeeReminderLog.kind, FeeReminderLog.offset_days, FeeReminderLog.reminder_date).where(FeeReminderLog.payment_id == payment.id).order_by(FeeReminderLog.created_at))
    return [tuple(r) for r in rows.all()]


async def notices(db, user, event_type: str | None = None) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id).execution_options(populate_existing=True)
    if event_type:
        stmt = stmt.where(Notification.event_type == event_type)
    return list((await db.scalars(stmt)).all())


async def channels(db, note) -> list[str]:
    return sorted((await db.scalars(select(NotificationDelivery.channel).where(NotificationDelivery.notification_id == note.id))).all())


# --- the sweep (AC1-AC5) --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_installment_due_in_three_days_gets_one_reminder_email(db_session):
    student, _, payment = await bill(db_session, TODAY + datetime.timedelta(days=3))
    await run()
    assert await logs(db_session, payment) == [("due_soon", 3, TODAY)]
    [note] = await notices(db_session, student)
    assert (note.event_type, note.entity_type, note.entity_id) == ("it.fee.payment_due", "payment", str(payment.id))
    assert await channels(db_session, note) == ["email"]  # no WhatsApp opt-in, no WhatsApp (the - scenario)


@pytest.mark.asyncio
async def test_a_second_run_the_same_day_sends_nothing_new(db_session):
    student, _, payment = await bill(db_session, TODAY + datetime.timedelta(days=3))
    await run()
    counts = await run()
    assert len(await logs(db_session, payment)) == 1 and len(await notices(db_session, student)) == 1
    assert counts["duplicate"] >= 1


@pytest.mark.asyncio
async def test_paid_installments_get_no_reminder(db_session):
    student, _, payment = await bill(db_session, TODAY - datetime.timedelta(days=1), status="paid")
    await run()
    assert await logs(db_session, payment) == [] and await notices(db_session, student) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [1, 7, 14])
async def test_overdue_days_remind_the_student_and_the_linked_counselor(db_session, days):
    student, _, payment = await bill(db_session, TODAY - datetime.timedelta(days=days))
    counselor = await make_user(db_session, "counselor", "it")
    db_session.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db_session.commit()
    await run()
    assert await logs(db_session, payment) == [("overdue", days, TODAY)]
    assert [n.event_type for n in await notices(db_session, student)] == ["it.fee.payment_overdue"]
    [staff] = await notices(db_session, counselor)
    assert (staff.event_type, staff.entity_id, staff.action_url) == ("it.fee.student_overdue", str(payment.id), f"/it/counselor/students/{student.id}/profile")


@pytest.mark.asyncio
async def test_other_days_and_undated_bills_get_nothing(db_session):
    quiet = [await bill(db_session, TODAY - datetime.timedelta(days=d)) for d in (2, 0)] + [await bill(db_session, TODAY + datetime.timedelta(days=2)), await bill(db_session, None)]
    await run()
    for student, _, payment in quiet:
        assert await logs(db_session, payment) == [] and await notices(db_session, student) == []


@pytest.mark.asyncio
async def test_a_whatsapp_opt_in_adds_whatsapp(db_session):
    student = await make_user(db_session, "it_student", "it")
    await set_prefs(db_session, student, whatsapp=True)
    await bill(db_session, TODAY - datetime.timedelta(days=7), student=student)
    await run()
    [note] = await notices(db_session, student)
    assert await channels(db_session, note) == ["email", "whatsapp"]


@pytest.mark.asyncio
async def test_a_deactivated_student_is_skipped(db_session):
    student = await make_user(db_session, "it_student", "it", active=False)
    _, _, payment = await bill(db_session, TODAY + datetime.timedelta(days=3), student=student)
    await run()
    assert await logs(db_session, payment) == []


def test_reminder_notices_carry_no_amounts():
    for key in ("it.fee.payment_due", "it.fee.payment_overdue", "it.fee.student_overdue"):
        event = EVENTS[key]
        assert event.entity_type == "payment" and "INR" not in event.body and not any(ch.isdigit() for ch in event.title + event.body)


@pytest.mark.asyncio
async def test_a_changed_schedule_is_followed_and_zero_switches_off(db_session):
    db_session.add(FeeReminderSetting(id=1, days_before=0, overdue_days=[2]))
    await db_session.commit()
    _, _, soon = await bill(db_session, TODAY + datetime.timedelta(days=3))
    _, _, late = await bill(db_session, TODAY - datetime.timedelta(days=2))
    _, _, week = await bill(db_session, TODAY - datetime.timedelta(days=7))
    await run()
    assert (await logs(db_session, soon), await logs(db_session, late), await logs(db_session, week)) == ([], [("overdue", 2, TODAY)], [])


@pytest.mark.asyncio
async def test_a_failed_reminder_sends_nothing_and_the_rest_continue(db_session, monkeypatch):
    first, _, broken = await bill(db_session, TODAY + datetime.timedelta(days=3))
    second, _, fine = await bill(db_session, TODAY + datetime.timedelta(days=3))
    real = fee_reminders.notify

    async def flaky(db, recipients, event_type, entity_id, **kw):
        if str(entity_id) == str(broken.id):
            raise RuntimeError("boom")
        return await real(db, recipients, event_type, entity_id, **kw)

    monkeypatch.setattr(fee_reminders, "notify", flaky)
    counts = await run()
    assert counts["failed"] >= 1
    assert await logs(db_session, broken) == [] and await notices(db_session, first) == []
    assert await logs(db_session, fine) == [("due_soon", 3, TODAY)] and len(await notices(db_session, second)) == 1


# --- the schedule (AC6) ---------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_schedule_defaults_and_the_it_admin_changes_it_audited(client, db_session):
    admin = await as_admin(client, db_session)
    got = await client.get(SETTINGS)
    assert got.status_code == 200 and got.json() == {"days_before": 3, "overdue_days": [1, 7, 14]}
    saved = await client.put(SETTINGS, json={"days_before": 5, "overdue_days": [10, 3, 3]})
    assert saved.status_code == 200 and saved.json() == {"days_before": 5, "overdue_days": [3, 10]}
    assert (await client.get(SETTINGS)).json() == {"days_before": 5, "overdue_days": [3, 10]}
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == admin.id, AuditLog.action == "it.fee_reminders.settings_update"))
    assert audit is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"days_before": 31, "overdue_days": []}, {"days_before": -1, "overdue_days": []}, {"days_before": 3, "overdue_days": [0]},
                                  {"days_before": 3, "overdue_days": [91]}, {"days_before": 3, "overdue_days": [1, 2, 3, 4, 5, 6, 7]}, {"overdue_days": [1]}])  # fmt: skip
async def test_bad_schedules_are_422(client, db_session, body):
    await as_admin(client, db_session)
    assert (await client.put(SETTINGS, json=body)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "trainer", "it_student", "accountant"])
async def test_only_the_it_admin_reads_or_changes_the_schedule(client, db_session, role):
    await login(client, await make_user(db_session, role, "it"))
    assert (await client.get(SETTINGS)).status_code == 403
    assert (await client.put(SETTINGS, json={"days_before": 1, "overdue_days": []})).status_code == 403


@pytest.mark.asyncio
async def test_an_overseas_admin_cannot_change_the_schedule(client, db_session):
    await login(client, await make_user(db_session, "it_admin", "overseas"))
    assert (await client.put(SETTINGS, json={"days_before": 1, "overdue_days": []})).status_code == 403


# --- installments and history on the fee account (AC7) -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_account_lists_installments_with_derived_overdue_and_history(client, db_session, monkeypatch):
    student, enrollment, late = await bill(db_session, TODAY - datetime.timedelta(days=1), 8000)
    later = Payment(user_id=student.id, division="it", reference_type="enrollment_fee", reference_id=enrollment.id, amount=12000, status="pending",
                    due_date=TODAY + datetime.timedelta(days=3), installment_no=2)  # fmt: skip
    db_session.add(later)
    await db_session.commit()
    await run()
    monkeypatch.setattr(fee_accounts, "india_today", lambda: TODAY)
    await login(client, student)
    [account] = (await client.get(MINE)).json()
    assert [(i["amount"], i["due_date"], i["status"], i["overdue"]) for i in account["installments"]] == [
        (8000.0, str(TODAY - datetime.timedelta(days=1)), "pending", True), (12000.0, str(TODAY + datetime.timedelta(days=3)), "pending", False),
    ]  # fmt: skip
    assert [i["reminders"] for i in account["installments"]] == [[{"kind": "overdue", "offset_days": 1, "sent_on": str(TODAY)}],
                                                                [{"kind": "due_soon", "offset_days": 3, "sent_on": str(TODAY)}]]  # fmt: skip
    assert account["installments"][1]["installment_no"] == 2
    await as_admin(client, db_session)
    staff = (await client.get(account_url(enrollment))).json()
    assert staff["installments"] == account["installments"]  # the IT Admin (payments.view) sees the same history


@pytest.mark.asyncio
async def test_a_paid_installment_is_never_overdue(client, db_session, monkeypatch):
    student, enrollment, _ = await bill(db_session, TODAY - datetime.timedelta(days=30), status="paid")
    monkeypatch.setattr(fee_accounts, "india_today", lambda: TODAY)
    await login(client, student)
    [account] = (await client.get(MINE)).json()
    assert [(i["status"], i["overdue"], i["reminders"]) for i in account["installments"]] == [("paid", False, [])]


@pytest.mark.asyncio
async def test_another_students_history_stays_hidden(client, db_session):
    _, enrollment, _ = await bill(db_session, TODAY)
    await login(client, await make_user(db_session, "it_student", "it"))
    assert (await client.get(account_url(enrollment))).status_code == 404


@pytest.mark.asyncio
async def test_installments_cost_a_fixed_number_of_queries(db_session):
    from sqlalchemy import event

    enrolments = [(await bill(db_session, TODAY))[1] for _ in range(3)]
    queries = []
    sync_engine = db_session.bind.sync_engine
    listener = lambda *_: queries.append(1)  # noqa: E731
    event.listen(sync_engine, "before_cursor_execute", listener)
    try:
        await fee_accounts.accounts(db_session, enrolments)
    finally:
        event.remove(sync_engine, "before_cursor_execute", listener)
    assert len(queries) == 3  # itc-018 pins the same count: the history rides the installments query


@pytest.mark.asyncio
async def test_reminder_counts_are_logged_without_personal_data(db_session, caplog):
    await bill(db_session, TODAY + datetime.timedelta(days=3))
    with caplog.at_level("INFO", logger="app.fee_reminders"):
        await run()
    [record] = [r for r in caplog.records if r.getMessage() == "itc016_fee_reminders_done"]
    assert set(record.extra_fields) == {"today", "sent", "counselor", "duplicate", "failed"}


@pytest.mark.asyncio
async def test_the_log_holds_one_row_per_installment_rule_and_day(db_session):
    _, _, payment = await bill(db_session, TODAY + datetime.timedelta(days=3))
    await run()
    await run()
    total = await db_session.scalar(select(func.count()).select_from(FeeReminderLog).where(FeeReminderLog.payment_id == payment.id))
    assert total == 1


def test_the_daily_job_runs_at_0830_ist():
    from app.worker import celery

    entry = celery.conf.beat_schedule["itc016-fee-reminders"]
    assert entry["task"] == "app.worker.send_fee_reminders_task"
    assert (entry["schedule"].hour, entry["schedule"].minute) == ({3}, {0})  # UTC 03:00 = 08:30 IST
