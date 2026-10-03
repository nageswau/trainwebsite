"""AGN-022 -- Overseas Admin agent network oversight (DEC-SCOPE-063; spec §8)."""

import pytest

from tests.agn001_helpers import login, mk_user
from tests.agn022_helpers import NETWORK, ORGS, ZERO, network_world


async def _admin(client, db, role="overseas_admin"):
    admin = await mk_user(db, role=role)
    await login(client, admin.email)
    return admin


def _item(body, org_id):
    return next(i for i in body["items"] if i["id"] == str(org_id))


@pytest.mark.asyncio
async def test_the_list_adds_counts_that_match_the_fixture(client, db_session):  # AC1, AC8
    w = await network_world(db_session)
    await _admin(client, db_session)
    body = (await client.get(ORGS, params={"q": w["org"].prefix, "limit": 100})).json()
    item = _item(body, w["org"].id)
    assert item["staff_count"] == NETWORK["staff_count"]
    assert item["counts"] == {k: NETWORK[k] for k in ("students", "applications", "enrollments")}
    assert set(item) == {"id", "name", "prefix", "status", "created_at", "masters", "staff_count", "counts"}  # existing keys kept


@pytest.mark.asyncio
async def test_other_agencies_and_empty_orgs_count_on_their_own(client, db_session):  # AC1, AC3
    w = await network_world(db_session)
    await _admin(client, db_session)
    empty = _item((await client.get(ORGS, params={"q": w["empty"]["org"].prefix})).json(), w["empty"]["org"].id)
    assert {"staff_count": empty["staff_count"], **empty["counts"]} == ZERO
    noise = _item((await client.get(ORGS, params={"q": w["other"]["org"].prefix})).json(), w["other"]["org"].id)
    assert noise["counts"] == {"students": 1, "applications": 1, "enrollments": 1}  # the noise agency's own rows only
