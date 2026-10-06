"""bdm-008 -- archiving an organization cancels its open items (F6, AC7)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.bdm006_helpers import bdm_with_org
from tests.bdm007_helpers import completed
from tests.bdm008_helpers import TASKS, create_task, insert_task, ist_day, listed

ORGS = "/api/v1/bdm/organizations"


@pytest.mark.asyncio
async def test_archive_cancels_open_items_and_restore_keeps_them_cancelled(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    manual = await create_task(client, organization_id=org["id"])
    a = await completed(client, db_session, org, next_follow_up_on=ist_day(1).isoformat())
    done = await insert_task(db_session, bdm.id, org_id=org["id"], status="done")
    general = await create_task(client)
    assert (await client.post(f"{ORGS}/{org['id']}/archive")).status_code == 200
    cancelled = {t["id"]: t for t in (await listed(client, bucket="cancelled"))["items"]}
    assert {manual["id"], a["follow_up"]["id"]} == set(cancelled) and all(t["cancel_reason"] == "Organization archived" for t in cancelled.values())
    assert [t["id"] for t in (await listed(client, bucket="done"))["items"]] == [str(done.id)]
    assert [t["id"] for t in (await listed(client))["items"]] == [general["id"]]
    meta = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.archive"))).one()
    assert meta == {"tasks_cancelled": 2}
    from tests.bdm001_helpers import login

    await login(client, manager)
    assert (await client.post(f"{ORGS}/{org['id']}/restore")).status_code == 200
    await login(client, bdm)
    assert (await listed(client, bucket="cancelled"))["total"] == 2


@pytest.mark.asyncio
async def test_archive_with_nothing_open_keeps_todays_audit(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    await client.post(f"{ORGS}/{org['id']}/archive")
    meta = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.archive"))).one()
    assert meta == {}


@pytest.mark.asyncio
async def test_complete_after_archive_is_409(client, db_session):
    """Review Focus 3."""
    _, _, org = await bdm_with_org(client, db_session)
    t = await create_task(client, organization_id=org["id"])
    await client.post(f"{ORGS}/{org['id']}/archive")
    r = await client.post(f"{TASKS}/{t['id']}/complete")
    assert (r.status_code, r.json()["detail"]) == (409, "This task was cancelled")
