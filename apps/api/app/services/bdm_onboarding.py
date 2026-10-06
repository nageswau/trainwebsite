"""bdm-018 (DEC-SCOPE-079, spec §5): the school onboarding handover -- request rules, resolution, queue and output.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Lock order is always organization -> request
-> school (spec §5). Audit metadata and logs carry ids only, never the note, the reason or any name."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, BdmMou, BdmOnboardingRequest, BdmOrganization, BdmOrganizationContact, School, User
from app.services import bdm_mous
from app.services import bdm_organizations as org_svc
from app.services.bdm import person_ref
from app.services.bdm_pipeline import LOST_CONFLICT

SCHOOL = "school"
QUALIFYING_MOU = ("signed", "active")  # H6: bdm-005's effective status, so an Expired MoU does not qualify
ADMIN_ROLES = ("overseas_admin", "super_admin")
ADMIN_ONLY = "Overseas Admin role required"
ADMIN_URL = "/overseas/admin/schools"
NOT_SCHOOL = "Onboarding requests are for School organizations"
MOU_NOT_SIGNED = "The MoU must be Signed or Active to request onboarding"
NOT_FOUND = "Onboarding request not found"
SCHOOL_NOT_FOUND = "No School has that School ID"
REQUEST_PENDING = {"message": "This organization already has an onboarding request waiting", "code": "request_pending"}
ALREADY_LINKED = {"message": "This organization is already linked to a School", "code": "already_linked"}
REQUEST_RESOLVED = {"message": "This request was already resolved", "code": "request_resolved"}
SCHOOL_LINKED = {"message": "This School is already linked to another organization", "code": "school_linked"}


def require_admin(user: User) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, ADMIN_ONLY)


async def _mou_qualifies(db: AsyncSession, org: BdmOrganization) -> bool:
    mou = await bdm_mous.load_current(db, org)
    return mou is not None and bdm_mous.effective_status(mou, bdm_mous.today()) in QUALIFYING_MOU


async def _pending(db: AsyncSession, org_id: UUID) -> BdmOnboardingRequest | None:
    return await db.scalar(select(BdmOnboardingRequest).where(BdmOnboardingRequest.organization_id == org_id, BdmOnboardingRequest.status == "pending"))


async def check_request(db: AsyncSession, org: BdmOrganization) -> None:
    """Spec §5.1 after `require(can_edit)`: not a School organization 422, Lost 409, linked 409, pending 409, MoU 422."""
    if org.bdm_type != SCHOOL:
        raise HTTPException(422, NOT_SCHOOL)
    if org.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)
    if org.school_id is not None:
        raise HTTPException(409, ALREADY_LINKED)
    if await _pending(db, org.id) is not None:
        raise HTTPException(409, REQUEST_PENDING)
    if not await _mou_qualifies(db, org):
        raise HTTPException(422, MOU_NOT_SIGNED)


async def add_request(db: AsyncSession, user: User, org: BdmOrganization, note: str | None) -> BdmOnboardingRequest:
    request = BdmOnboardingRequest(organization_id=org.id, requested_by_user_id=user.id, note=note)
    db.add(request)
    try:
        await db.flush()
    except IntegrityError:  # the pending index under a race the lock did not cover
        await db.rollback()
        raise HTTPException(409, REQUEST_PENDING) from None
    org_svc.audit(db, user, "onboarding_requested", org.id, {"request_id": str(request.id)})
    return request


async def overseas_admins(db: AsyncSession) -> list[User]:
    return list((await db.scalars(select(User).where(User.role == "overseas_admin", User.active.is_(True)))).all())


async def org_onboarding_out(db: AsyncSession, user: User, org: BdmOrganization) -> dict | None:
    """Spec §5.7: null unless a School organization; the latest request, the linked School and whether this caller may request."""
    if org.bdm_type != SCHOOL:
        return None
    latest = await db.scalar(select(BdmOnboardingRequest).where(BdmOnboardingRequest.organization_id == org.id).order_by(BdmOnboardingRequest.created_at.desc()).limit(1))
    school = await db.get(School, org.school_id) if org.school_id else None
    can_request = org_svc.permissions(user, org)["can_edit"] and org.lost_at is None and school is None and (latest is None or latest.status != "pending") and await _mou_qualifies(db, org)
    return {
        "request": None if latest is None else {k: getattr(latest, k) for k in ("id", "status", "created_at", "resolved_at", "reject_reason")},
        "school": None if school is None else {"name": school.name, "school_code": school.school_code},
        "can_request": can_request,
    }


async def lock_pending(db: AsyncSession, request_id: UUID) -> tuple[BdmOnboardingRequest, BdmOrganization]:
    """The organization row, then the request row, both locked; refuses a resolved request or an already-linked organization."""
    organization_id = await db.scalar(select(BdmOnboardingRequest.organization_id).where(BdmOnboardingRequest.id == request_id))
    if organization_id is None:
        raise HTTPException(404, NOT_FOUND)
    lock = {"populate_existing": True}
    org = await db.scalar(select(BdmOrganization).where(BdmOrganization.id == organization_id).with_for_update().execution_options(**lock))
    request = await db.scalar(select(BdmOnboardingRequest).where(BdmOnboardingRequest.id == request_id).with_for_update().execution_options(**lock))
    if request.status != "pending":
        raise HTTPException(409, REQUEST_RESOLVED)
    if org.school_id is not None:
        raise HTTPException(409, ALREADY_LINKED)
    return request, org


async def school_by_code(db: AsyncSession, code: str) -> School:
    """The School to link, locked, and not linked to any organization yet (one organization <-> at most one School)."""
    school = await db.scalar(select(School).where(School.school_code == code.upper()).with_for_update())
    if school is None:
        raise HTTPException(422, SCHOOL_NOT_FOUND)
    if await db.scalar(select(BdmOrganization.id).where(BdmOrganization.school_id == school.id)) is not None:
        raise HTTPException(409, SCHOOL_LINKED)
    return school


def _resolve(db: AsyncSession, user: User, request: BdmOnboardingRequest, action: str, metadata: dict) -> None:
    request.resolved_by_user_id = user.id
    request.resolved_at = datetime.now(UTC)
    db.add(AuditLog(user_id=user.id, action=f"bdm_onboarding_request.{action}", entity_type="bdm_onboarding_request", entity_id=str(request.id), metadata_json=metadata))


async def complete(db: AsyncSession, user: User, request: BdmOnboardingRequest, org: BdmOrganization, school: School, resolution: str) -> None:
    """Links both ways in the caller's transaction (AC2): the organization's `school_id` and the request's School."""
    request.status, request.resolution, request.school_id = "completed", resolution, school.id
    org.school_id = school.id
    _resolve(db, user, request, resolution, {"organization_id": str(org.id), "school_id": str(school.id)})
    try:
        await db.flush()
    except IntegrityError:  # uq_bdm_organizations_school: the School was linked meanwhile
        await db.rollback()
        raise HTTPException(409, SCHOOL_LINKED) from None


def reject(db: AsyncSession, user: User, request: BdmOnboardingRequest, reason: str) -> None:
    request.status, request.reject_reason = "rejected", reason
    _resolve(db, user, request, "rejected", {"organization_id": str(request.organization_id)})


def outcome_notice(org: BdmOrganization, request: BdmOnboardingRequest, school: School | None) -> tuple[str, str]:
    """H7: the in-app notice for the organization's assigned BDM."""
    if school is not None:
        return "School onboarded", f"{org.code} · {org.name} is now linked to {school.name} ({school.school_code})."
    return "School onboarding not approved", f"{org.code} · {org.name}: {request.reject_reason}"


async def queue_page(db: AsyncSession, status: str, limit: int, offset: int) -> dict:
    """Spec §5.2: pending oldest first (a queue), resolved newest first. Each related table is read once per page."""
    where = BdmOnboardingRequest.status == status
    total = await db.scalar(select(func.count()).select_from(BdmOnboardingRequest).where(where))
    order = BdmOnboardingRequest.created_at.asc() if status == "pending" else BdmOnboardingRequest.resolved_at.desc()
    requests = list((await db.scalars(select(BdmOnboardingRequest).where(where).order_by(order, BdmOnboardingRequest.id).limit(limit).offset(offset))).all())
    return {"items": await items_out(db, requests), "total": total or 0, "limit": limit, "offset": offset}


async def items_out(db: AsyncSession, requests: list[BdmOnboardingRequest]) -> list[dict]:
    if not requests:
        return []
    org_ids = {r.organization_id for r in requests}
    orgs = {o.id: o for o in (await db.scalars(select(BdmOrganization).where(BdmOrganization.id.in_(org_ids)))).all()}
    user_ids = {r.requested_by_user_id for r in requests} | {o.assigned_bdm_user_id for o in orgs.values()}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()}
    contacts = {c.organization_id: c for c in (await db.scalars(select(BdmOrganizationContact).where(BdmOrganizationContact.organization_id.in_(org_ids), BdmOrganizationContact.is_primary))).all()}
    mous = {m.organization_id: m for m in (await db.scalars(select(BdmMou).where(BdmMou.organization_id.in_(org_ids), BdmMou.is_current.is_(True)))).all()}
    school_ids = {r.school_id for r in requests if r.school_id}
    schools = {s.id: s for s in (await db.scalars(select(School).where(School.id.in_(school_ids)))).all()} if school_ids else {}

    def one(r: BdmOnboardingRequest) -> dict:
        org, contact, mou, school = orgs[r.organization_id], contacts.get(r.organization_id), mous.get(r.organization_id), schools.get(r.school_id)
        return {
            **{k: getattr(r, k) for k in ("id", "status", "note", "created_at", "resolved_at", "resolution", "reject_reason")},
            "requested_by": person_ref(people[r.requested_by_user_id]),
            "assigned_bdm": person_ref(people[org.assigned_bdm_user_id]),
            "organization": {k: getattr(org, k) for k in ("id", "code", "name", "city", "state", "address", "phone", "email", "website", "board", "grade_from", "grade_to")},
            "primary_contact": None if contact is None else {"name": contact.name, "email": contact.email, "phone": contact.phone},
            "mou": None if mou is None else {"reference": mou.reference, "signed_on": mou.signed_on},
            "school": None if school is None else {"id": school.id, "name": school.name, "school_code": school.school_code},
        }

    return [one(r) for r in requests]


def log(event: str, user: User, request: BdmOnboardingRequest, **extra) -> None:
    org_svc.log(event, user, request.organization_id, request_id=str(request.id), **extra)
