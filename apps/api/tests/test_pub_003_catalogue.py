"""PUB-003 -- Course catalogue and detail."""

import pytest


@pytest.mark.asyncio
async def test_programs_list_is_public_and_returns_full_detail_fields(client):
    response = await client.get("/api/v1/public/programs")
    assert response.status_code == 200
    programs = response.json()
    assert len(programs) > 0
    first = programs[0]
    assert {"slug", "category", "title", "summary", "duration", "eligibility", "fees", "certification", "curriculum", "placement_assistance", "trainer_name"} <= set(first)


@pytest.mark.asyncio
async def test_programs_category_filter_only_returns_matching_category(client):
    all_programs = (await client.get("/api/v1/public/programs")).json()
    category = all_programs[0]["category"]
    filtered = await client.get("/api/v1/public/programs", params={"category": category})
    assert filtered.status_code == 200
    assert all(p["category"] == category for p in filtered.json())
    assert len(filtered.json()) > 0


@pytest.mark.asyncio
async def test_programs_search_query_matches_title_or_summary(client):
    all_programs = (await client.get("/api/v1/public/programs")).json()
    keyword = all_programs[0]["title"].split()[0]
    matched = await client.get("/api/v1/public/programs", params={"q": keyword})
    assert matched.status_code == 200
    assert any(p["slug"] == all_programs[0]["slug"] for p in matched.json())


@pytest.mark.asyncio
async def test_programs_search_with_no_matches_returns_empty_list_not_an_error(client):
    # PUB-003-AC02: "No results -> empty state with guidance" -- the API's job is a
    # clean empty list; the UI's empty-state guidance is verified separately (E2E).
    response = await client.get("/api/v1/public/programs", params={"q": "no-such-program-xyz-123"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_program_detail_returns_full_fields(client):
    slug = (await client.get("/api/v1/public/programs")).json()[0]["slug"]
    detail = await client.get(f"/api/v1/public/programs/{slug}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["slug"] == slug
    assert isinstance(body["curriculum"], list) and len(body["curriculum"]) > 0


@pytest.mark.asyncio
async def test_program_detail_404_for_unknown_slug_not_a_broken_page(client):
    response = await client.get("/api/v1/public/programs/no-such-program")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_programs_endpoints_require_no_authentication(client):
    for path in ("/api/v1/public/programs",):
        assert (await client.get(path)).status_code == 200
