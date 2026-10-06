"""bdm-018 test builders, on top of bdm-002/005's. Unique values per call: the test database is shared and never truncated."""

import uuid
from uuid import UUID

from sqlalchemy import select

from app.models import AuditLog, BdmOnboardingRequest, Notification, User
from tests.bdm001_helpers import login, make_user
from tests.bdm002_helpers import ORGS
from tests.bdm005_helpers import started, world

QUEUE = "/api/v1/overseas-admin/bdm-onboarding-requests"
SCHOOLS = "/api/v1/overseas-admin/schools"
SIGNED = {"status": "signed", "signed_on": "2026-01-10"}


def request_url(org_id: str) -> str:
    return f"{ORGS}/{org_id}/onboarding-request"


async def request(client, org: dict, **body):
    return await client.post(request_url(org["id"]), json=body)


async def requested(client, org: dict, **body) -> dict:
    response = await request(client, org, **body)
    assert response.status_code == 201, response.text
    return response.json()["organization"]


async def school_world(client, db, *, mou: dict | None = SIGNED) -> dict:
    """bdm-005's world for a School organization, plus an Overseas Admin; with a Signed MoU unless `mou` is None. The owner is signed in."""
    w = await world(client, db, "school")
    if mou is not None:
        await started(client, w["org"], **mou)
    w["admin"] = await make_user(db, "overseas_admin", "overseas")
    w["ids"]["admin"] = w["admin"].id
    return w


async def pending_request(client, db) -> dict:
    """A world whose organization has a pending request; the Overseas Admin is signed in on return, with the request's queue item."""
    w = await school_world(client, db)
    await requested(client, w["org"])
    await login(client, w["admin"])
    w["item"] = await queue_item(client, w["org"]["id"])
    return w


async def queue_item(client, org_id: str, status: str = "pending") -> dict:
    offset = 0
    while True:
        page = (await client.get(QUEUE, params={"status": status, "limit": 100, "offset": offset})).json()
        for item in page["items"]:
            if item["organization"]["id"] == org_id:
                return item
        offset += 100
        assert offset < page["total"] + 100, f"no {status} request for {org_id}"


def school_payload(**overrides) -> dict:
    tag = uuid.uuid4().hex[:8]
    payload = {"name": f"School {tag}", "coordinator_full_name": "Coordinator", "coordinator_email": f"coord-{tag}@example.local"}
    payload.update(overrides)
    return payload


async def requests_of(db, org_id: str) -> list[BdmOnboardingRequest]:
    db.expire_all()
    stmt = select(BdmOnboardingRequest).where(BdmOnboardingRequest.organization_id == UUID(org_id)).order_by(BdmOnboardingRequest.created_at)
    return list((await db.scalars(stmt)).all())


async def notices(db, user_id) -> list[Notification]:
    db.expire_all()
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at))).all())


async def audits(db, entity_id: str, action: str) -> list[AuditLog]:
    db.expire_all()
    return list((await db.scalars(select(AuditLog).where(AuditLog.entity_id == entity_id, AuditLog.action == action))).all())


async def user(db, user_id) -> User:
    db.expire_all()
    return await db.get_one(User, user_id)
