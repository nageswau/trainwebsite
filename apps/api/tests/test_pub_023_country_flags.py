"""PUB-023 (DEC-SCOPE-222): the read-only iso2 fields the web needs to draw a country's flag (API §12EJ)."""

import string
import uuid

import pytest
from sqlalchemy import delete, select

from app.models import Country, OverseasCourse, University
from tests.agn001_helpers import login, mk_user
from tests.test_ovs_001_discovery import _make_country, _make_course, _make_university


async def _free_code(db) -> str:
    """An unassigned two-letter code (X?/Q? are never ISO countries); iso2 is unique and the test DB is shared."""
    taken = set(await db.scalars(select(Country.iso2).where(Country.iso2.is_not(None))))
    return next(a + b for a in "XQ" for b in string.ascii_uppercase if a + b not in taken)


async def _cleanup(db, country) -> None:
    unis = select(University.id).where(University.country_id == country.id)
    await db.execute(delete(OverseasCourse).where(OverseasCourse.university_id.in_(unis)))
    await db.execute(delete(University).where(University.country_id == country.id))
    await db.execute(delete(Country).where(Country.id == country.id))
    await db.commit()


@pytest.mark.asyncio
async def test_public_countries_carry_iso2(client, db_session):
    country = await _make_country(db_session, iso2=await _free_code(db_session))
    try:
        listed = next(c for c in (await client.get("/api/v1/public/countries")).json() if c["slug"] == country.slug)
        assert listed["iso2"] == country.iso2
        detail = (await client.get(f"/api/v1/public/countries/{country.slug}")).json()
        assert detail["country"]["iso2"] == country.iso2
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_a_country_without_a_code_has_null_iso2(client, db_session):  # F3: the web then shows no flag
    country = await _make_country(db_session)
    try:
        listed = next(c for c in (await client.get("/api/v1/public/countries")).json() if c["slug"] == country.slug)
        assert "iso2" in listed and listed["iso2"] is None
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_public_course_rows_carry_country_iso2(client, db_session):
    country = await _make_country(db_session, iso2=await _free_code(db_session))
    try:
        university = await _make_university(db_session, country.id)
        category = f"Flags {uuid.uuid4().hex[:8]}"
        await _make_course(db_session, university.id, category=category)
        rows = (await client.get("/api/v1/public/overseas-courses", params={"category": category})).json()
        assert len(rows) == 1 and rows[0]["country"] == country.name and rows[0]["country_iso2"] == country.iso2
    finally:
        await _cleanup(db_session, country)


@pytest.mark.asyncio
async def test_country_lookup_items_carry_iso2(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = (await client.get("/api/v1/lookups/countries", params={"q": "jp"})).json()["items"]
    assert items[0]["label"] == "Japan" and items[0]["iso2"] == "JP" and items[0]["detail"] == "JP · Asia"


@pytest.mark.asyncio
async def test_country_lookup_role_check_is_unchanged(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    assert (await client.get("/api/v1/lookups/countries")).status_code == 403
