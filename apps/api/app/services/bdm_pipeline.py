"""bdm-004 (DEC-SCOPE-070, spec §6.2): pipeline output, move / Lost / Revive rules, history and the pipeline view.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Every check runs on the row locked by
`load_scoped(lock=True)`. Audit metadata and logs carry stage keys and flags only, never the note or reason text (spec §6.6)."""

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bdm_stages import AGENT_STATUS, LIVE, MANUAL, PIPELINES, VOLUME
from app.models import BdmOrganization, BdmPipelineEvent, User
from app.schemas import BdmStageMove
from app.services.bdm import bdm_context, person_ref

_LATER_STATE = {MANUAL: "upcoming", LIVE: "awaiting_handover", VOLUME: "not_tracked"}
STAGE_UNKNOWN = "Choose a stage of this organization's pipeline"
STAGE_LIVE = "This stage is set by the onboarding handover"
STAGE_VOLUME = "This step is counted from live records, not set by hand"
STAGE_SAME = "The organization is already at this stage"
NOTE_REQUIRED = "Add a note to move an organization back"
LOST_CONFLICT = {"message": "This organization is marked lost. Revive it first.", "code": "organization_lost"}
NOT_LOST_CONFLICT = {"message": "This organization is not marked lost.", "code": "organization_not_lost"}


def label_of(bdm_type: str, key: str) -> str:
    """A stage key's source label; a key no longer in the catalogue (history after a future change) is shown as stored."""
    return next((s.label for s in PIPELINES[bdm_type] if s.key == key), key)


def live_status(org: BdmOrganization) -> None:
    """S3: the live post-handover stage, read from the linked School (bdm-018) or Agent Organization (bdm-019). Nothing is linked
    yet, so live steps show "Awaiting handover"."""
    return None


def pipeline_out(org: BdmOrganization) -> dict:
    steps = PIPELINES[org.bdm_type]
    current = next(i for i, s in enumerate(steps) if s.key == org.pipeline_stage)

    def state(i: int, kind: str) -> str:
        return "done" if i < current else "current" if i == current else _LATER_STATE[kind]

    return {
        "stage": org.pipeline_stage,
        "stage_label": steps[current].label,
        "lost": {"at": org.lost_at, "reason": org.lost_reason} if org.lost_at else None,
        "agent_status": AGENT_STATUS[org.pipeline_stage] if org.bdm_type == "agent" else None,
        "steps": [{"key": s.key, "label": s.label, "kind": s.kind, "state": state(i, s.kind)} for i, s in enumerate(steps)],
    }


def _invalid(field: str, msg: str, value) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def check_move(user: User, org: BdmOrganization, payload: BdmStageMove) -> bool:
    """Spec §6.4 steps 6-8 on the locked row (the route already ran require: 403, archived 409). Returns whether the move is
    backward (S6)."""
    if org.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)
    if payload.from_stage != org.pipeline_stage:
        log_conflict(user, org, payload.to_stage)
        current = label_of(org.bdm_type, org.pipeline_stage)
        raise HTTPException(409, {"message": f"This organization moved to {current} meanwhile", "code": "stage_changed", "current_stage": org.pipeline_stage})
    steps = PIPELINES[org.bdm_type]
    keys = [s.key for s in steps]
    if payload.to_stage not in keys:
        raise _invalid("to_stage", STAGE_UNKNOWN, payload.to_stage)
    kind = steps[keys.index(payload.to_stage)].kind
    if kind != MANUAL:
        raise _invalid("to_stage", STAGE_LIVE if kind == LIVE else STAGE_VOLUME, payload.to_stage)
    if payload.to_stage == org.pipeline_stage:
        raise _invalid("to_stage", STAGE_SAME, payload.to_stage)
    backward = keys.index(payload.to_stage) < keys.index(org.pipeline_stage)
    if backward and payload.note is None:
        raise _invalid("note", NOTE_REQUIRED, payload.note)
    return backward


def record_event(db: AsyncSession, user: User, org: BdmOrganization, kind: str, from_stage: str, to_stage: str, note: str | None) -> None:
    db.add(BdmPipelineEvent(organization_id=org.id, actor_user_id=user.id, kind=kind, from_stage=from_stage, to_stage=to_stage, note=note))


def log_conflict(user: User, org: BdmOrganization, to_stage: str) -> None:
    """Operational signal for two people (or two tabs) moving one organization; ids and keys only."""
    from app.services.bdm_organizations import log  # local: bdm_organizations imports this module

    log("bdm_org_stage_conflict", user, org.id, current_stage=org.pipeline_stage, to_stage=to_stage)


async def history_page(db: AsyncSession, org: BdmOrganization, limit: int, offset: int) -> dict:
    where = BdmPipelineEvent.organization_id == org.id
    total = await db.scalar(select(func.count()).select_from(BdmPipelineEvent).where(where))
    stmt = select(BdmPipelineEvent, User).join(User, User.id == BdmPipelineEvent.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(BdmPipelineEvent.position.desc()).limit(limit).offset(offset))).all()
    items = [
        {
            "id": e.id, "kind": e.kind, "from_stage": e.from_stage, "from_label": label_of(org.bdm_type, e.from_stage),
            "to_stage": e.to_stage, "to_label": label_of(org.bdm_type, e.to_stage), "note": e.note,
            "actor": {"id": actor.id, "full_name": actor.full_name}, "created_at": e.created_at,
        }
        for e, actor in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


LOST = "lost"  # the pipeline view's Lost bucket (S5)
TYPE_REQUIRED = "Choose a BDM type"
TYPE_NOT_YOURS = "You can only view your own module's pipeline"
VIEW_STAGE_UNKNOWN = "Choose a stage of this pipeline"


async def view_type(db: AsyncSession, user: User, bdm_type: str | None) -> str:
    """S7: a BDM sees their own module; a manager / super_admin names the type (a team may mix types, D26). Call after
    caller_scope, which refuses other roles with 403."""
    if user.role == "bdm":
        own = (await bdm_context(db, user)).bdm_type
        if bdm_type not in (None, own):
            raise HTTPException(422, TYPE_NOT_YOURS)
        return own
    if bdm_type is None:
        raise HTTPException(422, TYPE_REQUIRED)
    return bdm_type


async def pipeline_view(db: AsyncSession, filters: list, bdm_type: str, stage: str | None, limit: int, offset: int) -> dict:
    """One grouped count over the (bdm_type, pipeline_stage) index, then one page. Archived organizations are excluded; Lost ones are
    counted only in lost_count and listed only under stage=lost."""
    steps = PIPELINES[bdm_type]
    if stage is not None and stage != LOST and stage not in {s.key for s in steps}:
        raise HTTPException(422, VIEW_STAGE_UNKNOWN)
    scope = [*filters, BdmOrganization.bdm_type == bdm_type, BdmOrganization.archived_at.is_(None)]
    is_lost = BdmOrganization.lost_at.is_not(None)
    grouped = (await db.execute(select(BdmOrganization.pipeline_stage, is_lost, func.count()).where(*scope).group_by(BdmOrganization.pipeline_stage, is_lost))).all()
    counts = {key: n for key, lost, n in grouped if not lost}
    lost_count = sum(n for _, lost, n in grouped if lost)
    page = [*scope, is_lost if stage == LOST else BdmOrganization.lost_at.is_(None)]
    if stage not in (None, LOST):
        page.append(BdmOrganization.pipeline_stage == stage)
    total = await db.scalar(select(func.count()).select_from(BdmOrganization).where(*page))
    stmt = select(BdmOrganization, User).join(User, User.id == BdmOrganization.assigned_bdm_user_id).where(*page)
    rows = (await db.execute(stmt.order_by(BdmOrganization.name, BdmOrganization.id).limit(limit).offset(offset))).all()
    return {
        "bdm_type": bdm_type,
        "stages": [{"key": s.key, "label": s.label, "kind": s.kind, "count": counts.get(s.key, 0) if s.kind == MANUAL else None} for s in steps],
        "lost_count": lost_count,
        "items": [
            {
                "id": org.id, "code": org.code, "name": org.name, "city": org.city, "org_type": org.org_type, "assigned_bdm": person_ref(assignee),
                "stage": org.pipeline_stage, "stage_label": label_of(bdm_type, org.pipeline_stage), "lost": org.lost_at is not None,
            }
            for org, assignee in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }
