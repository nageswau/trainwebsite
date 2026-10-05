"""bdm-006 -- bdm-002's Last / Next meeting become real (AC9; spec §5.6, §12.1 R-A9)."""

import uuid

import pytest
from sqlalchemy import event

from app.core.database import engine
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm006_helpers import APPTS, bdm_with_org, create_appt, future, move_to_past


@pytest.mark.asyncio
async def test_values_on_list_and_detail(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    blank = (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]
    assert blank["last_meeting_at"] is None and blank["next_meeting_at"] is None  # bdm-002 AC6 still true without appointments
    done = await create_appt(client, org, starts_at=future(10))
    await move_to_past(db_session, done["id"], minutes=120)
    await client.post(f"{APPTS}/{done['id']}/complete", json={"outcome": "interested", "discussion": "Met"})
    stale = await create_appt(client, org, starts_at=future(20))
    await move_to_past(db_session, stale["id"], minutes=30)  # open but past: not "next"
    cancelled = await create_appt(client, org, starts_at=future(30))
    await client.post(f"{APPTS}/{cancelled['id']}/cancel", json={"reason": "x"})
    upcoming = await create_appt(client, org, starts_at=future(40))
    later = await create_appt(client, org, starts_at=future(60))
    detail = (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]
    done_at = (await client.get(f"{APPTS}/{done['id']}")).json()["appointment"]["starts_at"]
    assert detail["last_meeting_at"] == done_at
    assert detail["next_meeting_at"] == upcoming["starts_at"] != later["starts_at"]
    row = next(r for r in (await client.get(ORGS, params={"q": org["code"]})).json()["items"] if r["id"] == org["id"])
    assert (row["last_meeting_at"], row["next_meeting_at"]) == (detail["last_meeting_at"], detail["next_meeting_at"])


@pytest.mark.asyncio
async def test_list_query_count_does_not_grow_with_rows(client, db_session):
    await bdm_with_org(client, db_session)
    prefix = f"Meet{uuid.uuid4().hex[:6]}"
    one = await create_org(client, name=f"{prefix}A only")
    for i in range(5):
        org = await create_org(client, name=f"{prefix}B {i}")
        await create_appt(client, org, starts_at=future(10 + i))
    await create_appt(client, one, starts_at=future(30))
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        statements.clear()
        assert (await client.get(ORGS, params={"q": f"{prefix}A"})).json()["total"] == 1
        single = len(statements)
        statements.clear()
        assert (await client.get(ORGS, params={"q": f"{prefix}B"})).json()["total"] == 5
        assert len(statements) == single
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
