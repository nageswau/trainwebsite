"""bdm-011 test builders: a BDM with an organization and a trip, and IST times on trip days. Unique per call (shared database)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.services.bdm_travel import india_today
from tests.bdm006_helpers import APPTS, bdm_with_org, create_appt
from tests.bdm010_helpers import TRIPS, make_trip

IST = ZoneInfo("Asia/Kolkata")


def on_day(days_from_today: int, hour: int = 10) -> str:
    """An IST time on India's today + n (trips default to today + 7 .. today + 8)."""
    return datetime.combine(india_today() + timedelta(days=days_from_today), time(hour), IST).isoformat()


async def bdm_trip(client, db, bdm_type: str = "college", **trip_over):
    """Signed in as a BDM with one assigned organization and one draft trip (today + 7 .. today + 8)."""
    manager, bdm, org = await bdm_with_org(client, db, bdm_type)
    return manager, bdm, org, await make_trip(client, **trip_over)


async def linked(client, org: dict, trip: dict, day: int = 7, hour: int = 10, **over) -> dict:
    return await create_appt(client, org, starts_at=on_day(day, hour), trip_id=trip["id"], **over)


__all__ = ["APPTS", "TRIPS", "bdm_trip", "linked", "on_day"]
