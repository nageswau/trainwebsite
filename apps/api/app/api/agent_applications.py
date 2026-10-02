"""AGN-008 -- an agency's applications for its students, with or without a login (DEC-SCOPE-050; spec §5.3).

Masters see the agency's applications; staff only those of students assigned to them (G4); anything outside the caller's scope is
404. Every write locks the organisation row first and the application row second (AGN-004's lock order), writes its history and
audit rows in the same transaction and commits once, so the duplicate check, the throttle and the status rules hold under
concurrency. Agents move an application forward up to status_tracking or withdraw it; `enrolled` stays with counselor, university
and admin, so an agent never accrues their own commission (A4).
"""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentOrgMember, AuditLog, User
from app.services.agent_applications import detail, list_page, load_scoped
from app.services.agent_orgs import lock_active_org

logger = logging.getLogger("app.agent_applications")

router = APIRouter(prefix="/workflows/overseas/agent/crm/applications", tags=["agent-applications"])

StatusGroup = Literal["all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"]


def _audit(db: AsyncSession, user: User, action: str, application_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001); ids, field names and statuses only. The `overseas.application.*`
    names are the ones the existing paths write, so AGN-021 activity and the throttle read one record."""
    db.add(AuditLog(user_id=user.id, action=f"overseas.application.{action}", entity_type="overseas_application", entity_id=str(application_id), metadata_json=metadata or {}))


def _log(event: str, membership: AgentOrgMember, user: User, application_id, *, level: int = logging.INFO, **extra) -> None:
    logger.log(level, event, extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "application_id": str(application_id), **extra}})


async def _locked(db: AsyncSession, user: User, membership: AgentOrgMember, application_id: UUID):
    """Organisation lock first (the order every agency write uses), then the scoped row -- out of scope stays 404."""
    await lock_active_org(db, membership.org_id)
    return await load_scoped(db, user, application_id, lock=True)


@router.get("")
async def list_applications(
    status: StatusGroup = "all",
    student: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await list_page(db, user, group=status, agent_student_id=student, limit=limit, offset=offset)


@router.get("/{application_id}")
async def get_application(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _gate(user)
    return {"application": await detail(db, user, await load_scoped(db, user, application_id))}
