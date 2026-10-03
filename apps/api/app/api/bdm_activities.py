"""bdm-009 (DEC-SCOPE-065, spec §5.3): the BDM activity log.

Every `{activity_id}` resolves through `services.bdm_activities.load_readable` (unreadable = 404). Every write is one transaction --
scope (404), owner / assignee (403), lock (organization, then activity), rules (422 / 409), change, audit, one commit here. Lists are
{items, total, limit, offset}, newest first; the day lists also carry that whole day's counts."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmActivity, User
from app.schemas import BdmActivityChannel, BdmActivityCreate, BdmActivityDayPage, BdmActivityOut, BdmActivityPage, BdmActivityUpdate
from app.services import bdm_activities as svc
from app.services import bdm_organizations as org_svc
from app.services.bdm import bdm_context, require_manager, team_filter

router = APIRouter(prefix="/bdm", tags=["bdm-activities"])
DAY = Query(None, alias="date", description="IST calendar date, YYYY-MM-DD; default today")


def _day(day: date | None, now) -> date:
    today = svc.india_date(now)
    chosen = day or today
    if chosen > today:
        raise HTTPException(422, svc.FUTURE_DAY)
    return chosen


@router.get("/activities", response_model=BdmActivityDayPage)
async def my_activities(day: date | None = DAY, channel: BdmActivityChannel | None = None, organization_id: UUID | None = None,
                        limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await bdm_context(db, user)
    now = await svc.db_now(db)
    chosen = _day(day, now)
    filters = [BdmActivity.bdm_user_id == user.id, *svc.optional_filters(channel, organization_id)]
    listed = await svc.page(db, [*filters, *svc.day_filters(chosen)], limit, offset, user, now)
    return {**listed, "counts": await svc.day_counts(db, filters, chosen)}


@router.post("/activities", status_code=201, response_model=BdmActivityOut)
async def log_activity(payload: BdmActivityCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await bdm_context(db, user)
    org = await org_svc.load_scoped(db, user, payload.organization_id, lock=True)  # out of type -> 404; serializes with archive/assign
    if org.assigned_bdm_user_id != user.id:
        raise svc.refused(user, "activity_create", 403, svc.NOT_ASSIGNED, organization_id=org.id)
    if org.archived_at is not None:
        raise HTTPException(422, svc.ARCHIVED)
    contact = await svc.contact_for(db, org.id, payload.contact_id) if payload.contact_id else None
    now = await svc.db_now(db)
    occurred_at = svc.check_time(payload.occurred_at, now)  # V9: clamped to now when slightly ahead
    await svc.check_daily_cap(db, user.id, svc.india_date(occurred_at))
    activity = BdmActivity(
        bdm_user_id=user.id, organization_id=org.id, contact_id=contact.id if contact else None,
        contact_name=contact.name if contact else None, channel=payload.channel, direction=payload.direction,
        occurred_at=occurred_at, note=payload.note,
    )
    db.add(activity)
    await db.flush()
    svc.audit(db, user, "created", activity)
    await db.commit()
    svc.log("bdm_activity_created", user, activity.id, channel=activity.channel)
    return await svc.one(db, user, activity.id, now)


async def _owned(db: AsyncSession, user: User, activity_id: UUID, route: str):
    """Scope (404) and owner (403) before any lock; then organization, then activity (spec §5.5); then the day gate (409)."""
    current = await svc.load_readable(db, user, activity_id)
    if current.bdm_user_id != user.id:
        raise svc.refused(user, route, 403, svc.OWNER_ONLY, activity_id=activity_id)
    org = await org_svc.load_scoped(db, user, current.organization_id, lock=True)
    activity = await svc.load_readable(db, user, activity_id, lock=True)  # a concurrent delete -> 404 here
    now = await svc.db_now(db)
    if not svc.editable(activity, now):
        raise HTTPException(409, svc.NOT_TODAY)
    return org, activity, now


@router.patch("/activities/{activity_id}", response_model=BdmActivityOut)
async def update_activity(activity_id: UUID, payload: BdmActivityUpdate, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    org, activity, now = await _owned(db, user, activity_id, "activity_update")
    changes = payload.model_dump(exclude_unset=True)
    if "occurred_at" in changes:
        changes["occurred_at"] = svc.check_time(changes["occurred_at"], now)
        if svc.india_date(changes["occurred_at"]) != svc.india_date(now):
            raise HTTPException(422, svc.MOVE_TODAY)
    if "contact_id" in changes:
        if changes["contact_id"] == activity.contact_id:
            del changes["contact_id"]  # §12.1 A2: the same contact again never rewrites the stored name
        else:
            contact = await svc.contact_for(db, org.id, changes["contact_id"]) if changes["contact_id"] else None
            changes["contact_name"] = contact.name if contact else None
    svc.check_direction(changes.get("channel", activity.channel), changes.get("direction", activity.direction))
    changed = sorted(k for k, v in changes.items() if k != "contact_name" and getattr(activity, k) != v)
    if not changed:
        return await svc.one(db, user, activity.id, now)
    for key, value in changes.items():
        setattr(activity, key, value)
    await db.flush()
    svc.audit(db, user, "updated", activity, changed)
    await db.commit()
    svc.log("bdm_activity_updated", user, activity.id, fields=changed)
    return await svc.one(db, user, activity.id, now)


@router.delete("/activities/{activity_id}", status_code=204)
async def delete_activity(activity_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V8: a hard delete; the audit row keeps the id, organization and channel (never the note)."""
    _, activity, _ = await _owned(db, user, activity_id, "activity_delete")
    svc.audit(db, user, "deleted", activity)
    await db.delete(activity)
    await db.commit()
    svc.log("bdm_activity_deleted", user, activity_id)
    return Response(status_code=204)


@router.get("/organizations/{org_id}/activities", response_model=BdmActivityPage)
async def organization_activities(org_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """V5: every BDM's activities on the organization, for anyone who can read it (out of scope -> 404)."""
    org = await org_svc.load_scoped(db, user, org_id)
    now = await svc.db_now(db)
    return await svc.page(db, [BdmActivity.organization_id == org.id], limit, offset, user, now)


@router.get("/manager/activities", response_model=BdmActivityDayPage)
async def team_activities(day: date | None = DAY, bdm_user_id: UUID | None = None, channel: BdmActivityChannel | None = None,
                          limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Team scope (D4); `bdm_user_id` is ANDed with it, so it can only narrow."""
    require_manager(user)
    now = await svc.db_now(db)
    chosen = _day(day, now)
    filters = [*team_filter(user), *svc.optional_filters(channel, None)]
    if bdm_user_id:
        filters.append(BdmActivity.bdm_user_id == bdm_user_id)
    listed = await svc.page(db, [*filters, *svc.day_filters(chosen)], limit, offset, user, now)
    return {**listed, "counts": await svc.day_counts(db, filters, chosen)}
