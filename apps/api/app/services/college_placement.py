"""pob-013 (DEC-SCOPE-410): a college's placement profile, kept by the placement team beside the BDM-owned organization.

Functions only; nothing here commits -- the route owns the transaction. The BDM CRM's own scope (`bdm_organizations.caller_scope`) is
reused for BDM callers but never widened: it gates MoUs, appointments and activities, which stay BDM-only (P13). Out of scope is 404.
Logs and audit rows carry ids and field names, never names, phones or text.
"""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    BdmOrganization,
    BdmOrganizationContact,
    BdmOrgCourse,
    BdmOrgPlacementBatch,
    BdmOrgPlacementEvent,
    BdmOrgPlacementProfile,
    BdmOrgTpoInteraction,
    RecruitmentDrive,
    User,
)
from app.services import bdm_organizations as orgs
from app.services.bdm_pipeline import pipeline_out
from app.services.recruiter import recruiter_context

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "College not found"
ROLE_REFUSAL = "Your role cannot open college placement profiles"
EDIT_REFUSAL = "Only the placement team or the assigned BDM can change the placement profile"
ARCHIVED = "Restore this organization first"
# P2: a college-module college or university; an Agent-module university (an overseas partner) is not a placement institution.
COLLEGES = (BdmOrganization.bdm_type == "college", BdmOrganization.org_type.in_(("college", "university")))
MAX_COURSES, MAX_BATCHES, MAX_EVENTS = 100, 200, 500
INTERACTION_PAGE, DRIVE_PAGE = 50, 20


async def scope(db: AsyncSession, user: User) -> list:
    """P3: the placement team reads every active college; BDM callers keep their bdm-002 scope; any other role is 403."""
    if user.role == "placement_team":
        await recruiter_context(db, user)  # 403 without a recruiter profile, like every recruiter route
        return [*COLLEGES, BdmOrganization.archived_at.is_(None)]
    if user.role == "placement_manager":
        return [*COLLEGES, BdmOrganization.archived_at.is_(None)]
    if user.role in ("bdm", "bdm_manager", "super_admin"):
        return [*COLLEGES, *await orgs.caller_scope(db, user)]
    raise HTTPException(403, ROLE_REFUSAL)


async def load(db: AsyncSession, user: User, org_id: UUID, *, lock: bool = False) -> BdmOrganization:
    """bdm-025's lock order: lock the row by id first, then check scope in a fresh statement."""
    filters = await scope(db, user)
    stmt = select(BdmOrganization).where(BdmOrganization.id == org_id, *filters)
    if lock:
        await db.execute(select(BdmOrganization.id).where(BdmOrganization.id == org_id).with_for_update())
        stmt = stmt.execution_options(populate_existing=True)
    org = await db.scalar(stmt)
    if org is None:
        raise HTTPException(404, NOT_FOUND)
    return org


def _writer(user: User, org: BdmOrganization) -> bool:
    """P4: the placement team, super_admin and the organization's assigned BDM; both managers read only."""
    return user.role in ("placement_team", "super_admin") or (user.role == "bdm" and org.assigned_bdm_user_id == user.id)


def can_edit(user: User, org: BdmOrganization) -> bool:
    return _writer(user, org) and org.archived_at is None


async def editable(db: AsyncSession, user: User, org_id: UUID, route: str) -> BdmOrganization:
    """Scope (404), then role (403, logged), then state (409) -- bdm-002's order (C15)."""
    org = await load(db, user, org_id, lock=True)
    if not _writer(user, org):
        logger.warning("placement_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "org_id": str(org.id), "route": route}})
        raise HTTPException(403, EDIT_REFUSAL)
    if org.archived_at is not None:
        raise HTTPException(409, ARCHIVED)
    return org


async def count(db: AsyncSession, model, org_id: UUID) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(model.organization_id == org_id))


async def owned(db: AsyncSession, model, org_id: UUID, row_id: UUID, message: str):
    """A child row of this organization, else 404 (an id from another organization reads as missing)."""
    row = await db.scalar(select(model).where(model.id == row_id, model.organization_id == org_id))
    if row is None:
        raise HTTPException(404, message)
    return row


def course_key(department: str | None, course: str) -> str:
    return f"{(department or '').casefold()}|{course.casefold()}"


def audit(db: AsyncSession, user: User, action: str, org_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed)."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_organization.placement_{action}", entity_type="bdm_organization", entity_id=str(org_id), metadata_json=metadata or {}))


def log(event: str, user: User, org_id: UUID, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "org_id": str(org_id), **extra}})


def stage_label(org: BdmOrganization) -> str:
    """P12: the bdm-004 stage, read only. The spec's §6.1 status labels are NEEDS_CONFIRMATION, so none are invented here."""
    label = pipeline_out(org)["stage_label"]
    return f"{label} (Lost)" if org.lost_at is not None else label


def _contact(c: BdmOrganizationContact) -> dict:
    keys = ("id", "name", "designation", "role", "phone", "email", "is_primary", "office_details", "preferred_contact_method")
    return {k: getattr(c, k) for k in keys}


async def detail_out(db: AsyncSession, user: User, org: BdmOrganization) -> dict:
    """The placement view every route returns (P13: no MoU, assignment or commercial data). Every list is bounded."""
    oid = org.id
    bdm_name = await db.scalar(select(User.full_name).where(User.id == org.assigned_bdm_user_id))
    profile_row = (
        await db.execute(
            select(BdmOrgPlacementProfile, User.full_name)
            .join(User, User.id == BdmOrgPlacementProfile.updated_by_user_id)
            .where(BdmOrgPlacementProfile.organization_id == oid)
            .execution_options(populate_existing=True)
        )
    ).first()
    profile, editor = profile_row if profile_row else (None, None)
    contacts = await orgs.contacts_of(db, oid)
    courses = (await db.scalars(select(BdmOrgCourse).where(BdmOrgCourse.organization_id == oid).order_by(func.lower(BdmOrgCourse.course), BdmOrgCourse.id))).all()
    batches = (
        await db.execute(
            select(BdmOrgPlacementBatch, BdmOrgCourse.course)
            .outerjoin(BdmOrgCourse, BdmOrgCourse.id == BdmOrgPlacementBatch.course_id)
            .where(BdmOrgPlacementBatch.organization_id == oid)
            .order_by(BdmOrgPlacementBatch.pass_out_year.desc(), BdmOrgPlacementBatch.created_at, BdmOrgPlacementBatch.id)
        )
    ).all()
    events = (await db.scalars(select(BdmOrgPlacementEvent).where(BdmOrgPlacementEvent.organization_id == oid).order_by(BdmOrgPlacementEvent.starts_on, BdmOrgPlacementEvent.id))).all()
    interactions = (
        await db.execute(
            select(BdmOrgTpoInteraction, User.full_name)
            .join(User, User.id == BdmOrgTpoInteraction.logged_by_user_id)
            .where(BdmOrgTpoInteraction.organization_id == oid)
            .order_by(BdmOrgTpoInteraction.occurred_at.desc(), BdmOrgTpoInteraction.id)
            .limit(INTERACTION_PAGE)
        )
    ).all()
    drives = (await db.scalars(select(RecruitmentDrive).where(RecruitmentDrive.college_org_id == oid).order_by(RecruitmentDrive.drive_date.desc(), RecruitmentDrive.id).limit(DRIVE_PAGE))).all()
    return {
        "id": oid, "code": org.code, "name": org.name, "org_type": org.org_type, "city": org.city, "state": org.state, "website": org.website,
        "student_count": org.student_count, "affiliation": org.affiliation, "college_type": org.college_type, "courses_note": org.courses,
        "relationship_stage": stage_label(org), "assigned_bdm_name": bdm_name, "archived": org.archived_at is not None,
        "permissions": {"can_edit": can_edit(user, org)},
        "profile": {
            "drive_process": profile.drive_process if profile else None, "eligibility_rules": profile.eligibility_rules if profile else None,
            "updated_at": profile.updated_at if profile else None, "updated_by_name": editor,
        },
        "contacts": [_contact(c) for c in sorted(contacts, key=lambda c: not c.is_primary)],
        "courses": [{"id": c.id, "department": c.department, "course": c.course} for c in courses],
        "batches": [
            {"id": b.id, "course_id": b.course_id, "course": name, "pass_out_year": b.pass_out_year, "pass_out_date": b.pass_out_date,
             "student_count": b.student_count, "notes": b.notes}
            for b, name in batches
        ],
        "calendar": [{"id": e.id, "title": e.title, "kind": e.kind, "starts_on": e.starts_on, "ends_on": e.ends_on, "notes": e.notes} for e in events],
        "interactions": [
            {"id": i.id, "channel": i.channel, "occurred_at": i.occurred_at, "contact_id": i.contact_id, "contact_name": i.contact_name,
             "summary": i.summary, "next_step": i.next_step, "logged_by_name": name}
            for i, name in interactions
        ],
        "interaction_total": await count(db, BdmOrgTpoInteraction, oid),
        "drives": [{"id": d.id, "drive_code": d.drive_code, "drive_date": d.drive_date, "job_role": d.job_role, "status": d.status} for d in drives],
    }  # fmt: skip
