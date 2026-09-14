"""ADM-004 -- Directory management: Students, Trainers, Employers.

`GET/PATCH /admin/users` already existed (`ADM-001`) but only ever supported a flat list
and an activate/deactivate toggle -- there was no way to view or edit a directory record's
actual detail fields (name/phone/education/skills) at all, despite this feature's own main
workflow being exactly that ("Admin views/edits directory detail records"). `PATCH
/admin/users/{id}` already restricted writable fields to an explicit allowlist
(`full_name`, `phone`, `active`, `email_verified`, `profile`) -- role/division/email/
password_hash were never PATCH-able through it, which is this feature's own field-level
grant (`ADM-004-AC02`), confirmed directly here rather than assumed. Extended `GET
/admin/users` to also return `phone`/`profile` so a directory edit form can prefill real
values, and gave the "students"/"trainers" nav entries their own role-scoped view instead
of the same unfiltered "everyone" list `ADM-001`'s panel showed on every one of those pages.
No `employer` role exists anywhere in this codebase yet (`EMP-001` unbuilt) -- the
Employers directory honestly reports empty rather than 404ing or fabricating records.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import User


async def _create_admin(db_session, *, email_prefix: str = "adm004-admin") -> User:
    admin = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Directory Admin",
        role="it_admin",
        division="it",
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _create_student(db_session) -> User:
    student = User(
        email=f"adm004-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Directory Student",
        role="it_student",
        division="it",
        phone="+91-9000000001",
        profile={"education": "B.Sc", "skills": ["Python"]},
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_directory_listing_includes_detail_fields(db_session, client):
    admin = await _create_admin(db_session)
    student = await _create_student(db_session)
    await _login(client, admin.email)

    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 200
    row = next(r for r in response.json() if r["id"] == str(student.id))
    assert row["phone"] == "+91-9000000001"
    assert row["profile"]["education"] == "B.Sc"


@pytest.mark.asyncio
async def test_admin_edits_directory_detail_fields(db_session, client):
    admin = await _create_admin(db_session)
    student = await _create_student(db_session)
    await _login(client, admin.email)

    response = await client.patch(
        f"/api/v1/admin/users/{student.id}",
        json={"full_name": "Updated Student Name", "phone": "+91-9000000002", "profile": {"education": "M.Sc", "skills": ["Python", "FastAPI"]}},
    )
    assert response.status_code == 200

    await db_session.refresh(student)
    assert student.full_name == "Updated Student Name"
    assert student.phone == "+91-9000000002"
    assert student.profile["education"] == "M.Sc"


@pytest.mark.asyncio
async def test_directory_edit_never_writes_a_field_outside_the_allowlist(db_session, client):
    """ADM-004-AC02: role/division/email/password_hash are not directory-editable
    fields at all -- confirmed directly, not assumed, by attempting to set them and
    verifying the stored record is unchanged."""
    admin = await _create_admin(db_session)
    student = await _create_student(db_session)
    original_role, original_division, original_email, original_hash = student.role, student.division, student.email, student.password_hash
    await _login(client, admin.email)

    response = await client.patch(
        f"/api/v1/admin/users/{student.id}",
        json={"role": "super_admin", "division": "overseas", "email": "hijacked@example.local", "password_hash": "not-a-real-hash"},
    )
    assert response.status_code == 200

    await db_session.refresh(student)
    assert student.role == original_role
    assert student.division == original_division
    assert student.email == original_email
    assert student.password_hash == original_hash


@pytest.mark.asyncio
async def test_employers_directory_is_an_honest_empty_state_not_a_404(db_session, client):
    admin = await _create_admin(db_session)
    await _login(client, admin.email)

    response = await client.get("/api/v1/portal/it/admin/employers")
    assert response.status_code == 200
    assert response.json()["rows"] == []


@pytest.mark.asyncio
async def test_non_admin_role_is_rejected(db_session, client):
    student = await _create_student(db_session)
    await _login(client, student.email)

    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_directory_requires_authentication(client):
    assert (await client.get("/api/v1/admin/users")).status_code == 401
    assert (await client.patch(f"/api/v1/admin/users/{uuid.uuid4()}", json={"full_name": "Nope"})).status_code == 401
