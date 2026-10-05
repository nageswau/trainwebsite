"""bdm-004 (DEC-SCOPE-070, spec §6.2): pipeline output, move / Lost / Revive rules, history and the pipeline view.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Every check runs on the row locked by
`load_scoped(lock=True)`. Audit metadata and logs carry stage keys and flags only, never the note or reason text (spec §6.6)."""

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bdm_stages import AGENT_STATUS, LIVE, MANUAL, PIPELINES, VOLUME
from app.models import BdmOrganization, BdmPipelineEvent, User
from app.schemas import BdmStageMove

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
