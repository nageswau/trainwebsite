"""bdm-009 (DEC-SCOPE-065, spec §4.2, §5.2): activity time rules, scope, rows, day counts and audit.

Functions only; nothing here commits -- the route owns the transaction. Every `{activity_id}` resolves through `load_readable`, so an
activity on an organization the caller can't read is the same 404 as a missing one. Logs and audit rows carry ids, channel and field
names -- never the note or the contact's name."""

import logging
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import BDM_ACTIVITY_CHANNELS, AuditLog, BdmActivity, BdmOrganization, BdmOrganizationContact, BdmProfile, User
from app.schemas import activity_direction_error
from app.services.bdm_organizations import caller_scope
from app.services.bdm_travel import INDIA

logger = logging.getLogger("app.bdm")

BACKDATE_DAYS = 7  # V4
CLOCK_TOLERANCE = timedelta(minutes=5)  # V9: a browser clock slightly ahead of the server
DAILY_CAP = 200  # V10: an abuse bound, far above real use
NOT_FOUND = "Activity not found"
CAP_REACHED = f"You've logged {DAILY_CAP} activities for this day"
OWNER_ONLY = "Only the BDM who logged this activity can change it"
NOT_ASSIGNED = "Only the organization's assigned BDM can log activity"
ARCHIVED = "This organization is archived"
CONTACT_INVALID = "Choose a contact of this organization"
FUTURE = "When can't be in the future"
TOO_OLD = f"Activities can be logged up to {BACKDATE_DAYS} days back"
NOT_TODAY = "Only today's activities can be changed"
MOVE_TODAY = "An activity can only be moved within today"
FUTURE_DAY = "That date hasn't happened yet"
NEWEST = (BdmActivity.occurred_at.desc(), BdmActivity.id.desc())
Logger = aliased(User)


async def db_now(db: AsyncSession) -> datetime:
    """The database clock, read once per request: every time rule compares against the same instant."""
    now = await db.scalar(select(func.now()))
    assert now is not None  # SELECT now() always returns one row
    return now


def india_date(moment: datetime) -> date:
    return moment.astimezone(INDIA).date()


def day_range(day: date) -> tuple[datetime, datetime]:
    """An IST calendar day as a half-open instant range (index-friendly; no cast on the column)."""
    start = datetime.combine(day, time.min, tzinfo=INDIA)
    return start, start + timedelta(days=1)


def day_filters(day: date) -> list:
    start, end = day_range(day)
    return [BdmActivity.occurred_at >= start, BdmActivity.occurred_at < end]


def check_time(occurred_at: datetime, now: datetime) -> datetime:
    """V4 + V9. Returns the instant to store: up to CLOCK_TOLERANCE ahead is saved as `now`, so no future row is ever stored."""
    if occurred_at > now + CLOCK_TOLERANCE:
        raise HTTPException(422, FUTURE)
    if india_date(occurred_at) < india_date(now) - timedelta(days=BACKDATE_DAYS):
        raise HTTPException(422, TOO_OLD)
    return min(occurred_at, now)


async def check_daily_cap(db: AsyncSession, bdm_user_id: UUID, day: date) -> None:
    """V10, create only. A soft bound: two concurrent saves on different organizations may pass it by one or two."""
    count = await db.scalar(select(func.count()).select_from(BdmActivity).where(BdmActivity.bdm_user_id == bdm_user_id, *day_filters(day)))
    if (count or 0) >= DAILY_CAP:
        raise HTTPException(409, CAP_REACHED)


def refused(user: User, route: str, status: int, detail: str, **ids) -> HTTPException:
    """§12.3 S10: every refused write is visible in the logs (ids, route, status -- never text fields), as bdm-002's
    `bdm_org_write_refused`. Returns the exception for the caller to raise."""
    logger.warning("bdm_activity_write_refused", extra={"extra_fields": {
        "actor_id": str(user.id), "route": route, "status": status, **{k: str(v) for k, v in ids.items()}}})
    return HTTPException(status, detail)


def editable(activity: BdmActivity, now: datetime) -> bool:
    """AC4: the single gate for PATCH and DELETE. bdm-015 adds "and that day's report is not submitted" here."""
    return india_date(activity.occurred_at) == india_date(now)


def check_direction(channel: str, direction: str | None) -> None:
    error = activity_direction_error(channel, direction)
    if error:
        raise HTTPException(422, error)


async def contact_for(db: AsyncSession, org_id: UUID, contact_id: UUID) -> BdmOrganizationContact:
    contact = await db.scalar(select(BdmOrganizationContact).where(
        BdmOrganizationContact.id == contact_id, BdmOrganizationContact.organization_id == org_id))
    if contact is None:
        raise HTTPException(422, CONTACT_INVALID)
    return contact


def optional_filters(channel: str | None, organization_id: UUID | None) -> list:
    filters = []
    if channel:
        filters.append(BdmActivity.channel == channel)
    if organization_id:
        filters.append(BdmActivity.organization_id == organization_id)
    return filters


def _rows(filters: list):
    """One query for a list: activity + organization + logger name. Joined to the logger's profile so team scope (`team_filter`) can be
    expressed on it."""
    return (
        select(BdmActivity, BdmOrganization, Logger.full_name)
        .join(BdmOrganization, BdmOrganization.id == BdmActivity.organization_id)
        .join(Logger, Logger.id == BdmActivity.bdm_user_id)
        .join(BdmProfile, BdmProfile.user_id == BdmActivity.bdm_user_id)
        .where(*filters)
    )


def _out(activity: BdmActivity, org: BdmOrganization, logger_name: str, user: User, now: datetime) -> dict:
    return {
        "id": activity.id,
        "organization": {"id": org.id, "code": org.code, "name": org.name, "org_type": org.org_type},
        "bdm": {"id": activity.bdm_user_id, "full_name": logger_name},
        "contact_id": activity.contact_id,
        "contact_name": activity.contact_name,
        "contact_removed": activity.contact_name is not None and activity.contact_id is None,
        "channel": activity.channel,
        "direction": activity.direction,
        "occurred_at": activity.occurred_at,
        "note": activity.note,
        "created_at": activity.created_at,
        "updated_at": activity.updated_at,
        "permissions": {"can_change": user.id == activity.bdm_user_id and editable(activity, now)},
    }


async def page(db: AsyncSession, filters: list, limit: int, offset: int, user: User, now: datetime) -> dict:
    stmt = _rows(filters)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    result = (await db.execute(stmt.order_by(*NEWEST).limit(limit).offset(offset).execution_options(populate_existing=True))).tuples().all()
    return {"items": [_out(a, o, n, user, now) for a, o, n in result], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, user: User, activity_id: UUID, now: datetime) -> dict:
    row = (await db.execute(_rows([BdmActivity.id == activity_id]).execution_options(populate_existing=True))).one()
    return _out(row[0], row[1], row[2], user, now)


async def day_counts(db: AsyncSession, filters: list, day: date) -> dict:
    """AC3, reused by bdm-015: one query over the same filters as the list, for the whole IST day (not the page)."""
    per_channel = [func.count().filter(BdmActivity.channel == channel) for channel in BDM_ACTIVITY_CHANNELS]
    calls_made = func.count().filter(and_(BdmActivity.channel == "call", BdmActivity.direction == "outbound"))
    stmt = (
        select(*per_channel, calls_made, func.count(distinct(BdmActivity.organization_id)))
        .select_from(BdmActivity)
        .join(BdmOrganization, BdmOrganization.id == BdmActivity.organization_id)
        .join(BdmProfile, BdmProfile.user_id == BdmActivity.bdm_user_id)
        .where(*filters, *day_filters(day))
    )
    row = (await db.execute(stmt)).one()
    n = len(BDM_ACTIVITY_CHANNELS)
    return {"day": day, "by_channel": dict(zip(BDM_ACTIVITY_CHANNELS, row[:n], strict=True)), "calls_made": row[n],
            "organizations_contacted": row[n + 1]}


async def load_readable(db: AsyncSession, user: User, activity_id: UUID, *, lock: bool = False) -> BdmActivity:
    """V5: readable = its organization is readable (`caller_scope`; any other role is 403 there)."""
    stmt = (select(BdmActivity).join(BdmOrganization, BdmOrganization.id == BdmActivity.organization_id)
            .where(BdmActivity.id == activity_id, *await caller_scope(db, user)))
    if lock:
        stmt = stmt.with_for_update(of=BdmActivity).execution_options(populate_existing=True)
    activity = await db.scalar(stmt)
    if activity is None:
        raise HTTPException(404, NOT_FOUND)
    return activity


def audit(db: AsyncSession, user: User, action: str, activity: BdmActivity, fields: list[str] | None = None) -> None:
    """Same transaction as the write (fail closed); ids, channel and field names only."""
    meta: dict = {"organization_id": str(activity.organization_id), "channel": activity.channel}
    if fields is not None:
        meta["fields"] = fields
    db.add(AuditLog(user_id=user.id, action=f"bdm_activity.{action}", entity_type="bdm_activity", entity_id=str(activity.id),
                    metadata_json=meta))


def log(event: str, user: User, activity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "activity_id": str(activity_id), **extra}})
