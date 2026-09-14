"""OVS-001 -- Destination/university/course discovery.

The reference-implementation `Country`/`University`/`OverseasCourse`/`Scholarship`
models and the `/public/countries`, `/public/universities`, `/public/overseas-courses`
listing+detail endpoints already existed and already satisfied this feature's contract
(`DATA_MODEL.md` #6.1: "carries over") -- no code change was needed. This file adds the
test evidence this Feature ID never had (`TEST_CATALOG_AUDIT.md` #12: "None").
"""

import uuid

import pytest

from app.models import Country, OverseasCourse, Scholarship, University


async def _make_country(db_session, **overrides):
    defaults = dict(
        slug=f"test-country-{uuid.uuid4().hex[:8]}",
        name="Testland",
        overview="A test study destination.",
        tuition="USD 20,000 - 30,000/year",
        living_expenses="USD 1,000/month",
        visa_process=["Apply", "Interview", "Approval"],
        work_opportunities="20 hrs/week during study.",
        post_study_work="2-year post-study work visa.",
        pr_opportunities="Points-based PR pathway.",
        faq=[{"question": "Is IELTS required?", "answer": "Yes."}],
    )
    defaults.update(overrides)
    country = Country(**defaults)
    db_session.add(country)
    await db_session.commit()
    await db_session.refresh(country)
    return country


async def _make_university(db_session, country_id, **overrides):
    defaults = dict(
        country_id=country_id,
        slug=f"test-university-{uuid.uuid4().hex[:8]}",
        name="Test University",
        city="Testville",
        overview="A test university.",
        eligibility="65% aggregate, IELTS 6.5.",
        requirements=["Transcripts", "SOP", "LOR"],
        deadlines=["Fall: 15 May", "Spring: 15 Oct"],
        scholarships=["Merit scholarship up to 25%"],
    )
    defaults.update(overrides)
    university = University(**defaults)
    db_session.add(university)
    await db_session.commit()
    await db_session.refresh(university)
    return university


async def _make_course(db_session, university_id, **overrides):
    defaults = dict(
        university_id=university_id,
        title="MSc Test Engineering",
        level="Masters",
        category="Engineering",
        duration="2 years",
        tuition_fee="USD 25,000/year",
        intake="Fall, Spring",
    )
    defaults.update(overrides)
    course = OverseasCourse(**defaults)
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_countries_list_is_public_and_returns_full_detail_fields(client, db_session):
    country = await _make_country(db_session)

    response = await client.get("/api/v1/public/countries")
    assert response.status_code == 200
    body = response.json()
    assert any(c["slug"] == country.slug for c in body)
    match = next(c for c in body if c["slug"] == country.slug)
    assert {"slug", "name", "overview", "tuition", "living_expenses", "visa_process", "work_opportunities", "post_study_work", "pr_opportunities", "faq"} <= set(match)


@pytest.mark.asyncio
async def test_country_detail_includes_universities_and_scholarships(client, db_session):
    country = await _make_country(db_session)
    university = await _make_university(db_session, country.id)
    scholarship = Scholarship(title="Test Scholarship", country_id=country.id, eligibility="Any", amount="USD 5,000", active=True)
    db_session.add(scholarship)
    await db_session.commit()

    response = await client.get(f"/api/v1/public/countries/{country.slug}")
    assert response.status_code == 200
    body = response.json()
    assert body["country"]["slug"] == country.slug
    assert any(u["slug"] == university.slug for u in body["universities"])
    assert any(s["title"] == "Test Scholarship" for s in body["scholarships"])


@pytest.mark.asyncio
async def test_country_detail_404_for_unknown_slug_not_a_broken_page(client):
    response = await client.get("/api/v1/public/countries/no-such-country")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_universities_list_filterable_by_country_and_search(client, db_session):
    country = await _make_country(db_session)
    university = await _make_university(db_session, country.id, name="Uniquely Named Institute")

    by_country = await client.get("/api/v1/public/universities", params={"country": country.slug})
    assert by_country.status_code == 200
    assert any(u["slug"] == university.slug for u in by_country.json())

    by_search = await client.get("/api/v1/public/universities", params={"q": "Uniquely Named"})
    assert by_search.status_code == 200
    assert any(u["slug"] == university.slug for u in by_search.json())

    no_match = await client.get("/api/v1/public/universities", params={"q": "no-such-institute-xyz"})
    assert no_match.status_code == 200
    assert no_match.json() == []


@pytest.mark.asyncio
async def test_university_detail_includes_its_courses(client, db_session):
    country = await _make_country(db_session)
    university = await _make_university(db_session, country.id)
    course = await _make_course(db_session, university.id)

    response = await client.get(f"/api/v1/public/universities/{university.slug}")
    assert response.status_code == 200
    body = response.json()
    assert body["university"]["slug"] == university.slug
    assert any(c["title"] == course.title for c in body["courses"])


@pytest.mark.asyncio
async def test_university_detail_404_for_unknown_slug_not_a_broken_page(client):
    response = await client.get("/api/v1/public/universities/no-such-university")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_overseas_courses_filterable_by_category_and_level(client, db_session):
    country = await _make_country(db_session)
    university = await _make_university(db_session, country.id)
    course = await _make_course(db_session, university.id, category="Data Science", level="Masters")

    by_category = await client.get("/api/v1/public/overseas-courses", params={"category": "Data Science"})
    assert by_category.status_code == 200
    assert any(c["title"] == course.title for c in by_category.json())

    by_level = await client.get("/api/v1/public/overseas-courses", params={"level": "Masters"})
    assert by_level.status_code == 200
    assert any(c["title"] == course.title for c in by_level.json())

    no_match = await client.get("/api/v1/public/overseas-courses", params={"category": "no-such-category"})
    assert no_match.status_code == 200
    assert no_match.json() == []


@pytest.mark.asyncio
async def test_incomplete_admin_data_renders_only_present_fields_never_fabricated(client, db_session):
    # OVS-001-AC02: a record with an incomplete admin-entered field (tuition, here)
    # must show only what exists -- never a fabricated placeholder like "N/A" or
    # "Coming soon". Holds by construction (the API round-trips the stored value
    # verbatim, no substitution logic exists anywhere in this path) -- verified
    # directly rather than assumed.
    country = await _make_country(db_session, tuition="", living_expenses="")

    response = await client.get(f"/api/v1/public/countries/{country.slug}")
    assert response.status_code == 200
    body = response.json()["country"]
    assert body["tuition"] == ""
    assert body["living_expenses"] == ""
    for placeholder in ("N/A", "n/a", "TBD", "Coming soon", "Not available", "null", "None"):
        assert placeholder not in body["tuition"]
        assert placeholder not in body["living_expenses"]


@pytest.mark.asyncio
async def test_discovery_endpoints_require_no_authentication(client):
    for path in ("/api/v1/public/countries", "/api/v1/public/universities", "/api/v1/public/overseas-courses"):
        assert (await client.get(path)).status_code == 200
