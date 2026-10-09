"""upc-018 -- GET /partnership/performance and /partnership/universities/{id}/performance (spec §4, PF1, PF5-PF10; AC2, AC6-AC8).
Activity is dated into June 2024, a period only this file writes to, so the shared test DB does not disturb the ranking."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import update

from app.models import University
from app.services.bdm_appointments import IST
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url
from tests.upc018_helpers import application, history

PERFORMANCE = "/api/v1/partnership/performance"
JUNE = {"from": "2024-06-01", "to": "2024-06-30"}
IN_JUNE = datetime(2024, 6, 12, 6, tzinfo=UTC)
TRACKED = ["interested", "applications", "offers", "deposits", "visas", "enrolled"]


async def _university(client, db, head, manager=None) -> University:
    await login(client, head)
    made = await create(client, (await catalogue_country(db)).id)
    if manager is not None:
        response = await client.post(url(made["id"], "assign"), json={"primary_manager_user_id": str(manager.id)})
        assert response.status_code == 200, response.text
    return await db.get(University, uuid.UUID(made["id"]))


async def _activity(db, uni, applications: int = 1, enrolled: int = 0) -> None:
    for i in range(applications):
        app = await application(db, uni, when=IN_JUNE, status="enrolled" if i < enrolled else "enquiry")
        if i < enrolled:
            await history(db, app, "enrolled", IN_JUNE, "status_tracking")


async def _set(db, uni, **values) -> None:
    await db.execute(update(University).where(University.id == uni.id).values(**values))
    await db.commit()


async def _ids(client, **params) -> list[str]:
    response = await client.get(PERFORMANCE, params=JUNE | {"limit": 100} | params)
    assert response.status_code == 200, response.text
    return [row["university"]["id"] for row in response.json()["items"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("bdm", "overseas"), ("counselor", "overseas"), ("overseas_student", "overseas"), ("agent", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    uni = await _university(client, db_session, await make_head(db_session))
    await as_role(client, db_session, role, division)
    for path in (PERFORMANCE, url(uni.id, "performance")):
        response = await client.get(path)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["detail"] == "University master access required"


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(PERFORMANCE)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params", [{"from": "2024-06-30", "to": "2024-06-01"}, {"from": "2023-01-01", "to": "2024-06-01"}, {"from": "2024-6-1"}, {"to": "June"}, {"from": "2025-02-30", "to": "2025-03-01"}]
)
async def test_bad_period_is_422(client, db_session, params):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(PERFORMANCE, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_default_period_is_this_ist_month_to_date(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    body = (await client.get(PERFORMANCE, params={"limit": 1})).json()
    today = datetime.now(IST).date()
    assert (body["from"], body["to"]) == (today.replace(day=1).isoformat(), today.isoformat())


@pytest.mark.asyncio
async def test_one_university_funnel_with_untracked_steps_and_no_identifiers(client, db_session):
    head = await make_head(db_session)
    uni = await _university(client, db_session, head)
    await _activity(db_session, uni, applications=3, enrolled=1)
    pm = await make_pm(db_session, await make_head(db_session))  # another team: every reader reads every university (PF6)
    await login(client, pm)
    response = await client.get(url(uni.id, "performance"), params=JUNE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [s["key"] for s in body["steps"]] == ["leads", "counselling", "interested", "eligible", *TRACKED[1:]]
    assert {s["key"] for s in body["steps"] if not s["tracked"]} == {"leads", "counselling", "eligible"}
    assert body["counts"] == {
        "leads": None,
        "counselling": None,
        "eligible": None,
        "interested": 0,
        "applications": 3,
        "offers": 1,
        "deposits": 0,
        "visas": 0,
        "enrolled": 1,
    }  # enrolled implies the offer stage
    assert body["university"]["id"] == str(uni.id) and (body["from"], body["to"]) == (JUNE["from"], JUNE["to"])
    text = response.text.lower()
    assert "commission" not in text and "student_id" not in text and "application_reference" not in text


@pytest.mark.asyncio
async def test_unknown_university_is_404(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(url(uuid.uuid4(), "performance"))).status_code == 404


@pytest.mark.asyncio
async def test_list_scope_per_role(client, db_session):
    """PF6: manager = primary/backup; head = team + unowned; super_admin and overseas_admin = all."""
    head, other_head = await make_head(db_session), await make_head(db_session)
    pm, other_pm = await make_pm(db_session, head), await make_pm(db_session, other_head)
    mine = await _university(client, db_session, head, pm)
    theirs = await _university(client, db_session, other_head, other_pm)
    unowned = await _university(client, db_session, head)
    for uni in (mine, theirs, unowned):
        await _activity(db_session, uni)
    await login(client, pm)
    seen = await _ids(client)
    assert str(mine.id) in seen and str(theirs.id) not in seen and str(unowned.id) not in seen
    await login(client, head)
    seen = await _ids(client)
    assert str(mine.id) in seen and str(unowned.id) in seen and str(theirs.id) not in seen
    for role, division in (("super_admin", "global"), ("overseas_admin", "overseas")):
        await as_role(client, db_session, role, division)
        seen = await _ids(client)
        assert {str(mine.id), str(theirs.id), str(unowned.id)} <= set(seen), role


@pytest.mark.asyncio
async def test_ranking_partners_and_totals(client, db_session):
    """PF7/PF8: enrolled then applications; idle partners listed, idle non-partners and inactive universities not; totals over all rows."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    top, second, third, idle_partner, idle, inactive = [await _university(client, db_session, head, pm) for _ in range(6)]
    await _activity(db_session, top, applications=2, enrolled=2)
    await _activity(db_session, second, applications=3, enrolled=1)
    await _activity(db_session, third, applications=1, enrolled=1)
    await _set(db_session, idle_partner, stage="active_partner")
    await _activity(db_session, inactive, applications=5, enrolled=5)
    await _set(db_session, inactive, active=False)
    await login(client, pm)
    body = (await client.get(PERFORMANCE, params=JUNE)).json()
    assert [row["university"]["id"] for row in body["items"]] == [str(u.id) for u in (top, second, third, idle_partner)]
    assert [row["rank"] for row in body["items"]] == [1, 2, 3, 4]
    assert body["items"][3]["university"]["partner"] is True and body["items"][0]["university"]["partner"] is False
    assert body["total"] == 4
    assert body["totals"] == {"leads": None, "counselling": None, "eligible": None, "interested": 0, "applications": 6, "offers": 4, "deposits": 0, "visas": 0, "enrolled": 4}
    assert str(idle.id) not in str(body)
    paged = (await client.get(PERFORMANCE, params=JUNE | {"limit": 1, "offset": 1})).json()
    assert [row["rank"] for row in paged["items"]] == [2] and paged["totals"] == body["totals"] and paged["total"] == 4
    assert "commission" not in str(body).lower()


@pytest.mark.asyncio
async def test_manager_without_a_profile_is_refused(client, db_session):
    await login(client, await make_user(db_session, "partnership_manager", "overseas"))
    assert (await client.get(PERFORMANCE)).status_code == 403


@pytest.mark.asyncio
async def test_period_outside_activity_is_empty_for_a_fresh_manager(client, db_session):
    pm = await make_pm(db_session, await make_head(db_session))
    await login(client, pm)
    body = (await client.get(PERFORMANCE, params={"from": "2024-06-01", "to": "2024-06-30"})).json()
    assert body["items"] == [] and body["total"] == 0 and body["totals"]["applications"] == 0
    assert date.fromisoformat(body["to"]) == date(2024, 6, 30)
