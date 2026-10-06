"""bdm-005 test builders, on top of bdm-002/004's. Unique values per call: the test database is shared and never truncated."""

from uuid import UUID

from sqlalchemy import select

from app.models import AuditLog, BdmMou, BdmMouEvent
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm

MOUS = "/api/v1/bdm/mous"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def mou_url(org_id: str, suffix: str = "") -> str:
    return f"{ORGS}/{org_id}/mou{suffix}"


async def start(client, org: dict, **body):
    return await client.post(mou_url(org["id"]), json=body)


async def change(client, org: dict, **body):
    return await client.patch(mou_url(org["id"]), json=body)


async def started(client, org: dict, **body) -> dict:
    response = await start(client, org, **body)
    assert response.status_code == 201, response.text
    return response.json()["mou"]


async def events(db, mou_id: str) -> list[BdmMouEvent]:
    db.expire_all()
    stmt = select(BdmMouEvent).where(BdmMouEvent.mou_id == UUID(mou_id)).order_by(BdmMouEvent.position)
    return list((await db.scalars(stmt)).all())


async def audits(db, mou_id: str, action: str) -> list[AuditLog]:
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.entity_id == mou_id, AuditLog.action == f"bdm_mou.{action}").order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


async def mou_rows(db, org_id: str) -> list[BdmMou]:
    db.expire_all()
    return list((await db.scalars(select(BdmMou).where(BdmMou.organization_id == UUID(org_id)).order_by(BdmMou.created_at))).all())


async def world(client, db, bdm_type: str = "college") -> dict:
    """bdm-004's scope actors around one organization owned by `owner`, who is signed in on return."""
    manager = await make_manager(db)
    owner = await make_bdm(db, manager, bdm_type)
    w = {
        "owner": owner,
        "peer": await make_bdm(db, manager, bdm_type),
        "other_type": await make_bdm(db, manager, "school" if bdm_type != "school" else "college"),
        "manager": manager,
        "other_manager": await make_manager(db),
        "super_admin": await make_user(db, "super_admin", "global"),
        "it_admin": await make_user(db, "it_admin", "it"),
        "student": await make_user(db, "student", "it"),
        "no_profile": await make_user(db, "bdm", "it"),
    }
    w["ids"] = {name: user.id for name, user in w.items()}  # events() / audits() expire the session; ids stay readable
    await login(client, owner)
    w["org"] = await create_org(client, org_type=bdm_type)
    return w
