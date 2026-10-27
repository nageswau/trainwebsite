"""nehn-032 -- certificate signatures (DEC-SCOPE-300; spec docs/superpowers/specs/2026-10-27-nehn-032-certificate-signatures-design.md,
RBAC_MATRIX §2.211): both slots drawn on new certificates (AC1), a replaced signature affects only later certificates (AC2), signature files
are not downloadable by students (AC3), issuing without both slots is refused (AC4), and the upload check (S4)."""

import datetime
import io
import re
import uuid

import pytest
from PIL import Image
from reportlab import rl_config
from sqlalchemy import select, update

from app.core import rbac
from app.models import AuditLog, Certificate, CertificateSignatory
from app.services import certificates
from tests.test_nehn_031_certificate_workflow import BASE as ISSUE_BASE
from tests.test_nehn_031_certificate_workflow import _enrollment
from tests.upc001_helpers import as_role

SIGNATORIES = "/api/v1/admin/certificate-signatories"
PREVIEW = "/api/v1/admin/certificates/preview"


def png(width: int = 400, height: int = 120, mode: str = "RGBA") -> bytes:
    image = Image.new(mode, (width, height), (0, 0, 0, 0) if mode == "RGBA" else (255, 255, 255))
    for x in range(10, width - 10):  # a stroke, so the image is not blank
        image.putpixel((x, height // 2), (14, 27, 43, 255) if mode == "RGBA" else (14, 27, 43))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 120), (255, 255, 255)).save(out, format="JPEG")
    return out.getvalue()


async def upload(client, role: str, *, name: str | None = None, designation: str = "Founder & Director", data: bytes | None = None, content_type: str = "image/png"):
    form = {"role": role, "display_name": name or f"Signer {uuid.uuid4().hex[:6]}", "designation": designation}
    return await client.post(SIGNATORIES, data=form, files={"file": ("sig.png", data if data is not None else png(), content_type)})


async def ensure_both(client) -> dict[str, dict]:
    """A fresh active version in both slots, uploaded by the logged-in grant holder."""
    return {role: (await upload(client, role, designation=f"{role.title()} title")).json() for role in certificates.SIGNATORY_ROLES}


# --- the grant ---------------------------------------------------------------------------------------------------------------------


def test_manage_is_a_certificates_action_held_by_nobody_by_default():
    assert rbac.parse_key("certificates.manage") == ("certificates", "manage")
    assert not any("certificates.manage" in keys for keys in rbac.DEFAULT_GRANTS.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("it_admin", "it"), ("coordinator", "it"), ("it_student", "it"), ("trainer", "it")])
async def test_other_roles_cannot_manage_or_see_signatures(client, db_session, role, division):
    await as_role(client, db_session, "super_admin", "global")
    founder = (await upload(client, "founder")).json()
    await as_role(client, db_session, role, division)
    assert (await client.get(SIGNATORIES)).status_code == 403
    assert (await upload(client, "founder")).status_code == 403
    assert (await client.patch(f"{SIGNATORIES}/{founder['id']}", json={"designation": "x"})).status_code == 403
    assert (await client.get(f"{SIGNATORIES}/{founder['id']}/image")).status_code == 403  # AC3
    assert (await client.get(PREVIEW)).status_code == 403


# --- upload, versions, edit ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_replaces_the_active_version(client, db_session):
    actor = await as_role(client, db_session, "super_admin", "global")
    first = await upload(client, "founder", name="Asha Founder")
    assert first.status_code == 201, first.text
    second = await upload(client, "founder", name="Asha Founder", designation="Chairperson")
    assert second.status_code == 201
    body = second.json()
    assert body["active"] is True and body["designation"] == "Chairperson" and "image_key" not in body
    rows = {str(r.id): r for r in (await db_session.scalars(select(CertificateSignatory).where(CertificateSignatory.id.in_([first.json()["id"], body["id"]])))).all()}
    assert rows[first.json()["id"]].active_to is not None and rows[body["id"]].active_to is None
    assert re.fullmatch(r"signatures/[0-9a-f]{32}\.png", rows[body["id"]].image_key)
    listed = (await client.get(SIGNATORIES)).json()["items"]
    assert [i["id"] for i in listed if i["role"] == "founder" and i["active"]] == [body["id"]]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "certificate_signatory.upload"))
    assert audit and audit.user_id == actor.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,content_type,status",
    [
        (jpeg(), "image/jpeg", 415),  # not PNG
        (jpeg(), "image/png", 415),  # a JPEG claiming to be PNG (magic bytes)
        (png(mode="RGB"), "image/png", 422),  # no transparent background
        (png(30, 10), "image/png", 422),  # too small
        (png(2400, 200), "image/png", 422),  # too wide
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png", 422),  # PNG signature, not an image
    ],
)
async def test_upload_check_refuses_bad_files(client, db_session, data, content_type, status):
    await as_role(client, db_session, "super_admin", "global")
    response = await upload(client, "coordinator", data=data, content_type=content_type)
    assert response.status_code == status, response.text


@pytest.mark.asyncio
async def test_upload_validates_fields(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await upload(client, "trainer")).status_code == 422
    assert (await upload(client, "founder", name="   ")).status_code == 422
    assert (await upload(client, "founder", designation="x" * 121)).status_code == 422


@pytest.mark.asyncio
async def test_patch_edits_the_active_version_only(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    old = (await upload(client, "coordinator")).json()
    new = (await upload(client, "coordinator")).json()
    edited = await client.patch(f"{SIGNATORIES}/{new['id']}", json={"display_name": "Nisha R.", "designation": "IT Coordinator"})
    assert edited.status_code == 200 and edited.json()["display_name"] == "Nisha R."
    assert (await client.patch(f"{SIGNATORIES}/{old['id']}", json={"designation": "x"})).status_code == 409
    assert (await client.patch(f"{SIGNATORIES}/{uuid.uuid4()}", json={"designation": "x"})).status_code == 404
    assert (await client.patch(f"{SIGNATORIES}/{new['id']}", json={"image_key": "signatures/x.png"})).status_code == 422


@pytest.mark.asyncio
async def test_image_route_streams_the_png_privately(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    item = (await upload(client, "founder")).json()
    response = await client.get(f"{SIGNATORIES}/{item['id']}/image")
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert response.headers["content-type"] == "image/png" and "no-store" in response.headers["cache-control"]


# --- preview and rendering ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_renders_a_pdf(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    await ensure_both(client)
    response = await client.get(PREVIEW)
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-") and "no-store" in response.headers["cache-control"]


def _signatory(role: str, name: str, designation: str, data: bytes) -> CertificateSignatory:
    key = f"signatures/{uuid.uuid4().hex}.png"
    certificates.storage.write_bytes(key, data, "image/png")
    return CertificateSignatory(id=uuid.uuid4(), role=role, display_name=name, designation=designation, image_key=key)


def test_render_draws_both_slots_with_long_names(monkeypatch):
    monkeypatch.setattr(rl_config, "pageCompression", 0)  # readable text in the page stream
    signers = [_signatory("founder", "Asha Founder", "Founder & Director", png()), _signatory("coordinator", "Nisha Coordinator", "IT Coordinator", png(2000, 20))]
    pdf = certificates.render_certificate_pdf(
        certificate_no="CERT-N032",
        student_name="Maximiliana Alexandrina Bartholomew-Featherstonehaugh " * 2,
        program_title="Advanced " * 12,
        issued_on=datetime.date(2026, 10, 27),
        verification_code="V032",
        signatories=signers,
    )
    assert pdf.startswith(b"%PDF-")
    assert pdf.count(b"/SMask") == 2  # two signatures, each keeping its transparency as a soft mask
    assert pdf.count(b"/Subtype /Image") == 4  # each image plus its alpha mask
    for text in (b"Asha Founder", b"Founder & Director", b"Nisha Coordinator", b"IT Coordinator"):
        assert text in pdf


def test_missing_signatories_names_the_empty_slots():
    assert certificates.missing_signatories([]) == ["founder", "coordinator"]
    assert certificates.missing_signatories([CertificateSignatory(role="coordinator")]) == ["founder"]


# --- issue: AC1, AC2, AC4 ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_snapshots_the_active_signatories_and_a_replacement_affects_only_later_certificates(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    versions = await ensure_both(client)
    first, second = await _enrollment(db_session), await _enrollment(db_session)
    await as_role(client, db_session, "coordinator", "it")
    issued = await client.post(f"{ISSUE_BASE}/{first.id}/issue", json={})
    assert issued.status_code == 201, issued.text
    cert = await db_session.scalar(select(Certificate).where(Certificate.enrollment_id == first.id))
    assert [(s["role"], s["id"]) for s in cert.signatory_snapshot] == [("founder", versions["founder"]["id"]), ("coordinator", versions["coordinator"]["id"])]
    assert cert.signatory_snapshot[0]["designation"] == "Founder title"

    await as_role(client, db_session, "super_admin", "global")
    new_founder = (await upload(client, "founder", designation="Chairperson")).json()
    await as_role(client, db_session, "coordinator", "it")
    assert (await client.post(f"{ISSUE_BASE}/{second.id}/issue", json={})).status_code == 201
    later = await db_session.scalar(select(Certificate).where(Certificate.enrollment_id == second.id))
    assert later.signatory_snapshot[0]["id"] == new_founder["id"]
    await db_session.refresh(cert)
    assert cert.signatory_snapshot[0]["id"] == versions["founder"]["id"]  # AC2: the earlier certificate is unchanged


@pytest.mark.asyncio
async def test_issue_is_refused_while_a_slot_is_empty(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    await ensure_both(client)
    enrollment = await _enrollment(db_session)
    closed = (
        (
            await db_session.execute(
                update(CertificateSignatory)
                .where(CertificateSignatory.role == "coordinator", CertificateSignatory.active_to.is_(None))
                .values(active_to=datetime.datetime.now(datetime.UTC))
                .returning(CertificateSignatory.id)
            )
        )
        .scalars()
        .all()
    )
    await db_session.commit()
    try:
        await as_role(client, db_session, "coordinator", "it")
        single = await client.post(f"{ISSUE_BASE}/{enrollment.id}/issue", json={})
        assert single.status_code == 409 and "coordinator" in single.json()["detail"]
        bulk = (await client.post(f"{ISSUE_BASE}/issue", json={"enrollment_ids": [str(enrollment.id)]})).json()
        assert bulk["issued"] == [] and bulk["failed"][0]["status_code"] == 409
        assert await db_session.scalar(select(Certificate).where(Certificate.enrollment_id == enrollment.id)) is None
        await as_role(client, db_session, "super_admin", "global")
        assert (await client.get(PREVIEW)).status_code == 409
    finally:
        await as_role(client, db_session, "super_admin", "global")
        assert (await upload(client, "coordinator")).status_code == 201  # leave the shared database issuable
        assert closed
