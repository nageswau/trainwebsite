"""ccrm-030 (DEC-SCOPE-269, RM9/RM10) -- the Overseas Admin's reminder rules: read and change each rule, run the job now (idempotent) and
read the recent firings. Super Admin passes `_require` as everywhere; anyone else is 403. Spec:
docs/superpowers/specs/2026-10-25-ccrm-030-counselor-reminders-design.md."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.workflows import _require
from app.core.database import get_db
from app.models import User
from app.services import counselor_reminders as svc

router = APIRouter(prefix="/overseas-admin/reminder-rules", tags=["counselor-reminders"])

ADMINS = {"overseas_admin"}


class ReminderRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    offset_days: int = Field(ge=0, le=60)
    notify_student: bool | None = None


@router.get("")
async def list_rules(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, ADMINS, "overseas")
    return {"rules": await svc.rules_out(db)}


@router.put("/{key}")
async def update_rule(key: str, payload: ReminderRuleIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, ADMINS, "overseas")
    out = await svc.update_rule(db, user, key, payload.enabled, payload.offset_days, payload.notify_student)
    await db.commit()
    svc.log("counselor_reminder_rule_updated", actor_id=user.id, rule=key)
    return out


@router.post("/run")
async def run_now(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """RM10: the daily job, now -- the same de-duplication, so a second run creates nothing new."""
    _require(user, ADMINS, "overseas")
    svc.log("counselor_reminders_run_now", actor_id=user.id)
    return await svc.send_counselor_reminders(db, now=datetime.now(UTC))


@router.get("/log")
async def recent(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, ADMINS, "overseas")
    return await svc.log_page(db, limit, offset)
