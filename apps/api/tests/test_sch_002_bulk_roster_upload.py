"""SCH-002 -- School Coordinator bulk student roster upload (template-download-first).

Coordinator downloads a fixed-format template, fills it offline, uploads it; server
validates against the template schema and returns a row-level accept/reject report. A row
that fails validation does not block the rest of the batch (SCH-002-AC04). Net-new -- no
equivalent exists in the base codebase.
"""

import io
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import School, SchoolStudent, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_coordinator(db_session, extra_roles: tuple[str, ...] = ()) -> dict:
    admin = User(email=f"sch002-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-002 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()

    accounts = {}
    for role in ("school_coordinator", *extra_roles):
        u = User(email=f"sch002-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=f"Test {role}", role=role, division="overseas", active=True, profile={"school_id": str(school.id)})
        db_session.add(u)
        await db_session.flush()
        db_session.add(UserRoleAssignment(user_id=u.id, division="overseas", role=role, is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
        accounts[role] = u
    await db_session.commit()
    return {"admin": admin, "school": school, **accounts}


def _csv_bytes(rows: list[str]) -> bytes:
    header = "full_name,date_of_birth,grade_or_class,assigned_teacher_email\n"
    return (header + "\n".join(rows)).encode("utf-8")


@pytest.mark.asyncio
async def test_coordinator_downloads_the_roster_template(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["school_coordinator"].email)
    response = await client.get("/api/v1/school/students/roster-template")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "full_name" in response.text


@pytest.mark.asyncio
async def test_bulk_upload_requires_idempotency_key(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["school_coordinator"].email)
    csv_data = _csv_bytes(["Jane Doe,2015-04-12,Grade 5,"])
    response = await client.post("/api/v1/school/students/bulk-upload", files={"file": ("roster.csv", csv_data, "text/csv")})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bulk_upload_creates_students_and_reports_row_level_results(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["school_coordinator"].email)
    csv_data = _csv_bytes(["Jane Doe,2015-04-12,Grade 5,", "John Smith,,Grade 6,"])
    response = await client.post(
        "/api/v1/school/students/bulk-upload",
        files={"file": ("roster.csv", csv_data, "text/csv")},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["total_rows"] == 2
    assert data["accepted_count"] == 2
    assert data["rejected_count"] == 0
    assert all(r["status"] == "accepted" for r in data["rows"])

    students = (await db_session.scalars(select(SchoolStudent).where(SchoolStudent.school_id == ctx["school"].id))).all()
    assert {s.full_name for s in students} == {"Jane Doe", "John Smith"}


@pytest.mark.asyncio
async def test_a_bad_row_is_rejected_without_blocking_the_rest_of_the_batch(client, db_session):
    """SCH-002-AC04."""
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["school_coordinator"].email)
    csv_data = _csv_bytes([
        "Good Student One,2015-04-12,Grade 5,",
        ",2015-04-12,Grade 5,",  # missing full_name
        "Bad Date Student,not-a-date,Grade 5,",
        "Good Student Two,,Grade 6,",
    ])
    response = await client.post(
        "/api/v1/school/students/bulk-upload",
        files={"file": ("roster.csv", csv_data, "text/csv")},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["total_rows"] == 4
    assert data["accepted_count"] == 2
    assert data["rejected_count"] == 2
    statuses = {r["row_number"]: r["status"] for r in data["rows"]}
    assert statuses[1] == "accepted"
    assert statuses[2] == "rejected"
    assert statuses[3] == "rejected"
    assert statuses[4] == "accepted"
    row2 = next(r for r in data["rows"] if r["row_number"] == 2)
    assert "full_name" in row2["error_message"]
    row3 = next(r for r in data["rows"] if r["row_number"] == 3)
    assert "date_of_birth" in row3["error_message"]


@pytest.mark.asyncio
async def test_a_row_can_assign_an_existing_teacher_at_the_same_school(client, db_session):
    ctx = await _create_school_with_coordinator(db_session, extra_roles=("school_teacher",))
    await _login(client, ctx["school_coordinator"].email)
    csv_data = _csv_bytes([f"Assigned Student,,Grade 5,{ctx['school_teacher'].email}"])
    response = await client.post(
        "/api/v1/school/students/bulk-upload",
        files={"file": ("roster.csv", csv_data, "text/csv")},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201, response.text
    assert response.json()["accepted_count"] == 1
    # Scoped to this test's own school -- the shared dev DB has no test isolation
    # (RAID.md I-06), so an unscoped name-only lookup could match a stale row from an
    # earlier run of this same test.
    student = (await db_session.scalars(select(SchoolStudent).where(SchoolStudent.full_name == "Assigned Student", SchoolStudent.school_id == ctx["school"].id))).first()
    assert student.assigned_teacher_user_id == ctx["school_teacher"].id


@pytest.mark.asyncio
async def test_a_teacher_email_from_another_school_is_rejected(client, db_session):
    ctx_a = await _create_school_with_coordinator(db_session)
    ctx_b = await _create_school_with_coordinator(db_session, extra_roles=("school_teacher",))
    await _login(client, ctx_a["school_coordinator"].email)
    csv_data = _csv_bytes([f"Cross School Student,,Grade 5,{ctx_b['school_teacher'].email}"])
    response = await client.post(
        "/api/v1/school/students/bulk-upload",
        files={"file": ("roster.csv", csv_data, "text/csv")},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["rejected_count"] == 1
    assert "not an existing Teacher at your own school" in data["rows"][0]["error_message"]


@pytest.mark.asyncio
async def test_repeating_the_same_idempotency_key_replays_the_original_result(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["school_coordinator"].email)
    key = uuid.uuid4().hex
    csv_data = _csv_bytes(["Replay Student,,Grade 5,"])
    first = await client.post("/api/v1/school/students/bulk-upload", files={"file": ("roster.csv", csv_data, "text/csv")}, headers={"Idempotency-Key": key})
    assert first.status_code == 201
    batch_id = first.json()["id"]

    second = await client.post("/api/v1/school/students/bulk-upload", files={"file": ("roster.csv", csv_data, "text/csv")}, headers={"Idempotency-Key": key})
    assert second.status_code == 201
    assert second.json()["id"] == batch_id

    student_count = len((await db_session.scalars(select(SchoolStudent).where(SchoolStudent.school_id == ctx["school"].id))).all())
    assert student_count == 1  # never double-created by the replay


@pytest.mark.asyncio
async def test_coordinator_can_fetch_a_batch_report_by_id(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["school_coordinator"].email)
    csv_data = _csv_bytes(["Report Student,,Grade 5,"])
    created = await client.post("/api/v1/school/students/bulk-upload", files={"file": ("roster.csv", csv_data, "text/csv")}, headers={"Idempotency-Key": uuid.uuid4().hex})
    batch_id = created.json()["id"]

    response = await client.get(f"/api/v1/school/roster-uploads/{batch_id}")
    assert response.status_code == 200
    assert response.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_a_coordinator_cannot_fetch_another_schools_batch_report(client, db_session):
    ctx_a = await _create_school_with_coordinator(db_session)
    ctx_b = await _create_school_with_coordinator(db_session)
    await _login(client, ctx_b["school_coordinator"].email)
    csv_data = _csv_bytes(["B Student,,Grade 5,"])
    created = await client.post("/api/v1/school/students/bulk-upload", files={"file": ("roster.csv", csv_data, "text/csv")}, headers={"Idempotency-Key": uuid.uuid4().hex})
    batch_id = created.json()["id"]

    await _login(client, ctx_a["school_coordinator"].email)
    response = await client.get(f"/api/v1/school/roster-uploads/{batch_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_non_coordinator_cannot_bulk_upload(client, db_session):
    ctx = await _create_school_with_coordinator(db_session, extra_roles=("school_principal",))
    await _login(client, ctx["school_principal"].email)
    csv_data = _csv_bytes(["Should Not Save,,Grade 5,"])
    response = await client.post("/api/v1/school/students/bulk-upload", files={"file": ("roster.csv", csv_data, "text/csv")}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 403
