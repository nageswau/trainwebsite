"""hrc-032 (DEC-SCOPE-412 N8-N10; AC3) -- the Delivery exceptions page: failed recruitment deliveries and recruiter emails, who may read and
retry them, and a retry that succeeds. The database is shared and never truncated, so each test pages to find its own rows."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import CANDIDATE_ANONYMISED_REASONS, AuditLog, Notification, NotificationDelivery, RecruiterMessage
from app.notifications import delivery, twilio
from app.notifications.delivery import MAX_ATTEMPTS
from app.notifications.events import notify
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.rec038_helpers import make_candidate

URL = "/api/v1/recruiter/notification-exceptions"
EVENT = "it.requirement.changed"


@pytest.fixture(autouse=True)
def quiet_broker(monkeypatch):
    """Nothing is really published; the ids are kept for the assertions."""
    sent: list[str] = []
    monkeypatch.setattr("app.notifications.dispatch._publish", lambda delivery_id, countdown: sent.append(delivery_id))
    monkeypatch.setattr("app.notifications.dispatch._publish_recruiter_email", lambda message_id, countdown: sent.append(message_id))
    return sent


async def _failed(db, *, event=EVENT, channel="email", error="smtp timed out") -> tuple:
    person = await make_user(db, "placement_team", "it")
    if event:
        note = (await notify(db, [person], event, uuid.uuid4()))[0]
    else:  # a notice from outside recruitment
        note = Notification(user_id=person.id, title="Assignment reviewed", body="Score: 9/10", read=False)
        db.add(note)
        await db.flush()
    row = NotificationDelivery(notification_id=note.id, channel=channel, status="failed", attempt_count=MAX_ATTEMPTS, error=error)
    db.add(row)
    await db.commit()
    return row, person, note


async def _find(client, row_id, **params) -> tuple[dict | None, dict]:
    offset = 0
    while True:
        response = await client.get(URL, params={"limit": 100, "offset": offset, **params})
        assert response.status_code == 200, response.text
        page = response.json()
        found = next((r for r in page["items"] if r["id"] == str(row_id)), None)
        if found is not None or offset + 100 >= page["total"]:
            return found, page
        offset += 100


# --- N10: who ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "code"), [("hr_manager", "it", 200), ("placement_manager", "global", 200), ("super_admin", "global", 200),
                                                        ("placement_team", "it", 403), ("placement_officer", "it", 403), ("hr_team", "it", 403), ("it_student", "it", 403)])  # fmt: skip
async def test_only_a_retry_holder_reads_and_retries(client, db_session, role, division, code):
    row, *_ = await _failed(db_session)
    await login(client, await make_user(db_session, role, division))
    assert (await client.get(URL)).status_code == code
    answer = await client.post(f"{URL}/delivery/{row.id}/retry")
    assert answer.status_code == (code if code == 403 else 200), answer.text


@pytest.mark.asyncio
async def test_anonymous_is_refused(client):
    assert (await client.get(URL)).status_code == 401


# --- N8: the list --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_failed_delivery_is_listed_with_its_error_and_attempts_and_never_its_body(client, db_session):
    row, person, note = await _failed(db_session)
    await login(client, await make_pm(db_session))
    found, page = await _find(client, row.id)
    assert found["source"] == "delivery" and found["type"] == EVENT and found["type_label"] == "Vacancy updated"
    assert found["recipient"] == person.full_name and found["channel"] == "email" and found["error"] == "smtp timed out" and found["attempts"] == MAX_ATTEMPTS
    assert found["failed_at"]
    assert note.body not in str(found) and person.email not in str(found)
    assert {"key": EVENT, "label": "Vacancy updated"} in page["types"]


@pytest.mark.asyncio
async def test_an_error_never_shows_a_webhook_url(client, db_session):
    row, *_ = await _failed(db_session, error="Client error for url 'https://hooks.example.test/secret-token/abc' (404)")
    await login(client, await make_pm(db_session))
    found, _ = await _find(client, row.id)
    assert "secret-token" not in found["error"] and "hooks.example" not in found["error"] and "404" in found["error"]


@pytest.mark.asyncio
async def test_a_notice_from_outside_recruitment_is_neither_listed_nor_retried(client, db_session):
    row, *_ = await _failed(db_session, event=None)
    await login(client, await make_pm(db_session))
    found, _ = await _find(client, row.id)
    assert found is None
    assert (await client.post(f"{URL}/delivery/{row.id}/retry")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "retrying", "sending", "sent", "skipped", "not_configured"])
async def test_only_a_failed_delivery_is_an_exception(client, db_session, status):
    row, *_ = await _failed(db_session)
    row.status = status
    await db_session.commit()
    await login(client, await make_pm(db_session))
    found, _ = await _find(client, row.id)
    assert found is None
    assert (await client.post(f"{URL}/delivery/{row.id}/retry")).status_code == 409


@pytest.mark.asyncio
async def test_filters_narrow_the_list(client, db_session):
    row, *_ = await _failed(db_session, channel="whatsapp")
    other, *_ = await _failed(db_session, event="it.application.new", channel="sms")
    await login(client, await make_pm(db_session))
    assert (await _find(client, row.id, channel="whatsapp"))[0] is not None
    assert (await _find(client, row.id, channel="sms"))[0] is None
    assert (await _find(client, other.id, type="it.application.new"))[0] is not None
    assert (await _find(client, row.id, type="it.application.new"))[0] is None


@pytest.mark.asyncio
async def test_an_unknown_filter_is_a_422(client, db_session):
    await login(client, await make_pm(db_session))
    assert (await client.get(URL, params={"channel": "pigeon"})).status_code == 422
    assert (await client.get(URL, params={"limit": 0})).status_code == 422


# --- N9: retry -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_retry_requeues_once_and_is_audited(client, db_session, quiet_broker):
    row, *_ = await _failed(db_session)
    row_id = row.id
    manager = await make_pm(db_session)
    manager_id = manager.id
    await login(client, manager)
    first = await client.post(f"{URL}/delivery/{row_id}/retry")
    assert first.status_code == 200 and first.json() == {"id": str(row_id), "source": "delivery", "status": "queued"}
    db_session.expire_all()
    fresh = await db_session.get(NotificationDelivery, row_id)
    assert (fresh.status, fresh.attempt_count, fresh.error) == ("queued", 0, None)
    assert str(row_id) in quiet_broker
    assert (await client.post(f"{URL}/delivery/{row_id}/retry")).status_code == 409  # a double click sends once
    assert quiet_broker.count(str(row_id)) == 1
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "notification.retry", AuditLog.entity_id == str(row_id)))).all()
    assert len(audit) == 1 and audit[0].user_id == manager_id and audit[0].metadata_json["source"] == "delivery"
    assert "smtp timed out" not in str(audit[0].metadata_json)
    assert (await _find(client, row_id))[0] is None


@pytest.mark.asyncio
async def test_a_retry_of_something_unknown_is_a_404(client, db_session):
    await login(client, await make_pm(db_session))
    assert (await client.post(f"{URL}/delivery/{uuid.uuid4()}/retry")).status_code == 404
    assert (await client.post(f"{URL}/email/{uuid.uuid4()}/retry")).status_code == 404
    assert (await client.post(f"{URL}/pigeon/{uuid.uuid4()}/retry")).status_code == 422


@pytest.mark.asyncio
async def test_retries_exhausted_then_the_provider_returns(client, db_session, monkeypatch):
    """The backlog's edge: the provider is down for an hour, the item becomes an exception, and a manual retry delivers it."""
    person = await make_user(db_session, "placement_team", "it")
    note = (await notify(db_session, [person], EVENT, uuid.uuid4()))[0]
    await db_session.commit()
    row_id = await db_session.scalar(select(NotificationDelivery.id).where(NotificationDelivery.notification_id == note.id))

    async def down(_channel, _snapshot, _context):
        return twilio.SendResult("failed", error="provider down", transient=True)

    monkeypatch.setattr(delivery, "_send", down)
    for _ in range(MAX_ATTEMPTS):
        await delivery.deliver(row_id)
    db_session.expire_all()
    assert (await db_session.get(NotificationDelivery, row_id)).status == "failed"

    await login(client, await make_pm(db_session))
    found, _ = await _find(client, row_id)
    assert found["error"] == "provider down" and found["attempts"] == MAX_ATTEMPTS
    assert (await client.post(f"{URL}/delivery/{row_id}/retry")).status_code == 200

    async def up(_channel, _snapshot, _context):
        return twilio.SendResult("sent", provider_reference="ok")

    monkeypatch.setattr(delivery, "_send", up)
    assert await delivery.deliver(row_id) == "sent"
    assert (await _find(client, row_id))[0] is None


# --- recruiter emails (rec-026) --------------------------------------------------------------------------------------------------------
async def _failed_email(db) -> tuple:
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    candidate = await make_candidate(db, recruiter)
    mail = RecruiterMessage(candidate_id=candidate.id, sender_user_id=recruiter.id, channel="email", subject=f"Private subject {uuid.uuid4().hex[:6]}", body="Private body",
                            delivery_status="failed", attempt_count=MAX_ATTEMPTS, sent_at=datetime.now(UTC))  # fmt: skip
    db.add(mail)
    await db.commit()
    return mail, candidate, manager


@pytest.mark.asyncio
async def test_a_failed_recruiter_email_is_listed_without_its_subject_and_retried(client, db_session, quiet_broker):
    mail, candidate, manager = await _failed_email(db_session)
    mail_id, subject, name = mail.id, mail.subject, candidate.name
    await login(client, manager)
    found, _ = await _find(client, mail_id, type="recruiter.email")
    assert found["source"] == "email" and found["recipient"] == name and found["channel"] == "email" and found["attempts"] == MAX_ATTEMPTS
    assert subject not in str(found) and "Private body" not in str(found)
    assert (await client.post(f"{URL}/email/{mail_id}/retry")).status_code == 200
    db_session.expire_all()
    fresh = await db_session.get(RecruiterMessage, mail_id)
    assert (fresh.delivery_status, fresh.attempt_count) == ("queued", 0)
    assert str(mail_id) in quiet_broker
    assert (await client.post(f"{URL}/email/{mail_id}/retry")).status_code == 409


@pytest.mark.asyncio
async def test_an_anonymised_candidates_email_is_never_retried(client, db_session):
    mail, candidate, manager = await _failed_email(db_session)
    mail_id = mail.id
    candidate.anonymised_at, candidate.anonymised_reason = datetime.now(UTC), CANDIDATE_ANONYMISED_REASONS[0]
    await db_session.commit()
    await login(client, manager)
    assert (await _find(client, mail_id))[0] is None
    assert (await client.post(f"{URL}/email/{mail_id}/retry")).status_code == 404
