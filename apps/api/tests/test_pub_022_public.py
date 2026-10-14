"""PUB-022 -- public social proof reads (DEC-SCOPE-210 SP3/SP4/SP7/SP8; spec §4.1).

Shared DB: strip rows use display_order -1000-n so they sort ahead of anything else, and assertions look at our own ids."""

import uuid

import pytest
from sqlalchemy import delete

from app.models import Testimonial
from tests.test_pub_022_cms import as_role, create, leave_no_social_proof_behind, png_bytes  # noqa: F401 -- autouse cleanup

STRIP_RANGE = -1000  # display_order at or below this belongs to strip tests only


async def clear_strip_range(db_session) -> None:
    """Earlier runs leave rows behind (the DB is never truncated); strip tests own this order range and start from it empty."""
    await db_session.execute(delete(Testimonial).where(Testimonial.display_order <= STRIP_RANGE))
    await db_session.commit()


async def published(client, **overrides) -> dict:
    return await create(client, consent_confirmed=True, published=True, **overrides)


def ids(rows) -> list[str]:
    return [row["id"] for row in rows]


@pytest.mark.asyncio
async def test_unpublished_rows_never_reach_the_public(client, db_session):
    await as_role(client, db_session, "super_admin")
    hidden = await create(client, consent_confirmed=True, featured=True, display_order=-500)
    shown = await published(client)
    client.cookies.clear()
    listing = ids((await client.get("/api/v1/public/testimonials?division=it")).json())
    assert shown["id"] in listing and hidden["id"] not in listing
    assert (await client.get(f"/api/v1/public/testimonials/{hidden['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/public/testimonials/{shown['id']}")).json()["person_name"] == shown["person_name"]
    assert hidden["id"] not in ids((await client.get("/api/v1/public/social-proof?division=it")).json()["testimonials"])
    home = (await client.get("/api/v1/public/home")).json()
    assert hidden["person_name"] not in {t["name"] for t in home["testimonials"]}


@pytest.mark.asyncio
async def test_home_has_no_hard_coded_stats(client):
    assert "stats" not in (await client.get("/api/v1/public/home")).json()


@pytest.mark.asyncio
async def test_strip_is_featured_ordered_and_capped_at_six(client, db_session):
    await clear_strip_range(db_session)
    await as_role(client, db_session, "super_admin")
    tag = uuid.uuid4().hex[:6]
    rows = [await published(client, featured=True, display_order=-1000 - n, headline=f"{tag}-{n}") for n in range(7)]
    not_featured = await published(client, featured=False, display_order=-2000)
    client.cookies.clear()
    strip = (await client.get("/api/v1/public/social-proof?division=it")).json()["testimonials"]
    assert len(strip) == 6
    # display_order ascending: -1006 first ... the six lowest of ours fill the strip
    assert ids(strip) == [r["id"] for r in sorted(rows, key=lambda r: r["display_order"])][:6]
    assert not_featured["id"] not in ids(strip)
    assert all("photo_key" not in row and set(row) == {"id", "division", "person_name", "headline", "quote", "rating", "context", "photo_url"} for row in strip)


@pytest.mark.asyncio
async def test_strip_filters_by_division(client, db_session):
    await clear_strip_range(db_session)
    await as_role(client, db_session, "super_admin")
    it = await published(client, division="it", featured=True, display_order=-20000)
    ovs = await published(client, division="overseas", featured=True, display_order=-20000)
    client.cookies.clear()
    it_strip = ids((await client.get("/api/v1/public/social-proof?division=it")).json()["testimonials"])
    ovs_strip = ids((await client.get("/api/v1/public/social-proof?division=overseas")).json()["testimonials"])
    all_strip = ids((await client.get("/api/v1/public/social-proof")).json()["testimonials"])
    assert it["id"] in it_strip and ovs["id"] not in it_strip
    assert ovs["id"] in ovs_strip and it["id"] not in ovs_strip
    assert {it["id"], ovs["id"]} <= set(all_strip)
    assert (await client.get("/api/v1/public/social-proof?division=school")).status_code == 422


@pytest.mark.asyncio
async def test_badge_is_hidden_until_published(client, db_session):
    await as_role(client, db_session, "super_admin")
    payload = {"source_name": "Google", "rating": 4.8, "review_count": 77, "as_of": "2026-10-01", "published": False}
    assert (await client.put("/api/v1/cms/rating-badge", json=payload)).status_code == 200
    assert (await client.get("/api/v1/public/social-proof")).json()["badge"] is None
    assert (await client.put("/api/v1/cms/rating-badge", json={**payload, "published": True})).status_code == 200
    client.cookies.clear()
    badge = (await client.get("/api/v1/public/social-proof")).json()["badge"]
    assert badge == {"source_name": "Google", "rating": 4.8, "review_count": 77, "review_url": None, "as_of": "2026-10-01"}


@pytest.mark.asyncio
async def test_photo_is_public_only_while_published(client, db_session):
    await as_role(client, db_session, "it_admin")
    row = await published(client)
    tid = row["id"]
    image = png_bytes()
    assert (await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("me.png", image, "image/png")})).status_code == 200
    detail = (await client.get(f"/api/v1/public/testimonials/{tid}")).json()
    assert detail["photo_url"].startswith(f"/api/v1/public/testimonials/{tid}/photo?v=")
    photo = await client.get(detail["photo_url"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/png" and photo.content.startswith(b"\x89PNG")
    assert photo.headers["x-content-type-options"] == "nosniff" and photo.headers["cache-control"] == "no-cache"
    # a replaced photo gets a new URL, so no cache can keep serving the old one
    await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("me.png", png_bytes(), "image/png")})
    assert (await client.get(f"/api/v1/public/testimonials/{tid}")).json()["photo_url"] != detail["photo_url"]


@pytest.mark.asyncio
async def test_photo_404_after_unpublish(client, db_session):
    await as_role(client, db_session, "it_admin")
    tid = (await published(client))["id"]
    await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("me.png", png_bytes(), "image/png")})
    assert (await client.get(f"/api/v1/public/testimonials/{tid}/photo")).status_code == 200
    await client.patch(f"/api/v1/cms/testimonials/{tid}", json={"published": False})
    assert (await client.get(f"/api/v1/public/testimonials/{tid}/photo")).status_code == 404
    assert (await client.get(f"/api/v1/public/testimonials/{uuid.uuid4()}/photo")).status_code == 404


@pytest.mark.asyncio
async def test_public_reads_need_no_login(client):
    for path in ("/api/v1/public/social-proof", "/api/v1/public/social-proof?division=it", "/api/v1/public/testimonials"):
        assert (await client.get(path)).status_code == 200
