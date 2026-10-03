"""AGN-015 (DEC-SCOPE-061 §3, §5) -- the complete history: every source event once, in order, with its actor."""

import pytest
from sqlalchemy import update

from app.models import AuditLog, DocumentEvent
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc, world
from tests.agn015_helpers import mk_audit, mk_history, timeline_url

KEYS = {"id", "at", "kind", "actor", "application", "document", "from_status", "to_status", "fields", "notes"}


async def _get(email, student_id, **params):
    async with client_for(email) as c:
        r = await c.get(timeline_url(student_id, **params))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_every_source_event_appears_once_with_its_actor(db_session):
    w = await world(db_session)
    rec, master, staff = w["record"], w["master"], w["staff"]["user"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    await mk_history(db_session, app, to_status="enquiry", by=staff)
    await mk_audit(db_session, user=staff, action="overseas.application.create", entity_type="overseas_application", entity_id=app.id)  # history holds it
    await mk_history(db_session, app, from_status="enquiry", to_status="offer", by=master, notes="Offer recorded: Conditional")
    await mk_audit(db_session, user=master, action="agent_student.assign", entity_type="agent_student", entity_id=rec.id, metadata={"from": None, "to": "x"})
    await mk_audit(db_session, user=staff, action="agent_student.counseling", entity_type="agent_student", entity_id=rec.id, metadata={"fields": ["budget_amount"]})
    await mk_audit(db_session, user=staff, action="agent_student.create", entity_type="agent_student", entity_id=rec.id)  # the record holds it
    doc = await mk_doc(db_session, record=rec)
    db_session.add(DocumentEvent(document_id=doc.id, event="uploaded", actor_user_id=staff.id, to_status="pending"))
    await db_session.commit()
    await mk_audit(db_session, user=staff, action="document.upload", entity_type="student_document", entity_id=doc.id)  # the event holds it
    body = await _get(master.email, rec.id)
    kinds = [i["kind"] for i in body["items"]]
    assert sorted(kinds) == sorted(["student_created", "application_created", "application_stage_changed", "student_assigned", "counseling_saved", "document_uploaded"])
    assert body["total"] == 6 and all(set(i) == KEYS for i in body["items"])
    by_kind = {i["kind"]: i for i in body["items"]}
    changed = by_kind["application_stage_changed"]
    assert changed["actor"] == master.full_name
    assert (changed["from_status"], changed["to_status"], changed["notes"]) == ("enquiry", "offer", "Offer recorded: Conditional")
    assert changed["application"] == {"id": str(app.id), "university": w["university"].name}
    assert by_kind["application_created"]["actor"] == staff.full_name
    assert by_kind["counseling_saved"]["fields"] == ["budget_amount"]
    assert by_kind["document_uploaded"]["document"] == {"id": str(doc.id), "type": "Passport"}
    assert by_kind["student_created"]["actor"] == master.full_name
    assert by_kind["student_assigned"]["fields"] is None  # member ids in the metadata never leave


@pytest.mark.asyncio
async def test_newest_first_and_same_transaction_ties_follow_source_rank(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    h = await mk_history(db_session, app, to_status="enquiry", by=master)
    a = await mk_audit(db_session, user=master, action="overseas.application.update", entity_type="overseas_application", entity_id=app.id, metadata={"fields": ["intake"]})
    await db_session.execute(update(AuditLog).where(AuditLog.id == a.id).values(created_at=h.created_at))  # one transaction: shared now()
    await db_session.commit()
    kinds = [i["kind"] for i in (await _get(master.email, rec.id))["items"]]
    assert kinds == ["application_edited", "application_created", "student_created"]


@pytest.mark.asyncio
async def test_outside_actors_are_role_labels_and_values_never_leave(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    counselor = await mk_user(db_session, role="counselor", full_name="Secret Counsellor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Secret Admin")
    await mk_audit(db_session, user=counselor, action="overseas.application.update", entity_type="overseas_application", entity_id=app.id, metadata={"next_action": "call +44 7700 900123"})
    await mk_audit(db_session, user=None, action="overseas.application.deposit_paid", entity_type="overseas_application", entity_id=app.id, metadata={"payment_id": "p"})
    await mk_audit(db_session, user=admin, action="agent_student.archive", entity_type="agent_student", entity_id=rec.id)
    body = await _get(master.email, rec.id)
    text = str(body)
    assert "Secret" not in text and "7700" not in text
    by_kind = {i["kind"]: i for i in body["items"]}
    assert by_kind["application_edited"]["actor"] == "EduSphere counsellor" and by_kind["application_edited"]["fields"] == ["next_action"]
    assert by_kind["deposit_paid"]["actor"] == "System" and by_kind["deposit_paid"]["fields"] is None
    assert by_kind["student_archived"]["actor"] == "EduSphere admin"


@pytest.mark.asyncio
async def test_unmapped_actions_are_not_events(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    for action in ("overseas.application.deposit_checkout", "agent.commission_auto_create", "overseas.application.advance", "overseas.application.offer", "overseas.application.enroll"):
        await mk_audit(db_session, user=master, action=action, entity_type="overseas_application", entity_id=app.id)
    assert [i["kind"] for i in (await _get(master.email, rec.id))["items"]] == ["student_created"]


@pytest.mark.asyncio
async def test_legacy_upload_without_event_appears_once(db_session):
    w = await world(db_session)
    rec, master, staff = w["record"], w["master"], w["staff"]["user"]
    legacy = await mk_doc(db_session, record=rec)
    legacy.uploaded_by_user_id = staff.id
    current = await mk_doc(db_session, record=rec, document_type="CV")
    db_session.add(DocumentEvent(document_id=current.id, event="uploaded", actor_user_id=staff.id))
    await db_session.commit()
    items = (await _get(master.email, rec.id))["items"]
    uploads = [i for i in items if i["kind"] == "document_uploaded"]
    assert sorted(i["document"]["type"] for i in uploads) == ["CV", "Passport"]
    assert all(i["actor"] == staff.full_name for i in uploads)


@pytest.mark.asyncio
async def test_pagination_and_offset_past_the_end(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    for n in range(4):
        await mk_audit(db_session, user=master, action="agent_student.update", entity_type="agent_student", entity_id=rec.id, metadata={"fields": [f"f{n}"]})
    first = await _get(master.email, rec.id, limit=2, offset=0)
    second = await _get(master.email, rec.id, limit=2, offset=2)
    assert (first["total"], second["total"], first["limit"], second["offset"]) == (5, 5, 2, 2)
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
    beyond = await _get(master.email, rec.id, offset=5000)
    assert beyond["items"] == [] and beyond["total"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}])
async def test_bad_paging_is_422(db_session, params):
    w = await world(db_session)
    async with client_for(w["master"].email) as c:
        assert (await c.get(timeline_url(w["record"].id, **params))).status_code == 422
