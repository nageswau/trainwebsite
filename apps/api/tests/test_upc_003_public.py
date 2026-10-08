"""upc-003 -- an internal (unpublished or inactive) university never reaches the public catalogue or a student's catalogue panel (spec §3;
AC2, AC3), and the country lookup opens to the partnership roles."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Country, OverseasCourse, University
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url

PUBLIC = "/api/v1/public"


async def _course(db, university_id, title: str) -> None:
    db.add(OverseasCourse(university_id=university_id, title=title, level="PG", category="Business", duration="1 year", tuition_fee="GBP 20,000", intake="Sep"))
    await db.commit()


async def _visible_everywhere(client, db, uni: dict, course_title: str) -> dict[str, bool]:
    country = await db.get(Country, uuid.UUID(uni["country"]["id"]))
    student = await make_user(db, "overseas_student", "overseas")
    await login(client, student)
    panel = (await client.get("/api/v1/portal/overseas/student/applications")).json()
    client.cookies.clear()
    listed = {u["id"] for u in (await client.get(f"{PUBLIC}/universities", params={"q": uni["name"]})).json()}
    on_country = {u["id"] for u in (await client.get(f"{PUBLIC}/countries/{country.slug}")).json()["universities"]}
    searched = [x["title"] for x in (await client.get(f"{PUBLIC}/search", params={"q": uni["name"]})).json()["universities"]]
    courses = [c["title"] for c in (await client.get(f"{PUBLIC}/overseas-courses")).json()]
    return {
        "list": uni["id"] in listed,
        "detail": (await client.get(f"{PUBLIC}/universities/{uni['slug']}")).status_code == 200,
        "country": uni["id"] in on_country,
        "search": uni["name"] in searched,
        "courses": course_title in courses,
        "student_panel": any(uni["name"] in item for p in panel.get("panels", []) for item in p["items"]),
    }


@pytest.mark.asyncio
async def test_a_new_target_is_internal_until_published_and_hidden_again_when_deactivated(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    await login(client, admin)
    # Sweden: a catalogue country with few universities, so the country page's 20-row list is not already full.
    sweden = await db_session.scalar(select(Country).where(Country.iso2 == "SE", Country.catalogue_visible.is_(True)))
    uni = await create(client, sweden.id, name=f"Hidden University {uuid.uuid4().hex[:8]}", overview="Overview")
    title = f"MSc Hidden {uuid.uuid4().hex[:6]}"
    await _course(db_session, uuid.UUID(uni["id"]), title)

    assert not any((await _visible_everywhere(client, db_session, uni, title)).values())

    await login(client, admin)
    assert (await client.post(url(uni["id"], "publish"))).status_code == 200
    assert all((await _visible_everywhere(client, db_session, uni, title)).values())

    await login(client, admin)
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    assert not any((await _visible_everywhere(client, db_session, uni, title)).values())


@pytest.mark.asyncio
async def test_existing_catalogue_universities_stay_public(client, db_session):
    seeded = (await db_session.scalars(select(University).where(University.catalogue_visible.is_(True), University.active.is_(True)).limit(3))).all()
    assert seeded
    for uni in seeded:
        assert (await client.get(f"{PUBLIC}/universities/{uni.slug}")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partnership_head", "partnership_manager"])
async def test_partnership_roles_use_the_country_lookup(client, db_session, role):
    head = await make_head(db_session)
    if role == "partnership_head":
        await login(client, head)
    else:
        await login(client, await make_pm(db_session, head))
    response = await client.get("/api/v1/lookups/countries", params={"q": "JP"})
    assert response.status_code == 200 and response.json()["items"][0]["label"] == "Japan"


@pytest.mark.asyncio
async def test_other_roles_still_cannot_use_the_country_lookup(client, db_session):
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.get("/api/v1/lookups/countries")).status_code == 403
