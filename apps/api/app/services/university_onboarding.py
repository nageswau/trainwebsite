"""upc-027 (DEC-SCOPE-167, spec §3): a university's partner onboarding checklist (§29).

Functions only; nothing here commits -- the route owns the transaction. Rows are sparse (OB2): onboarding has started once the
university has a signed agreement, and an item without a row is Not Started. The overall status and the automatic course item (OB7) are
computed on read. Completing all ten moves the university to Partner Activated, forward only (OB8 / Q-27). Audit metadata carries kinds,
field names and statuses only, never the note."""

from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OverseasCourse, University, UniversityAgreement, UniversityOnboardingItem, User
from app.partnership_milestones import SIGNED_STATUSES
from app.partnership_onboarding import ACTIVATION_STAGE, AUTO_ITEM, COMPLETED, ITEMS
from app.schemas import UniversityOnboardingUpdate
from app.services import partnership_pipeline as pipeline
from app.services import partnership_tasks
from app.services import partnership_universities as unis
from app.services.bdm_travel import india_today
from app.services.telecaller import person_ref
from app.services.university_agreements import SIGNATORY_ROLES

NOT_STARTED = {"message": "Onboarding starts when an agreement is signed", "code": "onboarding_not_started"}
OWNER_INVALID = "Choose an active partnership manager, head or super admin"
ACTIVATION_NOTE = "Advanced by onboarding completed"


async def _started_on(db: AsyncSession, university_id: UUID):
    """OB2/OB6: the first signed agreement's date (the later of its two signatures, as upc-008 MS4), or None before any signing."""
    signed_on = func.greatest(UniversityAgreement.edusphere_signed_on, UniversityAgreement.university_signed_on)
    stmt = select(func.min(signed_on)).where(UniversityAgreement.university_id == university_id, UniversityAgreement.status.in_(SIGNED_STATUSES))
    return await db.scalar(stmt)


async def _has_active_course(db: AsyncSession, university_id: UUID) -> bool:
    return bool(await db.scalar(select(exists().where(OverseasCourse.university_id == university_id, OverseasCourse.active.is_(True)))))


async def _rows(db: AsyncSession, university_id: UUID) -> dict[str, UniversityOnboardingItem]:
    stmt = select(UniversityOnboardingItem).where(UniversityOnboardingItem.university_id == university_id)
    return {r.kind: r for r in (await db.scalars(stmt)).all()}


async def _owners(db: AsyncSession, rows: dict[str, UniversityOnboardingItem]) -> dict[UUID, User]:
    ids = {r.owner_user_id for r in rows.values() if r.owner_user_id}
    return {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids else {}


def _items(rows: dict[str, UniversityOnboardingItem], owners: dict[UUID, User], auto: bool) -> list[dict]:
    items = []
    for i in ITEMS:
        row = rows.get(i.key)
        stored = row.status if row else "not_started"
        automatic = i.key == AUTO_ITEM and auto and stored != COMPLETED  # OB7: a stored Completed stays the manual one
        owner = owners.get(row.owner_user_id) if row and row.owner_user_id else None
        items.append({
            "kind": i.key, "label": i.label, "status": COMPLETED if automatic else stored,
            "completed_by": "auto" if automatic else "manual" if stored == COMPLETED else None,
            "completed_on": row.completed_on if row and not automatic else None,
            "owner": person_ref(owner) if owner else None,
            "due_date": row.due_date if row else None, "note": row.note if row else None,
        })  # fmt: skip
    return items


def _overall(items: list[dict]) -> str:
    """OB6: Completed when all ten are; Not Started when none has moved; otherwise In Progress."""
    statuses = {i["status"] for i in items}
    return COMPLETED if statuses == {COMPLETED} else "not_started" if statuses == {"not_started"} else "in_progress"


async def page(db: AsyncSession, uni: University, can_edit: bool) -> dict:
    """`can_edit` is the caller's scope rule; it is also false before signing and while the university is Lost (OB3, OB9)."""
    started_on = await _started_on(db, uni.id)
    rows = await _rows(db, uni.id)
    items = _items(rows, await _owners(db, rows), await _has_active_course(db, uni.id))
    return {
        "started": started_on is not None, "started_on": started_on, "status": _overall(items),
        "completed_count": sum(i["status"] == COMPLETED for i in items), "items": items,
        "can_edit": can_edit and started_on is not None and uni.lost_at is None,
    }  # fmt: skip


async def _check_owner(db: AsyncSession, owner_id: UUID) -> None:
    owner = await db.get(User, owner_id)
    if owner is None or not owner.active or owner.role not in SIGNATORY_ROLES:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "owner_user_id"), "msg": OWNER_INVALID, "input": str(owner_id)}])


async def update(db: AsyncSession, user: User, uni: University, kind: str, payload: UniversityOnboardingUpdate) -> dict | None:
    """On the university row the route has locked after `can_edit_timeline` (so the select-then-insert cannot race;
    uq_university_onboarding_items_kind is the backstop). Returns the audit metadata, or None when nothing changed."""
    if await _started_on(db, uni.id) is None:
        raise HTTPException(409, NOT_STARTED)
    if uni.lost_at is not None:
        raise HTTPException(409, pipeline.LOST_CONFLICT)
    changes = payload.model_dump(include=payload.model_fields_set)
    if changes.get("owner_user_id") is not None:
        await _check_owner(db, changes["owner_user_id"])
    row = (await _rows(db, uni.id)).get(kind)
    old = {field: getattr(row, field) if row else ("not_started" if field == "status" else None) for field in changes}
    changed = sorted(field for field, value in changes.items() if old[field] != value)
    if not changed:
        return None
    if row is None:
        row = UniversityOnboardingItem(university_id=uni.id, kind=kind, status="not_started", updated_by_user_id=user.id)
        db.add(row)
    for field in changed:
        setattr(row, field, changes[field])
    if "status" in changed:  # OB4: the server dates a completion and clears it when the item leaves Completed
        row.completed_on = india_today() if row.status == COMPLETED else None
    row.updated_by_user_id = user.id
    metadata: dict = {"kind": kind, "fields": changed}
    if "status" in changed:
        metadata["status"] = {"from": old["status"], "to": changes["status"]}
    return metadata


async def activate_if_complete(db: AsyncSession, user: User, uni: University) -> bool:
    """OB8 / Q-27 on the locked university: when every item is effectively Completed, move it forward to Partner Activated (one stage
    history row, the upc-020 auto-task rule, one audit row). A no-op before signing, while Lost and at or past the stage. Called by the
    onboarding PATCH and by the course writes (OB7 can complete the last item)."""
    if uni.lost_at is not None or await _started_on(db, uni.id) is None:
        return False
    await db.flush()  # the caller's pending item / course changes take part in the check
    rows = await _rows(db, uni.id)
    if _overall(_items(rows, {}, await _has_active_course(db, uni.id))) != COMPLETED:
        return False
    from_stage = pipeline.advance_to(db, user, uni, ACTIVATION_STAGE, ACTIVATION_NOTE)
    if from_stage is None:
        return False
    await partnership_tasks.on_stage_entered(db, user, uni)
    unis.audit(db, user, "onboarding_completed", uni.id, {"from_stage": from_stage})
    return True
