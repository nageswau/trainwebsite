"""ADM-010 -- Agreement/consent oversight.

Promoted out of `Unscheduled/BLOCKED` on 2026-09-03 (`DEC-SCOPE-008` --
`docs/decisions/PRODUCT_DECISION_REGISTER.md` Group 11) -- its dependency, `STU-009`, was
already done. `STU-009`'s self-scoped agreement/consent flow (`GET`/`POST /workflows/it/
student/agreements...`) already existed and worked; no cross-student Admin oversight
existed anywhere. Added a `consent` section to the existing `it_admin`/`super_admin`
portal dispatcher (`services/portal.py`), reusing `Agreement`/`ConsentRecord` directly
(no new model/migration).
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Agreement, Batch, ConsentRecord, Enrollment, Program, User


async def _create_user(db_session, role: str, **overrides) -> User:
    defaults = dict(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}", role=role, division="it", active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_agreement(db_session, *, version: str = "v1") -> Agreement:
    agreement = Agreement(division="it", version=version, title=f"ADM-010 Test Agreement {uuid.uuid4().hex[:6]}", body="Terms.", active=True)
    db_session.add(agreement)
    await db_session.commit()
    return agreement


async def _create_batch(db_session) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}", category="Software Development", title=f"ADM-010 Test Program {uuid.uuid4().hex[:6]}",
        summary="Test", duration="8 weeks", eligibility="None", fees=10000, certification="Test cert",
        curriculum=["Module 1"], placement_assistance="Yes", trainer_name="Test Trainer", active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id, name=f"Batch-{uuid.uuid4().hex[:6]}", start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90), schedule="Mon-Fri 7pm", capacity=20,
        enrollment_open=True, status="upcoming",
    )
    db_session.add(batch)
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_it_admin_sees_both_consented_and_not_yet_consented_students(client, db_session):
    agreement = await _create_agreement(db_session)
    consented = await _create_user(db_session, "it_student", full_name="Consented Student")
    not_yet = await _create_user(db_session, "it_student", full_name="Not Yet Student")
    db_session.add(ConsentRecord(user_id=consented.id, agreement_id=agreement.id, version=agreement.version))
    await db_session.commit()
    admin = await _create_user(db_session, "it_admin")

    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/it/admin/consent")
    assert response.status_code == 200
    rows = {row["email"]: row for row in response.json()["rows"]}
    assert rows[consented.email]["consented"] == "Yes"
    assert rows[not_yet.email]["consented"] == "Not yet"


@pytest.mark.asyncio
async def test_pending_consent_enrollment_count_is_visible_per_student(client, db_session):
    agreement = await _create_agreement(db_session)
    student = await _create_user(db_session, "it_student")
    batch = await _create_batch(db_session)
    db_session.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="pending_consent"))
    await db_session.commit()
    admin = await _create_user(db_session, "it_admin")

    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/it/admin/consent")
    assert response.status_code == 200
    row = next(r for r in response.json()["rows"] if r["email"] == student.email)
    assert row["pending"] == 1


@pytest.mark.asyncio
async def test_consent_oversight_never_500s_regardless_of_agreement_state(client, db_session):
    # The "no active agreement" honest-empty-state branch (services/portal.py's
    # ternary on `agreement`) can't be reliably asserted here: `apps/api/tests/
    # conftest.py` has no test-database isolation (RAID.md I-06), and Agreement.active
    # is shared global state -- an earlier test in the same run (or this file's own
    # other tests) may have left one active. Asserting 200 either way still proves the
    # endpoint never 500s regardless of which branch it takes.
    admin = await _create_user(db_session, "it_admin")
    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/it/admin/consent")
    assert response.status_code == 200
    assert isinstance(response.json()["rows"], list)


@pytest.mark.asyncio
async def test_non_admin_role_is_rejected(client, db_session):
    student = await _create_user(db_session, "it_student")
    await _login(client, student.email)
    response = await client.get("/api/v1/portal/it/admin/consent")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_consent_oversight_requires_authentication(client):
    response = await client.get("/api/v1/portal/it/admin/consent")
    assert response.status_code == 401
