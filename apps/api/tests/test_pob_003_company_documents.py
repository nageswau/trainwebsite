"""pob-003 -- the company document store (DEC-SCOPE-406 D6-D9; AC3). Shared database: every revocation is a per-user deny override."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.models import AuditLog, Company, RecruiterMeeting, UserPermissionOverride
from app.services import company_documents as svc
from tests.bdm005_helpers import PDF_BYTES
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user

BASE = "/api/v1/recruiter/companies"
DOWNLOAD = "/api/v1/recruiter/companies/documents"
KINDS = ("company_profile", "vendor_onboarding_form", "recruitment_agreement", "job_description", "meeting_notes")
REFUSED = "Your role cannot view or change client commercial terms"


def docs_url(company_id: str) -> str:
    return f"{BASE}/{company_id}/documents"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client) -> dict:
    response = await client.post(BASE, json={"name": f"Doc {uuid.uuid4().hex[:8]} Pvt"})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _upload(client, company_id, kind="company_profile", data=PDF_BYTES, name="profile.pdf", content_type="application/pdf", **form):
    return await client.post(docs_url(company_id), data={"kind": kind, **form}, files={"file": (name, data, content_type)})


async def _deny(db, user, *actions: str) -> None:
    for action in actions:
        db.add(UserPermissionOverride(user_id=user.id, resource="commercials.client", action=action, effect="deny", reason="pob-003 test"))
    await db.commit()


async def _audits(db, document_id: str, action: str):
    return (await db.scalars(select(AuditLog).where(AuditLog.entity_id == document_id, AuditLog.action == f"recruiter_company_document.{action}"))).all()


@pytest.mark.asyncio
async def test_every_kind_uploads_lists_and_downloads_with_an_audit_row(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    empty = (await client.get(docs_url(company["id"]))).json()
    assert empty["items"] == [] and empty["total"] == 0 and empty["can_upload"] is True and empty["can_upload_agreement"] is True
    ids = []
    for kind in KINDS:
        uploaded = await _upload(client, company["id"], kind=kind, name=f"{kind}.pdf")
        assert uploaded.status_code == 201, uploaded.text
        doc = uploaded.json()["document"]
        assert doc["kind"] == kind and doc["name"] == f"{kind}.pdf" and doc["content_type"] == "application/pdf" and doc["can_download"] is True
        assert "key" not in doc and "storage_key" not in doc
        ids.append(doc["id"])
        assert len(await _audits(db_session, doc["id"], "uploaded")) == 1
    page = (await client.get(docs_url(company["id"]))).json()
    assert page["total"] == 5 and [d["id"] for d in page["items"]] == ids[::-1]  # newest first
    assert page["items"][0]["uploaded_by"]["full_name"]
    for document_id in ids:
        got = await client.get(f"{DOWNLOAD}/{document_id}/download")
        assert got.status_code == 200 and got.content == PDF_BYTES
        assert got.headers["content-type"] == "application/pdf" and got.headers["cache-control"] == "private, no-store"
        assert got.headers["content-disposition"].startswith('attachment; filename="') and company["code"] in got.headers["content-disposition"]
        assert len(await _audits(db_session, document_id, "downloaded")) == 1
    only = (await client.get(docs_url(company["id"]), params={"kind": "job_description"})).json()
    assert only["total"] == 1 and only["items"][0]["kind"] == "job_description"


@pytest.mark.asyncio
async def test_a_meeting_notes_document_links_to_a_meeting_of_the_same_company_only(client, db_session):
    _, recruiter = await _team(client, db_session)
    recruiter_id = recruiter.id
    company, other = await _company(client), await _company(client)
    meeting_ids = {}
    for target in (company, other):
        meeting_ids[target["id"]] = uuid.uuid4()
        db_session.add(RecruiterMeeting(id=meeting_ids[target["id"]], meeting_code=f"MTG-{uuid.uuid4().hex[:8]}", company_id=uuid.UUID(target["id"]),
                                        meeting_type="contract_discussion", starts_at=datetime.now(UTC) - timedelta(hours=1), mode="Online",
                                        created_by_user_id=recruiter_id))  # fmt: skip
    await db_session.commit()
    linked = await _upload(client, company["id"], kind="meeting_notes", meeting_id=str(meeting_ids[company["id"]]))
    assert linked.status_code == 201, linked.text
    assert linked.json()["document"]["meeting"]["id"] == str(meeting_ids[company["id"]]) and linked.json()["document"]["meeting"]["code"].startswith("MTG-")
    foreign = await _upload(client, company["id"], kind="meeting_notes", meeting_id=str(meeting_ids[other["id"]]))
    assert foreign.status_code == 422
    filtered = (await client.get(docs_url(company["id"]), params={"meeting_id": str(meeting_ids[company["id"]])})).json()
    assert filtered["total"] == 1


@pytest.mark.asyncio
async def test_bad_files_and_kinds_are_refused(client, db_session, monkeypatch):
    await _team(client, db_session)
    company = await _company(client)
    assert (await _upload(client, company["id"], data=b"MZ\x90\x00 not a pdf", name="x.exe", content_type="application/pdf")).status_code == 415
    assert (await _upload(client, company["id"], kind="invoice")).status_code == 422
    assert (await _upload(client, company["id"], data=b"")).status_code == 422
    monkeypatch.setattr(settings, "max_upload_bytes", len(PDF_BYTES) - 1)
    assert (await _upload(client, company["id"])).status_code == 413
    assert (await client.get(docs_url(company["id"]))).json()["total"] == 0


@pytest.mark.asyncio
async def test_scope_and_role_rules(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    doc = (await _upload(client, company["id"])).json()["document"]
    stranger = await make_recruiter(db_session, await make_pm(db_session))
    await login(client, stranger)
    assert (await client.get(docs_url(company["id"]))).status_code == 404
    assert (await _upload(client, company["id"])).status_code == 404
    assert (await client.get(f"{DOWNLOAD}/{doc['id']}/download")).status_code == 404
    assert (await client.get(f"{DOWNLOAD}/{uuid.uuid4()}/download")).status_code == 404
    await login(client, manager)  # the team's manager reads and downloads but cannot upload
    read = (await client.get(docs_url(company["id"]))).json()
    assert read["total"] == 1 and read["can_upload"] is False
    assert (await client.get(f"{DOWNLOAD}/{doc['id']}/download")).status_code == 200
    assert (await _upload(client, company["id"])).status_code == 403
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    assert (await client.get(docs_url(company["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_an_archived_company_takes_no_uploads(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await db_session.execute(update(Company).where(Company.id == uuid.UUID(company["id"])).values(archived_at=datetime.now(UTC)))
    await db_session.commit()
    assert (await _upload(client, company["id"])).status_code == 409


@pytest.mark.asyncio
async def test_agreements_follow_the_commercial_grant(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    agreement = (await _upload(client, company["id"], kind="recruitment_agreement")).json()["document"]
    profile = (await _upload(client, company["id"])).json()["document"]
    await _deny(db_session, recruiter, "edit")
    page = (await client.get(docs_url(company["id"]))).json()
    assert page["can_upload"] is True and page["can_upload_agreement"] is False
    refused = await _upload(client, company["id"], kind="recruitment_agreement")
    assert refused.status_code == 403 and refused.json()["detail"] == REFUSED
    assert (await _upload(client, company["id"], kind="job_description")).status_code == 201
    assert (await client.get(f"{DOWNLOAD}/{agreement['id']}/download")).status_code == 200  # view is kept
    await _deny(db_session, recruiter, "view")
    page = (await client.get(docs_url(company["id"]))).json()
    listed = {d["id"]: d for d in page["items"]}
    assert listed[agreement["id"]]["can_download"] is False and listed[agreement["id"]]["name"]  # that it exists is not a term
    assert listed[profile["id"]]["can_download"] is True
    denied = await client.get(f"{DOWNLOAD}/{agreement['id']}/download")
    assert denied.status_code == 403 and denied.json()["detail"] == REFUSED
    assert (await client.get(f"{DOWNLOAD}/{profile['id']}/download")).status_code == 200


@pytest.mark.asyncio
async def test_uploads_are_throttled_and_capped(client, db_session, monkeypatch):
    await _team(client, db_session)
    company = await _company(client)
    monkeypatch.setattr(svc, "UPLOAD_LIMIT", 2)
    for _ in range(2):
        assert (await _upload(client, company["id"])).status_code == 201
    throttled = await _upload(client, company["id"])
    assert throttled.status_code == 429 and int(throttled.headers["retry-after"]) > 0
    monkeypatch.setattr(svc, "UPLOAD_LIMIT", 100)
    monkeypatch.setattr(svc, "MAX_PER_COMPANY", 2)
    assert (await _upload(client, company["id"])).status_code == 409


@pytest.mark.asyncio
async def test_a_failed_commit_removes_the_stored_object(client, db_session, monkeypatch):
    await _team(client, db_session)
    company = await _company(client)
    stored, discarded = [], []
    real_store = svc.store
    monkeypatch.setattr(svc, "store", lambda data, ct: stored.append(real_store(data, ct)) or stored[-1])
    monkeypatch.setattr(svc, "discard", discarded.append)

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(svc, "audit", boom)
    with pytest.raises(RuntimeError):
        await _upload(client, company["id"])
    assert discarded == stored and len(stored) == 1
