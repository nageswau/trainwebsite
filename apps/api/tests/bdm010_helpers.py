"""bdm-010 test builders. Unique values per call: the test database is shared and never truncated."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.models import User
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import PASSWORD, create_bdm, login, make_manager, make_user

TRIPS = "/api/v1/bdm/trips"
TEAM_TRIPS = "/api/v1/bdm/manager/trips"
APPROVALS = "/api/v1/bdm/manager/approvals"


def trip_body(**over) -> dict:
    today = india_today()
    body = {"travel_date": str(today + timedelta(days=7)), "return_date": str(today + timedelta(days=8)), "from_place": "Hyderabad",
            "to_place": "Vijayawada", "purpose": "College visits", "mode": "train", "estimated_cost": "2500.00"}
    body.update(over)
    return body


async def sign_in(client, user: User) -> None:
    client.cookies.clear()
    await login(client, user)


async def bdm_pair(client, db, *, manager: User | None = None) -> tuple[User, User]:
    """A manager and one BDM reporting to them, created through the admin API. Leaves the client signed in as the BDM."""
    manager = manager or await make_manager(db)
    await sign_in(client, await make_user(db, "super_admin", "global"))
    created = (await create_bdm(client, manager.id)).json()
    bdm = await db.scalar(select(User).where(User.id == uuid.UUID(created["id"])))
    bdm.password_hash = hash_password(PASSWORD)
    await db.commit()
    await sign_in(client, bdm)
    return manager, bdm


async def make_trip(client, **over) -> dict:
    response = await client.post(TRIPS, json=trip_body(**over))
    assert response.status_code == 201, response.text
    return response.json()


async def act(client, trip_id: str, action: str, **kwargs):
    return await client.post(f"{TRIPS}/{trip_id}/{action}", **kwargs)
