"""ENH-029 -- bulk school onboarding (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md, AC01-AC12)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, PasswordResetToken, School, SchoolBulkUploadBatch, SchoolBulkUploadRow, User, UserRoleAssignment
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


# --- Row processing, report, replay (AC01-AC04) --------------------------------------------------------------------------------

ROW_KEYS = {"row_number", "status", "error_message", "created_record_id", "school_code", "school_name", "coordinator_id", "coordinator_email", "email_status"}


async def _ok(client, rows, **kw) -> dict:
    response = await upload(client, csv_bytes(rows, **kw))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_valid_rows_create_school_coordinator_pairs_like_the_single_create(client, db_session):
    admin = await mk_admin(db_session)
    await login(client, admin)
    rows = [school_row(tier="gold"), school_row(), school_row()]
    report = await _ok(client, rows)
    assert (report["target_type"], report["status"], report["total_rows"], report["accepted_count"], report["rejected_count"]) == ("school_onboarding", "completed", 3, 3, 0)
    codes = set()
    for line, (sent, row) in enumerate(zip(rows, report["rows"], strict=True), start=2):
        assert (row["row_number"], row["status"], row["error_message"]) == (line, "accepted", None)
        school = await db_session.get(School, uuid.UUID(row["created_record_id"]))
        coordinator = await db_session.get(User, uuid.UUID(row["coordinator_id"]))
        assert school.name == sent["name"] == row["school_name"]
        assert school.school_code == row["school_code"]
        assert school.created_by_user_id == admin.id
        assert (coordinator.email, coordinator.role, coordinator.active, coordinator.profile) == (sent["coordinator_email"], "school_coordinator", True, {"school_id": str(school.id)})
        assert row["coordinator_email"] == sent["coordinator_email"]
        assert await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == coordinator.id, UserRoleAssignment.assigned_by_user_id == admin.id))
        assert await db_session.scalar(select(func.count(PasswordResetToken.id)).where(PasswordResetToken.user_id == coordinator.id, PasswordResetToken.purpose == "welcome")) == 1
        codes.add(school.school_code)
    assert len(codes) == 3
    assert (await db_session.get(School, uuid.UUID(report["rows"][0]["created_record_id"]))).tier == "gold"
    actions = list((await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == admin.id))).all())
    assert actions.count("school.create") == 3
    assert actions.count("school.coordinator_seed") == 3
    assert actions.count("school.bulk_upload") == 1
    batch_rows = (await db_session.scalars(select(SchoolBulkUploadRow).where(SchoolBulkUploadRow.batch_id == uuid.UUID(report["id"])))).all()
    assert {(r.created_record_id, r.created_user_id) for r in batch_rows} == {(uuid.UUID(r["created_record_id"]), uuid.UUID(r["coordinator_id"])) for r in report["rows"]}


@pytest.mark.asyncio
async def test_mixed_file_isolates_each_bad_row(client, db_session):
    await login(client, await mk_admin(db_session))
    taken = school_row()
    await _ok(client, [taken])
    same_email = school_row(coordinator_email=f"enh029-dup-{uuid.uuid4().hex[:6]}@example.local")
    rows = [
        school_row(),  # 2 accepted
        school_row(tier="diamond"),  # 3 bad tier (helper)
        school_row(coordinator_email="not-an-email"),  # 4 bad email
        {**school_row(), "name": ""},  # 5 missing name (SchoolCreate)
        school_row(coordinator_email=taken["coordinator_email"].upper()),  # 6 existing email, case-insensitive
        same_email,  # 7 accepted
        school_row(coordinator_email=same_email["coordinator_email"]),  # 8 repeat of row 7
        school_row(name=taken["name"], city=taken["city"]),  # 9 existing school
        school_row(name=f"Twin {uuid.uuid4().hex[:6]}", city="Goa"),  # 10 accepted
    ]
    rows.append(school_row(name=rows[-1]["name"].upper() + "  ", city=" goa"))  # 11 repeat of row 10 (normalized)
    report = await _ok(client, rows)
    by_line = {r["row_number"]: r for r in report["rows"]}
    assert [line for line, r in by_line.items() if r["status"] == "accepted"] == [2, 7, 10]
    assert by_line[3]["error_message"] == "tier must be one of bronze, silver, gold, platinum"
    assert by_line[4]["error_message"] == "A valid email address is required"
    assert "name" in by_line[5]["error_message"]
    assert by_line[6]["error_message"] == "Email already exists"
    assert by_line[8]["error_message"] == "same coordinator_email as row 7"
    assert by_line[9]["error_message"] == "a school with this name and city already exists"
    assert by_line[11]["error_message"] == "same school name and city as row 10"
    assert report["accepted_count"] + report["rejected_count"] == report["total_rows"] == 10
    for r in report["rows"]:
        if r["status"] == "rejected":
            assert set(r) == ROW_KEYS  # one fixed shape (the dev-only token is the single documented extra, accepted rows only)
            assert (r["created_record_id"], r["coordinator_id"], r["school_code"], r["school_name"], r["coordinator_email"], r["email_status"]) == (None,) * 6
    assert await db_session.scalar(select(func.count(School.id)).where(School.name == rows[1]["name"])) == 0  # the helper's 422 left nothing behind


@pytest.mark.asyncio
async def test_all_rejected_file_is_still_a_report(client, db_session):
    await login(client, await mk_admin(db_session))
    report = await _ok(client, [school_row(tier="diamond"), school_row(coordinator_email="nope")])
    assert (report["accepted_count"], report["rejected_count"]) == (0, 2)


@pytest.mark.asyncio
async def test_duplicate_name_normalization(client, db_session):
    await login(client, await mk_admin(db_session))
    base = school_row(city="")
    await _ok(client, [base])
    report = await _ok(client, [school_row(name="  " + base["name"].lower().replace(" ", "   ") + " ", city="")])
    assert report["rows"][0]["error_message"] == "a school with this name and city already exists"


@pytest.mark.asyncio
async def test_email_comparison_is_case_insensitive(client, db_session):
    await login(client, await mk_admin(db_session))
    first = school_row()
    await _ok(client, [first])
    report = await _ok(client, [school_row(coordinator_email=f"  {first['coordinator_email'].upper()} ")])
    assert report["rows"][0]["error_message"] == "Email already exists"


@pytest.mark.asyncio
async def test_excel_style_csv_is_accepted(client, db_session):
    await login(client, await mk_admin(db_session))
    data = b"\xef\xbb\xbf" + csv_bytes([school_row(), school_row()]) + b",,,,\r\n,,,,\r\n"  # BOM, CRLF (csv default), blank tail rows
    response = await upload(client, data)
    assert response.status_code == 201, response.text
    assert response.json()["total_rows"] == 2


@pytest.mark.asyncio
async def test_optional_profile_fields_are_stored(client, db_session):
    await login(client, await mk_admin(db_session))
    row = school_row(board="CBSE", partnership_date="2026-10-01", tier_valid_until="2027-03-31", website="https://x.example", grades_available="1-12")
    report = await _ok(client, [row], header=list(SchoolCreate.model_fields))
    school = await db_session.get(School, uuid.UUID(report["rows"][0]["created_record_id"]))
    assert (school.board, str(school.partnership_date), str(school.tier_valid_until), school.grades_available) == ("CBSE", "2026-10-01", "2027-03-31", "1-12")


@pytest.mark.asyncio
async def test_replay_returns_the_same_report_and_creates_nothing(client, db_session):
    await login(client, await mk_admin(db_session))
    data, key = csv_bytes([school_row(), school_row(tier="diamond")]), uuid.uuid4().hex
    first = (await upload(client, data, key)).json()
    before = await db_session.scalar(select(func.count(School.id)))
    replay = await upload(client, data, key)
    assert replay.status_code == 201
    again = replay.json()
    assert await db_session.scalar(select(func.count(School.id))) == before
    assert {k: v for k, v in first.items() if k != "rows"} == {k: v for k, v in again.items() if k != "rows"}
    for a, b in zip(first["rows"], again["rows"], strict=True):
        assert {k: v for k, v in a.items() if k not in ("email_status", "development_welcome_token")} == {k: v for k, v in b.items() if k != "email_status"}
        assert b["email_status"] is None
        assert "development_welcome_token" not in b
    other = await upload(client, csv_bytes([school_row()]), key)
    assert (other.status_code, other.json()["detail"]) == (422, "Idempotency-Key was already used for a different file")
