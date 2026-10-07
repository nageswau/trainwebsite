"""bdm-004 (DEC-SCOPE-071, spec §6.2): pipeline output, move / Lost / Revive rules, history and the pipeline view.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Every check runs on the row locked by
`load_scoped(lock=True)`. Audit metadata and logs carry stage keys and flags only, never the note or reason text (spec §6.6)."""

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import and_, exists, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.bdm_stages import AGENT_STATUS, LIVE, MANUAL, PIPELINES, VOLUME
from app.models import (
    AgentOrg,
    AgentOrgMember,
    BdmOnboardingRequest,
    BdmOrganization,
    BdmPipelineEvent,
    OverseasApplication,
    PortfolioEntry,
    PortfolioProfile,
    SchoolCareerRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
    SchoolStudent,
    User,
)
from app.schemas import BdmStageMove
from app.services.agent_network import org_counts
from app.services.bdm import bdm_context, person_ref

_LATER_STATE = {MANUAL: "upcoming", LIVE: "awaiting_handover", VOLUME: "not_tracked"}
_LIVE_KEYS = {t: tuple(s.key for s in PIPELINES[t] if s.kind == LIVE) for t in ("school", "agent")}
_AGENT_VOLUME = tuple(s.key for s in PIPELINES["agent"] if s.kind == VOLUME)
INACTIVE = "inactive"  # bdm-019 A5: the linked agency is suspended or rejected
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


async def agency_snapshot(db: AsyncSession, agent_org_id) -> dict:
    """bdm-019 (A7): what a BDM may see of a linked Agent Organization -- its name, code and status, whether an active Master exists,
    and aggregate counts from AGN-022's `org_counts` (the agency dashboard's definitions). No member or student row leaves here."""
    agency = await db.get_one(AgentOrg, agent_org_id)
    master = exists().where(AgentOrgMember.org_id == agency.id, AgentOrgMember.role == "master", AgentOrgMember.status == "active")
    counts = (await org_counts(db, [agency.id]))[agency.id]
    return {
        "name": agency.name,
        "prefix": agency.prefix,
        "status": agency.status,
        "master_login": bool(await db.scalar(select(master))),
        "staff_count": counts["staff_count"],
        "counts": {k: counts[k] for k in _AGENT_VOLUME},
    }


def _agent_live(agency: dict) -> dict:
    """bdm-019 A3-A5: each live Agent step on its own evidence, the volume counts, and whether the agency is suspended or rejected."""
    return {
        "agent_onboarding": True,
        "master_login_created": agency["master_login"],
        "staff_logins_created": agency["staff_count"] > 0,
        "active_agent": agency["status"] == "active",
        **agency["counts"],
        INACTIVE: agency["status"] in ("suspended", "rejected"),
    }


async def live_status(db: AsyncSession, org: BdmOrganization) -> dict | None:
    """S3, filled by bdm-018 for School organizations (DEC-SCOPE-085 H2, spec §4) and bdm-019 for Agent ones (DEC-SCOPE-106 A3-A5):
    each live step's own evidence from the linked partner record; a pending request alone means nothing is reached yet. None (no request,
    no link) keeps "Awaiting handover". Agent volume steps map to counts; the `INACTIVE` key is not a step."""
    if org.bdm_type not in _LIVE_KEYS:
        return None
    link = org.school_id if org.bdm_type == "school" else org.agent_org_id
    if link is None:
        pending = exists().where(BdmOnboardingRequest.organization_id == org.id, BdmOnboardingRequest.status == "pending")
        return dict.fromkeys(_LIVE_KEYS[org.bdm_type], False) if await db.scalar(select(pending)) else None
    if org.bdm_type == "agent":
        return _agent_live(await agency_snapshot(db, link))
    students = select(SchoolStudent.id).where(SchoolStudent.school_id == org.school_id)
    checks = {
        "school_onboarding": true(),
        "users_created": and_(
            exists().where(User.role == "school_teacher", User.profile["school_id"].as_string() == str(org.school_id)),
            exists().where(SchoolParentLink.school_student_id.in_(students)),
            students.exists(),
        ),
        "career_guidance": exists().where(
            SchoolCareerRecord.school_student_id.in_(students), SchoolCareerRecord.record_type == "guidance_session", SchoolCareerRecord.status == "completed"
        ),
        "psychometric": exists().where(SchoolPsychometricRecord.school_student_id.in_(students), SchoolPsychometricRecord.status == "completed"),
        "profile_building": or_(
            exists().where(PortfolioEntry.school_student_id.in_(students)),
            exists().where(PortfolioProfile.school_student_id.in_(students), func.coalesce(func.trim(PortfolioProfile.personal_statement), "") != ""),
        ),
        "university_planning": exists().where(OverseasApplication.school_student_id.in_(students)),
    }
    row = (await db.execute(select(*(check.label(key) for key, check in checks.items())))).one()
    return {key: bool(value) for key, value in row._mapping.items()}


def _agent_status(org: BdmOrganization, live: dict | None) -> str | None:
    """S4 (D13), completed by bdm-019 A5: the stored-stage mapping until a request exists; then Onboarding, Active once the agency is
    active, Inactive while it is suspended or rejected."""
    if org.bdm_type != "agent":
        return None
    if live is None:
        return AGENT_STATUS[org.pipeline_stage]
    if live.get(INACTIVE):
        return "Inactive"
    return "Active" if live["active_agent"] else "Onboarding"


def pipeline_out(org: BdmOrganization, live: dict | None = None) -> dict:
    """bdm-018 (spec §4): with `live`, manual steps up to the stored stage are done, live steps are done on their own evidence and the
    first one without it is current. bdm-019 A4: a counted volume step carries its count and is done once it is above zero. `stage`
    stays the stored manual stage (H11)."""
    steps = PIPELINES[org.bdm_type]
    current = next(i for i, s in enumerate(steps) if s.key == org.pipeline_stage)
    first_open = next((s.key for s in steps if s.kind == LIVE and not live[s.key]), None) if live is not None else None

    def count(step) -> int | None:
        return live.get(step.key) if live is not None and step.kind == VOLUME else None

    def state(i: int, step) -> str:
        if live is not None and step.kind == LIVE:
            return "done" if live[step.key] else "current" if step.key == first_open else "upcoming"
        if live is not None and step.kind == MANUAL:
            return "done" if i <= current else "upcoming"
        if count(step) is not None:
            return "done" if count(step) > 0 else "upcoming"
        return "done" if i < current else "current" if i == current else _LATER_STATE[step.kind]

    return {
        "stage": org.pipeline_stage,
        "stage_label": steps[current].label,
        "lost": {"at": org.lost_at, "reason": org.lost_reason} if org.lost_at else None,
        "agent_status": _agent_status(org, live),
        "steps": [{"key": s.key, "label": s.label, "kind": s.kind, "state": state(i, s), "count": count(s)} for i, s in enumerate(steps)],
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


def behind(org: BdmOrganization, stage: str) -> bool:
    keys = [s.key for s in PIPELINES[org.bdm_type]]
    return keys.index(org.pipeline_stage) < keys.index(stage)


def advance_to(db: AsyncSession, user: User, org: BdmOrganization, stage: str, note: str) -> str | None:
    """bdm-005 (D28 / DEC-SCOPE-078 M5): move a locked organization forward to `stage` as one `move` event; at or past it, nothing.
    Returns the stage it left, or None. The caller owns the audit row and the commit."""
    if not behind(org, stage):
        return None
    from_stage = org.pipeline_stage
    org.pipeline_stage = stage
    record_event(db, user, org, "move", from_stage, stage, note)
    return from_stage


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
