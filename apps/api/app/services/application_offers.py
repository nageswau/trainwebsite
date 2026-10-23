"""ccrm-023 (DEC-SCOPE-245): an application's offer records -- the only writer of `application_offers` and of the offer columns
mirrored on `overseas_applications`. Shared by the counselor/admin routes (api/application_offers.py) and the agency PUT/PATCH
(api/agent_applications.py). Nothing here commits: the caller scopes, locks the application row (which serialises every offer write;
the partial unique index backs it), writes history, notifies, audits and commits.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.application_sub_status import SUB_STATUSES
from app.models import ApplicationOffer, OverseasApplication, StudentDocument, User
from app.services.agent_applications import before_offer, check_transition

# The values an offer carries; a request identical to the active offer's is a no-op (a retry is safe).
FIELDS = ("offer_type", "issue_date", "offer_deadline", "conditions", "currency", "tuition_amount", "scholarship_amount", "deposit_amount", "deposit_deadline", "offer_document_id")
TYPE_LABELS = {"conditional": "Conditional", "unconditional": "Unconditional", "pathway": "Pathway", "other": "Other"}
CLOSE_LABELS = {"withdrawn_by_university": "Offer withdrawn by the university", "expired": "Offer expired"}
OFFER_SUB_STATUSES = SUB_STATUSES["offer"]
NOT_ACTIVE = "Only the current offer can be withdrawn or marked expired"
OFFER_NOT_FOUND = "Offer not found"


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


async def record(db: AsyncSession, user: User, app: OverseasApplication, values: dict) -> ApplicationOffer:
    """Supersede the active offer (kept), add the new one and mirror it. The superseded row is flushed first, so the one-active index
    never sees two active rows."""
    previous = await active_offer(db, app)
    if previous is not None:
        previous.status = "superseded"
        await db.flush()
    offer = ApplicationOffer(application_id=app.id, recorded_by_id=user.id, status="active", **{field: values.get(field) for field in FIELDS})
    db.add(offer)
    await db.flush()
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


def close(user: User, app: OverseasApplication, offer: ApplicationOffer, status: str, reason: str) -> None:
    """OF4: close the current offer, clear the mirror and an offer sub-status; the stage stays (forward-only)."""
    offer.status = status
    offer.status_reason = reason
    offer.closed_by_id = user.id
    offer.closed_at = datetime.now(UTC)
    _mirror(app, None)
    if app.sub_status in OFFER_SUB_STATUSES:
        app.sub_status = None


def summary(offer: ApplicationOffer) -> str:
    """The history note: type, dates and conditions (amounts stay on the offer row)."""
    text = f"{TYPE_LABELS[offer.offer_type]}, issued {offer.issue_date.isoformat()}"
    if offer.offer_deadline:
        text += f", deadline {offer.offer_deadline.isoformat()}"
    return text + (f". Conditions: {offer.conditions}" if offer.conditions else ".")


_Recorder = aliased(User)
_Closer = aliased(User)


def _money(value) -> str | None:
    return f"{value:.2f}" if value is not None else None


async def views(db: AsyncSession, application_id, *, offer_id=None) -> list[dict]:
    """The application's offers (or the one `offer_id`), newest first, with the recorder's and closer's names and the letter's id and
    name -- never `file_url` (the audited download route presigns it)."""
    clause = ApplicationOffer.application_id == application_id if offer_id is None else ApplicationOffer.id == offer_id
    rows = (
        await db.execute(
            select(ApplicationOffer, _Recorder.full_name, _Closer.full_name, StudentDocument)
            .outerjoin(_Recorder, _Recorder.id == ApplicationOffer.recorded_by_id)
            .outerjoin(_Closer, _Closer.id == ApplicationOffer.closed_by_id)
            .outerjoin(StudentDocument, StudentDocument.id == ApplicationOffer.offer_document_id)
            .where(clause)
            .order_by(ApplicationOffer.created_at.desc(), ApplicationOffer.id.desc())
        )
    ).all()
    return [view(offer, recorder, closer, document) for offer, recorder, closer, document in rows]


def document_view(document: StudentDocument) -> dict:
    return {"id": document.id, "name": document.document_label or document.original_filename or document.document_type}


def view(offer: ApplicationOffer, recorder: str | None, closer: str | None, document: StudentDocument | None) -> dict:
    return {
        "id": offer.id,
        "offer_type": offer.offer_type,
        "offer_type_label": TYPE_LABELS[offer.offer_type],
        "issue_date": offer.issue_date,
        "offer_deadline": offer.offer_deadline,
        "conditions": offer.conditions,
        "currency": offer.currency,
        "tuition_amount": _money(offer.tuition_amount),
        "scholarship_amount": _money(offer.scholarship_amount),
        "deposit_amount": _money(offer.deposit_amount),
        "deposit_deadline": offer.deposit_deadline,
        "document": document_view(document) if document else None,
        "status": offer.status,
        "status_reason": offer.status_reason,
        "recorded_by": recorder,
        "recorded_at": offer.created_at,
        "closed_by": closer,
        "closed_at": offer.closed_at,
    }
