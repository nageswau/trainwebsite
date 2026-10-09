"""upc-012 -- the worker side of a university email (spec §4; UC7, AC1): claim, send to the contact's address now with the manager's
reply-to, record, retry and the stale sweeper. SMTP is replaced by tel-014's recorder on `mailer._send_sync`; the shared database is never
truncated."""

import smtplib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import UniversityMessage
from app.notifications import university_email
from app.services import mailer
from tests.test_tel_014_delivery import Outbox
from tests.test_upc_012_comms import _setup, smtp_on  # noqa: F401 -- a fixture
from tests.upc003_helpers import login


@pytest.fixture
def outbox(monkeypatch):
    """Every message handed to SMTP; `outbox.fail(exc)` makes the next send raise instead."""
    sent, failures = Outbox(), []

    def fake_send(msg) -> None:
        if failures:
            raise failures.pop(0)
        sent.append(msg)

    monkeypatch.setattr(mailer, "_send_sync", fake_send)
    sent.fail = failures.append
    return sent


async def queued(client, db, *, status="queued", attempts=0, **contact_over):
    _, pm, _, uni, person = await _setup(client, db, **contact_over)
    message = UniversityMessage(
        university_id=uuid.UUID(uni["id"]),
        contact_id=uuid.UUID(person["id"]),
        sender_user_id=pm.id,
        channel="email",
        subject="Partnership proposal",
        body="Dear Priya",
        delivery_status=status,
        attempt_count=attempts,
        sent_at=datetime.now(UTC),
    )
    db.add(message)
    await db.commit()
    return message, person, pm


async def reread(db, message: UniversityMessage) -> UniversityMessage:
    await db.refresh(message)
    return message


@pytest.mark.asyncio
async def test_a_queued_email_is_sent_once_to_the_contact_with_the_managers_reply_to(client, db_session, smtp_on, outbox):  # noqa: F811
    message, person, pm = await queued(client, db_session)
    assert await university_email.deliver_university_email(message.id) == "sent"
    assert await university_email.deliver_university_email(message.id) is None  # the claim lets one delivery through
    assert len(outbox) == 1 and outbox[0]["To"] == person["email"] and outbox[0]["Subject"] == "Partnership proposal"
    assert outbox[0]["Reply-To"].addresses[0].addr_spec == pm.email and f"{pm.full_name} via EduSphere" in str(outbox[0]["From"])
    stored = await reread(db_session, message)
    assert (stored.delivery_status, stored.attempt_count) == ("sent", 1)


@pytest.mark.asyncio
async def test_a_transient_failure_retries_with_the_countdown(client, db_session, smtp_on, outbox, university_emails_enqueued):  # noqa: F811
    message, _, _ = await queued(client, db_session)
    outbox.fail(smtplib.SMTPServerDisconnected("gone"))
    assert await university_email.deliver_university_email(message.id) == "retrying"
    assert university_emails_enqueued == [(str(message.id), 60)]
    assert await university_email.deliver_university_email(message.id) == "sent" and (await reread(db_session, message)).attempt_count == 2


@pytest.mark.asyncio
async def test_a_permanent_failure_or_a_deleted_contact_fails_at_once(client, db_session, smtp_on, outbox, university_emails_enqueued):  # noqa: F811
    message, _, _ = await queued(client, db_session)
    outbox.fail(smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")}))
    assert await university_email.deliver_university_email(message.id) == "failed"
    orphan, person, pm = await queued(client, db_session)
    await login(client, pm)
    await db_session.execute(update(UniversityMessage).where(UniversityMessage.id == orphan.id).values(contact_id=None))  # UC2: contact deleted
    await db_session.commit()
    assert await university_email.deliver_university_email(orphan.id) == "failed"
    assert university_emails_enqueued == [] and (await reread(db_session, message)).delivery_status == "failed"


@pytest.mark.asyncio
async def test_logs_carry_no_address_subject_or_body(client, db_session, smtp_on, outbox, caplog, monkeypatch):  # noqa: F811
    monkeypatch.setattr(university_email.logger, "disabled", False)
    message, person, _ = await queued(client, db_session)
    with caplog.at_level("INFO"):
        await university_email.deliver_university_email(message.id)
    logged = " ".join(f"{r.getMessage()} {getattr(r, 'extra_fields', '')}" for r in caplog.records)
    assert str(message.id) in logged and person["email"] not in logged and "Dear Priya" not in logged and "Partnership proposal" not in logged


@pytest.mark.asyncio
async def test_the_sweeper_republishes_stale_queued_emails_and_fails_interrupted_ones(client, db_session, university_emails_enqueued):
    stale, _, _ = await queued(client, db_session)
    stuck, _, _ = await queued(client, db_session, status="sending", attempts=1)
    fresh, _, _ = await queued(client, db_session)
    old = datetime.now(UTC) - timedelta(hours=1)
    await db_session.execute(update(UniversityMessage).where(UniversityMessage.id.in_([stale.id, stuck.id])).values(updated_at=old))
    await db_session.commit()
    await university_email.sweep_stale_university_emails()
    assert (str(stale.id), 0) in university_emails_enqueued and str(fresh.id) not in {m for m, _ in university_emails_enqueued}
    assert (await reread(db_session, stuck)).delivery_status == "failed"
