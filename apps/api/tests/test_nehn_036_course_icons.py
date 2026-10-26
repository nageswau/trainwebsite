"""nehn-036 -- an optional subject icon per overseas course (DEC-SCOPE-284 I3-I6): chosen from the curated set, cleared back to automatic
(null), refused outside the set, audited as a field name, and carried by the course and public payloads."""

import uuid

import pytest
from sqlalchemy import select, update

from app.models import COURSE_ICONS, AuditLog, University
from tests.test_upc_017_courses import add_course, courses_url
from tests.test_upc_026_documents import _owned

PUBLIC = "/api/v1/public"


def test_the_curated_set():
    assert COURSE_ICONS == ("ai", "security", "data", "computing", "engineering", "business", "health", "hospitality", "law", "education", "arts", "science", "general")


@pytest.mark.asyncio
async def test_a_writer_chooses_changes_and_clears_the_icon(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    automatic = await add_course(client, uni["id"])
    assert automatic["icon"] is None  # I3: no choice = automatic
    c = await add_course(client, uni["id"], icon="computing")
    assert c["icon"] == "computing"
    response = await client.patch(courses_url(uni["id"], c["id"]), json={"icon": "security"})
    assert response.status_code == 200, response.text
    assert response.json()["course"]["icon"] == "security"
    cleared = await client.patch(courses_url(uni["id"], c["id"]), json={"icon": None})
    assert cleared.status_code == 200 and cleared.json()["course"]["icon"] is None
    listed = (await client.get(courses_url(uni["id"]))).json()["items"]
    assert {x["id"]: x["icon"] for x in listed} == {automatic["id"]: None, c["id"]: None}
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == c["id"], AuditLog.action == "university_course.update"))).all()
    assert [a.metadata_json["fields"] for a in audit] == [["icon"], ["icon"]]  # a field name only, like every course field


@pytest.mark.asyncio
@pytest.mark.parametrize("icon", ["rocket", "", "Computing", "<script>", 3])
async def test_an_icon_outside_the_set_is_refused(client, db_session, icon):
    _, _, _, uni = await _owned(client, db_session)
    c = await add_course(client, uni["id"])
    assert (await client.patch(courses_url(uni["id"], c["id"]), json={"icon": icon})).status_code == 422
    assert (await client.post(courses_url(uni["id"]), json={"title": "MSc X", "level": "PG", "category": "Law", "duration": "1 year", "icon": icon})).status_code == 422


@pytest.mark.asyncio
async def test_the_public_payloads_carry_the_icon(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    category = f"Cat {uuid.uuid4().hex[:8]}"
    chosen = await add_course(client, uni["id"], category=category, icon="ai")
    automatic = await add_course(client, uni["id"], category=category, title=f"MSc Auto {uuid.uuid4().hex[:6]}")
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(catalogue_visible=True))
    await db_session.commit()
    client.cookies.clear()
    listed = (await client.get(f"{PUBLIC}/overseas-courses", params={"category": category})).json()
    assert {x["id"]: x["icon"] for x in listed} == {chosen["id"]: "ai", automatic["id"]: None}
    detail = (await client.get(f"{PUBLIC}/universities/{uni['slug']}")).json()
    assert {x["id"]: x["icon"] for x in detail["courses"]} == {chosen["id"]: "ai", automatic["id"]: None}
