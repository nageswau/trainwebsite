"""pob-026 -- client and candidate satisfaction surveys (DEC-SCOPE-435 S1-S12; AC1, AC2 and the "contact has left" edge). The shared test
database is never truncated, so every value is unique per test and each sweep is checked only for this test's placement."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import ALGORITHM, create_token
from app.models import AuditLog, Company, CompanyContact, JobOffer, Placement, PlacementSurvey, ProfileShare, ProfileShareItem, RecruiterMessage
from app.services import placement_surveys as svc
from tests.test_pob_024_placements import _accept, _join, _placement, _world

PUBLIC = "/api/v1/public/placement-surveys"
TODAY = date.today()


async def _joined(client, db, *, days_ago=svc.SURVEY_AFTER_DAYS, contact=True, contact_email=True, candidate_email=True) -> dict:
    s = await _world(client, db)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    offer = await db.scalar(select(JobOffer).where(JobOffer.id == s["offer"]["id"]))
    offer.actual_joining_date = TODAY - timedelta(days=days_ago)
    if not candidate_email:
        s["candidate"].mobile = s["candidate"].mobile or f"9{uuid4().int % 10**9:09d}"  # ck_candidates_contact: a mobile or an email
        s["candidate"].email = None
        db.add(s["candidate"])
    if contact:
        s["contact"] = CompanyContact(company_id=s["job"].company_id, name=f"HR {uuid4().hex[:6]}", is_primary=True,
                                      email=f"hr-{uuid4().hex[:8]}@example.com" if contact_email else None)  # fmt: skip
        db.add(s["contact"])
    await db.commit()
    s["placement_id"] = placement_id
    return s


async def _surveys(db, placement_id) -> dict[str, PlacementSurvey]:
    rows = await db.scalars(select(PlacementSurvey).where(PlacementSurvey.placement_id == placement_id).execution_options(populate_existing=True))
    return {r.respondent: r for r in rows}


async def _messages(db, survey: PlacementSurvey) -> list[RecruiterMessage]:
    ids = [i for i in (survey.message_id, survey.resend_message_id) if i]
    return list(await db.scalars(select(RecruiterMessage).where(RecruiterMessage.id.in_(ids)).order_by(RecruiterMessage.sent_at)))


def _token_from(message: RecruiterMessage) -> str:
    return message.body.split(svc.PUBLIC_PATH, 1)[1].split()[0]


async def _sweep(now=None):
    return await svc.run_surveys(now=now)


def _own_ip(client) -> None:
    """Refused lookups are counted per IP in the never-truncated audit log: each test that makes them uses its own address."""
    client.headers["X-Forwarded-For"] = f"10.{uuid4().int % 250}.{uuid4().int % 250}.{uuid4().int % 250 + 1}"


# --- AC1: sent once to each side, one response recorded (S1-S5) -----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_joined_placement_gets_one_survey_per_side_sent_once(client, db_session, recruiter_emails_enqueued):
    s = await _joined(client, db_session)
    await _sweep()
    await _sweep()
    rows = await _surveys(db_session, s["placement_id"])
    assert set(rows) == {"client", "candidate"}
    client_row, candidate_row = rows["client"], rows["candidate"]
    assert client_row.contact_id == s["contact"].id and candidate_row.contact_id is None
    assert client_row.sent_at and candidate_row.sent_at and not client_row.skip_reason
    [to_client] = await _messages(db_session, client_row)
    [to_candidate] = await _messages(db_session, candidate_row)
    assert (to_client.channel, to_client.contact_id, to_client.company_id, to_client.delivery_status) == ("email", s["contact"].id, s["job"].company_id, "queued")
    assert to_candidate.candidate_id == s["candidate"].id and to_client.sender_user_id == s["recruiter"].id
    assert svc.PUBLIC_PATH in to_client.body and s["candidate"].email not in to_client.body
    assert {str(to_client.id), str(to_candidate.id)} <= {m for m, _ in recruiter_emails_enqueued}


@pytest.mark.asyncio
async def test_not_due_until_the_days_after_joining_have_passed(client, db_session, recruiter_emails_enqueued):
    s = await _joined(client, db_session, days_ago=svc.SURVEY_AFTER_DAYS - 1)
    await _sweep()
    assert await _surveys(db_session, s["placement_id"]) == {}
    old = await _joined(client, db_session, days_ago=svc.SURVEY_LOOKBACK_DAYS + 1)
    await _sweep()
    assert await _surveys(db_session, old["placement_id"]) == {}


@pytest.mark.asyncio
async def test_a_side_with_no_address_is_skipped_once_with_a_reason(client, db_session, recruiter_emails_enqueued):
    s = await _joined(client, db_session, contact_email=False, candidate_email=False)
    await _sweep()
    await _sweep()
    rows = await _surveys(db_session, s["placement_id"])
    assert (rows["client"].skip_reason, rows["candidate"].skip_reason) == ("no_contact", "no_email")
    assert rows["client"].message_id is None and rows["client"].sent_at is None


# --- the edge: the contact has left (S3) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_submitted_contact_is_used_unless_they_have_left(client, db_session, recruiter_emails_enqueued):
    s = await _joined(client, db_session)
    submitted = CompanyContact(company_id=s["job"].company_id, name="Hiring manager", email=f"hm-{uuid4().hex[:8]}@example.com")
    db_session.add(submitted)
    await db_session.flush()
    share = ProfileShare(job_id=s["job"].id, company_id=s["job"].company_id, contact_id=submitted.id, channel="other", shared_by_user_id=s["recruiter"].id)
    db_session.add(share)
    await db_session.flush()
    db_session.add(ProfileShareItem(share_id=share.id, candidate_id=s["candidate"].id, application_id=s["application"]["id"]))
    await db_session.commit()
    placement = await db_session.get(Placement, s["placement_id"])
    assert (await svc.client_contact(db_session, placement)).id == submitted.id
    submitted.active = False  # left the company
    await db_session.commit()
    assert (await svc.client_contact(db_session, placement)).id == s["contact"].id  # the primary contact
    s["contact"].status = "do_not_contact"
    await db_session.commit()
    assert await svc.client_contact(db_session, placement) is None


# --- S7: resent once ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_unanswered_survey_is_resent_once(client, db_session, recruiter_emails_enqueued):
    s = await _joined(client, db_session)
    await _sweep()
    now = datetime.now(UTC)
    await _sweep(now + timedelta(days=svc.SURVEY_RESEND_DAYS - 1))
    assert (await _surveys(db_session, s["placement_id"]))["client"].resent_at is None
    await _sweep(now + timedelta(days=svc.SURVEY_RESEND_DAYS + 1))
    await _sweep(now + timedelta(days=svc.SURVEY_RESEND_DAYS * 2 + 1))
    row = (await _surveys(db_session, s["placement_id"]))["client"]
    assert row.resent_at is not None and len(await _messages(db_session, row)) == 2
    first, second = await _messages(db_session, row)
    assert (await client.get(f"{PUBLIC}/{_token_from(first)}")).status_code == 200  # the first link still works
    assert (await client.get(f"{PUBLIC}/{_token_from(second)}")).status_code == 200


# --- AC2 and S8: the public link ----------------------------------------------------------------------------------------------------------
async def _client_token(client, db) -> tuple[dict, str]:
    s = await _joined(client, db)
    await _sweep()
    [message] = await _messages(db, (await _surveys(db, s["placement_id"]))["client"])
    return s, _token_from(message)


@pytest.mark.asyncio
async def test_one_response_is_recorded_and_the_token_then_returns_410(client, db_session, recruiter_emails_enqueued):
    s, token = await _client_token(client, db_session)
    client.cookies.clear()  # no session: the token is the credential
    _own_ip(client)
    shown = await client.get(f"{PUBLIC}/{token}")
    assert shown.status_code == 200, shown.text
    company = await db_session.get(Company, s["job"].company_id)
    assert shown.json() == {"respondent": "client", "role": "Java Developer", "company": company.name}
    assert (await client.post(f"{PUBLIC}/{token}", json={"rating": 6})).status_code == 422
    answered = await client.post(f"{PUBLIC}/{token}", json={"rating": 4, "comment": "  Smooth hire  "})
    assert answered.status_code == 201, answered.text
    row = (await _surveys(db_session, s["placement_id"]))["client"]
    assert (row.rating, row.comment) == (4, "Smooth hire") and row.responded_at
    assert (await client.post(f"{PUBLIC}/{token}", json={"rating": 1})).status_code == 410
    assert (await client.get(f"{PUBLIC}/{token}")).status_code == 410
    assert (await _surveys(db_session, s["placement_id"]))["client"].rating == 4
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "placement_survey.responded", AuditLog.entity_id == str(row.id)))
    assert audit.metadata_json == {"placement_id": str(s["placement_id"]), "respondent": "client", "rating": 4}


@pytest.mark.asyncio
async def test_bad_foreign_and_expired_tokens(client, db_session, recruiter_emails_enqueued):
    s, token = await _client_token(client, db_session)
    survey_id = (await _surveys(db_session, s["placement_id"]))["client"].id
    client.cookies.clear()
    _own_ip(client)
    assert (await client.get(f"{PUBLIC}/not-a-token")).status_code == 404
    session = create_token(str(survey_id), "client", "it")  # a session token naming the survey id is not a survey link
    assert (await client.get(f"{PUBLIC}/{session}")).status_code == 404
    unknown = jwt.encode({"sub": str(uuid4()), "type": svc.LINK_TYPE, "exp": datetime.now(UTC) + timedelta(days=1)}, settings.secret_key, algorithm=ALGORITHM)
    assert (await client.get(f"{PUBLIC}/{unknown}")).status_code == 404
    expired = jwt.encode({"sub": str(survey_id), "type": svc.LINK_TYPE, "exp": datetime.now(UTC) - timedelta(seconds=5)}, settings.secret_key, algorithm=ALGORITHM)
    assert (await client.get(f"{PUBLIC}/{expired}")).status_code == 410
    assert (await client.post(f"{PUBLIC}/{expired}", json={"rating": 5})).status_code == 410


@pytest.mark.asyncio
async def test_refused_lookups_from_one_ip_are_throttled(client, db_session):
    ip = f"203.0.113.{uuid4().int % 250 + 1}"
    headers = {"X-Forwarded-For": ip}
    await db_session.execute(AuditLog.__table__.delete().where(AuditLog.action == svc.REFUSED_ACTION, AuditLog.metadata_json["ip"].as_string() == ip))
    await db_session.commit()
    for _ in range(svc.REFUSED_MAX_PER_IP):
        assert (await client.get(f"{PUBLIC}/guess-{uuid4().hex}", headers=headers)).status_code == 404
    throttled = await client.get(f"{PUBLIC}/guess-{uuid4().hex}", headers=headers)
    assert throttled.status_code == 429 and int(throttled.headers["Retry-After"]) > 0
    assert (await client.get(f"{PUBLIC}/guess-{uuid4().hex}", headers={"X-Forwarded-For": "198.51.100.7"})).status_code in (404, 429)


# --- S10: the results on the placement ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_placement_shows_both_surveys(client, db_session, recruiter_emails_enqueued):
    s = await _joined(client, db_session, candidate_email=False)
    assert (await _placement(client, s["placement_id"]))["satisfaction"] == {"client": None, "candidate": None}
    await _sweep()
    [message] = await _messages(db_session, (await _surveys(db_session, s["placement_id"]))["client"])
    token = _token_from(message)
    await client.post(f"{PUBLIC}/{token}", json={"rating": 5, "comment": "Great"})
    satisfaction = (await _placement(client, s["placement_id"]))["satisfaction"]
    assert (satisfaction["client"]["status"], satisfaction["client"]["rating"], satisfaction["client"]["comment"]) == ("responded", 5, "Great")
    assert (satisfaction["candidate"]["status"], satisfaction["candidate"]["skip_reason_label"]) == ("skipped", "The candidate has no email address")


def test_the_worker_task_imports_in_a_fresh_interpreter():
    import subprocess
    import sys

    code = "import app.worker; import app.services.telecaller_alerts; from app.services.placement_surveys import run_surveys"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/app")
    assert result.returncode == 0, result.stderr[-2000:]


# --- S11: a manual close needs a reason ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_manual_close_needs_a_reason(client, db_session):
    from tests.test_rec_017_tracking import _requirement, _team

    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    url = f"/api/v1/recruiter/requirements/{job.id}/status"
    refused = await client.post(url, json={"status": "closed"})
    assert refused.status_code == 422 and "reason for closing" in refused.text
    assert (await client.post(url, json={"status": "closed", "note": "   "})).status_code == 422
    closed = await client.post(url, json={"status": "closed", "note": "Client paused hiring"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["requirement"]["status_history"][0]["note"] == "Client paused hiring"
