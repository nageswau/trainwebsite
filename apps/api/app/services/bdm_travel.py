"""bdm-010 (DEC-SCOPE-060, spec §5.2): trip rules, scope, decisions, expenses and audit.

Functions only; nothing here commits -- the route owns the transaction. One transition table (`RULES`) drives both enforcement
and the UI's `can_*` flags. Logs carry ids, route, action and state -- never places, purpose, remarks, reason or amounts (S11)."""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import BDM_TRIP_CODE_SEQ, AuditLog, BdmProfile, BdmTrip, BdmTripExpense, User
from app.services.bdm import bdm_context, require_manager, team_filter

logger = logging.getLogger("app.bdm")

INDIA = ZoneInfo("Asia/Kolkata")  # T14: "today" is the India calendar date (as schools.TIER_TIMEZONE)
PAST_DAYS = 30
MAX_SPAN_DAYS = 30  # return - travel <= 30 days, i.e. a trip lasts at most 31 days
MAX_EXPENSES = 100  # §12.1 A9: keeps the detail response bounded
EDITABLE = ("draft", "rejected")
UNDERWAY = ("planned", "in_progress")



def _editable(t, today) -> bool:
    return t.approval_status in EDITABLE and t.travel_status == "planned"


def _pending(t, today) -> bool:
    return t.approval_status == "submitted" and t.travel_status == "planned"


RULES = {
    "edit": _editable,
    "submit": _editable,
    "withdraw": _pending,
    "decide": _pending,
    "start": lambda t, today: t.approval_status == "approved" and t.travel_status == "planned" and today >= t.travel_date,
    "complete": lambda t, today: t.approval_status == "approved" and t.travel_status in UNDERWAY and today >= t.travel_date,
    "cancel": lambda t, today: t.travel_status in UNDERWAY,
    "expense": lambda t, today: t.approval_status == "approved",
}
VERBS = {"edit": "edited", "submit": "submitted", "withdraw": "withdrawn", "decide": "decided", "start": "started",
         "complete": "completed", "cancel": "cancelled"}
FLAG_ACTIONS = {"can_edit": "edit", "can_submit": "submit", "can_withdraw": "withdraw", "can_start": "start",
                "can_complete": "complete", "can_cancel": "cancel", "can_add_expense": "expense"}


def india_today() -> date:
    return datetime.now(INDIA).date()


def now() -> datetime:
    return datetime.now(UTC)


def check_dates(travel: date, ret: date, today: date) -> None:
    if ret < travel:
        raise HTTPException(422, "Return date must be on or after the travel date")
    if travel < today - timedelta(days=PAST_DAYS):
        raise HTTPException(422, f"Travel date can be at most {PAST_DAYS} days in the past")
    if (ret - travel).days > MAX_SPAN_DAYS:
        raise HTTPException(422, f"A trip can last at most {MAX_SPAN_DAYS + 1} days")


def allowed(trip, action: str, today: date) -> bool:
    return RULES[action](trip, today)


# QA10-03: how a person would describe the trip's state ("is still a draft", not "is draft").
STATE_PHRASES = {
    "draft": "is still a draft", "submitted": "is waiting for approval", "approved": "is already approved",
    "rejected": "was not approved", "in_progress": "is in progress", "completed": "is completed", "cancelled": "is cancelled",
}


def state_phrase(trip) -> str:
    return STATE_PHRASES[trip.travel_status if trip.travel_status != "planned" else trip.approval_status]


def refusal(trip, action: str, today: date) -> HTTPException:
    """The 409 for an action outside its row of the transition table, worded for the user."""
    if action == "expense":
        return HTTPException(409, "Expenses can be added once the trip is approved")
    # Only when the date is the reason: the action would be allowed on the travel date, which hasn't come yet.
    if action in ("start", "complete") and today < trip.travel_date and allowed(trip, action, trip.travel_date):
        return HTTPException(409, f"This trip starts on {trip.travel_date:%d %b %Y}; it can be {VERBS[action]} from that day")
    return HTTPException(409, f"This trip {state_phrase(trip)} and can't be {VERBS[action]}")


def owner_flags(trip, today: date) -> dict[str, bool]:
    return {flag: allowed(trip, action, today) for flag, action in FLAG_ACTIONS.items()} | {"can_decide": False}


def decider_may(user, manager) -> bool:
    """T2/T3: the BDM's reporting manager decides; any super_admin only while that manager is inactive."""
    if user.role == "bdm_manager":
        return user.id == manager.id
    return user.role == "super_admin" and not manager.active


Owner = aliased(User)
Manager = aliased(User)
CENTS = Decimal("0.01")


def audit(db: AsyncSession, user: User, action: str, trip: BdmTrip, outcome: str = "recorded", **meta) -> None:
    """S13: one row per change, in the caller's transaction (the fields `workflows._audit` writes). Dates, decimals and UUIDs in
    the metadata are serialized by the engine (`core.database._json_default`)."""
    db.add(AuditLog(user_id=user.id, action=f"bdm.trip_{action}", entity_type="bdm_trip", entity_id=str(trip.id), outcome=outcome,
                    metadata_json={"code": trip.code, **meta}))


async def next_code(db: AsyncSession) -> str:
    return f"TRV-{await db.scalar(select(BDM_TRIP_CODE_SEQ.next_value())):06d}"


async def create_trip(db: AsyncSession, user: User, body, today: date) -> BdmTrip:
    check_dates(body.travel_date, body.return_date, today)
    trip = BdmTrip(code=await next_code(db), bdm_user_id=user.id, approval_status="draft", travel_status="planned", currency="INR",
                   **body.model_dump())
    db.add(trip)
    await db.flush()
    audit(db, user, "create", trip, mode=trip.mode, estimated_cost=trip.estimated_cost)
    return trip


def _refuse(user: User, trip: BdmTrip, action: str, error: HTTPException) -> HTTPException:
    logger.warning("bdm_trip_refused", extra={"extra_fields": {
        "actor_id": str(user.id), "trip_id": str(trip.id), "action": action, "status": error.status_code,
        "approval_status": trip.approval_status, "travel_status": trip.travel_status}})
    return error


async def load_own_trip(db: AsyncSession, user: User, trip_id, *, lock: bool = False) -> BdmTrip:
    """S3: scope in the WHERE; another BDM's trip is indistinguishable from a missing one (404)."""
    await bdm_context(db, user)
    stmt = select(BdmTrip).where(BdmTrip.id == trip_id, BdmTrip.bdm_user_id == user.id)
    trip = await db.scalar(stmt.with_for_update() if lock else stmt)
    if not trip:
        raise HTTPException(404, "Trip not found")
    return trip


async def load_team_trip(db: AsyncSession, user: User, trip_id, *, lock: bool = False) -> BdmTrip:
    require_manager(user)
    stmt = select(BdmTrip).join(BdmProfile, BdmProfile.user_id == BdmTrip.bdm_user_id).where(BdmTrip.id == trip_id, *team_filter(user))
    trip = await db.scalar(stmt.with_for_update(of=BdmTrip) if lock else stmt)
    if not trip:
        raise HTTPException(404, "Trip not found")
    return trip


async def update_trip(db: AsyncSession, user: User, trip: BdmTrip, body, today: date) -> None:
    """PATCH: remarks are editable in every state (backlog, the reminder's Add Remarks); every other field only while the trip
    is a draft or rejected. Audited with before/after of the changed fields."""
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Nothing to change")
    if set(changes) - {"remarks"}:
        if trip.approval_status == "submitted" and trip.travel_status == "planned":
            raise _refuse(user, trip, "edit", HTTPException(409, "Withdraw the trip to edit it"))
        if trip.approval_status == "approved":
            raise _refuse(user, trip, "edit", HTTPException(422, "An approved trip's details can't be changed"))
        if not allowed(trip, "edit", today):
            raise _refuse(user, trip, "edit", refusal(trip, "edit", today))
        check_dates(changes.get("travel_date", trip.travel_date), changes.get("return_date", trip.return_date), today)
    before = {k: getattr(trip, k) for k in changes}
    for key, value in changes.items():
        setattr(trip, key, value)
    await db.flush()
    audit(db, user, "update", trip, before=before, after=changes)


async def transition(db: AsyncSession, user: User, trip: BdmTrip, action: str, today: date) -> None:
    """The owner's commands (submit, withdraw, start, complete, cancel) on a trip the caller has locked."""
    if not allowed(trip, action, today):
        raise _refuse(user, trip, action, refusal(trip, action, today))
    before = (trip.approval_status, trip.travel_status)
    if action == "submit":
        trip.approval_status, trip.submitted_at = "submitted", now()
        trip.rejection_reason = trip.decided_by_user_id = trip.decided_at = None
    elif action == "withdraw":
        trip.approval_status, trip.submitted_at = "draft", None
    elif action == "start":
        trip.travel_status = "in_progress"
    elif action == "complete":
        trip.travel_status, trip.completed_at = "completed", now()
    elif action == "cancel":
        trip.travel_status, trip.cancelled_at = "cancelled", now()
    await db.flush()
    audit(db, user, action, trip, before=list(before), after=[trip.approval_status, trip.travel_status])


async def reporting_manager(db: AsyncSession, trip: BdmTrip, *, lock: bool = False) -> User:
    """The BDM's current reporting manager (T2: resolved now, never stored). `lock` takes FOR SHARE on the profile and the
    manager so a concurrent reassignment or deactivation waits for this transaction (bdm-001 §5.8)."""
    stmt = select(BdmProfile).where(BdmProfile.user_id == trip.bdm_user_id)
    profile = await db.scalar(stmt.with_for_update(read=True) if lock else stmt)
    stmt = select(User).where(User.id == profile.reporting_manager_user_id)
    return await db.scalar(stmt.with_for_update(read=True) if lock else stmt)


async def submit_recipients(db: AsyncSession, trip: BdmTrip) -> tuple[list[User], str]:
    """T11: the active manager, or every active super_admin when the manager is inactive."""
    manager = await reporting_manager(db, trip)
    if manager.active:
        return [manager], "/bdm/manager/approvals"
    admins = await db.scalars(select(User).where(User.role == "super_admin", User.active.is_(True)).order_by(User.id))
    return list(admins), "/admin/bdm-travel-approvals"


def status_filters(approval_status: str | None, travel_status: str | None) -> list:
    return ([BdmTrip.approval_status == approval_status] if approval_status else []) + (
        [BdmTrip.travel_status == travel_status] if travel_status else [])


def trip_rows(filters: list):
    """One query for a list page (§12.1 A13): trip + owner name + actual cost, joined to the owner's profile and manager so the
    team and approval filters can be expressed on them. The cost is a correlated sum, so only the rows on the page are summed (by
    `ix_bdm_trip_expenses_trip`), never the whole expenses table."""
    actual_cost = select(func.coalesce(func.sum(BdmTripExpense.amount), 0)).where(BdmTripExpense.trip_id == BdmTrip.id).scalar_subquery()
    return (
        select(BdmTrip, Owner.full_name, actual_cost)
        .join(Owner, Owner.id == BdmTrip.bdm_user_id)
        .join(BdmProfile, BdmProfile.user_id == BdmTrip.bdm_user_id)
        .join(Manager, Manager.id == BdmProfile.reporting_manager_user_id)
        .where(*filters)
    )


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENTS)


def _row(trip: BdmTrip, owner_name: str, actual) -> dict:
    return {
        "id": trip.id, "code": trip.code, "bdm": {"id": trip.bdm_user_id, "full_name": owner_name}, "travel_date": trip.travel_date,
        "return_date": trip.return_date, "from_place": trip.from_place, "to_place": trip.to_place, "mode": trip.mode,
        "accommodation_required": trip.accommodation_required, "estimated_cost": _money(trip.estimated_cost),
        "actual_cost": _money(actual), "currency": trip.currency, "approval_status": trip.approval_status,
        "travel_status": trip.travel_status, "submitted_at": trip.submitted_at,
    }


async def page(db: AsyncSession, stmt, limit: int, offset: int, order: tuple) -> dict:
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    return {"items": [_row(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def trip_out(db: AsyncSession, trip: BdmTrip, user: User, today: date) -> dict:
    """The detail (§5.1 `BdmTripOut`). The owner gets the transition flags; a manager or super_admin gets only `can_decide`."""
    expenses = list(await db.scalars(
        select(BdmTripExpense).where(BdmTripExpense.trip_id == trip.id).order_by(BdmTripExpense.expense_date, BdmTripExpense.created_at)))
    owner = await db.get(User, trip.bdm_user_id)
    decided_by = await db.get(User, trip.decided_by_user_id) if trip.decided_by_user_id else None
    if user.id == trip.bdm_user_id:
        flags = owner_flags(trip, today)
    else:
        flags = dict.fromkeys(FLAG_ACTIONS, False) | {
            "can_decide": allowed(trip, "decide", today) and decider_may(user, await reporting_manager(db, trip))}
    return {
        **_row(trip, owner.full_name, sum((e.amount for e in expenses), Decimal(0))),
        "purpose": trip.purpose, "remarks": trip.remarks, "rejection_reason": trip.rejection_reason,
        "decided_by": {"id": decided_by.id, "full_name": decided_by.full_name} if decided_by else None,
        "decided_at": trip.decided_at, "completed_at": trip.completed_at, "cancelled_at": trip.cancelled_at,
        "expenses": [{"id": e.id, "category": e.category, "amount": _money(e.amount), "expense_date": e.expense_date, "note": e.note}
                     for e in expenses],
        **flags,
    }


async def decide(db: AsyncSession, user: User, trip_id, *, approve: bool, reason: str | None = None) -> BdmTrip:
    """T2/T3 + separation of duties, under locks: the trip FOR UPDATE, then the owner's profile and manager FOR SHARE, so a
    concurrent withdraw, cancel, reassignment or deactivation is serialised against this decision (§5.5)."""
    trip = await load_team_trip(db, user, trip_id, lock=True)
    manager = await reporting_manager(db, trip, lock=True)
    if not decider_may(user, manager):  # the same rule as the `can_decide` flag
        error = HTTPException(404, "Trip not found") if user.role == "bdm_manager" else HTTPException(403, "The reporting manager is active and decides this trip")
        raise _refuse(user, trip, "decide", error)
    if user.id == trip.bdm_user_id:
        raise _refuse(user, trip, "decide", HTTPException(403, "You can't decide your own trip"))
    today = india_today()
    if not allowed(trip, "decide", today):
        raise _refuse(user, trip, "decide", refusal(trip, "decide", today))
    trip.approval_status = "approved" if approve else "rejected"
    trip.rejection_reason = None if approve else reason
    trip.decided_by_user_id, trip.decided_at = user.id, now()
    await db.flush()
    meta = {"fallback": user.role == "super_admin"} | ({} if approve else {"reason": reason})
    audit(db, user, "approve" if approve else "reject", trip, outcome=trip.approval_status, **meta)
    logger.info("bdm_trip_decided", extra={"extra_fields": {"actor_id": str(user.id), "trip_id": str(trip.id),
                                                            "outcome": trip.approval_status, "fallback": meta["fallback"]}})
    return trip


def approvals_filter(user: User) -> list:
    """The queue: submitted, still-planned trips the caller may decide (T3, §5.2)."""
    require_manager(user)
    pending = [BdmTrip.approval_status == "submitted", BdmTrip.travel_status == "planned"]
    if user.role == "super_admin":
        return [*pending, Manager.active.is_(False)]
    return [*pending, BdmProfile.reporting_manager_user_id == user.id]


def _expense_trip(user: User, trip: BdmTrip, today: date) -> None:
    if not allowed(trip, "expense", today):
        raise _refuse(user, trip, "expense", refusal(trip, "expense", today))


async def load_expense(db: AsyncSession, trip: BdmTrip, expense_id) -> BdmTripExpense:
    expense = await db.scalar(select(BdmTripExpense).where(BdmTripExpense.id == expense_id, BdmTripExpense.trip_id == trip.id))
    if not expense:
        raise HTTPException(404, "Expense not found")
    return expense


def _line_meta(expense: BdmTripExpense) -> dict:
    return {"expense_id": expense.id, "category": expense.category, "amount": expense.amount, "expense_date": expense.expense_date}


async def add_expense(db: AsyncSession, user: User, trip: BdmTrip, body, today: date) -> None:
    _expense_trip(user, trip, today)
    count = await db.scalar(select(func.count()).where(BdmTripExpense.trip_id == trip.id))
    if count >= MAX_EXPENSES:
        raise _refuse(user, trip, "expense", HTTPException(409, f"A trip can have at most {MAX_EXPENSES} expense lines"))
    expense = BdmTripExpense(trip_id=trip.id, created_by_user_id=user.id, **body.model_dump())
    db.add(expense)
    await db.flush()
    audit(db, user, "expense_add", trip, **_line_meta(expense))


async def update_expense(db: AsyncSession, user: User, trip: BdmTrip, expense_id, body, today: date) -> None:
    _expense_trip(user, trip, today)
    expense = await load_expense(db, trip, expense_id)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Nothing to change")
    before = _line_meta(expense)
    for key, value in changes.items():
        setattr(expense, key, value)
    await db.flush()
    audit(db, user, "expense_update", trip, before=before, after=_line_meta(expense))


async def delete_expense(db: AsyncSession, user: User, trip: BdmTrip, expense_id, today: date) -> None:
    _expense_trip(user, trip, today)
    expense = await load_expense(db, trip, expense_id)
    meta = _line_meta(expense)
    await db.delete(expense)
    await db.flush()
    audit(db, user, "expense_delete", trip, **meta)
