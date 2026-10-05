"""bdm-007 -- races (spec §6; Review Focus 3). Two real sessions through the app (bdm-006 pattern)."""

import asyncio
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmMeetingReport, BdmTask
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, create_appt, move_to_past
from tests.bdm007_helpers import REPORT, completed


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def in_days(n: int) -> str:
    return (datetime.now(IST) + timedelta(days=n)).date().isoformat()


async def _count(db, model, column, appt_id) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(column == appt_id))


@pytest.mark.asyncio
async def test_double_complete_files_one_report(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        a = await create_appt(one, await create_org(one))
        await move_to_past(db_session, a["id"])
        body = {**REPORT, "next_follow_up_on": in_days(2)}
        results = await asyncio.gather(one.post(f"{APPTS}/{a['id']}/complete", json=body), two.post(f"{APPTS}/{a['id']}/complete", json=body))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert await _count(db_session, BdmMeetingReport, BdmMeetingReport.appointment_id, a["id"]) == 1
    assert await _count(db_session, BdmTask, BdmTask.source_appointment_id, a["id"]) == 1


@pytest.mark.asyncio
async def test_complete_and_cancel_race_never_leaves_a_report_on_a_cancelled_appointment(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        a = await create_appt(one, await create_org(one))
        await move_to_past(db_session, a["id"])
        done, cancel = await asyncio.gather(one.post(f"{APPTS}/{a['id']}/complete", json=REPORT), two.post(f"{APPTS}/{a['id']}/cancel", json={"reason": "Clash"}))
    assert sorted((done.status_code, cancel.status_code)) == [200, 409]
    assert await _count(db_session, BdmMeetingReport, BdmMeetingReport.appointment_id, a["id"]) == (1 if done.status_code == 200 else 0)


@pytest.mark.asyncio
async def test_two_edits_of_the_follow_up_keep_one_row(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        a = await completed(one, db_session, await create_org(one), next_follow_up_on=in_days(2))
        url = f"{APPTS}/{a['id']}/report"
        results = await asyncio.gather(one.patch(url, json={"next_follow_up_on": None}), two.patch(url, json={"next_follow_up_on": in_days(6)}))
    assert all(r.status_code == 200 for r in results)
    assert await _count(db_session, BdmTask, BdmTask.source_appointment_id, a["id"]) == 1
