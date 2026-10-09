"""rec-019 -- profile sharing (spec §1-§3; AC1-AC4; DEC-SCOPE-158 S1-S14). The shared test database is never truncated, so every value is
unique per test."""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.core.security import hash_password
from app.models import AuditLog, Company, CompanyContact, EmployerProfile, JobApplication, ProfileShareItem, RecruiterMessage, User
from app.services import profile_sharing as svc
from tests.rec001_helpers import as_role, login, make_recruiter
from tests.rec017_helpers import student_application
from tests.test_rec_009_resumes import PDF
from tests.test_rec_017_tracking import _add, _candidate, _move, _requirement, _tag, _team

SHARES = "/api/v1/recruiter/shares"
REQ = "/api/v1/recruiter/requirements"
EMPLOYER = "/api/v1/employer/shared-profiles"
PUBLIC = "/api/v1/public/shared-resume"


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")


@pytest.fixture
def published(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr("app.api.recruiter_shares.enqueue_recruiter_email", lambda message_id: sent.append(str(message_id)) or True)
    return sent


async def _contact(db, company_id, **extra) -> CompanyContact:
    contact = CompanyContact(company_id=company_id, name=f"Priya {_tag()}", email=f"hr-{_tag()}@example.com", mobile="+919876543210", **extra)
    db.add(contact)
    await db.commit()
    return contact


async def _employer(db, company_id) -> User:
    user = User(email=f"emp-{_tag()}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Employer", role="employer", division="it", active=True)
    db.add(user)
    await db.flush()
    db.add(EmployerProfile(user_id=user.id, company_id=company_id, registration_status=None))
    await db.commit()
    return user


async def _setup(client, db, n: int = 3):
    manager, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    contact = await _contact(db, job.company_id)
    people = [await _candidate(db, recruiter, mobile=f"+9198{uuid.uuid4().int % 10**8:08d}", qualification="B.Tech", experience_months=26, location="Pune") for _ in range(n)]
    return {"manager": manager, "recruiter": recruiter, "job": job, "contact": contact, "candidates": people}


def _body(s, channel="email", **over) -> dict:
    body = {"requirement_id": str(s["job"].id), "candidate_ids": [str(c.id) for c in s["candidates"]], "channel": channel}
    if channel in ("email", "whatsapp"):
        body["contact_id"] = str(s["contact"].id)
    return body | over


async def _share(client, s, channel="email", **over):
    return await client.post(SHARES, json=_body(s, channel, **over))


async def _upload(client, candidate_id):
    response = await client.put(f"/api/v1/recruiter/candidates/{candidate_id}/resume", files={"file": ("cv.pdf", PDF, "application/pdf")})
    assert response.status_code == 201, response.text


def _links(text: str) -> list[str]:
    return [word.split(PUBLIC + "/", 1)[1].rstrip(").,") for word in text.split() if PUBLIC + "/" in word]


# --- AC1-AC4: email --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_email_share_records_three_items_one_email_and_moves_applications(client, db_session, smtp_on, published):
    s = await _setup(client, db_session)
    existing = (await _add(client, s["job"], s["candidates"][0], status="shortlisted")).json()["application"]
    for candidate in s["candidates"][:2]:
        await _upload(client, candidate.id)
    response = await _share(client, s, note="Top three")
    assert response.status_code == 201, response.text
    share = response.json()["share"]
    assert share["channel"] == "email" and share["contact"]["id"] == str(s["contact"].id) and share["note"] == "Top three"
    assert len(share["items"]) == 3 and {i["response"] for i in share["items"]} == {"pending"}
    with_resume = {str(c.id) for c in s["candidates"][:2]}
    assert {i["candidate"]["id"]: i["has_resume"] for i in share["items"]} == {str(c.id): str(c.id) in with_resume for c in s["candidates"]}
    assert response.json()["whatsapp_url"] is None
    message = await db_session.get(RecruiterMessage, uuid.UUID(share["message"]["id"]))
    assert message.channel == "email" and message.delivery_status == "queued" and message.contact_id == s["contact"].id
    assert published == [share["message"]["id"]]  # AC1: one email, published after the commit
    # AC2: no candidate phone or email in the email
    for candidate in s["candidates"]:
        assert candidate.name in message.body and candidate.candidate_code in message.body
        assert candidate.email not in message.body and candidate.mobile not in message.body
    assert len(_links(message.body)) == 2 and "Resume on request" in message.body
    # AC4: Profile Shared -- the existing application moved, the others were added at Profile Shared
    statuses = (await db_session.execute(select(JobApplication.candidate_id, JobApplication.status).where(JobApplication.job_id == s["job"].id).execution_options(populate_existing=True))).all()
    assert {status for _, status in statuses} == {"profile_shared"} and len(statuses) == 3
    history = (await client.get(f"/api/v1/recruiter/applications/{existing['id']}/history")).json()["items"]
    assert (history[0]["from_status"], history[0]["to_status"]) == ("shortlisted", "profile_shared")
    company = await db_session.scalar(select(Company).where(Company.id == s["job"].company_id).execution_options(populate_existing=True))
    assert company.stage == "profiles_shared"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "profile_share.create", AuditLog.entity_id == share["id"]))
    assert audit is not None and s["candidates"][0].name not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_resume_link_serves_the_file_audits_and_expires(client, db_session, smtp_on, published):
    s = await _setup(client, db_session, n=1)
    await _upload(client, s["candidates"][0].id)
    share = (await _share(client, s)).json()["share"]
    body = (await db_session.get(RecruiterMessage, uuid.UUID(share["message"]["id"]))).body
    (token,) = _links(body)
    client.cookies.clear()  # AC: no session needed
    download = await client.get(f"{PUBLIC}/{token}")
    assert download.status_code == 200 and download.content == PDF
    assert "no-store" in download.headers["cache-control"] and download.headers["x-content-type-options"] == "nosniff"
    item_id = share["items"][0]["id"]
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "profile_share.resume_download", AuditLog.entity_id == item_id))
    stored = await db_session.scalar(select(ProfileShareItem.token_hash).where(ProfileShareItem.id == uuid.UUID(item_id)))
    assert stored and token not in stored  # only the hash is stored
    # AC3: the link expires
    await db_session.execute(update(ProfileShareItem).where(ProfileShareItem.id == uuid.UUID(item_id)).values(token_expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await db_session.commit()
    assert (await client.get(f"{PUBLIC}/{token}")).status_code == 404
    assert (await client.get(f"{PUBLIC}/not-a-real-token")).status_code == 404


def test_token_validity_is_seven_days():
    assert svc.LINK_TTL == timedelta(days=7)


# --- channels ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_whatsapp_share_logs_a_message_and_returns_the_wa_link_without_contact_details(client, db_session):
    s = await _setup(client, db_session, n=2)
    response = await _share(client, s, "whatsapp")
    assert response.status_code == 201, response.text
    url = response.json()["whatsapp_url"]
    assert url.startswith("https://wa.me/919876543210?text=")
    text = unquote(url.split("?text=", 1)[1])
    for candidate in s["candidates"]:
        assert candidate.name in text and candidate.email not in text and candidate.mobile not in text
    message = await db_session.get(RecruiterMessage, uuid.UUID(response.json()["share"]["message"]["id"]))
    assert message.channel == "whatsapp" and message.delivery_status is None and message.body == text


@pytest.mark.asyncio
async def test_portal_share_reaches_only_the_companys_employers_who_can_respond(client, db_session):
    s = await _setup(client, db_session, n=2)
    await _upload(client, s["candidates"][0].id)
    assert (await _share(client, s, "portal")).status_code == 409  # no employer portal account yet
    employer = await _employer(db_session, s["job"].company_id)
    response = await _share(client, s, "portal")
    assert response.status_code == 201, response.text
    assert response.json()["share"]["message"] is None and response.json()["share"]["contact"] is None
    other_job = await _requirement(db_session, s["recruiter"])
    outsider = await _employer(db_session, other_job.company_id)

    await login(client, employer)
    listing = await client.get(EMPLOYER)
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 2
    first = next(i for i in items if i["candidate"]["code"] == s["candidates"][0].candidate_code)
    assert first["candidate"]["qualification"] == "B.Tech" and first["has_resume"] is True
    assert not {"email", "mobile", "phone", "linkedin", "current_salary", "expected_salary"} & set(first["candidate"])  # AC2
    assert first["requirement"]["title"] == s["job"].title
    resume = await client.get(f"{EMPLOYER}/{first['id']}/resume")
    assert resume.status_code == 200 and resume.content == PDF
    answered = await client.patch(f"{EMPLOYER}/{first['id']}", json={"response": "interested"})
    assert answered.status_code == 200 and answered.json()["response"] == "interested"
    assert (await client.patch(f"{EMPLOYER}/{first['id']}", json={"response": "maybe"})).status_code == 422

    await login(client, outsider)
    assert (await client.get(EMPLOYER)).json()["items"] == []
    assert (await client.patch(f"{EMPLOYER}/{first['id']}", json={"response": "not_interested"})).status_code == 404
    assert (await client.get(f"{EMPLOYER}/{first['id']}/resume")).status_code == 404

    await login(client, s["recruiter"])
    shares = (await client.get(f"{REQ}/{s['job'].id}/shares")).json()
    item = next(i for i in shares["items"][0]["items"] if i["id"] == first["id"])
    assert item["response"] == "interested" and item["responded_by"]["id"] == str(employer.id)


@pytest.mark.asyncio
async def test_email_or_portal_share_is_not_on_the_portal(client, db_session, smtp_on, published):
    s = await _setup(client, db_session, n=1)
    employer = await _employer(db_session, s["job"].company_id)
    assert (await _share(client, s, "email")).status_code == 201
    assert (await _share(client, s, "other", repeat=True)).status_code == 201
    await login(client, employer)
    assert (await client.get(EMPLOYER)).json()["items"] == []


@pytest.mark.asyncio
async def test_other_share_is_log_only(client, db_session):
    s = await _setup(client, db_session, n=1)
    response = await _share(client, s, "other")
    assert response.status_code == 201 and response.json()["share"]["message"] is None


# --- recruiter response and feedback (S9) ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_records_response_and_feedback(client, db_session):
    s = await _setup(client, db_session, n=1)
    share = (await _share(client, s, "other")).json()["share"]
    url = f"{SHARES}/{share['id']}/items/{share['items'][0]['id']}"
    response = await client.patch(url, json={"response": "interview_requested", "feedback": "Wants a call on Monday"})
    assert response.status_code == 200, response.text
    assert response.json()["response"] == "interview_requested" and response.json()["feedback"] == "Wants a call on Monday"
    assert response.json()["responded_by"]["id"] == str(s["recruiter"].id)
    assert (await client.patch(url, json={})).status_code == 422
    assert (await client.patch(f"{SHARES}/{share['id']}/items/{uuid.uuid4()}", json={"response": "interested"})).status_code == 404
    company_list = (await client.get(f"/api/v1/recruiter/companies/{s['job'].company_id}/shares")).json()
    assert company_list["total"] == 1 and company_list["items"][0]["items"][0]["feedback"] == "Wants a call on Monday"
    await login(client, s["manager"])
    assert (await client.patch(url, json={"response": "interested"})).status_code == 403
    assert (await client.get(f"{REQ}/{s['job'].id}/shares")).status_code == 200  # the manager reads


# --- refusals ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_contact_of_another_company_is_422_and_inactive_contact_409(client, db_session, smtp_on, published):
    s = await _setup(client, db_session, n=1)
    other = Company(name=f"Elsewhere {_tag()}")
    db_session.add(other)
    await db_session.flush()
    foreign = await _contact(db_session, other.id)
    assert (await _share(client, s, contact_id=str(foreign.id))).status_code == 422
    assert (await _share(client, s, contact_id=None)).status_code == 422
    s["contact"].active = False
    await db_session.commit()
    assert (await _share(client, s)).status_code == 409


@pytest.mark.asyncio
async def test_a_non_opted_in_student_is_refused(client, db_session):
    s = await _setup(client, db_session, n=1)
    student = User(email=f"stu-{_tag()}@example.local", password_hash="x", full_name=f"Student {_tag()}", role="it_student", division="it", active=True)
    db_session.add(student)
    await db_session.commit()
    application = await student_application(db_session, s["job"].id, student)
    candidate_id = application.candidate_id
    await db_session.commit()
    response = await _share(client, s, "other", candidate_ids=[str(candidate_id)])
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejected_application_is_refused(client, db_session):
    s = await _setup(client, db_session, n=1)
    application = (await _add(client, s["job"], s["candidates"][0])).json()["application"]
    assert (await _move(client, application["id"], "rejected")).status_code == 200
    response = await _share(client, s, "other")
    assert response.status_code == 422 and s["candidates"][0].name in response.json()["detail"]


@pytest.mark.asyncio
async def test_repeat_share_warns_then_is_allowed(client, db_session):
    s = await _setup(client, db_session, n=2)
    assert (await _share(client, s, "other")).status_code == 201
    again = await _share(client, s, "other")
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert {d["code"] for d in detail["duplicates"]} == {c.candidate_code for c in s["candidates"]} and "already shared" in detail["message"]
    assert (await _share(client, s, "other", repeat=True)).status_code == 201


@pytest.mark.asyncio
async def test_email_needs_smtp(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    s = await _setup(client, db_session, n=1)
    assert (await _share(client, s)).status_code == 503


@pytest.mark.asyncio
async def test_closed_requirement_is_409(client, db_session):
    s = await _setup(client, db_session, n=1)
    s["job"].status = "closed"
    await db_session.commit()
    assert (await _share(client, s, "other")).status_code == 409


@pytest.mark.asyncio
async def test_validation(client, db_session):
    s = await _setup(client, db_session, n=1)
    assert (await _share(client, s, "other", candidate_ids=[])).status_code == 422
    assert (await _share(client, s, "other", candidate_ids=[str(uuid.uuid4()) for _ in range(21)])).status_code == 422
    assert (await _share(client, s, "fax")).status_code == 422
    assert (await _share(client, s, "other", note="x" * 501)).status_code == 422
    assert (await _share(client, s, "other", candidate_ids=[str(uuid.uuid4())])).status_code == 422


@pytest.mark.asyncio
async def test_roles_and_scope(client, db_session):
    s = await _setup(client, db_session, n=1)
    await make_recruiter(db_session, s["manager"])
    stranger = await make_recruiter(db_session)
    await login(client, stranger)
    assert (await _share(client, s, "other")).status_code == 404
    assert (await client.get(f"{REQ}/{s['job'].id}/shares")).status_code == 404
    await login(client, s["manager"])
    assert (await _share(client, s, "other")).status_code == 403
    await as_role(client, db_session, "it_student", "it")
    assert (await _share(client, s, "other")).status_code == 403
    assert (await client.get(EMPLOYER)).status_code == 403
