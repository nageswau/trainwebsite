"""pob-011 -- vendor requirements, vendor submissions and candidate-visibility control (DEC-SCOPE-427 V1-V12). Shared database: every value
is unique per test."""

import importlib.util
import pathlib
import uuid

import pytest
from sqlalchemy import select

from app import models
from app.models import AuditLog, Company, CompanyContact, CompanyDocument, Job, RecruiterContract, RecruiterMessage
from tests.rec001_helpers import make_recruiter
from tests.test_rec_017_tracking import _candidate, _requirement, _tag, _team
from tests.test_rec_019_shares import _upload, published, smtp_on  # noqa: F401  (fixtures)

SHARES = "/api/v1/recruiter/shares"
REQ = "/api/v1/recruiter/requirements"


async def _vendor(db, recruiter, *, status="active", nda=True, agreement="signed", partner_type="vendor") -> Company:
    vendor = Company(name=f"Vendor {_tag()} Staffing", partner_type=partner_type, vendor_status=status, assigned_recruiter_user_id=recruiter.id)
    db.add(vendor)
    await db.flush()
    if nda:
        db.add(CompanyDocument(company_id=vendor.id, kind="nda", name="nda.pdf", content_type="application/pdf", size_bytes=10, storage_key=f"k/{_tag()}",
                               uploaded_by_user_id=recruiter.id))  # fmt: skip
    if agreement:
        db.add(RecruiterContract(company_id=vendor.id, created_by_user_id=recruiter.id, status=agreement, party="vendor", direction="we_pay_vendor",
                                 contract_document_key=f"c/{_tag()}", contract_document_content_type="application/pdf"))  # fmt: skip
    await db.commit()
    return vendor


async def _contact(db, company_id) -> CompanyContact:
    contact = CompanyContact(company_id=company_id, name=f"Asha {_tag()}", email=f"v-{_tag()}@example.com", mobile="+919812345678")
    db.add(contact)
    await db.commit()
    return contact


async def _setup(client, db, n=2, **vendor_opts):
    manager, recruiter = await _team(client, db)
    vendor = await _vendor(db, recruiter, **vendor_opts)
    job = await _requirement(db, recruiter)
    job.via_vendor_id = vendor.id
    await db.commit()
    people = [await _candidate(db, recruiter, mobile=f"+9197{uuid.uuid4().int % 10**8:08d}", current_company=f"Acme {_tag()}", location="Pune") for _ in range(n)]
    return {"manager": manager, "recruiter": recruiter, "vendor": vendor, "vendor_contact": await _contact(db, vendor.id), "job": job,
            "client_contact": await _contact(db, job.company_id), "candidates": people}  # fmt: skip


def _vendor_body(s, channel="email", **over) -> dict:
    body = {"requirement_id": str(s["job"].id), "candidate_ids": [str(c.id) for c in s["candidates"]], "channel": channel, "recipient": "vendor"}
    if channel in ("email", "whatsapp"):
        body["contact_id"] = str(s["vendor_contact"].id)
    return body | over


# --- V2/V3/V10: the requirement ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_requirement_comes_via_a_vendor_with_a_disclosure_flag_and_a_revision(client, db_session):
    _, recruiter = await _team(client, db_session)
    vendor = await _vendor(db_session, recruiter)
    end_client = Company(name=f"End {_tag()} Ltd", assigned_recruiter_user_id=recruiter.id)
    db_session.add(end_client)
    await db_session.commit()
    created = await client.post(REQ, json={"company_id": str(end_client.id), "title": "Java Dev", "location": "Pune", "via_vendor_id": str(vendor.id),
                                           "end_client_disclosure": "internal"})  # fmt: skip
    assert created.status_code == 201, created.text
    requirement = created.json()["requirement"]
    assert requirement["via_vendor"] == {"id": str(vendor.id), "code": vendor.company_code, "name": vendor.name}
    assert requirement["end_client_disclosure"] == "internal" and requirement["company"]["id"] == str(end_client.id)
    cleared = await client.patch(f"{REQ}/{requirement['id']}", json={"via_vendor_id": None, "end_client_disclosure": "external"})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["requirement"]["via_vendor"] is None and cleared.json()["requirement"]["end_client_disclosure"] == "external"
    revisions = (await client.get(f"{REQ}/{requirement['id']}/revisions")).json()["items"]
    assert {"via_vendor", "end_client_disclosure"} <= {f["field"] for f in revisions[0]["changed_fields"]}
    first = {v["field"]: v["value"] for v in (await client.get(f"{REQ}/{requirement['id']}/revisions/1")).json()["values"]}
    assert first["via_vendor"] == vendor.name and first["end_client_disclosure"] == "internal"


@pytest.mark.asyncio
async def test_the_vendor_must_be_a_usable_vendor_in_scope(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    other = await make_recruiter(db_session)
    suspended = await _vendor(db_session, recruiter, status="suspended")
    foreign = await _vendor(db_session, other)
    client_only = Company(name=f"Client {_tag()}", assigned_recruiter_user_id=recruiter.id)
    db_session.add(client_only)
    await db_session.commit()
    for target in (client_only.id, suspended.id, foreign.id, job.company_id, uuid.uuid4()):
        response = await client.patch(f"{REQ}/{job.id}", json={"via_vendor_id": str(target)})
        assert response.status_code == 422, (target, response.text)
    both = await _vendor(db_session, recruiter, partner_type="vendor_client")
    ok = await client.patch(f"{REQ}/{job.id}", json={"via_vendor_id": str(both.id)})
    assert ok.status_code == 200, ok.text
    bad_flag = await client.patch(f"{REQ}/{job.id}", json={"end_client_disclosure": "secret"})
    assert bad_flag.status_code == 422


@pytest.mark.asyncio
async def test_an_internal_end_client_is_masked_on_the_public_job_list(client, db_session):
    company = Company(name=f"Secret {_tag()} Corp")
    db_session.add(company)
    await db_session.flush()
    hidden = Job(company_id=company.id, title=f"Hidden {_tag()}", location="Pune", description="", skills=[], status="sourcing", end_client_disclosure="internal")
    shown = Job(company_id=company.id, title=f"Shown {_tag()}", location="Pune", description="", skills=[], status="sourcing")
    db_session.add_all([hidden, shown])
    await db_session.commit()
    rows = {r["title"]: r for r in (await client.get("/api/v1/public/jobs")).json()}
    assert rows[hidden.title]["company"] == "Confidential client"
    assert rows[shown.title]["company"] == company.name


# --- V4-V7: vendor shares ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.usefixtures("smtp_on", "published")
async def test_a_vendor_share_is_anonymised_by_default(client, db_session):
    s = await _setup(client, db_session)
    await _upload(client, s["candidates"][0].id)
    response = await client.post(SHARES, json=_vendor_body(s))
    assert response.status_code == 201, response.text
    share = response.json()["share"]
    assert share["recipient"] == "vendor" and share["detail"] == "anonymised" and share["company_id"] == str(s["vendor"].id)
    assert share["consent_reference"] is None and share["contact"]["id"] == str(s["vendor_contact"].id)
    message = await db_session.get(RecruiterMessage, uuid.UUID(share["message"]["id"]))
    assert message.company_id == s["vendor"].id
    for candidate in s["candidates"]:
        assert candidate.candidate_code in message.body
        assert candidate.name not in message.body and candidate.current_company not in message.body
        assert candidate.email not in message.body and candidate.mobile not in message.body
    assert "/public/shared-resume/" not in message.body and "Resume on request" in message.body
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "profile_share.create", AuditLog.entity_id == share["id"]))
    assert audit.metadata_json["recipient"] == "vendor" and audit.metadata_json["detail"] == "anonymised"


@pytest.mark.asyncio
@pytest.mark.usefixtures("smtp_on", "published")
async def test_full_details_need_consent_and_carry_contact_details(client, db_session):
    s = await _setup(client, db_session)
    refused = await client.post(SHARES, json=_vendor_body(s, detail="full"))
    assert refused.status_code == 409 and "consent" in refused.json()["detail"].lower()
    half = await client.post(SHARES, json=_vendor_body(s, detail="full", consent_confirmed=True))
    assert half.status_code == 409
    response = await client.post(SHARES, json=_vendor_body(s, detail="full", consent_confirmed=True, consent_reference="Call on 8 Nov"))
    assert response.status_code == 201, response.text
    share = response.json()["share"]
    assert share["detail"] == "full" and share["consent_reference"] == "Call on 8 Nov"
    message = await db_session.get(RecruiterMessage, uuid.UUID(share["message"]["id"]))
    for candidate in s["candidates"]:
        assert candidate.name in message.body and candidate.email in message.body and candidate.mobile in message.body
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "profile_share.create", AuditLog.entity_id == share["id"]))
    assert "Call on 8 Nov" not in str(audit.metadata_json)


@pytest.mark.parametrize(("opts", "word"), [({"nda": False}, "nda"), ({"status": "approved"}, "active"), ({"agreement": None}, "agreement"),
                                             ({"agreement": "discussion"}, "agreement")])  # fmt: skip
@pytest.mark.asyncio
async def test_a_vendor_share_needs_an_active_vendor_with_agreement_and_nda(client, db_session, opts, word):
    s = await _setup(client, db_session, **opts)
    response = await client.post(SHARES, json=_vendor_body(s, channel="other"))
    assert response.status_code == 409, response.text
    assert word in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_vendor_share_shape_rules(client, db_session):
    s = await _setup(client, db_session)
    portal = await client.post(SHARES, json=_vendor_body(s, channel="portal"))
    assert portal.status_code == 422
    wrong_contact = await client.post(SHARES, json=_vendor_body(s, channel="other", contact_id=str(s["client_contact"].id)))
    assert wrong_contact.status_code == 422
    client_with_detail = await client.post(SHARES, json=_vendor_body(s, channel="other", recipient="client", detail="anonymised"))
    assert client_with_detail.status_code == 422
    s["job"].via_vendor_id = None
    await db_session.commit()
    no_vendor = await client.post(SHARES, json=_vendor_body(s, channel="other"))
    assert no_vendor.status_code == 422


# --- V8: the duplicate check across routes (AC1) -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_vendor_share_after_a_direct_share_to_the_same_end_client_warns(client, db_session):
    s = await _setup(client, db_session, n=1)
    direct_job = await _requirement(db_session, s["recruiter"], company=await db_session.get(Company, s["job"].company_id))
    first = await client.post(SHARES, json={"requirement_id": str(direct_job.id), "candidate_ids": [str(s["candidates"][0].id)], "channel": "other"})
    assert first.status_code == 201, first.text
    warned = await client.post(SHARES, json=_vendor_body(s, channel="other"))
    assert warned.status_code == 409, warned.text
    assert warned.json()["detail"]["duplicates"][0]["id"] == str(s["candidates"][0].id)
    again = await client.post(SHARES, json=_vendor_body(s, channel="other", repeat=True))
    assert again.status_code == 201, again.text
    # and a direct share after the vendor share warns too
    third_job = await _requirement(db_session, s["recruiter"], company=await db_session.get(Company, s["job"].company_id))
    back = await client.post(SHARES, json={"requirement_id": str(third_job.id), "candidate_ids": [str(s["candidates"][0].id)], "channel": "other"})
    assert back.status_code == 409


@pytest.mark.asyncio
async def test_direct_shares_across_requirements_stay_unwarned(client, db_session):
    _, recruiter = await _team(client, db_session)
    first_job = await _requirement(db_session, recruiter)
    second_job = await _requirement(db_session, recruiter, company=await db_session.get(Company, first_job.company_id))
    person = await _candidate(db_session, recruiter)
    for job in (first_job, second_job):
        response = await client.post(SHARES, json={"requirement_id": str(job.id), "candidate_ids": [str(person.id)], "channel": "other"})
        assert response.status_code == 201, response.text
        assert response.json()["share"]["recipient"] == "client" and response.json()["share"]["detail"] == "named"


# --- V11: the migration -----------------------------------------------------------------------------------------------------------
def test_the_migration_chains_and_freezes_the_checks():
    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0308_vendor_requirements.py"
    spec = importlib.util.spec_from_file_location("m0308", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "0308_vendor_requirements" and migration.down_revision == "0307_institution_vacancy_shares"
    assert migration.JOB_CHECKS == models.JOB_VENDOR_CHECKS
    assert migration.SHARE_CHECKS == models.PROFILE_SHARE_VENDOR_CHECKS
