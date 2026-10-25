"""ccrm-022 (DEC-SCOPE-263, AC 10) -- document sensitivity classes, who may see identity/financial documents, audited downloads (a
refusal too), the /files/download gap and file keys kept out of lists. Spec:
docs/superpowers/specs/2026-10-25-ccrm-022-sensitive-documents-design.md (SD1-SD8)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.document_checklists import highest, type_sensitivity
from app.models import ApplicationChecklist, ApplicationChecklistItem, ApplicationChecklistItemDocument, AuditLog, DocumentChecklistTemplate, DocumentEvent, StudentDocument
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn003_helpers import agency_document
from tests.test_ovs_005_documents import _make_application, _make_university

DOWNLOAD = "/api/v1/workflows/overseas/documents/{}/download"
FILES = "/api/v1/files/download"
TEMPLATES = "/api/v1/overseas-admin/checklists"
CHECKLIST = "/api/v1/workflows/overseas/applications/{}/checklist"
REP_DOCS = "/api/v1/portal/overseas/university/documents"


async def _world(db, *types: str) -> dict:
    student = await mk_user(db, role="overseas_student", full_name=f"Sensitive Student {uniq()}")
    counselor = await mk_user(db, role="counselor", full_name="Sensitive Counselor")
    university = await _make_university(db)
    application = await _make_application(db, student, university, counselor)
    rep = await mk_user(db, role="university_rep", full_name="Rep", profile={"university_id": str(university.id)})
    admin = await mk_user(db, role="overseas_admin", full_name="Overseas Admin")
    docs = {}
    for document_type in types or ("Passport", "Financial documents", "Transcripts"):
        docs[document_type] = StudentDocument(student_id=student.id, application_id=application.id, document_type=document_type, file_url=f"uploads/{uniq('doc')}.pdf", verification_status="pending")
        db.add(docs[document_type])
    await db.commit()
    return {"student": student, "counselor": counselor, "university": university, "application": application, "rep": rep, "admin": admin, "docs": docs}


async def _audits(db, document_id, action="document.download") -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(document_id)).order_by(AuditLog.created_at))).all())


# --- SD1: the classes -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("document_type", "expected"),
    [
        ("Passport", "identity"),
        ("QA passport copy", "identity"),
        ("Aadhaar card", "identity"),
        ("National ID", "identity"),
        ("Birth certificate", "identity"),
        ("Financial documents", "financial"),
        ("Bank statement", "financial"),
        ("Sponsor letter", "financial"),
        ("Education loan sanction", "financial"),
        ("Income tax return", "financial"),
        ("Transcripts", "standard"),
        ("CV", "standard"),
        ("Offer letter", "standard"),
        ("Bankruptcy-free", "standard"),  # whole words only
        ("", "standard"),
    ],
)
def test_a_type_is_classed_by_whole_words(document_type, expected):
    assert type_sensitivity(document_type) == expected


def test_a_label_can_class_an_other_type_and_the_highest_class_wins():
    assert type_sensitivity("Other", "Bank statement") == "financial"
    assert highest(["standard", "identity"]) == "identity"
    assert highest(["identity", "financial", "standard"]) == "financial"
    assert highest([]) == "standard"


# --- SD2: checklist items carry a class --------------------------------------------------------------------------------------------


def _template_body(country_id, items) -> dict:
    return {
        "name": f"Sensitive {uniq()}", "kind": "admission", "country_id": str(country_id), "university_id": None, "course_level": None,
        "intake": None, "gate_mode": "warn", "notes": None, "items": items,
    }  # fmt: skip


@pytest.mark.asyncio
async def test_a_template_item_takes_its_types_class_unless_the_admin_sets_one(db_session):
    w = await _world(db_session, "Transcripts")
    items = [
        {"document_type": "Passport", "label": None, "required": True, "allowed_statuses": [], "notes": None},
        {"document_type": "Other", "label": "Sponsor affidavit", "required": True, "allowed_statuses": [], "notes": None},
        {"document_type": "Transcripts", "label": None, "required": True, "allowed_statuses": [], "notes": None, "sensitivity": "financial"},
        {"document_type": "CV", "label": None, "required": False, "allowed_statuses": [], "notes": None},
    ]
    async with client_for(w["admin"].email) as c:
        response = await c.post(TEMPLATES, json=_template_body(w["university"].country_id, items))
        assert response.status_code == 201, response.text
        assert [i["sensitivity"] for i in response.json()["items"]] == ["identity", "financial", "financial", "standard"]
        bad = items[:1] + [{**items[3], "sensitivity": "secret"}]
        assert (await c.post(TEMPLATES, json=_template_body(w["university"].country_id, bad))).status_code == 422


@pytest.mark.asyncio
async def test_an_application_checklist_copies_the_class_and_a_counselor_item_takes_its_types(db_session):
    w = await _world(db_session, "Transcripts")
    template = DocumentChecklistTemplate(name="Adm", kind="admission", country_id=w["university"].country_id, gate_mode="warn", version=1)
    db_session.add(template)
    await db_session.flush()
    from app.models import DocumentChecklistTemplateItem

    db_session.add(DocumentChecklistTemplateItem(template_id=template.id, position=1, document_type="Transcripts", required=True, allowed_statuses=[], sensitivity="financial"))
    await db_session.commit()
    async with client_for(w["counselor"].email) as c:
        created = await c.post(CHECKLIST.format(w["application"].id))
        assert created.status_code == 201, created.text
        item = created.json()["checklist"]["items"][0]
        assert item["sensitivity"] == "financial"
        assert [d["sensitivity"] for d in item["documents"]] == ["financial"]  # the linked transcript is raised by its item
        added = await c.post(CHECKLIST.format(w["application"].id) + "/items", json={"document_type": "Passport", "required": True})
        assert added.status_code == 201, added.text
        assert {i["document_type"]: i["sensitivity"] for i in added.json()["checklist"]["items"]} == {"Transcripts": "financial", "Passport": "identity"}


# --- SD3 / AC 10: the university_rep ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_university_rep_sees_only_standard_documents_and_cannot_open_a_financial_one(db_session):
    w = await _world(db_session)
    async with client_for(w["rep"].email) as c:
        listed = await c.get(REP_DOCS)
        assert listed.status_code == 200, listed.text
        assert [r["document"] for r in listed.json()["rows"]] == ["Transcripts"]
        refused = await c.get(DOWNLOAD.format(w["docs"]["Financial documents"].id))
    assert refused.status_code == 403
    denied = await _audits(db_session, w["docs"]["Financial documents"].id)
    assert [(a.user_id, a.outcome, a.metadata_json["sensitivity"]) for a in denied] == [(w["rep"].id, "denied", "financial")]


@pytest.mark.asyncio
async def test_a_transcript_linked_to_a_financial_item_is_hidden_from_the_rep(db_session):
    w = await _world(db_session, "Transcripts")
    db_session.add(ApplicationChecklist(application_id=w["application"].id, gate_mode="warn"))
    await db_session.flush()
    item = ApplicationChecklistItem(application_id=w["application"].id, position=1, document_type="Other", label="Sponsor proof", required=True, allowed_statuses=[], sensitivity="financial")
    db_session.add(item)
    await db_session.flush()
    db_session.add(ApplicationChecklistItemDocument(item_id=item.id, document_id=w["docs"]["Transcripts"].id))
    await db_session.commit()
    async with client_for(w["rep"].email) as c:
        assert (await c.get(REP_DOCS)).json()["rows"] == []


@pytest.mark.asyncio
async def test_the_counselor_queue_shows_each_documents_class(db_session):
    w = await _world(db_session)
    async with client_for(w["counselor"].email) as c:
        rows = (await c.get("/api/v1/portal/overseas/counselor/documents")).json()["rows"]
    assert {r["document"]: r["sensitivity"] for r in rows} == {"Passport": "identity", "Financial documents": "financial", "Transcripts": "standard"}


# --- SD4: downloads are audited with their class ------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["student", "counselor", "admin"])
async def test_each_authorised_download_is_audited_with_its_class(db_session, who):
    w = await _world(db_session)
    passport = w["docs"]["Passport"]
    async with client_for(w[who].email) as c:
        response = await c.get(DOWNLOAD.format(passport.id))
    assert response.status_code == 200, response.text
    rows = await _audits(db_session, passport.id)
    assert [(a.user_id, a.outcome, a.metadata_json["sensitivity"]) for a in rows] == [(w[who].id, "recorded", "identity")]
    events = (await db_session.scalars(select(DocumentEvent.event).where(DocumentEvent.document_id == passport.id))).all()
    assert list(events) == ["downloaded"]


@pytest.mark.asyncio
async def test_the_agency_reaches_its_applications_passport_and_another_counselor_does_not(db_session):
    ctx = await mk_active_org(db_session, name=f"Sensitive Agency {uniq()}")
    world = await agency_document(db_session, ctx)
    stranger = await mk_user(db_session, role="counselor", full_name="Other Counselor")
    async with client_for(ctx["master"].email) as c:
        assert (await c.get(DOWNLOAD.format(world["document"].id))).status_code == 200
    async with client_for(stranger.email) as c:
        assert (await c.get(DOWNLOAD.format(world["document"].id))).status_code == 403
    outcomes = [(a.user_id, a.outcome) for a in await _audits(db_session, world["document"].id)]
    assert outcomes == [(ctx["master"].id, "recorded"), (stranger.id, "denied")]


@pytest.mark.asyncio
async def test_a_refused_standard_download_is_not_audited(db_session):
    w = await _world(db_session, "Transcripts")
    async with client_for(w["rep"].email) as c:
        assert (await c.get(DOWNLOAD.format(w["docs"]["Transcripts"].id))).status_code == 403
    assert await _audits(db_session, w["docs"]["Transcripts"].id) == []


# --- SD5: /files/download no longer reaches overseas documents ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_files_download_refuses_every_shape_of_an_overseas_document_key(db_session):
    w = await _world(db_session, "Passport", "Transcripts")
    passport, transcript = w["docs"]["Passport"], w["docs"]["Transcripts"]
    local = StudentDocument(student_id=w["student"].id, document_type="Bank statement", file_url=f"/local-files/uploads/{uniq('local')}.pdf", verification_status="pending")
    archived = StudentDocument(student_id=w["student"].id, document_type="CV", file_url=f"uploads/{uniq('old')}.pdf", verification_status="pending", archived_at=datetime.now(UTC))
    db_session.add_all([local, archived])
    await db_session.flush()
    replaced_key = f"uploads/{uniq('replaced')}.pdf"
    db_session.add(DocumentEvent(document_id=transcript.id, event="replaced", file_key=replaced_key))
    await db_session.commit()
    keys = [passport.file_url, transcript.file_url, local.file_url.removeprefix("/local-files/"), archived.file_url, replaced_key, f"agent-documents/{uniq()}"]
    async with client_for(w["student"].email) as c:
        for key in keys:
            assert (await c.get(FILES, params={"key": key})).status_code == 404, key
        assert (await c.get(FILES, params={"key": f"uploads/{uniq('unrelated')}.pdf"})).status_code == 200


# --- SD6: lists never return file keys ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_students_downloads_list_has_no_file_keys(db_session):
    w = await _world(db_session, "Passport")
    w["docs"]["Passport"].verification_status = "verified"
    await db_session.commit()
    async with client_for(w["student"].email) as c:
        body = (await c.get("/api/v1/portal/overseas/student/downloads")).text
    assert w["docs"]["Passport"].file_url not in body
    assert "Passport" in body


@pytest.mark.asyncio
async def test_the_agents_documents_list_has_no_file_keys(db_session):
    ctx = await mk_active_org(db_session, name=f"Keyless Agency {uniq()}")
    world = await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as c:
        response = await c.get("/api/v1/portal/overseas/agent/documents")
    assert response.status_code == 200
    assert world["document"].file_url not in response.text
    assert all("file" not in row for row in response.json()["rows"])
