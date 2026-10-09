"""upc-011 -- partnership events (spec §1 CL2-CL7, CL14; §3)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.services.bdm_travel import india_today
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url

EVENTS = "/api/v1/partnership/events"


def event_url(event_id, action: str | None = None) -> str:
    return f"{EVENTS}/{event_id}" + (f"/{action}" if action else "")


def day(offset: int) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


def body(**overrides) -> dict:
    out = {"kind": "education_fair", "title": "QS Higher Education Fair", "starts_on": day(5), "ends_on": day(7), "location": "Delhi, Pragati Maidan"}
    out.update(overrides)
    return out


async def add(client, expected: int = 201, **overrides) -> dict:
    response = await client.post(EVENTS, json=body(**overrides))
    assert response.status_code == expected, response.text
    return response.json()["event"] if expected == 201 else response.json()


async def _team(db):
    head = await make_head(db)
    return head, await make_pm(db, head), await make_pm(db, head)


# --- create (CL2-CL5) -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_education_fair_without_university_stores_every_field(client, db_session):
    head, pm, other = await _team(db_session)
    await login(client, pm)
    e = await add(client, participant_user_ids=[str(other.id)], notes="Stall 14")
    assert e["code"].startswith("PEV-") and e["kind"] == "education_fair" and e["status"] == "scheduled"
    assert e["title"] == "QS Higher Education Fair" and e["university"] is None
    assert (e["starts_on"], e["ends_on"]) == (day(5), day(7)) and e["location"] == "Delhi, Pragati Maidan" and e["notes"] == "Stall 14"
    assert e["owner"]["id"] == str(pm.id) and e["created_by"]["id"] == str(pm.id)
    assert [p["id"] for p in e["participants"]] == [str(other.id)]
    assert e["overlaps"] == [] and e["permissions"] == {"can_edit": True, "can_cancel": True}
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == e["id"]))).all()
    assert [a.action for a in audit] == ["partnership_event.create"]
    assert "Stall 14" not in str(audit[0].metadata_json) and "QS Higher" not in str(audit[0].metadata_json)
    assert (await client.get(event_url(e["id"]))).json()["event"]["id"] == e["id"]


@pytest.mark.asyncio
async def test_event_may_name_any_active_university(client, db_session):
    head, pm, _ = await _team(db_session)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db_session)).id)
    await login(client, pm)  # not the university's manager: an event is not a write on the university (CL2)
    e = await add(client, kind="mou_signing", title="MoU signing", university_id=uni["id"], starts_on=day(3), ends_on=day(3))
    assert e["university"] == {"id": uni["id"], "name": uni["name"]}
    await add(client, 422, university_id="00000000-0000-0000-0000-000000000000")
    await login(client, head)
    assert (await client.post(url(uni["id"], "deactivate"))).status_code == 200
    await login(client, pm)
    await add(client, 422, university_id=uni["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"starts_on": day(-1)},  # CL3: today or later
        {"starts_on": day(5), "ends_on": day(4)},  # ends before it starts
        {"starts_on": day(1), "ends_on": day(32)},  # CL2: span > 31 days
        {"kind": "trade_show"},
        {"title": "  "},
        {"surprise": True},  # unknown keys
    ],
)
async def test_invalid_events_are_422(client, db_session, overrides):
    _, pm, _ = await _team(db_session)
    await login(client, pm)
    await add(client, 422, **overrides)


@pytest.mark.asyncio
async def test_today_and_a_31_day_span_are_allowed(client, db_session):
    _, pm, _ = await _team(db_session)
    await login(client, pm)
    await add(client, starts_on=day(0), ends_on=day(30))


@pytest.mark.asyncio
async def test_owner_and_employee_rules(client, db_session):
    """CL4/CL5: a manager owns their own events; a head picks themselves or an active direct report; employees are active staff."""
    head, pm, other = await _team(db_session)
    stranger_head = await make_head(db_session)
    inactive = await make_pm(db_session, head, active=False)
    await login(client, pm)
    await add(client, 422, owner_user_id=str(other.id))
    await add(client, 422, participant_user_ids=[str(pm.id)])  # the owner is not an "other" employee
    await add(client, 422, participant_user_ids=[str(inactive.id)])
    twice = await add(client, participant_user_ids=[str(other.id)] * 2)  # a repeated pick is one pick (upc-010 idiom)
    assert [p["id"] for p in twice["participants"]] == [str(other.id)]
    await login(client, head)
    assert (await add(client, owner_user_id=str(pm.id)))["owner"]["id"] == str(pm.id)
    assert (await add(client))["owner"]["id"] == str(head.id)
    await add(client, 422, owner_user_id=str(stranger_head.id))


@pytest.mark.asyncio
async def test_roles(client, db_session):
    """CL7: other roles 403 on read and write; super_admin reads only."""
    _, pm, _ = await _team(db_session)
    await login(client, pm)
    e = await add(client)
    for role, division in (("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.post(EVENTS, json=body())).status_code == 403, role
        assert (await client.get(event_url(e["id"]))).status_code == 403, role
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(event_url(e["id"]))).json()["event"]["permissions"] == {"can_edit": False, "can_cancel": False}
    assert (await client.post(EVENTS, json=body())).status_code == 403
    assert (await client.get(event_url("00000000-0000-0000-0000-000000000000"))).status_code == 404


# --- edit and cancel (CL6, CL7) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_owner_edits_and_others_cannot(client, db_session):
    head, pm, other = await _team(db_session)
    await login(client, pm)
    e = await add(client)
    response = await client.patch(event_url(e["id"]), json={"title": "QS Fair (Delhi)", "ends_on": day(8), "location": None})
    assert response.status_code == 200, response.text
    edited = response.json()["event"]
    assert edited["title"] == "QS Fair (Delhi)" and edited["ends_on"] == day(8) and edited["location"] is None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == e["id"], AuditLog.action == "partnership_event.update"))
    assert audit.metadata_json["fields"] == ["ends_on", "location", "title"]
    assert (await client.patch(event_url(e["id"]), json={"title": None})).status_code == 422
    assert (await client.patch(event_url(e["id"]), json={"ends_on": day(2)})).status_code == 422  # before the start
    await login(client, other)
    assert (await client.patch(event_url(e["id"]), json={"title": "Mine now"})).status_code == 403
    assert (await client.post(event_url(e["id"], "cancel"), json={"reason": "No"})).status_code == 403
    await login(client, head)  # the head is neither owner nor creator
    assert (await client.patch(event_url(e["id"]), json={"title": "Head edit"})).status_code == 403


@pytest.mark.asyncio
async def test_cancel_needs_a_reason_and_is_final(client, db_session):
    _, pm, _ = await _team(db_session)
    await login(client, pm)
    e = await add(client)
    assert (await client.post(event_url(e["id"], "cancel"), json={})).status_code == 422
    response = await client.post(event_url(e["id"], "cancel"), json={"reason": "Fair postponed"})
    assert response.status_code == 200, response.text
    cancelled = response.json()["event"]
    assert cancelled["status"] == "cancelled" and cancelled["cancel_reason"] == "Fair postponed" and cancelled["cancelled_at"]
    assert cancelled["permissions"] == {"can_edit": False, "can_cancel": False}
    assert (await client.patch(event_url(e["id"]), json={"title": "Back on"})).status_code == 409
    assert (await client.post(event_url(e["id"], "cancel"), json={"reason": "Again"})).status_code == 409


@pytest.mark.asyncio
async def test_a_started_event_keeps_its_past_start_when_other_fields_change(client, db_session):
    """CL3: only a changed date must be today or later -- an ongoing event can still be edited."""
    from sqlalchemy import update

    from app.models import PartnershipEvent

    _, pm, _ = await _team(db_session)
    await login(client, pm)
    e = await add(client)
    await db_session.execute(update(PartnershipEvent).where(PartnershipEvent.code == e["code"]).values(starts_on=india_today() - timedelta(days=1)))
    await db_session.commit()
    assert (await client.patch(event_url(e["id"]), json={"notes": "Day 2 stall moved"})).status_code == 200
    assert (await client.patch(event_url(e["id"]), json={"starts_on": day(-2)})).status_code == 422
