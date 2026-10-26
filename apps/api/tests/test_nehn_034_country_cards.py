"""nehn-034 (DEC-SCOPE-286): the country cards' university count (C1) and the student portal's Explore Countries section (C5)."""

import pytest

from tests.agn001_helpers import login, mk_user
from tests.test_ovs_001_discovery import _make_country, _make_university
from tests.test_pub_023_country_flags import _cleanup


def _listed(response, slug: str) -> dict:
    return next(c for c in response.json() if c["slug"] == slug)


@pytest.mark.asyncio
async def test_country_card_counts_only_published_active_universities(client, db_session):
    country, other = await _make_country(db_session), await _make_country(db_session)
    try:
        await _make_university(db_session, country.id)
        await _make_university(db_session, country.id)
        await _make_university(db_session, country.id, catalogue_visible=False)  # the master's internal row
        await _make_university(db_session, country.id, active=False)
        await _make_university(db_session, other.id)
        listed = await client.get("/api/v1/public/countries")
        assert _listed(listed, country.slug)["university_count"] == 2
        assert _listed(listed, other.slug)["university_count"] == 1
        detail = (await client.get(f"/api/v1/public/countries/{country.slug}")).json()
        assert detail["country"]["university_count"] == 2 and len(detail["universities"]) == 2
    finally:
        await _cleanup(db_session, country)
        await _cleanup(db_session, other)


@pytest.mark.asyncio
async def test_a_country_without_universities_counts_zero(client, db_session):  # C2: the card then shows "Coming soon"
    country = await _make_country(db_session)
    try:
        assert _listed(await client.get("/api/v1/public/countries"), country.slug)["university_count"] == 0
        assert (await client.get(f"/api/v1/public/countries/{country.slug}")).json()["country"]["university_count"] == 0
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_view_universities_filter_and_unknown_slug(client, db_session):  # C3
    country = await _make_country(db_session)
    try:
        await _make_university(db_session, country.id, name="Filter Target University")
        rows = (await client.get("/api/v1/public/universities", params={"country": country.slug})).json()
        assert [r["name"] for r in rows] == ["Filter Target University"]
        assert (await client.get("/api/v1/public/universities", params={"country": "no-such-country"})).json() == []
        assert (await client.get("/api/v1/public/countries/no-such-country")).status_code == 404
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_public_countries_stay_public(client):
    assert (await client.get("/api/v1/public/countries")).status_code == 200


@pytest.mark.asyncio
async def test_student_explore_countries_section_is_header_only(client, db_session):  # C5
    student = await mk_user(db_session, role="overseas_student")
    await login(client, student.email)
    response = await client.get("/api/v1/portal/overseas/student/explore-countries")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Explore Countries" and body["rows"] == [] and body["metrics"] == []


@pytest.mark.asyncio
async def test_explore_countries_section_is_the_students_only(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    assert (await client.get("/api/v1/portal/overseas/student/explore-countries")).status_code == 403


@pytest.mark.asyncio
async def test_explore_countries_requires_a_session(client):
    assert (await client.get("/api/v1/portal/overseas/student/explore-countries")).status_code == 401
