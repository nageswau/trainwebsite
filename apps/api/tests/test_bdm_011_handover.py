"""bdm-011 x bdm-025: an appointment handed to another BDM leaves its trip -- trips never move, and an appointment and its trip
must belong to the same BDM (backlog bdm-011 authorization impact)."""

import pytest

from app.models import BdmAppointment
from tests.bdm025_helpers import appt, as_super, deactivate, fresh, org, team, trip


@pytest.mark.asyncio
async def test_a_handed_over_appointment_is_unlinked_from_the_old_bdms_trip(client, db_session):
    _, a, b = await team(db_session)
    a_trip = await trip(db_session, a, approval="approved", travel="in_progress")
    moved = await appt(db_session, a, await org(db_session, a), hours=24)
    moved.trip_id = a_trip.id
    await db_session.commit()
    await as_super(client, db_session)
    response = await deactivate(client, a.id, {"mode": "reassign", "reassign_to": str(b.id)})
    assert response.status_code == 200, response.text
    after = await fresh(db_session, BdmAppointment, moved.id)
    assert (after.bdm_user_id, after.trip_id) == (b.id, None)


@pytest.mark.asyncio
async def test_leaving_the_work_with_the_bdm_keeps_the_link(client, db_session):
    _, a, _ = await team(db_session)
    a_trip = await trip(db_session, a, approval="approved", travel="in_progress")
    kept = await appt(db_session, a, await org(db_session, a), hours=24)
    kept.trip_id = a_trip.id
    await db_session.commit()
    await as_super(client, db_session)
    assert (await deactivate(client, a.id, {"mode": "leave"})).status_code == 200
    assert (await fresh(db_session, BdmAppointment, kept.id)).trip_id == a_trip.id
