"""tel-012 -- brochure assets, signed links and the public download (spec §5, §6; AC4, AC5, AC6; DEC-SCOPE-079 C1). Local storage
(AWS_S3_BUCKET is empty in CI)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import ALGORITHM, create_token
from app.models import AuditLog, TelAsset
from app.services import telecaller_content as svc
from app.services.storage import storage
from tests.tel012_helpers import NON_READERS, PDF_BYTES, READERS, WRITERS, as_role, product, uname

ASSETS = "/api/v1/telecaller/assets"
TEMPLATES = "/api/v1/telecaller/templates"
GONE = "This link has expired or is no longer available"


async def _upload(client, data: bytes = PDF_BYTES, filename: str = "brochure.pdf", content_type: str = "application/pdf", **fields):
    form = {"name": uname("Brochure"), "kind": "brochure", **fields}
    return await client.post(ASSETS, data=form, files={"file": (filename, data, content_type)})


def _path(url: str) -> str:
    """The link is absolute (FRONTEND_URL); the test client calls the API path."""
    return "/api/v1/" + url.split("/api/v1/", 1)[1]


async def _link(client, asset_id) -> dict:
    response = await client.post(f"{ASSETS}/{asset_id}/link")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), WRITERS)
async def test_writers_upload_a_pdf(client, db_session, role, division):
    user = await as_role(client, db_session, role, division)
    prod = await product(db_session)
    response = await _upload(client, filename="Cyber “Security”.pdf", content_type="application/octet-stream", product_id=str(prod.id), kind="fee")
    assert response.status_code == 201, response.text
    body = response.json()
    assert {k: body[k] for k in ("kind", "file_name", "size_bytes", "active")} == {"kind": "fee", "file_name": "Cyber “Security”.pdf", "size_bytes": len(PDF_BYTES), "active": True}
    assert body["product"]["id"] == str(prod.id) and "storage_key" not in body
    row = await db_session.get(TelAsset, uuid.UUID(body["id"]))
    assert row.storage_key.startswith("tel-assets/") and row.uploaded_by_user_id == user.id
    assert storage.read_bytes(row.storage_key) == PDF_BYTES
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"]))
    assert (audit.action, audit.metadata_json) == ("telecaller.asset_create", {"fields": ["file", "kind", "name", "product_id"]})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "status", "detail"),
    [
        ({"data": b"\x89PNG\r\n\x1a\nxxxx", "filename": "brochure.pdf"}, 422, "Upload a PDF file"),
        ({"data": b"", "filename": "empty.pdf"}, 422, "The file is empty"),
        ({"kind": "video"}, 422, "Kind: Input should be 'brochure' or 'fee'"),
        ({"name": "  "}, 422, "Name is required"),
        ({"product_id": "00000000-0000-0000-0000-000000000000"}, 422, "Choose an active product"),
    ],
)
async def test_upload_validation(client, db_session, kwargs, status, detail):
    await as_role(client, db_session)
    response = await _upload(client, **kwargs)
    assert response.status_code == status and response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_oversize_upload_is_413(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 64)
    await as_role(client, db_session)
    response = await _upload(client, data=PDF_BYTES + b"x" * 64)
    assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), *NON_READERS])
async def test_other_roles_cannot_upload_or_edit(client, db_session, role, division):
    await as_role(client, db_session)
    created = (await _upload(client)).json()
    await as_role(client, db_session, role, division)
    assert (await _upload(client)).status_code == 403
    assert (await client.patch(f"{ASSETS}/{created['id']}", json={"name": "X"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), NON_READERS)
async def test_non_readers_cannot_list_or_link(client, db_session, role, division):
    await as_role(client, db_session)
    created = (await _upload(client)).json()
    await as_role(client, db_session, role, division)
    assert (await client.get(ASSETS)).status_code == 403
    assert (await client.post(f"{ASSETS}/{created['id']}/link")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), READERS)
async def test_readers_list_and_telecallers_see_active_only(client, db_session, role, division):
    prod = await product(db_session)
    await as_role(client, db_session)
    old = (await _upload(client, product_id=str(prod.id))).json()
    await client.patch(f"{ASSETS}/{old['id']}", json={"active": False})
    new = (await _upload(client, product_id=str(prod.id))).json()
    await as_role(client, db_session, role, division)
    ids = [i["id"] for i in (await client.get(ASSETS, params={"product_id": str(prod.id)})).json()["items"]]
    assert ids == ([new["id"]] if role == "telecaller" else [new["id"], old["id"]])  # newest first


@pytest.mark.asyncio
async def test_a_deactivated_brochure_keeps_its_place(client, db_session):
    """QA-04: the order is newest first whatever the status, so deactivating never moves the row (or its Reactivate button) away."""
    prod = await product(db_session)
    await as_role(client, db_session)
    older = (await _upload(client, product_id=str(prod.id))).json()
    newer = (await _upload(client, product_id=str(prod.id))).json()
    await client.patch(f"{ASSETS}/{newer['id']}", json={"active": False})
    ids = [i["id"] for i in (await client.get(ASSETS, params={"product_id": str(prod.id)})).json()["items"]]
    assert ids == [newer["id"], older["id"]]


@pytest.mark.asyncio
async def test_signed_link_opens_signed_out_until_deactivated(client, db_session):
    """AC4: the public link streams the PDF with no session; deactivating ends it, reactivating restores it until expiry."""
    await as_role(client, db_session)
    asset = (await _upload(client, filename="Fee plan ₹ 'v2'.pdf")).json()
    await as_role(client, db_session, "telecaller", "it")
    link = await _link(client, asset["id"])
    assert link["url"].startswith(f"{settings.frontend_url.rstrip('/')}/api/v1/public/telecaller-assets/")
    expires = datetime.fromisoformat(link["expires_at"])
    assert timedelta(days=6, hours=23) < expires - datetime.now(UTC) <= timedelta(days=7)
    client.cookies.clear()
    response = await client.get(_path(link["url"]))
    assert response.status_code == 200 and response.content == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store" and response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == "inline; filename=\"Fee plan _ 'v2'.pdf\"; filename*=UTF-8''Fee%20plan%20%E2%82%B9%20%27v2%27.pdf"
    await as_role(client, db_session)
    assert (await client.patch(f"{ASSETS}/{asset['id']}", json={"active": False})).status_code == 200
    gone = await client.get(_path(link["url"]))
    assert gone.status_code == 404 and gone.json()["detail"] == GONE
    assert (await client.post(f"{ASSETS}/{asset['id']}/link")).status_code == 404
    await client.patch(f"{ASSETS}/{asset['id']}", json={"active": True})
    assert (await client.get(_path(link["url"]))).status_code == 200


def test_download_headers_survive_quotes_and_newlines():
    """Review focus 3: a stored name can never break or inject into the header."""
    disposition = svc.download_headers('a"b\\c\r\nSet-Cookie: x.pdf')["Content-Disposition"]
    assert disposition == "inline; filename=\"a_b_c__Set-Cookie: x.pdf\"; filename*=UTF-8''a%22b%5Cc%0D%0ASet-Cookie%3A%20x.pdf"


@pytest.mark.asyncio
async def test_expired_tampered_and_foreign_tokens_fail(client, db_session):
    manager = await as_role(client, db_session)
    asset = (await _upload(client)).json()
    base = "/api/v1/public/telecaller-assets/"
    expired = jwt.encode({"sub": asset["id"], "type": "tel_asset", "exp": datetime.now(UTC) - timedelta(seconds=1)}, settings.secret_key, algorithm=ALGORITHM)
    good = _path((await _link(client, asset["id"]))["url"]).removeprefix(base)
    tampered = good[:-2] + ("AA" if good[-2:] != "AA" else "BB")
    session = create_token(str(manager.id), manager.role, manager.division)
    other_type = jwt.encode({"sub": asset["id"], "type": "access", "exp": datetime.now(UTC) + timedelta(days=1)}, settings.secret_key, algorithm=ALGORITHM)
    unknown = jwt.encode({"sub": str(uuid.uuid4()), "type": "tel_asset", "exp": datetime.now(UTC) + timedelta(days=1)}, settings.secret_key, algorithm=ALGORITHM)
    client.cookies.clear()
    for token in (expired, tampered, session, other_type, unknown, "not-a-token"):
        response = await client.get(base + token)
        assert response.status_code == 404 and response.json()["detail"] == GONE
    assert (await client.get(base + good)).status_code == 200


@pytest.mark.asyncio
async def test_a_link_token_is_never_a_session(client, db_session):
    await as_role(client, db_session)
    asset = (await _upload(client)).json()
    token = _path((await _link(client, asset["id"]))["url"]).rsplit("/", 1)[1]
    client.cookies.clear()
    client.cookies.set("edusphere_access", token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_update_metadata_and_audit(client, db_session):
    prod = await product(db_session)
    await as_role(client, db_session)
    asset = (await _upload(client)).json()
    response = await client.patch(f"{ASSETS}/{asset['id']}", json={"name": "Fees 2026", "kind": "fee", "product_id": str(prod.id)})
    assert response.status_code == 200 and response.json()["name"] == "Fees 2026" and response.json()["product"]["id"] == str(prod.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == asset["id"], AuditLog.action == "telecaller.asset_update"))
    assert audit.metadata_json == {"fields": ["kind", "name", "product_id"]}
    cleared = await client.patch(f"{ASSETS}/{asset['id']}", json={"product_id": None})
    assert cleared.json()["product"] is None
    assert (await client.patch(f"{ASSETS}/{asset['id']}", json={"storage_key": "x"})).json()["detail"] == "Unknown field: storage_key"
    assert (await client.patch(f"{ASSETS}/{uuid.uuid4()}", json={"name": "X"})).status_code == 404


@pytest.mark.asyncio
async def test_template_with_brochure_previews_a_working_link(client, db_session):
    """Positive scenario: the manager links the uploaded brochure to "Course details" and uses {brochure_link}."""
    await as_role(client, db_session)
    asset = (await _upload(client)).json()
    created = await client.post(TEMPLATES, json={"channel": "whatsapp", "kind": "course_details", "name": uname("Course"), "asset_id": asset["id"], "body": "Hi {name}: {brochure_link}"})
    assert created.status_code == 201 and created.json()["asset"] == {"id": asset["id"], "name": asset["name"], "active": True}
    template = created.json()
    preview = (await client.get(f"{TEMPLATES}/{template['id']}/preview")).json()
    assert preview["body"] == f"Hi Priya Sharma: {preview['brochure_link']['url']}"
    client.cookies.clear()
    assert (await client.get(_path(preview["brochure_link"]["url"]))).status_code == 200
    await as_role(client, db_session)
    removing = await client.patch(f"{TEMPLATES}/{template['id']}", json={"asset_id": None})
    assert removing.json()["detail"] == "Attach a brochure to use {brochure_link}"
    await client.patch(f"{ASSETS}/{asset['id']}", json={"active": False})
    stale = (await client.get(f"{TEMPLATES}/{template['id']}/preview")).json()
    assert stale == {"subject": None, "body": "Hi Priya Sharma: ", "brochure_link": None}
    other = await client.post(TEMPLATES, json={"channel": "whatsapp", "kind": "brochure", "name": uname("B"), "asset_id": asset["id"], "body": "x"})
    assert other.json()["detail"] == "Choose an active brochure"
    renamed = await client.patch(f"{TEMPLATES}/{template['id']}", json={"name": uname("Kept")})
    assert renamed.status_code == 200  # keeping a since-deactivated brochure is allowed


@pytest.mark.asyncio
async def test_object_is_discarded_when_the_row_fails(client, db_session, monkeypatch):
    """The object is written before the row; when the write after it fails, the object is deleted (no orphan)."""
    from app.api import telecaller_content as routes

    await as_role(client, db_session)
    stored: list[str] = []
    real_store = svc.store
    monkeypatch.setattr(svc, "store", lambda data: stored.append(real_store(data)) or stored[-1])

    def broken_audit(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(routes, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        await _upload(client)
    assert len(stored) == 1
    with pytest.raises(FileNotFoundError):
        storage.read_bytes(stored[0])
