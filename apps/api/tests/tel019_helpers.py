"""tel-019 test builders. Every value is unique per call: the test database is shared and never truncated, so pool requests from other
tests are visible too -- assert on the ids a test made, never on totals of a pool."""

from datetime import UTC, datetime, timedelta

from app.models import User
from tests.bdm001_helpers import make_manager, make_user
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import appt_payload
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager

__all__ = ["TEL", "OPTIONS", "BDM", "accept_url", "decline_url", "as_user", "at", "body", "file_request", "make_bdm", "make_manager",
           "make_telecaller", "make_tl_manager", "make_user", "telecaller", "bdm_with_org", "accept_body"]

TEL = "/api/v1/telecaller/meeting-requests"
OPTIONS = f"{TEL}/options"
BDM = "/api/v1/bdm/meeting-requests"


def accept_url(request_id) -> str:
    return f"{BDM}/{request_id}/accept"


def decline_url(request_id) -> str:
    return f"{BDM}/{request_id}/decline"


def at(hours: float = 0, *, days: int = 2) -> str:
    return (datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=days, hours=hours)).isoformat()


def body(**over) -> dict:
    return {"request_type": "college", "organization_name": "Govt College Kochi", "person_name": "Dr Rao", "contact_phone": "+91 98765 43210",
            "contact_email": "rao@college.example", "proposed_at": at(), "mode": "In person", "location": "Main campus",
            "purpose": "Course partnership", "remarks": "Prefers mornings", **over}


async def telecaller(db) -> User:
    return await make_telecaller(db, await make_tl_manager(db))


async def file_request(client, tel: User, **over) -> dict:
    await as_user(client, tel)
    response = await client.post(TEL, json=body(**over))
    assert response.status_code == 201, response.text
    return response.json()


async def bdm_with_org(client, db, bdm_type: str = "college", manager: User | None = None):
    """A logged-in BDM of `bdm_type` with one organization assigned to them."""
    manager = manager or await make_manager(db)
    bdm = await make_bdm(db, manager, bdm_type)
    await as_user(client, bdm)
    return manager, bdm, await create_org(client)


def accept_body(org: dict, **over) -> dict:
    return appt_payload(org, **({"starts_at": at(days=3)} | over))
