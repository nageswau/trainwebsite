"""upc-002 (U12, design C4-C8) -- internal ISO countries stay out of the public catalogue; the country lookup lists them all."""

import pytest
from sqlalchemy import select

from app.models import Country
from tests.agn001_helpers import login, mk_user, uniq

LOOKUP = "/api/v1/lookups/countries"


async def _country(db, *, visible: bool, iso2: str | None = None, region: str | None = None, name: str | None = None) -> Country:
    country = Country(slug=uniq("upc002-c"), name=name or uniq("Upc002land"), overview="Guide" if visible else "", tuition="", living_expenses="",
                      visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[], iso2=iso2, region=region,
                      catalogue_visible=visible)
    db.add(country)
    await db.commit()
    return country


@pytest.mark.asyncio
async def test_public_list_shows_visible_countries_only(client, db_session):  # upc-002-AC1
    shown = await _country(db_session, visible=True)
    hidden = await _country(db_session, visible=False)
    slugs = {c["slug"] for c in (await client.get("/api/v1/public/countries")).json()}
    assert shown.slug in slugs and hidden.slug not in slugs
    assert "japan" not in slugs  # the seeded ISO rows are internal


@pytest.mark.asyncio
async def test_public_list_contract_is_unchanged(client, db_session):
    shown = await _country(db_session, visible=True)
    match = next(c for c in (await client.get("/api/v1/public/countries")).json() if c["slug"] == shown.slug)
    assert set(match) == {"id", "slug", "name", "overview", "tuition", "living_expenses", "visa_process", "work_opportunities", "post_study_work", "pr_opportunities", "faq"}


@pytest.mark.asyncio
async def test_public_detail_of_an_internal_country_is_a_plain_404(client, db_session):
    hidden = await _country(db_session, visible=False)
    for slug in (hidden.slug, "japan", "no-such-country"):
        response = await client.get(f"/api/v1/public/countries/{slug}")
        assert response.status_code == 404 and response.json()["detail"] == "Country not found", slug


@pytest.mark.asyncio
async def test_every_seeded_iso_country_exists_once_with_a_region(db_session):  # upc-002-AC2 on the migrated test database
    rows = (await db_session.execute(select(Country.iso2, Country.region).where(Country.iso2.is_not(None)))).all()
    assert len(rows) == 249 and len({iso2 for iso2, _ in rows}) == 249 and all(region for _, region in rows)


@pytest.mark.asyncio
async def test_lookup_finds_japan_by_name_or_code_for_an_overseas_admin(client, db_session):  # positive: Japan is selectable
    japan = await db_session.scalar(select(Country).where(Country.iso2 == "JP"))
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    expected = {"id": str(japan.id), "label": japan.name, "detail": "JP · Asia"}
    by_name = await client.get(LOOKUP, params={"q": "japa"})
    by_code = await client.get(LOOKUP, params={"q": "jp"})
    assert by_name.status_code == 200 and expected in by_name.json()["items"]
    assert by_code.json()["items"][0] == expected  # the exact code ranks first


@pytest.mark.asyncio
async def test_lookup_lists_visible_and_internal_rows_and_pages(client, db_session):
    tag = uniq("Upc002")
    await _country(db_session, visible=True, name=f"{tag} Shown")
    await _country(db_session, visible=False, name=f"{tag} Hidden")
    admin = await mk_user(db_session, role="super_admin", division="global")
    await login(client, admin.email)
    body = (await client.get(LOOKUP, params={"q": tag})).json()
    assert [i["label"] for i in body["items"]] == [f"{tag} Hidden", f"{tag} Shown"] and body["truncated"] is False
    assert all(i["detail"] is None for i in body["items"])  # a row without a code or region (test data) has no detail
    page = (await client.get(LOOKUP, params={"limit": 5})).json()
    assert len(page["items"]) == 5 and page["truncated"] is True


@pytest.mark.asyncio
async def test_lookup_requires_sign_in(client):
    assert (await client.get(LOOKUP)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("counselor", "overseas"), ("student", "overseas"), ("it_admin", "it")])
async def test_lookup_refuses_other_roles(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division=division)
    assert (await client.get(LOOKUP)).status_code == 403


@pytest.mark.asyncio
async def test_lookup_validates_its_query(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert (await client.get(LOOKUP, params={"q": "x" * 101})).status_code == 422
    assert (await client.get(LOOKUP, params={"limit": 0})).status_code == 422
    assert (await client.get(LOOKUP, params={"limit": 51})).status_code == 422
    wildcards = await client.get(LOOKUP, params={"q": "%_"})
    assert wildcards.status_code == 200 and wildcards.json()["items"] == []  # LIKE wildcards are literal, not match-all


@pytest.mark.asyncio
async def test_admin_cannot_create_a_catalogue_university_in_an_internal_country(client, db_session):  # design C5
    hidden = await _country(db_session, visible=False)
    shown = await _country(db_session, visible=True)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    body = {"slug": uniq("upc002-u"), "name": "Upc University"}
    refused = await client.post("/api/v1/admin/universities", json={**body, "country_slug": hidden.slug})
    assert refused.status_code == 422 and refused.json()["detail"] == "Unknown country"
    created = await client.post("/api/v1/admin/universities", json={**body, "country_slug": shown.slug})
    assert created.status_code == 201


@pytest.mark.asyncio
async def test_seed_turns_a_migration_placeholder_into_the_catalogue_row(db_session):  # design C8: fresh database order
    from app.seed import catalogue_country

    placeholder = await _country(db_session, visible=False, name="Placeholder")
    row = [placeholder.slug, "Catalogue Name", "Overview text", "Tuition text", "Living text", "ZZ", "Asia"]
    country = await catalogue_country(db_session, row, {placeholder.slug: "Prep"})
    await db_session.commit()
    assert country.id == placeholder.id and country.catalogue_visible
    assert (country.name, country.overview, country.tuition, country.living_expenses, country.interview_prep) == (
        "Catalogue Name", "Overview text", "Tuition text", "Living text", "Prep")
    assert country.iso2 is None  # an existing row's code is the migration's, never the seed file's


@pytest.mark.asyncio
async def test_seed_never_overwrites_a_country_with_content(db_session):
    from app.seed import catalogue_country

    existing = await _country(db_session, visible=True, name="Kept")
    row = [existing.slug, "Other", "Other overview", "t", "l", "ZZ", "Asia"]
    country = await catalogue_country(db_session, row, {})
    assert (country.id, country.name, country.overview) == (existing.id, "Kept", "Guide")
