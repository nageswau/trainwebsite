"""pob-013 (DEC-SCOPE-410, API §12LD): college placement profiles for the placement team, beside the BDM-owned organization.

Every `{org_id}` resolves through `services.college_placement.load` (out of scope = 404). Every write is one transaction -- scope, row
lock on the organization, role (403), archived (409), change, audit, one commit -- and returns the whole placement view. The organization
row itself is never written (P1). Mounted on recruiter_drives.router (prefix /recruiter)."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import (
    BdmOrganization,
    BdmOrganizationContact,
    BdmOrgCourse,
    BdmOrgPlacementBatch,
    BdmOrgPlacementEvent,
    BdmOrgPlacementProfile,
    BdmOrgTpoInteraction,
    User,
)
from app.schemas import (
    PlacementBatchIn,
    PlacementCollegeEnvelope,
    PlacementCollegePage,
    PlacementCourseIn,
    PlacementEventIn,
    PlacementProfileIn,
    TpoContactUpdate,
    TpoInteractionIn,
)
from app.services import bdm_organizations as orgs
from app.services import college_placement as svc

router = APIRouter(prefix="/colleges", tags=["recruiter-colleges"])
COURSE_NOT_FOUND = "Course not found"
FUTURE_SLACK = timedelta(minutes=5)


async def _respond(db: AsyncSession, user: User, org: BdmOrganization) -> dict:
    return {"college": await svc.detail_out(db, user, org)}


async def _unchanged(db: AsyncSession, user: User, org: BdmOrganization) -> dict:
    """A save equal to what is stored: no audit row; the commit only releases the row lock (expire_on_commit=False keeps `org`)."""
    await db.commit()
    return await _respond(db, user, org)


async def _commit(db: AsyncSession, user: User, org: BdmOrganization, action: str, metadata: dict | None = None) -> dict:
    svc.audit(db, user, action, org.id, metadata)
    await db.commit()
    svc.log(f"placement_{action}", user, org.id, **(metadata or {}))
    return await _respond(db, user, org)


async def _at_most(db: AsyncSession, model, org_id: UUID, limit: int, what: str) -> None:
    if await svc.count(db, model, org_id) >= limit:
        raise HTTPException(409, f"A college can have at most {limit} {what}")


@router.get("", response_model=PlacementCollegePage)
async def list_colleges(
    q: str | None = SEARCH,
    city: str | None = Query(None, max_length=120),
    course: str | None = Query(None, max_length=120),
    pass_out_year: int | None = Query(None, ge=2000, le=2100),
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """P11: filters are ANDed with the caller's scope; each is a literal, case-insensitive substring."""
    filters = await svc.scope(db, user)
    filters += _matching(like_pattern(q), BdmOrganization.name, BdmOrganization.code)
    filters += _matching(like_pattern(city), BdmOrganization.city, BdmOrganization.state)
    pattern = like_pattern(course)
    if pattern:
        structured = exists().where(BdmOrgCourse.organization_id == BdmOrganization.id, *_matching(pattern, BdmOrgCourse.course, BdmOrgCourse.department))
        filters.append(structured | BdmOrganization.courses.ilike(pattern, escape="\\"))
    if pass_out_year is not None:
        filters.append(exists().where(BdmOrgPlacementBatch.organization_id == BdmOrganization.id, BdmOrgPlacementBatch.pass_out_year == pass_out_year))
    total = await db.scalar(select(func.count()).select_from(BdmOrganization).where(*filters))
    course_count = select(func.count()).where(BdmOrgCourse.organization_id == BdmOrganization.id).correlate(BdmOrganization).scalar_subquery()
    next_year = (
        select(func.min(BdmOrgPlacementBatch.pass_out_year))
        .where(BdmOrgPlacementBatch.organization_id == BdmOrganization.id, BdmOrgPlacementBatch.pass_out_year >= date.today().year)
        .correlate(BdmOrganization)
        .scalar_subquery()
    )
    stmt = (
        select(BdmOrganization, User.full_name, course_count, next_year)
        .join(User, User.id == BdmOrganization.assigned_bdm_user_id)
        .where(*filters)
        .order_by(BdmOrganization.name, BdmOrganization.id)
        .limit(limit)
        .offset(offset)
    )
    items = [
        {"id": o.id, "code": o.code, "name": o.name, "org_type": o.org_type, "city": o.city, "state": o.state, "assigned_bdm_name": bdm,
         "course_count": courses, "next_pass_out_year": year, "archived": o.archived_at is not None}
        for o, bdm, courses, year in (await db.execute(stmt)).all()
    ]  # fmt: skip
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/{org_id}", response_model=PlacementCollegeEnvelope)
async def get_college(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _respond(db, user, await svc.load(db, user, org_id))


@router.put("/{org_id}/profile", response_model=PlacementCollegeEnvelope)
async def put_profile(org_id: UUID, payload: PlacementProfileIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P5: replaces both texts. A save with no change writes nothing (no audit row)."""
    org = await svc.editable(db, user, org_id, "profile")
    values = payload.model_dump()
    stored = await db.get(BdmOrgPlacementProfile, org.id)
    profile = stored or BdmOrgPlacementProfile(organization_id=org.id)
    changed = sorted(k for k, v in values.items() if getattr(profile, k) != v)
    if not changed:
        return await _unchanged(db, user, org)
    if stored is None:
        db.add(profile)
    for key in changed:
        setattr(profile, key, values[key])
    profile.updated_by_user_id = user.id
    return await _commit(db, user, org, "profile", {"fields": changed})


@router.post("/{org_id}/courses", status_code=201, response_model=PlacementCollegeEnvelope)
async def add_course(org_id: UUID, payload: PlacementCourseIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P6: unique per college case-insensitively (the unique index decides a race)."""
    org = await svc.editable(db, user, org_id, "course_create")
    await _at_most(db, BdmOrgCourse, org.id, svc.MAX_COURSES, "courses")
    course = BdmOrgCourse(organization_id=org.id, course_key=svc.course_key(payload.department, payload.course), **payload.model_dump())
    db.add(course)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "This course is already listed") from None
    return await _commit(db, user, org, "course_create", {"course_id": str(course.id)})


@router.delete("/{org_id}/courses/{course_id}", response_model=PlacementCollegeEnvelope)
async def delete_course(org_id: UUID, course_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await svc.editable(db, user, org_id, "course_delete")
    course = await svc.owned(db, BdmOrgCourse, org.id, course_id, COURSE_NOT_FOUND)
    if await db.scalar(select(exists().where(BdmOrgPlacementBatch.course_id == course.id))):
        raise HTTPException(409, "Remove this course's batches first")
    await db.delete(course)
    return await _commit(db, user, org, "course_delete", {"course_id": str(course_id)})


@router.post("/{org_id}/batches", status_code=201, response_model=PlacementCollegeEnvelope)
async def add_batch(org_id: UUID, payload: PlacementBatchIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P7: the course, when given, must be one of this college's (422 otherwise)."""
    org = await svc.editable(db, user, org_id, "batch_create")
    if payload.course_id is not None and await db.scalar(select(BdmOrgCourse.id).where(BdmOrgCourse.id == payload.course_id, BdmOrgCourse.organization_id == org.id)) is None:
        raise HTTPException(422, "Choose one of this college's courses")
    await _at_most(db, BdmOrgPlacementBatch, org.id, svc.MAX_BATCHES, "batches")
    batch = BdmOrgPlacementBatch(organization_id=org.id, created_by_user_id=user.id, **payload.model_dump())
    db.add(batch)
    await db.flush()
    return await _commit(db, user, org, "batch_create", {"batch_id": str(batch.id)})


@router.delete("/{org_id}/batches/{batch_id}", response_model=PlacementCollegeEnvelope)
async def delete_batch(org_id: UUID, batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await svc.editable(db, user, org_id, "batch_delete")
    await db.delete(await svc.owned(db, BdmOrgPlacementBatch, org.id, batch_id, "Batch not found"))
    return await _commit(db, user, org, "batch_delete", {"batch_id": str(batch_id)})


@router.post("/{org_id}/calendar", status_code=201, response_model=PlacementCollegeEnvelope)
async def add_event(org_id: UUID, payload: PlacementEventIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await svc.editable(db, user, org_id, "event_create")
    await _at_most(db, BdmOrgPlacementEvent, org.id, svc.MAX_EVENTS, "calendar entries")
    event = BdmOrgPlacementEvent(organization_id=org.id, created_by_user_id=user.id, **payload.model_dump())
    db.add(event)
    await db.flush()
    return await _commit(db, user, org, "event_create", {"event_id": str(event.id), "kind": event.kind})


@router.delete("/{org_id}/calendar/{event_id}", response_model=PlacementCollegeEnvelope)
async def delete_event(org_id: UUID, event_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await svc.editable(db, user, org_id, "event_delete")
    await db.delete(await svc.owned(db, BdmOrgPlacementEvent, org.id, event_id, "Calendar entry not found"))
    return await _commit(db, user, org, "event_delete", {"event_id": str(event_id)})


@router.post("/{org_id}/interactions", status_code=201, response_model=PlacementCollegeEnvelope)
async def log_interaction(org_id: UUID, payload: TpoInteractionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P9: append-only. The contact, when given, must be this college's; its name is kept on the row."""
    org = await svc.editable(db, user, org_id, "interaction_create")
    if payload.occurred_at > datetime.now(UTC) + FUTURE_SLACK:
        raise HTTPException(422, "An interaction can't be in the future")
    contact_name = None
    if payload.contact_id is not None:
        contact_name = await db.scalar(select(BdmOrganizationContact.name).where(BdmOrganizationContact.id == payload.contact_id, BdmOrganizationContact.organization_id == org.id))
        if contact_name is None:
            raise HTTPException(422, "Choose one of this college's contacts")
    row = BdmOrgTpoInteraction(organization_id=org.id, logged_by_user_id=user.id, contact_name=contact_name, **payload.model_dump())
    db.add(row)
    await db.flush()
    return await _commit(db, user, org, "interaction_create", {"interaction_id": str(row.id), "channel": row.channel})


@router.patch("/{org_id}/contacts/{contact_id}", response_model=PlacementCollegeEnvelope)
async def update_tpo_contact(org_id: UUID, contact_id: UUID, payload: TpoContactUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P10: only the office details and preferred method; the BDM's contact fields stay on the bdm-002 routes."""
    org = await svc.editable(db, user, org_id, "contact_update")
    contact = await orgs.load_contact(db, org, contact_id)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(contact, k) != v)
    if not changed:
        return await _unchanged(db, user, org)
    for key in changed:
        setattr(contact, key, changes[key])
    return await _commit(db, user, org, "contact_update", {"contact_id": str(contact.id), "fields": changed})
