"""tel-019 -- the BDM side of meeting requests (spec §3; DEC-SCOPE-097 MR1-MR3, MR9, MR11, MR12): scope, accept into exactly one
bdm-006 appointment, decline with a reason. Pool requests from other tests are visible too, so assertions use the ids a test made."""

import uuid

import pytest
from sqlalchemy import func, select, update

from app.models import AuditLog, BdmAppointment, BdmMeetingRequest
from tests.bdm006_helpers import APPTS
from tests.tel019_helpers import (
    BDM,
    TEL,
    accept_body,
    accept_url,
    as_user,
    at,
    bdm_with_org,
    decline_url,
    file_request,
    make_bdm,
    make_manager,
    make_user,
    telecaller,
)


async def _ids(client, **params) -> set[str]:
    """Every id the caller can list, page by page (the shared database keeps every earlier test's pool requests)."""
    ids: set[str] = set()
    while True:
        response = await client.get(BDM, params={"limit": 100, "offset": len(ids), **params})
        assert response.status_code == 200, response.text
        page = response.json()
        ids |= {r["id"] for r in page["items"]}
        if len(ids) >= page["total"] or not page["items"]:
            return ids


async def _ordered(client) -> list[str]:
    items: list[str] = []
    while True:
        page = (await client.get(BDM, params={"limit": 100, "offset": len(items)})).json()
        items += [r["id"] for r in page["items"]]
        if len(items) >= page["total"] or not page["items"]:
            return items


async def _appointments_for(db, request_id) -> int:
    row = await db.scalar(select(BdmMeetingRequest).where(BdmMeetingRequest.id == uuid.UUID(request_id)).execution_options(populate_existing=True))
    if row.bdm_appointment_id is None:
        return 0
    return await db.scalar(select(func.count()).select_from(BdmAppointment).where(BdmAppointment.id == row.bdm_appointment_id))


# --- scope (AC1, MR11, MR3) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_corporate_request_reaches_college_bdms_only(client, db_session):
    req = await file_request(client, await telecaller(db_session), request_type="corporate")
    manager = await make_manager(db_session)
    for bdm_type, visible in (("college", True), ("agent", False), ("school", False)):
        await as_user(client, await make_bdm(db_session, manager, bdm_type))
        assert (req["id"] in await _ids(client)) is visible, bdm_type
        assert (await client.get(f"{BDM}/{req['id']}")).status_code == (200 if visible else 404)


@pytest.mark.asyncio
async def test_a_named_request_is_only_for_its_bdm(client, db_session):
    manager = await make_manager(db_session)
    named, peer = await make_bdm(db_session, manager, "college"), await make_bdm(db_session, manager, "college")
    req = await file_request(client, await telecaller(db_session), bdm_user_id=str(named.id))
    await as_user(client, peer)
    assert req["id"] not in await _ids(client)
    assert (await client.get(f"{BDM}/{req['id']}")).status_code == 404
    await as_user(client, named)
    detail = (await client.get(f"{BDM}/{req['id']}")).json()
    assert detail["permissions"] == {"can_accept": True, "can_decline": True}


@pytest.mark.asyncio
async def test_a_manager_sees_their_team_and_the_pool_and_super_admin_sees_all(client, db_session):
    mine, other = await make_manager(db_session), await make_manager(db_session)
    team_bdm, other_bdm = await make_bdm(db_session, mine, "school"), await make_bdm(db_session, other, "school")
    tel = await telecaller(db_session)
    for_team = await file_request(client, tel, request_type="school", bdm_user_id=str(team_bdm.id))
    for_other = await file_request(client, tel, request_type="school", bdm_user_id=str(other_bdm.id))
    pool = await file_request(client, tel, request_type="agent")
    await as_user(client, mine)
    seen = await _ids(client)
    assert for_team["id"] in seen and pool["id"] in seen and for_other["id"] not in seen
    assert (await client.get(f"{BDM}/{for_other['id']}")).status_code == 404
    detail = (await client.get(f"{BDM}/{for_team['id']}")).json()
    assert detail["permissions"] == {"can_accept": False, "can_decline": False}
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert {for_team["id"], for_other["id"], pool["id"]} <= await _ids(client)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["telecaller", "counselor"])
async def test_other_roles_cannot_read_the_bdm_inbox(client, db_session, role):
    user = await telecaller(db_session) if role == "telecaller" else await make_user(db_session, role, "it")
    await as_user(client, user)
    assert (await client.get(BDM)).status_code == 403


@pytest.mark.asyncio
async def test_the_inbox_lists_pending_first_soonest_first(client, db_session):
    tel = await telecaller(db_session)
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager, "agent")
    later = await file_request(client, tel, request_type="agent", bdm_user_id=str(bdm.id), proposed_at=at(days=5))
    sooner = await file_request(client, tel, request_type="agent", bdm_user_id=str(bdm.id), proposed_at=at(days=1))
    await as_user(client, bdm)
    assert (await client.post(decline_url(sooner["id"]), json={"reason": "Not my territory"})).status_code == 200
    soonest = await file_request(client, tel, request_type="agent", bdm_user_id=str(bdm.id), proposed_at=at(hours=2, days=0))
    await as_user(client, bdm)
    items = await _ordered(client)
    assert items.index(soonest["id"]) < items.index(later["id"]) < items.index(sooner["id"])
    assert sooner["id"] not in await _ids(client, status="pending")


# --- accept (AC2, MR9) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_school_bdm_accepts_a_school_request_into_exactly_one_appointment(client, db_session):
    tel = await telecaller(db_session)
    req = await file_request(client, tel, request_type="school")
    _, bdm, org = await bdm_with_org(client, db_session, "school")
    response = await client.post(accept_url(req["id"]), json=accept_body(org, appointment_type="school_meeting", purpose="From telecaller"))
    assert response.status_code == 200, response.text
    out = response.json()
    appt, mr = out["appointment"], out["meeting_request"]
    assert appt["organization"]["id"] == org["id"] and appt["status"] == "scheduled" and appt["bdm"]["id"] == str(bdm.id)
    assert appt["appointment_type"] == "school_meeting" and appt["purpose"] == "From telecaller"
    assert mr["status"] == "accepted" and mr["bdm"]["id"] == str(bdm.id) and mr["decided_at"] is not None
    assert mr["appointment"]["id"] == appt["id"] and mr["appointment"]["code"] == appt["code"]
    assert mr["permissions"] == {"can_accept": False, "can_decline": False}
    assert await _appointments_for(db_session, req["id"]) == 1
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id.in_([req["id"], appt["id"]])))).all())
    assert {"bdm_meeting_request.create", "bdm_meeting_request.accept", "bdm_appointment.create"} <= actions
    # the telecaller now sees it accepted, with the appointment
    await as_user(client, tel)
    mine = {r["id"]: r for r in (await client.get(TEL)).json()["items"]}
    assert mine[req["id"]]["status"] == "accepted" and mine[req["id"]]["appointment"]["code"] == appt["code"]


@pytest.mark.asyncio
async def test_a_second_accept_is_409_and_creates_nothing(client, db_session):
    req = await file_request(client, await telecaller(db_session))
    _, _, org = await bdm_with_org(client, db_session)
    assert (await client.post(accept_url(req["id"]), json=accept_body(org))).status_code == 200
    again = await client.post(accept_url(req["id"]), json=accept_body(org, starts_at=at(days=4)))
    assert again.status_code == 409 and "already accepted" in again.text
    assert await _appointments_for(db_session, req["id"]) == 1


@pytest.mark.asyncio
async def test_a_pool_request_taken_by_one_bdm_is_gone_for_the_others(client, db_session):
    req = await file_request(client, await telecaller(db_session))
    manager = await make_manager(db_session)
    _, _, org = await bdm_with_org(client, db_session, manager=manager)
    assert (await client.post(accept_url(req["id"]), json=accept_body(org))).status_code == 200
    _, _, other_org = await bdm_with_org(client, db_session, manager=manager)
    assert req["id"] not in await _ids(client)
    assert (await client.post(accept_url(req["id"]), json=accept_body(other_org))).status_code == 404


@pytest.mark.asyncio
async def test_an_agent_bdm_accepting_a_college_request_gets_404(client, db_session):
    req = await file_request(client, await telecaller(db_session), request_type="college")
    _, _, org = await bdm_with_org(client, db_session, "agent")
    response = await client.post(accept_url(req["id"]), json=accept_body(org, appointment_type="agent_meeting"))
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_a_request_accepted_after_its_proposed_time_takes_a_new_future_start(client, db_session):
    req = await file_request(client, await telecaller(db_session))
    await db_session.execute(update(BdmMeetingRequest).where(BdmMeetingRequest.id == uuid.UUID(req["id"])).values(proposed_at=func.now() - func.make_interval(0, 0, 0, 1)))
    await db_session.commit()
    _, _, org = await bdm_with_org(client, db_session)
    past = await client.post(accept_url(req["id"]), json=accept_body(org, starts_at=at(days=-1)))
    assert past.status_code == 422 and "Choose a time in the future" in past.text
    assert (await client.post(accept_url(req["id"]), json=accept_body(org))).status_code == 200


@pytest.mark.asyncio
async def test_a_bdm_006_refusal_leaves_the_request_pending(client, db_session):
    req = await file_request(client, await telecaller(db_session))
    _, _, org = await bdm_with_org(client, db_session)
    start = at(days=3)
    booked = await client.post(APPTS, json=accept_body(org, starts_at=start))
    assert booked.status_code == 201, booked.text
    clash = await client.post(accept_url(req["id"]), json=accept_body(org, starts_at=start))
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "possible_overlap"
    detail = (await client.get(f"{BDM}/{req['id']}")).json()
    assert detail["status"] == "pending" and detail["appointment"] is None and await _appointments_for(db_session, req["id"]) == 0
    confirmed = await client.post(accept_url(req["id"]), json=accept_body(org, starts_at=start, confirm_overlap=True))
    assert confirmed.status_code == 200, confirmed.text


@pytest.mark.asyncio
async def test_a_foreign_organization_is_refused_by_bdm_006s_rule(client, db_session):
    req = await file_request(client, await telecaller(db_session))
    _, _, org = await bdm_with_org(client, db_session)
    await bdm_with_org(client, db_session)  # now logged in as another college BDM, who doesn't own `org`
    response = await client.post(accept_url(req["id"]), json=accept_body(org))
    assert response.status_code == 403 and "Only the assigned BDM" in response.text
    assert (await client.get(f"{BDM}/{req['id']}")).json()["status"] == "pending"


@pytest.mark.asyncio
async def test_a_manager_cannot_accept_or_decline(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager)
    req = await file_request(client, await telecaller(db_session), bdm_user_id=str(bdm.id))
    await as_user(client, manager)
    assert (await client.post(accept_url(req["id"]), json={"organization_id": str(uuid.uuid4()), "contact_id": str(uuid.uuid4()),
                                                           "starts_at": at(), "appointment_type": "college_meeting"})).status_code == 403
    assert (await client.post(decline_url(req["id"]), json={"reason": "No"})).status_code == 403


# --- decline (AC3, MR2) --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"reason": "   "}, {"reason": "x" * 501}])
async def test_a_decline_requires_a_reason(client, db_session, payload):
    req = await file_request(client, await telecaller(db_session))
    await bdm_with_org(client, db_session)
    response = await client.post(decline_url(req["id"]), json=payload)
    assert response.status_code == 422, response.text
    assert (await client.get(f"{BDM}/{req['id']}")).json()["status"] == "pending"


@pytest.mark.asyncio
async def test_a_decline_is_final_and_the_telecaller_sees_the_reason(client, db_session):
    tel = await telecaller(db_session)
    req = await file_request(client, tel, request_type="corporate")
    _, bdm, org = await bdm_with_org(client, db_session)
    response = await client.post(decline_url(req["id"]), json={"reason": "Corporate tie-ups paused this quarter"})
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "declined" and out["decline_reason"] == "Corporate tie-ups paused this quarter" and out["bdm"]["id"] == str(bdm.id)
    assert (await client.post(accept_url(req["id"]), json=accept_body(org))).status_code == 409
    assert (await client.post(decline_url(req["id"]), json={"reason": "Again"})).status_code == 409
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == req["id"], AuditLog.action == "bdm_meeting_request.decline"))
    assert audit is not None and "paused" not in str(audit.metadata_json)
    await as_user(client, tel)
    mine = {r["id"]: r for r in (await client.get(TEL)).json()["items"]}
    assert mine[req["id"]]["status"] == "declined" and mine[req["id"]]["decline_reason"] == "Corporate tie-ups paused this quarter"
