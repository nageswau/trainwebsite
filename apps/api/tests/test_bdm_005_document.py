"""bdm-005 -- the MoU document upload (M4, M8; AC9; Review Focus 3)."""

from datetime import UTC, datetime

import pytest

from app.api import bdm_mous as router_module
from app.core.config import settings
from app.models import AuditLog, BdmMou
from app.services.storage import storage
from tests.bdm001_helpers import login
from tests.bdm005_helpers import PDF_BYTES, audits, events, mou_url, started, world
from tests.enh025_helpers import png_bytes

PNG = png_bytes()  # structurally valid, with a tEXt chunk the upload must strip


async def upload(client, org: dict, data: bytes = PDF_BYTES, name: str = "signed.pdf", content_type: str = "application/pdf"):
    return await client.put(mou_url(org["id"], "/document"), files={"file": (name, data, content_type)})


async def _row(db, mou_id: str) -> BdmMou:
    db.expire_all()
    return await db.get(BdmMou, mou_id)


@pytest.mark.asyncio
async def test_a_pdf_is_stored_under_a_server_key_that_is_never_returned(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    response = await upload(client, w["org"])
    assert response.status_code == 200, response.text
    body = response.json()["mou"]
    assert body["has_document"] is True
    assert body["document"]["name"] == "signed.pdf" and body["document"]["content_type"] == "application/pdf" and body["document"]["uploaded_at"]
    row = await _row(db_session, mou["id"])
    assert row.document_key.startswith("bdm-mous/") and row.document_key not in response.text
    assert storage.read_bytes(row.document_key) == PDF_BYTES
    last = (await events(db_session, mou["id"]))[-1]
    assert (last.kind, last.from_status, last.to_status, last.changed, last.document_key) == ("document", "prospect", "prospect", ["document"], None)
    [audit] = await audits(db_session, mou["id"], "document_uploaded")
    assert audit.metadata_json == {"org_id": w["org"]["id"], "content_type": "application/pdf", "replaced": False, "bytes": len(PDF_BYTES)}


@pytest.mark.asyncio
async def test_the_type_is_decided_by_the_bytes_and_image_metadata_is_stripped(client, db_session):
    """Review Focus 3: PNG bytes named contract.pdf are stored and served as a PNG."""
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    response = await upload(client, w["org"], PNG, "contract.pdf", "application/pdf")
    assert response.status_code == 200 and response.json()["mou"]["document"]["content_type"] == "image/png"
    stored = storage.read_bytes((await _row(db_session, mou["id"])).document_key)
    assert b"tEXt" in PNG and b"tEXt" not in stored


@pytest.mark.asyncio
async def test_wrong_type_and_too_large_are_refused(client, db_session, monkeypatch):
    w = await world(client, db_session)
    await started(client, w["org"])
    assert (await upload(client, w["org"], b"just text", "notes.pdf")).status_code == 415
    assert (await upload(client, w["org"], b"", "empty.pdf")).status_code == 422
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    assert (await upload(client, w["org"])).status_code == 413


@pytest.mark.asyncio
async def test_a_replace_keeps_the_old_object_out_of_reach(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    await upload(client, w["org"])
    old_key = (await _row(db_session, mou["id"])).document_key
    response = await upload(client, w["org"], PNG, "scan.png", "image/png")
    assert response.status_code == 200 and old_key not in response.text
    row = await _row(db_session, mou["id"])
    assert row.document_key != old_key and storage.read_bytes(old_key) == PDF_BYTES
    assert (await events(db_session, mou["id"]))[-1].document_key == old_key
    assert (await audits(db_session, mou["id"], "document_uploaded"))[-1].metadata_json["replaced"] is True


@pytest.mark.asyncio
async def test_a_failed_write_after_storing_deletes_the_new_object(client, db_session, monkeypatch):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    stored: list[str] = []
    real_write = storage.write_bytes
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: (stored.append(key), real_write(key, data, ct)))

    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(router_module.svc, "audit", boom)
    with pytest.raises(RuntimeError):
        await upload(client, w["org"])
    assert (await _row(db_session, mou["id"])).document_key is None
    assert len(stored) == 1
    with pytest.raises(FileNotFoundError):
        storage.read_bytes(stored[0])


@pytest.mark.asyncio
async def test_the_21st_upload_in_an_hour_is_429(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    now = datetime.now(UTC)
    for _ in range(20):
        db_session.add(AuditLog(user_id=w["ids"]["owner"], action="bdm_mou.document_uploaded", entity_type="bdm_mou", entity_id=mou["id"], metadata_json={}, created_at=now))
    await db_session.commit()
    response = await upload(client, w["org"])
    assert response.status_code == 429 and 0 < int(response.headers["Retry-After"]) <= 3600


@pytest.mark.asyncio
async def test_only_writers_upload_and_only_to_a_current_mou(client, db_session):
    w = await world(client, db_session)
    assert (await upload(client, w["org"])).status_code == 404  # no MoU yet
    await started(client, w["org"])
    for actor in ("peer", "manager"):
        await login(client, w[actor])
        assert (await upload(client, w["org"], b"not even a pdf")).status_code == 403  # the role is checked before the bytes
    await login(client, w["other_type"])
    assert (await upload(client, w["org"])).status_code == 404
