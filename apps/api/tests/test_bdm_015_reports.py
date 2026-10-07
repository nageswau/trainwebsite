"""bdm-015 -- the BDM's own daily report: live preview, submit, snapshot (spec §5; AC1-AC3, negative scenarios)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmDailyReport
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import login, make_user
from tests.bdm009_helpers import bdm_with_org
from tests.bdm015_helpers import activity, by_key, inside, report_url, submit_url


async def _bdm(client, db, bdm_type: str = "college"):
    manager, bdm, org = await bdm_with_org(client, db, bdm_type)
    return manager, bdm, org


@pytest.mark.asyncio
async def test_today_is_a_live_draft_preview_of_the_bdms_type(client, db_session):
    _, bdm, _ = await _bdm(client, db_session, "school")
    response = await client.get(report_url(india_today()))
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["status"], data["submitted_at"], data["note"], data["manager_comment"]) == ("draft", None, None, None)
    assert data["bdm"] == {"id": str(bdm.id), "full_name": bdm.full_name}
    assert data["bdm_type"] == "school" and data["can_submit"] is True and data["submit_window_days"] == 7
    assert [c["key"] for c in data["counts"]][:2] == ["schools_contacted", "calls_made"]
    assert not await db_session.scalar(select(BdmDailyReport).where(BdmDailyReport.bdm_user_id == bdm.id))  # a preview stores nothing


@pytest.mark.asyncio
async def test_a_future_day_is_422_and_an_old_day_is_read_only(client, db_session):
    await _bdm(client, db_session)
    assert (await client.get(report_url(india_today() + timedelta(days=1)))).status_code == 422
    old = (await client.get(report_url(india_today() - timedelta(days=8)))).json()
    assert old["status"] == "draft" and old["can_submit"] is False
    assert (await client.get(report_url(india_today() - timedelta(days=7)))).json()["can_submit"] is True


@pytest.mark.asyncio
async def test_submit_snapshots_the_counts_with_the_note_and_is_audited(client, db_session):
    _, bdm, org = await _bdm(client, db_session)
    day = india_today() - timedelta(days=1)
    await activity(db_session, bdm.id, org["id"], inside(day))
    response = await client.post(submit_url(day), json={"note": "  Met two principals.  "})
    assert response.status_code == 201, response.text
    data = response.json()
    assert (data["status"], data["note"], data["can_submit"]) == ("submitted", "Met two principals.", False)
    assert data["submitted_at"] is not None
    assert by_key(data["counts"])["calls_made"] == 1
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "bdm_daily_report.submitted", AuditLog.user_id == bdm.id))
    assert audit is not None and audit.metadata_json == {"report_date": str(day)}  # never the note


@pytest.mark.asyncio
async def test_a_second_submit_for_the_same_day_is_409(client, db_session):
    await _bdm(client, db_session)
    assert (await client.post(submit_url(india_today()), json={})).status_code == 201
    response = await client.post(submit_url(india_today()), json={"note": "again"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_the_snapshot_is_unchanged_by_later_record_edits(client, db_session):
    _, bdm, org = await _bdm(client, db_session)
    day = india_today() - timedelta(days=2)
    await activity(db_session, bdm.id, org["id"], inside(day))
    assert (await client.post(submit_url(day), json={})).status_code == 201
    await activity(db_session, bdm.id, org["id"], inside(day, 11))  # written straight to the table, past every API lock
    data = (await client.get(report_url(day))).json()
    assert data["status"] == "submitted" and by_key(data["counts"])["calls_made"] == 1


@pytest.mark.asyncio
async def test_a_day_with_no_activity_can_be_submitted_with_a_note(client, db_session):
    await _bdm(client, db_session, "agent")
    response = await client.post(submit_url(india_today()), json={"note": "On leave"})
    assert response.status_code == 201
    counts = by_key(response.json()["counts"])
    assert counts["new_agents"] == "not tracked" and counts["calls_made"] == 0


@pytest.mark.asyncio
async def test_submit_window_future_and_bad_bodies_are_422(client, db_session):
    await _bdm(client, db_session)
    assert (await client.post(submit_url(india_today() + timedelta(days=1)), json={})).status_code == 422
    assert (await client.post(submit_url(india_today() - timedelta(days=8)), json={})).status_code == 422
    assert (await client.post(submit_url(india_today()), json={"note": "x" * 2001})).status_code == 422
    assert (await client.post(submit_url(india_today()), json={"counts": []})).status_code == 422
    assert (await client.post(submit_url(india_today() - timedelta(days=7)), json={})).status_code == 201


@pytest.mark.asyncio
async def test_other_roles_cannot_read_or_submit_a_bdm_report(client, db_session):
    manager, _, _ = await _bdm(client, db_session)
    for user in (manager, await make_user(db_session, "super_admin", "global"), await make_user(db_session, "student", "it")):
        client.cookies.clear()
        await login(client, user)
        assert (await client.post(submit_url(india_today()), json={})).status_code == 403  # no one submits for another BDM
        assert (await client.get(report_url(india_today()))).status_code == 403
    client.cookies.clear()
    assert (await client.get(report_url(india_today()))).status_code == 401
