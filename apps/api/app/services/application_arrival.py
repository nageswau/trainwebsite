"""ccrm-028 (DEC-SCOPE-265): an application's arrival and orientation after enrolment -- the rules, the change set and the read view
behind the counselor/Admin routes in api/application_offers.py. Nothing here commits: the route scopes, locks, notifies, audits and
commits. Recording arrival moves nothing else (A1). Spec: docs/superpowers/specs/2026-10-25-ccrm-028-arrival-orientation-design.md."""

from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OverseasApplication, User
from app.schemas import ApplicationArrivalSave

NOT_ENROLLED = "Arrival is recorded after enrolment is confirmed"
NEED_DATE = "Enter the arrival date to confirm arrival"
FUTURE_DATE = "A confirmed arrival date cannot be in the future"
NEED_ARRIVAL = "Confirm arrival before recording orientation"


def _values(app: OverseasApplication) -> dict:
    """The saved state in the audit's field names (`arrival_confirmed` stands for the stamp)."""
    return {
        "arrival_date": app.arrival_date,
        "arrival_confirmed": app.arrival_confirmed_at is not None,
        "orientation_attended": app.orientation_attended,
        "arrival_notes": app.arrival_notes,
    }


def changes(app: OverseasApplication, payload: ApplicationArrivalSave) -> list[str]:
    """A3/A5 checked, the names of the fields the save changes (empty: nothing to write)."""
    if app.status != "enrolled":
        raise HTTPException(422, NOT_ENROLLED)
    if payload.arrival_confirmed and payload.arrival_date is None:
        raise HTTPException(422, NEED_DATE)
    if payload.arrival_confirmed and payload.arrival_date > date.today():
        raise HTTPException(422, FUTURE_DATE)
    if payload.orientation_attended and not payload.arrival_confirmed:
        raise HTTPException(422, NEED_ARRIVAL)
    new = {"arrival_date": payload.arrival_date, "arrival_confirmed": payload.arrival_confirmed, "orientation_attended": payload.orientation_attended, "arrival_notes": payload.notes}
    return [name for name, value in _values(app).items() if new[name] != value]


def apply(app: OverseasApplication, payload: ApplicationArrivalSave, actor: User) -> None:
    """A4: confirming stamps who and when; a save that keeps it confirmed keeps the first stamp; un-confirming clears it."""
    app.arrival_date, app.orientation_attended, app.arrival_notes = payload.arrival_date, payload.orientation_attended, payload.notes
    if not payload.arrival_confirmed:
        app.arrival_confirmed_at = app.arrival_confirmed_by_id = None
    elif app.arrival_confirmed_at is None:
        app.arrival_confirmed_at, app.arrival_confirmed_by_id = datetime.now(UTC), actor.id


def summary(app: OverseasApplication) -> str:
    """The status-history note (A6). The free-text notes stay on the arrival record."""
    if app.arrival_confirmed_at is not None:
        text = f"arrived {app.arrival_date.isoformat()}"
    else:
        text = f"expected {app.arrival_date.isoformat()}" if app.arrival_date else "no arrival date"
    return f"Arrival updated -- {text}, orientation attended" if app.orientation_attended else f"Arrival updated -- {text}"


async def view(db: AsyncSession, app: OverseasApplication) -> dict:
    confirmer = await db.get(User, app.arrival_confirmed_by_id) if app.arrival_confirmed_by_id else None
    return {
        "status": app.status,
        "can_record": app.status == "enrolled",
        "arrival_date": app.arrival_date,
        "arrival_confirmed": app.arrival_confirmed_at is not None,
        "confirmed_at": app.arrival_confirmed_at,
        "confirmed_by": confirmer.full_name if confirmer else None,
        "orientation_attended": app.orientation_attended,
        "notes": app.arrival_notes,
    }
