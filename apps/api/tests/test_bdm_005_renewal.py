"""bdm-005 -- renewal: a new current MoU only after Expired or Rejected; the old row is kept (M6; AC7)."""

from datetime import date

import pytest

from app.services import bdm_mous as svc
from tests.bdm005_helpers import audits, change, events, mou_rows, mou_url, start, started, world

EXPIRED = {"status": "active", "signed_on": "2025-10-01", "valid_from": "2025-10-01", "valid_until": "2026-09-30"}


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(svc, "today", lambda: date(2026, 10, 6))


@pytest.mark.asyncio
async def test_renewing_an_expired_mou_keeps_the_old_row(client, db_session, frozen):
    w = await world(client, db_session)
    old = await started(client, w["org"], reference="MOU-1", **EXPIRED)
    new = await started(client, w["org"], reference="MOU-2")
    assert (new["status"], new["is_current"], new["reference"]) == ("prospect", True, "MOU-2") and new["id"] != old["id"]
    rows = await mou_rows(db_session, w["org"]["id"])
    assert [(str(r.id), r.is_current) for r in rows] == [(old["id"], False), (new["id"], True)]
    last = (await events(db_session, old["id"]))[-1]
    assert (last.kind, last.from_status, last.to_status) == ("renewed", "expired", "expired")
    [audit] = await audits(db_session, old["id"], "renewed")
    assert audit.metadata_json == {"org_id": w["org"]["id"], "renewed_by": new["id"]}
    body = (await client.get(mou_url(w["org"]["id"]))).json()
    assert body["current"]["id"] == new["id"] and body["can_start"] is False


@pytest.mark.asyncio
async def test_renewing_a_rejected_mou(client, db_session):
    w = await world(client, db_session)
    old = await started(client, w["org"], status="rejected")
    assert (await client.get(mou_url(w["org"]["id"]))).json()["can_start"] is True
    new = await started(client, w["org"])
    assert new["id"] != old["id"]
    assert [e.kind for e in await events(db_session, old["id"])] == ["created", "renewed"]


@pytest.mark.asyncio
async def test_an_active_mou_cannot_be_replaced(client, db_session, frozen):
    w = await world(client, db_session)
    await started(client, w["org"], **{**EXPIRED, "valid_until": "2027-09-30"})
    response = await start(client, w["org"])
    assert response.status_code == 409 and response.json()["detail"]["code"] == "mou_exists"


@pytest.mark.asyncio
async def test_a_previous_mou_is_never_edited(client, db_session):
    w = await world(client, db_session)
    old = await started(client, w["org"], status="rejected")
    await started(client, w["org"])
    await change(client, w["org"], notes="on the new one")
    [old_row] = [r for r in await mou_rows(db_session, w["org"]["id"]) if str(r.id) == old["id"]]
    assert old_row.notes is None and old_row.is_current is False
