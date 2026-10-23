"""ccrm-015 (DEC-SCOPE-244): an application's exception outcome -- the guards every stage write uses, the record / reopen writes shared by
the counselor-admin routes (api/workflows.py) and the agency withdraw (api/agent_applications.py), and the read views. Nothing here
commits: the caller scopes, locks, notifies, audits and commits. Spec: docs/superpowers/specs/2026-10-23-ccrm-015-application-outcomes-design.md."""

from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_outcome import CLEARED, TERMINAL, label
from app.application_sub_status import fit as fit_sub_status
from app.models import ApplicationOutcome, ApplicationStatusHistory, OverseasApplication, StudentDocument, User
from app.services.agent_applications import OFFER_STAGES_ON, WITHDRAWN, WITHDRAWN_REFUSED

ON_HOLD = "This application is on hold -- resume it before changing its stage"
ENROLLED = "An enrolled application cannot be given an outcome"
OFFER_NEEDED = "An offer is needed before it can be declined"
LETTER_MISMATCH = "Choose a document uploaded for this application"
HOLD_OWNER = "Choose an active overseas counselor or admin as the hold owner"
REVIEW_PAST = "The review date cannot be in the past"
NOTHING_TO_CLEAR = "This application has no outcome to clear"
ADMIN_REOPENS = "Only the Overseas Admin can reopen a closed application"


def closed_message(outcome: str) -> str:
    return f"This application is {label(outcome).lower()} -- only the Overseas Admin can reopen it"


def is_closed(app: OverseasApplication) -> bool:
    return app.status == WITHDRAWN or app.outcome in TERMINAL


def refuse_closed(app: OverseasApplication) -> None:
    """O2: a terminal outcome refuses every stage write (409). Withdrawn keeps AGN-008's message."""
    if app.status == WITHDRAWN:
        raise HTTPException(409, WITHDRAWN_REFUSED)
    if app.outcome in TERMINAL:
        raise HTTPException(409, closed_message(app.outcome))


def refuse_on_hold(app: OverseasApplication) -> None:
    if app.outcome == "on_hold":
        raise HTTPException(409, ON_HOLD)


def _history(db: AsyncSession, user: User, app: OverseasApplication, before: tuple[str, str | None], note: str, *, outcome: str, reason: str | None) -> None:
    db.add(
        ApplicationStatusHistory(
            application_id=app.id, from_status=before[0], to_status=app.status, from_sub_status=before[1], to_sub_status=app.sub_status,
            next_action=app.next_action, notes=note, outcome=outcome, reason=reason, changed_by_id=user.id,
        )
    )  # fmt: skip


def _note(prefix: str, reason: str | None) -> str:
    return f"{prefix} -- {reason}" if reason else prefix


def withdraw_event(db: AsyncSession, user: User, app: OverseasApplication, *, requested_by: str, reason: str | None) -> None:
    """The agency route's withdraw (it writes its own history row): the outcome and its event."""
    app.outcome = "withdrawn"
    db.add(ApplicationOutcome(application_id=app.id, outcome="withdrawn", outcome_date=date.today(), reason=reason, requested_by=requested_by, created_by_id=user.id))


async def _check_document(db: AsyncSession, app: OverseasApplication, document_id: UUID | None) -> None:
    if document_id is None:
        return
    found = await db.scalar(select(StudentDocument.application_id).where(StudentDocument.id == document_id))
    if found != app.id:
        raise HTTPException(422, LETTER_MISMATCH)


async def _hold_owner(db: AsyncSession, user: User, owner_id: UUID | None) -> UUID:
    if owner_id is None or owner_id == user.id:
        return user.id
    owner = await db.get(User, owner_id)
    if owner is None or owner.role not in {"counselor", "overseas_admin"} or owner.division != "overseas" or not owner.active:
        raise HTTPException(422, HOLD_OWNER)
    return owner.id


async def record(db: AsyncSession, user: User, app: OverseasApplication, body) -> ApplicationOutcome:
    """Set `body.outcome` (an `ApplicationOutcomeSet`, its per-outcome fields already required). Refusals: closed, enrolled 409."""
    refuse_closed(app)
    if app.status == "enrolled":
        raise HTTPException(409, ENROLLED)
    kind = body.outcome
    event = ApplicationOutcome(application_id=app.id, outcome=kind, outcome_date=body.outcome_date or date.today(), reason=body.reason, created_by_id=user.id)
    if kind == "rejected":
        await _check_document(db, app, body.document_id)
        event.next_steps, event.document_id = body.next_steps, body.document_id
    elif kind == "withdrawn":
        event.requested_by = body.requested_by
    elif kind == "deferred":
        event.previous_intake, event.new_intake = app.intake, body.new_intake
        app.intake = body.new_intake
        for field in ("application_deadline", "offer_deadline"):
            if getattr(body, field) is not None:
                setattr(app, field, getattr(body, field))
    elif kind == "on_hold":
        if body.review_date < date.today():
            raise HTTPException(422, REVIEW_PAST)
        event.review_date, event.hold_owner_id = body.review_date, await _hold_owner(db, user, body.hold_owner_id)
    elif kind == "offer_declined":
        if app.status not in OFFER_STAGES_ON and app.offer_type is None:
            raise HTTPException(422, OFFER_NEEDED)
        event.another_offer_preferred = body.another_offer_preferred
    before = (app.status, app.sub_status)
    app.outcome = kind
    if kind == "withdrawn":
        app.status = WITHDRAWN
    db.add(event)
    _history(db, user, app, before, _note(f"Outcome: {label(kind)}", body.reason), outcome=kind, reason=body.reason)
    return event


async def reopen(db: AsyncSession, user: User, app: OverseasApplication, reason: str) -> str:
    """Clear the outcome: on hold / deferred by the counselor or Admin (resume), a terminal one by the Overseas Admin only. A withdrawn
    application gets back the stage and sub-status it was withdrawn from. Returns the outcome that was cleared."""
    cleared = app.outcome or (WITHDRAWN if app.status == WITHDRAWN else None)
    if cleared is None:
        raise HTTPException(409, NOTHING_TO_CLEAR)
    if cleared in TERMINAL and user.role != "overseas_admin":
        raise HTTPException(403, ADMIN_REOPENS)
    before = (app.status, app.sub_status)
    if app.status == WITHDRAWN:
        last = await db.scalar(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == app.id, ApplicationStatusHistory.to_status == WITHDRAWN)
            .order_by(ApplicationStatusHistory.created_at.desc())
            .limit(1)
        )
        stage = last.from_status if last is not None and last.from_status and last.from_status != WITHDRAWN else "enquiry"
        app.status = stage
        app.sub_status = fit_sub_status(stage, last.from_sub_status if last is not None else None)
    app.outcome = None
    db.add(ApplicationOutcome(application_id=app.id, outcome=CLEARED, outcome_date=date.today(), reason=reason, created_by_id=user.id))
    _history(db, user, app, before, _note(f"{'Reopened' if cleared in TERMINAL else 'Resumed'} ({label(cleared)})", reason), outcome=CLEARED, reason=reason)
    return cleared


async def latest(db: AsyncSession, application_ids: list[UUID]) -> dict[UUID, ApplicationOutcome]:
    """Each application's latest outcome event (the detail of its current outcome when one is set), in one query."""
    if not application_ids:
        return {}
    stmt = select(ApplicationOutcome).where(ApplicationOutcome.application_id.in_(application_ids)).order_by(ApplicationOutcome.created_at.desc())
    found: dict[UUID, ApplicationOutcome] = {}
    for row in (await db.scalars(stmt)).all():  # a handful of events per application
        found.setdefault(row.application_id, row)
    return found


def summary(app: OverseasApplication, event: ApplicationOutcome | None) -> str | None:
    """A one-line staff summary of the current outcome, e.g. "On hold until 2026-11-05 -- awaiting funds"."""
    if not app.outcome:
        return None
    text = label(app.outcome)
    if event is None or event.outcome != app.outcome:
        return text
    if event.review_date:
        text += f" until {event.review_date.isoformat()}"
    if event.new_intake:
        text += f" to {event.new_intake}"
    return _note(text, event.reason)


def view(app: OverseasApplication, event: ApplicationOutcome | None, *, staff: bool, hold_owner: str | None = None) -> dict | None:
    """The current outcome's detail. A student sees the outcome, its date, next steps and new intake -- not the internal reason,
    owner or letter."""
    if not app.outcome:
        return None
    current = event if event is not None and event.outcome == app.outcome else None
    fields = ("outcome_date", "next_steps", "new_intake") + (("reason", "requested_by", "review_date", "document_id", "another_offer_preferred") if staff else ())
    out = {"outcome": app.outcome, "label": label(app.outcome), "terminal": app.outcome in TERMINAL}
    out |= {name: getattr(current, name) if current else None for name in fields}
    if staff:
        out["hold_owner"] = hold_owner
    return out
