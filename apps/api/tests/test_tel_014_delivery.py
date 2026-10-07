"""tel-014 -- the worker side of a lead email (spec §1 E4-E7, E10; §4): the message builder, the claim, send, record and retry, and the
stale sweeper. SMTP itself is replaced by a recorder on `mailer._send_sync`; the shared test database is never truncated."""

import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from sqlalchemy import update

from app.core.config import settings
from app.models import LeadMessage
from app.notifications import lead_email
from app.services import mailer
from tests.test_tel_013_messages import lead, team


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")


class Outbox(list):
    fail = None


@pytest.fixture
def outbox(monkeypatch):
    """Every message handed to SMTP; `outbox.fail` makes the next sends raise instead."""
    sent = Outbox()
    failures: list[Exception] = []

    def fake_send(msg: EmailMessage) -> None:
        if failures:
            raise failures.pop(0)
        sent.append(msg)

    monkeypatch.setattr(mailer, "_send_sync", fake_send)
    sent.fail = failures.append
    return sent


async def queued(db, *, status="queued", attempts=0, **lead_over) -> tuple[LeadMessage, object, object]:
    _, tel, _ = await team(db)
    row = await lead(db, tel, **lead_over)
    message = LeadMessage(lead_id=row.id, sender_user_id=tel.id, channel="email", subject="Your brochure", body="Hi Priya",
                          delivery_status=status, attempt_count=attempts, sent_at=datetime.now(UTC))
    db.add(message)
    await db.commit()
    return message, row, tel


async def reread(db, message: LeadMessage) -> LeadMessage:
    await db.refresh(message)
    return message


# --- the message (EM1, E6) -------------------------------------------------------------------------------------------------------
def test_the_message_comes_from_the_system_address_in_the_telecallers_name_with_their_reply_to(smtp_on):
    msg = mailer.lead_email_message(to_email="lead@example.com", subject="Your brochure", body="Hi", sender_name="Asha Rao",
                                    sender_email="asha@edusphere.local")
    assert msg["From"] == "Asha Rao via EduSphere <noreply@edusphere.local>"
    assert msg["Reply-To"] == "Asha Rao <asha@edusphere.local>"
    assert (msg["To"], msg["Subject"]) == ("lead@example.com", "Your brochure")


def test_a_display_name_with_specials_is_quoted_not_parsed_as_addresses(smtp_on):
    msg = mailer.lead_email_message(to_email="lead@example.com", subject="S", body="Hi", sender_name='Rao, "Asha" <x@evil.test>',
                                    sender_email="asha@edusphere.local")
    assert [a.addr_spec for a in msg["From"].addresses] == ["noreply@edusphere.local"]
    assert [a.addr_spec for a in msg["Reply-To"].addresses] == ["asha@edusphere.local"]


def test_the_html_part_escapes_the_text_and_links_only_urls(smtp_on):
    body = 'Hi <b>Priya</b> & co\nBrochure: https://edusphere.test/b?t=1&e=2\n<script>alert(1)</script> "https://x.test/"onclick'
    msg = mailer.lead_email_message(to_email="lead@example.com", subject="S", body=body, sender_name="<i>Asha</i>", sender_email="a@x.test")
    text = msg.get_body(("plain",)).get_content()
    html = msg.get_body(("html",)).get_content()
    assert body in text
    assert "<b>" not in html and "<script>" not in html and "<i>Asha</i>" not in html
    assert "&lt;b&gt;Priya&lt;/b&gt; &amp; co" in html and "&lt;i&gt;Asha&lt;/i&gt;" in html
    assert '<a href="https://edusphere.test/b?t=1&amp;e=2" ' in html and ">https://edusphere.test/b?t=1&amp;e=2</a>" in html
    assert '"onclick' not in html  # the quote is escaped, so the link can't break out of its attribute


# --- deliver (E4, E5, E7) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_queued_email_is_sent_once_to_the_leads_address(db_session, smtp_on, outbox):
    message, row, tel = await queued(db_session)
    assert await lead_email.deliver_lead_email(message.id) == "sent"
    assert await lead_email.deliver_lead_email(message.id) is None  # the claim lets one delivery through
    assert len(outbox) == 1 and outbox[0]["To"] == row.email and outbox[0]["Reply-To"].addresses[0].addr_spec == tel.email
    stored = await reread(db_session, message)
    assert (stored.delivery_status, stored.attempt_count) == ("sent", 1)


@pytest.mark.asyncio
async def test_a_whatsapp_row_is_never_claimed(db_session, smtp_on, outbox):
    message, _, _ = await queued(db_session)
    await db_session.execute(update(LeadMessage).where(LeadMessage.id == message.id).values(channel="whatsapp", subject=None, delivery_status=None))
    await db_session.commit()
    assert await lead_email.deliver_lead_email(message.id) is None and outbox == []


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [smtplib.SMTPServerDisconnected("gone"), ConnectionRefusedError(), TimeoutError(),
                                   smtplib.SMTPResponseException(421, b"try later")])
async def test_a_transient_failure_retries_with_the_countdown(db_session, smtp_on, outbox, lead_emails_enqueued, error):
    message, _, _ = await queued(db_session)
    outbox.fail(error)
    assert await lead_email.deliver_lead_email(message.id) == "retrying"
    assert lead_emails_enqueued == [(str(message.id), 60)]
    assert await lead_email.deliver_lead_email(message.id) == "sent" and len(outbox) == 1
    assert (await reread(db_session, message)).attempt_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")}),
                                   smtplib.SMTPResponseException(554, b"rejected"), smtplib.SMTPAuthenticationError(535, b"bad login")])
async def test_a_permanent_failure_fails_at_once(db_session, smtp_on, outbox, lead_emails_enqueued, error):
    message, _, _ = await queued(db_session)
    outbox.fail(error)
    assert await lead_email.deliver_lead_email(message.id) == "failed"
    assert lead_emails_enqueued == [] and (await reread(db_session, message)).delivery_status == "failed"


@pytest.mark.asyncio
async def test_the_last_attempt_fails_instead_of_retrying(db_session, smtp_on, outbox, lead_emails_enqueued):
    message, _, _ = await queued(db_session, status="retrying", attempts=lead_email.MAX_ATTEMPTS - 1)
    outbox.fail(TimeoutError())
    assert await lead_email.deliver_lead_email(message.id) == "failed" and lead_emails_enqueued == []


@pytest.mark.asyncio
async def test_an_address_removed_or_smtp_unset_before_sending_fails(db_session, smtp_on, outbox, monkeypatch):
    message, _, _ = await queued(db_session, email=None)
    assert await lead_email.deliver_lead_email(message.id) == "failed"
    other, _, _ = await queued(db_session)
    monkeypatch.setattr(settings, "smtp_host", None)
    assert await lead_email.deliver_lead_email(other.id) == "failed" and outbox == []


@pytest.mark.asyncio
async def test_logs_carry_no_address_subject_or_body(db_session, smtp_on, outbox, caplog):
    message, row, _ = await queued(db_session)
    outbox.fail(smtplib.SMTPRecipientsRefused({row.email: (550, b"no such user " + row.email.encode())}))
    with caplog.at_level("INFO"):
        await lead_email.deliver_lead_email(message.id)
    logged = " ".join(f"{r.getMessage()} {getattr(r, 'extra_fields', '')}" for r in caplog.records)
    assert str(message.id) in logged and "SMTPRecipientsRefused" in logged
    assert row.email not in logged and "Your brochure" not in logged and "Hi Priya" not in logged


# --- sweep (E5) ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_sweeper_republishes_stale_queued_emails_and_fails_interrupted_ones(db_session, lead_emails_enqueued):
    stale, _, _ = await queued(db_session)
    stuck, _, _ = await queued(db_session, status="sending", attempts=1)
    fresh, _, _ = await queued(db_session)
    old = datetime.now(UTC) - timedelta(hours=1)
    await db_session.execute(update(LeadMessage).where(LeadMessage.id.in_([stale.id, stuck.id])).values(updated_at=old))
    await db_session.commit()
    await lead_email.sweep_stale_lead_emails()
    assert (str(stale.id), 0) in lead_emails_enqueued and str(fresh.id) not in {m for m, _ in lead_emails_enqueued}
    assert (await reread(db_session, stuck)).delivery_status == "failed"
    assert (await reread(db_session, stale)).delivery_status == "queued"
