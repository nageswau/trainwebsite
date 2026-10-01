"""AGN-003 -- agents decide pending documents of their agency (spec §7; AGN-003-AC04, AC07; DEC-SCOPE-041 P5/P6)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, StudentDocument
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn003_helpers import DOC_VERIFY, agency_document

VERIFY_REFUSED = "Your agency Master hasn't given you permission to verify documents"
REVIEW_MASTER_ONLY = "Only an agency Master can reject documents or request changes"


async def _doc(db_session, document_id) -> StudentDocument:
    return await db_session.get(StudentDocument, document_id, populate_existing=True)


async def _notifications(db_session, student_id) -> list[Notification]:
    return (await db_session.scalars(select(Notification).where(Notification.user_id == student_id).execution_options(populate_existing=True))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["verified", "rejected", "changes_required"])
async def test_a_master_decides_a_pending_document(db_session, decision):
    ctx = await mk_active_org(db_session, name=f"Master Review {uniq()}")
    world = await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": decision, "notes": "Checked"})
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == decision
    doc = await _doc(db_session, world["document"].id)
    assert (doc.verification_status, doc.verified_by_id, doc.reviewer_notes) == (decision, ctx["master"].id, "Checked")
    assert [n.title for n in await _notifications(db_session, world["student"].id)] == ["Document reviewed"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "document.verify", AuditLog.entity_id == str(doc.id)))
    assert audit.metadata_json == {"verification_status": decision, "notes": "Checked", "member_role": "master"}


@pytest.mark.asyncio
async def test_staff_without_verify_are_refused_before_anything_is_read(db_session):
    ctx = await mk_active_org(db_session, name=f"Staff No Verify {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    world = await agency_document(db_session, ctx)
    async with client_for(staff["user"].email) as s:
        for body in ({"verification_status": "verified"}, {"verification_status": "nonsense"}):
            response = await s.patch(DOC_VERIFY.format(world["document"].id), json=body)
            assert response.status_code == 403 and response.json()["detail"] == VERIFY_REFUSED
        unknown = await s.patch(DOC_VERIFY.format(uuid.uuid4()), json={"verification_status": "verified"})
        assert unknown.status_code == 403  # never 404: a refused caller learns nothing about existence
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"


@pytest.mark.asyncio
async def test_staff_with_verify_mark_a_document_verified(db_session):
    ctx = await mk_active_org(db_session, name=f"Staff Verify {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True)
    world = await agency_document(db_session, ctx)
    async with client_for(staff["user"].email) as s:
        response = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
    assert response.status_code == 200
    doc = await _doc(db_session, world["document"].id)
    assert (doc.verification_status, doc.verified_by_id) == ("verified", staff["user"].id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "document.verify", AuditLog.entity_id == str(doc.id)))
    assert audit.metadata_json["member_role"] == "staff"


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["rejected", "changes_required"])
async def test_staff_with_verify_cannot_reject_or_request_changes(db_session, decision):  # Review Focus 3
    ctx = await mk_active_org(db_session, name=f"Staff Reject {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True)
    world = await agency_document(db_session, ctx)
    async with client_for(staff["user"].email) as s:
        response = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": decision})
    assert response.status_code == 403 and response.json()["detail"] == REVIEW_MASTER_ONLY
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"
    assert await _notifications(db_session, world["student"].id) == []


@pytest.mark.asyncio
async def test_a_second_review_is_refused_and_the_first_stands(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name=f"Second Review {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True)
    world = await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as m, client_for(staff["user"].email) as s:
        assert (await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})).status_code == 200
        again = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
        assert again.status_code == 409 and again.json()["detail"] == "This document has already been reviewed"
        repeat = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})
        assert repeat.status_code == 409
    assert (await _doc(db_session, world["document"].id)).verification_status == "rejected"
    assert len(await _notifications(db_session, world["student"].id)) == 1


@pytest.mark.asyncio
async def test_a_document_already_decided_by_a_counselor_is_not_overwritten(db_session):
    ctx = await mk_active_org(db_session, name=f"Counselor First {uniq()}")
    world = await agency_document(db_session, ctx, status="verified")
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})
    assert response.status_code == 409
    assert (await _doc(db_session, world["document"].id)).verification_status == "verified"


@pytest.mark.asyncio
async def test_a_counselor_can_still_re_review_an_agent_decision(db_session):  # Review Focus 2, P5
    ctx = await mk_active_org(db_session, name=f"Counselor After {uniq()}")
    counselor = await mk_user(db_session, role="counselor")
    world = await agency_document(db_session, ctx, counselor=counselor)
    async with client_for(ctx["master"].email) as m:
        assert (await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})).status_code == 200
    async with client_for(counselor.email) as c:
        assert (await c.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})).status_code == 200
    assert (await _doc(db_session, world["document"].id)).verification_status == "rejected"


@pytest.mark.asyncio
async def test_an_unattached_document_of_an_agency_student_can_be_reviewed(db_session):
    ctx = await mk_active_org(db_session, name=f"Unattached {uniq()}")
    world = await agency_document(db_session, ctx, attached=False)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("attached", "detail"), [(True, "Application is outside your assigned scope"), (False, "Document is outside your assigned scope")])
async def test_another_agencys_document_is_out_of_scope(db_session, attached, detail):
    ctx = await mk_active_org(db_session, name=f"Mine {uniq()}")
    other = await mk_active_org(db_session, name=f"Theirs {uniq()}")
    world = await agency_document(db_session, other, attached=attached)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
    assert response.status_code == 403 and response.json()["detail"] == detail
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"


@pytest.mark.asyncio
async def test_an_unknown_document_is_not_found_for_a_master(db_session):
    ctx = await mk_active_org(db_session, name=f"Unknown Doc {uniq()}")
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(uuid.uuid4()), json={"verification_status": "verified"})
    assert response.status_code == 404 and response.json()["detail"] == "Document not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {},
    {"verification_status": "approved"},
    {"verification_status": "verified", "notes": "x" * 10001},
    {"verification_status": "verified", "verified_by_id": "00000000-0000-0000-0000-000000000000"},
])
async def test_bad_agent_review_bodies_are_refused(db_session, body):  # Review Focus 4
    ctx = await mk_active_org(db_session, name=f"Bad Review {uniq()}")
    world = await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json=body)
    assert response.status_code == 422 and isinstance(response.json()["detail"], list)
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"


@pytest.mark.asyncio
async def test_verify_toggle_applies_on_next_request(db_session):  # Review Focus 1
    ctx = await mk_active_org(db_session, name=f"Verify Next {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    first, second = await agency_document(db_session, ctx), await agency_document(db_session, ctx)
    on = {"can_verify_documents": True, "can_view_reports": False}
    async with client_for(staff["user"].email) as s, client_for(ctx["master"].email) as m:
        assert (await s.patch(DOC_VERIFY.format(first["document"].id), json={"verification_status": "verified"})).status_code == 403
        assert (await m.put(f"{STAFF}/{staff['member'].id}/permissions", json=on)).status_code == 200
        assert (await s.patch(DOC_VERIFY.format(first["document"].id), json={"verification_status": "verified"})).status_code == 200
        off = {"can_verify_documents": False, "can_view_reports": False}
        assert (await m.put(f"{STAFF}/{staff['member'].id}/permissions", json=off)).status_code == 200
        assert (await s.patch(DOC_VERIFY.format(second["document"].id), json={"verification_status": "verified"})).status_code == 403
