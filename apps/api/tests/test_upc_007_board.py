"""upc-007 -- the Kanban board (spec PS11, PS12; AC2). The shared test database is never truncated, so every count here is narrowed to one
fresh manager (`manager=<id>` or `me`)."""

import uuid

import pytest

from app.partnership_stages import COLUMNS, column_of
from tests.upc003_helpers import as_role, catalogue_country, create, login, url
from tests.upc007_helpers import PIPELINE, move_ok, owned_university

# A manager's universities: (target stage, lost?) -- Appendix B K folds these into columns.
SPREAD = [
    ("target_university", False), ("researching", False), ("initial_contact", False), ("meeting_completed", False),
    ("commercial_discussion", False), ("documents_shared", False), ("partner_activated", False), ("active_partner", False),
    ("interested", True),
]  # fmt: skip


async def _spread(client, db):
    """One manager owning a university per SPREAD row plus one inactive one; the client ends signed in as the manager."""
    head, pm, first = await owned_university(client, db, name=f"Board Aardvark University {uuid.uuid4().hex[:8]}")  # unique: upc-004 blocks duplicates
    country = (await catalogue_country(db)).id
    await login(client, head)
    unis = [first]
    for i in range(len(SPREAD)):
        uni = await create(client, country, name=f"Board University {i:02d} {pm.id.hex[:6]}")
        assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})).status_code == 200
        unis.append(uni)
    inactive = unis.pop(0)
    assert (await client.post(url(inactive["id"], "deactivate"), json={})).status_code == 200
    await login(client, pm)
    for uni, (stage, lost) in zip(unis, SPREAD, strict=True):
        if stage != "target_university":
            await move_ok(client, uni["id"], "target_university", stage)
        if lost:
            assert (await client.post(url(uni["id"], "lost"), json={"reason": "Closed"})).status_code == 200
    return head, pm, unis


@pytest.mark.asyncio
async def test_column_counts_equal_the_appendix_b_mapping(client, db_session):
    _, pm, _ = await _spread(client, db_session)
    body = (await client.get(f"{PIPELINE}?manager=me")).json()
    expected = dict.fromkeys(COLUMNS, 0)
    for stage, lost in SPREAD:
        if not lost:
            expected[column_of(stage)] += 1
    assert {c["key"]: c["count"] for c in body["columns"]} == expected
    assert [c["label"] for c in body["columns"]][:3] == ["Target", "Contacted", "Interested"]
    assert body["columns"][5]["stages"] == ["commercial_discussion", "documents_shared"]
    assert body["lost_count"] == 1
    assert body["total"] == 8 and len(body["items"]) == 8  # every open (not lost, active) university
    assert all(i["primary_manager"]["id"] == str(pm.id) for i in body["items"])
    assert [i["name"] for i in body["items"]] == sorted(i["name"] for i in body["items"])


@pytest.mark.asyncio
async def test_one_column_and_the_lost_bucket(client, db_session):
    _, pm, _ = await _spread(client, db_session)
    negotiation = (await client.get(f"{PIPELINE}?manager={pm.id}&column=negotiation")).json()
    assert negotiation["total"] == 2 and {i["stage"] for i in negotiation["items"]} == {"commercial_discussion", "documents_shared"}
    assert {i["column"] for i in negotiation["items"]} == {"negotiation"} and negotiation["items"][0]["stage_label"] in ("Commercial Discussion", "Documents Shared")
    lost = (await client.get(f"{PIPELINE}?manager={pm.id}&column=lost")).json()
    assert lost["total"] == 1 and lost["items"][0]["lost"] is True and lost["items"][0]["stage"] == "interested"
    paged = (await client.get(f"{PIPELINE}?manager={pm.id}&limit=3&offset=6")).json()
    assert paged["total"] == 8 and len(paged["items"]) == 2 and paged["offset"] == 6


@pytest.mark.asyncio
async def test_unknown_column_or_manager_filter_is_422(client, db_session):
    await owned_university(client, db_session)
    assert (await client.get(f"{PIPELINE}?column=signed_off")).status_code == 422
    assert (await client.get(f"{PIPELINE}?manager=someone")).status_code == 422


@pytest.mark.asyncio
async def test_unassigned_filter_and_read_roles(client, db_session):
    head, _, _ = await owned_university(client, db_session)
    await login(client, head)
    body = (await client.get(f"{PIPELINE}?manager=none&limit=1")).json()
    assert all(i["primary_manager"] is None for i in body["items"])
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await client.get(PIPELINE)).status_code == 200
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.get(PIPELINE)).status_code == 403
