"""dtu-001 (DEC-SCOPE-209 §5): the agent commission reaches only super_admin, overseas_admin and an agent Master; one edit route."""

import pytest
from sqlalchemy.orm import selectinload

from app.models import AgentOrgMember, User
from app.services.agent_commission_access import can_edit_agent_commission, can_view_agent_commission, with_agent_commission
from tests.agn001_helpers import mk_active_org
from tests.agn004_helpers import mk_staff
from tests.upc001_helpers import as_role
from tests.upc003_helpers import BASE, catalogue_country, create

RATE = {"percent": "16.00", "note": "0.16"}


async def _uni_with_rate(client, db_session):
    """Signs in as super_admin and leaves that session on the client; returns the university."""
    await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    r = await client.put(f"{BASE}/{uni['id']}/agent-commission", json=RATE)
    assert r.status_code == 200, r.text
    return uni


@pytest.mark.asyncio
async def test_admins_see_the_rate_on_the_master_detail(client, db_session):
    uni = await _uni_with_rate(client, db_session)
    body = (await client.get(f"{BASE}/{uni['id']}")).json()["university"]
    assert body["agent_commission"] == {"percent": "16.00", "amount": None, "currency": None, "note": "0.16"}
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await client.get(f"{BASE}/{uni['id']}")).json()["university"]["agent_commission"]["percent"] == "16.00"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partnership_manager", "partnership_head"])
async def test_partnership_roles_do_not_get_the_key(client, db_session, role):
    uni = await _uni_with_rate(client, db_session)
    await as_role(client, db_session, role, "overseas" if role == "partnership_manager" else "global")
    r = await client.get(f"{BASE}/{uni['id']}")
    if r.status_code == 200:  # a manager outside the team gets 403/404 -- either way no key
        assert "agent_commission" not in r.json()["university"]
    assert "agent_commission" not in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "status"), [
    ("partnership_manager", "overseas", 403), ("partnership_head", "global", 403), ("it_admin", "it", 403), ("counselor", "overseas", 403),
])
async def test_only_admins_edit(client, db_session, role, division, status):
    uni = await _uni_with_rate(client, db_session)
    await as_role(client, db_session, role, division)
    r = await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"percent": "20"})
    assert r.status_code == status


@pytest.mark.asyncio
async def test_anonymous_put_is_401(client, db_session):
    uni = await _uni_with_rate(client, db_session)
    client.cookies.clear()
    assert (await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"percent": "20"})).status_code == 401


@pytest.mark.asyncio
async def test_put_validates_one_rate_and_clears_with_null(client, db_session):
    uni = await _uni_with_rate(client, db_session)
    url = f"{BASE}/{uni['id']}/agent-commission"
    assert (await client.put(url, json={"percent": "10", "amount": "100", "currency": "GBP"})).status_code == 422
    assert (await client.put(url, json={"amount": "100"})).status_code == 422  # amount needs a currency
    assert (await client.put(url, json={"percent": "0"})).status_code == 422
    assert (await client.put(url, json={"percent": "100.01"})).status_code == 422
    r = await client.put(url, json={"amount": "4000", "currency": "GBP", "note": "4000GBP flat"})
    assert r.json()["university"]["agent_commission"] == {"percent": None, "amount": "4000.00", "currency": "GBP", "note": "4000GBP flat"}
    r = await client.put(url, json=None)
    assert r.status_code == 200 and r.json()["university"]["agent_commission"] is None


async def _agent(db, user_id) -> User:
    return await db.get(User, user_id, options=[selectinload(User.agent_membership).selectinload(AgentOrgMember.org)], populate_existing=True)


@pytest.mark.asyncio
async def test_an_agent_master_views_but_staff_and_others_do_not(db_session):
    world = await mk_active_org(db_session)
    master = await _agent(db_session, world["master"].id)
    staff = await mk_staff(db_session, world["org"])
    staff_user = await _agent(db_session, staff["user"].id)
    assert can_view_agent_commission(master) and not can_edit_agent_commission(master)
    assert not can_view_agent_commission(staff_user)
    assert with_agent_commission(master, _Uni(), {"id": 1})["agent_commission"]["percent"] == "5.00"
    assert "agent_commission" not in with_agent_commission(staff_user, _Uni(), {"id": 1})


class _Uni:
    agent_commission_percent = 5
    agent_commission_amount = None
    agent_commission_currency = None
    agent_commission_note = None
