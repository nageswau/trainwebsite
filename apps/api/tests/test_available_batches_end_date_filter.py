"""RAID.md I-25: `GET /workflows/it/batches/available` never excluded a batch whose own
`end_date` had already passed -- confirmed directly, surfaced by a user screenshot of the
student's own slot picker showing several stale, already-ended test cohorts alongside
real ones. A batch that has already ended has nothing left to enrol into, regardless of
its stored `status`/`enrollment_open` flags.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Program, User


async def _create_student(db_session) -> User:
    student = User(
        email=f"end-date-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="End Date Filter Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _create_batch(db_session, *, end_date: datetime.date, name: str) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"End Date Filter Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id,
        name=name,
        start_date=datetime.date.today() - datetime.timedelta(days=180),
        end_date=end_date,
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_batch_whose_end_date_has_already_passed_is_excluded(client, db_session):
    student = await _create_student(db_session)
    ended = await _create_batch(db_session, end_date=datetime.date.today() - datetime.timedelta(days=1), name=f"Ended Batch {uuid.uuid4().hex[:6]}")
    await _login(client, student.email)

    response = await client.get("/api/v1/workflows/it/batches/available")
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert str(ended.id) not in ids


@pytest.mark.asyncio
async def test_a_batch_ending_today_or_later_is_still_listed(client, db_session):
    student = await _create_student(db_session)
    ending_today = await _create_batch(db_session, end_date=datetime.date.today(), name=f"Ending Today Batch {uuid.uuid4().hex[:6]}")
    still_open = await _create_batch(db_session, end_date=datetime.date.today() + datetime.timedelta(days=30), name=f"Still Open Batch {uuid.uuid4().hex[:6]}")
    await _login(client, student.email)

    response = await client.get("/api/v1/workflows/it/batches/available")
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert str(ending_today.id) in ids
    assert str(still_open.id) in ids
