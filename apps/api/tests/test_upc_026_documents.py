"""upc-026 -- University document centre (spec §1-§5; AC1, AC2, P1, N1, E1, R1, S1; DEC-SCOPE-138 DC1-DC15)."""

import io
import uuid
import zipfile

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.models import AuditLog, University, UniversityDocument
from app.services import university_documents as svc
from tests.enh025_helpers import png_bytes
from tests.test_rec_009_resumes import PDF, docx, plain_zip
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url

KINDS = [
    "mou", "partnership_agreement", "commission_agreement", "brochure", "course_list", "fee_structure", "entry_requirements",
    "scholarship_information", "marketing_materials", "application_guidelines", "contact_documents", "training_documents",
]  # fmt: skip
MENU = "/api/v1/partnership/documents"


def docs_url(university_id, tail: str = "") -> str:
    return url(university_id, "documents") + tail


def ooxml(part: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(part, "<x/>")
    return buffer.getvalue()


async def _owned(client, db):
    """A head creates a university and makes `pm` its primary manager; returns (head, pm, other_pm, university). Logged in as pm."""
    head = await make_head(db)
    pm, other = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    assert response.status_code == 200, response.text
    await login(client, pm)
    return head, pm, other, uni


async def upload(client, university_id, *, kind="fee_structure", title="Fee structure 2026", shareable=None, data=PDF, name="fees.pdf"):
    form = {"kind": kind, "title": title} | ({} if shareable is None else {"shareable": "true" if shareable else "false"})
    return await client.post(docs_url(university_id), data=form, files={"file": (name, data, "application/octet-stream")})


async def add(client, university_id, **kwargs) -> dict:
    response = await upload(client, university_id, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()["document"]


async def new_version(client, university_id, document_id, data=PDF, name="fees-v2.pdf"):
    return await client.post(docs_url(university_id, f"/{document_id}/versions"), files={"file": (name, data, "application/pdf")})


def file_url(university_id, document_id, version: int | None = None) -> str:
    return docs_url(university_id, f"/{document_id}/file") + (f"?version={version}" if version else "")


# --- AC1: the 12 kinds -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_twelve_kinds_upload_and_list_in_source_order(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    assert svc.KINDS == tuple(KINDS)
    for kind in reversed(KINDS):
        await add(client, uni["id"], kind=kind, title=f"{kind} document")
    page = (await client.get(docs_url(uni["id"]))).json()
    assert page["total"] == 12 and [d["kind"] for d in page["items"]] == KINDS


@pytest.mark.asyncio
async def test_an_unknown_kind_is_422(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    assert (await upload(client, uni["id"], kind="invoice")).status_code == 422


@pytest.mark.asyncio
async def test_upload_stores_version_one_with_every_field_and_audits_ids_only(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"], title="  Fee structure 2026  ")
    assert doc["title"] == "Fee structure 2026" and doc["kind"] == "fee_structure" and doc["current_version"] == 1
    assert doc["shareable"] is True  # DC3 default for a fee structure
    assert doc["university"] == {"id": uni["id"], "name": uni["name"], "university_code": uni["university_code"]}
    [v] = doc["versions"]
    assert v["version"] == 1 and v["file_name"] == "fees.pdf" and v["content_type"] == "application/pdf" and v["size_bytes"] == len(PDF)
    assert v["uploaded_by"]["id"] == str(pm.id) and v["uploaded_at"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == doc["id"], AuditLog.action == "university_document.upload"))
    assert audit.metadata_json["university_id"] == uni["id"] and audit.metadata_json["version"] == 1
    assert "Fee" not in str(audit.metadata_json) and "fees.pdf" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "shareable"), [("mou", False), ("partnership_agreement", False), ("contact_documents", False), ("brochure", True), ("training_documents", True)])
async def test_shareable_defaults_per_kind(client, db_session, kind, shareable):
    _, _, _, uni = await _owned(client, db_session)
    assert (await add(client, uni["id"], kind=kind, title="Doc"))["shareable"] is shareable


@pytest.mark.asyncio
async def test_the_uploader_may_override_the_default(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    assert (await add(client, uni["id"], kind="mou", title="MoU", shareable=True))["shareable"] is True
    assert (await add(client, uni["id"], kind="brochure", title="Brochure", shareable=False))["shareable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("title", ["", " ", "A", "x" * 201])
async def test_title_is_two_to_two_hundred_characters(client, db_session, title):
    _, _, _, uni = await _owned(client, db_session)
    assert (await upload(client, uni["id"], title=title)).status_code == 422


@pytest.mark.asyncio
async def test_same_title_and_kind_twice_is_409_but_another_kind_is_fine(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    await add(client, uni["id"], title="Fees")
    response = await upload(client, uni["id"], title="FEES")
    assert response.status_code == 409 and "new version" in response.json()["detail"]
    await add(client, uni["id"], kind="course_list", title="Fees")


# --- N1: file checks (DC4, DC5) --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (ooxml("xl/workbook.xml"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        (ooxml("ppt/presentation.xml"), "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        (png_bytes(), "image/png"),
    ],
)
async def test_office_and_image_files_are_typed_by_their_bytes(client, db_session, data, content_type):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"], kind="marketing_materials", title="Pack", data=data, name="pack.bin")
    assert doc["versions"][0]["content_type"] == content_type


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"MZ\x90\x00\x03" + b"\x00" * 60, b"\x7fELF\x02\x01\x01", b"#!/bin/sh\nrm -rf /\n", plain_zip(), b"<html><script>x</script>"])
async def test_an_executable_or_unknown_file_is_422_and_nothing_is_stored(client, db_session, monkeypatch, data):
    _, _, _, uni = await _owned(client, db_session)
    stored = []
    monkeypatch.setattr(svc, "store", lambda *a: stored.append(a) or "university-documents/x")
    response = await upload(client, uni["id"], data=data, name="fees.pdf")
    assert response.status_code == 422 and "PDF" in response.json()["detail"]
    assert stored == []


@pytest.mark.asyncio
async def test_empty_file_is_422_and_oversize_is_413(client, db_session, monkeypatch):
    _, _, _, uni = await _owned(client, db_session)
    assert (await upload(client, uni["id"], data=b"")).status_code == 422
    monkeypatch.setattr(svc.settings, "max_upload_bytes", 32)
    assert (await upload(client, uni["id"], data=PDF + b"0" * 40)).status_code == 413


@pytest.mark.asyncio
async def test_the_stored_file_is_discarded_when_the_write_fails(client, db_session, monkeypatch):
    _, _, _, uni = await _owned(client, db_session)
    discarded = []
    monkeypatch.setattr(svc, "discard", discarded.append)

    async def lost_race(*_args, **_kwargs):
        raise HTTPException(409, "lost a race")

    monkeypatch.setattr(svc, "check_title_free", lost_race)
    assert (await upload(client, uni["id"])).status_code == 409
    assert len(discarded) == 1 and discarded[0].startswith("university-documents/")


# --- E1: versions (DC6) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_new_version_becomes_current_and_the_old_one_still_downloads(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"])
    response = await new_version(client, uni["id"], doc["id"], data=PDF + b"% v2\n")
    assert response.status_code == 201, response.text
    body = response.json()["document"]
    assert body["current_version"] == 2 and [v["version"] for v in body["versions"]] == [2, 1]
    assert (await client.get(file_url(uni["id"], doc["id"]))).content == PDF + b"% v2\n"
    assert (await client.get(file_url(uni["id"], doc["id"], 1))).content == PDF
    assert (await client.get(file_url(uni["id"], doc["id"], 3))).status_code == 404


@pytest.mark.asyncio
async def test_version_limit_is_409(client, db_session, monkeypatch):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"])
    monkeypatch.setattr(svc, "MAX_VERSIONS", 2)
    assert (await new_version(client, uni["id"], doc["id"])).status_code == 201
    assert (await new_version(client, uni["id"], doc["id"])).status_code == 409


@pytest.mark.asyncio
async def test_document_limit_is_409(client, db_session, monkeypatch):
    _, _, _, uni = await _owned(client, db_session)
    monkeypatch.setattr(svc, "MAX_DOCUMENTS", 1)
    await add(client, uni["id"])
    assert (await upload(client, uni["id"], title="Another")).status_code == 409


@pytest.mark.asyncio
async def test_a_version_of_another_universitys_document_is_404(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"])
    _, _, _, other_uni = await _owned(client, db_session)
    assert (await new_version(client, other_uni["id"], doc["id"])).status_code == 404
    assert (await client.get(file_url(other_uni["id"], doc["id"]))).status_code == 404


# --- PATCH metadata -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_renames_and_toggles_shareable_auditing_field_names(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"], kind="mou", title="MoU draft")
    response = await client.patch(docs_url(uni["id"], f"/{doc['id']}"), json={"title": "MoU signed", "shareable": True})
    assert response.status_code == 200, response.text
    assert response.json()["document"]["title"] == "MoU signed" and response.json()["document"]["shareable"] is True
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == doc["id"], AuditLog.action == "university_document.update"))
    assert audit.metadata_json["fields"] == ["shareable", "title"]
    assert (await client.patch(docs_url(uni["id"], f"/{doc['id']}"), json={"kind": "brochure"})).status_code == 422  # extra field


# --- AC2: the commission agreement (DC2) -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_commission_agreement_can_never_be_shareable(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    assert (await upload(client, uni["id"], kind="commission_agreement", title="Commission", shareable=True)).status_code == 422
    doc = await add(client, uni["id"], kind="commission_agreement", title="Commission")
    assert doc["shareable"] is False
    assert (await client.patch(docs_url(uni["id"], f"/{doc['id']}"), json={"shareable": True})).status_code == 422


@pytest.mark.asyncio
async def test_a_role_without_commission_access_never_sees_the_commission_agreement(client, db_session, monkeypatch):
    _, _, _, uni = await _owned(client, db_session)
    commission = await add(client, uni["id"], kind="commission_agreement", title="Commission terms")
    await add(client, uni["id"], kind="brochure", title="Brochure")
    assert (await client.get(docs_url(uni["id"]))).json()["total"] == 2  # the manager sees it
    monkeypatch.setattr(svc, "can_see_commission", lambda _user: False)  # e.g. a future reader role without commission access
    page = (await client.get(docs_url(uni["id"]))).json()
    assert [d["kind"] for d in page["items"]] == ["brochure"] and page["total"] == 1
    assert commission["id"] not in str((await client.get(MENU, params={"q": uni["name"]})).json())
    assert (await client.get(file_url(uni["id"], commission["id"]))).status_code == 404


# --- P1 + DC7: the shareable slice for overseas_admin --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overseas_admin_reads_and_downloads_shareable_documents_only(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    fees = await add(client, uni["id"])
    mou = await add(client, uni["id"], kind="mou", title="MoU")
    commission = await add(client, uni["id"], kind="commission_agreement", title="Commission")
    await as_role(client, db_session, "overseas_admin", "overseas")
    page = (await client.get(docs_url(uni["id"]))).json()
    assert [d["id"] for d in page["items"]] == [fees["id"]] and page["total"] == 1
    response = await client.get(file_url(uni["id"], fees["id"]))
    assert response.status_code == 200 and response.content == PDF
    for hidden in (mou, commission):
        assert (await client.get(file_url(uni["id"], hidden["id"]))).status_code == 404
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_manage_documents"] is False
    assert (await upload(client, uni["id"], title="Admin upload")).status_code == 403


# --- R1: access ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_can_manage_documents_follows_the_contacts_scope(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_manage_documents"] is True
    await login(client, other)
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_manage_documents"] is False
    response = await upload(client, uni["id"])
    assert response.status_code == 403
    await login(client, head)
    assert (await upload(client, uni["id"])).status_code == 201


@pytest.mark.asyncio
async def test_non_owner_manager_still_reads_every_document(client, db_session):
    _, _, other, uni = await _owned(client, db_session)
    await add(client, uni["id"], kind="mou", title="MoU")
    await login(client, other)
    assert (await client.get(docs_url(uni["id"]))).json()["total"] == 1
    doc = (await client.get(docs_url(uni["id"]))).json()["items"][0]
    assert (await new_version(client, uni["id"], doc["id"])).status_code == 403
    assert (await client.patch(docs_url(uni["id"], f"/{doc['id']}"), json={"title": "Nope"})).status_code == 403


@pytest.mark.asyncio
async def test_inactive_university_is_read_only(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"])
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(active=False))
    await db_session.commit()
    assert (await upload(client, uni["id"], title="Later")).status_code == 409
    assert (await new_version(client, uni["id"], doc["id"])).status_code == 409
    assert (await client.get(file_url(uni["id"], doc["id"]))).status_code == 200


@pytest.mark.asyncio
async def test_counselor_is_403_and_unknown_ids_are_404(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    assert (await client.get(docs_url(uuid.uuid4()))).status_code == 404
    assert (await upload(client, uuid.uuid4())).status_code == 404
    assert (await client.get(file_url(uni["id"], uuid.uuid4()))).status_code == 404
    assert (await client.patch(docs_url(uni["id"], f"/{uuid.uuid4()}"), json={"title": "Gone"})).status_code == 404
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.get(docs_url(uni["id"]))).status_code == 403
    assert (await client.get(MENU)).status_code == 403
    assert (await upload(client, uni["id"])).status_code == 403


# --- S1: downloads (DC10) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_download_is_audited_and_served_as_a_safe_attachment(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"], name='evil"\r\nX-Injected: 1.pdf')
    response = await client.get(file_url(uni["id"], doc["id"]))
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="{uni["university_code"]}-fee_structure-v1.pdf"'
    assert response.headers["cache-control"] == "private, no-store" and response.headers["x-content-type-options"] == "nosniff"
    assert "x-injected" not in response.headers
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == doc["id"], AuditLog.action == "university_document.download"))
    assert audit.metadata_json["version"] == 1


# --- DC12: the menu list --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_menu_list_spans_universities_and_filters_by_kind_and_search(client, db_session):
    _, _, _, first = await _owned(client, db_session)
    tag = uuid.uuid4().hex[:8]
    await add(client, first["id"], kind="brochure", title=f"Brochure {tag}")
    _, _, _, second = await _owned(client, db_session)
    await add(client, second["id"], kind="fee_structure", title=f"Fees {tag}")
    page = (await client.get(MENU, params={"q": tag})).json()
    assert page["total"] == 2 and {d["university"]["id"] for d in page["items"]} == {first["id"], second["id"]}
    assert page["items"][0]["title"] == f"Fees {tag}"  # newest change first
    assert [d["kind"] for d in (await client.get(MENU, params={"q": tag, "kind": "brochure"})).json()["items"]] == ["brochure"]
    assert (await client.get(MENU, params={"q": first["name"]})).json()["items"][0]["university"]["id"] == first["id"]
    assert (await client.get(MENU, params={"kind": "invoice"})).status_code == 422


@pytest.mark.asyncio
async def test_unchanged_patch_is_not_audited(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    doc = await add(client, uni["id"])
    assert (await client.patch(docs_url(uni["id"], f"/{doc['id']}"), json={"title": doc["title"]})).status_code == 200
    rows = await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == doc["id"], AuditLog.action == "university_document.update"))
    assert rows.all() == []
    assert await db_session.get(UniversityDocument, uuid.UUID(doc["id"])) is not None
