"""upc-011 -- the §9 calendar and overlap warnings (spec CL1, CL8-CL12; AC1, AC2, P1, N1, E1)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.models import UniversityVisit
from app.services.bdm_travel import india_today
from tests.test_upc_011_events import add, event_url
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url

CALENDAR = "/api/v1/partnership/calendar"
MEETINGS = "/api/v1/partnership/meetings"
VISITS = "/api/v1/partnership/visits"


def day(offset: int) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


def at(offset: int, hour: int) -> str:
    return f"{day(offset)}T{hour:02d}:00:00+05:30"


async def _owned(client, db):
    head = await make_head(db)
    pm, other = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})).status_code == 200
    return head, pm, other, uni


async def meeting(client, university_id, starts_at, expected=201, **extra) -> dict:
    body = {"university_id": university_id, "meeting_type": "introduction", "starts_at": starts_at, "mode": "offline", **extra}
    response = await client.post(MEETINGS, json=body)
    assert response.status_code == expected, response.text
    return response.json()["meeting"]


async def visit(client, university_id, offset: int, **extra) -> dict:
    body = {"university_id": university_id, "purpose": "Campus tour", "proposed_date": day(offset), **extra}
    response = await client.post(VISITS, json=body)
    assert response.status_code == 201, response.text
    return response.json()["visit"]


async def read(client, first: int, last: int, expected: int = 200, **params) -> dict:
    response = await client.get(CALENDAR, params={"date_from": day(first), "date_to": day(last), **params})
    assert response.status_code == expected, response.text
    return response.json()


def keys(cal: dict) -> list[tuple[str, str]]:
    return [(i["source"], i["code"]) for i in cal["items"]]


# --- AC1 + P1: all eight kinds, an education fair week plus two visits ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_calendar_shows_all_eight_kinds(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await meeting(client, uni["id"], at(2, 10))
    v = await visit(client, uni["id"], 3)
    kinds = ("conference", "education_fair", "partner_meeting", "mou_signing", "webinar", "university_presentation")
    events = [await add(client, kind=k, title=k, starts_on=day(4 + n), ends_on=day(4 + n)) for n, k in enumerate(kinds)]
    cal = await read(client, 0, 13)
    assert {i["kind"] for i in cal["items"]} == {"university_meeting", "university_visit", *kinds}
    assert cal["employee"]["id"] == str(pm.id) and cal["truncated"] is False and cal["today"] == day(0)
    meeting_item = next(i for i in cal["items"] if i["id"] == m["id"])
    assert meeting_item["title"] == uni["name"] and meeting_item["starts_on"] == day(2) and meeting_item["starts_at"]
    assert meeting_item["university"] == {"id": uni["id"], "name": uni["name"]} and [p["id"] for p in meeting_item["people"]] == [str(pm.id)]
    visit_item = next(i for i in cal["items"] if i["id"] == v["id"])
    assert (visit_item["starts_on"], visit_item["ends_on"], visit_item["starts_at"]) == (day(3), day(3), None)
    assert [i["code"] for i in cal["items"]] == [m["code"], v["code"], *(e["code"] for e in events)]  # by start


@pytest.mark.asyncio
async def test_education_fair_week_with_two_visits_warns_on_the_visit_days(client, db_session):
    """P1 + AC2: the fair occupies the week; each visit day inside it overlaps for the manager -- on the calendar and on create."""
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    v1, v2 = await visit(client, uni["id"], 8), await visit(client, uni["id"], 10)
    fair = await add(client, starts_on=day(7), ends_on=day(11))
    assert {o["item"]["code"] for o in fair["overlaps"]} == {v1["code"], v2["code"]}  # warning on create
    assert all(o["employee"]["id"] == str(pm.id) for o in fair["overlaps"])
    cal = await read(client, 7, 13)
    by_code = {i["code"]: i for i in cal["items"]}
    assert [o["item"]["code"] for o in by_code[v1["code"]]["overlaps"]] == [fair["code"]]
    assert {o["item"]["source"] for o in by_code[fair["code"]]["overlaps"]} == {"visit"}
    assert (await client.get(f"{VISITS}/{v1['id']}")).json()["visit"]["overlaps"][0]["item"]["code"] == fair["code"]


@pytest.mark.asyncio
async def test_meeting_overlaps_are_a_60_minute_slot(client, db_session):
    """CL10: 30 minutes apart overlaps; back-to-back hourly meetings do not; a meeting on a visit day does."""
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await meeting(client, uni["id"], at(4, 10))
    clash = await meeting(client, uni["id"], f"{day(4)}T10:30:00+05:30")
    assert [o["item"]["code"] for o in clash["overlaps"]] == [first["code"]]  # warning on create
    later = await meeting(client, uni["id"], at(4, 11))
    assert [o["item"]["code"] for o in later["overlaps"]] == [clash["code"]]  # 10:30-11:30 meets 11:00, not 10:00-11:00
    other_day = await meeting(client, uni["id"], at(5, 15))
    assert other_day["overlaps"] == []
    v = await visit(client, uni["id"], 5)
    assert [o["item"]["code"] for o in v["overlaps"]] == [other_day["code"]]


@pytest.mark.asyncio
async def test_cancelled_and_called_off_items_leave_the_calendar(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await meeting(client, uni["id"], at(6, 9))
    e = await add(client, starts_on=day(6), ends_on=day(6))
    v = await visit(client, uni["id"], 6)
    assert len((await read(client, 6, 6))["items"]) == 3
    assert (await client.post(f"{MEETINGS}/{m['id']}/cancel", json={"reason": "Postponed"})).status_code == 200
    assert (await client.post(event_url(e["id"], "cancel"), json={"reason": "Postponed"})).status_code == 200
    assert (await client.post(f"{VISITS}/{v['id']}/close", json={"reason": "Called off"})).status_code == 200
    assert (await read(client, 6, 6))["items"] == []


@pytest.mark.asyncio
async def test_visit_uses_its_confirmed_date(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await visit(client, uni["id"], 3)
    await db_session.execute(update(UniversityVisit).where(UniversityVisit.id == uuid.UUID(v["id"])).values(confirmed_date=india_today() + timedelta(days=9)))
    await db_session.commit()
    assert v["code"] not in [c for _, c in keys(await read(client, 3, 3))]
    assert keys(await read(client, 9, 9)) == [("visit", v["code"])]


@pytest.mark.asyncio
async def test_multi_day_event_across_months_shows_in_both_windows(client, db_session):
    """E1: an event touching two windows appears in each; its own detail sees overlaps in both."""
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    e = await add(client, kind="conference", starts_on=day(20), ends_on=day(24))
    late = await meeting(client, uni["id"], at(24, 12))
    assert ("event", e["code"]) in keys(await read(client, 0, 21))
    second = await read(client, 22, 40)
    assert ("event", e["code"]) in keys(second) and ("meeting", late["code"]) in keys(second)
    detail = (await client.get(event_url(e["id"]))).json()["event"]
    assert [o["item"]["code"] for o in detail["overlaps"]] == [late["code"]]


# --- range and scope (CL8, CL9; N1) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_range_rules(client, db_session):
    _, pm, _, _ = await _owned(client, db_session)
    await login(client, pm)
    await read(client, 0, 31, 422)  # 32 days (N1)
    await read(client, 5, 4, 422)
    await read(client, 0, 30)


@pytest.mark.asyncio
async def test_whose_calendar(client, db_session):
    """CL9: a manager reads only their own; a head their team; super_admin anyone; out of scope is 404; other roles 403."""
    head, pm, other, uni = await _owned(client, db_session)
    stranger = await make_pm(db_session, await make_head(db_session))
    await login(client, pm)
    mine = await meeting(client, uni["id"], at(3, 9))
    await login(client, other)
    theirs = await add(client, starts_on=day(3), ends_on=day(3))
    await login(client, pm)
    assert keys(await read(client, 3, 3)) == [("meeting", mine["code"])]
    await read(client, 3, 3, 404, user_id=str(other.id))
    assert (await read(client, 3, 3, user_id=str(pm.id)))["employee"]["id"] == str(pm.id)
    await login(client, head)
    team = await read(client, 3, 3)
    assert team["employee"] is None and {c for _, c in keys(team)} == {mine["code"], theirs["code"]}
    assert keys(await read(client, 3, 3, user_id=str(other.id))) == [("event", theirs["code"])]
    await read(client, 3, 3, 404, user_id=str(stranger.id))
    await read(client, 3, 3, 404, user_id=str(uuid.uuid4()))
    names = [p["id"] for p in (await client.get(f"{CALENDAR}/employees")).json()["items"]]
    assert set(names) == {str(head.id), str(pm.id), str(other.id)}
    await as_role(client, db_session, "super_admin", "global")
    assert keys(await read(client, 3, 3, user_id=str(other.id))) == [("event", theirs["code"])]
    assert {mine["code"], theirs["code"]} <= {c for _, c in keys(await read(client, 3, 3))}
    assert str(stranger.id) in [p["id"] for p in (await client.get(f"{CALENDAR}/employees")).json()["items"]]
    for role, division in (("overseas_admin", "overseas"), ("counselor", "overseas"), ("university_rep", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.get(CALENDAR, params={"date_from": day(0), "date_to": day(1)})).status_code == 403, role
        assert (await client.get(f"{CALENDAR}/employees")).status_code == 403, role


@pytest.mark.asyncio
async def test_participants_count_for_overlaps(client, db_session):
    """CL10: a colleague added to a meeting overlaps with their own event that day; the overlap names that colleague."""
    _, pm, other, uni = await _owned(client, db_session)
    await login(client, other)
    fair = await add(client, starts_on=day(12), ends_on=day(12))
    await login(client, pm)
    m = await meeting(client, uni["id"], at(12, 14), participant_user_ids=[str(other.id)])
    assert [(o["employee"]["id"], o["item"]["code"]) for o in m["overlaps"]] == [(str(other.id), fair["code"])]
    assert (await read(client, 12, 12))["items"][0]["overlaps"] == []  # the manager's own calendar: only their overlaps
