"""hrc-022 (DEC-SCOPE-386, spec docs/superpowers/specs/2026-11-04-hrc-022-candidate-portal-identity-design.md): an external candidate
registers, verifies and signs in (C2-C6, AC1), sees only their own record (C10, AC2), edits only the allow-listed fields (C7/C11, AC3),
changes their email only through a verified link (C9, AC4), the throttles answer 429 (AC5) and the privacy consent (C12)."""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, CandidateConsent, CandidateSelfServiceSetting, User, UserVerificationToken
from app.services import candidate_portal as portal
from tests.rec038_helpers import _recruiter, _user, make_candidate, tag
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
REGISTER = "/api/v1/candidate/register"
VERIFY = "/api/v1/candidate/verify-email"
RESEND = "/api/v1/candidate/resend-verification"
ME = "/api/v1/candidate/me"
EMAIL = "/api/v1/candidate/me/email"
PRIVACY = "/api/v1/candidate/me/privacy"
SETTINGS = "/api/v1/recruiter/candidate-self-service-settings"
LOGIN = "/api/v1/auth/login"
PASSWORD = "Candidate@12345"


def _ip() -> dict:
    return {"X-Forwarded-For": f"2001:db8::{uuid.uuid4().hex[:4]}:{uuid.uuid4().hex[:4]}"}


def _body(**overrides) -> dict:
    return {"full_name": "Asha Candidate", "email": f"{tag('c22-')}@example.com", "phone": "+91 99887 76655", "password": PASSWORD,
            "consent_version": portal.CONSENT_VERSION, **overrides}  # fmt: skip


async def _register(client, **overrides) -> tuple[dict, dict]:
    body = _body(**overrides)
    response = await client.post(REGISTER, json=body, headers=_ip())
    assert response.status_code == 202, response.text
    return body, response.json()


async def _verified(client, db, **overrides) -> tuple[User, Candidate]:
    body, out = await _register(client, **overrides)
    assert (await client.post(VERIFY, json={"token": out["development_verification_token"]})).status_code == 200
    user = await db.scalar(select(User).where(User.email == body["email"].lower()))
    await db.refresh(user)
    candidate = await db.scalar(select(Candidate).where(Candidate.user_id == user.id))
    return user, candidate


@pytest_asyncio.fixture
async def default_allow_list(db_session):
    """The allow-list is one global row: each test that depends on it starts from the default and puts the stored value back."""
    row = await db_session.get(CandidateSelfServiceSetting, 1)
    before = list(row.fields) if row else None
    if row is None:
        row = CandidateSelfServiceSetting(id=1, fields=list(portal.DEFAULT_FIELDS))
        db_session.add(row)
    row.fields = list(portal.DEFAULT_FIELDS)
    await db_session.commit()
    yield
    row = await db_session.get(CandidateSelfServiceSetting, 1)
    await db_session.refresh(row)
    row.fields = before if before is not None else list(portal.DEFAULT_FIELDS)
    await db_session.commit()


# --- AC1: register, verify, log in -----------------------------------------------------------------------------------------------
async def test_register_verify_and_log_in(client, db_session):
    body, out = await _register(client)
    assert out["accepted"] is True and out["development_verification_token"]
    user = await db_session.scalar(select(User).where(User.email == body["email"]))
    assert user.role == "candidate" and user.division == "it" and user.email_verified is False
    assert "edusphere_access" not in (await client.post(REGISTER, json=_body(), headers=_ip())).cookies

    refused = await client.post(LOGIN, json={"email": body["email"], "password": PASSWORD, "division": "it"})
    assert refused.status_code == 403 and "Verify your email" in refused.json()["detail"]

    verified = await client.post(VERIFY, json={"token": out["development_verification_token"]})
    assert verified.status_code == 200 and verified.json()["purpose"] == "verify_email"
    login = await client.post(LOGIN, json={"email": body["email"], "password": PASSWORD, "division": "it"})
    assert login.status_code == 200 and login.json()["user"]["role"] == "candidate"

    await db_session.refresh(user)
    candidate = await db_session.scalar(select(Candidate).where(Candidate.user_id == user.id))
    assert user.email_verified and candidate.opted_in and candidate.email == body["email"] and candidate.email_verified_at is not None
    consent = await db_session.scalar(select(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id))
    assert consent.action == "opt_in" and consent.consent_version == portal.CONSENT_VERSION
    assert (await client.post(VERIFY, json={"token": out["development_verification_token"]})).status_code == 400  # single use


async def test_a_bad_token_is_one_generic_400(client):
    response = await client.post(VERIFY, json={"token": "not-a-token"})
    assert response.status_code == 400 and response.json()["detail"] == portal.INVALID_TOKEN


async def test_registration_needs_consent_and_a_long_password(client):
    assert (await client.post(REGISTER, json=_body(consent_version="v0"), headers=_ip())).status_code == 422
    assert (await client.post(REGISTER, json=_body(password="short"), headers=_ip())).status_code == 422


async def test_an_existing_email_answers_the_same_and_creates_nothing(client, db_session):
    staff = await _user(db_session, "placement_team", "it")
    await db_session.commit()
    _, out = await _register(client, email=staff.email.upper())
    assert out == {"accepted": True}
    await db_session.refresh(staff)
    assert staff.role == "placement_team"
    assert await db_session.scalar(select(func.count()).select_from(User).where(func.lower(User.email) == staff.email)) == 1


async def test_two_simultaneous_signups_for_one_email_make_one_account(client, db_session):
    body = _body()
    first, second = await asyncio.gather(client.post(REGISTER, json=body, headers=_ip()), client.post(REGISTER, json=body, headers=_ip()))
    assert first.status_code == second.status_code == 202
    assert await db_session.scalar(select(func.count()).select_from(User).where(User.email == body["email"])) == 1


async def test_verification_claims_the_recruiter_record_by_email_never_by_phone(client, db_session):
    manager = await _user(db_session, "placement_manager", "global")
    recruiter = await _recruiter(db_session, manager)
    by_email = await make_candidate(db_session, recruiter)
    phone = f"+91 9{uuid.uuid4().int % 10**9:09d}"
    by_phone = await make_candidate(db_session, recruiter, mobile=phone, mobile_normalized=phone.replace(" ", ""))
    await db_session.commit()
    user, candidate = await _verified(client, db_session, email=by_email.email.upper(), phone=phone)
    assert candidate.id == by_email.id and candidate.user_id == user.id
    await db_session.refresh(by_phone)
    assert by_phone.user_id is None


# --- AC5: throttles ----------------------------------------------------------------------------------------------------------------
async def test_registration_is_throttled_per_network(client):
    ip = _ip()
    for _ in range(portal.REGISTER_MAX_PER_IP):
        assert (await client.post(REGISTER, json=_body(), headers=ip)).status_code == 202
    blocked = await client.post(REGISTER, json=_body(), headers=ip)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0


async def test_resend_is_enumeration_safe_and_capped(client, db_session):
    body, _ = await _register(client)
    assert (await client.post(RESEND, json={"email": f"{tag('nobody-')}@example.com"})).json() == {"accepted": True}
    for _ in range(portal.EMAILS_PER_WINDOW + 1):
        assert (await client.post(RESEND, json={"email": body["email"]})).status_code == 202
    user = await db_session.scalar(select(User).where(User.email == body["email"]))
    issued = await db_session.scalar(select(func.count()).select_from(UserVerificationToken).where(UserVerificationToken.user_id == user.id))
    assert issued == portal.EMAILS_PER_WINDOW  # the registration's link plus the resends, never more


# --- AC2: own record only ----------------------------------------------------------------------------------------------------------
async def test_each_candidate_sees_only_their_own_profile(client, db_session, default_allow_list):
    one, one_candidate = await _verified(client, db_session)
    two, _ = await _verified(client, db_session)
    out = (await client.get(ME, headers=headers(one))).json()
    assert out["candidate_code"] == one_candidate.candidate_code and out["email"] == one.email
    assert set(out["editable"]) == set(portal.DEFAULT_FIELDS) and "name" not in out["editable"]
    assert (await client.get(ME, headers=headers(two))).json()["candidate_code"] != out["candidate_code"]
    assert (await client.get(ME)).status_code == 401
    staff = await _user(db_session, "placement_team", "it")
    await db_session.commit()
    assert (await client.get(ME, headers=headers(staff))).status_code == 403


# --- AC3: allow-listed fields only -------------------------------------------------------------------------------------------------
async def test_a_candidate_edits_only_allow_listed_fields(client, db_session, default_allow_list):
    user, candidate = await _verified(client, db_session)
    saved = await client.patch(ME, json={"city": "Pune", "notice_days": 30}, headers=headers(user))
    assert saved.status_code == 200 and saved.json()["fields"]["city"] == "Pune"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(candidate.id), AuditLog.action == "candidate.update"))
    assert audit.metadata_json["self_service"] is True and audit.metadata_json["changes"]["city"] == [None, "Pune"]

    name = await client.patch(ME, json={"name": "Someone Else"}, headers=headers(user))
    assert name.status_code == 403 and "Name" in name.json()["detail"]
    for key, value in (("email", "x@example.com"), ("status", "placed"), ("expected_salary", 1), ("mobile", "+91 90000 00000")):
        assert (await client.patch(ME, json={key: value}, headers=headers(user))).status_code == 422, key
    assert (await client.patch(ME, json={"notice_days": 999}, headers=headers(user))).status_code == 422
    await db_session.refresh(candidate)
    assert candidate.name == "Asha Candidate" and candidate.status == "available"


async def test_the_allow_list_is_configured_by_managers(client, db_session, default_allow_list):
    manager = await _user(db_session, "placement_manager", "global")
    recruiter = await _recruiter(db_session, manager)
    await db_session.commit()
    user, _ = await _verified(client, db_session)
    assert (await client.get(SETTINGS, headers=headers(recruiter))).json()["can_edit"] is False
    assert (await client.put(SETTINGS, json={"fields": ["name"]}, headers=headers(recruiter))).status_code == 403
    assert (await client.put(SETTINGS, json={"fields": ["status"]}, headers=headers(manager))).status_code == 422
    saved = await client.put(SETTINGS, json={"fields": ["name", "city"]}, headers=headers(manager))
    assert saved.status_code == 200 and saved.json()["fields"] == ["name", "city"]
    assert (await client.patch(ME, json={"name": "Asha K"}, headers=headers(user))).status_code == 200
    assert (await client.patch(ME, json={"notice_days": 10}, headers=headers(user))).status_code == 403
    assert (await client.get(SETTINGS, headers=headers(user))).status_code == 403


# --- AC4: a changed email is verified first ----------------------------------------------------------------------------------------
async def test_an_email_change_waits_for_the_new_address(client, db_session):
    user, candidate = await _verified(client, db_session)
    old = user.email
    assert (await client.post(EMAIL, json={"new_email": "x@example.com", "current_password": "wrong-password"}, headers=headers(user))).status_code == 400
    assert (await client.post(EMAIL, json={"new_email": old, "current_password": PASSWORD}, headers=headers(user))).status_code == 422
    new = f"{tag('new-')}@example.com"
    out = (await client.post(EMAIL, json={"new_email": new.upper(), "current_password": PASSWORD}, headers=headers(user))).json()
    assert out["accepted"] and out["development_verification_token"]
    assert (await client.get(ME, headers=headers(user))).json()["pending_email"] == new
    await db_session.refresh(user)
    assert user.email == old  # nothing replaced yet
    confirmed = await client.post(VERIFY, json={"token": out["development_verification_token"]})
    assert confirmed.status_code == 200 and confirmed.json()["purpose"] == "email_change"
    await db_session.refresh(user)
    await db_session.refresh(candidate)
    assert user.email == new and candidate.email == new and candidate.email_verified_at is not None
    assert (await client.post(LOGIN, json={"email": new, "password": PASSWORD, "division": "it"})).status_code == 200


async def test_an_address_in_use_is_accepted_silently(client, db_session):
    user, _ = await _verified(client, db_session)
    other = await _user(db_session, "placement_team", "it")
    await db_session.commit()
    out = (await client.post(EMAIL, json={"new_email": other.email, "current_password": PASSWORD}, headers=headers(user))).json()
    assert out == {"accepted": True}


async def test_email_change_requests_are_throttled(client, db_session):
    user, _ = await _verified(client, db_session)
    for _ in range(portal.EMAILS_PER_WINDOW):
        assert (await client.post(EMAIL, json={"new_email": f"{tag('n-')}@example.com", "current_password": PASSWORD}, headers=headers(user))).status_code == 202
    blocked = await client.post(EMAIL, json={"new_email": f"{tag('n-')}@example.com", "current_password": PASSWORD}, headers=headers(user))
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


async def test_a_superseded_change_link_is_dead(client, db_session):
    user, _ = await _verified(client, db_session)
    first = (await client.post(EMAIL, json={"new_email": f"{tag('a-')}@example.com", "current_password": PASSWORD}, headers=headers(user))).json()
    await client.post(EMAIL, json={"new_email": f"{tag('b-')}@example.com", "current_password": PASSWORD}, headers=headers(user))
    assert (await client.post(VERIFY, json={"token": first["development_verification_token"]})).status_code == 400


# --- C12: privacy ------------------------------------------------------------------------------------------------------------------
async def test_a_candidate_leaves_and_rejoins_the_pool(client, db_session):
    user, candidate = await _verified(client, db_session)
    state = (await client.get(PRIVACY, headers=headers(user))).json()
    assert state["opted_in"] is True and state["consent"]["version"] == portal.CONSENT_VERSION and len(state["history"]) == 1
    left = await client.put(PRIVACY, json={"opted_in": False, "consent_version": portal.CONSENT_VERSION}, headers=headers(user))
    assert left.status_code == 200 and left.json()["opted_in"] is False
    await db_session.refresh(candidate)
    assert candidate.opted_in is False
    back = await client.put(PRIVACY, json={"opted_in": True, "consent_version": portal.CONSENT_VERSION}, headers=headers(user))
    assert back.json()["opted_in"] is True and [h["action"] for h in back.json()["history"]] == ["opt_in", "opt_out", "opt_in"]
