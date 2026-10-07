"""bdm-019 test builders, on top of bdm-005/018's and AGN-001's. Unique values per call: the test database is shared and never truncated."""

from app.models import AgentOrg
from tests.agn001_helpers import mk_active_org, uniq
from tests.bdm001_helpers import login, make_user
from tests.bdm005_helpers import started, world
from tests.bdm018_helpers import QUEUE, SIGNED, requested

LINK_AGENT = QUEUE + "/{rid}/link-agent"


async def agent_world(client, db, *, mou: dict | None = SIGNED) -> dict:
    """bdm-005's world for an Agent organization plus an Overseas Admin. A Signed MoU moves it to Agreement Signed (bdm-005 M5) unless
    `mou` is None. The owner is signed in on return."""
    w = await world(client, db, "agent")
    if mou is not None:
        await started(client, w["org"], **mou)
    w["admin"] = await make_user(db, "overseas_admin", "overseas")
    w["ids"]["admin"] = w["admin"].id
    return w


async def agent_queue_item(client, org_id: str, status: str = "pending") -> dict:
    offset = 0
    while True:
        page = (await client.get(QUEUE, params={"kind": "agent", "status": status, "limit": 100, "offset": offset})).json()
        for item in page["items"]:
            if item["organization"]["id"] == org_id:
                return item
        offset += 100
        assert offset < page["total"] + 100, f"no {status} agent request for {org_id}"


async def pending_agent(client, db) -> dict:
    """An Agent organization with a pending request and an active agency to link; the Overseas Admin is signed in on return."""
    w = await agent_world(client, db)
    await requested(client, w["org"])
    await login(client, w["admin"])
    w["item"] = await agent_queue_item(client, w["org"]["id"])
    w["agency"] = await mk_active_org(db, name=f"Agency {uniq()}")
    return w


async def link_agent(client, request_id: str, code: str):
    return await client.post(LINK_AGENT.format(rid=request_id), json={"agent_code": code})


async def agency(db, org_id) -> AgentOrg:
    db.expire_all()
    return await db.get_one(AgentOrg, org_id)
