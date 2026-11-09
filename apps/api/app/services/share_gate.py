"""pob-030 (DEC-SCOPE-440 G1-G8, spec docs/superpowers/specs/2026-11-09-pob-030-share-gate-design.md): the one server-side gate every
path that sends a resume or candidate data outward goes through.

Two moments:
- **share** (`request` then `people`): the business purpose (an open requirement), the vendor's standing and signed NDA (pob-011), the
  candidates' consent reference and interest (pob-021), the compensation grant (pob-001), and each candidate's permission to be
  represented (pob-018) and their institution's placement permission (pob-014). The status codes and messages are the ones these
  checks had inside `profile_sharing` before pob-030 (G2), so no client contract moves.
- **delivery** (`deliverable`): a resume or profile that was shared earlier leaves again only while the candidate is still shareable --
  a withdrawn permission or a revoked or lapsed institution permission stops future deliveries; past shares stay logged (G4).

`OUTWARD` is the route inventory: every route that hands candidate data to someone outside the team, with how it is gated. The
route-inventory test fails when a new such route appears without an entry (AC1). Functions only; nothing here commits."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candidate, Company, CompanyDocument, InstitutionDataPermission, Job, User
from app.services import candidate_sourcing, candidates, institution_pool
from app.services import recruiter_contracts as contracts
from app.services import recruiter_requirements as requirements

ENDED = "Profiles cannot be shared for a closed or cancelled requirement"
NOT_IN_POOL = "Choose active candidates from the pool"
NO_PERMISSION = "Record each candidate's permission to be represented (Source and outreach) before sharing"
NO_PLACEMENT_PURPOSE = "Their institution's permission does not cover the placement purpose"
NO_VENDOR = "This requirement did not come through a vendor"
VENDOR_NO_PORTAL = "A vendor has no employer portal. Share by email, WhatsApp or Other"
VENDOR_NOT_ACTIVE = "Profiles can be shared with this vendor only while it is active"
VENDOR_NO_AGREEMENT = "The vendor agreement must be signed or active before sharing profiles with this vendor"
VENDOR_NO_NDA = "Upload the vendor's signed NDA before sharing profiles with it"
CONSENT_MISSING = "Confirm the candidates' consent to this submission and say how and when they gave it"
INTEREST_MISSING = "Confirm the candidates' interest in and availability for this requirement before submitting them"

# G6/AC1: (method, path) -> how the route is gated. "share" = request + people; "delivery" = deliverable() before any resume byte
# leaves; "record" = the summary of a share already made, shown only to the party it went to (G5); "internal" = staff-only inside the
# system, gated by its grant and audited (not a share to a third party).
OUTWARD = {
    ("POST", "/api/v1/recruiter/shares"): "share",  # client, vendor and employer-portal shares
    ("GET", "/api/v1/public/shared-resume/{token}"): "delivery",  # the emailed / WhatsApp resume link
    ("GET", "/api/v1/employer/shared-profiles/{item_id}/resume"): "delivery",
    ("GET", "/api/v1/interviewer/interviews/{interview_id}/resume"): "delivery",  # hrc-029: a panel member's copy
    ("GET", "/api/v1/employer/shared-profiles"): "record",  # rec-019 S8: the R8 summary of the company's portal shares
    ("PATCH", "/api/v1/employer/shared-profiles/{item_id}"): "record",
    ("GET", "/api/v1/interviewer/interviews"): "record",  # hrc-029 V6: what the panel member needs, no contact details
    ("GET", "/api/v1/interviewer/interviews/{interview_id}"): "record",
    ("POST", "/api/v1/recruiter/candidates/search/export"): "internal",  # hrc-020: the candidates.export grant, pob-001 salary columns
    ("GET", "/api/v1/recruiter/candidates/{candidate_id}/resume/{version}"): "internal",  # hrc-015: the pool's readers, audited
    ("GET", "/api/v1/recruiter/candidates/{candidate_id}/resume/{version}/link"): "internal",
    ("POST", "/api/v1/recruiter/candidates/{candidate_id}/resume/{version}/extract"): "internal",  # hrc-017: parse into the record
    ("POST", "/api/v1/recruiter/candidates/{candidate_id}/resume/{version}/apply"): "internal",
}


# --- share ------------------------------------------------------------------------------------------------------------------------------
async def request(db: AsyncSession, user: User, job: Job, payload) -> Company | None:
    """Purpose, recipient, consent and grants, in the order `profile_sharing.create` always refused them; returns the vendor (None for a
    client share). The vendor is read-locked so a concurrent suspension waits for this share's commit."""
    if job.status in requirements.ENDED:
        raise HTTPException(409, ENDED)
    vendor = await _vendor(db, job, payload)
    if not (payload.consent_confirmed and payload.consent_reference):
        raise HTTPException(409, CONSENT_MISSING)
    if not payload.interest_confirmed:
        raise HTTPException(409, INTEREST_MISSING)
    if payload.include_compensation and not await candidates.sees_compensation(db, user):
        raise HTTPException(403, candidates.NO_COMPENSATION)  # pob-021 B9
    return vendor


async def _vendor(db: AsyncSession, job: Job, payload) -> Company | None:
    if payload.recipient == "client":
        return None
    if job.via_vendor_id is None:
        raise HTTPException(422, NO_VENDOR)
    if payload.channel == "portal":
        raise HTTPException(422, VENDOR_NO_PORTAL)
    vendor = await db.scalar(select(Company).where(Company.id == job.via_vendor_id).with_for_update(read=True))
    if vendor.vendor_status != "active":
        raise HTTPException(409, VENDOR_NOT_ACTIVE)
    agreement = await contracts.company_contract_ref(db, vendor, "vendor")
    if agreement is None or agreement["status"] not in ("signed", "active"):
        raise HTTPException(409, VENDOR_NO_AGREEMENT)
    if await db.scalar(select(CompanyDocument.id).where(CompanyDocument.company_id == vendor.id, CompanyDocument.kind == "nda").limit(1)) is None:
        raise HTTPException(409, VENDOR_NO_NDA)
    return vendor


def names(people) -> str:
    return ", ".join(f"{c.name} ({c.candidate_code})" for c in people)


async def people(db: AsyncSession, ids: list[UUID], user: User) -> list[Candidate]:
    """Pool members only, read-locked, in the order chosen. pob-014 S9: an institution's student only while the sharer is on its active
    permission and that permission allows placement; pob-018 A7: each one's permission to be represented. Under FOR SHARE, so a
    concurrent withdrawal or revoke waits for this share's commit."""
    rows = (await db.scalars(select(Candidate).where(Candidate.id.in_(ids), *candidates.pool_filter(user.id)).with_for_update(read=True))).all()
    found = {c.id: c for c in rows}
    archived = [c for c in rows if c.archived_at is not None]
    if len(found) != len(ids) or archived:
        raise HTTPException(422, f"{NOT_IN_POOL}{f': {names(archived)} is archived' if archived else ''}")
    permission_ids = {c.institution_permission_id for c in rows} - {None}
    if permission_ids:
        permissions = (await db.scalars(select(InstitutionDataPermission).where(InstitutionDataPermission.id.in_(permission_ids)).with_for_update(read=True))).all()
        allowed = {p.id for p in permissions if "placement" in p.purposes}
        barred = [c for c in rows if c.institution_permission_id is not None and c.institution_permission_id not in allowed]
        if barred:
            raise HTTPException(422, f"{NO_PLACEMENT_PURPOSE}: {names(barred)}")
    unpermitted = [found[i] for i in ids if not candidate_sourcing.permitted(found[i])]
    if unpermitted:
        raise HTTPException(422, f"{NO_PERMISSION}: {names(unpermitted)}")
    return [found[i] for i in ids]


# --- delivery (G4) ------------------------------------------------------------------------------------------------------------------------
async def deliverable_ids(db: AsyncSession, people) -> set[UUID]:
    """The ids of those whose shared resume may leave again now: still in the pool (not archived or anonymised), still permitted to be
    represented, and -- for an institution's student -- that institution's permission still active and still covering placement. One
    query at most, so a list can flag each row's resume link."""
    open_ = [c for c in people if c.archived_at is None and c.anonymised_at is None and candidate_sourcing.permitted(c)]
    permission_ids = {c.institution_permission_id for c in open_} - {None}
    placement = set()
    if permission_ids:
        P = InstitutionDataPermission
        rows = (await db.execute(select(P.id, P.purposes).where(P.id.in_(permission_ids), institution_pool.active()))).all()
        placement = {pid for pid, purposes in rows if "placement" in purposes}
    return {c.id for c in open_ if c.institution_permission_id is None or c.institution_permission_id in placement}


async def deliverable(db: AsyncSession, candidate: Candidate) -> bool:
    return candidate.id in await deliverable_ids(db, [candidate])
