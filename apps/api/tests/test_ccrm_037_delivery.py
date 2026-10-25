"""ccrm-037 -- the worker side of a counselor's email to a student (DEC-SCOPE-271 MT6): claim, send to the student's account email with the
counselor's reply-to, record, retry and the stale sweeper. SMTP is replaced by tel-014's recorder on `mailer._send_sync`; the shared database
is never truncated."""

import smtplib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import StudentMessage
from app.notifications import student_email
from app.services import mailer
from tests.agn001_helpers import mk_user
from tests.test_bdm_012_email import smtp_on  # noqa: F401 -- a fixture
from tests.test_tel_014_delivery import Outbox


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


async def queued(db, *, status="queued", attempts=0, direction="outbound"):
    counselor = await mk_user(db, role="counselor", full_name="Nora Counselor")
    student = await mk_user(db, role="overseas_student", full_name="Priya Student")
    message = StudentMessage(
        student_user_id=student.id, sender_user_id=counselor.id, direction=direction, channel="email", subject="Your offer", body="Dear Priya",
        delivery_status=status if direction == "outbound" else None, attempt_count=attempts, sent_at=datetime.now(UTC),
    )  # fmt: skip
    db.add(message)
    await db.commit()
    return message, student, counselor


async def reread(db, message: StudentMessage) -> StudentMessage:
    await db.refresh(message)
    return message


@pytest.mark.asyncio
async def test_a_queued_email_is_sent_once_to_the_student_with_the_counselors_reply_to(db_session, smtp_on, outbox):  # noqa: F811
    message, student, counselor = await queued(db_session)
    assert await student_email.deliver_student_email(message.id) == "sent"
    assert await student_email.deliver_student_email(message.id) is None  # the claim lets one delivery through
    assert len(outbox) == 1 and outbox[0]["To"] == student.email and outbox[0]["Subject"] == "Your offer"
    assert outbox[0]["Reply-To"].addresses[0].addr_spec == counselor.email and f"{counselor.full_name} via EduSphere" in str(outbox[0]["From"])
    stored = await reread(db_session, message)
    assert (stored.delivery_status, stored.attempt_count) == ("sent", 1)


@pytest.mark.asyncio
async def test_a_recorded_reply_is_never_sent(db_session, smtp_on, outbox):  # noqa: F811
    reply, _, _ = await queued(db_session, direction="inbound")
    assert await student_email.deliver_student_email(reply.id) is None and outbox == []


@pytest.mark.asyncio
async def test_a_transient_failure_retries_then_a_permanent_one_fails(db_session, smtp_on, outbox, student_emails_enqueued):  # noqa: F811
    message, _, _ = await queued(db_session)
    outbox.fail(smtplib.SMTPServerDisconnected("gone"))
    assert await student_email.deliver_student_email(message.id) == "retrying"
    assert student_emails_enqueued == [(str(message.id), 60)]
    assert await student_email.deliver_student_email(message.id) == "sent" and (await reread(db_session, message)).attempt_count == 2
    refused, _, _ = await queued(db_session)
    outbox.fail(smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")}))
    assert await student_email.deliver_student_email(refused.id) == "failed"


@pytest.mark.asyncio
async def test_logs_carry_no_address_subject_or_body(db_session, smtp_on, outbox, caplog, monkeypatch):  # noqa: F811
    monkeypatch.setattr(student_email.logger, "disabled", False)
    message, student, _ = await queued(db_session)
    with caplog.at_level("INFO"):
        await student_email.deliver_student_email(message.id)
    logged = " ".join(f"{r.getMessage()} {getattr(r, 'extra_fields', '')}" for r in caplog.records)
    assert str(message.id) in logged and student.email not in logged and "Dear Priya" not in logged and "Your offer" not in logged


@pytest.mark.asyncio
async def test_the_sweeper_republishes_stale_queued_emails_and_fails_interrupted_ones(db_session, student_emails_enqueued):
    stale, _, _ = await queued(db_session)
    stuck, _, _ = await queued(db_session, status="sending", attempts=1)
    fresh, _, _ = await queued(db_session)
    old = datetime.now(UTC) - timedelta(hours=1)
    await db_session.execute(update(StudentMessage).where(StudentMessage.id.in_([stale.id, stuck.id])).values(updated_at=old))
    await db_session.commit()
    await student_email.sweep_stale_student_emails()
    assert (str(stale.id), 0) in student_emails_enqueued and str(fresh.id) not in {m for m, _ in student_emails_enqueued}
    assert (await reread(db_session, stuck)).delivery_status == "failed"
