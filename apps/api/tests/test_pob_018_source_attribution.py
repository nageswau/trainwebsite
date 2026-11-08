"""pob-018 -- source attribution, verification and outreach permission (DEC-SCOPE-428 A1-A12; AC1-AC3). The shared test database is
never truncated, so every value is unique per test."""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, Company, RecCandidateSource
from app.services import candidate_privacy
from tests.rec001_helpers import as_role, login, make_recruiter
from tests.test_rec_017_tracking import _candidate, _requirement, _tag, _team
from tests.test_rec_019_shares import SUBMIT, _contact

URL = "/api/v1/recruiter/candidates"
SHARES = "/api/v1/recruiter/shares"
IST = ZoneInfo("Asia/Kolkata")
pytestmark = pytest.mark.asyncio


def _today() -> date:
    return datetime.now(IST).date()


async def _source_id(db, name="Referral") -> str:
    return str(await db.scalar(select(RecCandidateSource.id).where(func.lower(RecCandidateSource.name) == name.lower())))


async def _create(client, db, **extra):
    body = {"name": f"Asha {_tag()}", "email": f"{_tag()}@example.com", "source_id": await _source_id(db), **extra}
    return await client.post(URL, json=body)


async def _vendor(db, recruiter, **extra) -> Company:
    company = Company(name=f"Vendor {_tag()}", partner_type="vendor", vendor_status="prospect", assigned_recruiter_user_id=recruiter.id, **extra)
    db.add(company)
    await db.commit()
    return company


# --- AC1 ---------------------------------------------------------------------------------------------------------------------------
async def test_ac1_a_new_candidate_has_a_source_and_a_date(client, db_session):
    await _team(client, db_session)
    created = await _create(client, db_session)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"]["name"] == "Referral"
    assert body["sourcing"]["source_date"] == _today().isoformat()
    listed = await client.get(URL, params={"q": body["candidate_code"]})
    assert listed.json()["items"][0]["source_date"] == _today().isoformat()


async def test_ac1_the_source_date_is_sent_or_edited_but_never_in_the_future(client, db_session):
    await _team(client, db_session)
    created = await _create(client, db_session, source_date="2026-03-01")
    assert created.json()["sourcing"]["source_date"] == "2026-03-01"
    future = (_today() + timedelta(days=1)).isoformat()
    refused = await client.patch(f"{URL}/{created.json()['id']}", json={"source_date": future})
    assert refused.status_code == 422 and "future" in refused.text
    edited = await client.patch(f"{URL}/{created.json()['id']}", json={"source_date": "2026-04-02"})
    assert edited.json()["sourcing"]["source_date"] == "2026-04-02"
    assert (await client.patch(f"{URL}/{created.json()['id']}", json={"source_date": None})).status_code == 422


async def test_the_new_catalogue_sources_exist(db_session):
    names = {n.lower() for n in (await db_session.scalars(select(RecCandidateSource.name))).all()}
    assert {"vendor", "website", "community", "institution"} <= names


# --- A3 attribution ----------------------------------------------------------------------------------------------------------------
async def test_referrer_vendor_and_portal_reference_are_recorded_and_audited(client, db_session):
    _, recruiter = await _team(client, db_session)
    referrer = await _candidate(db_session, recruiter)
    vendor = await _vendor(db_session, recruiter)
    created = await _create(client, db_session, referrer_name="Kiran (alumnus)", referrer_candidate_id=str(referrer.id), vendor_id=str(vendor.id),
                            portal_import_reference="Naukri export 2026-11-01 #44")  # fmt: skip
    assert created.status_code == 201, created.text
    sourcing = created.json()["sourcing"]
    assert sourcing["referrer_name"] == "Kiran (alumnus)"
    assert sourcing["referrer"] == {"id": str(referrer.id), "candidate_code": referrer.candidate_code, "name": referrer.name}
    assert sourcing["vendor"] == {"id": str(vendor.id), "name": vendor.name}
    assert sourcing["portal_import_reference"] == "Naukri export 2026-11-01 #44"
    cleared = await client.patch(f"{URL}/{created.json()['id']}", json={"vendor_id": None, "referrer_candidate_id": None})
    assert cleared.json()["sourcing"]["vendor"] is None and cleared.json()["sourcing"]["referrer"] is None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == created.json()["id"], AuditLog.action == "candidate.update"))
    assert {"vendor_id", "referrer_candidate_id"} <= set(audit.metadata_json["fields"])


async def test_a_vendor_must_be_a_vendor_in_scope_and_a_referrer_a_visible_other_candidate(client, db_session):
    manager, recruiter = await _team(client, db_session)
    client_company = Company(name=f"Client {_tag()}", assigned_recruiter_user_id=recruiter.id)
    db_session.add(client_company)
    other = await make_recruiter(db_session, manager)
    foreign_vendor = await _vendor(db_session, other)
    archived_vendor = await _vendor(db_session, recruiter, archived_at=datetime.now(IST))
    await db_session.commit()
    for vendor_id in (client_company.id, foreign_vendor.id, archived_vendor.id, uuid.uuid4()):
        refused = await _create(client, db_session, vendor_id=str(vendor_id))
        assert refused.status_code == 422 and "vendor" in refused.text.lower(), refused.text
    assert (await _create(client, db_session, referrer_candidate_id=str(uuid.uuid4()))).status_code == 422
    created = await _create(client, db_session)
    itself = await client.patch(f"{URL}/{created.json()['id']}", json={"referrer_candidate_id": created.json()["id"]})
    assert itself.status_code == 422


# --- AC2 verify --------------------------------------------------------------------------------------------------------------------
async def test_ac2_verify_sets_last_verified_on(client, db_session):
    _, recruiter = await _team(client, db_session)
    created = (await _create(client, db_session)).json()
    assert created["sourcing"]["last_verified_on"] is None
    verified = await client.post(f"{URL}/{created['id']}/verify")
    assert verified.status_code == 200, verified.text
    assert verified.json()["sourcing"]["last_verified_on"] == _today().isoformat()
    assert verified.json()["sourcing"]["last_verified_by"]["id"] == str(recruiter.id)
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.entity_id == created["id"], AuditLog.action == "candidate.verify"))


async def test_verify_is_for_writers_and_active_candidates(client, db_session):
    await _team(client, db_session)
    created = (await _create(client, db_session)).json()
    await client.post(f"{URL}/{created['id']}/archive")
    assert (await client.post(f"{URL}/{created['id']}/verify")).status_code == 409
    assert (await client.post(f"{URL}/{uuid.uuid4()}/verify")).status_code == 404
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.post(f"{URL}/{created['id']}/verify")).status_code == 403
    assert (await client.put(f"{URL}/{created['id']}/outreach", json={"status": "contacted"})).status_code == 403
    read = await client.get(f"{URL}/{created['id']}")
    assert read.status_code == 200 and read.json()["sourcing"]["outreach_status"] == "not_contacted"


# --- A4/A5 outreach ----------------------------------------------------------------------------------------------------------------
async def test_outreach_moves_and_the_permission_is_recorded_then_withdrawn(client, db_session):
    _, recruiter = await _team(client, db_session)
    created = (await _create(client, db_session)).json()
    assert created["sourcing"]["permitted"] is False
    contacted = await client.put(f"{URL}/{created['id']}/outreach", json={"status": "contacted"})
    assert contacted.status_code == 200 and contacted.json()["sourcing"]["outreach_status"] == "contacted"
    assert contacted.json()["sourcing"]["permission"] is None
    missing = await client.put(f"{URL}/{created['id']}/outreach", json={"status": "consented"})
    assert missing.status_code == 422
    future = (_today() + timedelta(days=1)).isoformat()
    assert (await client.put(f"{URL}/{created['id']}/outreach", json={"status": "consented", "method": "call", "given_on": future})).status_code == 422
    consented = await client.put(f"{URL}/{created['id']}/outreach", json={"status": "consented", "method": "call", "given_on": _today().isoformat(),
                                                                          "note": "Agreed on the phone to be put forward"})  # fmt: skip
    sourcing = consented.json()["sourcing"]
    assert sourcing["outreach_status"] == "consented" and sourcing["permitted"] is True
    assert sourcing["permission"]["method"] == "call" and sourcing["permission"]["given_on"] == _today().isoformat()
    assert sourcing["permission"]["note"] == "Agreed on the phone to be put forward"
    assert sourcing["permission"]["recorded_by"]["id"] == str(recruiter.id)
    stray = await client.put(f"{URL}/{created['id']}/outreach", json={"status": "contacted", "method": "call"})
    assert stray.status_code == 422  # permission details only with consented
    declined = await client.put(f"{URL}/{created['id']}/outreach", json={"status": "declined"})
    assert declined.json()["sourcing"]["permission"] is None and declined.json()["sourcing"]["permitted"] is False
    actions = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == created["id"], AuditLog.action == "candidate.outreach")
                                .order_by(AuditLog.created_at))).all()  # fmt: skip
    assert [(a["from"], a["to"]) for a in actions] == [("not_contacted", "contacted"), ("contacted", "consented"), ("consented", "declined")]
    assert actions[1]["method"] == "call" and "note" not in actions[1]  # free text never in the audit


async def test_the_same_outreach_status_is_a_no_op(client, db_session):
    await _team(client, db_session)
    created = (await _create(client, db_session)).json()
    await client.put(f"{URL}/{created['id']}/outreach", json={"status": "contacted"})
    again = await client.put(f"{URL}/{created['id']}/outreach", json={"status": "contacted"})
    assert again.status_code == 200
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "candidate.outreach"))
    assert count == 1
    assert (await client.put(f"{URL}/{created['id']}/outreach", json={"status": "maybe"})).status_code == 422


# --- AC3 submission gate -----------------------------------------------------------------------------------------------------------
async def test_ac3_without_an_outreach_permission_the_candidate_cannot_be_shared(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    contact = await _contact(db_session, job.company_id)
    created = (await _create(client, db_session, location="Pune")).json()
    body = {"requirement_id": str(job.id), "candidate_ids": [created["id"]], "channel": "other"} | SUBMIT  # pob-021 B3-B5
    refused = await client.post(SHARES, json=body)
    assert refused.status_code == 422 and created["candidate_code"] in refused.text and "permission" in refused.text.lower()
    await client.put(f"{URL}/{created['id']}/outreach", json={"status": "consented", "method": "email", "given_on": _today().isoformat()})
    shared = await client.post(SHARES, json=body)
    assert shared.status_code == 201, shared.text
    assert contact  # the requirement's company has a contact (unused by the Other channel)


async def test_a_candidate_who_opted_in_themselves_needs_no_staff_permission(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    person = await _candidate(db_session, recruiter, opted_in=True, location="Pune")  # the website / portal consent sets opted_in (hrc-023, hrc-022)
    shared = await client.post(SHARES, json={"requirement_id": str(job.id), "candidate_ids": [str(person.id)], "channel": "other"} | SUBMIT)
    assert shared.status_code == 201, shared.text


# --- A9 privacy --------------------------------------------------------------------------------------------------------------------
async def test_the_anonymiser_clears_the_free_text(client, db_session):
    _, recruiter = await _team(client, db_session)
    created = (await _create(client, db_session, referrer_name="Kiran", portal_import_reference="ref-1")).json()
    await client.put(f"{URL}/{created['id']}/outreach", json={"status": "consented", "method": "email", "given_on": _today().isoformat(), "note": "by email"})
    candidate = await db_session.get(Candidate, uuid.UUID(created["id"]))
    await candidate_privacy.anonymise(db_session, candidate, "request", recruiter.id)
    await db_session.commit()
    await db_session.refresh(candidate)
    assert (candidate.referrer_name, candidate.portal_import_reference, candidate.outreach_permission_note) == (None, None, None)


async def test_a_referrer_the_viewer_cannot_see_reads_as_restricted(client, db_session):
    _, recruiter = await _team(client, db_session)
    referrer = await _candidate(db_session, recruiter)
    created = (await _create(client, db_session, referrer_candidate_id=str(referrer.id))).json()
    referrer.anonymised_at, referrer.anonymised_reason = datetime.now(IST), "request"  # outside the pool for good
    await db_session.commit()
    await login(client, recruiter)
    sourcing = (await client.get(f"{URL}/{created['id']}")).json()["sourcing"]
    assert sourcing["referrer"] == {"id": None, "candidate_code": None, "name": "Restricted record"}
