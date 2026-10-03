"""bdm-010 (DEC-SCOPE-060, spec §5.3): BDM trips, the manager's team view and approval queue, and expenses.

Scope always comes from the session; the only ids in a path are trip and expense ids, both scope-checked in SQL (404).
Each write is one transaction: the service flushes, this module sends the in-app notices (`channels=[]`, T4) and commits once,
so a failed commit leaves no trip change, audit row or notice behind. Lists are {items, total, limit, offset}."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.workflows import _notify_user
from app.core.database import get_db
from app.models import BdmTrip, User
from app.schemas import BdmTripCreate, BdmTripExpenseCreate, BdmTripExpenseUpdate, BdmTripOut, BdmTripPage, BdmTripReject, BdmTripUpdate
from app.services import bdm_travel as travel
from app.services.bdm import bdm_context, require_manager, team_filter

router = APIRouter(prefix="/bdm", tags=["bdm-travel"])
ApprovalStatus = Literal["draft", "submitted", "approved", "rejected"]
TravelStatus = Literal["planned", "in_progress", "completed", "cancelled"]
NEWEST = (BdmTrip.travel_date.desc(), BdmTrip.code.desc())


def _place_line(trip: BdmTrip) -> str:
    return f"{trip.code}: {trip.from_place} → {trip.to_place}, {trip.travel_date:%d %b %Y}"


@router.get("/trips", response_model=BdmTripPage)
async def my_trips(approval_status: ApprovalStatus | None = None, travel_status: TravelStatus | None = None, limit: int = LIMIT,
                   offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await bdm_context(db, user)
    filters = [BdmTrip.bdm_user_id == user.id, *travel.status_filters(approval_status, travel_status)]
    return await travel.page(db, travel.trip_rows(filters), limit, offset, NEWEST)


@router.post("/trips", status_code=201, response_model=BdmTripOut)
async def create_trip(body: BdmTripCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await bdm_context(db, user)
    today = travel.india_today()
    trip = await travel.create_trip(db, user, body, today)
    await db.commit()
    return await travel.trip_out(db, trip, user, today)


@router.get("/trips/{trip_id}", response_model=BdmTripOut)
async def get_trip(trip_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    trip = await travel.load_own_trip(db, user, trip_id)
    return await travel.trip_out(db, trip, user, travel.india_today())


@router.patch("/trips/{trip_id}", response_model=BdmTripOut)
async def update_trip(trip_id: UUID, body: BdmTripUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = travel.india_today()
    trip = await travel.load_own_trip(db, user, trip_id, lock=True)
    await travel.update_trip(db, user, trip, body, today)
    await db.commit()
    return await travel.trip_out(db, trip, user, today)


async def _owner_command(db: AsyncSession, user: User, trip_id: UUID, action: str) -> dict:
    today = travel.india_today()
    trip = await travel.load_own_trip(db, user, trip_id, lock=True)
    await travel.transition(db, user, trip, action, today)
    if action == "submit":
        recipients, url = await travel.submit_recipients(db, trip)
        for recipient in recipients:
            await _notify_user(db, recipient, "Travel approval needed", _place_line(trip), url, channels=[])
    await db.commit()
    return await travel.trip_out(db, trip, user, today)


def _command_route(action: str) -> None:
    async def command(trip_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        return await _owner_command(db, user, trip_id, action)

    router.post(f"/trips/{{trip_id}}/{action}", response_model=BdmTripOut, name=f"bdm_trip_{action}")(command)


for _action in ("submit", "withdraw", "start", "complete", "cancel"):
    _command_route(_action)


@router.get("/manager/trips", response_model=BdmTripPage)
async def team_trips(bdm_user_id: UUID | None = None, approval_status: ApprovalStatus | None = None, travel_status: TravelStatus | None = None,
                     limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Team scope (D4); `bdm_user_id` is ANDed with it, so it can only narrow (S3)."""
    require_manager(user)
    filters = [*team_filter(user), *travel.status_filters(approval_status, travel_status)]
    if bdm_user_id:
        filters.append(BdmTrip.bdm_user_id == bdm_user_id)
    return await travel.page(db, travel.trip_rows(filters), limit, offset, NEWEST)


@router.get("/manager/approvals", response_model=BdmTripPage)
async def approvals(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = travel.approvals_filter(user)
    return await travel.page(db, travel.trip_rows(filters), limit, offset, (BdmTrip.submitted_at, BdmTrip.code))


@router.get("/manager/trips/{trip_id}", response_model=BdmTripOut)
async def team_trip(trip_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    trip = await travel.load_team_trip(db, user, trip_id)
    return await travel.trip_out(db, trip, user, travel.india_today())


async def _decision(db: AsyncSession, user: User, trip_id: UUID, approve: bool, reason: str | None = None) -> dict:
    trip = await travel.decide(db, user, trip_id, approve=approve, reason=reason)
    owner = await db.get(User, trip.bdm_user_id)
    title = "Trip approved" if approve else "Trip not approved"
    await _notify_user(db, owner, title, _place_line(trip), f"/bdm/travel/{trip.id}", channels=[])  # T12
    await db.commit()
    return await travel.trip_out(db, trip, user, travel.india_today())


@router.post("/manager/trips/{trip_id}/approve", response_model=BdmTripOut)
async def approve(trip_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _decision(db, user, trip_id, True)


@router.post("/manager/trips/{trip_id}/reject", response_model=BdmTripOut)
async def reject(trip_id: UUID, body: BdmTripReject, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _decision(db, user, trip_id, False, body.reason)


async def _expense_write(db: AsyncSession, user: User, trip_id: UUID, write) -> dict:
    """Locks the trip first, so an expense write and a cancel or a second write serialise (§5.5)."""
    today = travel.india_today()
    trip = await travel.load_own_trip(db, user, trip_id, lock=True)
    await write(trip, today)
    await db.commit()
    return await travel.trip_out(db, trip, user, today)


@router.post("/trips/{trip_id}/expenses", status_code=201, response_model=BdmTripOut)
async def add_expense(trip_id: UUID, body: BdmTripExpenseCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _expense_write(db, user, trip_id, lambda trip, today: travel.add_expense(db, user, trip, body, today))


@router.patch("/trips/{trip_id}/expenses/{expense_id}", response_model=BdmTripOut)
async def update_expense(trip_id: UUID, expense_id: UUID, body: BdmTripExpenseUpdate, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    return await _expense_write(db, user, trip_id, lambda trip, today: travel.update_expense(db, user, trip, expense_id, body, today))


@router.delete("/trips/{trip_id}/expenses/{expense_id}", response_model=BdmTripOut)
async def delete_expense(trip_id: UUID, expense_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _expense_write(db, user, trip_id, lambda trip, today: travel.delete_expense(db, user, trip, expense_id, today))
