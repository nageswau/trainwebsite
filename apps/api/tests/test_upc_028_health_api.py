"""upc-028 -- the health score in the §18 performance responses (spec §3, HS1, HS2, HS9; AC4-AC6, AC8). Health is as of today, so
each test builds fresh universities; the ranking rows are found by id, with activity in March 2018, a period no other test writes."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import University, UniversityMeeting
from app.services.bdm_appointments import IST
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url
from tests.upc018_helpers import application, history
from tests.upc019_helpers import agreement

PERFORMANCE = "/api/v1/partnership/performance"
MARCH_2018 = {"from": "2018-03-01", "to": "2018-03-31", "limit": "100"}
IN_MARCH_2018 = datetime(2018, 3, 12, 6, tzinfo=UTC)


async def _university(client, db, head, manager=None, *, stage: str | None = "active_partner") -> University:
    await login(client, head)
    made = await create(client, (await catalogue_country(db)).id)
    if manager is not None:
        assert (await client.post(url(made["id"], "assign"), json={"primary_manager_user_id": str(manager.id)})).status_code == 200
    uni = await db.get(University, uuid.UUID(made["id"]))
    if stage:
        await db.execute(update(University).where(University.id == uni.id).values(stage=stage))
        await db.commit()
        await db.refresh(uni)
    return uni


async def _healthy(db, uni, by) -> None:
    """An active agreement, a meeting completed this week and an enrolment in March 2018 (so it ranks in that period)."""
    await agreement(db, uni, by, start=date(2018, 1, 1), expiry=date.today() + timedelta(days=900))
    done = datetime.now(UTC) - timedelta(days=3)
    db.add(UniversityMeeting(
        code=f"H-{uuid.uuid4().hex[:10]}", university_id=uni.id, meeting_type="introduction", starts_at=done, mode="online", responsible_user_id=by.id,
        created_by_user_id=by.id, status="completed", completed_at=done, completed_by_user_id=by.id,
    ))  # fmt: skip
    await db.commit()
    app = await application(db, uni, when=IN_MARCH_2018, status="enrolled")
    await history(db, app, "enrolled", IN_MARCH_2018)


def _row(body: dict, uni: University) -> dict:
    return next(r for r in body["items"] if r["university"]["id"] == str(uni.id))


@pytest.mark.asyncio
async def test_a_manager_reads_health_with_its_breakdown_on_both_endpoints(client, db_session):
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    partner = await _university(client, db_session, head, pm)
    await _healthy(db_session, partner, head)
    await login(client, pm)
    page = await client.get(PERFORMANCE, params=MARCH_2018)
    assert page.status_code == 200, page.text
    health = _row(page.json(), partner)["health"]
    assert health["as_of"] == datetime.now(IST).date().isoformat()  # HS2: today, whatever the period
    assert health["band"] in ("excellent", "good", "needs_attention") and isinstance(health["score"], int)
    keys = [f["key"] for f in health["factors"]]
    assert keys[-1] == "satisfaction" and "commission" in keys and len(keys) == 9
    assert sum(f["points"] for f in health["factors"] if f["points"] is not None) == health["score"]  # AC1
    assert all("value" not in f for f in health["factors"])
    one = (await client.get(url(partner.id, "performance"), params={"from": "2018-03-01", "to": "2018-03-31"})).json()
    assert one["health"] == health


@pytest.mark.asyncio
async def test_a_non_partner_has_null_health_and_a_partner_without_data_is_insufficient(client, db_session):
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    prospect = await _university(client, db_session, head, pm, stage=None)
    await _healthy(db_session, prospect, head)
    empty_partner = await _university(client, db_session, head, pm)
    await login(client, pm)
    body = (await client.get(PERFORMANCE, params=MARCH_2018)).json()
    assert _row(body, prospect)["health"] is None  # AC5
    empty = _row(body, empty_partner)["health"]
    assert (empty["score"], empty["band"], empty["band_label"], len(empty["factors"])) == (None, "insufficient_data", "Insufficient data", 9)  # AC4
    assert (await client.get(url(prospect.id, "performance"))).json()["health"] is None


@pytest.mark.asyncio
async def test_overseas_admin_sees_the_score_but_never_the_breakdown(client, db_session):
    """HS9 / AC6: the commission factor stays inside the score; no `factors` key and no commission measure for a non-commission role."""
    head = await make_head(db_session)
    partner = await _university(client, db_session, head)
    await _healthy(db_session, partner, head)
    await as_role(client, db_session, "overseas_admin", "overseas")
    page = await client.get(PERFORMANCE, params=MARCH_2018)
    assert page.status_code == 200, page.text
    health = _row(page.json(), partner)["health"]
    assert set(health) == {"as_of", "score", "band", "band_label"} and isinstance(health["score"], int)
    one = await client.get(url(partner.id, "performance"))
    assert set(one.json()["health"]) == {"as_of", "score", "band", "band_label"}
    assert "factors" not in one.text and "expected commission" not in one.text and "commission" not in one.json()


@pytest.mark.asyncio
async def test_super_admin_gets_the_breakdown(client, db_session):
    partner = await _university(client, db_session, await make_head(db_session))
    await as_role(client, db_session, "super_admin", "global")
    health = (await client.get(url(partner.id, "performance"))).json()["health"]
    assert health["band"] == "insufficient_data" and [f["key"] for f in health["factors"]][0] == "applications"


@pytest.mark.asyncio
async def test_a_deactivated_partner_is_not_scored(client, db_session):
    partner = await _university(client, db_session, await make_head(db_session))
    await db_session.execute(update(University).where(University.id == partner.id).values(active=False))
    await db_session.commit()
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(url(partner.id, "performance"))).json()["health"] is None
