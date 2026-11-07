"""pob-014 (DEC-SCOPE-425, API §12LR): a college's institution data permissions and the student pool they cover.

Every `{org_id}` resolves through pob-013's `college_placement.load` (out of scope = 404, a role without college access = 403). Only a
placement manager or super_admin writes a permission (S4); each write is one transaction with its audit row (ids and field names only).
The pool lists only the students the caller may see now (`candidates.pool_filter(user.id)`, S6). Mounted on recruiter_drives.router."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, BdmMou, BdmOrganization, Candidate, InstitutionDataPermission, InstitutionDataPermissionUser, JobApplication, User
from app.schemas import InstitutionPermissionIn, InstitutionPermissionUpdate
from app.services import candidates as candidate_svc
from app.services import college_placement as colleges
from app.services import institution_pool as pool
from app.services.recruiter import MANAGER_ROLE

logger = get_logger("app.recruiter")
router = APIRouter(prefix="/colleges", tags=["recruiter-colleges"])
P, PU = InstitutionDataPermission, InstitutionDataPermissionUser
MANAGERS = frozenset({MANAGER_ROLE, "super_admin"})
NOT_FOUND = "Permission not found"
MANAGE_REFUSAL = "Only a placement manager can record institution data permissions"
REVOKED = "This permission was revoked"
BAD_MOU = "Choose one of this college's MoUs"
BAD_USERS = "Each listed person must be an active user who can view candidates"
BAD_WINDOW = "The expiry date must be on or after the start date"


async def _managed(db: AsyncSession, user: User, org_id: UUID) -> BdmOrganization:
    """Scope (404), then role (403, logged), then state (409) -- pob-013's order. The college row is locked: one write at a time."""
    org = await colleges.load(db, user, org_id, lock=True)
    if user.role not in MANAGERS:
        logger.warning("institution_permission_refused", extra={"extra_fields": {"actor_id": str(user.id), "org_id": str(org.id)}})
        raise HTTPException(403, MANAGE_REFUSAL)
    if org.archived_at is not None:
        raise HTTPException(409, colleges.ARCHIVED)
    return org


async def _check(db: AsyncSession, org_id: UUID, values: dict) -> None:
    if values.get("mou_id") and await db.scalar(select(BdmMou.id).where(BdmMou.id == values["mou_id"], BdmMou.organization_id == org_id)) is None:
        raise HTTPException(422, BAD_MOU)
    if "user_ids" in values:
        found = await db.scalar(select(func.count()).select_from(User).where(User.id.in_(values["user_ids"]), User.active.is_(True), User.role.in_(candidate_svc.READERS)))
        if found != len(values["user_ids"]):
            raise HTTPException(422, BAD_USERS)


def _set_users(db: AsyncSession, permission_id: UUID, user_ids, actor: User) -> None:
    db.add_all(PU(permission_id=permission_id, user_id=uid, added_by_user_id=actor.id) for uid in user_ids)


def _audit(db: AsyncSession, user: User, action: str, permission: InstitutionDataPermission, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=f"institution_permission.{action}", entity_type="institution_data_permission", entity_id=str(permission.id),
                    metadata_json={"organization_id": str(permission.organization_id), **metadata}))  # fmt: skip


async def _out(db: AsyncSession, permissions: list[InstitutionDataPermission]) -> list[dict]:
    """Each permission with its state, its listed people and how many students it covers (a count, never a name)."""
    ids = [p.id for p in permissions]
    if not ids:
        return []
    states = dict((await db.execute(select(P.id, pool.status()).where(P.id.in_(ids)))).all())
    people: dict[UUID, list] = {i: [] for i in ids}
    for permission_id, uid, name in (
        await db.execute(select(PU.permission_id, User.id, User.full_name).join(User, User.id == PU.user_id).where(PU.permission_id.in_(ids)).order_by(User.full_name))
    ).all():
        people[permission_id].append({"id": uid, "full_name": name})
    counts = dict((await db.execute(select(Candidate.institution_permission_id, func.count()).where(Candidate.institution_permission_id.in_(ids)).group_by(Candidate.institution_permission_id))).all())
    keys = ("id", "agreement_reference", "mou_id", "purposes", "valid_from", "expires_on", "notes", "created_at", "revoked_at")
    return [{**{k: getattr(p, k) for k in keys}, "status": states[p.id], "users": people[p.id], "student_count": counts.get(p.id, 0)} for p in permissions]


async def _respond(db: AsyncSession, permission: InstitutionDataPermission) -> dict:
    await db.refresh(permission)
    return {"permission": (await _out(db, [permission]))[0]}


@router.get("/{org_id}/student-pool")
async def student_pool(
    org_id: UUID,
    permission_id: UUID | None = None,
    pass_out_year: int | None = Query(None, ge=2000, le=2100),
    course: str | None = Query(None, max_length=120),
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """S10: the permissions the caller may see (a manager: all of the college's; others: those listing them) and a page of the students
    the caller may see now, each with the status of their latest application as the placement status."""
    org = await colleges.load(db, user, org_id)
    manages = user.role in MANAGERS
    shown = select(P).where(P.organization_id == org.id)
    if not manages:
        shown = shown.where(P.id.in_(select(PU.permission_id).where(PU.user_id == user.id)))
    permissions = (await db.scalars(shown.order_by(P.created_at.desc(), P.id))).all()
    filters = [Candidate.institution_org_id == org.id, *candidate_svc.pool_filter(user.id), Candidate.archived_at.is_(None)]
    if permission_id:
        filters.append(Candidate.institution_permission_id == permission_id)
    if pass_out_year is not None:
        filters.append(Candidate.passing_year == pass_out_year)
    filters += _matching(like_pattern(course), Candidate.qualification)
    filters += _matching(like_pattern(q), Candidate.name, Candidate.candidate_code)
    total = await db.scalar(select(func.count()).select_from(Candidate).where(*filters))
    latest = (
        select(JobApplication.status).where(JobApplication.candidate_id == Candidate.id)
        .order_by(JobApplication.updated_at.desc(), JobApplication.id.desc()).limit(1).correlate(Candidate).scalar_subquery()
    )  # fmt: skip
    rows = (await db.execute(select(Candidate, latest).where(*filters).order_by(Candidate.name, Candidate.id).limit(limit).offset(offset))).all()
    items = [
        {"id": c.id, "candidate_code": c.candidate_code, "name": c.name, "passing_year": c.passing_year, "qualification": c.qualification,
         "notice_status": c.institution_notice_status, "permission_id": c.institution_permission_id, "placement_status": status}
        for c, status in rows
    ]  # fmt: skip
    return {
        "college": {"id": org.id, "name": org.name},
        "can_manage": manages and org.archived_at is None,
        "permissions": await _out(db, list(permissions)),
        "students": {"items": items, "total": total or 0, "limit": limit, "offset": offset},
    }


@router.post("/{org_id}/data-permissions", status_code=201)
async def create_permission(org_id: UUID, payload: InstitutionPermissionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await _managed(db, user, org_id)
    values = payload.model_dump()
    await _check(db, org.id, values)
    user_ids = values.pop("user_ids")
    permission = P(organization_id=org.id, created_by_user_id=user.id, **values)
    db.add(permission)
    await db.flush()
    _set_users(db, permission.id, user_ids, user)
    _audit(db, user, "create", permission, {"purposes": permission.purposes, "user_count": len(user_ids)})
    await db.commit()
    logger.info("institution_permission_created", extra={"extra_fields": {"actor_id": str(user.id), "permission_id": str(permission.id)}})
    return await _respond(db, permission)


async def _writable(db: AsyncSession, user: User, org_id: UUID, permission_id: UUID) -> InstitutionDataPermission:
    org = await _managed(db, user, org_id)
    permission = await db.scalar(select(P).where(P.id == permission_id, P.organization_id == org.id).with_for_update())
    if permission is None:
        raise HTTPException(404, NOT_FOUND)
    if permission.revoked_at is not None:
        raise HTTPException(409, REVOKED)
    return permission


@router.patch("/{org_id}/data-permissions/{permission_id}")
async def update_permission(org_id: UUID, permission_id: UUID, payload: InstitutionPermissionUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S4: change the window, purposes, people, reference, MoU or notes. A save with no change writes nothing."""
    permission = await _writable(db, user, org_id, permission_id)
    values = payload.model_dump(exclude_unset=True)
    await _check(db, permission.organization_id, values)
    changed = sorted(k for k, v in values.items() if k != "user_ids" and getattr(permission, k) != v)
    if values.get("expires_on", permission.expires_on) < values.get("valid_from", permission.valid_from):
        raise HTTPException(422, BAD_WINDOW)
    for key in changed:
        setattr(permission, key, values[key])
    if "user_ids" in values:
        current = set((await db.scalars(select(PU.user_id).where(PU.permission_id == permission.id))).all())
        wanted = set(values["user_ids"])
        if wanted != current:
            changed.append("user_ids")
            await db.execute(PU.__table__.delete().where(PU.permission_id == permission.id, PU.user_id.in_(current - wanted)))
            _set_users(db, permission.id, wanted - current, user)
    if changed:
        _audit(db, user, "update", permission, {"fields": sorted(changed)})
    await db.commit()
    return await _respond(db, permission)


@router.post("/{org_id}/data-permissions/{permission_id}/revoke")
async def revoke_permission(org_id: UUID, permission_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S4: final. Its students leave every pool at once."""
    permission = await _writable(db, user, org_id, permission_id)
    permission.revoked_at, permission.revoked_by_user_id = datetime.now(UTC), user.id
    _audit(db, user, "revoke", permission, {})
    await db.commit()
    logger.info("institution_permission_revoked", extra={"extra_fields": {"actor_id": str(user.id), "permission_id": str(permission.id)}})
    return await _respond(db, permission)
