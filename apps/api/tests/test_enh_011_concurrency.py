import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from enh011_helpers import BATCHES, ENROLMENTS, SESSIONS, create_batch, enrol, login, skills_world
from httpx import ASGITransport
from sqlalchemy import func, select

from app.api import school_skills
from app.core.database import SessionLocal
from app.main import app
from app.models import AuditLog, Notification, SchoolSkillBatch, SchoolSkillEnrollment

# ENH-011 spec §5.4. Each test holds a row lock in a SEPARATE transaction so the competing requests are genuinely queued behind
# it, then releases it: the interleaving is forced, not left to timing (the ENH-005 concurrency tests' method). AC-05.


@asynccontextmanager
async def _client_for(email: str):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@asynccontextmanager
async def _held(model, pk, *, read: bool = False):
    session = SessionLocal()
    try:
        await session.execute(select(model).where(model.id == pk).with_for_update(read=read))
        yield
    finally:
        await session.rollback()
        await session.close()


async def _waiting(*tasks) -> None:
    await asyncio.sleep(0.7)
    assert not any(t.done() for t in tasks), "a request did not wait for the row lock"


@pytest.mark.asyncio
async def test_two_concurrent_certifies_give_one_transition_and_one_notification(db_session):
    w = await skills_world(db_session)
    async with _client_for(w["counselor"].email) as client:
        batch = await create_batch(client, w["a"]["school"].id)
        [row] = await enrol(client, batch["id"], w["a"]["students"][0])
        before = await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == w["a"]["parent"].id))
        async with _held(SchoolSkillEnrollment, row["id"]):
            first = asyncio.create_task(client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "certified"}))
            second = asyncio.create_task(client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "certified"}))
            await _waiting(first, second)
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=20)
    assert [r.status_code for r in results] == [200, 200] and {r.json()["status"] for r in results} == {"certified"}
    after = await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == w["a"]["parent"].id))
    changes = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.skill_enrollment_status_change", AuditLog.entity_id == row["id"]))
    assert after - before == 1 and changes == 1


@pytest.mark.asyncio
async def test_two_concurrent_enrolments_of_the_same_student_give_one_201_and_one_409(db_session):
    w = await skills_world(db_session)
    kid = w["a"]["students"][0]
    async with _client_for(w["counselor"].email) as client:
        batch = await create_batch(client, w["a"]["school"].id)
        body = {"school_student_ids": [str(kid.id)]}
        async with _held(SchoolSkillBatch, batch["id"]):
            first = asyncio.create_task(client.post(f"{BATCHES}/{batch['id']}/enrollments", json=body))
            second = asyncio.create_task(client.post(f"{BATCHES}/{batch['id']}/enrollments", json=body))
            await _waiting(first, second)
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=20)
    assert sorted(r.status_code for r in results) == [201, 409]
    assert await db_session.scalar(select(func.count()).select_from(SchoolSkillEnrollment).where(SchoolSkillEnrollment.batch_id == batch["id"])) == 1


@pytest.mark.asyncio
async def test_concurrent_enrolments_cannot_exceed_the_cap(db_session, monkeypatch):
    monkeypatch.setattr(school_skills, "MAX_ENROLMENTS_PER_BATCH", 1)
    w = await skills_world(db_session)
    kid0, kid1 = w["a"]["students"]
    async with _client_for(w["counselor"].email) as client:
        batch = await create_batch(client, w["a"]["school"].id)
        # Two different students, so the unique index cannot help: only the batch lock keeps "count, then insert" honest.
        async with _held(SchoolSkillBatch, batch["id"]):
            tasks = [asyncio.create_task(client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(k.id)]})) for k in (kid0, kid1)]
            await _waiting(*tasks)
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
    assert sorted(r.status_code for r in results) == [201, 409]
    assert await db_session.scalar(select(func.count()).select_from(SchoolSkillEnrollment).where(SchoolSkillEnrollment.batch_id == batch["id"])) == 1


@pytest.mark.asyncio
async def test_closing_waits_for_an_in_flight_attendance_write_and_attendance_waits_for_a_close(db_session):
    w = await skills_world(db_session)
    async with _client_for(w["counselor"].email) as client:
        batch = await create_batch(client, w["a"]["school"].id)
        [row] = await enrol(client, batch["id"], w["a"]["students"][0])
        session = (await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": "2026-10-05"})).json()
        # An attendance write holds the batch FOR SHARE: a close must wait for it.
        async with _held(SchoolSkillBatch, batch["id"], read=True):
            close = asyncio.create_task(client.patch(f"{BATCHES}/{batch['id']}", json={"status": "closed"}))
            await _waiting(close)
        assert (await asyncio.wait_for(close, timeout=20)).status_code == 200
        # A close holds the batch row: attendance must wait, then see the batch closed.
        await client.patch(f"{BATCHES}/{batch['id']}", json={"status": "open"})
        async with _held(SchoolSkillBatch, batch["id"]):
            mark = asyncio.create_task(client.put(f"{SESSIONS}/{session['id']}/attendance", json={"records": [{"enrollment_id": row["id"], "present": True}]}))
            await _waiting(mark)
        assert (await asyncio.wait_for(mark, timeout=20)).status_code == 200
