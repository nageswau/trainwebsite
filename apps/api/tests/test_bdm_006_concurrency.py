"""bdm-006 -- races (spec §5.7; Review Focus 2). Two real sessions through the app, the bdm-002 pattern."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmAppointment, BdmAppointmentEvent
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm006_helpers import APPTS, appt_payload, create_appt


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_confirm_and_cancel_race(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        org = await create_org(one)
        a = await create_appt(one, org)
        results = await asyncio.gather(one.post(f"{APPTS}/{a['id']}/confirm"), two.post(f"{APPTS}/{a['id']}/cancel", json={"reason": "Clash"}))
    codes = sorted(r.status_code for r in results)
    assert codes in ([200, 200], [200, 409])  # confirm then cancel is legal; cancel then confirm is 409
    events = await db_session.scalar(select(func.count()).select_from(BdmAppointmentEvent).where(BdmAppointmentEvent.appointment_id == a["id"]))
    assert events == 1 + codes.count(200)
    final = await db_session.scalar(select(BdmAppointment.status).where(BdmAppointment.id == a["id"]).execution_options(populate_existing=True))
    assert final == "cancelled"  # in both orders the cancel lands (or was the only success)


@pytest.mark.asyncio
async def test_archive_and_create_serialize(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        org = await create_org(one)
        archive, create = await asyncio.gather(one.post(f"{ORGS}/{org['id']}/archive"), two.post(APPTS, json=appt_payload(org)))
    assert archive.status_code == 200
    assert create.status_code in (201, 422), create.text  # never a 500


@pytest.mark.asyncio
async def test_contact_switch_and_contact_delete_race(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        org = await create_org(one, contacts=[{"name": "Dr Rao", "is_primary": True}, {"name": "Ms Iyer"}])
        rao, iyer = org["contacts"]
        a = await create_appt(one, org, contact_id=rao["id"])
        patch, delete = await asyncio.gather(
            one.patch(f"{APPTS}/{a['id']}", json={"contact_id": iyer["id"]}),
            two.delete(f"{ORGS}/{org['id']}/contacts/{iyer['id']}"),
        )
    assert delete.status_code == 200
    assert patch.status_code in (200, 422), patch.text  # never a 500
    row = await db_session.scalar(select(BdmAppointment).where(BdmAppointment.id == a["id"]).execution_options(populate_existing=True))
    if patch.status_code == 200:  # switched first, then the delete nulled the link and kept the Iyer snapshot
        assert row.contact_id is None and row.contact_name == "Ms Iyer"
    else:  # the delete won; the switch was refused and the booking still points at Dr Rao
        assert str(row.contact_id) == rao["id"] and row.contact_name == "Dr Rao"
