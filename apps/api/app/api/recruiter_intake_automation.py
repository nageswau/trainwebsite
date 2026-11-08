"""pob-027 (DEC-SCOPE-434 I3, I6, I7; API §12MA): the Team Lead's intake automation -- the task template and the escalation rules -- and
a requirement's tasks. Settings and rules are the Team Lead's (placement_manager, super_admin: 403 otherwise). The tasks follow the
requirement's scope (rec-007 `load_scoped`, officers included: out of scope = 404). Every write is one transaction, committed here."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import EscalationRuleCreate, EscalationRuleUpdate, IntakeAutomationSettingsIn
from app.services import escalations
from app.services import recruiter_requirements as requirements
from app.services import requirement_intake as intake

router = APIRouter(prefix="/recruiter", tags=["recruiter-intake-automation"])


def _settings_out(row) -> dict:
    return {"task_template": row.task_template}


@router.get("/intake-automation/settings")
async def get_settings(response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    intake.require_editor(user)
    response.headers.update(NO_STORE)
    return _settings_out(await intake.settings(db))


@router.put("/intake-automation/settings")
async def put_settings(payload: IntakeAutomationSettingsIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await intake.save_settings(db, user, [item.model_dump() for item in payload.task_template])
    await db.commit()
    intake.log("requirement_intake_settings_saved", "-", tasks=len(row.task_template))
    return _settings_out(row)


@router.get("/escalation-rules")
async def get_rules(response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    intake.require_editor(user)
    response.headers.update(NO_STORE)
    return {"items": [escalations.rule_out(rule) for rule in await escalations.list_rules(db)]}


@router.post("/escalation-rules", status_code=201)
async def create_rule(payload: EscalationRuleCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rule = await escalations.create_rule(db, user, payload.model_dump())
    out = escalations.rule_out(rule)
    await db.commit()
    return {"rule": out}


@router.patch("/escalation-rules/{rule_id}")
async def update_rule(rule_id: UUID, payload: EscalationRuleUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rule = await escalations.update_rule(db, user, rule_id, payload.model_dump(exclude_none=True))
    out = escalations.rule_out(rule)
    await db.commit()
    return {"rule": out}


@router.get("/requirements/{requirement_id}/tasks")
async def list_tasks(requirement_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, officers=True)
    response.headers.update(NO_STORE)
    return {"items": await intake.tasks_out(db, user, job, requirements.permissions(user, job)["can_edit"])}


@router.post("/requirements/{requirement_id}/tasks/{task_id}/complete")
async def complete_task(requirement_id: UUID, task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, officers=True)
    can_edit = requirements.permissions(user, job)["can_edit"]
    task = await intake.complete(db, user, job, task_id, can_edit, datetime.now(UTC))
    assignee = await db.get(User, task.assignee_user_id)
    out = intake.task_out(user, task, assignee, can_edit)
    await db.commit()
    intake.log("requirement_task_completed", job.id, task_id=str(task.id))
    return {"task": out}
