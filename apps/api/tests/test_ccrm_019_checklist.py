"""ccrm-019 (DEC-SCOPE-257, AC1-AC9) -- an application's document checklist: created from the admission template (version frozen,
documents auto-linked by type), counselor items, marks, links, the derived status and summary, `documents_completed_on`, replace and
expiry keeping it current, scope, and the Ready-for-Submission gate in block and warn modes on the counselor and agency routes. Spec:
docs/superpowers/specs/2026-10-24-ccrm-019-application-checklist-design.md."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.application_checklists import item_status, summary
from app.models import ApplicationChecklistItem, ApplicationStatusHistory, AuditLog, DocumentChecklistTemplate, DocumentChecklistTemplateItem, StudentDocument
from app.services.document_expiry import expire_documents
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import APPS, mk_application
from tests.agn009_helpers import PDF, VERIFY, mk_doc
from tests.agn023_helpers import fresh
from tests.ccrm025_helpers import offers_world

BASE = "/api/v1/workflows/overseas/applications/{}"
CHECKLIST = BASE + "/checklist"
ITEMS = CHECKLIST + "/items"
ITEM = ITEMS + "/{}"
LINK = ITEM + "/documents/{}"
SUB = BASE + "/sub-status"
AGENT_SUB = APPS + "/{}/sub-status"
READY = {"sub_status": "ready_for_submission"}


async def mk_template(db, world, *, gate_mode="block", items=(("Passport", True), ("Academic transcript", True), ("CV", False))) -> DocumentChecklistTemplate:
    template = DocumentChecklistTemplate(name="Admission", kind="admission", country_id=world["university"].country_id, gate_mode=gate_mode, version=3)
    db.add(template)
    await db.flush()
    for position, (document_type, required) in enumerate(items, start=1):
        db.add(DocumentChecklistTemplateItem(template_id=template.id, position=position, document_type=document_type, required=required, allowed_statuses=["pending", "requested", "verified", "not_required"]))
    await db.commit()
    return template


@pytest_asyncio.fixture
async def world(db_session):
    return await offers_world(db_session)


def _items(data) -> dict:
    return {i["document_type"]: i for i in data["checklist"]["items"]}


# --- pure rules ---------------------------------------------------------------------------------------------------------------


def test_item_status_prefers_the_mark_then_the_best_current_document():
    assert item_status(None, []) == "pending"
    assert item_status(None, ["pending", "verified", "expired"]) == "verified"
    assert item_status(None, ["reupload_required", "under_review"]) == "under_review"
    assert item_status("requested", ["verified"]) == "requested"
    assert item_status("not_required", []) == "not_required"


def test_summary_counts_required_and_optional_and_lists_the_missing():
    rows = [
        {"id": 1, "label": "Passport", "required": True, "status": "verified"},
        {"id": 2, "label": "Transcript", "required": True, "status": "pending"},
        {"id": 3, "label": "CV", "required": False, "status": "approved"},
    ]
    s = summary(rows)
    assert (s["required_total"], s["required_complete"], s["optional_total"], s["optional_complete"], s["ready"]) == (2, 1, 1, 1, False)
    assert s["missing"] == [{"id": 2, "label": "Transcript", "status": "pending"}]


# --- create, links, marks, summary ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_counselor_creates_the_checklist_from_the_template_and_documents_auto_link(db_session, world):
    app = world["direct_app"]
    template = await mk_template(db_session, world)
    passport = await mk_doc(db_session, student=world["direct_student"], document_type="passport", status="verified")
    elsewhere = await mk_doc(db_session, student=world["direct_student"], application=world["app"], document_type="Passport")  # another app
    async with client_for(world["counselor"].email) as c:
        before = (await c.get(CHECKLIST.format(app.id))).json()
        r = await c.post(CHECKLIST.format(app.id))
        again = await c.post(CHECKLIST.format(app.id))
    assert before["checklist"] is None and before["template"]["id"] == str(template.id) and before["template"]["version"] == 3
    assert r.status_code == 201, r.text
    data = r.json()
    assert (data["checklist"]["template_version"], data["checklist"]["gate_mode"]) == (3, "block")
    items = _items(data)
    assert [d["id"] for d in items["Passport"]["documents"]] == [str(passport.id)] and str(elsewhere.id) not in str(items)
    assert items["Passport"]["status"] == "verified" and items["Academic transcript"]["status"] == "pending"
    assert data["checklist"]["summary"]["required_complete"] == 1 and data["checklist"]["summary"]["required_total"] == 2
    assert "file_url" not in str(data)
    assert again.status_code == 409
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.checklist.create"))
    assert audit.metadata_json["template_version"] == 3


@pytest.mark.asyncio
async def test_without_a_template_the_checklist_is_empty_in_warn_mode_and_takes_counselor_items(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.get(CHECKLIST.format(app.id))).json()["template"] is None
        created = await c.post(CHECKLIST.format(app.id))
        added = await c.post(ITEMS.format(app.id), json={"document_type": "Other", "label": "Portfolio", "required": True})
        bad = await c.post(ITEMS.format(app.id), json={"document_type": "Other", "required": True})
    assert created.status_code == 201 and created.json()["checklist"]["gate_mode"] == "warn" and created.json()["checklist"]["items"] == []
    assert added.status_code == 201, added.text
    item = added.json()["checklist"]["items"][0]
    assert (item["label"], item["required"], item["removable"]) == ("Portfolio", True, True)
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_link_mark_unlink_and_remove(db_session, world):
    app = world["direct_app"]
    await mk_template(db_session, world)
    transcript = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Transcript scan", status="verified")
    foreign = await mk_doc(db_session, record=world["record"], application=world["app"], document_type="Transcript")
    async with client_for(world["counselor"].email) as c:
        data = (await c.post(CHECKLIST.format(app.id))).json()
        item = _items(data)["Academic transcript"]
        linked = await c.put(LINK.format(app.id, item["id"], transcript.id))
        twice = await c.put(LINK.format(app.id, item["id"], transcript.id))
        refused = await c.put(LINK.format(app.id, item["id"], foreign.id))
        marked = await c.patch(ITEM.format(app.id, item["id"]), json={"mark": "requested"})
        not_allowed = await c.patch(ITEM.format(app.id, item["id"]), json={"mark": "verified"})
        unlinked = await c.delete(LINK.format(app.id, item["id"], transcript.id))
        template_remove = await c.delete(ITEM.format(app.id, item["id"]))
        extra = (await c.post(ITEMS.format(app.id), json={"document_type": "CV", "required": False})).json()
        extra_id = [i for i in extra["checklist"]["items"] if i["removable"]][0]["id"]
        removed = await c.delete(ITEM.format(app.id, extra_id))
    assert linked.status_code == 200 and _items(linked.json())["Academic transcript"]["status"] == "verified"
    assert twice.status_code == 200 and len(_items(twice.json())["Academic transcript"]["documents"]) == 1
    assert refused.status_code == 422
    assert _items(marked.json())["Academic transcript"]["status"] == "requested"
    assert not_allowed.status_code == 422
    assert unlinked.status_code == 200 and _items(unlinked.json())["Academic transcript"]["documents"] == []
    assert template_remove.status_code == 409
    assert removed.status_code == 200 and extra_id not in str(removed.json())


@pytest.mark.asyncio
async def test_linking_clears_a_requested_mark(db_session, world):
    app = world["direct_app"]
    await mk_template(db_session, world)
    doc = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Scan", status="under_review")
    async with client_for(world["counselor"].email) as c:
        item = _items((await c.post(CHECKLIST.format(app.id))).json())["Passport"]
        await c.patch(ITEM.format(app.id, item["id"]), json={"mark": "requested"})
        r = await c.put(LINK.format(app.id, item["id"], doc.id))
    assert _items(r.json())["Passport"]["status"] == "under_review" and _items(r.json())["Passport"]["mark"] is None


@pytest.mark.asyncio
async def test_appendix_b_a_request_on_one_application_leaves_the_other_complete(db_session, world):
    """University A asks again for the transcript: pending on A only (AC 9)."""
    await mk_template(db_session, world)
    student = world["direct_student"]
    second = await mk_application(
        db_session, agent=None, university=world["university"], student=student, status="university_selection", counselor_id=world["counselor"].id
    )
    await mk_doc(db_session, student=student, document_type="Academic transcript", status="verified")
    async with client_for(world["counselor"].email) as c:
        a = _items((await c.post(CHECKLIST.format(world["direct_app"].id))).json())["Academic transcript"]
        b = _items((await c.post(CHECKLIST.format(second.id))).json())["Academic transcript"]
        await c.patch(ITEM.format(world["direct_app"].id, a["id"]), json={"mark": "requested"})
        a_after = _items((await c.get(CHECKLIST.format(world["direct_app"].id))).json())["Academic transcript"]
        b_after = _items((await c.get(CHECKLIST.format(second.id))).json())["Academic transcript"]
    assert a["status"] == b["status"] == "verified"
    assert (a_after["status"], b_after["status"]) == ("requested", "verified")


@pytest.mark.asyncio
async def test_documents_completed_on_is_set_when_complete_and_cleared_when_not(db_session, world):
    app = world["direct_app"]
    await mk_template(db_session, world, items=(("Passport", True),))
    doc = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Passport", status="pending")
    async with client_for(world["counselor"].email) as c:
        created = (await c.post(CHECKLIST.format(app.id))).json()
        assert (await fresh(db_session, app)).documents_completed_on is None
        verified = await c.patch(VERIFY.format(doc.id), json={"verification_status": "verified", "expiry_date": (date.today() + timedelta(days=400)).isoformat()})
        assert verified.status_code == 200, verified.text
        assert (await fresh(db_session, app)).documents_completed_on is not None
        item = _items(created)["Passport"]
        await c.patch(ITEM.format(app.id, item["id"]), json={"mark": "requested"})
        assert (await fresh(db_session, app)).documents_completed_on is None
        await c.patch(ITEM.format(app.id, item["id"]), json={"mark": None})
        listed = (await c.get(CHECKLIST.format(app.id))).json()
    assert listed["checklist"]["documents_completed_on"] is not None and listed["checklist"]["summary"]["ready"] is True


@pytest.mark.asyncio
async def test_a_replaced_document_moves_its_links_and_expiry_refreshes_completion(db_session, world):
    app = world["direct_app"]
    await mk_template(db_session, world, items=(("Passport", True),))
    doc = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Passport", status="verified")
    doc.expiry_date = date.today() + timedelta(days=30)
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        item = _items((await c.post(CHECKLIST.format(app.id))).json())["Passport"]
        assert (await fresh(db_session, app)).documents_completed_on is not None
        await expire_documents(db_session, date.today() + timedelta(days=60))
        assert (await fresh(db_session, app)).documents_completed_on is None
        replaced = await c.post(f"/api/v1/workflows/overseas/documents/{doc.id}/versions", files={"file": ("p.pdf", PDF, "application/pdf")})
        assert replaced.status_code == 201, replaced.text
        after = _items((await c.get(CHECKLIST.format(app.id))).json())["Passport"]
    assert [d["id"] for d in after["documents"]] == [replaced.json()["id"]] and after["status"] == "pending"
    assert item["id"] == after["id"]


# --- scope ------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_other_counselor_agent_read_only_student_reads_own(db_session, world):
    await mk_template(db_session, world)
    other_student = await mk_user(db_session, role="overseas_student")
    async with client_for(world["counselor"].email) as c:
        agency = (await c.post(CHECKLIST.format(world["app"].id))).json()
        await c.post(CHECKLIST.format(world["direct_app"].id))
    item_id = agency["checklist"]["items"][0]["id"]
    async with client_for(world["counselor2"].email) as c:
        assert (await c.get(CHECKLIST.format(world["app"].id))).status_code == 403
    async with client_for(world["master"].email) as c:
        read = await c.get(CHECKLIST.format(world["app"].id))
        assert (await c.patch(ITEM.format(world["app"].id, item_id), json={"mark": "requested"})).status_code == 403
        assert (await c.post(ITEMS.format(world["app"].id), json={"document_type": "CV", "required": False})).status_code == 403
    assert read.status_code == 200 and read.json()["checklist"]["summary"]["required_total"] == 2
    assert read.json()["template"] is None and read.json()["documents"] == []
    async with client_for(world["direct_student"].email) as c:
        own = await c.get(CHECKLIST.format(world["direct_app"].id))
    async with client_for(other_student.email) as c:
        assert (await c.get(CHECKLIST.format(world["direct_app"].id))).status_code == 403
    assert own.status_code == 200 and own.json()["checklist"]["summary"]["required_total"] == 2
    async with client_for(world["counselor"].email) as c:  # an item of another application is 404
        assert (await c.patch(ITEM.format(world["direct_app"].id, item_id), json={"mark": "requested"})).status_code == 404


# --- the Ready-for-Submission gate (AC 5) -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_mode_refuses_ready_for_submission_with_the_missing_items_even_before_the_checklist_exists(db_session, world):
    app = world["direct_app"]
    await mk_template(db_session, world, gate_mode="block")
    async with client_for(world["counselor"].email) as c:
        r = await c.post(SUB.format(app.id), json=READY)
        overridden = await c.post(SUB.format(app.id), json=READY | {"override_reason": "University said fine"})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["gate_mode"] == "block" and [m["label"] for m in detail["missing"]] == ["Passport", "Academic transcript"]
    assert overridden.status_code == 409
    assert (await fresh(db_session, app)).sub_status != "ready_for_submission"
    assert await db_session.scalar(select(ApplicationChecklistItem.id).where(ApplicationChecklistItem.application_id == app.id).limit(1)) is not None


@pytest.mark.asyncio
async def test_block_mode_passes_once_every_required_item_is_complete(db_session, world):
    app = world["direct_app"]
    await mk_template(db_session, world, gate_mode="block")
    for document_type in ("Passport", "Academic transcript"):
        await mk_doc(db_session, student=world["direct_student"], application=app, document_type=document_type, status="verified")
    async with client_for(world["counselor"].email) as c:
        r = await c.post(SUB.format(app.id), json=READY)
    assert r.status_code == 200, r.text
    assert (await fresh(db_session, app)).sub_status == "ready_for_submission"


@pytest.mark.asyncio
async def test_warn_mode_needs_an_override_reason_and_records_it_in_history(db_session, world):
    app = world["direct_app"]
    await mk_template(db_session, world, gate_mode="warn")
    async with client_for(world["counselor"].email) as c:
        r = await c.post(SUB.format(app.id), json=READY)
        ok = await c.post(SUB.format(app.id), json=READY | {"override_reason": "  University accepts the transcript later  "})
    assert r.status_code == 409 and r.json()["detail"]["gate_mode"] == "warn"
    assert ok.status_code == 200, ok.text
    assert (await fresh(db_session, app)).sub_status == "ready_for_submission"
    row = await db_session.scalar(
        select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app.id, ApplicationStatusHistory.to_sub_status == "ready_for_submission")
    )
    assert row.reason == "Override: University accepts the transcript later"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.sub_status"))
    assert audit.metadata_json["checklist_override"] == "University accepts the transcript later"


@pytest.mark.asyncio
async def test_no_template_and_no_checklist_passes_and_other_sub_statuses_are_not_gated(db_session, world):
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(world["direct_app"].id), json=READY)).status_code == 200
    await mk_template(db_session, world, gate_mode="block")
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(world["app"].id), json={"sub_status": "documents_pending"})).status_code == 200


@pytest.mark.asyncio
async def test_the_agency_route_is_gated_too(db_session, world):
    await mk_template(db_session, world, gate_mode="block")
    async with client_for(world["master"].email) as c:
        r = await c.post(AGENT_SUB.format(world["app"].id), json=READY)
    assert r.status_code == 409 and r.json()["detail"]["gate_mode"] == "block"


@pytest.mark.asyncio
async def test_a_document_of_another_student_never_auto_links(db_session, world):
    await mk_template(db_session, world)
    other = await mk_user(db_session, role="overseas_student")
    db_session.add(StudentDocument(student_id=other.id, document_type="Passport", file_url="x", verification_status="verified"))
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        data = (await c.post(CHECKLIST.format(world["direct_app"].id))).json()
    assert _items(data)["Passport"]["documents"] == []
