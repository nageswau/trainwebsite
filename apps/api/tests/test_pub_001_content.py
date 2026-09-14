"""PUB-001 -- Corporate & IT marketing content: Career Paths, Real Projects,
Success Stories (Testimonials), Business Services."""

import pytest


@pytest.mark.asyncio
async def test_career_paths_list_and_detail(client):
    listing = await client.get("/api/v1/public/career-paths?division=it")
    assert listing.status_code == 200
    paths = listing.json()
    assert len(paths) > 0
    first = paths[0]
    assert {"id", "slug", "title", "summary", "skills", "related_program_slugs", "outcomes"} <= set(first)

    detail = await client.get(f"/api/v1/public/career-paths/{first['slug']}")
    assert detail.status_code == 200
    assert detail.json()["slug"] == first["slug"]


@pytest.mark.asyncio
async def test_career_path_detail_404_for_unknown_slug(client):
    response = await client.get("/api/v1/public/career-paths/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_real_projects_list_and_detail(client):
    listing = await client.get("/api/v1/public/real-projects?division=it")
    assert listing.status_code == 200
    projects = listing.json()
    assert len(projects) > 0
    first = projects[0]
    assert {"id", "slug", "title", "summary", "description", "tech_stack"} <= set(first)

    detail = await client.get(f"/api/v1/public/real-projects/{first['slug']}")
    assert detail.status_code == 200
    assert detail.json()["description"]


@pytest.mark.asyncio
async def test_real_project_detail_404_for_unknown_slug(client):
    response = await client.get("/api/v1/public/real-projects/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_testimonials_list_and_detail(client):
    listing = await client.get("/api/v1/public/testimonials?division=it")
    assert listing.status_code == 200
    stories = listing.json()
    assert len(stories) > 0
    first = stories[0]

    detail = await client.get(f"/api/v1/public/testimonials/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["person_name"] == first["person_name"]


@pytest.mark.asyncio
async def test_testimonial_detail_404_for_unknown_id(client):
    import uuid

    response = await client.get(f"/api/v1/public/testimonials/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_business_services_content_page(client):
    response = await client.get("/api/v1/cms/pages/it/business-services")
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "business-services"
    assert body["title"]
    assert body["body"]


@pytest.mark.asyncio
async def test_public_content_endpoints_require_no_authentication(client):
    # PUB-001: Visitor (unauthenticated) browsing -- these must never demand a session.
    for path in (
        "/api/v1/public/career-paths",
        "/api/v1/public/real-projects",
        "/api/v1/public/testimonials",
        "/api/v1/cms/pages/it/business-services",
    ):
        response = await client.get(path)
        assert response.status_code == 200, f"{path} unexpectedly required auth"
