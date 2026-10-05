"""bdm-004 test builders, on top of bdm-002/003's. Unique values per call: the test database is shared and never truncated."""

from uuid import UUID

from sqlalchemy import select

from app.models import AuditLog, BdmPipelineEvent
from tests.bdm002_helpers import ORGS

PIPELINE = "/api/v1/bdm/pipeline"


def url(org_id: str, action: str) -> str:
    return f"{ORGS}/{org_id}/{action}"


async def move(client, org: dict, to_stage: str, note: str | None = None, from_stage: str | None = None):
    body = {"from_stage": from_stage or org["pipeline"]["stage"], "to_stage": to_stage}
    if note is not None:
        body["note"] = note
    return await client.post(url(org["id"], "stage"), json=body)


async def events(db, org_id: str) -> list[BdmPipelineEvent]:
    db.expire_all()
    stmt = select(BdmPipelineEvent).where(BdmPipelineEvent.organization_id == UUID(org_id)).order_by(BdmPipelineEvent.position)
    return list((await db.scalars(stmt)).all())


async def audits(db, org_id: str, action: str) -> list[AuditLog]:
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.entity_id == org_id, AuditLog.action == f"bdm_organization.{action}").order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())
