"""upc-017 -- the public catalogue shows the active courses of published universities, with its keys unchanged and never a commission
(AC3, CO13, U2)."""

import uuid

import pytest
from sqlalchemy import select, update

from app.models import Country, University
from tests.test_upc_017_courses import add_course, courses_url
from tests.upc003_helpers import create, login, make_user

PUBLIC = "/api/v1/public"
KEYS = {"id", "title", "level", "category", "duration", "tuition_fee", "intake"}


@pytest.mark.asyncio
async def test_only_active_courses_of_published_universities_and_never_commission(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    await login(client, admin)
    sweden = await db_session.scalar(select(Country).where(Country.iso2 == "SE", Country.catalogue_visible.is_(True)))
    uni = await create(client, sweden.id, name=f"Course University {uuid.uuid4().hex[:8]}", overview="Overview")
    category = f"Cat {uuid.uuid4().hex[:8]}"
    shown = await add_course(client, uni["id"], category=category, commission={"percent": "15"})
    paused = await add_course(client, uni["id"], category=category, title=f"MSc Paused {uuid.uuid4().hex[:6]}")
    await client.patch(courses_url(uni["id"], paused["id"]), json={"active": False})
    client.cookies.clear()
    listed = lambda: client.get(f"{PUBLIC}/overseas-courses", params={"category": category})  # noqa: E731
    assert (await listed()).json() == []  # unpublished university (AC3)
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(catalogue_visible=True))
    await db_session.commit()
    response = await listed()
    assert [c["id"] for c in response.json()] == [shown["id"]]  # the inactive course is not offered (CO11)
    assert set(response.json()[0]) == KEYS | {"university", "country"} and response.json()[0]["tuition_fee"] == "GBP 18,000"
    assert "commission" not in response.text and "15.00" not in response.text
    detail = await client.get(f"{PUBLIC}/universities/{uni['slug']}")
    assert [c["id"] for c in detail.json()["courses"]] == [shown["id"]] and set(detail.json()["courses"][0]) == KEYS
    assert "commission" not in detail.text
