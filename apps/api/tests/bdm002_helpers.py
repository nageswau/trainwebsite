"""bdm-002 test builders. Unique values per call: the test database is shared and never truncated."""

import uuid

from app.models import BdmProfile, User
from app.services.bdm import BDM_DIVISION
from tests.bdm001_helpers import emp, make_user

ORGS = "/api/v1/bdm/organizations"


async def make_bdm(db, manager: User, bdm_type: str = "college", *, active: bool = True) -> User:
    user = await make_user(db, "bdm", BDM_DIVISION[bdm_type], active=active)
    db.add(BdmProfile(user_id=user.id, bdm_type=bdm_type, employee_id=emp(), reporting_manager_user_id=manager.id))
    await db.commit()
    return user


def unique_name(prefix: str = "College") -> str:
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def org_payload(**overrides) -> dict:
    payload = {
        "org_type": "college",
        "name": unique_name(),
        "city": "Kochi",
        "state": "Kerala",
        "contacts": [{"name": "Dr Rao", "designation": "Principal", "role": "principal"}],
    }
    payload.update(overrides)
    return payload


async def create_org(client, **overrides) -> dict:
    response = await client.post(ORGS, json=org_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["organization"]
