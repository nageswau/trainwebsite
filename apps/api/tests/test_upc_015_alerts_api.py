"""upc-015 -- GET /partnership/alerts (DEC-SCOPE-162 AL12, AL13; spec §6 AC8): the caller's own alerts only, newest first, a kind filter,
paging and the unread count; other roles 403."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest

from app.models import Notification, User
from app.schemas import PartnershipAlertKind
from app.services import partnership_alerts
from tests.upc003_helpers import as_role, login, make_head, make_pm, make_user

ALERTS = "/api/v1/partnership/alerts"


async def note(db, user: User, kind: str, *, read: bool = False, minutes_ago: int = 0, prefix: str = "upc015") -> Notification:
    row = Notification(user_id=user.id, title=f"{kind} alert", body="Body", read=read, action_url="/partnership/tasks?band=overdue",
                       dedupe_key=f"{prefix}:{kind}:{uuid.uuid4()}:{user.id}", created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago))  # fmt: skip
    db.add(row)
    await db.commit()
    return row


def test_the_schema_kinds_match_the_service():
    assert get_args(PartnershipAlertKind) == partnership_alerts.KINDS


@pytest.mark.asyncio
async def test_a_manager_sees_only_their_own_alerts_newest_first_with_the_unread_count(client, db_session):
    head = await make_head(db_session)
    pm, other = await make_pm(db_session, head), await make_pm(db_session, head)
    old = await note(db_session, pm, "agreement_expiry", minutes_ago=10, read=True)
    new = await note(db_session, pm, "milestone_delayed")
    await note(db_session, other, "agreement_expiry")
    await note(db_session, pm, "x", prefix="bdm012")  # someone else's reminder kind is not a partnership alert
    await login(client, pm)
    response = await client.get(ALERTS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [i["id"] for i in body["items"]] == [str(new.id), str(old.id)]
    assert body["items"][0] | {"created_at": None} == {
        "id": str(new.id), "kind": "milestone_delayed", "title": "milestone_delayed alert", "body": "Body", "read": False,
        "action_url": "/partnership/tasks?band=overdue", "created_at": None,
    }  # fmt: skip
    assert (body["total"], body["unread"], body["limit"], body["offset"]) == (2, 1, 25, 0)


@pytest.mark.asyncio
async def test_the_kind_filter_and_paging(client, db_session):
    head = await make_head(db_session)
    for i in range(3):
        await note(db_session, head, "agreement_expiry", minutes_ago=i)
    await note(db_session, head, "overdue_digest")
    await login(client, head)
    body = (await client.get(ALERTS, params={"kind": "agreement_expiry", "limit": 2, "offset": 1})).json()
    assert [i["kind"] for i in body["items"]] == ["agreement_expiry", "agreement_expiry"]
    assert (body["total"], body["unread"]) == (3, 4)
    assert (await client.get(ALERTS, params={"kind": "overdue_digest"})).json()["total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"kind": "bogus"}, {"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_bad_parameters_are_422(client, db_session, params):
    await login(client, await make_head(db_session))
    assert (await client.get(ALERTS, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_super_admin_reads_an_empty_list(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    body = (await client.get(ALERTS)).json()
    assert (body["items"], body["total"], body["unread"]) == ([], 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("counselor", "overseas"), ("partnership_manager", "overseas")])
async def test_other_roles_and_a_manager_without_a_profile_are_403(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))  # make_user gives a manager no profile
    assert (await client.get(ALERTS)).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.get(ALERTS)).status_code == 401


@pytest.mark.asyncio
async def test_reading_an_alert_uses_the_shared_notification_route(client, db_session):
    head = await make_head(db_session)
    row = await note(db_session, head, "agreement_expiry")
    await login(client, head)
    assert (await client.patch(f"/api/v1/workflows/notifications/{row.id}/read")).status_code == 200
    body = (await client.get(ALERTS)).json()
    assert (body["items"][0]["read"], body["unread"]) == (True, 0)
