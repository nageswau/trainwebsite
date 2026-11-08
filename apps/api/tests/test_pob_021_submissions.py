"""pob-021 -- the submission record (DEC-SCOPE-430 B1-B13; AC1-AC5): a SUB- code per shared candidate, consent and interest gates, the
same-client duplicate warning, the skills-match block in the summary, the SLA follow-up and the logged status workflow. The shared test
database is never truncated, so every value is unique per test."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, CandidateSkill, Company, JobSkill, ProfileShare, ProfileShareItem, RecruiterFollowUp, RecruiterMessage, Skill, SkillCategory
from app.services import candidates as candidate_svc
from tests.test_rec_017_tracking import _requirement, _tag
from tests.test_rec_019_shares import EMPLOYER, SHARES, _body, _employer, _setup, published, smtp_on  # noqa: F401

CONSENT = {"consent_confirmed": True, "consent_reference": "Phone call on 8 Nov", "interest_confirmed": True}


def _item_url(share: dict, item: dict) -> str:
    return f"{SHARES}/{share['id']}/items/{item['id']}"


async def _submit(client, s, channel="other", **over):
    return await client.post(SHARES, json=_body(s, channel, **(CONSENT | over)))


# --- AC1: consent ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_without_consent_or_interest_a_submission_is_409_and_with_them_each_candidate_gets_a_sub_code(client, db_session):
    s = await _setup(client, db_session, n=2)
    bare = await client.post(SHARES, json=_body(s, "other"))
    assert bare.status_code == 409 and "consent" in bare.json()["detail"].lower()
    half = await client.post(SHARES, json=_body(s, "other", consent_confirmed=True, interest_confirmed=True))
    assert half.status_code == 409
    no_interest = await client.post(SHARES, json=_body(s, "other", consent_confirmed=True, consent_reference="Call"))
    assert no_interest.status_code == 409 and "interest" in no_interest.json()["detail"].lower()
    assert (await db_session.scalar(select(ProfileShare.id).where(ProfileShare.job_id == s["job"].id))) is None
    response = await _submit(client, s)
    assert response.status_code == 201, response.text
    items = response.json()["share"]["items"]
    codes = {i["submission_code"] for i in items}
    assert len(codes) == 2 and all(c.startswith("SUB-") for c in codes)
    assert {i["status"] for i in items} == {"submitted"} and {i["consent_reference"] for i in items} == {"Phone call on 8 Nov"}


@pytest.mark.asyncio
async def test_required_profile_fields_and_the_hard_filters_gate_a_submission(client, db_session):
    s = await _setup(client, db_session, n=1)
    person = s["candidates"][0]
    person.location = None
    await db_session.commit()
    missing = await _submit(client, s)
    assert missing.status_code == 422 and person.candidate_code in missing.json()["detail"] and "location" in missing.json()["detail"].lower()
    person.location = "Delhi"
    s["job"].match_hard_location = True  # the job is in Pune
    await db_session.commit()
    barred = await _submit(client, s)
    assert barred.status_code == 422 and "eligib" in barred.json()["detail"].lower()


# --- AC2: duplicate to the same client --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_duplicate_to_the_same_client_on_another_requirement_warns_and_repeat_submits(client, db_session):
    s = await _setup(client, db_session, n=1)
    assert (await _submit(client, s)).status_code == 201
    company = await db_session.get(Company, s["job"].company_id)
    other = await _requirement(db_session, s["recruiter"], company=company)
    body = _body(s, "other", **CONSENT) | {"requirement_id": str(other.id)}
    warned = await client.post(SHARES, json=body)
    assert warned.status_code == 409 and warned.json()["detail"]["duplicates"][0]["id"] == str(s["candidates"][0].id)
    assert (await client.post(SHARES, json=body | {"repeat": True})).status_code == 201


# --- AC3: the match block ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_summary_carries_the_skills_match_block(client, db_session, smtp_on, published):  # noqa: F811
    s = await _setup(client, db_session, n=1)
    category = await db_session.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    java, kafka = Skill(name=f"Java {_tag()}", category_id=category), Skill(name=f"Kafka {_tag()}", category_id=category)
    db_session.add_all([java, kafka])
    await db_session.flush()
    db_session.add_all([
        JobSkill(job_id=s["job"].id, skill_id=java.id, name=java.name, kind="required", weight=2, position=0),
        JobSkill(job_id=s["job"].id, skill_id=kafka.id, name=kafka.name, kind="preferred", weight=1, position=1),
        CandidateSkill(candidate_id=s["candidates"][0].id, skill_id=java.id, level="advanced", added_by_user_id=s["recruiter"].id, status="claimed"),
    ])  # fmt: skip
    await db_session.commit()
    response = await _submit(client, s, channel="email")
    assert response.status_code == 201, response.text
    match = response.json()["share"]["items"][0]["match"]
    assert match["required_matched"] == [java.name] and match["preferred_missing"] == [kafka.name] and isinstance(match["score"], int)
    message = await db_session.get(RecruiterMessage, uuid.UUID(response.json()["share"]["message"]["id"]))
    assert "Skills match: 1 of 1 required" in message.body and f"gaps: {kafka.name}" in message.body


# --- AC4: the SLA follow-up ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_submitting_creates_the_client_follow_up_at_the_company_sla(client, db_session):
    s = await _setup(client, db_session, n=2)
    saved = await client.patch(f"/api/v1/recruiter/companies/{s['job'].company_id}", json={"submission_sla_hours": 24})
    assert saved.status_code == 200, saved.text
    assert (await client.patch(f"/api/v1/recruiter/companies/{s['job'].company_id}", json={"submission_sla_hours": 0})).status_code == 422
    created = await client.post("/api/v1/recruiter/companies", json={"name": f"SLA Co {_tag()} Ltd", "submission_sla_hours": 72})  # QA21-01
    assert created.status_code == 201 and created.json()["company"]["submission_sla_hours"] == 72, created.text
    response = await _submit(client, s)
    assert response.status_code == 201, response.text
    share = await db_session.get(ProfileShare, uuid.UUID(response.json()["share"]["id"]))
    follow_up = await db_session.get(RecruiterFollowUp, share.follow_up_id)
    assert follow_up.reason == "profile_feedback" and follow_up.job_id == s["job"].id and follow_up.company_id == s["job"].company_id
    assert follow_up.due_at - share.created_at == timedelta(hours=24)
    assert response.json()["share"]["follow_up"]["id"] == str(follow_up.id)


# --- AC5: status workflow, logged ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_status_changes_are_checked_and_logged(client, db_session):
    s = await _setup(client, db_session, n=1)
    share = (await _submit(client, s)).json()["share"]
    url = _item_url(share, share["items"][0])
    acknowledged = await client.patch(url, json={"acknowledged": True})
    assert acknowledged.status_code == 200 and acknowledged.json()["acknowledged_at"] and acknowledged.json()["status"] == "client_reviewing"
    assert (await client.patch(url, json={"status": "rejected"})).status_code == 422  # a rejection needs its reason
    assert (await client.patch(url, json={"status": "rejected", "rejection_reason": "made_up"})).status_code == 422
    rejected = await client.patch(url, json={"status": "rejected", "rejection_reason": "skills_mismatch", "next_action": "Find another", "next_action_on": "2030-01-05"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected" and rejected.json()["rejection_reason"] == "skills_mismatch" and rejected.json()["next_action_on"] == "2030-01-05"
    assert (await client.patch(url, json={"status": "shortlisted"})).status_code == 409  # a closed submission stays closed
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "submission.status", AuditLog.entity_id == share["items"][0]["id"]).order_by(AuditLog.created_at))).all()
    assert [(r.metadata_json["from"], r.metadata_json["to"]) for r in rows] == [("submitted", "client_reviewing"), ("client_reviewing", "rejected")]


@pytest.mark.asyncio
async def test_an_employer_portal_response_maps_onto_the_submission_status(client, db_session):
    s = await _setup(client, db_session, n=1)
    employer = await _employer(db_session, s["job"].company_id)
    share = (await _submit(client, s, channel="portal")).json()["share"]
    from tests.rec001_helpers import login

    await login(client, employer)
    listed = (await client.get(EMPLOYER)).json()["items"][0]
    assert listed["submission_code"].startswith("SUB-") and listed["match"] is not None
    assert (await client.patch(f"{EMPLOYER}/{listed['id']}", json={"response": "interested"})).status_code == 200
    item = await db_session.get(ProfileShareItem, uuid.UUID(share["items"][0]["id"]), populate_existing=True)
    assert item.status == "shortlisted"


# --- summary mode and compensation ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_anonymised_client_summary_drops_the_name_and_the_resume(client, db_session, smtp_on, published):  # noqa: F811
    s = await _setup(client, db_session, n=1)
    response = await _submit(client, s, channel="email", detail="anonymised")
    assert response.status_code == 201, response.text
    share = response.json()["share"]
    assert share["detail"] == "anonymised" and share["items"][0]["has_resume"] is False
    message = await db_session.get(RecruiterMessage, uuid.UUID(share["message"]["id"]))
    assert s["candidates"][0].name not in message.body and s["candidates"][0].candidate_code in message.body


@pytest.mark.asyncio
async def test_compensation_is_sent_only_when_ticked_and_granted(client, db_session, smtp_on, published, monkeypatch):  # noqa: F811
    s = await _setup(client, db_session, n=1)
    s["candidates"][0].expected_salary, s["candidates"][0].expected_salary_currency, s["candidates"][0].expected_salary_period = 900000, "INR", "year"
    await db_session.commit()
    plain = await _submit(client, s, channel="email")
    assert "Expected salary" not in (await db_session.get(RecruiterMessage, uuid.UUID(plain.json()["share"]["message"]["id"]))).body
    ticked = await _submit(client, s, channel="email", include_compensation=True, repeat=True)
    assert ticked.status_code == 201 and ticked.json()["share"]["compensation_included"] is True
    assert "Expected salary: INR 900000 per year" in (await db_session.get(RecruiterMessage, uuid.UUID(ticked.json()["share"]["message"]["id"]))).body

    async def no_grant(db, user):
        return False

    monkeypatch.setattr(candidate_svc, "sees_compensation", no_grant)
    refused = await _submit(client, s, channel="email", include_compensation=True, repeat=True)
    assert refused.status_code == 403


# --- the migration ----------------------------------------------------------------------------------------------------------------------------
def test_the_migration_chains_and_freezes_the_checks():
    import importlib.util
    import pathlib

    from app import models

    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0313_submissions.py"
    spec = importlib.util.spec_from_file_location("m0313", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "0313_submissions" and migration.down_revision == "0312_placements"
    assert migration.ITEM_CHECKS == models.SUBMISSION_CHECKS
    assert migration.DETAIL_NEW == models.PROFILE_SHARE_VENDOR_CHECKS["ck_profile_shares_recipient_detail"]
    assert migration.SLA_CHECK == models.COMPANY_CHECKS["ck_companies_submission_sla"]
