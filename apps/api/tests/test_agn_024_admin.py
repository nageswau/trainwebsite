"""AGN-024 -- Overseas Admin / Super Admin KYC review (spec §4.5, §4.7; DEC-SCOPE-224 K3/K6/K7; AC04, AC09)."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditLog, Notification
from app.services import agent_kyc as kyc
from app.services.storage import storage
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn009_helpers import PDF
from tests.agn024_helpers import kyc_rows, org_for, register_kyc_agent

BASE = "/api/v1/overseas-admin/agent-orgs/{}/kyc-documents"


async def _world(client, db):
    body = await register_kyc_agent(client)
    org = await org_for(db, body["user"]["id"])
    docs = {d.doc_type: d for d in await kyc_rows(db, org.id)}
    return body["user"]["id"], org, docs


@pytest.mark.asyncio
@pytest.mark.parametrize("admin_role", ["overseas_admin", "super_admin"])
async def test_admin_lists_views_verifies_and_rejects(client, db_session, admin_role):
    user_id, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role=admin_role)
    async with client_for(admin.email) as c:
        listed = (await c.get(BASE.format(org.id))).json()
        assert listed["kyc_required"] is True and [i["doc_type"] for i in listed["items"]] == list(kyc.DOC_TYPES)
        assert listed["items"][0]["doc_number"] == "ABCDE1234F" and "file_key" not in listed["items"][0]
        view = await c.get(f"{BASE.format(org.id)}/{docs['pan'].id}/file")
        assert view.status_code == 200 and view.content == PDF and view.headers["content-type"].startswith("application/pdf")
        assert view.headers["cache-control"] == "no-store" and view.headers["x-content-type-options"] == "nosniff"
        assert view.headers["content-disposition"] == 'inline; filename="pan.pdf"'
        verified = await c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/verify")
        assert verified.status_code == 200 and verified.json()["status"] == "verified"
        rejected = await c.post(f"{BASE.format(org.id)}/{docs['aadhaar'].id}/reject", json={"reason": "Photo is blurred"})
        assert rejected.status_code == 200 and rejected.json()["status"] == "rejected" and rejected.json()["rejection_reason"] == "Photo is blurred"
        flipped = await c.post(f"{BASE.format(org.id)}/{docs['aadhaar'].id}/verify")  # a decision may change while pending
        assert flipped.json()["status"] == "verified" and flipped.json()["rejection_reason"] is None
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == admin.id))).all())
    assert {"agent_kyc.view", "agent_kyc.verify", "agent_kyc.reject"} <= actions
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == admin.id, AuditLog.action.like("agent_kyc.%")))).all()
    assert all("ABCDE1234F" not in str(a.metadata_json) for a in audits)
    note = await db_session.scalar(select(Notification).where(Notification.user_id == user_id, Notification.title == "Verification document rejected"))
    assert note is not None and "Photo is blurred" in note.body


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "  ", "ab", "x" * 501])
async def test_reject_needs_a_3_to_500_character_reason(client, db_session, reason):
    _uid, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/reject", json={"reason": reason})).status_code == 422


@pytest.mark.asyncio
async def test_review_only_while_pending(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        await c.post(f"/api/v1/overseas-admin/agent-orgs/{org.id}/reject")
        refused = await c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/verify")
    assert refused.status_code == 409 and refused.json()["detail"] == kyc.NOT_PENDING_REVIEW


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["agent", "counselor", "it_admin", "overseas_student", "bdm"])
async def test_other_roles_are_403_on_every_admin_route(client, db_session, role):
    _uid, org, docs = await _world(client, db_session)
    other = await mk_user(db_session, role=role)
    async with client_for(other.email) as c:
        calls = [c.get(BASE.format(org.id)), c.get(f"{BASE.format(org.id)}/{docs['pan'].id}/file"),
                 c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/verify"), c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/reject", json={"reason": "nope"})]  # fmt: skip
        for call in calls:
            assert (await call).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    client.cookies.clear()
    assert (await client.get(f"{BASE.format(org.id)}/{docs['pan'].id}/file")).status_code == 401


@pytest.mark.asyncio
async def test_document_of_another_org_is_404(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    other = await mk_active_org(db_session, name=f"Other {uniq()}")
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.get(f"{BASE.format(other['org'].id)}/{docs['pan'].id}/file")).status_code == 404
        assert (await c.post(f"{BASE.format(other['org'].id)}/{docs['pan'].id}/verify")).status_code == 404


@pytest.mark.asyncio
async def test_kyc_keys_are_never_served_by_generic_routes(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.get("/api/v1/files/download", params={"key": docs["pan"].file_key})).status_code == 404
    if not settings.aws_s3_bucket:  # the public static mount exists only in local storage mode
        assert storage.read_bytes(docs["pan"].file_key) == PDF
        assert (await client.get(f"/local-files/{docs['pan'].file_key}")).status_code == 404
