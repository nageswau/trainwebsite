"""pob-018 (DEC-SCOPE-428, spec docs/superpowers/specs/2026-11-08-pob-018-source-attribution-outreach-design.md): where a candidate came
from and when (A2/A3), when the details were last checked (A6), how far outreach has got and -- while `consented` -- how and when the
candidate agreed to be represented (A4/A5), and whether they may be put forward to a client (A7).

Functions only; nothing here commits -- the route owns the transaction. Audit rows and logs carry ids, statuses and the method, never the
note, the referrer's name or the reference."""

import logging
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BdmOrganization, Candidate, Company, User
from app.schemas import CandidateOutreachIn
from app.services import candidates, institution_pool, recruiter_companies

logger = logging.getLogger("app.candidates")

ATTRIBUTION = ("source_date", "referrer_name", "referrer_candidate_id", "vendor_id", "portal_import_reference")
IST = ZoneInfo("Asia/Kolkata")
NO_VENDOR = "Choose an active vendor from your companies"
NO_REFERRER = "Choose another candidate from the pool as the referrer"


# --- A3 the links -------------------------------------------------------------------------------------------------------------------
async def check_links(db: AsyncSession, user: User, candidate_id: UUID | None, values: dict) -> None:
    """The sent (non-null) referrer must be another pool candidate the caller can see; the vendor a live vendor company in the caller's
    company scope. One message per link whatever the reason, so the check never tells whether a record exists."""
    referrer_id = values.get("referrer_candidate_id")
    if referrer_id is not None:
        visible = await db.scalar(select(Candidate.id).where(Candidate.id == referrer_id, Candidate.archived_at.is_(None), *candidates.pool_filter(user.id)))
        if visible is None or referrer_id == candidate_id:
            raise HTTPException(422, NO_REFERRER)
    vendor_id = values.get("vendor_id")
    if vendor_id is not None:
        scope = await recruiter_companies.caller_scope(db, user)
        found = await db.scalar(select(Company.id).where(Company.id == vendor_id, Company.archived_at.is_(None), recruiter_companies.VENDOR_COMPANY, *scope))
        if found is None:
            raise HTTPException(422, NO_VENDOR)


# --- A6 verify ----------------------------------------------------------------------------------------------------------------------
def verify(db: AsyncSession, user: User, candidate: Candidate) -> None:
    if candidate.archived_at is not None:
        raise HTTPException(409, candidates.ARCHIVED)
    candidate.last_verified_on = datetime.now(IST).date()
    candidate.last_verified_by_user_id = user.id
    candidate.updated_by_user_id = user.id
    candidates.audit(db, user, "verify", candidate, {"on": candidate.last_verified_on.isoformat()})


# --- A4/A5 outreach -----------------------------------------------------------------------------------------------------------------
def set_outreach(db: AsyncSession, user: User, candidate: Candidate, body: CandidateOutreachIn) -> bool:
    """Any move; leaving `consented` withdraws the permission (the audit row keeps what it was). The same status and permission is a
    no-op (False, nothing written)."""
    if candidate.archived_at is not None:
        raise HTTPException(409, candidates.ARCHIVED)
    permission = (body.method, body.given_on, body.note)
    stored = (candidate.outreach_permission_method, candidate.outreach_permission_on, candidate.outreach_permission_note)
    if body.status == candidate.outreach_status and permission == stored:
        return False
    before = candidate.outreach_status
    consented = body.status == "consented"
    candidate.outreach_status = body.status
    candidate.outreach_status_changed_at = datetime.now(UTC)
    candidate.outreach_permission_method, candidate.outreach_permission_on, candidate.outreach_permission_note = permission
    candidate.outreach_permission_by_user_id = user.id if consented else None
    candidate.updated_by_user_id = user.id
    metadata = {"from": before, "to": body.status}
    if consented:
        metadata |= {"method": body.method, "given_on": body.given_on.isoformat()}
    candidates.audit(db, user, "outreach", candidate, metadata)
    return True


# --- A7 may be put forward ----------------------------------------------------------------------------------------------------------
def permitted(candidate: Candidate) -> bool:
    """A recorded permission, the candidate's own opt-in (student, portal, website), or an institution's permission (pob-014 governs)."""
    return candidate.outreach_status == "consented" or candidate.opted_in or candidate.institution_permission_id is not None


# --- A10 output ---------------------------------------------------------------------------------------------------------------------
async def out(db: AsyncSession, user: User, candidate: Candidate) -> dict:
    referrer = None
    if candidate.referrer_candidate_id is not None:
        row = await db.scalar(select(Candidate).where(Candidate.id == candidate.referrer_candidate_id, *candidates.pool_filter(user.id)))
        referrer = {"id": row.id, "candidate_code": row.candidate_code, "name": row.name} if row else {"id": None, "candidate_code": None, "name": institution_pool.RESTRICTED_NAME}
    vendor = await db.get(Company, candidate.vendor_id) if candidate.vendor_id else None
    institution = await db.get(BdmOrganization, candidate.institution_org_id) if candidate.institution_org_id else None
    ids = {candidate.last_verified_by_user_id, candidate.outreach_permission_by_user_id} - {None}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids else {}
    permission = None
    if candidate.outreach_status == "consented":
        permission = {"method": candidate.outreach_permission_method, "given_on": candidate.outreach_permission_on, "note": candidate.outreach_permission_note,
                      "recorded_by": candidates._person(people.get(candidate.outreach_permission_by_user_id))}  # fmt: skip
    return {
        "source_date": candidate.source_date, "referrer_name": candidate.referrer_name, "referrer": referrer,
        "vendor": {"id": vendor.id, "name": vendor.name} if vendor else None,
        "institution": {"id": institution.id, "name": institution.name} if institution else None,
        "portal_import_reference": candidate.portal_import_reference, "last_verified_on": candidate.last_verified_on,
        "last_verified_by": candidates._person(people.get(candidate.last_verified_by_user_id)), "outreach_status": candidate.outreach_status,
        "outreach_status_changed_at": candidate.outreach_status_changed_at, "permission": permission, "permitted": permitted(candidate),
    }  # fmt: skip
