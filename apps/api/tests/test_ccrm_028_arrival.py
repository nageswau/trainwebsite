"""ccrm-028 (DEC-SCOPE-265) -- arrival and orientation after enrolment: the counselor/Admin `PUT …/arrival` (arrival date, arrival
confirmed -- stamped with who and when --, orientation attended, notes; agency applications too: CC4), the readers' GET, and nothing else
moving (A1)."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api import application_offers
from app.models import AgentCommission, ApplicationStatusHistory, AuditLog
from tests.agn001_helpers import client_for
from tests.agn023_helpers import ASSIGN, assign_world, fresh, history_notes
from tests.ccrm027_helpers import confirm_enrollment

ARRIVAL = "/api/v1/workflows/overseas/applications/{}/arrival"


@pytest_asyncio.fixture
async def world(db_session):
    """Assigned at the offer stage (assignment refuses an enrolled application), then enrolled the real way (ccrm-027)."""
    w = await assign_world(db_session, status="offer")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
            assert (await confirm_enrollment(c, db_session, app)).status_code == 200
    return w


def body(**overrides) -> dict:
    data = {"arrival_date": date.today().isoformat(), "arrival_confirmed": True, "orientation_attended": False, "notes": None}
    return data | overrides


async def _history_count(db, app) -> int:
    return await db.scalar(select(func.count()).select_from(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app.id))


@pytest.mark.asyncio
async def test_the_counselor_records_an_expected_date_then_confirms_arrival_and_orientation(db_session, world):  # AC1, A4
    app = world["direct_app"]
    expected = (date.today() + timedelta(days=10)).isoformat()
    async with client_for(world["counselor"].email) as c:
        first = await c.put(ARRIVAL.format(app.id), json=body(arrival_date=expected, arrival_confirmed=False))
        confirmed = await c.put(ARRIVAL.format(app.id), json=body(orientation_attended=True, notes="Met at the airport; university email"))
        got = (await c.get(ARRIVAL.format(app.id))).json()["arrival"]
    assert first.status_code == 200, first.text
    assert first.json()["arrival"]["arrival_date"] == expected and first.json()["arrival"]["arrival_confirmed"] is False
    assert confirmed.status_code == 200, confirmed.text
    row = await fresh(db_session, app)
    assert (row.arrival_date, row.orientation_attended, row.arrival_notes) == (date.today(), True, "Met at the airport; university email")
    assert row.arrival_confirmed_by_id == world["counselor"].id and row.arrival_confirmed_at is not None
    assert got["arrival_confirmed"] is True and got["confirmed_by"] == world["counselor"].full_name and got["confirmed_at"]
    assert got["can_record"] is True
    notes = await history_notes(db_session, app)
    assert notes[-1] == f"Arrival updated -- arrived {date.today().isoformat()}, orientation attended" and notes[-2] == f"Arrival updated -- expected {expected}"
    audits = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.arrival"))).all()
    assert {"fields": ["arrival_date", "arrival_confirmed", "orientation_attended", "arrival_notes"]} in audits


@pytest.mark.asyncio
async def test_arrival_is_recorded_only_after_enrolment(db_session):  # AC2, A3
    w = await assign_world(db_session, status="offer")
    async with client_for(w["admin"].email) as c:
        r = await c.put(ARRIVAL.format(w["direct_app"].id), json=body())
        got = (await c.get(ARRIVAL.format(w["direct_app"].id))).json()["arrival"]
    assert r.status_code == 422 and r.json()["detail"] == "Arrival is recorded after enrolment is confirmed"
    assert got["can_record"] is False


@pytest.mark.asyncio
async def test_the_rules_on_date_and_orientation(db_session, world):  # AC2, A5
    app = world["direct_app"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    before = await _history_count(db_session, app)
    async with client_for(world["counselor"].email) as c:
        no_date = await c.put(ARRIVAL.format(app.id), json=body(arrival_date=None))
        future = await c.put(ARRIVAL.format(app.id), json=body(arrival_date=tomorrow))
        orientation = await c.put(ARRIVAL.format(app.id), json=body(arrival_confirmed=False, orientation_attended=True))
        typo = await c.put(ARRIVAL.format(app.id), json=body(arrival_date="0202-01-01"))
        extra = await c.put(ARRIVAL.format(app.id), json=body(arrival_confirmed_by_id=str(world["admin"].id)))
    assert (no_date.status_code, no_date.json()["detail"]) == (422, "Enter the arrival date to confirm arrival")
    assert (future.status_code, future.json()["detail"]) == (422, "A confirmed arrival date cannot be in the future")
    assert (orientation.status_code, orientation.json()["detail"]) == (422, "Confirm arrival before recording orientation")
    assert typo.status_code == 422 and extra.status_code == 422
    assert (await fresh(db_session, app)).arrival_date is None and await _history_count(db_session, app) == before


@pytest.mark.asyncio
async def test_unconfirming_clears_the_stamp_and_an_unchanged_save_writes_nothing(db_session, world):  # AC3
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(ARRIVAL.format(app.id), json=body())).status_code == 200
        before = await _history_count(db_session, app)
        same = await c.put(ARRIVAL.format(app.id), json=body())
        assert same.status_code == 200 and same.json()["changed"] is False
        assert await _history_count(db_session, app) == before
        undo = await c.put(ARRIVAL.format(app.id), json=body(arrival_confirmed=False))
    assert undo.status_code == 200 and undo.json()["changed"] is True
    row = await fresh(db_session, app)
    assert row.arrival_confirmed_at is None and row.arrival_confirmed_by_id is None and row.arrival_date == date.today()
    assert (await history_notes(db_session, app))[-1] == f"Arrival updated -- expected {date.today().isoformat()}"


@pytest.mark.asyncio
async def test_agency_application_counselor_scope_admin_and_agency_told(db_session, world, monkeypatch):  # AC4, CC4, CC5
    app = world["app"]
    told = []

    async def details_changed(db, application, actor):
        told.append((application.id, actor.id))

    monkeypatch.setattr(application_offers.agency_notices, "details_changed", details_changed)
    async with client_for(world["counselor2"].email) as c:
        assert (await c.put(ARRIVAL.format(app.id), json=body())).status_code == 403
    async with client_for(world["counselor"].email) as c:
        r = await c.put(ARRIVAL.format(app.id), json=body())
    assert r.status_code == 200, r.text
    assert told == [(app.id, world["counselor"].id)]  # the CC5 notice (its recipients: test_ccrm_013_application_fields)
    async with client_for(world["admin"].email) as c:
        r = await c.put(ARRIVAL.format(app.id), json=body(orientation_attended=True))
    assert r.status_code == 200
    row = await fresh(db_session, app)
    assert row.orientation_attended is True and row.arrival_confirmed_by_id == world["counselor"].id  # stamp kept while still confirmed


@pytest.mark.asyncio
async def test_student_and_agent_read_but_cannot_write(db_session, world):  # AC5
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(ARRIVAL.format(world["direct_app"].id), json=body())).status_code == 200
    async with client_for(world["direct_student"].email) as c:
        got = await c.get(ARRIVAL.format(world["direct_app"].id))
        put = await c.put(ARRIVAL.format(world["direct_app"].id), json=body())
        other = await c.get(ARRIVAL.format(world["app"].id))
    assert got.status_code == 200 and got.json()["arrival"]["arrival_confirmed"] is True and put.status_code == 403
    assert other.status_code in (403, 404)
    async with client_for(world["master"].email) as c:
        assert (await c.get(ARRIVAL.format(world["app"].id))).status_code == 200
        assert (await c.put(ARRIVAL.format(world["app"].id), json=body())).status_code == 403


@pytest.mark.asyncio
async def test_recording_arrival_moves_nothing_else(db_session, world):  # AC6, A1
    app = world["app"]
    before = await fresh(db_session, app)
    state = (before.status, before.sub_status, before.outcome)
    commissions = await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == app.id))
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(ARRIVAL.format(app.id), json=body(orientation_attended=True))).status_code == 200
    after = await fresh(db_session, app)
    assert (after.status, after.sub_status, after.outcome) == state
    assert await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == app.id)) == commissions
