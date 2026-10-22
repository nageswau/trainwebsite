"""ccrm-014 (DEC-SCOPE-238): the sub-status change shared by the counselor/admin route (api/workflows.py) and the agency route
(api/agent_applications.py). Nothing here commits: the caller scopes, locks, applies its role's cap, notifies, audits and commits."""

from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_sub_status import STAGE_OF
from app.models import ApplicationStatusHistory, OverseasApplication, User
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES

UNKNOWN = "Choose a sub-status from the list"
EARLIER = "That sub-status belongs to an earlier stage -- an application only moves forward"


class Before(NamedTuple):
    status: str
    sub_status: str | None


def stage_of(sub_status: str) -> str:
    stage = STAGE_OF.get(sub_status)
    if stage is None:
        raise HTTPException(422, UNKNOWN)
    return stage


def change(db: AsyncSession, user: User, app: OverseasApplication, sub_status: str, notes: str | None) -> Before | None:
    """Move within the stage, or forward to a later stage's sub-status (a legacy stage counts as before the first, as `/advance`
    treats it). The values before the change, or None when it is already set (no history row: a retry is safe)."""
    stage = stage_of(sub_status)
    current = OVERSEAS_APPLICATION_STAGES.index(app.status) if app.status in OVERSEAS_APPLICATION_STAGES else -1
    if OVERSEAS_APPLICATION_STAGES.index(stage) < current:
        raise HTTPException(422, EARLIER)
    if (app.status, app.sub_status) == (stage, sub_status):
        return None
    before = Before(app.status, app.sub_status)
    app.status = stage
    app.sub_status = sub_status
    db.add(
        ApplicationStatusHistory(
            application_id=app.id, from_status=before.status, to_status=stage, from_sub_status=before.sub_status, to_sub_status=sub_status,
            next_action=app.next_action, notes=notes, changed_by_id=user.id,
        )
    )  # fmt: skip
    return before
