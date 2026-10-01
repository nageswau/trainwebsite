# ENH-029 Bulk School Onboarding Implementation Plan

> **Renumbered on merging `main` (2026-10-01):** this plan was executed as written with `DEC-SCOPE-044` and migration
> `0052_school_onboarding_bulk` (after `0051`). `main` had already used 044–046 and 0052–0053, so the decision is now
> `DEC-SCOPE-047` and the migration `0054_school_onboarding_bulk` (after `0053_school_funding_records`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Overseas Admin / Super Admin onboard up to 100 schools (each with its seed Coordinator) from one CSV upload, with
per-row isolation, idempotent replay and a per-row batch report.

**Architecture:** A new router module `app/api/school_onboarding_bulk.py` reuses `create_school`'s body (extracted to
`admin._provision_school`), ENH-028's parser/claim helpers (parameterized by `target_type`) and its batch/row tables
(`target_type = 'school_onboarding'`, plus a nullable `created_user_id`). One request = one transaction with a savepoint per row,
an advisory lock serializing onboarding uploads, and welcome links delivered after commit (≤ 5 concurrent). A new React panel on
the Admin Schools page drives it.

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy 2, Alembic, PostgreSQL; Next.js 15 / React 19, Vitest + Testing Library,
Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md` (D1–D10, AC01–AC12).

## Global Constraints

- Limits: file ≤ 1 MB (`MAX_FILE_BYTES`), 1–100 filled-in rows, welcome sends ≤ 5 concurrent, lock timeout `5s` (ENH-028's `LOCK_TIMEOUT`).
- Roles: `{"overseas_admin", "super_admin"}` only; 403 detail `Overseas Admin role required`.
- `target_type`: `school_onboarding`. Migration revision `0052_school_onboarding_bulk`, `down_revision = "0051_school_bulk_uploads"`.
- Template/CSV columns = `tuple(SchoolCreate.model_fields)` in that order; required `name`, `coordinator_full_name`, `coordinator_email`.
- No new dependencies. No change to `POST /overseas-admin/schools` or any ENH-028 response. No existing data read or written by the migration.
- Logs: ids, counts, reasons, `target_type` only — never emails, names, file content or tokens.
- `development_welcome_token` only when `settings.environment in DEV_TOKEN_ENVIRONMENTS`, never on replay.
- Error body shape `{"detail": "<message>"}` (FastAPI default). Exact messages per spec §5.2 / §6.

## Commands

PowerShell or bash from the worktree root. `T` = `docker compose -p enh029 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm`
(Postgres + Redis for project `enh029` already up; the api-test entrypoint runs `alembic upgrade head` first.)

- backend test: `$T -v "$PWD/apps/api:/app" api-test python -m pytest -q -p no:cacheprovider tests/<file>[::name]`
- web unit: `$T --no-deps -v "$PWD/apps/web:/app" -v /app/node_modules web-test npx vitest run <file>`
- lint: `$T --no-deps -v "$PWD/apps/api:/app" api-test sh -c "ruff format --check . && ruff check ."`

## Review Focus

1. A CSV saved by Excel (UTF-8 BOM, CRLF line endings, trailing blank rows) must parse exactly like a plain file → Task 5 test `test_excel_style_csv_is_accepted`.
2. Upper-case / padded coordinator emails (`" Meera@X.IN "`) must collide with an existing `meera@x.in` → Task 5 test `test_email_comparison_is_case_insensitive`.
3. A school name differing only by case/whitespace from an existing one, with a blank city vs no city, must be a duplicate → Task 5 test `test_duplicate_name_normalization`.
4. A header with a trailing empty column (`name,...,`) — common from spreadsheets — must not be "Unknown column" → Task 4 test `test_trailing_empty_header_is_ignored`.
5. An all-rejected file must still return 201 with a report, and the panel must show the error-tone summary, not a crash → Task 5 `test_all_rejected_file_is_still_a_report`, Task 9 `"all rejected"` case.

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/alembic/versions/0052_school_onboarding_bulk.py` (create) | CHECK swap + `created_user_id` column, guarded downgrade |
| `apps/api/app/models.py` (modify ~1401, ~1424) | `BULK_TARGET_TYPES` + `SchoolBulkUploadRow.created_user_id` |
| `apps/api/app/api/admin.py` (modify ~1171-1219) | extract `_provision_school`; `create_school` calls it |
| `apps/api/app/api/school_bulk.py` (modify) | `_read_upload`, `_read_csv`, `_file_error(target_type…)`, `_claim(target_type…)` |
| `apps/api/app/api/school_onboarding_bulk.py` (create) | template + upload endpoints, row rules, report, delivery |
| `apps/api/app/main.py` (modify) | register router |
| `apps/api/tests/enh029_helpers.py` (create) | admin builder, CSV builder, upload helper |
| `apps/api/tests/test_enh_029_migration.py`, `test_enh_029_provision_refactor.py`, `test_enh_029_bulk_onboarding.py` (create) | tests |
| `apps/api/tests/test_enh_028_migration.py` (modify) | head is now 0052; rows table has `created_user_id` (schema fact changed by this feature) |
| `apps/web/lib/bulkEntry.ts` (modify) | `SCHOOL_ONBOARDING: BulkTarget` |
| `apps/web/components/AdminSchoolBulkOnboardPanel.tsx` (create) | panel |
| `apps/web/components/WorkflowPanel.tsx` (modify line ~475) | mount panel |
| `apps/web/tests/components/AdminSchoolBulkOnboardPanel.test.tsx`, `apps/web/tests/e2e/enh-029-bulk-school-onboarding.spec.ts` (create) | tests |
| docs (spec §14) | contract, data model, RBAC, security, UX, RTM, decision, backlog |

---

### Task 1: Migration 0052 and model

**Files:** Create `apps/api/alembic/versions/0052_school_onboarding_bulk.py`, `apps/api/tests/test_enh_029_migration.py`;
Modify `apps/api/app/models.py`, `apps/api/tests/test_enh_028_migration.py`.

**Interfaces:** Produces `BULK_TARGET_TYPES` containing `"school_onboarding"`; `SchoolBulkUploadRow.created_user_id: Mapped[UUID | None]`.

- [ ] **Step 1: Write the failing test** `tests/test_enh_029_migration.py`:

```python
"""ENH-029 -- migration 0052 (spec §4, AC10): single head, CHECK swap + nullable created_user_id, data preserved, guarded downgrade."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models import SchoolBulkUploadBatch, SchoolBulkUploadRow
from tests.test_enh_028_migration import _parents

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_029_migration_0052", VERSIONS / "0052_school_onboarding_bulk.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def test_migration_follows_0051_and_is_the_single_head():
    assert _migration.revision == "0052_school_onboarding_bulk"
    assert _migration.down_revision == "0051_school_bulk_uploads"
    parents = _parents()
    assert set(parents) - set(parents.values()) == {"0052_school_onboarding_bulk"}


def test_migration_touches_only_the_constraint_and_the_new_column():
    source = (VERSIONS / "0052_school_onboarding_bulk.py").read_text(encoding="utf-8")
    for forbidden in ("op.create_table", "op.drop_table", "op.alter_column", "UPDATE ", "DELETE ", "INSERT "):
        assert forbidden not in source
    assert source.count("op.add_column(") == 1 and source.count("op.drop_column(") == 1


@pytest.mark.asyncio
async def test_rows_table_has_a_nullable_created_user_id_fk(db_session):
    def _describe(sync_conn):
        insp = inspect(sync_conn)
        cols = {c["name"]: c["nullable"] for c in insp.get_columns("school_bulk_upload_rows")}
        fks = {(tuple(f["constrained_columns"]), f["referred_table"]) for f in insp.get_foreign_keys("school_bulk_upload_rows")}
        return cols, fks

    cols, fks = await (await db_session.connection()).run_sync(_describe)
    assert cols["created_user_id"] is True
    assert (("created_user_id",), "users") in fks


@pytest.mark.asyncio
async def test_constraint_accepts_school_onboarding_and_still_rejects_unknown(db_session):
    from tests.enh029_helpers import mk_admin

    admin = await mk_admin(db_session)
    db_session.add(SchoolBulkUploadBatch(target_type="school_onboarding", uploaded_by_user_id=admin.id, idempotency_key=uuid.uuid4().hex, file_sha256="0" * 64))
    await db_session.commit()
    db_session.add(SchoolBulkUploadBatch(target_type="nonsense", uploaded_by_user_id=admin.id, idempotency_key=uuid.uuid4().hex, file_sha256="0" * 64))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_downgrade_refuses_when_onboarding_batches_exist():
    source = (VERSIONS / "0052_school_onboarding_bulk.py").read_text(encoding="utf-8")
    assert "school_onboarding" in source.split("def downgrade", 1)[1]
    assert "raise RuntimeError" in source.split("def downgrade", 1)[1]
```

- [ ] **Step 2: Run, expect FAIL** (`FileNotFoundError` for 0052). Run: `$T ... tests/test_enh_029_migration.py`.

- [ ] **Step 3: Implement.** `0052_school_onboarding_bulk.py`:

```python
"""ENH-029 -- school_onboarding bulk target + school_bulk_upload_rows.created_user_id.

Revision ID: 0052_school_onboarding_bulk
Revises: 0051_school_bulk_uploads

docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md §4 (DEC-SCOPE-044). Widens the target_type CHECK and adds
one nullable column (no default, no backfill); no existing row is read or written. downgrade() refuses while onboarding batches
exist rather than silently deleting that history.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0052_school_onboarding_bulk"
down_revision = "0051_school_bulk_uploads"
branch_labels = None
depends_on = None

CHECK = "ck_school_bulk_upload_target_type"
BEFORE = "target_type IN ('academic_result', 'psychometric_record', 'test_prep_record', 'language_record')"
AFTER = "target_type IN ('academic_result', 'psychometric_record', 'test_prep_record', 'language_record', 'school_onboarding')"


def upgrade() -> None:
    op.drop_constraint(CHECK, "school_bulk_upload_batches", type_="check")
    op.create_check_constraint(CHECK, "school_bulk_upload_batches", AFTER)
    op.add_column("school_bulk_upload_rows", sa.Column("created_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", name="fk_school_bulk_upload_rows_created_user_id"), nullable=True))


def downgrade() -> None:
    if not op.get_context().as_sql:
        count = op.get_bind().execute(sa.text("SELECT count(*) FROM school_bulk_upload_batches WHERE target_type = 'school_onboarding'")).scalar()
        if count:
            raise RuntimeError(f"{count} school_onboarding bulk batches exist; refusing to downgrade 0052 and lose them")
    op.drop_column("school_bulk_upload_rows", "created_user_id")
    op.drop_constraint(CHECK, "school_bulk_upload_batches", type_="check")
    op.create_check_constraint(CHECK, "school_bulk_upload_batches", BEFORE)
```

`models.py`: `BULK_TARGET_TYPES = ("academic_result", "psychometric_record", "test_prep_record", "language_record", "school_onboarding")`;
in `SchoolBulkUploadRow` add after `created_record_id`:
`created_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)  # ENH-029: the Coordinator an onboarding row created`.
Update the class docstring line ("`created_user_id` -- ENH-029 onboarding rows only").

`test_enh_028_migration.py`: in `test_migration_follows_0050_and_is_the_single_head` replace the head assertion with
`assert "0051_school_bulk_uploads" in parents.values()  # 0052 (ENH-029) now follows it`; in `test_tables_match_the_model` add
`"created_user_id": True,` to the rows columns dict (comment `# ENH-029 (0052)`).

`tests/enh029_helpers.py` (also used by Tasks 2–7):

```python
"""Shared builders for ENH-029 bulk school onboarding tests (docs/superpowers/plans/2026-10-01-enh-029-bulk-school-onboarding.md)."""

import csv
import io
import uuid

from app.core.security import hash_password
from app.models import User

PASSWORD = "Sup3r-Secret-Pass!"
UPLOAD_URL = "/api/v1/overseas-admin/schools/bulk-upload"
TEMPLATE_URL = "/api/v1/overseas-admin/schools/bulk-template"
HEADER = ["name", "city", "coordinator_full_name", "coordinator_email", "tier"]


async def mk_admin(db, role: str = "overseas_admin") -> User:
    user = User(email=f"enh029-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=f"ENH-029 {role}", role=role, division="overseas", active=True)
    db.add(user)
    await db.commit()
    return user


async def login(client, user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": user.division})
    assert response.status_code == 200, response.text


def school_row(tag: str | None = None, **over) -> dict:
    tag = tag or uuid.uuid4().hex[:8]
    return {"name": f"ENH029 School {tag}", "city": "Pune", "coordinator_full_name": f"Coord {tag}", "coordinator_email": f"enh029-coord-{tag}@example.local", **over}


def csv_bytes(rows: list[dict], header: list[str] | None = None) -> bytes:
    header = header or HEADER
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(name, "") for name in header])
    return buffer.getvalue().encode("utf-8")


async def upload(client, data: bytes, key: str | None = None):
    return await client.post(UPLOAD_URL, files={"file": ("schools.csv", data, "text/csv")}, headers={"Idempotency-Key": key or uuid.uuid4().hex})
```

- [ ] **Step 4: Run, expect PASS:** `tests/test_enh_029_migration.py tests/test_enh_028_migration.py`.
- [ ] **Step 5: Commit** `feat(enh-029): migration 0052 -- school_onboarding bulk target and created_user_id`.

### Task 2: Extract `_provision_school` (behaviour-preserving)

**Files:** Modify `apps/api/app/api/admin.py:1166-1219`; Create `apps/api/tests/test_enh_029_provision_refactor.py`.

**Interfaces:** Produces `async def _provision_school(db: AsyncSession, payload: SchoolCreate, actor: User, *, flush_coordinator: Callable[[AsyncSession], Awaitable[None]] = _flush_unique_email) -> tuple[School, User, IssuedWelcome]` — no commit, no delivery; raises `HTTPException` (409 email exists, 422 tier/email/length) before or after adds.

- [ ] **Step 1: Failing test** (`ImportError` on `_provision_school`):

```python
"""ENH-029 -- create_school's body moved into admin._provision_school (spec §7): the single create is byte-for-byte unchanged."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, School, User, UserRoleAssignment
from tests.enh029_helpers import login, mk_admin


def test_helper_exists_and_defaults_to_flush_unique_email():
    import inspect

    from app.api.admin import _provision_school
    from app.services.provisioning import flush_unique_email

    assert inspect.signature(_provision_school).parameters["flush_coordinator"].default is flush_unique_email


@pytest.mark.asyncio
async def test_single_create_response_and_audits_unchanged(client, db_session):
    admin = await mk_admin(db_session)
    await login(client, admin)
    tag = uuid.uuid4().hex[:8]
    response = await client.post("/api/v1/overseas-admin/schools", json={"name": f"Refactor {tag}", "city": "Pune", "tier": "gold", "coordinator_full_name": "C", "coordinator_email": f"r-{tag}@example.local"})
    assert response.status_code == 201
    body = response.json()
    assert {"id", "school_code", "coordinator_id", "coordinator_email", "email_status", "expires_at", "development_welcome_token"} <= set(body)
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == admin.id))).all())
    assert {"school.create", "school.coordinator_seed", "user.welcome_link_issue", "user.welcome_link_delivery"} <= actions
    coordinator = await db_session.get(User, uuid.UUID(body["coordinator_id"]))
    assert coordinator.role == "school_coordinator" and coordinator.profile == {"school_id": body["id"]}
    assert await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == coordinator.id, UserRoleAssignment.assigned_by_user_id == admin.id))


@pytest.mark.asyncio
async def test_single_create_duplicate_email_is_still_409_and_creates_no_school(client, db_session):
    admin = await mk_admin(db_session)
    await login(client, admin)
    tag = uuid.uuid4().hex[:8]
    payload = {"name": f"Dup {tag}", "coordinator_full_name": "C", "coordinator_email": f"dup-{tag}@example.local"}
    assert (await client.post("/api/v1/overseas-admin/schools", json=payload)).status_code == 201
    second = await client.post("/api/v1/overseas-admin/schools", json={**payload, "name": f"Dup2 {tag}"})
    assert second.status_code == 409 and second.json()["detail"] == "Email already exists"
    assert await db_session.scalar(select(School).where(School.name == f"Dup2 {tag}")) is None
```

- [ ] **Step 2: Run, expect FAIL** on the import test only (the other two pass today — they pin behaviour across the refactor).
- [ ] **Step 3: Implement** in `admin.py`: add imports `from collections.abc import Awaitable, Callable` and `IssuedWelcome` to the
  `app.services.provisioning` import. Move lines from `email = _valid_email(...)` through the two `AuditLog` adds into:

```python
async def _provision_school(
    db: AsyncSession, payload: SchoolCreate, actor: User, *, flush_coordinator: Callable[[AsyncSession], Awaitable[None]] = _flush_unique_email
) -> tuple[School, User, IssuedWelcome]:
    """SCH-003 create_school's body, shared with ENH-029's bulk onboarding: School + seed Coordinator + role assignment + welcome
    token + audits. No commit, no delivery. `flush_coordinator` settles the email race: the single create's default rolls the
    whole request back into a 409; bulk passes a plain flush so the IntegrityError rolls back only that row's savepoint."""
    # (moved body, with `user` renamed `actor`, and `await _flush_unique_email(db)` replaced by `await flush_coordinator(db)`)
    return school, coordinator, issued
```

`create_school` becomes:

```python
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    # (keep the existing SchoolCreate extra="forbid" comment)
    school, coordinator, issued = await _provision_school(db, payload, user)
    await db.commit()
    delivery = await deliver_welcome_link(user=coordinator, issued=issued, issued_by=user)
    out = await _school_out(db, school)
    return {**out.model_dump(mode="json"), "coordinator_id": coordinator.id, "coordinator_email": coordinator.email, **delivery}
```

- [ ] **Step 4: Run, expect PASS:** `tests/test_enh_029_provision_refactor.py tests/test_sch_003_school_onboarding.py tests/test_enh_009_school_profile_schemas.py tests/test_enh_003_first_time_provisioning.py`.
- [ ] **Step 5: Commit** `refactor(enh-029): extract admin._provision_school from create_school`.

### Task 3: Parameterize ENH-028's private file/claim helpers

**Files:** Modify `apps/api/app/api/school_bulk.py` (helpers ~277-352 and `_upload` ~415-430).

**Interfaces:** Produces (all in `school_bulk`):
- `_file_error(target_type: str, user: User, reason: str, message: str, status: int = 422) -> HTTPException`
- `async def _read_upload(file: UploadFile, idempotency_key: str | None, target_type: str, user: User) -> bytes` (key 422s, 413)
- `def _read_csv(raw: bytes, *, target_type: str, user: User, required: tuple[str, ...], columns: tuple[str, ...], max_rows: int, known: tuple[str, ...] | None = None) -> list[tuple[int, dict[str, str]]]`
- `async def _claim(db, target_type: str, user, key, digest) -> SchoolBulkUploadBatch | tuple[SchoolBulkUploadBatch, list[SchoolBulkUploadRow]]`
- Reused constants: `MAX_FILE_BYTES`, `LOCK_TIMEOUT`, `IN_PROGRESS`, `NOT_CSV`, `_lock_timed_out`.

- [ ] **Step 1: Pin current behaviour** — no new test; ENH-028's suite is the guard. Run first to record the baseline:
  `tests/test_enh_028_bulk_core.py tests/test_enh_028_bulk_results.py` → expect PASS.
- [ ] **Step 2: Refactor.**

```python
def _file_error(target_type: str, user: User, reason: str, message: str, status: int = 422) -> HTTPException:
    logger.info("bulk_upload_rejected_file", extra={"extra_fields": {"actor_id": str(user.id), "target_type": target_type, "reason": reason}})
    return HTTPException(status, message)


async def _read_upload(file: UploadFile, idempotency_key: str | None, target_type: str, user: User) -> bytes:
    """The key checks and the bounded read every bulk surface shares (ENH-028 §5.1, ENH-029 §5.2)."""
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")
    if not KEY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(422, "Idempotency-Key must be 1-120 letters, digits or . _ : -")
    raw = await file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise _file_error(target_type, user, "too_large", "The file is larger than 1 MB", 413)
    return raw


def _read_csv(raw, *, target_type, user, required, columns, max_rows, known=None):
    """(file line, {column: trimmed cell}) for every row with at least one of `columns` filled. `known` (ENH-029) also rejects
    unknown and repeated header names; ENH-028 passes None and keeps ignoring extra columns."""
    # body = today's _filled_rows with: target -> target_type in _file_error calls; ("student_code", *target.required) -> required;
    # target.columns -> columns; MAX_ROWS -> max_rows. After computing `header`, before the missing-column check:
    #     if known is not None:
    #         named = [name for name in header if name]
    #         repeated = next((name for name in named if named.count(name) > 1), None)
    #         if repeated:
    #             raise _file_error(target_type, user, "duplicate_column", f"Duplicate column: {repeated[:40]}")
    #         unknown = next((name for name in named if name not in known), None)
    #         if unknown:
    #             raise _file_error(target_type, user, "unknown_column", f"Unknown column: {unknown[:40]}")
    #     The too-many-rows message uses max_rows.


def _filled_rows(raw: bytes, target: BulkTarget, user: User) -> list[tuple[int, dict[str, str]]]:
    return _read_csv(raw, target_type=target.target_type, user=user, required=("student_code", *target.required), columns=target.columns, max_rows=MAX_ROWS)
```

`_claim(db, target_type, user, key, digest)`: replace `target.target_type` with `target_type`; the replay tail returns
`existing, list(rows)` instead of `_report(existing, list(rows))`. In `_upload`: replace the key/read block with
`raw = await _read_upload(file, idempotency_key, target.target_type, user)`; call `_claim(db, target.target_type, ...)`; replace
`if isinstance(claimed, dict): return claimed` with `if isinstance(claimed, tuple): return _report(*claimed)`.
Update the remaining `_file_error(target, ...)` callers to `_file_error(target.target_type, ...)`.

- [ ] **Step 3: Run, expect PASS** (unchanged): `tests/test_enh_028_bulk_core.py tests/test_enh_028_bulk_results.py tests/test_enh_025_bulk_upload.py`.
- [ ] **Step 4: Commit** `refactor(enh-028): parameterize bulk file/claim helpers by target_type for reuse`.

### Task 4: Onboarding router — authorization, template, file-level validation

**Files:** Create `apps/api/app/api/school_onboarding_bulk.py`, `apps/api/tests/test_enh_029_bulk_onboarding.py`; Modify `apps/api/app/main.py`.

**Interfaces:** Produces `router`, `COLUMNS: tuple[str, ...]`, `REQUIRED`, `TARGET_TYPE = "school_onboarding"`, `MAX_ROWS = 100`.

- [ ] **Step 1: Failing tests** (404 on both paths):

```python
"""ENH-029 -- bulk school onboarding (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import School, SchoolBulkUploadBatch
from app.schemas import SchoolCreate
from tests.enh029_helpers import HEADER, TEMPLATE_URL, csv_bytes, login, mk_admin, school_row, upload


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
    assert response.status_code == 403 and response.json()["detail"] == "Overseas Admin role required"


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client):
    assert (await client.get(TEMPLATE_URL)).status_code == 401
    assert (await upload(client, csv_bytes([school_row()]))).status_code == 401


async def _school_count(db):
    return await db.scalar(select(func.count(School.id)))


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
)
async def test_file_level_rejections_create_nothing(client, db_session, data, status, detail):
    admin = await mk_admin(db_session)
    await login(client, admin)
    before = await _school_count(db_session)
    response = await upload(client, data)
    assert (response.status_code, response.json()["detail"]) == (status, detail)
    assert await _school_count(db_session) == before
    assert not (await db_session.scalars(select(SchoolBulkUploadBatch).where(SchoolBulkUploadBatch.uploaded_by_user_id == admin.id))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "detail"), [(None, "Idempotency-Key header is required"), ("bad key!", "Idempotency-Key must be 1-120 letters, digits or . _ : -")])
async def test_key_is_required_and_validated(client, db_session, key, detail):
    await login(client, await mk_admin(db_session))
    headers = {} if key is None else {"Idempotency-Key": key}
    response = await client.post("/api/v1/overseas-admin/schools/bulk-upload", files={"file": ("s.csv", csv_bytes([school_row()]), "text/csv")}, headers=headers)
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
```

- [ ] **Step 2: Run, expect FAIL** (404).
- [ ] **Step 3: Implement** `school_onboarding_bulk.py` skeleton + template + upload up to parsing (rows processed in Task 5):

```python
"""ENH-029 -- bulk school partner onboarding (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md,
DEC-SCOPE-044).

Each accepted CSV row creates exactly what `POST /overseas-admin/schools` creates, through the same `admin._provision_school`.
One request = one transaction with a savepoint per row, on ENH-028's batch/row tables (`target_type = 'school_onboarding'`);
welcome links go out after the commit. Its own router so `admin.py` does not grow; imports from `admin`/`school_bulk` only.
"""

import asyncio
import csv
import hashlib
import io
import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _provision_school, _valid_email
from app.api.deps import get_current_user
from app.api.school_bulk import IN_PROGRESS, LOCK_TIMEOUT, _claim, _lock_timed_out, _read_csv, _read_upload
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, School, SchoolBulkUploadBatch, SchoolBulkUploadRow, User
from app.schemas import SchoolCreate, validation_message
from app.services.provisioning import IssuedWelcome, deliver_welcome_link

logger = get_logger(__name__)
router = APIRouter(prefix="/overseas-admin", tags=["school-onboarding-bulk"])

TARGET_TYPE = "school_onboarding"
ADMIN_ROLES = {"overseas_admin", "super_admin"}
COLUMNS = tuple(SchoolCreate.model_fields)  # D1: the template is exactly the single create's fields, in order
REQUIRED = ("name", "coordinator_full_name", "coordinator_email")
MAX_ROWS = 100
SEND_CONCURRENCY = 5
LOCK_KEY = 29_0029  # pg_advisory_xact_lock key serializing onboarding uploads (fixed constant, bound as a parameter)
ROW_CONFLICT = "This row conflicts with a record created at the same time; upload it again"


def _require_admin(user: User) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Overseas Admin role required")


@router.get("/schools/bulk-template")
async def bulk_onboarding_template(user: User = Depends(get_current_user)):
    _require_admin(user)
    buffer = io.StringIO()
    csv.writer(buffer).writerow(COLUMNS)
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=school-onboarding-bulk-template.csv", "Cache-Control": "private, no-store"})
```

Register in `main.py`: add `school_onboarding_bulk,` to the `from app.api import (...)` list and `school_onboarding_bulk.router` at
the end of the router tuple.

The upload route (body completed in Task 5):

```python
@router.post("/schools/bulk-upload", status_code=201)
async def bulk_onboard_schools(
    file: UploadFile = File(...), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    started = time.monotonic()
    _require_admin(user)
    raw = await _read_upload(file, idempotency_key, TARGET_TYPE, user)
    filled = _read_csv(raw, target_type=TARGET_TYPE, user=user, required=REQUIRED, columns=COLUMNS, max_rows=MAX_ROWS, known=COLUMNS)
    ...  # Task 5
```

- [ ] **Step 4: Run, expect PASS** for the Task 4 tests (`-k "template or 403 or 401 or file_level or key_is or truncated"`; the trailing-header test passes after Task 5).
- [ ] **Step 5: Commit** `feat(enh-029): onboarding bulk router, template and file-level validation`.

### Task 5: Row processing, transaction, report, replay

**Files:** Modify `school_onboarding_bulk.py`; extend `tests/test_enh_029_bulk_onboarding.py`.

**Interfaces:** Consumes Task 2 `_provision_school`, Task 3 `_claim`. Produces `_report(db, batch, rows, deliveries=None) -> dict`
and `_process(...)` returning `(rows, created)` where `created: list[tuple[int, User, IssuedWelcome]]` (file line, coordinator, token).

- [ ] **Step 1: Failing tests** (append):

```python
from app.models import AuditLog, SchoolBulkUploadRow, User, UserRoleAssignment, PasswordResetToken


ROW_KEYS = {"row_number", "status", "error_message", "created_record_id", "school_code", "school_name", "coordinator_id", "coordinator_email", "email_status"}


async def _ok(client, rows, **kw):
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
    for line, (sent, row) in enumerate(zip(rows, report["rows"]), start=2):
        assert row["row_number"] == line and row["status"] == "accepted" and row["error_message"] is None
        school = await db_session.get(School, uuid.UUID(row["created_record_id"]))
        coordinator = await db_session.get(User, uuid.UUID(row["coordinator_id"]))
        assert school.name == sent["name"] == row["school_name"] and school.school_code == row["school_code"] and school.created_by_user_id == admin.id
        assert (coordinator.email, coordinator.role, coordinator.active, coordinator.profile) == (sent["coordinator_email"], "school_coordinator", True, {"school_id": str(school.id)})
        assert not coordinator.password_hash.startswith("$2")  # unusable hash, never a usable password
        assert await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == coordinator.id, UserRoleAssignment.assigned_by_user_id == admin.id))
        assert await db_session.scalar(select(func.count(PasswordResetToken.id)).where(PasswordResetToken.user_id == coordinator.id, PasswordResetToken.purpose == "welcome")) == 1
        codes.add(school.school_code)
    assert len(codes) == 3
    assert (await db_session.get(School, uuid.UUID(report["rows"][0]["created_record_id"]))).tier == "gold"
    actions = list((await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == admin.id))).all())
    assert actions.count("school.create") == 3 and actions.count("school.coordinator_seed") == 3 and actions.count("school.bulk_upload") == 1


@pytest.mark.asyncio
async def test_mixed_file_isolates_each_bad_row(client, db_session):
    admin = await mk_admin(db_session)
    await login(client, admin)
    taken = school_row()
    await _ok(client, [taken])
    same_email = school_row(coordinator_email="dup-in-file-" + uuid.uuid4().hex[:6] + "@example.local")
    rows = [
        school_row(),                                                     # 2 accepted
        school_row(tier="diamond"),                                       # 3 bad tier (helper)
        school_row(coordinator_email="not-an-email"),                     # 4 bad email
        {**school_row(), "name": ""},                                     # 5 missing name (SchoolCreate)
        school_row(coordinator_email=taken["coordinator_email"].upper()),  # 6 existing email, case-insensitive
        same_email,                                                       # 7 accepted
        school_row(coordinator_email=same_email["coordinator_email"]),    # 8 repeat of row 7
        school_row(name=taken["name"], city=taken["city"]),               # 9 existing school
        school_row(name="Twin " + uuid.uuid4().hex[:6], city="Goa"),      # 10 accepted
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
            assert (r["created_record_id"], r["coordinator_id"], r["school_code"], r["school_name"], r["coordinator_email"], r["email_status"]) == (None,) * 6
            assert set(r) == ROW_KEYS  # one fixed shape (the dev-only token is the single, documented extra on accepted rows)


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
    report = await _ok(client, [school_row(name="  " + base["name"].lower().replace(" ", "   ") + " ")])
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
    header = list(SchoolCreate.model_fields)
    row = school_row(board="CBSE", partnership_date="2026-10-01", tier_valid_until="2027-03-31", website="https://x.example", grades_available="1-12")
    report = await _ok(client, [row], header=header)
    school = await db_session.get(School, uuid.UUID(report["rows"][0]["created_record_id"]))
    assert (school.board, str(school.partnership_date), str(school.tier_valid_until), school.grades_available) == ("CBSE", "2026-10-01", "2027-03-31", "1-12")


@pytest.mark.asyncio
async def test_replay_returns_the_same_report_and_creates_nothing(client, db_session):
    admin = await mk_admin(db_session)
    await login(client, admin)
    data, key = csv_bytes([school_row(), school_row(tier="diamond")]), uuid.uuid4().hex
    first = (await upload(client, data, key)).json()
    before = await db_session.scalar(select(func.count(School.id)))
    replay = await upload(client, data, key)
    assert replay.status_code == 201
    again = replay.json()
    assert await db_session.scalar(select(func.count(School.id))) == before
    for a, b in zip(first["rows"], again["rows"]):
        assert {k: v for k, v in a.items() if k not in ("email_status", "development_welcome_token")} == {k: v for k, v in b.items() if k != "email_status"}
        assert b["email_status"] is None and "development_welcome_token" not in b
    other = await upload(client, csv_bytes([school_row()]), key)
    assert (other.status_code, other.json()["detail"]) == (422, "Idempotency-Key was already used for a different file")
```

- [ ] **Step 2: Run, expect FAIL** (route returns `None` / 500).
- [ ] **Step 3: Implement** in `school_onboarding_bulk.py`:

```python
async def _flush_row(db: AsyncSession) -> None:
    """A plain flush for the row's savepoint (never provisioning.flush_unique_email, whose rollback would discard the batch)."""
    await db.flush()


def _norm(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


async def _report(db: AsyncSession, batch: SchoolBulkUploadBatch, rows: list[SchoolBulkUploadRow], deliveries: dict[int, dict] | None = None) -> dict:
    """One fixed row shape for the first response and every replay; names/codes/emails are read back by the stored ids."""
    school_ids = [r.created_record_id for r in rows if r.created_record_id]
    user_ids = [r.created_user_id for r in rows if r.created_user_id]
    schools = {sid: (code, name) for sid, code, name in (await db.execute(select(School.id, School.school_code, School.name).where(School.id.in_(school_ids)))).all()} if school_ids else {}
    emails = dict((await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all()) if user_ids else {}
    out = []
    for r in rows:
        code, name = schools.get(r.created_record_id, (None, None))
        delivery = (deliveries or {}).get(r.row_number, {})
        item = {
            "row_number": r.row_number, "status": r.status, "error_message": r.error_message,
            "created_record_id": r.created_record_id, "school_code": code, "school_name": name,
            "coordinator_id": r.created_user_id, "coordinator_email": emails.get(r.created_user_id), "email_status": delivery.get("email_status"),
        }
        if "development_welcome_token" in delivery:
            item["development_welcome_token"] = delivery["development_welcome_token"]
        out.append(item)
    return {"id": batch.id, "target_type": batch.target_type, "status": "completed", "total_rows": batch.total_rows, "accepted_count": batch.accepted_count, "rejected_count": batch.rejected_count, "rows": out}


class _Seen:
    """Rules 2-5 (spec §6): what the database already has plus what earlier rows of this file claimed."""

    def __init__(self, emails: set[str], schools: set[tuple[str, str]]):
        self.emails, self.schools = emails, schools
        self.file_emails: dict[str, int] = {}
        self.file_schools: dict[tuple[str, str], int] = {}

    def error(self, line: int, payload: SchoolCreate) -> str | None:
        try:
            email = _valid_email(payload.coordinator_email)
        except HTTPException as exc:
            return exc.detail
        if email in self.file_emails:
            return f"same coordinator_email as row {self.file_emails[email]}"
        self.file_emails[email] = line
        if email in self.emails:
            return "Email already exists"
        school = (_norm(payload.name), _norm(payload.city))
        if school in self.schools:
            return "a school with this name and city already exists"
        if school in self.file_schools:
            return f"same school name and city as row {self.file_schools[school]}"
        self.file_schools[school] = line
        return None


async def _seen(db: AsyncSession, filled: list[tuple[int, dict[str, str]]]) -> _Seen:
    wanted = {cells.get("coordinator_email", "").strip().lower() for _, cells in filled} - {""}
    emails = set((await db.scalars(select(func.lower(User.email)).where(func.lower(User.email).in_(wanted)))).all()) if wanted else set()
    schools = {(_norm(name), _norm(city)) for name, city in (await db.execute(select(School.name, School.city))).all()}
    return _Seen(emails, schools)


async def _process(db: AsyncSession, user: User, batch: SchoolBulkUploadBatch, filled) -> tuple[list[SchoolBulkUploadRow], list[tuple[int, User, IssuedWelcome]]]:
    seen = await _seen(db, filled)
    rows: list[SchoolBulkUploadRow] = []
    created: list[tuple[int, User, IssuedWelcome]] = []
    for line, cells in filled:
        error, school, coordinator = None, None, None
        try:
            payload = SchoolCreate.model_validate({name: value for name, value in cells.items() if value})
        except ValidationError as exc:
            error = validation_message(exc)
        else:
            error = seen.error(line, payload)
            if error is None:
                try:
                    async with db.begin_nested():  # the row's own savepoint: a failure undoes this row only
                        school, coordinator, issued = await _provision_school(db, payload, user, flush_coordinator=_flush_row)
                    created.append((line, coordinator, issued))
                except HTTPException as exc:
                    error = exc.detail
                except IntegrityError:
                    error = ROW_CONFLICT
                    logger.warning("bulk_upload_row_conflict", extra={"extra_fields": {"batch_id": str(batch.id), "target_type": TARGET_TYPE, "row_number": line}})
                if error:
                    school = coordinator = None
        row = SchoolBulkUploadRow(
            batch_id=batch.id, row_number=line, status="rejected" if error else "accepted", error_message=error,
            created_record_id=school.id if school else None, created_user_id=coordinator.id if coordinator else None,
        )
        db.add(row)
        rows.append(row)
    return rows, created
```

Complete the route after parsing:

```python
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
    claimed = await _claim(db, TARGET_TYPE, user, idempotency_key, hashlib.sha256(raw).hexdigest())
    if isinstance(claimed, tuple):
        return await _report(db, *claimed)
    batch = claimed
    await _lock_onboarding(db, user)  # Task 7; until then: await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
    rows, created = await _process(db, user, batch, filled)
    batch.total_rows = len(rows)
    batch.accepted_count = len(created)
    batch.rejected_count = batch.total_rows - batch.accepted_count
    db.add(AuditLog(user_id=user.id, action="school.bulk_upload", entity_type="school_bulk_upload_batch", entity_id=str(batch.id), metadata_json={"target_type": TARGET_TYPE, "total": batch.total_rows, "accepted": batch.accepted_count, "rejected": batch.rejected_count, "file_sha256": batch.file_sha256}))
    await db.commit()
    deliveries = await _deliver(created, user)  # Task 6; until then: deliveries = {}
    report = await _report(db, batch, rows, deliveries)
    logger.info("bulk_upload_completed", extra={"extra_fields": {"batch_id": str(batch.id), "target_type": TARGET_TYPE, "actor_id": str(user.id), "total": batch.total_rows, "accepted": batch.accepted_count, "rejected": batch.rejected_count, "duration_ms": round((time.monotonic() - started) * 1000)}})
    return report
```

- [ ] **Step 4: Run, expect PASS:** whole `tests/test_enh_029_bulk_onboarding.py` (Task 4 + 5 tests).
- [ ] **Step 5: Refactor/lint** (`ruff format`, `ruff check`), rerun, **commit** `feat(enh-029): per-row onboarding with savepoints, batch report and replay`.

### Task 6: Post-commit welcome delivery (≤ 5 concurrent), dev token, logs

**Files:** Modify `school_onboarding_bulk.py`; extend the test file.

**Interfaces:** Produces `async def _deliver(created: list[tuple[int, User, IssuedWelcome]], actor: User) -> dict[int, dict]` keyed by file line.

- [ ] **Step 1: Failing tests:**

```python
import logging

from app.api import school_onboarding_bulk


@pytest.mark.asyncio
async def test_welcome_links_sent_after_commit_at_most_five_at_a_time(client, db_session, monkeypatch):
    await login(client, await mk_admin(db_session))
    state = {"now": 0, "peak": 0, "calls": 0}

    async def fake_deliver(*, user, issued, issued_by):
        state["now"] += 1; state["calls"] += 1; state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return {"email_status": "failed" if user.email.startswith("enh029-coord-fail") else "sent", "expires_at": issued.expires_at}

    monkeypatch.setattr(school_onboarding_bulk, "deliver_welcome_link", fake_deliver)
    rows = [school_row() for _ in range(12)] + [school_row(coordinator_email=f"enh029-coord-fail-{uuid.uuid4().hex[:6]}@example.local")]
    report = await _ok(client, rows)
    assert state["calls"] == 13 and 1 < state["peak"] <= 5
    assert [r["email_status"] for r in report["rows"]] == ["sent"] * 12 + ["failed"]
    assert report["accepted_count"] == 13  # a failed send never undoes a school


@pytest.mark.asyncio
async def test_dev_token_only_in_first_response_and_lets_the_coordinator_sign_in(client, db_session):
    await login(client, await mk_admin(db_session))
    data, key = csv_bytes([school_row()]), uuid.uuid4().hex
    row = (await upload(client, data, key)).json()["rows"][0]
    assert row["email_status"] in {"sent", "not_configured", "failed"}
    activation = await client.post("/api/v1/auth/reset-password", json={"token": row["development_welcome_token"], "new_password": "Sup3r-Secret-Pass!"})
    assert activation.status_code == 200
    assert "development_welcome_token" not in (await upload(client, data, key)).json()["rows"][0]


@pytest.mark.asyncio
async def test_logs_never_carry_emails_names_or_tokens(client, db_session, caplog):
    await login(client, await mk_admin(db_session))
    row = school_row()
    caplog.set_level(logging.DEBUG)
    report = await _ok(client, [row, school_row(tier="diamond")])
    text_logged = "\n".join(f"{r.getMessage()} {getattr(r, 'extra_fields', '')}" for r in caplog.records)
    for secret in (row["coordinator_email"], row["name"], row["coordinator_full_name"], report["rows"][0]["development_welcome_token"]):
        assert secret not in text_logged
    assert "bulk_upload_completed" in text_logged
```

(add `import asyncio` at the top of the test file.)

- [ ] **Step 2: Run, expect FAIL** (`email_status` is `None`; no token).
- [ ] **Step 3: Implement:**

```python
async def _deliver(created: list[tuple[int, User, IssuedWelcome]], actor: User) -> dict[int, dict]:
    """After the commit: each accepted row's welcome link, at most SEND_CONCURRENCY at once. deliver_welcome_link never raises and
    audits in its own session, so a failed send leaves the school and account in place (pending_setup, re-sendable)."""
    gate = asyncio.Semaphore(SEND_CONCURRENCY)

    async def one(coordinator: User, issued: IssuedWelcome) -> dict:
        async with gate:
            return await deliver_welcome_link(user=coordinator, issued=issued, issued_by=actor)

    results = await asyncio.gather(*(one(coordinator, issued) for _, coordinator, issued in created))
    return {line: result for (line, _, _), result in zip(created, results, strict=True)}
```

Replace the Task 5 placeholder `deliveries = {}` with `deliveries = await _deliver(created, user)`.

- [ ] **Step 4: Run, expect PASS** (whole file). **Step 5: Commit** `feat(enh-029): post-commit welcome links, five at a time`.

### Task 7: Concurrency — savepoint isolation and advisory lock

**Files:** Modify `school_onboarding_bulk.py`; extend the test file.

**Interfaces:** Produces `async def _lock_onboarding(db: AsyncSession, user: User) -> None` (409 `IN_PROGRESS` on lock timeout).

- [ ] **Step 1: Failing tests:**

```python
from app.core.database import SessionLocal
from app.services import provisioning


@pytest.mark.asyncio
async def test_email_taken_mid_batch_rolls_back_only_that_row(client, db_session, monkeypatch):
    await login(client, await mk_admin(db_session))
    rows = [school_row(), school_row(), school_row()]
    racer = rows[1]["coordinator_email"]
    original = school_onboarding_bulk._flush_row

    async def racing_flush(db):
        # Past every pre-check, just before this row's coordinator is flushed, another request commits the same email.
        if any(isinstance(o, User) and o.email == racer for o in db.new):
            async with SessionLocal() as other:
                other.add(User(email=racer, password_hash="x", full_name="Racer", role="student", division="overseas", active=True))
                await other.commit()
        await original(db)

    monkeypatch.setattr(school_onboarding_bulk, "_flush_row", racing_flush)
    report = await _ok(client, rows)
    assert [r["status"] for r in report["rows"]] == ["accepted", "rejected", "accepted"]
    assert report["rows"][1]["error_message"] == "This row conflicts with a record created at the same time; upload it again"
    assert await db_session.scalar(select(func.count(School.id)).where(School.name == rows[1]["name"])) == 0
    assert await db_session.scalar(select(func.count(School.id)).where(School.name.in_([rows[0]["name"], rows[2]["name"]]))) == 2


@pytest.mark.asyncio
async def test_concurrent_onboarding_upload_gets_409_while_another_holds_the_lock(client, db_session, monkeypatch):
    await login(client, await mk_admin(db_session))
    monkeypatch.setattr(school_onboarding_bulk, "LOCK_TIMEOUT", "200ms")
    async with SessionLocal() as holder:
        await holder.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": school_onboarding_bulk.LOCK_KEY})
        key = uuid.uuid4().hex
        response = await upload(client, csv_bytes([school_row()]), key)
        await holder.rollback()
    assert (response.status_code, response.json()["detail"]) == (409, "This upload is still being processed; retry shortly")
    assert not (await db_session.scalars(select(SchoolBulkUploadBatch).where(SchoolBulkUploadBatch.idempotency_key == key))).all()  # rolled back; key free
```

(add `from sqlalchemy import text` to imports; the route must read `LOCK_TIMEOUT` from its own module so the monkeypatch applies —
import it as a module-level name in `school_onboarding_bulk`.)

- [ ] **Step 2: Run.** The race test exercises Task 5's savepoint + `_flush_row` and is expected to PASS already (a
  characterization test pinning AC07; if it fails, fix Task 5). The lock test must FAIL: without `_lock_onboarding` the upload
  never takes the advisory lock, so it returns 201 instead of 409.
- [ ] **Step 3: Implement:**

```python
async def _lock_onboarding(db: AsyncSession, user: User) -> None:
    """Spec §7 step 4: one onboarding upload at a time, so two files cannot both pass the duplicate-school checks. Held until this
    transaction ends (before any email is sent); bounded by the request's lock_timeout."""
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
    except DBAPIError as exc:
        if _lock_timed_out(exc):
            logger.warning("bulk_upload_lock_timeout", extra={"extra_fields": {"actor_id": str(user.id), "target_type": TARGET_TYPE, "lock": "onboarding"}})
            raise HTTPException(409, IN_PROGRESS) from exc
        raise
```

The route uses `LOCK_TIMEOUT` (module-level name imported from `school_bulk`) in its `set_config` call.

- [ ] **Step 4: Run, expect PASS.** Then run the whole ENH-029 + regression API set (Task 11 list). **Step 5: Commit** `feat(enh-029): serialize onboarding uploads with an advisory lock`.

### Task 8: Frontend target definition

**Files:** Modify `apps/web/lib/bulkEntry.ts`.

**Interfaces:** Produces `export const SCHOOL_ONBOARDING: BulkTarget` (`id: "bulk-schools"`, `title: "Onboard several schools (CSV)"`,
`noun: "schools"`, `templateUrl: "/api/v1/overseas-admin/schools/bulk-template"`, `uploadUrl: "/api/v1/overseas-admin/schools/bulk-upload"`).

- [ ] **Step 1:** add (the panel test in Task 9 asserts the column order equals the server's template order):

```ts
// ENH-029 -- bulk school onboarding (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md §5.1). Same order as
// SchoolCreate / the server template; the server is the authority on every rule.
const ADMIN_BASE = "/api/v1/overseas-admin/schools";
const UP_TO = (n: number) => `Text, up to ${n} characters`;
export const SCHOOL_ONBOARDING: BulkTarget = {
  id: "bulk-schools",
  title: "Onboard several schools (CSV)",
  noun: "schools",
  templateUrl: `${ADMIN_BASE}/bulk-template`,
  uploadUrl: `${ADMIN_BASE}/bulk-upload`,
  columns: [
    { name: "name", required: true, format: UP_TO(200), example: "Sunrise Public School" },
    { name: "city", required: false, format: UP_TO(120), example: "Pune" },
    { name: "state", required: false, format: UP_TO(120), example: "Maharashtra" },
    { name: "tier", required: false, format: "bronze, silver, gold or platinum", example: "gold" },
    { name: "tier_valid_until", required: false, format: DATE, example: "2027-03-31" },
    { name: "coordinator_full_name", required: true, format: UP_TO(160), example: "Meera Iyer" },
    { name: "coordinator_email", required: true, format: "Email; must not already have an account", example: "meera@sunrise.edu.in" },
    { name: "branch", required: false, format: UP_TO(200), example: "Kothrud" },
    { name: "address", required: false, format: UP_TO(500), example: "12 FC Road, Pune" },
    { name: "contact_number", required: false, format: UP_TO(30), example: "+91 98200 00000" },
    { name: "email", required: false, format: "School email", example: "office@sunrise.edu.in" },
    { name: "website", required: false, format: UP_TO(255), example: "https://sunrise.edu.in" },
    { name: "grades_available", required: false, format: UP_TO(200), example: "1-12" },
    { name: "board", required: false, format: "CBSE, ICSE, State, IB or Other", example: "CBSE" },
    { name: "partnership_date", required: false, format: DATE, example: "2026-10-01" },
    { name: "mou_reference", required: false, format: UP_TO(255), example: "MOU-2026-014" },
    { name: "edusphere_bdm", required: false, format: UP_TO(200), example: "Rahul Menon" },
    { name: "monthly_visit_schedule", required: false, format: UP_TO(200), example: "First Monday" },
    { name: "vice_principal_name", required: false, format: UP_TO(200), example: "Anil Rao" },
  ],
};
```

- [ ] **Step 2:** `tsc` via the Task 9 test run; commit with Task 9.

### Task 9: `AdminSchoolBulkOnboardPanel` + mount

**Files:** Create `apps/web/components/AdminSchoolBulkOnboardPanel.tsx`, `apps/web/tests/components/AdminSchoolBulkOnboardPanel.test.tsx`; Modify `apps/web/components/WorkflowPanel.tsx`.

- [ ] **Step 1: Failing tests:**

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminSchoolBulkOnboardPanel from "@/components/AdminSchoolBulkOnboardPanel";
import { SCHOOL_ONBOARDING } from "@/lib/bulkEntry";

// ENH-029 -- bulk school onboarding panel (spec §9 / AC11).
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const accepted = (n: number, email_status: string | null = "sent") => ({ row_number: n, status: "accepted", error_message: null, created_record_id: `s${n}`, school_code: `CODE000${n}`, school_name: `School ${n}`, coordinator_id: `u${n}`, coordinator_email: `c${n}@x.in`, email_status });
const rejected = (n: number, error_message: string) => ({ row_number: n, status: "rejected", error_message, created_record_id: null, school_code: null, school_name: null, coordinator_id: null, coordinator_email: null, email_status: null });
const report = (rows: object[]) => {
  const acc = rows.filter((r) => (r as { status: string }).status === "accepted").length;
  return { id: "b1", target_type: "school_onboarding", status: "completed", total_rows: rows.length, accepted_count: acc, rejected_count: rows.length - acc, rows };
};

let keys = 0;
beforeEach(() => {
  keys = 0;
  refresh.mockClear();
  vi.stubGlobal("crypto", { ...crypto, randomUUID: () => `key-${++keys}` });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const fileInput = () => screen.getByLabelText(/Filled-in schools file/);
function choose(name = "schools.csv", size = 10) {
  fireEvent.change(fileInput(), { target: { files: [new File(["x".repeat(size)], name, { type: "text/csv" })] } });
}
const submit = () => fireEvent.click(screen.getByRole("button", { name: "Upload schools" }));
const respond = (status: number, body: object) => vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });

describe("AdminSchoolBulkOnboardPanel", () => {
  it("is an action card with the template link and a column reference matching the server order", () => {
    const { container } = render(<AdminSchoolBulkOnboardPanel />);
    expect((container.firstElementChild as HTMLElement).className).toBe("action-card");
    expect(screen.getByRole("heading", { level: 3, name: "Onboard several schools (CSV)" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download the template/ }).getAttribute("href")).toBe(SCHOOL_ONBOARDING.templateUrl);
    expect(SCHOOL_ONBOARDING.columns.map((c) => c.name)).toEqual(["name", "city", "state", "tier", "tier_valid_until", "coordinator_full_name", "coordinator_email", "branch", "address", "contact_number", "email", "website", "grades_available", "board", "partnership_date", "mou_reference", "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name"]);
  });

  it.each([
    ["no file", () => undefined, "Choose a filled-in CSV file first."],
    ["too large", () => choose("big.csv", 1024 * 1024 + 1), "The file is larger than 1 MB."],
    ["not csv", () => choose("schools.xlsx"), "Choose a .csv file."],
  ])("pre-checks %s without calling the server", async (_label, act, message) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminSchoolBulkOnboardPanel />);
    act();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("disables the form while uploading and announces progress", async () => {
    let resolve: (v: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise((r) => { resolve = r; })));
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    expect(screen.getByRole("button", { name: "Uploading…" }).hasAttribute("disabled")).toBe(true);
    expect((fileInput() as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toMatch(/creating schools and sending set-password emails/);
    resolve({ ok: true, status: 201, json: async () => report([accepted(2)]) });
    await screen.findByRole("heading", { name: "Upload result" });
  });

  it("shows the server's file-level error and keeps the same key for a retry", async () => {
    const fetchMock = respond(422, { detail: "Unknown column: role" });
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toBe("Unknown column: role");
    submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const keyOf = (i: number) => ((fetchMock.mock.calls[i][1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"];
    expect(keyOf(0)).toBe("key-1");
    expect(keyOf(1)).toBe("key-1");
  });

  it("explains a dropped connection and retries with the same key; a new file gets a new key", async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("network")).mockResolvedValue({ ok: true, status: 201, json: async () => report([accepted(2)]) });
    vi.stubGlobal("fetch", fetchMock);
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/The connection dropped/);
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    const keyOf = (i: number) => ((fetchMock.mock.calls[i][1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"];
    expect([keyOf(0), keyOf(1)]).toEqual(["key-1", "key-1"]);
    choose("next.csv");
    submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(keyOf(2)).toBe("key-2");
  });

  it.each([
    ["all accepted", [accepted(2), accepted(3)], "form-message", /2 schools onboarded\./],
    ["some rejected", [accepted(2), rejected(3, "Email already exists")], "form-warning", /1 of 2 schools onboarded, 1 rejected/],
    ["all rejected", [rejected(2, "Email already exists")], "form-error", /No schools were onboarded/],
  ])("summarises %s with the matching tone and focuses the result", async (_label, rows, cls, text) => {
    vi.stubGlobal("fetch", respond(201, report(rows)));
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    const heading = await screen.findByRole("heading", { name: "Upload result" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    const summary = screen.getByText(text);
    expect(summary.className).toBe(cls);
    expect(refresh).toHaveBeenCalled();
  });

  it("describes each row: rejected reason, sent, not delivered, replay", async () => {
    vi.stubGlobal("fetch", respond(201, report([rejected(2, "Email already exists"), accepted(3, "sent"), accepted(4, "not_configured"), accepted(5, null)])));
    render(<AdminSchoolBulkOnboardPanel />);
    choose();
    submit();
    await screen.findByRole("heading", { name: "Upload result" });
    const rows = within(screen.getAllByRole("table").at(-1) as HTMLElement).getAllByRole("row").slice(1); // the result table, not the column reference
    expect(within(rows[0]).getByText("Rejected")).toBeTruthy();
    expect(within(rows[0]).getByText("Email already exists")).toBeTruthy();
    expect(within(rows[1]).getByText("Set-password link emailed")).toBeTruthy();
    expect(within(rows[1]).getByText("CODE0003")).toBeTruthy();
    expect(within(rows[2]).getByText(/Email not delivered — re-send from the Users page/)).toBeTruthy();
    expect(within(rows[3]).getByText(/Check the Users page for set-password status/)).toBeTruthy();
    expect(screen.getByText(/1 welcome email was not delivered/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run, expect FAIL** (module not found).
- [ ] **Step 3: Implement** `AdminSchoolBulkOnboardPanel.tsx`:

```tsx
"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { SCHOOL_ONBOARDING } from "@/lib/bulkEntry";
import { type Feedback, errorText, toneClass } from "@/lib/welcomeLink";

type RowReport = {
  row_number: number;
  status: "accepted" | "rejected";
  error_message: string | null;
  school_code: string | null;
  school_name: string | null;
  coordinator_email: string | null;
  email_status: string | null;
};
type BatchReport = { total_rows: number; accepted_count: number; rejected_count: number; rows: RowReport[] };

const MAX_BYTES = 1024 * 1024;
const NETWORK_ERROR = "The connection dropped. Upload again — the same file won't be added twice.";
const UNDELIVERED = new Set(["not_configured", "failed"]);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function rowDetail(row: RowReport): string {
  if (row.status === "rejected") return row.error_message ?? "Rejected";
  if (row.email_status === "sent") return "Set-password link emailed";
  if (row.email_status && UNDELIVERED.has(row.email_status)) return "Email not delivered — re-send from the Users page";
  return "Check the Users page for set-password status";
}

function summary(report: BatchReport): Feedback {
  const undelivered = report.rows.filter((r) => r.status === "accepted" && r.email_status && UNDELIVERED.has(r.email_status)).length;
  const emails = undelivered ? ` ${plural(undelivered, "welcome email")} ${undelivered === 1 ? "was" : "were"} not delivered — re-send from the Users page.` : "";
  if (report.accepted_count === 0) return { text: "No schools were onboarded. Fix the rows below and upload again.", tone: "error" };
  if (report.rejected_count === 0) return { text: `${plural(report.accepted_count, "school")} onboarded.${emails}`, tone: "success" };
  return {
    text: `${report.accepted_count} of ${plural(report.total_rows, "school")} onboarded, ${report.rejected_count} rejected. Schools that succeeded are kept — fix the rejected rows and upload just those.${emails}`,
    tone: "warning",
  };
}

function precheck(file: File | undefined): string | null {
  if (!file) return "Choose a filled-in CSV file first.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose a .csv file.";
  if (file.size > MAX_BYTES) return "The file is larger than 1 MB.";
  return null;
}

function OnboardReport({ report }: { report: BatchReport }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [report]);
  const note = summary(report);
  return (
    <div style={{ marginTop: 16 }}>
      <h4 ref={heading} tabIndex={-1}>Upload result</h4>
      <p className={toneClass[note.tone]}>{note.text}</p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>Row</th><th>Result</th><th>School ID</th><th>School</th><th>Coordinator</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {report.rows.map((r) => (
              <tr key={r.row_number}>
                <td data-label="Row">{r.row_number}</td>
                <td data-label="Result">{r.status === "accepted" ? "Added" : "Rejected"}</td>
                <td data-label="School ID">{r.school_code ?? "-"}</td>
                <td data-label="School">{r.school_name ?? "-"}</td>
                <td data-label="Coordinator">{r.coordinator_email ?? "-"}</td>
                <td data-label="Detail">{rowDetail(r)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ENH-029: download the header-only template, fill one school per row, upload. Each row succeeds or fails on its own. The
// Idempotency-Key belongs to the chosen file, so a retry after a dropped connection replays the first result.
export default function AdminSchoolBulkOnboardPanel() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState<{ file: File; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<BatchReport | null>(null);
  const target = SCHOOL_ONBOARDING;
  const fileId = `${target.id}-file`;

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setChosen(file ? { file, key: crypto.randomUUID() } : null);
    setError(null);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const problem = precheck(chosen?.file);
    if (problem || !chosen) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    const body = new FormData();
    body.append("file", chosen.file);
    try {
      const response = await fetch(target.uploadUrl, { method: "POST", headers: { "Idempotency-Key": chosen.key }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(errorText(data.detail, "Unable to process this upload."));
        return;
      }
      setReport(data);
      setChosen(null);
      if (input.current) input.current.value = "";
      router.refresh();
    } catch {
      setError(NETWORK_ERROR);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card">
      <h3>{target.title}</h3>
      <p className="muted">Add many partner schools at once. Each school gets its own coordinator account and set-password email, exactly like Create school.</p>
      <h4>1. Download the template</h4>
      <a className="btn secondary" href={target.templateUrl} download>Download the template (.csv)</a>
      <details style={{ marginTop: 12 }}>
        <summary>Column reference</summary>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Column</th><th>Required</th><th>Format</th><th>Example</th></tr></thead>
            <tbody>
              {target.columns.map((c) => (
                <tr key={c.name}>
                  <td data-label="Column"><code>{c.name}</code></td>
                  <td data-label="Required">{c.required ? "Yes" : "No"}</td>
                  <td data-label="Format">{c.format}</td>
                  <td data-label="Example">{c.example}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <h4 style={{ marginTop: 16 }}>2. Upload the filled-in file</h4>
      <form className="form" onSubmit={upload} aria-busy={busy} noValidate>
        <div className="field">
          <label htmlFor={fileId}>Filled-in schools file</label>
          <input ref={input} id={fileId} type="file" accept=".csv,text/csv" onChange={choose} disabled={busy} aria-describedby={`${fileId}-help`} />
          <p id={`${fileId}-help`} className="muted field-help">CSV, up to 1 MB and 100 schools. One school per row.</p>
        </div>
        <button className="btn" disabled={busy}>{busy ? "Uploading…" : "Upload schools"}</button>
      </form>
      <p className="visually-hidden" role="status" aria-live="polite">{busy ? "Uploading — creating schools and sending set-password emails. Large files can take up to a minute." : ""}</p>
      {error && <div className="form-error" role="alert" style={{ marginTop: 8 }}>{error}</div>}
      {report && <OnboardReport report={report} />}
    </div>
  );
}
```

Note: the result heading is `h4` (sits under the card's `h3`); the Task 9 tests query `{ name: "Upload result" }` without a level.
`WorkflowPanel.tsx`: import `AdminSchoolBulkOnboardPanel` next to `AdminSchoolCreatePanel` and insert
`{showSchoolCreate && <AdminSchoolBulkOnboardPanel/>}` immediately after `{showSchoolCreate && <AdminSchoolCreatePanel/>}`.

- [ ] **Step 4: Run, expect PASS:** `tests/components/AdminSchoolBulkOnboardPanel.test.tsx tests/components/AdminSchoolCreatePanel.test.tsx tests/components/SchoolBulkEntryPanel.test.tsx`; then `npx tsc --noEmit` and `npx eslint components/AdminSchoolBulkOnboardPanel.tsx lib/bulkEntry.ts components/WorkflowPanel.tsx`.
- [ ] **Step 5: Commit** `feat(enh-029): admin bulk school onboarding panel`.

### Task 10: Playwright e2e

**Files:** Create `apps/web/tests/e2e/enh-029-bulk-school-onboarding.spec.ts`.

```ts
import { expect, test } from "@playwright/test";
import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ENH-029 -- bulk school onboarding through the real Admin Schools page (spec AC01/AC02/AC04/AC11).
const unique = Date.now();
const coord = (n: number) => `enh029-e2e-${n}-${unique}@example.local`;
const header = "name,city,coordinator_full_name,coordinator_email";
const csv = (lines: string[]) => Buffer.from([header, ...lines].join("\n") + "\n");
const file = { name: "schools.csv", mimeType: "text/csv", buffer: csv([`E2E 029 A ${unique},Pune,Coord A,${coord(1)}`, `E2E 029 B ${unique},Goa,Coord B,${coord(2)}`, `E2E 029 C ${unique},Goa,Coord C,${coord(1)}`]) };

async function signIn(page, email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("admin onboards several schools from one CSV; a new coordinator signs in (ENH-029)", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Onboard several schools (CSV)" }) });
  await panel.getByLabel("Filled-in schools file").setInputFiles(file);
  const [response] = await Promise.all([page.waitForResponse((r) => r.url().endsWith("/schools/bulk-upload")), panel.getByRole("button", { name: "Upload schools" }).click()]);
  const report = await response.json();
  await expect(panel.getByRole("heading", { name: "Upload result" })).toBeFocused();
  await expect(panel.getByText("2 of 3 schools onboarded, 1 rejected", { exact: false })).toBeVisible();
  await expect(panel.getByText("same coordinator_email as row 2")).toBeVisible();
  await expect(page.getByText(`E2E 029 A ${unique}`).first()).toBeVisible();

  // choosing the file again is a new intent (new key): every row is now a duplicate and is rejected row-by-row
  await panel.getByLabel("Filled-in schools file").setInputFiles(file);
  await panel.getByRole("button", { name: "Upload schools" }).click();
  await expect(panel.getByText("No schools were onboarded", { exact: false })).toBeVisible();

  await activateWithToken(page.request, report.rows[0].development_welcome_token);
  await signIn(page, coord(1), E2E_PASSWORD, "/school/coordinator/dashboard");
});

test("keyboard-only upload and a 360 px layout (ENH-029 AC11)", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Onboard several schools (CSV)" }) });
  await panel.getByRole("button", { name: "Upload schools" }).focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("alert")).toHaveText("Choose a filled-in CSV file first.");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
```

- [ ] Run against the `enh029` stack (`api` + `web` up with CI env, `web-test npx playwright test tests/e2e/enh-029-bulk-school-onboarding.spec.ts`), plus `sch-003-school-onboarding.spec.ts` and `enh-028-bulk-entry.spec.ts`. Commit `test(enh-029): e2e bulk school onboarding`.

### Task 11: Docs, decision, verification

**Files:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-044`, text = spec §12, `CONFIRMED_CURRENT`, approved
in-session 2026-10-01), `docs/architecture/API_CONTRACT.md` §12A (two endpoints, table §5.2, report shape), `DATA_MODEL.md` (bulk
tables: target list + `created_user_id`), `RBAC_MATRIX.md` (both routes: overseas_admin, super_admin), `SECURITY_CONTROLS.md` (§8
table + D9 accepted risk), `docs/ux/SCREEN_CATALOG.md` + `USER_FLOW_MAP.md` (Admin Schools: bulk onboarding panel),
`docs/features/MASTER_FEATURE_CATALOG.md` + `docs/quality/RTM.md` (ENH-029 AC01–AC12 → tests), `docs/delivery/ENHANCEMENT_BACKLOG.md`
§ENH-029 (status; correct the stale default-password note and line refs).

- [ ] Write the docs; commit `docs(enh-029): contract, data model, RBAC, security, UX, RTM, DEC-SCOPE-044`.
- [ ] Verification (record outputs; no completion claim): `ruff format --check`, `ruff check`, API regression set
  `test_enh_029_* test_sch_003_* test_enh_003_* test_enh_009_* test_enh_023_* test_sch_011_* test_enh_028_* test_sch_002_* test_enh_025_bulk_upload.py`,
  `alembic upgrade head` → `downgrade -1` → `upgrade head` on an empty onboarding table, `vitest run`, `tsc --noEmit`, `eslint`,
  `next build`, the Playwright specs above. Browser validation (1440/768/360/320) and independent review are separate, later steps.
