"""AGN-024 -- the pending agency's own registration status and re-upload (spec §4.4; DEC-SCOPE-224 K5; AC07)."""

import pytest
from sqlalchemy import select, update

from app.models import AgentOrgKycDocument, AuditLog
from app.services import agent_kyc as kyc
from app.services.storage import storage
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import mk_staff
from tests.agn009_helpers import PDF, PNG
from tests.agn024_helpers import kyc_rows, org_for, register_kyc_agent

STATUS = "/api/v1/agent/registration"
REUPLOAD = "/api/v1/agent/registration/documents/{}/file"


async def _registered(client, db):
    body = await register_kyc_agent(client)  # `client` now holds the new agent's cookies
    return body, await org_for(db, body["user"]["id"])


async def _reject(db, org_id, doc_type: str, reason: str = "Unreadable"):
    await db.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id, AgentOrgKycDocument.doc_type == doc_type).values(status="rejected", rejection_reason=reason))
    await db.commit()


@pytest.mark.asyncio
async def test_pending_master_sees_masked_status(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "aadhaar", "Blurred")
    data = (await client.get(STATUS)).json()
    assert data["org"] == {"name": org.name, "status": "pending", "kyc_required": True}
    by_type = {d["doc_type"]: d for d in data["documents"]}
    assert by_type["pan"]["doc_number_display"] == "ABCDE****F" and by_type["aadhaar"]["doc_number_display"] == "XXXX XXXX 1234"
    assert by_type["aadhaar"]["status"] == "rejected" and by_type["aadhaar"]["rejection_reason"] == "Blurred"
    assert "ABCDE1234F" not in str(data) and all("doc_number" not in d and "file_key" not in d for d in data["documents"])


@pytest.mark.asyncio
async def test_reupload_of_a_rejected_document_resets_it_to_pending(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "aadhaar")
    old_key = next(d for d in await kyc_rows(db_session, org.id) if d.doc_type == "aadhaar").file_key
    response = await client.put(REUPLOAD.format("aadhaar"), files={"file": ("aadhaar.png", PNG, "image/png")}, data={"doc_number": "9876"})
    assert response.status_code == 200 and response.json()["status"] == "pending" and response.json()["rejection_reason"] is None
    doc = next(d for d in await kyc_rows(db_session, org.id) if d.doc_type == "aadhaar")
    assert doc.doc_number == "9876" and doc.content_type == "image/png" and doc.file_key != old_key and doc.reviewed_by_user_id is None
    with pytest.raises(FileNotFoundError):
        storage.read_bytes(old_key)  # the replaced file is gone
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "agent_kyc.reupload", AuditLog.entity_id == str(doc.id))) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "verified"])
async def test_only_rejected_documents_can_be_replaced(client, db_session, status):
    _body, org = await _registered(client, db_session)
    await db_session.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.doc_type == "pan").values(status=status))
    await db_session.commit()
    response = await client.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})
    assert response.status_code == 409 and response.json()["detail"] == kyc.ONLY_REJECTED


@pytest.mark.asyncio
async def test_no_reupload_once_the_org_is_not_pending(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "pan")
    org.status = "rejected"
    await db_session.commit()
    response = await client.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})
    assert response.status_code == 409 and response.json()["detail"] == kyc.NOT_PENDING_UPLOAD
    assert (await client.get(STATUS)).json()["org"]["status"] == "rejected"  # a rejected agency can still read its status


@pytest.mark.asyncio
async def test_bad_reupload_inputs(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "pan")
    assert (await client.put(REUPLOAD.format("pan"), files={"file": ("x.pdf", b"MZ\x90", "application/pdf")})).status_code == 415
    assert (await client.put(REUPLOAD.format("pan"), files={"file": ("x.pdf", PDF, "application/pdf")}, data={"doc_number": "bad"})).status_code == 422
    assert (await client.put(REUPLOAD.format("passport"), files={"file": ("x.pdf", PDF, "application/pdf")})).status_code == 422


@pytest.mark.asyncio
async def test_reupload_is_throttled(client, db_session):
    body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "pan")
    for _ in range(kyc.REUPLOAD_LIMIT):
        db_session.add(AuditLog(user_id=body["user"]["id"], action="agent_kyc.reupload", entity_type="agent_org_kyc_document", entity_id=str(uniq())))
    await db_session.commit()
    response = await client.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_non_master_and_non_agent_are_refused(client, db_session):
    ctx = await mk_active_org(db_session, name=f"Staffed {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], full_name="Plain Staff")
    student = await mk_user(db_session, role="overseas_student")
    admin = await mk_user(db_session, role="overseas_admin")
    for email in (staff["user"].email, student.email, admin.email):
        async with client_for(email) as c:
            assert (await c.get(STATUS)).status_code == 403
            assert (await c.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})).status_code == 403


@pytest.mark.asyncio
async def test_legacy_active_master_sees_no_documents(db_session):
    ctx = await mk_active_org(db_session, name=f"Legacy {uniq()}")
    async with client_for(ctx["master"].email) as c:
        data = (await c.get(STATUS)).json()
    assert data["org"]["kyc_required"] is False and data["documents"] == []
