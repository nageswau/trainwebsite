"""ccrm-023 (DEC-SCOPE-245): an application's offer records -- the only writer of `application_offers` and of the offer columns
mirrored on `overseas_applications`. Shared by the counselor/admin routes (api/application_offers.py) and the agency PUT/PATCH
(api/agent_applications.py). Nothing here commits: the caller scopes, locks the application row (which serialises every offer write;
the partial unique index backs it), writes history, notifies, audits and commits.
"""

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.application_outcome import TERMINAL
from app.application_sub_status import SUB_STATUSES
from app.models import ApplicationOffer, ApplicationStatusHistory, OverseasApplication, StudentDocument, University, User
from app.services import agent_notifications as agency_notices
from app.services import offer_conditions
from app.services.agent_applications import WITHDRAWN, before_offer, check_transition

logger = logging.getLogger("app.application_offers")
INDIA = ZoneInfo("Asia/Kolkata")

# The values an offer carries; a request identical to the active offer's is a no-op (a retry is safe).
FIELDS = ("offer_type", "issue_date", "offer_deadline", "conditions", "currency", "tuition_amount", "scholarship_amount", "deposit_amount", "deposit_deadline", "offer_document_id")
TYPE_LABELS = {"conditional": "Conditional", "unconditional": "Unconditional", "pathway": "Pathway", "other": "Other"}
CLOSE_LABELS = {"withdrawn_by_university": "Offer withdrawn by the university", "expired": "Offer expired"}
OFFER_SUB_STATUSES = SUB_STATUSES["offer"]
NOT_ACTIVE = "Only the current offer can be withdrawn or marked expired"
OFFER_NOT_FOUND = "Offer not found"
# ccrm-025 (DEC-SCOPE-255): the student's decision on the current offer.
DECISION_LABELS = {"considering": "Considering", "accepted": "Accepted", "declined": "Declined", "expired": "Expired"}
NOT_DECIDABLE = "Only the current offer can be accepted or declined"
DECIDED_BEFORE_ISSUE = "The decision date cannot be before the offer was issued"
STUDENT_URL = "/overseas/student/applications"
COUNSELOR_URL = "/overseas/counselor/applications"


def sub_status_for(offer_type: str) -> str:
    """OF3: unconditional is an unconditional offer; conditional, pathway and other are conditional ones."""
    return "unconditional_offer" if offer_type == "unconditional" else "conditional_offer"


async def active_offer(db: AsyncSession, app: OverseasApplication) -> ApplicationOffer | None:
    return await db.scalar(select(ApplicationOffer).where(ApplicationOffer.application_id == app.id, ApplicationOffer.status == "active"))


def values_of(offer: ApplicationOffer | None) -> dict | None:
    return {field: getattr(offer, field) for field in FIELDS} if offer else None


def _mirror(app: OverseasApplication, offer: ApplicationOffer | None) -> None:
    app.offer_type = offer.offer_type if offer else None
    app.offer_date = offer.issue_date if offer else None
    app.offer_deadline = offer.offer_deadline if offer else None
    app.offer_conditions = offer.conditions if offer else None
    app.offer_document_id = offer.offer_document_id if offer else None


async def record(db: AsyncSession, user: User, app: OverseasApplication, values: dict, *, carry_conditions: bool = False) -> ApplicationOffer:
    """Supersede the active offer (kept), add the new one and mirror it. The superseded row is flushed first, so the one-active index
    never sees two active rows. ccrm-024: the new offer's conditions text seeds one condition (C1); `carry_conditions` -- the same offer
    re-recorded with a new deadline -- moves the previous offer's conditions instead (C9)."""
    previous = await active_offer(db, app)
    if previous is not None:
        previous.status = "superseded"
        await db.flush()
    offer = ApplicationOffer(application_id=app.id, recorded_by_id=user.id, status="active", **{field: values.get(field) for field in FIELDS})
    db.add(offer)
    await db.flush()
    if carry_conditions and previous is not None:
        await offer_conditions.move(db, previous, offer)
    else:
        offer_conditions.seed(db, user, offer)
    _mirror(app, offer)
    return offer


def apply_stage(app: OverseasApplication, offer_type: str) -> None:
    """A stage before `offer` moves to `offer` (forward only); at `offer` the type's sub-status is set (OF3). A later stage keeps its
    stage and sub-status."""
    if before_offer(app.status):
        check_transition(app.status, "offer")
        app.status = "offer"
    if app.status == "offer":
        app.sub_status = sub_status_for(offer_type)


def close(user: User | None, app: OverseasApplication, offer: ApplicationOffer, status: str, reason: str) -> None:
    """OF4: close the current offer, clear the mirror and an offer sub-status; the stage stays (forward-only). No user: the expiry job."""
    offer.status = status
    offer.status_reason = reason
    offer.closed_by_id = user.id if user else None
    offer.closed_at = datetime.now(UTC)
    _mirror(app, None)
    if app.sub_status in OFFER_SUB_STATUSES:
        app.sub_status = None


def set_decision(user: User | None, offer: ApplicationOffer, decision: str, on: date) -> None:
    offer.decision, offer.decision_date, offer.decided_by_id = decision, on, user.id if user else None


def accept(user: User, app: OverseasApplication, offer: ApplicationOffer, on: date) -> None:
    """ccrm-025: the student accepted the current offer; at stage `offer` the sub-status becomes Offer accepted (a later stage keeps its own)."""
    set_decision(user, offer, "accepted", on)
    if app.status == "offer":
        app.sub_status = "offer_accepted"


def decline(user: User, app: OverseasApplication, offer: ApplicationOffer, on: date) -> None:
    """ccrm-025: called by the `offer_declined` outcome writer -- the current offer is declined; Offer accepted goes back to its type's."""
    set_decision(user, offer, "declined", on)
    if app.sub_status == "offer_accepted":
        app.sub_status = sub_status_for(offer.offer_type)


async def other_accepted(db: AsyncSession, app: OverseasApplication) -> list[dict]:
    """D1: the same student's other open applications whose current offer is accepted -- a warning, never a block."""
    owner = [column == value for column, value in ((OverseasApplication.student_id, app.student_id), (OverseasApplication.agent_student_id, app.agent_student_id)) if value]
    if not owner:
        return []
    rows = await db.execute(
        select(OverseasApplication.id, OverseasApplication.application_code, University.name)
        .join(ApplicationOffer, ApplicationOffer.application_id == OverseasApplication.id)
        .join(University, University.id == OverseasApplication.university_id)
        .where(
            or_(*owner),
            OverseasApplication.id != app.id,
            OverseasApplication.status != WITHDRAWN,
            or_(OverseasApplication.outcome.is_(None), OverseasApplication.outcome.not_in(TERMINAL)),
            ApplicationOffer.status == "active",
            ApplicationOffer.decision == "accepted",
        )
        .order_by(OverseasApplication.application_code)
    )
    return [{"id": id_, "application_code": code, "university": university} for id_, code, university in rows.all()]


async def expire_offers(db: AsyncSession, today: date) -> int:
    """D3: the current offer of an application at stage `offer` (no outcome, or deferred), still undecided, whose deadline is before
    `today` -> decision expired and the offer closed as expired (OF4). Rows another session holds are skipped (SKIP LOCKED) and picked up
    by the next run; a rerun finds nothing left. Returns how many."""
    rows = (
        await db.execute(
            select(OverseasApplication, ApplicationOffer)
            .join(ApplicationOffer, ApplicationOffer.application_id == OverseasApplication.id)
            .where(
                OverseasApplication.status == "offer",
                or_(OverseasApplication.outcome.is_(None), OverseasApplication.outcome == "deferred"),
                ApplicationOffer.status == "active",
                ApplicationOffer.decision == "considering",
                ApplicationOffer.offer_deadline < today,
            )
            .with_for_update(skip_locked=True, of=OverseasApplication)
            .execution_options(populate_existing=True)
        )
    ).all()
    for app, offer in rows:
        reason = f"Offer deadline {offer.offer_deadline.isoformat()} passed without a decision"
        before = app.sub_status
        set_decision(None, offer, "expired", today)
        close(None, app, offer, "expired", reason)
        db.add(
            ApplicationStatusHistory(
                application_id=app.id, from_status=app.status, to_status=app.status, from_sub_status=before, to_sub_status=app.sub_status,
                next_action=app.next_action, notes=f"Offer expired: {reason}", reason=reason, changed_by_id=None,
            )
        )  # fmt: skip
        for person_id, url in ((app.counselor_id, COUNSELOR_URL), (app.student_id, STUDENT_URL)):
            person = await db.get(User, person_id) if person_id else None
            if person is not None and person.active:
                await agency_notices.notify(db, [person], "Offer expired", f"{reason}.", url)
        await agency_notices.offer_changed(db, app, None, "Offer expired")
    await db.commit()
    logger.info("offers_expired", extra={"extra_fields": {"day": today.isoformat(), "count": len(rows)}})
    return len(rows)


async def run_offer_expiry() -> int:
    """The beat task's entry point: its own session, today's India date."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await expire_offers(db, datetime.now(UTC).astimezone(INDIA).date())


def summary(offer: ApplicationOffer) -> str:
    """The history note: type, dates and conditions (amounts stay on the offer row)."""
    text = f"{TYPE_LABELS[offer.offer_type]}, issued {offer.issue_date.isoformat()}"
    if offer.offer_deadline:
        text += f", deadline {offer.offer_deadline.isoformat()}"
    return text + (f". Conditions: {offer.conditions}" if offer.conditions else ".")


_Recorder = aliased(User)
_Closer = aliased(User)
_Decider = aliased(User)


def money(value) -> str | None:
    return f"{value:.2f}" if value is not None else None


async def views(db: AsyncSession, application_id, *, offer_id=None) -> list[dict]:
    """The application's offers (or the one `offer_id`), newest first, with the recorder's and closer's names, the letter's id and
    name -- never `file_url` (the audited download route presigns it) -- and ccrm-024's conditions with their summary."""
    clause = ApplicationOffer.application_id == application_id if offer_id is None else ApplicationOffer.id == offer_id
    rows = (
        await db.execute(
            select(ApplicationOffer, _Recorder.full_name, _Closer.full_name, StudentDocument, _Decider.full_name)
            .outerjoin(_Recorder, _Recorder.id == ApplicationOffer.recorded_by_id)
            .outerjoin(_Closer, _Closer.id == ApplicationOffer.closed_by_id)
            .outerjoin(_Decider, _Decider.id == ApplicationOffer.decided_by_id)
            .outerjoin(StudentDocument, StudentDocument.id == ApplicationOffer.offer_document_id)
            .where(clause)
            .order_by(ApplicationOffer.created_at.desc(), ApplicationOffer.id.desc())
        )
    ).all()
    conditions = await offer_conditions.views(db, [offer.id for offer, *_ in rows])
    return [
        view(offer, recorder, closer, document, decider) | {"condition_items": conditions[offer.id], "conditions_summary": offer_conditions.summary(conditions[offer.id])}
        for offer, recorder, closer, document, decider in rows
    ]


def document_view(document: StudentDocument) -> dict:
    return {"id": document.id, "name": document.document_label or document.original_filename or document.document_type}


def view(offer: ApplicationOffer, recorder: str | None, closer: str | None, document: StudentDocument | None, decider: str | None) -> dict:
    return {
        "id": offer.id,
        "offer_type": offer.offer_type,
        "offer_type_label": TYPE_LABELS[offer.offer_type],
        "issue_date": offer.issue_date,
        "offer_deadline": offer.offer_deadline,
        "conditions": offer.conditions,
        "currency": offer.currency,
        "tuition_amount": money(offer.tuition_amount),
        "scholarship_amount": money(offer.scholarship_amount),
        "deposit_amount": money(offer.deposit_amount),
        "deposit_deadline": offer.deposit_deadline,
        "document": document_view(document) if document else None,
        "status": offer.status,
        "status_reason": offer.status_reason,
        "recorded_by": recorder,
        "recorded_at": offer.created_at,
        "closed_by": closer,
        "closed_at": offer.closed_at,
        "decision": offer.decision,
        "decision_label": DECISION_LABELS[offer.decision],
        "decision_date": offer.decision_date,
        "decided_by": decider,
    }
