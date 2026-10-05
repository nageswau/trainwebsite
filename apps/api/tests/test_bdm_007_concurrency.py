"""bdm-007 -- races (spec §6; Review Focus 3). Two real sessions through the app (bdm-006 pattern)."""

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

from app.core.database import SessionLocal
from app.main import app
from app.models import BdmMeetingReport, BdmTask
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, bdm_with_org, create_appt, move_to_past
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


@pytest.mark.asyncio
async def test_a_complete_waiting_on_the_row_lock_gets_409_not_500(client, db_session):
    """Review Focus 3, deterministic: another transaction holds the appointment's row lock and completes it (status, outcome, report).
    The request must wait on the lock and then see `completed` (409). Without the lock it would insert a second report and hit
    uq_bdm_meeting_reports_appointment (500)."""
    _, bdm, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    await move_to_past(db_session, a["id"])
    async with SessionLocal() as holder:
        await holder.execute(text("SELECT id FROM bdm_appointments WHERE id = :id FOR UPDATE"), {"id": uuid.UUID(a["id"])})
        await holder.execute(text("UPDATE bdm_appointments SET status = 'completed', outcome = 'interested' WHERE id = :id"), {"id": uuid.UUID(a["id"])})
        holder.add(BdmMeetingReport(appointment_id=uuid.UUID(a["id"]), author_user_id=bdm.id, discussion="Filed elsewhere"))
        await holder.flush()
        pending = asyncio.create_task(client.post(f"{APPTS}/{a['id']}/complete", json=REPORT))
        await asyncio.sleep(1.0)
        assert not pending.done()  # waiting on the row lock
        await holder.commit()
    response = await pending
    assert (response.status_code, response.json()["detail"]) == (409, "Appointment is already completed")
    assert await _count(db_session, BdmMeetingReport, BdmMeetingReport.appointment_id, a["id"]) == 1
