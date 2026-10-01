"""ENH-029 -- bulk school onboarding (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md, AC01-AC12)."""

import pytest
from sqlalchemy import func, select

from app.models import School, SchoolBulkUploadBatch
from app.schemas import SchoolCreate
from tests.enh029_helpers import HEADER, TEMPLATE_URL, UPLOAD_URL, csv_bytes, login, mk_admin, school_row, upload

# --- Authorization and template (AC09) -------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_admin", "super_admin"])
async def test_template_is_header_only_schoolcreate_columns(client, db_session, role):
    await login(client, await mk_admin(db_session, role))
    response = await client.get(TEMPLATE_URL)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["cache-control"] == "private, no-store"
    assert "school-onboarding-bulk-template.csv" in response.headers["content-disposition"]
    assert response.text.strip().split(",") == list(SchoolCreate.model_fields)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "student"])
async def test_other_roles_get_403_on_both_routes(client, db_session, role):
    await login(client, await mk_admin(db_session, role))
    assert (await client.get(TEMPLATE_URL)).status_code == 403
    response = await upload(client, csv_bytes([school_row()]))
    assert response.status_code == 403
    assert response.json()["detail"] == "Overseas Admin role required"


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client):
    assert (await client.get(TEMPLATE_URL)).status_code == 401
    assert (await upload(client, csv_bytes([school_row()]))).status_code == 401


# --- File-level rejections (AC05) -----------------------------------------------------------------------------------------------


async def _batches_of(db, user) -> list[SchoolBulkUploadBatch]:
    return list((await db.scalars(select(SchoolBulkUploadBatch).where(SchoolBulkUploadBatch.uploaded_by_user_id == user.id))).all())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "status", "detail"),
    [
        (b"\xff\xfe bad", 422, "The file must be a UTF-8 CSV"),
        (b"name\x00,city\n", 422, "The file must be a UTF-8 CSV"),
        (csv_bytes([school_row()], header=["name", "city", "coordinator_email"]), 422, "Missing required column: coordinator_full_name"),
        (csv_bytes([school_row(role="super_admin")], header=[*HEADER, "role"]), 422, "Unknown column: role"),
        (csv_bytes([school_row(password="x")], header=[*HEADER, "password"]), 422, "Unknown column: password"),
        (csv_bytes([school_row()], header=[*HEADER, "name"]), 422, "Duplicate column: name"),
        (csv_bytes([]), 422, "The file has no filled-in rows"),
        (csv_bytes([school_row() for _ in range(101)]), 422, "The file has more than 100 filled-in rows"),
        (b"name,coordinator_full_name,coordinator_email\n" + b"x" * (1024 * 1024), 413, "The file is larger than 1 MB"),
    ],
    ids=["not-utf8", "nul", "missing-required", "role-column", "password-column", "duplicate-column", "empty", "too-many-rows", "too-large"],
)
async def test_file_level_rejections_create_nothing(client, db_session, data, status, detail):
    admin = await mk_admin(db_session)
    await login(client, admin)
    before = await db_session.scalar(select(func.count(School.id)))
    response = await upload(client, data)
    assert (response.status_code, response.json()["detail"]) == (status, detail)
    assert await db_session.scalar(select(func.count(School.id))) == before
    assert await _batches_of(db_session, admin) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "detail"), [(None, "Idempotency-Key header is required"), ("bad key!", "Idempotency-Key must be 1-120 letters, digits or . _ : -")])
async def test_key_is_required_and_validated(client, db_session, key, detail):
    await login(client, await mk_admin(db_session))
    headers = {} if key is None else {"Idempotency-Key": key}
    response = await client.post(UPLOAD_URL, files={"file": ("s.csv", csv_bytes([school_row()]), "text/csv")}, headers=headers)
    assert (response.status_code, response.json()["detail"]) == (422, detail)


@pytest.mark.asyncio
async def test_unknown_column_name_is_truncated(client, db_session):
    await login(client, await mk_admin(db_session))
    response = await upload(client, csv_bytes([school_row()], header=[*HEADER, "z" * 300]))
    assert response.json()["detail"] == "Unknown column: " + "z" * 40


@pytest.mark.asyncio
async def test_trailing_empty_header_is_ignored(client, db_session):
    await login(client, await mk_admin(db_session))
    response = await upload(client, csv_bytes([school_row()], header=[*HEADER, ""]))
    assert response.status_code == 201, response.text
