"""dtu-001 §6: the catalogue's new public fields, everywhere a university / course is read; never the agent commission in public."""

import uuid

import pytest

from app.models import Country
from app.services import course_import
from tests.upc001_helpers import as_role
from tests.upc003_helpers import BASE, create

API = "/api/v1"


async def _country(db) -> Country:
    """Its own catalogue-visible country, so publishing never depends on what the shared test database holds."""
    tag = uuid.uuid4().hex[:8]
    country = Country(slug=f"dtu001-{tag}", name=f"Dtuland {tag}", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.commit()
    return country


async def _published(client, db_session):
    await as_role(client, db_session, "super_admin", "overseas")
    country = await _country(db_session)
    uni = await create(client, country.id, overview="An overview.", logo_url="/universities/logos/x.png", campuses=["Cardiff", "Newport"], fee_structure="UG: £1 – £2")
    r = await client.post(f"{BASE}/{uni['id']}/courses", json={
        "title": "MBA Global", "level": "PG", "category": "Business", "duration": "Not specified",
        "campus": "Newport Campus", "fee_text": "£18,970", "intake_text": "January / September",
    })
    assert r.status_code == 201, r.text
    assert (await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"percent": "13"})).status_code == 200
    pub = await client.post(f"{BASE}/{uni['id']}/publish")
    assert pub.status_code == 200, pub.text
    return uni


@pytest.mark.asyncio
async def test_master_round_trips_the_new_fields(client, db_session):
    uni = await _published(client, db_session)
    body = (await client.get(f"{BASE}/{uni['id']}")).json()["university"]
    assert body["logo_url"] == "/universities/logos/x.png" and body["campuses"] == ["Cardiff", "Newport"] and body["fee_structure"] == "UG: £1 – £2"
    course = (await client.get(f"{BASE}/{uni['id']}/courses")).json()["items"][0]
    assert (course["campus"], course["fee_text"], course["intake_text"]) == ("Newport Campus", "£18,970", "January / September")


@pytest.mark.asyncio
async def test_created_without_them_reads_empty_and_patch_changes_them(client, db_session):
    await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, (await _country(db_session)).id)
    assert (uni["logo_url"], uni["campuses"], uni["fee_structure"]) == (None, [], None)
    patched = (await client.patch(f"{BASE}/{uni['id']}", json={"campuses": ["A"], "logo_url": "https://cdn.example.com/l.png"})).json()["university"]
    assert patched["campuses"] == ["A"] and patched["logo_url"] == "https://cdn.example.com/l.png"
    cleared = (await client.patch(f"{BASE}/{uni['id']}", json={"campuses": None})).json()["university"]
    assert cleared["campuses"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"logo_url": "javascript:alert(1)"}, {"logo_url": "http://x.example/l.png"}, {"campuses": [""]}, {"campuses": ["c"] * 21}])
async def test_bad_values_are_refused(client, db_session, bad):
    await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, (await _country(db_session)).id)
    assert (await client.patch(f"{BASE}/{uni['id']}", json=bad)).status_code == 422


@pytest.mark.asyncio
async def test_public_detail_and_lists_show_them(client, db_session):
    uni = await _published(client, db_session)
    d = (await client.get(f"{API}/public/universities/{uni['slug']}")).json()
    assert d["university"]["logo_url"] == "/universities/logos/x.png" and d["university"]["campuses"] == ["Cardiff", "Newport"]
    assert d["university"]["fee_structure"] == "UG: £1 – £2"
    assert d["courses"][0]["campus"] == "Newport Campus" and d["courses"][0]["fee_text"] == "£18,970" and d["courses"][0]["intake_text"] == "January / September"
    listed = (await client.get(f"{API}/public/universities", params={"q": uni["name"]})).json()
    assert listed[0]["logo_url"] == "/universities/logos/x.png"
    cs = (await client.get(f"{API}/public/overseas-courses", params={"category": "Business"})).json()
    assert any(c["campus"] == "Newport Campus" and c["fee_text"] == "£18,970" for c in cs)


@pytest.mark.asyncio
async def test_public_never_carries_agent_commission(client, db_session):
    uni = await _published(client, db_session)
    for path in (f"/public/universities/{uni['slug']}", f"/public/universities?q={uni['name']}", "/public/overseas-courses?category=Business"):
        assert "agent_commission" not in (await client.get(API + path)).text


def test_course_csv_carries_the_new_columns():
    assert {"campus", "fee_text", "intake_text"} <= set(course_import.COLUMNS)
    row = course_import.parse_row({"title": "X", "level": "PG", "category": "Business", "duration": "1 year", "campus": "Cardiff", "fee_text": "£1", "intake_text": "Sep"})
    assert isinstance(row, dict) and (row["campus"], row["fee_text"], row["intake_text"]) == ("Cardiff", "£1", "Sep")
