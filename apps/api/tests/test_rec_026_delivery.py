"""rec-026 -- the worker side of a recruiter email (spec §4; MS7, AC2): claim, send to the party's address now with the recruiter's
reply-to, record, retry and the stale sweeper. SMTP is replaced by a recorder on `mailer._send_sync`; the shared database is never
truncated."""

import smtplib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.config import settings
from app.models import Candidate, Company, CompanyContact, RecruiterMessage
from app.notifications import recruiter_email
from app.services import mailer
from app.services.candidates import next_code
from tests.rec001_helpers import make_recruiter
from tests.test_rec_009_candidates import mail, mobile, source_id
from tests.test_rec_026_messages import unique
from tests.test_tel_014_delivery import Outbox


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")


@pytest.fixture
def outbox(monkeypatch):
    """Every message handed to SMTP; `outbox.fail(exc)` makes the next send raise instead (tel-014's recorder)."""
    sent, failures = Outbox(), []

    def fake_send(msg) -> None:
        if failures:
            raise failures.pop(0)
        sent.append(msg)

    monkeypatch.setattr(mailer, "_send_sync", fake_send)
    sent.fail = failures.append
    return sent


async def _candidate(db, creator, **over) -> Candidate:
    values = {"name": "Rahul Verma", "mobile": mobile(), "email": mail()} | over
    row = Candidate(candidate_code=await next_code(db), source_id=await source_id(db), created_by_user_id=creator.id, **values)
    db.add(row)
    await db.commit()
    return row


async def queued(db, *, status="queued", attempts=0, **candidate_over) -> tuple[RecruiterMessage, Candidate, object]:
    sender = await make_recruiter(db, name="Asha Recruiter")
    candidate = await _candidate(db, sender, **candidate_over)
    message = RecruiterMessage(
        candidate_id=candidate.id,
        sender_user_id=sender.id,
        channel="email",
        subject="Interview confirmation",
        body="Dear Rahul",
        delivery_status=status,
        attempt_count=attempts,
        sent_at=datetime.now(UTC),
    )
    db.add(message)
    await db.commit()
    return message, candidate, sender


async def reread(db, message: RecruiterMessage) -> RecruiterMessage:
    await db.refresh(message)
    return message


@pytest.mark.asyncio
async def test_a_queued_email_is_sent_once_to_the_candidate_with_the_recruiters_reply_to(db_session, smtp_on, outbox):
    message, candidate, sender = await queued(db_session)
    assert await recruiter_email.deliver_recruiter_email(message.id) == "sent"
    assert await recruiter_email.deliver_recruiter_email(message.id) is None  # the claim lets one delivery through
    assert len(outbox) == 1 and outbox[0]["To"] == candidate.email and outbox[0]["Subject"] == "Interview confirmation"
    assert outbox[0]["Reply-To"].addresses[0].addr_spec == sender.email and "Asha Recruiter via EduSphere" in str(outbox[0]["From"])
    stored = await reread(db_session, message)
    assert (stored.delivery_status, stored.attempt_count) == ("sent", 1)


@pytest.mark.asyncio
async def test_a_contact_email_goes_to_the_contacts_address(db_session, smtp_on, outbox):
    sender = await make_recruiter(db_session)
    company = Company(name=unique("Deliver Co"))
    db_session.add(company)
    await db_session.flush()
    contact = CompanyContact(company_id=company.id, name="Meera", email=mail())
    db_session.add(contact)
    await db_session.flush()
    message = RecruiterMessage(company_id=company.id, contact_id=contact.id, sender_user_id=sender.id, channel="email", subject="Hi", body="B", delivery_status="queued", sent_at=datetime.now(UTC))
    db_session.add(message)
    await db_session.commit()
    assert await recruiter_email.deliver_recruiter_email(message.id) == "sent" and outbox[0]["To"] == contact.email


@pytest.mark.asyncio
async def test_a_transient_failure_retries_with_the_countdown(db_session, smtp_on, outbox, recruiter_emails_enqueued):
    message, _, _ = await queued(db_session)
    outbox.fail(smtplib.SMTPServerDisconnected("gone"))
    assert await recruiter_email.deliver_recruiter_email(message.id) == "retrying"
    assert recruiter_emails_enqueued == [(str(message.id), 60)]
    assert await recruiter_email.deliver_recruiter_email(message.id) == "sent" and (await reread(db_session, message)).attempt_count == 2


@pytest.mark.asyncio
async def test_a_permanent_failure_or_a_removed_address_fails_at_once(db_session, smtp_on, outbox, recruiter_emails_enqueued):
    message, _, _ = await queued(db_session)
    outbox.fail(smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")}))
    assert await recruiter_email.deliver_recruiter_email(message.id) == "failed"
    no_address, _, _ = await queued(db_session, email=None)
    assert await recruiter_email.deliver_recruiter_email(no_address.id) == "failed"
    assert recruiter_emails_enqueued == [] and (await reread(db_session, message)).delivery_status == "failed"


@pytest.mark.asyncio
async def test_logs_carry_no_address_subject_or_body(db_session, smtp_on, outbox, caplog, monkeypatch):
    monkeypatch.setattr(recruiter_email.logger, "disabled", False)
    message, candidate, _ = await queued(db_session)
    with caplog.at_level("INFO"):
        await recruiter_email.deliver_recruiter_email(message.id)
    logged = " ".join(f"{r.getMessage()} {getattr(r, 'extra_fields', '')}" for r in caplog.records)
    assert str(message.id) in logged and candidate.email not in logged and "Dear Rahul" not in logged and "Interview confirmation" not in logged


@pytest.mark.asyncio
async def test_the_sweeper_republishes_stale_queued_emails_and_fails_interrupted_ones(db_session, recruiter_emails_enqueued):
    stale, _, _ = await queued(db_session)
    stuck, _, _ = await queued(db_session, status="sending", attempts=1)
    fresh, _, _ = await queued(db_session)
    old = datetime.now(UTC) - timedelta(hours=1)
    await db_session.execute(update(RecruiterMessage).where(RecruiterMessage.id.in_([stale.id, stuck.id])).values(updated_at=old))
    await db_session.commit()
    await recruiter_email.sweep_stale_recruiter_emails()
    assert (str(stale.id), 0) in recruiter_emails_enqueued and str(fresh.id) not in {m for m, _ in recruiter_emails_enqueued}
    assert (await reread(db_session, stuck)).delivery_status == "failed"
