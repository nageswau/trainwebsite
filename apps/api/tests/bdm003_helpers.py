"""bdm-003 test builders, on top of bdm-002's. Unique values per call: the test database is shared and never truncated."""

from app.models import User
from tests.bdm001_helpers import make_manager
from tests.bdm002_helpers import create_org, make_bdm


async def bdm_of(db, bdm_type: str, manager: User | None = None) -> User:
    return await make_bdm(db, manager or await make_manager(db), bdm_type)


async def profile_org(client, org_type: str, **profile) -> dict:
    return await create_org(client, org_type=org_type, **({"profile": profile} if profile else {}))
