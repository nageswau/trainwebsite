"""bdm-005 -- the MoU document download is scope-checked, audited and streamed (M3; AC4; Review Focus 5)."""

import uuid

import pytest

from app.models import BdmMou
from app.services.storage import storage
from tests.bdm001_helpers import login
from tests.bdm005_helpers import MOUS, PDF_BYTES, audits, mou_url, started, world


def doc_url(mou_id: str) -> str:
    return f"{MOUS}/{mou_id}/document"


async def _with_document(client, db, name: str = "signed.pdf") -> tuple[dict, dict]:
    w = await world(client, db)
    mou = await started(client, w["org"])
    response = await client.put(mou_url(w["org"]["id"], "/document"), files={"file": (name, PDF_BYTES, "application/pdf")})
    assert response.status_code == 200, response.text
    return w, mou


# actor -> download status
EXPECTED = {
    "owner": 200,
    "peer": 200,
    "manager": 200,
    "super_admin": 200,
    "other_type": 404,
    "other_manager": 404,
    "it_admin": 403,
    "student": 403,
    "no_profile": 403,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", list(EXPECTED))
async def test_download_scope_matrix(client, db_session, actor):
    w, mou = await _with_document(client, db_session)
    await login(client, w[actor])
    response = await client.get(doc_url(mou["id"]))
    assert response.status_code == EXPECTED[actor]
    if response.status_code == 200:
        assert response.content == PDF_BYTES and response.headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_headers_force_a_download_and_never_echo_the_file_name(client, db_session):
    """Review Focus 5: the stored name (with a quote and CR LF) never reaches the header; the name is built from the org code."""
    w, mou = await _with_document(client, db_session, name='a"\r\nX-Evil: 1.pdf')
    response = await client.get(doc_url(mou["id"]))
    assert response.headers["content-disposition"] == f'attachment; filename="mou-{w["org"]["code"]}.pdf"'
    assert response.headers["x-content-type-options"] == "nosniff" and "no-store" in response.headers["cache-control"]
    assert "x-evil" not in response.headers


@pytest.mark.asyncio
async def test_every_download_is_audited(client, db_session):
    w, mou = await _with_document(client, db_session)
    await login(client, w["manager"])
    await client.get(doc_url(mou["id"]))
    [audit] = await audits(db_session, mou["id"], "document_downloaded")
    assert audit.user_id == w["ids"]["manager"] and audit.metadata_json == {"org_id": w["org"]["id"], "role": "bdm_manager"}


@pytest.mark.asyncio
async def test_unknown_and_out_of_scope_look_the_same(client, db_session):
    w, mou = await _with_document(client, db_session)
    await login(client, w["other_type"])
    assert (await client.get(doc_url(mou["id"]))).json() == (await client.get(doc_url(str(uuid.uuid4())))).json() == {"detail": "MoU not found"}


@pytest.mark.asyncio
async def test_no_document_and_a_missing_object_are_404(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    assert (await client.get(doc_url(mou["id"]))).json() == {"detail": "No document on file"}
    w, mou = await _with_document(client, db_session)
    db_session.expire_all()
    storage.delete((await db_session.get(BdmMou, mou["id"])).document_key)
    response = await client.get(doc_url(mou["id"]))
    assert response.status_code == 404 and response.json() == {"detail": "No document on file"}


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    _, mou = await _with_document(client, db_session)
    await client.post("/api/v1/auth/logout")
    assert (await client.get(doc_url(mou["id"]))).status_code == 401
