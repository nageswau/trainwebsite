"""hrc-023 (DEC-SCOPE-389, spec docs/superpowers/specs/2026-11-04-hrc-023-website-registration-intake-design.md): a website job application
or registration creates -- or matches by exact email -- one candidate with source Website and the visit's UTM (W1-W3, AC1/AC2), records the
consent (W4, AC3) and is visible to recruiters with no import (W9, AC4). Concurrency (W5), bot protection (W6) and merge (W10)."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, CandidateConsent, CareerApplication, RecCandidateSource, User
from app.notifications.phone import normalise_phone
from app.services import candidate_portal as portal
from app.services import website_intake as intake
from tests.rec038_helpers import _user, make_candidate, tag
from tests.tel026_helpers import headers
from tests.test_hrc_008_visibility import _job

pytestmark = pytest.mark.asyncio
REGISTER = "/api/v1/candidate/register"
VERIFY = "/api/v1/candidate/verify-email"
UTM = {"utm_source": "linkedin", "utm_medium": "social", "utm_campaign": "java-nov", "utm_term": "java", "utm_content": "banner-2"}


async def _staff(db) -> User:
    user = await _user(db, "placement_manager", "global")
    await db.commit()
    return user


def _ip() -> dict:
    return {"X-Forwarded-For": f"2001:db8::{uuid.uuid4().hex[:4]}:{uuid.uuid4().hex[:4]}"}


def _apply_body(**overrides) -> dict:
    return {"full_name": "Meera Website", "email": f"{tag('w23-')}@example.com", "phone": None, "resume_url": "/local-files/career-resumes/x.pdf",
            "cover_note": "Hello", "consent_version": portal.CONSENT_VERSION, "utm": UTM, **overrides}  # fmt: skip


async def _apply(client, job_id, ip: dict | None = None, **overrides):
    return await client.post(f"/api/v1/public/jobs/{job_id}/apply", json=_apply_body(**overrides), headers=ip or _ip())


async def _candidate_by_email(db, email: str) -> Candidate | None:
    return await db.scalar(select(Candidate).where(func.lower(Candidate.email) == email.lower()))


async def _source_name(db, candidate: Candidate) -> str:
    return await db.scalar(select(RecCandidateSource.name).where(RecCandidateSource.id == candidate.source_id))


# --- W1 ------------------------------------------------------------------------------------------------------------------------------
async def test_utm_keeps_the_five_standard_keys_trimmed_and_capped():
    assert intake.clean_utm({"utm_source": "  google ", "utm_medium": "", "gclid": "x", "utm_term": "t" * 300, "utm_content": 5}) == {
        "utm_source": "google", "utm_term": "t" * 100}  # fmt: skip
    assert intake.clean_utm(None) is None and intake.clean_utm("nope") is None and intake.clean_utm({"other": "x"}) is None


# --- AC1 / W3 / W4: a job application creates a Website candidate with UTM and consent ---------------------------------------------
async def test_a_job_application_creates_a_website_candidate_with_utm_and_consent(client, db_session):
    job = await _job(db_session)
    body = _apply_body(phone="+91 90000 1" + str(uuid.uuid4().int)[:4])
    response = await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=_ip())
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "tracking_code", "status"}  # W7: nothing about the candidate
    candidate = await _candidate_by_email(db_session, body["email"])
    assert candidate is not None and await _source_name(db_session, candidate) == "Website"
    assert candidate.source_detail == "Job application" and candidate.utm == UTM and candidate.email_verified_at is None
    assert candidate.created_by_user_id is None and candidate.user_id is None and candidate.mobile_normalized
    assert candidate.opted_in is True  # AC3: a new candidate who ticked the consent joins the pool
    consent = await db_session.scalar(select(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id))
    assert consent.action == "opt_in" and consent.consent_version == portal.CONSENT_VERSION and consent.user_id is None
    application = await db_session.scalar(select(CareerApplication).where(CareerApplication.tracking_code == response.json()["tracking_code"]))
    assert application.candidate_id == candidate.id and application.utm == UTM and application.consent_version == portal.CONSENT_VERSION
    assert application.consented_at is not None


async def test_without_consent_the_application_still_creates_a_candidate_outside_the_pool(client, db_session):
    """W4: the consent is optional in the API (older clients); a wrong version is refused."""
    job = await _job(db_session)
    body = _apply_body(consent_version=None, utm=None)
    assert (await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=_ip())).status_code == 201
    candidate = await _candidate_by_email(db_session, body["email"])
    assert candidate.opted_in is False and candidate.utm is None
    assert not (await db_session.scalars(select(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id))).all()
    wrong = await _apply(client, job.id, consent_version="old-v0")
    assert wrong.status_code == 422 and "consent" in wrong.json()["detail"]


# --- AC2 / W3: a second submission with the same email matches; the matched record is not changed ----------------------------------
async def test_the_same_email_matches_and_never_changes_the_existing_candidate(client, db_session):
    job, other_job = await _job(db_session), await _job(db_session)
    recruiter = await _staff(db_session)
    existing = await make_candidate(db_session, recruiter)
    existing.opted_in = False
    await db_session.commit()
    before = (existing.name, existing.source_id, existing.opted_in)
    for target in (job, other_job):
        response = await _apply(client, target.id, email=existing.email.upper(), full_name="Somebody Else")
        assert response.status_code == 201, response.text
    await db_session.refresh(existing)
    assert (existing.name, existing.source_id, existing.opted_in) == before  # anti-goal: an unverified form changes nothing
    assert await db_session.scalar(select(func.count()).select_from(Candidate).where(func.lower(Candidate.email) == existing.email.lower())) == 1
    linked = (await db_session.scalars(select(CareerApplication.candidate_id).where(func.lower(CareerApplication.email) == existing.email.lower()))).all()
    assert linked == [existing.id, existing.id]
    assert not (await db_session.scalars(select(CandidateConsent).where(CandidateConsent.candidate_id == existing.id))).all()


async def test_a_merged_candidate_is_followed_to_its_survivor(client, db_session):
    job = await _job(db_session)
    recruiter = await _staff(db_session)
    survivor = await make_candidate(db_session, recruiter)
    victim = await make_candidate(db_session, recruiter)
    now = datetime.now(UTC)
    victim.merged_into_id, victim.merged_at, victim.merged_by_user_id, victim.archived_at = survivor.id, now, recruiter.id, now
    await db_session.commit()
    assert (await _apply(client, job.id, email=victim.email)).status_code == 201
    application = await db_session.scalar(select(CareerApplication).where(func.lower(CareerApplication.email) == victim.email.lower()))
    assert application.candidate_id == survivor.id


async def test_a_phone_held_by_another_candidate_is_left_off_and_never_matches(client, db_session):
    job = await _job(db_session)
    recruiter = await _staff(db_session)
    mobile = "+91 98" + str(uuid.uuid4().int)[:8]
    holder = await make_candidate(db_session, recruiter, mobile=mobile, mobile_normalized=normalise_phone(mobile))
    await db_session.commit()
    body = _apply_body(phone=mobile)
    assert (await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=_ip())).status_code == 201
    created = await _candidate_by_email(db_session, body["email"])
    assert created.id != holder.id and created.mobile is None and created.mobile_normalized is None


# --- W5: two submissions in the same second make one candidate ---------------------------------------------------------------------
async def test_concurrent_submissions_make_one_candidate(client, db_session):
    job = await _job(db_session)
    email = f"{tag('w23race-')}@example.com"
    responses = await asyncio.gather(*(_apply(client, job.id, email=email) for _ in range(3)))
    assert [r.status_code for r in responses] == [201, 201, 201]
    assert await db_session.scalar(select(func.count()).select_from(Candidate).where(func.lower(Candidate.email) == email)) == 1


# --- W6: honeypot and per-IP throttle ----------------------------------------------------------------------------------------------
async def test_the_honeypot_answers_normally_and_stores_nothing(client, db_session):
    job = await _job(db_session)
    body = _apply_body(website="http://spam.example")
    response = await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=_ip())
    assert response.status_code == 201 and set(response.json()) == {"id", "tracking_code", "status"}
    assert await _candidate_by_email(db_session, body["email"]) is None
    assert await db_session.scalar(select(CareerApplication).where(CareerApplication.email == body["email"])) is None


async def test_applications_are_throttled_per_network(client, db_session):
    job = await _job(db_session)
    ip = _ip()
    for _ in range(intake.APPLY_MAX_PER_IP):
        assert (await _apply(client, job.id, ip=ip)).status_code == 201
    refused = await _apply(client, job.id, ip=ip)
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 0
    assert (await _apply(client, job.id)).status_code == 201  # another network is unaffected


async def test_overlong_fields_are_a_422_not_a_server_error(client, db_session):
    job = await _job(db_session)
    assert (await _apply(client, job.id, full_name="x" * 161)).status_code == 422
    assert (await _apply(client, job.id, email="not-an-email")).status_code == 422
    assert (await _apply(client, job.id, phone="12")).status_code == 422


# --- AC1 / W2: the registration form's UTM reaches the verified candidate, source Website ------------------------------------------
async def test_a_registration_creates_a_website_candidate_with_utm_on_verification(client, db_session):
    email = f"{tag('w23reg-')}@example.com"
    body = {"full_name": "Ravi Register", "email": email, "password": "Candidate@12345", "consent_version": portal.CONSENT_VERSION, "utm": UTM}
    out = (await client.post(REGISTER, json=body, headers=_ip())).json()
    assert await _candidate_by_email(db_session, email) is None  # created only once the email is verified (C4)
    assert (await client.post(VERIFY, json={"token": out["development_verification_token"]})).status_code == 200
    candidate = await _candidate_by_email(db_session, email)
    assert await _source_name(db_session, candidate) == "Website" and candidate.source_detail == "Website registration"
    assert candidate.utm == UTM and candidate.opted_in is True


async def test_a_second_registration_with_the_same_email_matches(client, db_session):
    """AC2: an applicant who registers later claims the website candidate their application created -- one record."""
    job = await _job(db_session)
    email = f"{tag('w23both-')}@example.com"
    assert (await _apply(client, job.id, email=email)).status_code == 201
    first = await _candidate_by_email(db_session, email)
    body = {"full_name": "Meera Website", "email": email, "password": "Candidate@12345", "consent_version": portal.CONSENT_VERSION}
    out = (await client.post(REGISTER, json=body, headers=_ip())).json()
    assert (await client.post(VERIFY, json={"token": out["development_verification_token"]})).status_code == 200
    user = await db_session.scalar(select(User).where(User.email == email))
    await db_session.refresh(first)
    assert first.user_id == user.id
    assert await db_session.scalar(select(func.count()).select_from(Candidate).where(func.lower(Candidate.email) == email)) == 1


# --- AC4 / W9: recruiters see the website candidate and its applications -----------------------------------------------------------
async def test_recruiters_see_the_website_candidate_with_no_import(client, db_session):
    job = await _job(db_session)
    body = _apply_body()
    application = (await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=_ip())).json()
    candidate = await _candidate_by_email(db_session, body["email"])
    recruiter = await _staff(db_session)
    listed = await client.get("/api/v1/recruiter/candidates", params={"q": candidate.candidate_code}, headers=headers(recruiter))
    assert listed.status_code == 200, listed.text
    assert [row["source"]["name"] for row in listed.json()["items"] if row["id"] == str(candidate.id)] == ["Website"]
    detail = (await client.get(f"/api/v1/recruiter/candidates/{candidate.id}", headers=headers(recruiter))).json()
    assert detail["utm"] == UTM
    assert detail["website_applications"] == [
        {"job_title": job.title, "tracking_code": application["tracking_code"], "status": "submitted", "created_at": detail["website_applications"][0]["created_at"]}
    ]


# --- logging/audit carry no contact data -------------------------------------------------------------------------------------------
async def test_the_audit_row_carries_ids_and_the_ip_only(client, db_session):
    job = await _job(db_session)
    body = _apply_body()
    response = await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=_ip())
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "career.apply", AuditLog.entity_id == response.json()["id"]))
    assert row is not None and body["email"] not in str(row.metadata_json) and set(row.metadata_json) <= {"ip", "candidate_id", "outcome"}
