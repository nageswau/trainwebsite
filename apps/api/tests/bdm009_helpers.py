"""bdm-009 test builders. Unique values per call: the test database is shared and never truncated."""

from datetime import UTC, datetime, timedelta

from app.models import BdmActivity, User
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm

ACTIVITIES = "/api/v1/bdm/activities"
TEAM_ACTIVITIES = "/api/v1/bdm/manager/activities"


def org_activities(org_id) -> str:
    return f"/api/v1/bdm/organizations/{org_id}/activities"


async def bdm_with_org(client, db, bdm_type: str = "college", **org_over) -> tuple[User, User, dict]:
    """A manager, one BDM reporting to them, and an organization assigned to that BDM. Leaves the client signed in as the BDM."""
    manager = await make_manager(db)
    bdm = await make_bdm(db, manager, bdm_type)
    client.cookies.clear()
    await login(client, bdm)
    org = await create_org(client, org_type=bdm_type, **org_over)  # college / school / agent are all organization types
    return manager, bdm, org


def activity_body(org_id, **over) -> dict:
    body = {"organization_id": str(org_id), "channel": "call", "direction": "outbound",
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    body.update(over)
    return body


async def add_activity(db, bdm_id, org_id, occurred_at: datetime, channel: str = "call", direction: str | None = "outbound",
                       contact_id=None, contact_name: str | None = None) -> BdmActivity:
    """A row written straight to the table (past days, boundary instants) -- the API's time window doesn't apply."""
    activity = BdmActivity(bdm_user_id=bdm_id, organization_id=org_id, channel=channel, direction=direction, occurred_at=occurred_at,
                           contact_id=contact_id, contact_name=contact_name)
    db.add(activity)
    await db.commit()
    return activity
