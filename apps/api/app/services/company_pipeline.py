"""rec-005 (DEC-SCOPE-127, spec §4): the company B2B pipeline -- the only writer of `companies.stage`, and (pob-004, DEC-SCOPE-417) of the
client status and the Inactive flag.

Requirement-side items call `apply_event`; people call `person_move`, `mark_lost`, `mark_inactive` and `reopen`. All work on a row the caller locked
(`recruiter_companies.load_scoped(lock=True)`), so concurrent changes serialise. Functions only; nothing here commits -- the route owns
the transaction. Logs carry ids, stage keys and the event, never the reason text."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import SessionLocal
from app.models import (
    AuditLog,
    Company,
    CompanyStageHistory,
    Job,
    JobApplication,
    JobOffer,
    RecCompanyInactiveReason,
    RecCompanyLostReason,
    RecruiterContract,
    RecruiterFollowUp,
    RecruiterMeeting,
    User,
)
from app.recruiter_stages import CLIENT_LABELS, CLIENT_ORDER, DRIVEN, EVENTS, KINDS, ORDER, STAGES, START, label
from app.services.recruiter import MANAGER_ROLE
from app.services.recruiter_companies import _allowed, person

logger = logging.getLogger("app.recruiter")

STAGE_UNKNOWN = "Choose a stage of the company pipeline"
STAGE_START = "Target Identified is the starting stage"
STAGE_DRIVEN = "This stage moves with the company's requirements"
STAGE_PAST = "This company's stage now moves with its requirements"
STAGE_SAME = "The company is already at this stage"
REASON_BACK = "Add a reason to move a company back"
REOPEN_FORBIDDEN = "Only a placement manager can reopen this company"
REASON_UNKNOWN = "Choose a reason from the list"
ARCHIVED = "Restore this company first"
LOST_CONFLICT = {"message": "This company is marked lost. A placement manager can reopen it.", "code": "company_lost"}
NOT_LOST_CONFLICT = {"message": "This company is not marked lost or inactive.", "code": "company_not_lost"}
INACTIVE_CONFLICT = {"message": "This company is marked inactive. A placement manager can reopen it.", "code": "company_inactive"}
LOST = "lost"  # the board's Lost bucket
INACTIVE, ACTIVE_CLIENT, REPEAT_BUSINESS, FOLLOW_UP_DUE = "inactive", "active_client", "repeat_business", "follow_up_due"  # pob-004 board filters
REGISTRATION_CONTRACTS = ("contract_sent", "signed", "active")  # pob-004 D4: the contract has no "registration" status; these are as far
SIGNED_CONTRACTS = ("signed", "active")
INACTIVE_AFTER_DAYS = 182  # pob-004 D8 (Q-04): about 6 months
AUTO_INACTIVE_REASON = "No activity for 6 months"
SWEEP_BATCH = 500
IST = ZoneInfo("Asia/Kolkata")
BOARD_STAGE_UNKNOWN = "Choose a stage of this pipeline"
BUCKET_LABELS = {
    ACTIVE_CLIENT: CLIENT_LABELS[ACTIVE_CLIENT], REPEAT_BUSINESS: CLIENT_LABELS[REPEAT_BUSINESS], FOLLOW_UP_DUE: "Follow-up Due", INACTIVE: "Inactive", LOST: "Lost",
}  # fmt: skip


def _invalid(field: str, msg: str, value) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


async def _record(db: AsyncSession, company: Company, to_stage: str, event: str, actor: User | None, reason: str | None) -> None:
    from_stage = company.stage
    if to_stage != from_stage:
        company.stage, company.stage_changed_at = to_stage, await db.scalar(select(func.now()))
    db.add(CompanyStageHistory(company_id=company.id, from_stage=from_stage, to_stage=to_stage, event=event, actor_user_id=actor.id if actor else None, reason=reason))
    logger.info("company_stage_changed", extra={"extra_fields": {
        "company_id": str(company.id), "from_stage": from_stage, "to_stage": to_stage, "event": event, "actor_id": str(actor.id) if actor else None}})


async def apply_event(db: AsyncSession, company: Company, event: str, actor: User | None = None, reason: str | None = None) -> bool:
    """P2/P3: move the locked company if it is in the event's from-set; otherwise (already past it) leave it. A Lost or archived company
    never moves; nor, since pob-004, does an inactive one. Returns whether it moved, so a repeated event never fires twice. An unknown event is
    a KeyError: a caller bug."""
    sources, to_stage = EVENTS[event]
    if _closed(company) or company.stage not in sources:
        return False
    await _record(db, company, to_stage, event, actor, reason)
    return True


def _closed(company: Company) -> bool:
    return company.lost_at is not None or company.inactive_at is not None or company.archived_at is not None


async def _move_client(db: AsyncSession, company: Company, to: str, actor: User | None) -> None:
    """pob-004 D2: forward only, one history row (Lost's shape: the stage is unchanged). A closed company does not move."""
    if not _closed(company) and CLIENT_ORDER.index(to) > CLIENT_ORDER.index(company.client_status):
        company.client_status = to
        await _record(db, company, company.stage, to, actor, None)


async def requirement_received(db: AsyncSession, company: Company, job: Job, actor: User | None) -> None:
    """pob-004 D4: the first requirement makes an Active Client; one arriving after a joining on ANOTHER requirement is Repeat Business."""
    joined_elsewhere = await db.scalar(select(exists().where(
        JobOffer.joining_status == "joined", JobOffer.application_id == JobApplication.id, JobApplication.job_id == Job.id, Job.company_id == company.id, Job.id != job.id,
    )))  # fmt: skip
    await _move_client(db, company, "repeat_business" if joined_elsewhere else "active_client", actor)


async def contract_moved(db: AsyncSession, company: Company, status: str, actor: User | None) -> None:
    """pob-004 D4: a contract at this status on the locked company."""
    if status in REGISTRATION_CONTRACTS:
        await apply_event(db, company, "contract_registration", actor)
    if status in SIGNED_CONTRACTS:
        await _move_client(db, company, "active_client", actor)


def can_move(user: User, company: Company) -> bool:
    """P6: rec-003's `can_edit` holders (the assigned recruiter, super_admin), on an active company that is not Lost."""
    return _allowed(user, company, "can_edit") and not _closed(company)


def can_reopen(user: User, company: Company) -> bool:
    flagged = company.lost_at is not None or company.inactive_at is not None
    return user.role in (MANAGER_ROLE, "super_admin") and company.archived_at is None and flagged


def _require_writer(user: User, company: Company) -> None:
    """403 for the wrong person, then 409 archived, then 409 Lost or Inactive (the same order as rec-003's `require`)."""
    if not _allowed(user, company, "can_edit"):
        raise HTTPException(403, "Only the assigned recruiter can change this company's stage")
    if company.archived_at is not None:
        raise HTTPException(409, ARCHIVED)
    if company.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)
    if company.inactive_at is not None:
        raise HTTPException(409, INACTIVE_CONFLICT)


async def person_move(db: AsyncSession, user: User, company: Company, from_stage: str, to_stage: str, reason: str | None) -> bool:
    """AC2 / P4: a manual stage only, from New Lead or a manual stage; back needs a reason. A stale `from_stage` (someone else moved it)
    is 409 `stage_changed`. Returns whether the move was backward."""
    _require_writer(user, company)
    if from_stage != company.stage:
        raise HTTPException(409, {"message": f"This company moved to {label(company.stage)} meanwhile", "code": "stage_changed", "current_stage": company.stage})
    kind = KINDS.get(to_stage)
    if kind is None:
        raise _invalid("to_stage", STAGE_UNKNOWN, to_stage)
    if kind == START:
        raise _invalid("to_stage", STAGE_START, to_stage)
    if kind == DRIVEN:
        raise _invalid("to_stage", STAGE_DRIVEN, to_stage)
    if KINDS[company.stage] == DRIVEN:
        raise _invalid("to_stage", STAGE_PAST, to_stage)
    if to_stage == company.stage:
        raise _invalid("to_stage", STAGE_SAME, to_stage)
    backward = ORDER.index(to_stage) < ORDER.index(company.stage)
    if backward and reason is None:
        raise _invalid("reason", REASON_BACK, reason)
    await _record(db, company, to_stage, "manual", user, reason)
    return backward


async def _reason_text(db: AsyncSession, model, reason_id: UUID, note: str | None) -> str:
    """pob-004 D5/D6: an active value of that list (FOR SHARE: a concurrent deactivation waits). The text is recorded as it reads now, so a later
    rename does not rewrite what happened."""
    row = await db.scalar(select(model).where(model.id == reason_id).with_for_update(read=True))
    if row is None or not row.active:
        raise _invalid("reason_id", REASON_UNKNOWN, str(reason_id))
    return f"{row.name}: {note}" if note else row.name


async def mark_lost(db: AsyncSession, user: User, company: Company, reason_id: UUID, note: str | None) -> None:
    """AC4 / P5: a flag with a reason on top of the stage, which is kept. pob-004 D6: the reason comes from the catalogue."""
    _require_writer(user, company)
    reason = await _reason_text(db, RecCompanyLostReason, reason_id, note)
    company.lost_at, company.lost_reason, company.lost_reason_id = await db.scalar(select(func.now())), reason, reason_id
    await _record(db, company, company.stage, "lost", user, reason)


async def mark_inactive(db: AsyncSession, user: User, company: Company, reason_id: UUID, note: str | None) -> None:
    """pob-004 D3/D7: the same rules as Lost."""
    _require_writer(user, company)
    reason = await _reason_text(db, RecCompanyInactiveReason, reason_id, note)
    company.inactive_at, company.inactive_reason, company.inactive_reason_id = await db.scalar(select(func.now())), reason, reason_id
    await _record(db, company, company.stage, "inactive", user, reason)


async def reopen(db: AsyncSession, user: User, company: Company, reason: str) -> None:
    """P5 (tel-004 T13), pob-004 D9: a manager (or super_admin) clears the Lost or Inactive flag; the company is back at the stage it had."""
    if user.role not in (MANAGER_ROLE, "super_admin"):
        raise HTTPException(403, REOPEN_FORBIDDEN)
    if company.archived_at is not None:
        raise HTTPException(409, ARCHIVED)
    if company.lost_at is None and company.inactive_at is None:
        raise HTTPException(409, NOT_LOST_CONFLICT)
    company.lost_at, company.lost_reason, company.lost_reason_id = None, None, None
    company.inactive_at, company.inactive_reason, company.inactive_reason_id = None, None, None
    await _record(db, company, company.stage, "reopen", user, reason)


def pipeline_out(user: User, company: Company, follow_up_due: bool) -> dict:
    current = ORDER.index(company.stage)

    def state(i: int) -> str:
        return "done" if i < current else "current" if i == current else "upcoming"

    return {
        "stage": company.stage,
        "stage_label": label(company.stage),
        "stage_changed_at": company.stage_changed_at,
        "lost": {"at": company.lost_at, "reason": company.lost_reason} if company.lost_at else None,
        "inactive": {"at": company.inactive_at, "reason": company.inactive_reason} if company.inactive_at else None,
        "client_status": company.client_status,
        "client_status_label": CLIENT_LABELS[company.client_status],
        "follow_up_due": follow_up_due,
        "can_move": can_move(user, company),
        "can_reopen": can_reopen(user, company),
        "steps": [{"key": key, "label": text, "kind": kind, "state": state(i)} for i, (key, text, kind) in enumerate(STAGES)],
    }


async def history_page(db: AsyncSession, company: Company, limit: int, offset: int) -> dict:
    """Newest first; the actor is null for the system."""
    where = CompanyStageHistory.company_id == company.id
    total = await db.scalar(select(func.count()).select_from(CompanyStageHistory).where(where))
    stmt = select(CompanyStageHistory, User).outerjoin(User, User.id == CompanyStageHistory.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(CompanyStageHistory.position.desc()).limit(limit).offset(offset))).all()
    items = [
        {
            "id": h.id, "event": h.event, "from_stage": h.from_stage, "from_label": label(h.from_stage), "to_stage": h.to_stage,
            "to_label": label(h.to_stage), "reason": h.reason, "actor": {"id": actor.id, "full_name": actor.full_name} if actor else None,
            "created_at": h.created_at,
        }
        for h, actor in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def board(db: AsyncSession, filters: list, stage: str | None, limit: int, offset: int) -> dict:
    """P7: one grouped count over the caller's scope (archived left out; Lost and, pob-004 AC3, Inactive counted apart), then one page of one
    stage, one bucket (D3/D11), or every open company."""
    if stage is not None and stage not in BUCKET_LABELS and stage not in KINDS:
        raise HTTPException(422, BOARD_STAGE_UNKNOWN)
    scope = [*filters, Company.archived_at.is_(None), Company.partner_type != "vendor"]  # pob-010 V10: the board is the client pipeline
    is_lost, is_inactive = Company.lost_at.is_not(None), Company.inactive_at.is_not(None)
    is_open = [Company.lost_at.is_(None), Company.inactive_at.is_(None)]
    follow_up_due = exists().where(RecruiterFollowUp.company_id == Company.id, RecruiterFollowUp.status == "open", RecruiterFollowUp.due_at <= func.now())
    grouped = (await db.execute(
        select(Company.stage, Company.client_status, is_lost, is_inactive, func.count()).where(*scope).group_by(Company.stage, Company.client_status, is_lost, is_inactive)
    )).all()  # fmt: skip
    stage_counts, client_counts, lost_count, inactive_count = {}, {}, 0, 0
    for key, client, lost, inactive, n in grouped:
        if lost:
            lost_count += n
        elif inactive:
            inactive_count += n
        else:
            stage_counts[key] = stage_counts.get(key, 0) + n
            client_counts[client] = client_counts.get(client, 0) + n
    bucket_counts = {
        ACTIVE_CLIENT: client_counts.get(ACTIVE_CLIENT, 0), REPEAT_BUSINESS: client_counts.get(REPEAT_BUSINESS, 0),
        FOLLOW_UP_DUE: await db.scalar(select(func.count()).select_from(Company).where(*scope, *is_open, follow_up_due)) or 0,
        INACTIVE: inactive_count, LOST: lost_count,
    }  # fmt: skip
    match stage:
        case "lost":
            narrow = [is_lost]
        case "inactive":
            narrow = [is_inactive]
        case "active_client" | "repeat_business":
            narrow = [*is_open, Company.client_status == stage]
        case "follow_up_due":
            narrow = [*is_open, follow_up_due]
        case None:
            narrow = is_open
        case _:
            narrow = [*is_open, Company.stage == stage]
    page = [*scope, *narrow]
    total = await db.scalar(select(func.count()).select_from(Company).where(*page))
    recruiter = aliased(User)
    stmt = select(Company, recruiter, follow_up_due.label("follow_up_due")).outerjoin(recruiter, recruiter.id == Company.assigned_recruiter_user_id).where(*page)
    rows = (await db.execute(stmt.order_by(func.lower(Company.name), Company.id).limit(limit).offset(offset))).all()
    return {
        "stages": [{"key": key, "label": text, "kind": kind, "count": stage_counts.get(key, 0)} for key, text, kind in STAGES],
        "buckets": [{"key": key, "label": text, "count": bucket_counts[key]} for key, text in BUCKET_LABELS.items()],
        "lost_count": lost_count,
        "items": [
            {
                "id": c.id, "code": c.company_code, "name": c.name, "city": c.city, "priority": c.priority, "assigned_recruiter": person(r),
                "stage": c.stage, "stage_label": label(c.stage), "lost": c.lost_at is not None, "inactive": c.inactive_at is not None,
                "client_status": c.client_status, "client_status_label": CLIENT_LABELS[c.client_status], "follow_up_due": due,
            }
            for c, r, due in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def run_inactive_sweep(now: datetime | None = None) -> dict[str, int]:
    """pob-004 D8: daily via beat. Flags companies with no activity for INACTIVE_AFTER_DAYS. A flagged row leaves the candidates, so it is
    idempotent; SKIP LOCKED leaves a row someone is writing to the next run."""
    from app.services.recruiter_requirements import ENDED  # local: recruiter_requirements imports this module

    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=INACTIVE_AFTER_DAYS)
    candidates = (
        Company.archived_at.is_(None), Company.lost_at.is_(None), Company.inactive_at.is_(None), Company.partner_type != "vendor",  # pob-010 V10
        Company.created_at < cutoff, Company.stage_changed_at < cutoff,
        or_(Company.last_contacted_at.is_(None), Company.last_contacted_at < cutoff),
        ~exists().where(Job.company_id == Company.id, or_(Job.status.not_in(ENDED), Job.updated_at >= cutoff)),
        ~exists().where(RecruiterFollowUp.company_id == Company.id, RecruiterFollowUp.status == "open"),
        ~exists().where(RecruiterMeeting.company_id == Company.id, RecruiterMeeting.starts_at >= cutoff),
        ~exists().where(
            RecruiterContract.company_id == Company.id, RecruiterContract.is_current.is_(True), RecruiterContract.status.in_(SIGNED_CONTRACTS),
            or_(RecruiterContract.end_date.is_(None), RecruiterContract.end_date >= now.astimezone(IST).date()),
        ),
    )  # fmt: skip
    flagged = 0
    async with SessionLocal() as db:
        while batch := (await db.scalars(select(Company).where(*candidates).order_by(Company.id).limit(SWEEP_BATCH).with_for_update(skip_locked=True))).all():
            for company in batch:
                company.inactive_at, company.inactive_reason = now, AUTO_INACTIVE_REASON
                await _record(db, company, company.stage, "inactive", None, AUTO_INACTIVE_REASON)
                db.add(AuditLog(user_id=None, action="recruiter_company.inactive", entity_type="company", entity_id=str(company.id), metadata_json={"stage": company.stage, "automatic": True}))
            await db.commit()
            flagged += len(batch)
    logger.info("companies_marked_inactive", extra={"extra_fields": {"count": flagged}})
    return {"inactive": flagged}
