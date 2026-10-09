"""upc-017 -- course CSV import, per university (spec §1 CO14, Q-21)."""

import csv
import io
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, CourseImportBatch, OverseasCourse
from tests.test_upc_017_courses import add_course, courses_url
from tests.test_upc_026_documents import _owned
from tests.upc003_helpers import login, make_pm, make_user, url

HEADER = "title,level,category,duration,intakes,tuition_amount,tuition_currency,english_test,english_score,deadline,active"


def import_url(university_id) -> str:
    return url(university_id, "courses/import")


def _csv(*rows: str, header: str = HEADER) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


async def _upload(client, university_id, content: bytes, key: str | None = None):
    return await client.post(import_url(university_id), files={"file": ("courses.csv", content, "text/csv")}, headers={"Idempotency-Key": key or f"k-{uuid.uuid4().hex[:8]}"})


@pytest.mark.asyncio
async def test_template_lists_the_columns_without_commission(client, db_session):
    _, _, other, uni = await _owned(client, db_session)
    response = await client.get(url(uni["id"], "courses/imports/template"))
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    header = next(csv.reader(io.StringIO(response.text)))
    assert header[:4] == ["title", "level", "category", "duration"] and "intakes" in header and not any("commission" in h for h in header)
    await login(client, other)
    assert (await client.get(url(uni["id"], "courses/imports/template"))).status_code == 403


@pytest.mark.asyncio
async def test_rows_are_created_duplicate_or_invalid_with_a_reason(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await add_course(client, uni["id"], title="MSc Existing")
    content = _csv(
        "MSc Cyber Security,pg,Computer Science,1 year,Sep;Jan,18000,GBP,IELTS,6.5,2027-06-30,yes",
        "BSc Nursing,UG,Health,3 years,,,,,,,",
        "msc  existing,PG,Tech,1 year,,,,,,,",  # matches the master (CO12)
        "MSc Cyber Security,PG,Again,1 year,,,,,,,",  # repeats row 2
        "MBA,Masters,Business,1 year,,,,,,,",  # not a master level
        "MSc Bad Fee,PG,Tech,1 year,,-5,GBP,,,,",
        "MSc Bad Date,PG,Tech,1 year,,,,,,30/06/2027,",
        "MSc Paused,PG,Tech,1 year,,,,,,,no",
    )
    response = await _upload(client, uni["id"], content)
    assert response.status_code == 201, response.text
    report = response.json()
    assert (report["total_rows"], report["created_count"], report["duplicate_count"], report["invalid_count"]) == (8, 3, 2, 3)
    rows = {r["row_number"]: r for r in report["rows"]}
    assert rows[2]["status"] == "created" and rows[3]["status"] == "created" and rows[9]["status"] == "created"
    assert rows[4]["status"] == "duplicate" and rows[5] == rows[5] | {"status": "duplicate", "reason": "Repeats row 2 of this file"}
    assert all(rows[n]["status"] == "invalid" and rows[n]["reason"] for n in (6, 7, 8))
    cyber = await db_session.get(OverseasCourse, uuid.UUID(rows[2]["course_id"]))
    assert (cyber.level, cyber.intakes, cyber.intake, cyber.tuition_fee, str(cyber.english_score), cyber.active) == ("PG", ["Jan", "Sep"], "Jan, Sep", "GBP 18,000", "6.5", True)
    paused = await db_session.get(OverseasCourse, uuid.UUID(rows[9]["course_id"]))
    assert paused.active is False and paused.commission_percent is None
    batch = await db_session.get(CourseImportBatch, uuid.UUID(report["id"]))
    assert batch.university_id == uuid.UUID(uni["id"]) and batch.uploaded_by_user_id == pm.id
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id.in_([rows[n]["course_id"] for n in (2, 3, 9)])))).all()
    assert sorted(actions) == ["university_course.create"] * 3
    assert (await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == report["id"]))).action == "university_course.import"


@pytest.mark.asyncio
async def test_the_same_key_replays_and_a_new_key_creates_nothing_new(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    content = _csv("MSc Replay,PG,Tech,1 year,,,,,,,")
    first = (await _upload(client, uni["id"], content, key="replay-1")).json()
    again = await _upload(client, uni["id"], content, key="replay-1")
    assert again.status_code == 201 and again.json()["id"] == first["id"]
    assert (await _upload(client, uni["id"], _csv("MSc Other,PG,Tech,1 year,,,,,,,"), key="replay-1")).status_code == 422
    fresh = (await _upload(client, uni["id"], content)).json()
    assert fresh["created_count"] == 0 and fresh["duplicate_count"] == 1
    assert (await client.get(courses_url(uni["id"]))).json()["total"] == 1


@pytest.mark.asyncio
async def test_file_problems_and_roles(client, db_session):
    head, _, _, uni = await _owned(client, db_session)
    assert (await _upload(client, uni["id"], _csv("x", header="name,country"))).status_code == 422  # wrong columns
    assert (await _upload(client, uni["id"], _csv("MSc,PG,Tech,1 year,,,,,,,,", header=HEADER + ",commission"))).status_code == 422
    assert (await client.post(import_url(uni["id"]), files={"file": ("c.csv", _csv(), "text/csv")})).status_code == 422  # no key
    await login(client, await make_pm(db_session, head))
    assert (await _upload(client, uni["id"], _csv("MSc,PG,Tech,1 year,,,,,,,"))).status_code == 403
    await login(client, await make_user(db_session, "counselor", "overseas"))
    assert (await _upload(client, uni["id"], _csv("MSc,PG,Tech,1 year,,,,,,,"))).status_code == 403
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await _upload(client, uni["id"], _csv("MSc By Admin,PG,Tech,1 year,,,,,,,"))).status_code == 201
    assert (await _upload(client, uuid.uuid4(), _csv("MSc,PG,Tech,1 year,,,,,,,"))).status_code == 404
