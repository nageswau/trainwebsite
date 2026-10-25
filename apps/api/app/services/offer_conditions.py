"""ccrm-024 (DEC-SCOPE-261): an offer's conditions -- the only writer of `application_offer_conditions`. Seeded from the offer's text
when an offer is recorded (C1), moved to the re-recorded row when the agency only moves the deadline (C9), otherwise left with their offer
(C3). Nothing here commits: the route (api/application_offers.py) scopes, locks the application row, writes history, notifies, audits and
commits. Spec: docs/superpowers/specs/2026-10-25-ccrm-024-offer-conditions-design.md.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationOffer, ApplicationOfferCondition, OverseasApplication, StudentDocument, User

FIELDS = ("description", "owner", "due_date", "status", "evidence_document_id", "note")
OWNER_LABELS = {"student": "Student", "counselor": "Counselor", "agent": "Agent"}
STATUS_LABELS = {"open": "Open", "met": "Met", "waived": "Waived", "failed": "Failed"}
SATISFIED = {"met", "waived"}
EVIDENCE = "Condition evidence"
NOT_CURRENT = "Conditions can be changed only on the current offer"
CONDITION_NOT_FOUND = "Condition not found"
NEEDS_EVIDENCE = "Attach the evidence before marking the condition met"
NEEDS_NOTE = "Give a note when a condition is waived or failed"
AGENT_ON_DIRECT = "Only an agency application can have a condition owned by the agent"
EVIDENCE_MISMATCH = "Choose condition evidence uploaded for this application"


def seed(db: AsyncSession, user: User, offer: ApplicationOffer) -> None:
    """C1: the offer's conditions text becomes one open condition the student owns."""
    if offer.conditions:
        db.add(ApplicationOfferCondition(offer_id=offer.id, description=offer.conditions, owner="student", status="open", created_by_id=user.id, updated_by_id=user.id))


async def move(db: AsyncSession, previous: ApplicationOffer, offer: ApplicationOffer) -> None:
    """C9: the same university offer re-recorded with a new deadline keeps its conditions."""
    await db.execute(update(ApplicationOfferCondition).where(ApplicationOfferCondition.offer_id == previous.id).values(offer_id=offer.id))


async def check(db: AsyncSession, app: OverseasApplication, values: dict) -> None:
    """The rules on the condition as it will be saved: C6 agent owner, C2 evidence for met, C5 note for waived/failed, C11 evidence."""
    if values["owner"] == "agent" and app.agent_id is None:
        raise HTTPException(422, AGENT_ON_DIRECT)
    if values["evidence_document_id"] is not None:
        document = await db.get(StudentDocument, values["evidence_document_id"])
        if document is None or document.application_id != app.id or document.document_type != EVIDENCE or document.archived_at is not None:
            raise HTTPException(422, EVIDENCE_MISMATCH)
    if values["status"] == "met" and values["evidence_document_id"] is None:
        raise HTTPException(422, NEEDS_EVIDENCE)
    if values["status"] in {"waived", "failed"} and not values["note"]:
        raise HTTPException(422, NEEDS_NOTE)


def values_of(condition: ApplicationOfferCondition) -> dict:
    return {field: getattr(condition, field) for field in FIELDS}


def save(user: User, offer: ApplicationOffer, condition: ApplicationOfferCondition | None, values: dict) -> ApplicationOfferCondition:
    """Create the condition or apply the checked values; a status change is stamped."""
    if condition is None:
        condition = ApplicationOfferCondition(offer_id=offer.id, created_by_id=user.id)
    elif condition.status != values["status"]:
        condition.status_changed_at = datetime.now(UTC)
    for field in FIELDS:
        setattr(condition, field, values[field])
    condition.updated_by_id = user.id
    return condition


def describe(condition: ApplicationOfferCondition, *, added: bool) -> str:
    """The history note."""
    if added:
        due = f", due {condition.due_date.isoformat()}" if condition.due_date else ""
        return f"Offer condition added: {condition.description} (owner {OWNER_LABELS[condition.owner]}{due})."
    return f"Offer condition updated: {condition.description} -- {STATUS_LABELS[condition.status]}."


def summary(items: list[dict]) -> dict:
    """C4: all satisfied once there is at least one condition and every one is met or waived."""
    counts = {status: sum(1 for i in items if i["status"] == status) for status in STATUS_LABELS}
    satisfied = counts["met"] + counts["waived"]
    return {"total": len(items), "satisfied": satisfied, "open": counts["open"], "failed": counts["failed"], "all_satisfied": bool(items) and satisfied == len(items)}


async def views(db: AsyncSession, offer_ids: list) -> dict:
    """{offer_id: [condition view]} oldest first, with the evidence's id and name -- never `file_url`."""
    from app.services.application_offers import document_view  # application_offers imports this module

    grouped: dict = {offer_id: [] for offer_id in offer_ids}
    if not offer_ids:
        return grouped
    rows = await db.execute(
        select(ApplicationOfferCondition, StudentDocument)
        .outerjoin(StudentDocument, StudentDocument.id == ApplicationOfferCondition.evidence_document_id)
        .where(ApplicationOfferCondition.offer_id.in_(offer_ids))
        .order_by(ApplicationOfferCondition.created_at, ApplicationOfferCondition.id)
    )
    for condition, evidence in rows.all():
        grouped[condition.offer_id].append(
            {
                "id": condition.id,
                "description": condition.description,
                "owner": condition.owner,
                "owner_label": OWNER_LABELS[condition.owner],
                "due_date": condition.due_date,
                "status": condition.status,
                "status_label": STATUS_LABELS[condition.status],
                "evidence": document_view(evidence) if evidence else None,
                "note": condition.note,
                "status_changed_at": condition.status_changed_at,
            }
        )
    return grouped
