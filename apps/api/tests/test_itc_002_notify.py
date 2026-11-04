"""itc-002 (DEC-SCOPE-336): typed notifications with a record link, a preview-safe catalogue, the bulk `notify()` helper, the additive
GET /workflows/notifications fields and the first emitter (an IT student's payment receipt)."""

import importlib.util
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select

from app.models import Notification, NotificationDelivery
from app.notifications.events import COUNT, EVENTS, notify
from tests.enh014_helpers import make_user, set_prefs
from tests.upc001_helpers import as_role, login

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_itc_002_migration", VERSIONS / "0221_notification_event_type.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

PAID = "it.fee.payment_received"


async def _notices(db, user) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user.id))).all())


async def _channels(db, note) -> list[str]:
    return sorted((await db.scalars(select(NotificationDelivery.channel).where(NotificationDelivery.notification_id == note.id))).all())


# --- N1 migration and model ---


def test_migration_chains_after_0220():
    assert (_migration.revision, _migration.down_revision) == ("0221_notification_event_type", "0220_program_syllabus_image")


@pytest.mark.asyncio
async def test_columns_and_inbox_index_exist(db_session):
    conn = await db_session.connection()
    columns, indexes = await conn.run_sync(lambda s: ({c["name"]: c for c in inspect(s).get_columns("notifications")}, {i["name"]: i for i in inspect(s).get_indexes("notifications")}))
    for name in ("event_type", "entity_type", "entity_id"):
        assert columns[name]["nullable"], name
    assert indexes[_migration.INDEX]["column_names"] == ["user_id", "read", "created_at"]


# --- N2 catalogue ---


def test_catalogue_is_dotted_and_preview_safe():
    """AC4: a preview never carries an amount, score or note -- the catalogue text is the only text notify() can send."""
    assert EVENTS, "catalogue is empty"
    for key, event in EVENTS.items():
        assert re.fullmatch(r"[a-z]+(\.[a-z_]+){2}", key), key
        for text in (event.title, event.body.replace(COUNT, "", 1)):  # hrc-009 (DEC-SCOPE-390 R6): at most one whole-number count slot
            assert not re.search(r"\d|₹|\$|%|rs\.?\s|inr", text, re.IGNORECASE), (key, text)
            assert "{" not in text, (key, text)  # fixed text, no other interpolation slots
        assert len(event.title) <= 180


# --- N3 notify() ---


@pytest.mark.asyncio
async def test_notify_writes_a_typed_linked_row_and_queues_email(db_session, enqueued):
    user = await make_user(db_session, role="it_student", division="it")
    entity = uuid.uuid4()
    rows = await notify(db_session, [user], PAID, entity, action_url="/it/student/fees")
    await db_session.commit()
    [note] = await _notices(db_session, user)
    assert rows == [note]
    assert (note.event_type, note.entity_type, note.entity_id, note.action_url) == (PAID, "payment", str(entity), "/it/student/fees")
    assert (note.title, note.body) == (EVENTS[PAID].title, EVENTS[PAID].body)
    assert await _channels(db_session, note) == ["email"]
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_notify_respects_channel_consent(db_session, enqueued):
    """AC3 / negative case: no WhatsApp opt-in, no WhatsApp message; an SMS opt-in adds SMS only."""
    opted = await make_user(db_session, role="it_student", division="it", phone="9876543210")
    await set_prefs(db_session, opted, sms=True)
    plain = await make_user(db_session, role="it_student", division="it", phone="9876543211")
    await notify(db_session, [opted, plain], PAID, uuid.uuid4())
    await db_session.commit()
    [a], [b] = await _notices(db_session, opted), await _notices(db_session, plain)
    assert await _channels(db_session, a) == ["email", "sms"]
    assert await _channels(db_session, b) == ["email"]


@pytest.mark.asyncio
async def test_a_rollback_sends_nothing(db_session, enqueued):
    """AC2."""
    user = await make_user(db_session, role="it_student", division="it")
    await notify(db_session, [user], PAID, uuid.uuid4())
    await db_session.rollback()
    await db_session.commit()
    await db_session.refresh(user)  # the rollback expired it
    assert enqueued == []
    assert await _notices(db_session, user) == []


@pytest.mark.asyncio
async def test_duplicate_events_in_one_transaction_are_sent_once(db_session, enqueued):
    """Edge: dedupe per (recipient, event, entity) -- across calls and within one call -- until the transaction ends."""
    user = await make_user(db_session, role="it_student", division="it")
    entity = uuid.uuid4()
    await notify(db_session, [user, user], PAID, entity)
    assert await notify(db_session, [user], PAID, entity) == []
    await notify(db_session, [user], PAID, uuid.uuid4())  # another record is a separate event
    await db_session.commit()
    assert len(await _notices(db_session, user)) == 2
    await notify(db_session, [user], PAID, entity)  # a later transaction is a new event
    await db_session.commit()
    assert len(await _notices(db_session, user)) == 3


@pytest.mark.asyncio
async def test_a_rolled_back_dedupe_does_not_suppress_the_retry(db_session, enqueued):
    user = await make_user(db_session, role="it_student", division="it")
    entity = uuid.uuid4()
    await notify(db_session, [user], PAID, entity)
    await db_session.rollback()
    await db_session.refresh(user)  # the rollback expired it
    await notify(db_session, [user], PAID, entity)
    await db_session.commit()
    assert len(await _notices(db_session, user)) == 1


@pytest.mark.asyncio
async def test_deactivated_and_missing_recipients_are_skipped(db_session, enqueued):
    gone = await make_user(db_session, role="it_student", division="it", active=False)
    assert await notify(db_session, [gone, None], PAID, uuid.uuid4()) == []
    await db_session.commit()
    assert await _notices(db_session, gone) == [] and enqueued == []


@pytest.mark.asyncio
async def test_unknown_event_type_is_refused(db_session):
    user = await make_user(db_session, role="it_student", division="it")
    with pytest.raises(ValueError, match="Unknown notification event"):
        await notify(db_session, [user], "it.fee.made_up", uuid.uuid4())


@pytest.mark.asyncio
async def test_a_batch_fan_out_is_one_call(db_session, enqueued):
    students = [await make_user(db_session, role="it_student", division="it") for _ in range(40)]
    rows = await notify(db_session, students, "it.batch.changed", uuid.uuid4(), action_url="/it/student/course")
    await db_session.commit()
    assert len(rows) == 40 and len(enqueued) == 40
    ids = [s.id for s in students]
    assert await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id.in_(ids), Notification.event_type == "it.batch.changed")) == 40


# --- N4 API ---


@pytest.mark.asyncio
async def test_inbox_returns_the_new_fields_and_only_own_rows(client, db_session, enqueued):
    student = await make_user(db_session, role="it_student", division="it")
    other = await make_user(db_session, role="it_student", division="it")
    entity = uuid.uuid4()
    await notify(db_session, [student, other], PAID, entity, action_url="/it/student/fees")
    db_session.add(Notification(user_id=student.id, title="Legacy", body="Untyped", read=False))
    await db_session.commit()
    await login(client, student)
    body = (await client.get("/api/v1/workflows/notifications")).json()
    assert len(body) == 2
    typed = next(x for x in body if x["event_type"])
    assert (typed["event_type"], typed["entity_type"], typed["entity_id"], typed["action_url"]) == (PAID, "payment", str(entity), "/it/student/fees")
    legacy = next(x for x in body if not x["event_type"])
    assert (legacy["entity_type"], legacy["entity_id"]) == (None, None)


# --- N5 the payment-received emitter ---


async def _record_payment(client, db, student, status="paid"):
    await as_role(client, db, "it_admin", "it")
    response = await client.post("/api/v1/admin/payments", json={"user_id": str(student.id), "amount": 4999, "status": status, "reference_type": "service_fee"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_a_paid_payment_notifies_the_it_student(client, db_session, enqueued):
    """Positive case: a fee payment is recorded and the student gets an in-app "Payment received" with a link to their receipts."""
    student = await make_user(db_session, role="it_student", division="it")
    payment_id = await _record_payment(client, db_session, student)
    [note] = await _notices(db_session, student)
    assert (note.event_type, note.entity_type, note.entity_id, note.action_url) == (PAID, "payment", payment_id, "/it/student/fees")
    assert "4999" not in note.title + note.body
    assert await _channels(db_session, note) == ["email"]


@pytest.mark.asyncio
async def test_a_pending_payment_sends_nothing(client, db_session, enqueued):
    student = await make_user(db_session, role="it_student", division="it")
    await _record_payment(client, db_session, student, status="pending")
    assert await _notices(db_session, student) == []


@pytest.mark.asyncio
async def test_overseas_payments_are_unchanged(client, db_session, enqueued):
    student = await make_user(db_session, role="overseas_student", division="overseas")
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post("/api/v1/admin/payments", json={"user_id": str(student.id), "amount": 100, "status": "paid"})
    assert response.status_code == 201, response.text
    assert await _notices(db_session, student) == []


@pytest.mark.asyncio
async def test_an_existing_receipt_is_not_notified_again(db_session, enqueued):
    from app.api.payments import _ensure_receipt
    from app.models import Payment

    student = await make_user(db_session, role="it_student", division="it")
    payment = Payment(user_id=student.id, division="it", reference_type="service_fee", amount=10, currency="INR", provider="manual", status="paid", is_manual=True)
    db_session.add(payment)
    await db_session.flush()
    await _ensure_receipt(db_session, payment, student)
    await db_session.commit()
    await _ensure_receipt(db_session, payment, student)
    await db_session.commit()
    assert len(await _notices(db_session, student)) == 1


# --- N6 the IT student Notifications section ---


@pytest.mark.asyncio
async def test_it_student_has_a_notifications_section(client, db_session):
    student = await make_user(db_session, role="it_student", division="it")
    await login(client, student)
    response = await client.get("/api/v1/portal/it/student/notifications")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Notifications" and not body.get("locked") and body["rows"] == []
