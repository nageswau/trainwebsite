"""pob-005 (DEC-SCOPE-411 D3-D6): a company contact's outreach status -- the automatic forward moves the activity write paths call, the
manual change, and the Do Not Contact refusal. Its own module because the call, message, meeting and share services all use it and
`recruiter_contacts` already imports some of them. Functions only; nothing here commits -- the caller's transaction (which already holds
the company lock) owns it."""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanyContact, User
from app.services import recruiter_companies as companies

LABELS = {
    "not_contacted": "Not contacted", "contacted": "Contacted", "replied": "Replied", "meeting_scheduled": "Meeting scheduled",
    "not_interested": "Not interested", "do_not_contact": "Do not contact",
}  # fmt: skip
PROGRESSION = ("not_contacted", "contacted", "replied", "meeting_scheduled")  # D4: automatic moves go forward through these only
DO_NOT_CONTACT = "This contact has asked not to be contacted"


def refuse_do_not_contact(contact: CompanyContact) -> None:
    """D6: outreach to a Do Not Contact person is refused server-side (409), whatever the screen offered."""
    if contact.status == "do_not_contact":
        raise HTTPException(409, DO_NOT_CONTACT)


def record(db: AsyncSession, user: User, contact: CompanyContact, to: str, cause: str) -> None:
    """One status change and its audit row (the per-contact timeline reads these). Ids and statuses only."""
    metadata = {"contact_id": str(contact.id), "from": contact.status, "to": to, "cause": cause}
    contact.status = to
    contact.status_changed_at = datetime.now(UTC)
    companies.audit(db, user, "contact_status", contact.company_id, metadata)


async def advance(db: AsyncSession, user: User, contact_ids: Iterable[UUID | None], to: str, cause: str) -> None:
    """D4: move each active contact forward to `to` -- never backwards, never out of Not interested / Do not contact. Every activity write
    path locks the company first, so two writers cannot interleave on one contact."""
    ids = {i for i in contact_ids if i is not None}
    if not ids:
        return
    for contact in await db.scalars(select(CompanyContact).where(CompanyContact.id.in_(ids)).execution_options(populate_existing=True)):
        if contact.active and contact.status in PROGRESSION and PROGRESSION.index(to) > PROGRESSION.index(contact.status):
            record(db, user, contact, to, cause)
    await db.flush()
