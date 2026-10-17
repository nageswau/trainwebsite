# AGN-024 Agent Signup KYC Documents — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Education agent who self-registers must upload a PAN card, an Aadhaar card and a business licence, with the numbers. An Overseas Admin or Super Admin verifies or rejects each document, and the agency cannot be approved until all three are verified.

**Architecture:**
- **Data:** a new `agent_org_kyc_documents` table (one row per org per document type) and an `agent_orgs.kyc_required` flag, set only by self-registration.
- **Signup:** `POST /auth/register` also accepts multipart, and an agent signup stores user, org and documents atomically.
- **Gate:** inside `agent_orgs.set_org_status`, so every approve path is covered.
- **New routes** live in `app/api/agent_kyc.py`:
  - admin review under `/overseas-admin/agent-orgs/{org_id}/kyc-documents`
  - the pending agent's own status and re-upload under `/agent/registration`
- **Emails:** go through the existing Notification + `queue_deliveries` outbox.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + PostgreSQL; Next.js 15 / React 19; vitest + Testing Library; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-17-agent-signup-kyc-design.md` (owner answers K1–K8). Executors read both.

## Global Constraints

- The numbers are migration `0164_agent_org_kyc` (down_revision `0163_monthly_reviews`), `DEC-SCOPE-224`, API contract §12EK, RBAC §2.147 and Feature ID AGN-024. **Before Task 1 and again before the final commit, run `git fetch origin && git log origin/main --oneline -5` and re-check that these numbers are still free.** If main moved, re-chain them.
- Document types are exactly `pan`, `aadhaar`, `business_license`. The labels are "PAN card", "Aadhaar card" and "Business licence".
- PAN is upper-cased, then must match `^[A-Z]{5}[0-9]{4}[A-Z]$`. Aadhaar is the **last 4 digits only** and must match `^[0-9]{4}$`. The full Aadhaar number is never accepted or stored. The licence must match `^[A-Za-z0-9/\-. ]{3,64}$` after stripping.
- Files must be PDF, JPEG or PNG, decided from the bytes. EXIF/metadata is stripped. **Max 5 MB (5 × 1024 × 1024 bytes) per file.**
- KYC file storage keys are `agent-kyc/{uuid4 hex}`. They are never served via `/local-files`, `/files/download` or a presigned URL. Only the admin streaming route serves them.
- Document numbers never appear in logs, audit metadata, notification bodies or error messages.
- Only `overseas_admin` and `super_admin` can use admin KYC routes. Only an active Master of the org can use `/agent/registration`.
- Orgs with `kyc_required = false` (every pre-existing org, BDM-onboarded orgs, admin-created orgs) approve exactly as before.
- Backend tests: run only the lite set listed in each task. The user runs the full backend suite themselves. Never run the full suite.
- API tests run in docker from the worktree (Windows-form mount path):
  `docker compose -p agn024 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/agn-024/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"`
  Below, this is written as `API_TEST "<paths>"`.
- Web tests run in docker with `MSYS_NO_PATHCONV=1`:
  `MSYS_NO_PATHCONV=1 docker compose -p agn024 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/agn-024/apps/web:/app" -v /app/node_modules web-test sh -c "<cmd>"`
  Below, this is written as `WEB_TEST "<cmd>"`.
- The user controls the docker stack lifecycle. Ask before starting or stopping long-running stacks for e2e.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push; give the user the push command.

## Review Focus

1. **The legacy per-person approve route** `POST /overseas-admin/agents/{agent_id}/approve` must not bypass the KYC gate. It calls `set_org_status`, so the gate lives there. Task 4 tests this route explicitly.
2. **A partial failure during signup** (for example, the third file is invalid, or the DB commit fails after files were stored) must leave no user, no org and no orphan stored objects. This is tested in Task 3.
3. **A reinstated agency** (suspended → active) must not be re-gated or re-emailed. Only pending/rejected → active is gated. This is tested in Task 4.
4. **Direct access through the public `/local-files` static mount**, using a known `agent-kyc/...` key, must return 404. This is tested in Task 5.
5. **A pending agent re-uploading while the org is concurrently approved or rejected**: the re-upload takes the org row lock and re-checks `pending`, so it returns 409 rather than writing. This is tested in Task 6 (rejected-org case).

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/app/models.py` (modify) | `AgentOrg.kyc_required`; new `AgentOrgKycDocument` + `KYC_CHECKS` |
| `apps/api/alembic/versions/0164_agent_org_kyc.py` (create) | Migration |
| `apps/api/app/services/agent_documents.py` (modify) | `read_upload(file, max_bytes=None)` |
| `apps/api/app/services/agent_kyc.py` (create) | All KYC rules: numbers, files, storage, masking, views, gate, notifications |
| `apps/api/app/services/agent_orgs.py` (modify) | Gate + approval notice in `set_org_status` |
| `apps/api/app/api/auth.py` (modify) | Multipart-capable `/register` |
| `apps/api/app/api/agent_kyc.py` (create) | `admin_router` (review) + `router` (agent status / re-upload) |
| `apps/api/app/api/admin.py` (modify) | `kyc_required` + `kyc_summary` on `/agent-orgs` items |
| `apps/api/app/api/files.py`, `apps/api/app/main.py` (modify) | Refuse `agent-kyc/` keys; register routers; guard `/local-files` |
| `apps/api/app/schemas.py` (modify) | `KycRejectRequest` |
| `apps/api/tests/agn024_helpers.py` (create) | Shared test fixtures |
| `apps/api/tests/test_agn_024_*.py` (create) | Feature tests |
| `apps/api/tests/agn001_helpers.py`, `test_agt_001_registration_approval.py`, `test_agn_001_registration_and_gate.py` (modify) | Agent signups now carry KYC |
| `apps/web/components/RegisterForm.tsx` (modify) | KYC fields, multipart submit |
| `apps/web/lib/agentKyc.ts` (create) | Shared web types, labels, URLs |
| `apps/web/components/AgentKycReview.tsx` (create) | Admin per-document review block |
| `apps/web/components/AgentApprovalPanel.tsx` (modify) | Mount review block; Approve gate |
| `apps/web/components/WorkflowPanel.tsx`, `apps/web/lib/navigation.ts` (modify) | Super Admin access + nav link |
| `apps/web/components/AgentRegistrationStatus.tsx` + `apps/web/app/overseas/agent/registration-status/page.tsx` (create) | Pending agent page |
| `apps/web/components/AccessUnavailable.tsx` (modify) | Link to the status page for pending agents |
| `apps/web/tests/components/*.test.tsx` | vitest |
| `apps/web/tests/e2e/helpers/agency.ts`, existing agent-registering specs, `apps/web/tests/e2e/agn-024-agent-kyc.spec.ts` | e2e |
| `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/delivery/AGENT_CRM_BACKLOG.md`, `docs/architecture/API_CONTRACT.md`, `docs/architecture/RBAC_MATRIX.md`, spec | Docs |

---

### Task 1: Data model and migration 0164

**Files:**
- Modify: `apps/api/app/models.py` (class `AgentOrg` ~line 3638; add the new class right after `AgentOrgMember` ~line 3685)
- Create: `apps/api/alembic/versions/0164_agent_org_kyc.py`
- Test: `apps/api/tests/test_agn_024_migration.py`

**Interfaces:**
- Produces:
  - `app.models.AgentOrgKycDocument`
  - `app.models.KYC_CHECKS: dict[str, str]`
  - `app.models.KYC_DOC_TYPES = ("pan", "aadhaar", "business_license")`
  - `AgentOrg.kyc_required: bool`

- [ ] **Step 1: Write the failing migration test**

Create `apps/api/tests/test_agn_024_migration.py`. Copy the module header, imports and the throwaway-database round-trip test(s) from `apps/api/tests/test_mgmt_032_migration.py`, changing only the following:
- the spec name → `"_agn_024_migration_0164"`
- the file → `VERSIONS / "0164_agent_org_kyc.py"`
- `BASE, HEAD = "0163_monthly_reviews", "0164_agent_org_kyc"`
- the table name `monthly_reviews` → `agent_org_kyc_documents`
- the downgrade-refusal case seeds one `agent_org_kyc_documents` row (it needs an `agent_orgs` row and a `users` row first) instead of a final review.

The two tests below must be present verbatim:

```python
def test_migration_chains_after_0163_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import KYC_CHECKS, AgentOrg, AgentOrgKycDocument

    assert KYC_CHECKS == _migration.CHECKS
    assert {c.name for c in AgentOrgKycDocument.__table__.columns} == {
        "id", "org_id", "doc_type", "doc_number", "file_key", "original_filename", "content_type", "file_size", "status",
        "rejection_reason", "reviewed_by_user_id", "reviewed_at", "uploaded_by_user_id", "created_at", "updated_at",
    }  # fmt: skip
    assert "kyc_required" in {c.name for c in AgentOrg.__table__.columns}
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `API_TEST "tests/test_agn_024_migration.py"`
Expected: an error, because `0164_agent_org_kyc.py` does not exist.

- [ ] **Step 3: Add the models**

In `apps/api/app/models.py`, add to `AgentOrg` after `status_changed_at`:

```python
    # AGN-024 (DEC-SCOPE-224 K4): set only by self-registration; when true the org cannot become active until its three KYC documents
    # are verified (`services.agent_kyc.assert_complete`). Every org that existed before AGN-024 stays false.
    kyc_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
```

Add after the `AgentOrgMember` class:

```python
KYC_DOC_TYPES = ("pan", "aadhaar", "business_license")
KYC_CHECKS = {  # must equal alembic 0164_agent_org_kyc.CHECKS
    "ck_agent_org_kyc_documents_type": "doc_type IN ('pan', 'aadhaar', 'business_license')",
    "ck_agent_org_kyc_documents_status": "status IN ('pending', 'verified', 'rejected')",
    "ck_agent_org_kyc_documents_reason": "(status = 'rejected') = (rejection_reason IS NOT NULL)",
}


class AgentOrgKycDocument(Base, TimestampMixin):
    """AGN-024 / DEC-SCOPE-224: one current KYC document per agency per type (K1). `doc_number` is the full PAN, the licence number,
    or only the LAST 4 Aadhaar digits (K2) -- never the full Aadhaar. `file_key` is server-generated under `agent-kyc/`; the file is
    served only by the admin streaming route. A re-upload replaces the row's file in place; history is the audit log."""

    __tablename__ = "agent_org_kyc_documents"
    __table_args__ = (
        UniqueConstraint("org_id", "doc_type", name="uq_agent_org_kyc_documents_org_type"),
        *(CheckConstraint(sql, name=name) for name, sql in KYC_CHECKS.items()),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(32))
    doc_number: Mapped[str] = mapped_column(String(64))
    file_key: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default=text("'pending'"))
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
```

Before writing the migration, check how `TimestampMixin` declares `created_at`/`updated_at` (grep `class TimestampMixin` in models.py) and that `Text` is imported in models.py. Add the import if it is missing.

- [ ] **Step 4: Write the migration**

Create `apps/api/alembic/versions/0164_agent_org_kyc.py`:

```python
"""AGN-024 -- agent signup KYC documents: agent_org_kyc_documents + agent_orgs.kyc_required.

Revision ID: 0164_agent_org_kyc
Revises: 0163_monthly_reviews

docs/superpowers/specs/2026-10-17-agent-signup-kyc-design.md (DEC-SCOPE-224). Every existing agent_orgs row gets kyc_required=false
(K4: existing agencies approve unchanged). 0001 builds a fresh database from the current models, which already carry both, so each
is created only when missing (0160's idiom). downgrade() refuses while KYC rows exist: identity documents are not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0164_agent_org_kyc"
down_revision = "0163_monthly_reviews"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {  # must equal app.models.KYC_CHECKS
    "ck_agent_org_kyc_documents_type": "doc_type IN ('pan', 'aadhaar', 'business_license')",
    "ck_agent_org_kyc_documents_status": "status IN ('pending', 'verified', 'rejected')",
    "ck_agent_org_kyc_documents_reason": "(status = 'rejected') = (rejection_reason IS NOT NULL)",
}


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or "kyc_required" not in {c["name"] for c in inspector.get_columns("agent_orgs")}:
        op.add_column("agent_orgs", sa.Column("kyc_required", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    if not offline and "agent_org_kyc_documents" in inspector.get_table_names():
        return
    op.create_table(
        "agent_org_kyc_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("agent_orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("doc_number", sa.String(64), nullable=False),
        sa.Column("file_key", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "doc_type", name="uq_agent_org_kyc_documents_org_type"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_agent_org_kyc_documents_org_id", "agent_org_kyc_documents", ["org_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM agent_org_kyc_documents LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0164_agent_org_kyc: KYC documents exist. Export them deliberately first.")
    op.drop_index("ix_agent_org_kyc_documents_org_id", table_name="agent_org_kyc_documents")
    op.drop_table("agent_org_kyc_documents")
    op.drop_column("agent_orgs", "kyc_required")
```

Match the `created_at`/`updated_at` column definitions to `TimestampMixin`. If the mixin's server defaults or nullability differ, copy what the mixin does.

- [ ] **Step 5: Run the test and confirm it passes**

Run: `API_TEST "tests/test_agn_024_migration.py tests/test_mgmt_032_migration.py"`
Expected: all pass. The mgmt-032 "single head" test will now fail because 0164 is the head. Update `test_mgmt_032_migration.py` only if its single-head assertion names 0163 as *the* head (it asserts `len(heads)==1` and that 0163 is among the revisions, which still holds). Leave it unchanged if it still passes.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0164_agent_org_kyc.py apps/api/tests/test_agn_024_migration.py
git commit -m "feat(agn-024): agent_org_kyc_documents table and agent_orgs.kyc_required (migration 0164)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: KYC service (rules, files, views, gate, notifications)

**Files:**
- Modify: `apps/api/app/services/agent_documents.py` (`read_upload`, ~line 117)
- Create: `apps/api/app/services/agent_kyc.py`
- Test: `apps/api/tests/test_agn_024_service.py`

**Interfaces:**
- Consumes: `AgentOrgKycDocument`, `KYC_DOC_TYPES`, `AgentOrg.kyc_required` (Task 1)
- Produces (module `app.services.agent_kyc`, imported as `kyc`):
  - Constants:
    - `DOC_TYPES`
    - `LABELS: dict[str, str]`
    - `NUMBER_FIELDS = {"pan": "pan_number", "aadhaar": "aadhaar_last4", "business_license": "license_number"}`
    - `FILE_FIELDS = {"pan": "pan_file", "aadhaar": "aadhaar_file", "business_license": "license_file"}`
    - `MAX_BYTES`, `STORAGE_PREFIX = "agent-kyc"`, `STATUS_URL = "/overseas/agent/registration-status"`, `REUPLOAD_LIMIT = 20`
    - Messages: `REQUIRED`, `NOT_VERIFIED`, `NOT_PENDING_REVIEW`, `NOT_PENDING_UPLOAD`, `ONLY_REJECTED`
  - `clean_number(doc_type: str, raw: str | None) -> str` (raises 422)
  - `clean_numbers(fields: Mapping[str, object]) -> dict[str, str]` (raises 422 `REQUIRED` when any number is missing)
  - `require_files(files: Mapping[str, object]) -> dict[str, UploadFile]` (raises 422 `REQUIRED`)
  - `async read_kyc_file(doc_type: str, file) -> tuple[bytes, str, str | None]`
  - `store(data: bytes, content_type: str) -> str` and `discard(key: str) -> None`
  - `mask(doc_type: str, number: str) -> str`
  - `async documents(db, org_id) -> list[AgentOrgKycDocument]` (ordered pan, aadhaar, business_license)
  - `admin_view(doc) -> dict` and `agent_view(doc) -> dict`
  - `async summaries(db, org_ids: list) -> dict[UUID, dict[str, int]]`
  - `async assert_complete(db, org: AgentOrg) -> None` (409 `NOT_VERIFIED`)
  - `async notify_rejected(db, org_id, doc) -> None` and `async notify_approved(db, org) -> None` (no commit)
  - `download_name(doc) -> str`
- `app.services.agent_documents.read_upload(file, max_bytes: int | None = None)`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_agn_024_service.py`:

```python
"""AGN-024 -- services.agent_kyc rules (spec §4.2, §4.4, §4.5; DEC-SCOPE-224 K2/K3/K8)."""

import io

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.models import AgentOrgKycDocument, Notification
from app.services import agent_kyc as kyc
from tests.agn001_helpers import mk_active_org, uniq
from tests.agn009_helpers import PDF, PNG


def upload(data: bytes, name: str = "doc.pdf") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


@pytest.mark.parametrize("raw,expected", [("abcde1234f", "ABCDE1234F"), (" ABCDE1234F ", "ABCDE1234F")])
def test_pan_is_upper_cased_and_validated(raw, expected):
    assert kyc.clean_number("pan", raw) == expected


@pytest.mark.parametrize("doc_type,raw", [("pan", "ABCD1234FF"), ("pan", ""), ("aadhaar", "12345"), ("aadhaar", "123412341234"), ("aadhaar", "12a4"), ("business_license", "ab"), ("business_license", "x" * 65), ("business_license", "LIC<1>")])
def test_bad_numbers_are_422_without_echoing_the_value(doc_type, raw):
    with pytest.raises(HTTPException) as exc:
        kyc.clean_number(doc_type, raw)
    assert exc.value.status_code == 422 and (not raw or raw not in exc.value.detail)


def test_clean_numbers_requires_all_three():
    with pytest.raises(HTTPException) as exc:
        kyc.clean_numbers({"pan_number": "ABCDE1234F", "aadhaar_last4": "1234"})
    assert exc.value.status_code == 422 and exc.value.detail == kyc.REQUIRED
    assert kyc.clean_numbers({"pan_number": "abcde1234f", "aadhaar_last4": "1234", "license_number": "LIC-2026/001"}) == {
        "pan": "ABCDE1234F", "aadhaar": "1234", "business_license": "LIC-2026/001"}  # fmt: skip


def test_require_files_needs_three_non_empty_uploads():
    with pytest.raises(HTTPException) as exc:
        kyc.require_files({"pan_file": upload(PDF), "aadhaar_file": upload(PDF)})
    assert exc.value.detail == kyc.REQUIRED
    files = kyc.require_files({"pan_file": upload(PDF), "aadhaar_file": upload(PDF), "license_file": upload(PDF)})
    assert set(files) == set(kyc.DOC_TYPES)


@pytest.mark.asyncio
async def test_read_kyc_file_names_the_document_on_error():
    with pytest.raises(HTTPException) as exc:
        await kyc.read_kyc_file("aadhaar", upload(b"MZ\x90\x00 not a pdf", "evil.pdf"))
    assert exc.value.status_code == 415 and exc.value.detail.startswith("Aadhaar card: ")
    with pytest.raises(HTTPException) as exc:
        await kyc.read_kyc_file("pan", upload(PDF + b"0" * kyc.MAX_BYTES))
    assert exc.value.status_code == 413 and exc.value.detail == "PAN card: The file must be at most 5 MB"
    data, content_type, name = await kyc.read_kyc_file("pan", upload(PNG, "pan.png"))
    assert content_type == "image/png" and name == "pan.png" and b"tEXt" not in data


def test_masking():
    assert kyc.mask("pan", "ABCDE1234F") == "ABCDE****F"
    assert kyc.mask("aadhaar", "1234") == "XXXX XXXX 1234"
    assert kyc.mask("business_license", "LIC-1") == "LIC-1"


def test_store_and_discard_only_touch_kyc_keys():
    key = kyc.store(PDF, "application/pdf")
    assert key.startswith("agent-kyc/") and len(key) == len("agent-kyc/") + 32
    kyc.discard("agent-documents/not-mine")  # refused, logged, no exception
    kyc.discard(key)


async def _org_with_docs(db, statuses: dict[str, str], *, kyc_required: bool = True):
    ctx = await mk_active_org(db, name=f"KYC {uniq()}")
    org = ctx["org"]
    org.status, org.kyc_required = "pending", kyc_required
    for doc_type, status in statuses.items():
        db.add(AgentOrgKycDocument(org_id=org.id, doc_type=doc_type, doc_number="1234" if doc_type == "aadhaar" else "ABCDE1234F", file_key=f"agent-kyc/{uniq()}",
                                   content_type="application/pdf", file_size=10, status=status, rejection_reason="Blurry" if status == "rejected" else None,
                                   uploaded_by_user_id=ctx["master"].id))  # fmt: skip
    await db.commit()
    return ctx


@pytest.mark.asyncio
@pytest.mark.parametrize("statuses", [{}, {"pan": "verified", "aadhaar": "verified"}, {"pan": "verified", "aadhaar": "verified", "business_license": "pending"}, {"pan": "verified", "aadhaar": "rejected", "business_license": "verified"}])
async def test_assert_complete_refuses_until_all_three_verified(db_session, statuses):
    ctx = await _org_with_docs(db_session, statuses)
    with pytest.raises(HTTPException) as exc:
        await kyc.assert_complete(db_session, ctx["org"])
    assert exc.value.status_code == 409 and exc.value.detail == kyc.NOT_VERIFIED


@pytest.mark.asyncio
async def test_assert_complete_passes_when_verified_or_not_required(db_session):
    ok = await _org_with_docs(db_session, {t: "verified" for t in kyc.DOC_TYPES})
    await kyc.assert_complete(db_session, ok["org"])
    legacy = await _org_with_docs(db_session, {}, kyc_required=False)
    await kyc.assert_complete(db_session, legacy["org"])


@pytest.mark.asyncio
async def test_views_summaries_and_rejection_notice(db_session):
    ctx = await _org_with_docs(db_session, {"pan": "verified", "aadhaar": "rejected", "business_license": "pending"})
    docs = await kyc.documents(db_session, ctx["org"].id)
    assert [d.doc_type for d in docs] == ["pan", "aadhaar", "business_license"]
    assert kyc.agent_view(docs[0])["doc_number_display"] == "ABCDE****F" and "doc_number" not in kyc.agent_view(docs[0])
    assert kyc.admin_view(docs[0])["doc_number"] == "ABCDE1234F" and "file_key" not in kyc.admin_view(docs[0])
    assert (await kyc.summaries(db_session, [ctx["org"].id]))[ctx["org"].id] == {"verified": 1, "rejected": 1, "pending": 1}
    await kyc.notify_rejected(db_session, ctx["org"].id, docs[1])
    await db_session.commit()
    note = await db_session.scalar(select(Notification).where(Notification.user_id == ctx["master"].id).order_by(Notification.created_at.desc()))
    assert note.title == "Verification document rejected" and "Aadhaar card" in note.body and "Blurry" in note.body and "1234" not in note.body
    assert note.action_url == kyc.STATUS_URL
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `API_TEST "tests/test_agn_024_service.py"`
Expected: `ModuleNotFoundError: app.services.agent_kyc`.

- [ ] **Step 3: Give `read_upload` a size parameter**

In `apps/api/app/services/agent_documents.py`, replace the head of `read_upload`:

```python
async def read_upload(file: UploadFile, max_bytes: int | None = None) -> tuple[bytes, str, str | None]:
    """G8: the type is decided by the bytes, never by the name or the client's Content-Type; image metadata (EXIF GPS on a passport
    photo) is stripped. Returns (bytes, content type, display file name). `max_bytes` (AGN-024: 5 MB KYC files) defaults to the
    global upload limit."""
    limit = max_bytes or settings.max_upload_bytes
    data = await file.read(limit + 1)
    if not data:
        raise HTTPException(422, EMPTY_FILE)
    if len(data) > limit:
        raise HTTPException(413, f"The file must be at most {max(1, limit // (1024 * 1024))} MB")
```

The rest of the function is unchanged.

- [ ] **Step 4: Write the service**

Create `apps/api/app/services/agent_kyc.py`:

```python
"""AGN-024 (DEC-SCOPE-224): KYC documents at agent self-registration -- PAN card, Aadhaar card and business licence (K1).

Numbers (K2): the full PAN and licence number; ONLY the last 4 Aadhaar digits. Numbers never reach logs, audit metadata, notification
bodies or error messages. Files (K8): PDF/JPEG/PNG decided from the bytes, metadata stripped, at most 5 MB, stored under `agent-kyc/`
and served only by the admin streaming route. The approval gate (K3) is `assert_complete`, called from `agent_orgs.set_org_status`.
"""

import hashlib
import logging
import re
from collections.abc import Mapping
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KYC_DOC_TYPES, AgentOrg, AgentOrgKycDocument, AgentOrgMember, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.services.agent_documents import read_upload
from app.services.storage import storage

logger = logging.getLogger(__name__)

DOC_TYPES = KYC_DOC_TYPES
LABELS = {"pan": "PAN card", "aadhaar": "Aadhaar card", "business_license": "Business licence"}
NUMBER_FIELDS = {"pan": "pan_number", "aadhaar": "aadhaar_last4", "business_license": "license_number"}
FILE_FIELDS = {"pan": "pan_file", "aadhaar": "aadhaar_file", "business_license": "license_file"}
MAX_BYTES = 5 * 1024 * 1024
STORAGE_PREFIX = "agent-kyc"
STATUS_URL = "/overseas/agent/registration-status"
DASHBOARD_URL = "/overseas/agent/dashboard"
REUPLOAD_LIMIT = 20  # per agency per rolling THROTTLE_WINDOW (24 h), counted from audit rows (the AGN-009 pattern)
CHANNELS = ["email"]
EXTENSIONS = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}

REQUIRED = "PAN card, Aadhaar card and business licence are required"
NOT_VERIFIED = "All verification documents must be verified before approval"
NOT_PENDING_REVIEW = "Documents can only be reviewed while the organisation is pending"
NOT_PENDING_UPLOAD = "Documents can only be changed while your registration is pending"
ONLY_REJECTED = "Only a rejected document can be replaced"
REUPLOAD_THROTTLED = "Too many re-uploads today -- try again later"

_PATTERNS = {
    "pan": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "aadhaar": re.compile(r"^[0-9]{4}$"),
    "business_license": re.compile(r"^[A-Za-z0-9/\-. ]{3,64}$"),
}
_INVALID = {
    "pan": "PAN number must look like ABCDE1234F",
    "aadhaar": "Enter only the last 4 digits of the Aadhaar number",
    "business_license": "Business licence number must be 3-64 letters, digits, spaces or / - .",
}


def clean_number(doc_type: str, raw: str | None) -> str:
    value = (raw or "").strip()
    if doc_type == "pan":
        value = value.upper()
    if not _PATTERNS[doc_type].fullmatch(value):
        raise HTTPException(422, _INVALID[doc_type])
    return value


def clean_numbers(fields: Mapping[str, object]) -> dict[str, str]:
    raw = {t: fields.get(NUMBER_FIELDS[t]) for t in DOC_TYPES}
    if any(not isinstance(v, str) or not v.strip() for v in raw.values()):
        raise HTTPException(422, REQUIRED)
    return {t: clean_number(t, raw[t]) for t in DOC_TYPES}


def require_files(files: Mapping[str, object]) -> dict[str, UploadFile]:
    chosen = {t: files.get(FILE_FIELDS[t]) for t in DOC_TYPES}
    if any(f is None or isinstance(f, str) or not getattr(f, "filename", None) for f in chosen.values()):
        raise HTTPException(422, REQUIRED)
    return chosen  # type: ignore[return-value]


async def read_kyc_file(doc_type: str, file) -> tuple[bytes, str, str | None]:
    try:
        return await read_upload(file, max_bytes=MAX_BYTES)
    except HTTPException as exc:
        raise HTTPException(exc.status_code, f"{LABELS[doc_type]}: {exc.detail}") from None


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("agent_kyc_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object this module stored; anything else is refused. A failure leaves an orphan, logged by key digest."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        logger.error("agent_kyc_discard_refused", extra={"extra_fields": {"key_digest": _digest(key)}})
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("agent_kyc_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def mask(doc_type: str, number: str) -> str:
    if doc_type == "pan":
        return f"{number[:5]}****{number[-1:]}"
    if doc_type == "aadhaar":
        return f"XXXX XXXX {number}"
    return number


def download_name(doc: AgentOrgKycDocument) -> str:
    return f"{doc.doc_type}{EXTENSIONS.get(doc.content_type, '')}"  # never the client's file name (header safety)


async def documents(db: AsyncSession, org_id) -> list[AgentOrgKycDocument]:
    rows = (await db.scalars(select(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id))).all()
    return sorted(rows, key=lambda d: DOC_TYPES.index(d.doc_type))


def _common(doc: AgentOrgKycDocument) -> dict:
    return {
        "id": doc.id, "doc_type": doc.doc_type, "label": LABELS[doc.doc_type], "status": doc.status, "rejection_reason": doc.rejection_reason,
        "original_filename": doc.original_filename, "content_type": doc.content_type, "file_size": doc.file_size, "updated_at": doc.updated_at,
    }  # fmt: skip


def admin_view(doc: AgentOrgKycDocument) -> dict:
    return _common(doc) | {"doc_number": doc.doc_number, "reviewed_at": doc.reviewed_at}


def agent_view(doc: AgentOrgKycDocument) -> dict:
    return _common(doc) | {"doc_number_display": mask(doc.doc_type, doc.doc_number)}


async def summaries(db: AsyncSession, org_ids: list) -> dict:
    out = {oid: {"verified": 0, "rejected": 0, "pending": 0} for oid in org_ids}
    if not org_ids:
        return out
    rows = await db.execute(
        select(AgentOrgKycDocument.org_id, AgentOrgKycDocument.status, func.count())
        .where(AgentOrgKycDocument.org_id.in_(org_ids))
        .group_by(AgentOrgKycDocument.org_id, AgentOrgKycDocument.status)
    )
    for org_id, status, count in rows.all():
        out[org_id][status] = count
    return out


async def assert_complete(db: AsyncSession, org: AgentOrg) -> None:
    """K3/K4: a kyc_required org needs all three documents verified; legacy orgs pass untouched."""
    if not org.kyc_required:
        return
    verified = await db.scalar(
        select(func.count()).select_from(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.status == "verified")
    )
    if (verified or 0) < len(DOC_TYPES):
        raise HTTPException(409, NOT_VERIFIED)


async def _active_masters(db: AsyncSession, org_id) -> list[User]:
    rows = await db.scalars(
        select(User)
        .join(AgentOrgMember, AgentOrgMember.user_id == User.id)
        .where(AgentOrgMember.org_id == org_id, AgentOrgMember.role == "master", AgentOrgMember.status == "active", User.active.is_(True))
        .order_by(AgentOrgMember.seq)
    )
    return list(rows)


async def _notify(db: AsyncSession, org_id, title: str, body: str, action_url: str) -> None:
    """No commit: the notice rides the caller's transaction, so a rolled-back action sends nothing (ENH-014 outbox)."""
    for user in await _active_masters(db, org_id):
        item = Notification(user_id=user.id, title=title, body=body, read=False, action_url=action_url)
        db.add(item)
        await queue_deliveries(db, item, user, channels=CHANNELS)


async def notify_rejected(db: AsyncSession, org_id, doc: AgentOrgKycDocument) -> None:
    body = f"Your {LABELS[doc.doc_type]} was rejected: {doc.rejection_reason} Upload a corrected file from your registration status page."
    await _notify(db, org_id, "Verification document rejected", body, STATUS_URL)


async def notify_approved(db: AsyncSession, org: AgentOrg) -> None:
    await _notify(db, org.id, "Agency approved", f"{org.name} has been approved. You can now use the EduSphere agent portal.", DASHBOARD_URL)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `API_TEST "tests/test_agn_024_service.py tests/test_agn_009_upload.py"`
Expected: all pass. `test_agn_009_upload.py` is the regression check for `read_upload`.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/agent_kyc.py apps/api/app/services/agent_documents.py apps/api/tests/test_agn_024_service.py
git commit -m "feat(agn-024): agent_kyc service -- number rules, 5 MB typed uploads, masking, gate, notices

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Multipart agent registration (atomic)

**Files:**
- Modify: `apps/api/app/api/auth.py` (the `register` route, ~lines 116-146)
- Create: `apps/api/tests/agn024_helpers.py`
- Modify: `apps/api/tests/agn001_helpers.py` (`register_agent`), `apps/api/tests/test_agt_001_registration_approval.py` (~line 32), `apps/api/tests/test_agn_001_registration_and_gate.py` (~line 43)
- Test: `apps/api/tests/test_agn_024_registration.py`

**Interfaces:**
- Consumes: the `kyc.*` functions from Task 2
- Produces:
  - `tests.agn024_helpers.KYC_FIELDS: dict[str, str]`
  - `tests.agn024_helpers.kyc_files(pan=PDF, aadhaar=PDF, license=PDF) -> dict` (the httpx `files=` mapping)
  - `async tests.agn024_helpers.register_kyc_agent(client, **overrides) -> dict` (returns the 201 JSON)
  - `async tests.agn024_helpers.org_for(db, user_id) -> AgentOrg`
  - `async tests.agn024_helpers.verify_all(db, org_id, actor) -> None` (marks all three verified directly in the DB)

- [ ] **Step 1: Write the helpers and the failing tests**

Create `apps/api/tests/agn024_helpers.py`:

```python
"""AGN-024 test helpers: a self-registered agent with its three KYC documents, and direct-DB verification for tests whose subject is
something else."""

from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models import AgentOrg, AgentOrgKycDocument
from tests.agn001_helpers import PASSWORD, org_of, uniq
from tests.agn009_helpers import PDF

KYC_FIELDS = {"pan_number": "ABCDE1234F", "aadhaar_last4": "1234", "license_number": "LIC-2026/001"}
REGISTER = "/api/v1/auth/register"


def kyc_files(pan: bytes = PDF, aadhaar: bytes = PDF, license: bytes = PDF) -> dict:
    return {
        "pan_file": ("pan.pdf", pan, "application/pdf"),
        "aadhaar_file": ("aadhaar.pdf", aadhaar, "application/pdf"),
        "license_file": ("licence.pdf", license, "application/pdf"),
    }


def agent_form(**overrides) -> dict:
    return {"email": f"{uniq('agn024')}@example.local", "password": PASSWORD, "full_name": "KYC Agent", "division": "overseas", "account_type": "agent", **KYC_FIELDS, **overrides}


async def register_kyc_agent(client, files: dict | None = None, **overrides) -> dict:
    response = await client.post(REGISTER, data=agent_form(**overrides), files=files or kyc_files())
    assert response.status_code == 201, response.text
    return response.json()


async def org_for(db, user_id) -> AgentOrg:
    return await org_of(db, user_id)


async def verify_all(db, org_id, actor) -> None:
    await db.execute(
        update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id)
        .values(status="verified", rejection_reason=None, reviewed_by_user_id=actor.id, reviewed_at=datetime.now(UTC))
    )
    await db.commit()


async def kyc_rows(db, org_id) -> list[AgentOrgKycDocument]:
    return list((await db.scalars(select(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id).execution_options(populate_existing=True))).all())
```

Create `apps/api/tests/test_agn_024_registration.py`:

```python
"""AGN-024 -- agent self-registration carries the three KYC documents (spec §4.2; DEC-SCOPE-224 K1/K2/K8; AC01-AC03)."""

import pytest
from sqlalchemy import func, select

from app.models import AgentOrgKycDocument, AuditLog, User
from app.services import agent_kyc as kyc
from app.services.storage import storage
from tests.agn001_helpers import PASSWORD, uniq
from tests.agn009_helpers import PDF, PNG
from tests.agn024_helpers import KYC_FIELDS, REGISTER, agent_form, kyc_files, kyc_rows, org_for, register_kyc_agent


async def _users_with(db, email: str) -> int:
    return await db.scalar(select(func.count()).select_from(User).where(User.email == email.lower()))


@pytest.mark.asyncio
async def test_agent_signup_stores_three_pending_documents(client, db_session):
    body = await register_kyc_agent(client, files=kyc_files(aadhaar=PNG))
    org = await org_for(db_session, body["user"]["id"])
    assert org.status == "pending" and org.kyc_required is True
    rows = {r.doc_type: r for r in await kyc_rows(db_session, org.id)}
    assert set(rows) == set(kyc.DOC_TYPES) and {r.status for r in rows.values()} == {"pending"}
    assert rows["aadhaar"].doc_number == "1234" and rows["aadhaar"].content_type == "image/png"
    assert rows["pan"].doc_number == "ABCDE1234F" and rows["pan"].file_key.startswith("agent-kyc/")
    assert storage.read_bytes(rows["pan"].file_key) == PDF
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.register", AuditLog.entity_id == body["user"]["id"]))
    assert audit.metadata_json["kyc_documents"] == 3 and "ABCDE1234F" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["pan_number", "aadhaar_last4", "license_number", "pan_file", "aadhaar_file", "license_file"])
async def test_each_missing_item_is_422_and_creates_nothing(client, db_session, missing):
    form, files = agent_form(), kyc_files()
    form.pop(missing, None)
    files.pop(missing, None)
    response = await client.post(REGISTER, data=form, files=files)
    assert response.status_code == 422 and response.json()["detail"] == kyc.REQUIRED
    assert await _users_with(db_session, form["email"]) == 0


@pytest.mark.asyncio
async def test_json_agent_signup_is_refused_but_json_student_signup_still_works(client, db_session):
    email = f"{uniq('json')}@example.local"
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD, "full_name": "Json Agent", "division": "overseas", "account_type": "agent"})
    assert response.status_code == 422 and response.json()["detail"] == kyc.REQUIRED
    student = await client.post(REGISTER, json={"email": f"{uniq('stu')}@example.local", "password": PASSWORD, "full_name": "Json Student", "division": "overseas"})
    assert student.status_code == 201 and student.json()["user"]["role"] == "overseas_student"


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("pan_number", "ABC1234567"), ("aadhaar_last4", "123412341234"), ("license_number", "x")])
async def test_bad_numbers_are_422(client, db_session, field, value):
    form = agent_form(**{field: value})
    response = await client.post(REGISTER, data=form, files=kyc_files())
    assert response.status_code == 422 and value not in response.text
    assert await _users_with(db_session, form["email"]) == 0


@pytest.mark.asyncio
async def test_oversize_or_wrong_type_file_creates_nothing_and_stores_nothing(client, db_session, monkeypatch):
    written: list[str] = []
    real_write = storage.write_bytes
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: (written.append(key), real_write(key, data, ct))[1])
    form = agent_form()
    big = await client.post(REGISTER, data=form, files=kyc_files(license=PDF + b"0" * kyc.MAX_BYTES))
    assert big.status_code == 413 and big.json()["detail"].startswith("Business licence: ")
    exe = await client.post(REGISTER, data=form, files=kyc_files(license=b"MZ\x90\x00binary"))
    assert exe.status_code == 415 and exe.json()["detail"].startswith("Business licence: ")
    assert await _users_with(db_session, form["email"]) == 0 and written == []


@pytest.mark.asyncio
async def test_commit_failure_discards_stored_files(client, db_session, monkeypatch):
    from app.api import auth as auth_api

    discarded: list[str] = []
    monkeypatch.setattr(auth_api.kyc, "discard", lambda key: discarded.append(key))

    async def boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(auth_api, "_sync_role_assignment", boom)
    form = agent_form()
    with pytest.raises(RuntimeError):
        await client.post(REGISTER, data=form, files=kyc_files())
    assert len(discarded) == 3 and all(k.startswith("agent-kyc/") for k in discarded)
    assert await _users_with(db_session, form["email"]) == 0


@pytest.mark.asyncio
async def test_duplicate_email_is_409_before_any_file_is_stored(client, db_session, monkeypatch):
    body = await register_kyc_agent(client)
    written: list[str] = []
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: written.append(key))
    again = await client.post(REGISTER, data=agent_form(email=body["user"]["email"]), files=kyc_files())
    assert again.status_code == 409 and written == []


@pytest.mark.asyncio
async def test_multipart_student_signup_ignores_kyc(client, db_session):
    response = await client.post(REGISTER, data={"email": f"{uniq('mstu')}@example.local", "password": PASSWORD, "full_name": "Multipart Student", "division": "overseas", **KYC_FIELDS})
    assert response.status_code == 201 and response.json()["user"]["role"] == "overseas_student"
    assert await db_session.scalar(select(func.count()).select_from(AgentOrgKycDocument).where(AgentOrgKycDocument.uploaded_by_user_id == response.json()["user"]["id"])) == 0
```

Note on `test_commit_failure_discards_stored_files`: the ASGI transport re-raises unhandled exceptions. If it returns a 500 instead, assert `response.status_code == 500` rather than using `pytest.raises`.

- [ ] **Step 2: Run them and confirm they fail**

Run: `API_TEST "tests/test_agn_024_registration.py"`
Expected: failures (the JSON agent signup returns 201; multipart returns 422 because the body is not JSON).

- [ ] **Step 3: Rewrite the `register` route**

In `apps/api/app/api/auth.py`, add the imports:
- `from fastapi import Request`, `from fastapi.exceptions import RequestValidationError`, `from pydantic import ValidationError`
- `from app.models import AgentOrg` (if not already imported)
- `from app.services import agent_kyc as kyc`

Then replace the `register` function with:

```python
async def _registration_input(request: Request):
    """AGN-024 (DEC-SCOPE-224): JSON as before, or multipart -- an agent's signup carries its three KYC files. Returns (fields, files,
    form-to-close)."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form(max_files=3, max_fields=20)
        fields = {k: v for k, v in form.multi_items() if isinstance(v, str)}
        files = {k: v for k, v in form.multi_items() if not isinstance(v, str)}
        return fields, files, form
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise RequestValidationError([{"type": "json_invalid", "loc": ("body",), "msg": "A JSON object or multipart form is required", "input": None}])
    return body, {}, None


@router.post("/register", status_code=201)
async def register(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    fields, files, form = await _registration_input(request)
    try:
        return await _register(fields, files, response, db)
    finally:
        if form is not None:
            await form.close()


async def _register(fields: dict, files: dict, response: Response, db: AsyncSession):
    try:
        payload = RegistrationRequest.model_validate(fields)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from None
    is_agent = payload.account_type == "agent"
    # K1: numbers and file presence are checked before anything is looked up or stored.
    numbers = kyc.clean_numbers(fields) if is_agent else {}
    uploads = kyc.require_files(files) if is_agent else {}
    email = payload.email.lower().strip()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    contents = {t: await kyc.read_kyc_file(t, f) for t, f in uploads.items()}  # K8: every file passes before any is stored
    stored: list[str] = []
    try:
        for doc_type, (data, content_type, _name) in contents.items():
            stored.append(kyc.store(data, content_type))
        role = "agent" if is_agent else ("it_student" if payload.division == "it" else "overseas_student")
        student_code = await unique_student_code(db, User.student_code) if role in ("it_student", "overseas_student") else None
        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name.strip(),
            role=role,
            division=payload.division,
            phone=payload.phone,
            active=True,
            email_verified=False,
            student_code=student_code,
            profile={"registration_source": "self_service"},
        )
        db.add(user)
        await db.flush()
        metadata = {"division": user.division, "role": user.role}
        if role == "agent":
            # AGN-001 (D2, E2): one pending organisation + Master M001, named from the optional agency name.
            member = await ensure_agent_org(db, user, agency_name=payload.agency_name, status="pending")
            org = await db.get(AgentOrg, member.org_id)
            org.kyc_required = True  # AGN-024 K4: only self-registered agencies are gated
            for (doc_type, (data, content_type, name)), key in zip(contents.items(), stored, strict=True):
                db.add(AgentOrgKycDocument(org_id=org.id, doc_type=doc_type, doc_number=numbers[doc_type], file_key=key, original_filename=name,
                                           content_type=content_type, file_size=len(data), status="pending", uploaded_by_user_id=user.id))  # fmt: skip
            metadata["kyc_documents"] = len(stored)
        await _sync_role_assignment(db, user)
        db.add(AuditLog(user_id=user.id, action="auth.register", entity_type="user", entity_id=str(user.id), metadata_json=metadata))
        await db.commit()
    except BaseException:
        await db.rollback()
        for key in stored:
            kyc.discard(key)
        raise
    loaded = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role_assignments)))
    assert loaded is not None
    _set_auth_cookies(response, loaded)
    return {"user": UserOut.model_validate(loaded), "expires_in_minutes": settings.access_token_minutes}
```

Also import `AgentOrgKycDocument` from `app.models`. Keep `register_agent`'s old behaviour reachable only through the new helper (next step).

- [ ] **Step 4: Move existing agent-signup tests to multipart**

- `apps/api/tests/agn001_helpers.py` — replace `register_agent` so every existing caller keeps working:

```python
async def register_agent(client, **overrides) -> dict:
    """AGN-024: an agent signup now carries the three KYC documents (DEC-SCOPE-224 K1)."""
    from tests.agn024_helpers import KYC_FIELDS, kyc_files

    payload = {"email": f"{uniq('agn-reg')}@example.local", "password": PASSWORD, "full_name": "Test Agent", "division": "overseas", "account_type": "agent", **KYC_FIELDS, **overrides}
    response = await client.post("/api/v1/auth/register", data={k: v for k, v in payload.items() if v is not None}, files=kyc_files())
    assert response.status_code == 201, response.text
    return response.json()
```

- `apps/api/tests/test_agn_001_registration_and_gate.py:43` — change the JSON post to `data={...same fields..., **KYC_FIELDS}, files=kyc_files()`, importing both from `tests.agn024_helpers`. It still expects 422 (agency_name > 160).
- `apps/api/tests/test_agt_001_registration_approval.py:~32` — change the JSON agent registration the same way.
  - The approve tests at lines ~81 and ~111 call the legacy `/overseas-admin/agents/{id}/approve` on a freshly registered (now `kyc_required`) org. Insert `await verify_all(db_session, (await org_for(db_session, registration["user"]["id"])).id, <the admin user object used in that test>)` before each approve.
  - If a test has no `db_session` fixture, add it to the signature.
- Then search for any other JSON agent signup and convert it the same way:
  `grep -rn "account_type\": \"agent\"\|\"account_type\": \"agent\"" apps/api/tests`
  `test_provider_services.py:54` builds a `RegistrationRequest` object directly. Leave it alone (it never hits the route).

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `API_TEST "tests/test_agn_024_registration.py tests/test_agn_001_registration_and_gate.py tests/test_agt_001_registration_approval.py tests/test_agn_001_org_admin.py tests/test_agn_001_tenancy.py"`
Expected: all pass. If `test_agn_001_org_admin.py` approves a *self-registered* org, it now fails with 409. Fix it the same way, with `verify_all` before the approve. Never weaken the gate to make it pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/auth.py apps/api/tests/agn024_helpers.py apps/api/tests/test_agn_024_registration.py apps/api/tests/agn001_helpers.py apps/api/tests/test_agn_001_registration_and_gate.py apps/api/tests/test_agt_001_registration_approval.py
git commit -m "feat(agn-024): agent self-registration requires PAN, Aadhaar and licence uploads (multipart, atomic)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Approval gate and approval notice in `set_org_status`; list summary

**Files:**
- Modify: `apps/api/app/services/agent_orgs.py` (`set_org_status`, ~line 140)
- Modify: `apps/api/app/api/admin.py` (`list_agent_orgs`, ~line 1405)
- Test: `apps/api/tests/test_agn_024_gate.py`

**Interfaces:**
- Consumes: `kyc.assert_complete`, `kyc.notify_approved`, `kyc.summaries`; helpers `register_kyc_agent`, `org_for`, `verify_all`
- Produces: `/overseas-admin/agent-orgs` items gain `kyc_required: bool` and `kyc_summary: {verified, rejected, pending}`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_agn_024_gate.py`:

```python
"""AGN-024 -- approval gate (spec §4.5; DEC-SCOPE-224 K3/K4/K6; AC05, AC06, AC08)."""

import pytest
from sqlalchemy import select, update

from app.models import AgentOrg, AgentOrgKycDocument, Notification
from app.services import agent_kyc as kyc
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn024_helpers import org_for, register_kyc_agent, verify_all

ORG_ACTION = "/api/v1/overseas-admin/agent-orgs/{}/{}"
LEGACY_APPROVE = "/api/v1/overseas-admin/agents/{}/approve"


async def _pending(client, db):
    body = await register_kyc_agent(client)
    return body["user"]["id"], await org_for(db, body["user"]["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("admin_role", ["overseas_admin", "super_admin"])
async def test_approve_refused_until_all_three_verified(client, db_session, admin_role):
    user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role=admin_role)
    async with client_for(admin.email) as c:
        for verified in (0, 1, 2):
            if verified:
                doc_type = kyc.DOC_TYPES[verified - 1]
                await db_session.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.doc_type == doc_type).values(status="verified"))
                await db_session.commit()
            refused = await c.post(ORG_ACTION.format(org.id, "approve"))
            assert refused.status_code == 409 and refused.json()["detail"] == kyc.NOT_VERIFIED
        await verify_all(db_session, org.id, admin)
        ok = await c.post(ORG_ACTION.format(org.id, "approve"))
    assert ok.status_code == 200 and ok.json()["status"] == "active"
    note = await db_session.scalar(select(Notification).where(Notification.user_id == user_id, Notification.title == "Agency approved"))
    assert note is not None and note.action_url == "/overseas/agent/dashboard"


@pytest.mark.asyncio
async def test_legacy_per_agent_approve_is_gated_too(client, db_session):
    user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(LEGACY_APPROVE.format(user_id))).status_code == 409
        await verify_all(db_session, org.id, admin)
        assert (await c.post(LEGACY_APPROVE.format(user_id))).status_code == 200


@pytest.mark.asyncio
async def test_rejected_to_active_is_gated_and_reject_is_never_gated(client, db_session):
    _user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(ORG_ACTION.format(org.id, "reject"))).status_code == 200
        assert (await c.post(ORG_ACTION.format(org.id, "approve"))).status_code == 409


@pytest.mark.asyncio
async def test_legacy_org_without_kyc_approves_unchanged_and_gets_no_notice(db_session):
    ctx = await mk_active_org(db_session, name=f"Legacy {uniq()}")
    ctx["org"].status = "pending"
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(ORG_ACTION.format(ctx["org"].id, "approve"))).status_code == 200
    assert await db_session.scalar(select(Notification).where(Notification.user_id == ctx["master"].id, Notification.title == "Agency approved")) is None


@pytest.mark.asyncio
async def test_suspend_then_reinstate_is_not_regated_or_renotified(client, db_session):
    user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    await verify_all(db_session, org.id, admin)
    async with client_for(admin.email) as c:
        assert (await c.post(ORG_ACTION.format(org.id, "approve"))).status_code == 200
        assert (await c.post(ORG_ACTION.format(org.id, "suspend"))).status_code == 200
        assert (await c.post(ORG_ACTION.format(org.id, "reinstate"))).status_code == 200
    notes = (await db_session.scalars(select(Notification).where(Notification.user_id == user_id, Notification.title == "Agency approved"))).all()
    assert len(notes) == 1


@pytest.mark.asyncio
async def test_list_items_carry_kyc_summary(client, db_session):
    _user_id, org = await _pending(client, db_session)
    await db_session.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.doc_type == "pan").values(status="verified"))
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        page = (await c.get("/api/v1/overseas-admin/agent-orgs", params={"status": "pending", "q": org.prefix})).json()
    item = next(i for i in page["items"] if i["id"] == str(org.id))
    assert item["kyc_required"] is True and item["kyc_summary"] == {"verified": 1, "rejected": 0, "pending": 2}
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `API_TEST "tests/test_agn_024_gate.py"`
Expected: the first approve returns 200 instead of 409, and `kyc_summary` is a KeyError.

- [ ] **Step 3: Gate in `set_org_status`**

In `apps/api/app/services/agent_orgs.py`, change `set_org_status`:

```python
async def set_org_status(db: AsyncSession, org: AgentOrg, status: str, actor: User, *, write_through: bool) -> None:
    """No commit. E11: approve/reject also set the Master assignments' approval_status; suspend/reinstate do not.
    AGN-024 (DEC-SCOPE-224 K3/K6): becoming active from pending or rejected needs all KYC documents verified when the org is
    kyc_required (every approve path -- org-level and the legacy per-agent route -- comes through here), and queues the approval email.
    Reinstating a suspended org is neither re-gated nor re-announced."""
    from app.services import agent_kyc  # local: agent_kyc imports agent_documents, which imports this module

    approving = status == "active" and org.status in {"pending", "rejected"}
    if approving:
        await agent_kyc.assert_complete(db, org)
    now = datetime.now(UTC)
    org.status = status
    org.status_changed_by_user_id = actor.id
    org.status_changed_at = now
    if write_through:
        await db.execute(
            update(UserRoleAssignment)
            .where(UserRoleAssignment.role == "agent", UserRoleAssignment.division == "overseas", UserRoleAssignment.user_id.in_(select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == org.id)))
            .values(approval_status="approved" if status == "active" else "rejected", approved_by_user_id=actor.id, approved_at=now)
        )
    if approving and org.kyc_required:
        await agent_kyc.notify_approved(db, org)
```

In the legacy `approve_agent` (`admin.py` ~line 1350), `assignment.approval_status = "approved"` is set *before* `set_org_status`. Because the request fails with 409 and the transaction is never committed, the in-memory change is discarded. No reorder is needed, but confirm that the 409 test leaves `approval_status == "pending"` by adding this assertion to `test_legacy_per_agent_approve_is_gated_too`:

```python
    from app.models import UserRoleAssignment
    # after the 409, before verify_all:
    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user_id, UserRoleAssignment.role == "agent").execution_options(populate_existing=True))
    assert assignment.approval_status == "pending"
```

- [ ] **Step 4: Summary on list items**

In `apps/api/app/api/admin.py`, add the import `from app.services import agent_kyc`. In `list_agent_orgs`, after `counts = await org_counts(...)`, add:

```python
    kyc_counts = await agent_kyc.summaries(db, [o.id for o in orgs])  # AGN-024: additive keys only
```

and extend each item dict with `"kyc_required": o.kyc_required, "kyc_summary": kyc_counts[o.id]`.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `API_TEST "tests/test_agn_024_gate.py tests/test_agn_001_org_admin.py tests/test_agt_001_registration_approval.py tests/test_agn_022_network.py tests/test_bdm_019_live.py"`
(Use `ls apps/api/tests | grep agn_022` to get the exact agn-022 file names.)
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/app/api/admin.py apps/api/tests/test_agn_024_gate.py
git commit -m "feat(agn-024): approval gate -- all three KYC documents verified before an agency becomes active

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Admin KYC review routes; private storage hardening

**Files:**
- Create: `apps/api/app/api/agent_kyc.py` (`admin_router`)
- Modify: `apps/api/app/schemas.py` (add `KycRejectRequest`), `apps/api/app/main.py` (router registration ~line 164, `/local-files` mount ~line 166), `apps/api/app/api/files.py` (`download`)
- Test: `apps/api/tests/test_agn_024_admin.py`

**Interfaces:**
- Consumes: `kyc.*`, `lock_org`
- Produces (prefix `/api/v1/overseas-admin`):
  - `GET /agent-orgs/{org_id}/kyc-documents` → `{"kyc_required": bool, "org_status": str, "items": [admin_view...]}`
  - `GET /agent-orgs/{org_id}/kyc-documents/{doc_id}/file` → the bytes
  - `POST /agent-orgs/{org_id}/kyc-documents/{doc_id}/verify` → `admin_view`
  - `POST /agent-orgs/{org_id}/kyc-documents/{doc_id}/reject` with body `{"reason": str}` → `admin_view`
  - `app.api.agent_kyc.admin_router` and `app.api.agent_kyc.router` (the latter is filled in Task 6)

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_agn_024_admin.py`:

```python
"""AGN-024 -- Overseas Admin / Super Admin KYC review (spec §4.5, §4.7; DEC-SCOPE-224 K3/K6/K7; AC04, AC09)."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditLog, Notification
from app.services import agent_kyc as kyc
from app.services.storage import storage
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn009_helpers import PDF
from tests.agn024_helpers import kyc_rows, org_for, register_kyc_agent

BASE = "/api/v1/overseas-admin/agent-orgs/{}/kyc-documents"


async def _world(client, db):
    body = await register_kyc_agent(client)
    org = await org_for(db, body["user"]["id"])
    docs = {d.doc_type: d for d in await kyc_rows(db, org.id)}
    return body["user"]["id"], org, docs


@pytest.mark.asyncio
@pytest.mark.parametrize("admin_role", ["overseas_admin", "super_admin"])
async def test_admin_lists_views_verifies_and_rejects(client, db_session, admin_role):
    user_id, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role=admin_role)
    async with client_for(admin.email) as c:
        listed = (await c.get(BASE.format(org.id))).json()
        assert listed["kyc_required"] is True and [i["doc_type"] for i in listed["items"]] == list(kyc.DOC_TYPES)
        assert listed["items"][0]["doc_number"] == "ABCDE1234F" and "file_key" not in listed["items"][0]
        view = await c.get(f"{BASE.format(org.id)}/{docs['pan'].id}/file")
        assert view.status_code == 200 and view.content == PDF and view.headers["content-type"].startswith("application/pdf")
        assert view.headers["cache-control"] == "no-store" and view.headers["x-content-type-options"] == "nosniff"
        assert view.headers["content-disposition"] == 'inline; filename="pan.pdf"'
        verified = await c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/verify")
        assert verified.status_code == 200 and verified.json()["status"] == "verified"
        rejected = await c.post(f"{BASE.format(org.id)}/{docs['aadhaar'].id}/reject", json={"reason": "Photo is blurred"})
        assert rejected.status_code == 200 and rejected.json()["status"] == "rejected" and rejected.json()["rejection_reason"] == "Photo is blurred"
        flipped = await c.post(f"{BASE.format(org.id)}/{docs['aadhaar'].id}/verify")  # a decision may change while pending
        assert flipped.json()["status"] == "verified" and flipped.json()["rejection_reason"] is None
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == admin.id))).all())
    assert {"agent_kyc.view", "agent_kyc.verify", "agent_kyc.reject"} <= actions
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == admin.id, AuditLog.action.like("agent_kyc.%")))).all()
    assert all("ABCDE1234F" not in str(a.metadata_json) for a in audits)
    note = await db_session.scalar(select(Notification).where(Notification.user_id == user_id, Notification.title == "Verification document rejected"))
    assert note is not None and "Photo is blurred" in note.body


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "  ", "ab", "x" * 501])
async def test_reject_needs_a_3_to_500_character_reason(client, db_session, reason):
    _uid, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/reject", json={"reason": reason})).status_code == 422


@pytest.mark.asyncio
async def test_review_only_while_pending(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        await c.post(f"/api/v1/overseas-admin/agent-orgs/{org.id}/reject")
        refused = await c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/verify")
    assert refused.status_code == 409 and refused.json()["detail"] == kyc.NOT_PENDING_REVIEW


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["agent", "overseas_counselor", "counselor", "it_admin", "overseas_student", "bdm"])
async def test_other_roles_are_403_on_every_admin_route(client, db_session, role):
    _uid, org, docs = await _world(client, db_session)
    other = await mk_user(db_session, role=role)
    async with client_for(other.email) as c:
        calls = [c.get(BASE.format(org.id)), c.get(f"{BASE.format(org.id)}/{docs['pan'].id}/file"),
                 c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/verify"), c.post(f"{BASE.format(org.id)}/{docs['pan'].id}/reject", json={"reason": "nope"})]  # fmt: skip
        for call in calls:
            assert (await call).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    client.cookies.clear()
    assert (await client.get(f"{BASE.format(org.id)}/{docs['pan'].id}/file")).status_code == 401


@pytest.mark.asyncio
async def test_document_of_another_org_is_404(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    other = await mk_active_org(db_session, name=f"Other {uniq()}")
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.get(f"{BASE.format(other['org'].id)}/{docs['pan'].id}/file")).status_code == 404
        assert (await c.post(f"{BASE.format(other['org'].id)}/{docs['pan'].id}/verify")).status_code == 404


@pytest.mark.asyncio
async def test_kyc_keys_are_never_served_by_generic_routes(client, db_session):
    _uid, org, docs = await _world(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.get("/api/v1/files/download", params={"key": docs["pan"].file_key})).status_code == 404
    if not settings.aws_s3_bucket:  # the public static mount exists only in local storage mode
        assert storage.read_bytes(docs["pan"].file_key) == PDF
        assert (await client.get(f"/local-files/{docs['pan'].file_key}")).status_code == 404
```

Before running, confirm the role strings exist (`grep -n "overseas_counselor\|\"bdm\"" apps/api/app/models.py apps/api/app/core/rbac.py | head`) and drop any role that is not real.

- [ ] **Step 2: Run them and confirm they fail**

Run: `API_TEST "tests/test_agn_024_admin.py"`
Expected: 404s (routes not registered).

- [ ] **Step 3: Schema**

Append to `apps/api/app/schemas.py`:

```python
class KycRejectRequest(BaseModel):
    """AGN-024 (DEC-SCOPE-224 K3): the reason the agent is shown and emailed."""

    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value):
        return value.strip() if isinstance(value, str) else value
```

- [ ] **Step 4: The admin router**

Create `apps/api/app/api/agent_kyc.py`:

```python
"""AGN-024 (DEC-SCOPE-224): KYC documents of a self-registered agency.

`admin_router` -- Overseas Admin and Super Admin review each document (K3, K7); the role gate runs before any lookup. Files are
streamed (never a presigned or /local-files URL), never cached, and every view is audited. `router` -- a pending agency's Master sees
its own documents and replaces rejected ones (K5); it deliberately skips `agent_denial_reason`, which refuses pending agencies.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import AgentOrg, AgentOrgKycDocument, AuditLog, User
from app.schemas import KycRejectRequest
from app.services import agent_kyc as kyc
from app.services.agent_orgs import lock_org
from app.services.storage import storage

admin_router = APIRouter(prefix="/overseas-admin", tags=["agent-kyc"])
router = APIRouter(prefix="/agent/registration", tags=["agent-kyc"])

ADMIN_ROLES = {"overseas_admin", "super_admin"}
NO_STORE = {"Cache-Control": "no-store"}


def _require_admin(user: User) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Overseas Admin role required")


def _audit(db: AsyncSession, actor: User, action: str, doc: AgentOrgKycDocument, outcome: str | None = None) -> None:
    db.add(AuditLog(user_id=actor.id, action=action, entity_type="agent_org_kyc_document", entity_id=str(doc.id), outcome=outcome,
                    metadata_json={"org_id": str(doc.org_id), "doc_type": doc.doc_type}))  # fmt: skip  # never the number


async def _doc(db: AsyncSession, org_id: UUID, doc_id: UUID) -> AgentOrgKycDocument:
    doc = await db.scalar(select(AgentOrgKycDocument).where(AgentOrgKycDocument.id == doc_id, AgentOrgKycDocument.org_id == org_id))
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


@admin_router.get("/agent-orgs/{org_id}/kyc-documents")
async def list_kyc_documents(org_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    org = await db.get(AgentOrg, org_id)
    if org is None:
        raise HTTPException(404, "Agent organisation not found")
    response.headers.update(NO_STORE)
    return {"kyc_required": org.kyc_required, "org_status": org.status, "items": [kyc.admin_view(d) for d in await kyc.documents(db, org.id)]}


@admin_router.get("/agent-orgs/{org_id}/kyc-documents/{doc_id}/file")
async def view_kyc_file(org_id: UUID, doc_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    doc = await _doc(db, org_id, doc_id)
    try:
        data = storage.read_bytes(doc.file_key)
    except Exception:
        raise HTTPException(500, "Could not read the file; please try again") from None
    _audit(db, user, "agent_kyc.view", doc)
    await db.commit()
    headers = {**NO_STORE, "Content-Disposition": f'inline; filename="{kyc.download_name(doc)}"', "X-Content-Type-Options": "nosniff"}
    return Response(content=data, media_type=doc.content_type, headers=headers)


async def _review(db: AsyncSession, org_id: UUID, doc_id: UUID, actor: User) -> tuple[AgentOrg, AgentOrgKycDocument]:
    org = await lock_org(db, org_id)  # serialises with approve/reject of the org
    doc = await _doc(db, org.id, doc_id)
    if org.status != "pending":
        raise HTTPException(409, kyc.NOT_PENDING_REVIEW)
    doc.reviewed_by_user_id = actor.id
    doc.reviewed_at = datetime.now(UTC)
    return org, doc


@admin_router.post("/agent-orgs/{org_id}/kyc-documents/{doc_id}/verify")
async def verify_kyc_document(org_id: UUID, doc_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    _org, doc = await _review(db, org_id, doc_id, user)
    doc.status, doc.rejection_reason = "verified", None
    _audit(db, user, "agent_kyc.verify", doc, "verified")
    await db.commit()
    await db.refresh(doc)
    return kyc.admin_view(doc)


@admin_router.post("/agent-orgs/{org_id}/kyc-documents/{doc_id}/reject")
async def reject_kyc_document(org_id: UUID, doc_id: UUID, payload: KycRejectRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    org, doc = await _review(db, org_id, doc_id, user)
    doc.status, doc.rejection_reason = "rejected", payload.reason
    _audit(db, user, "agent_kyc.reject", doc, "rejected")
    await kyc.notify_rejected(db, org.id, doc)  # K6: rides this transaction
    await db.commit()
    await db.refresh(doc)
    return kyc.admin_view(doc)
```

`_require_admin` runs before body validation only if the body is valid. A 403 test for reject sends a valid reason, so this is fine. Check the import path of `get_current_user`/`get_db` against `apps/api/app/api/agent_documents.py` and copy that file's import lines.

- [ ] **Step 5: Register the routers and close the generic paths**

In `apps/api/app/main.py`:
- import `agent_kyc` in the same `from app.api import (...)` block as `agent_documents`
- add `agent_kyc.admin_router, agent_kyc.router` to the router tuple right after `agent_documents.router`
- replace the `/local-files` mount line with:

```python
class _LocalFiles(StaticFiles):
    """AGN-024: the local-mode public mount never serves private prefixes (KYC files are streamed by an admin-only route)."""

    PRIVATE_PREFIXES = ("agent-kyc/",)

    async def get_response(self, path: str, scope):
        if path.replace("\\", "/").lstrip("/").startswith(self.PRIVATE_PREFIXES):
            raise StarletteHTTPException(404)
        return await super().get_response(path, scope)


app.mount("/local-files", _LocalFiles(directory=settings.local_upload_dir, check_dir=False), name="local-files")
```

with `from starlette.exceptions import HTTPException as StarletteHTTPException`.

In `apps/api/app/api/files.py` `download`, after the traversal check, add:

```python
    if key.startswith("agent-kyc/"):  # AGN-024: KYC files are served only by the admin streaming route
        raise HTTPException(404, "Not found")
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `API_TEST "tests/test_agn_024_admin.py tests/test_agn_024_gate.py tests/test_enh_005_hardening.py"`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/agent_kyc.py apps/api/app/schemas.py apps/api/app/main.py apps/api/app/api/files.py apps/api/tests/test_agn_024_admin.py
git commit -m "feat(agn-024): admin KYC review -- list, streamed view, verify, reject with reason; private storage paths

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Pending agent's registration status and re-upload

**Files:**
- Modify: `apps/api/app/api/agent_kyc.py` (`router`)
- Test: `apps/api/tests/test_agn_024_agent.py`

**Interfaces:**
- Produces (prefix `/api/v1/agent/registration`):
  - `GET ""` → `{"org": {"name", "status", "kyc_required"}, "documents": [agent_view...]}`
  - `PUT /documents/{doc_type}/file` (multipart: `file`, optional `doc_number`) → `agent_view`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_agn_024_agent.py`:

```python
"""AGN-024 -- the pending agency's own registration status and re-upload (spec §4.4; DEC-SCOPE-224 K5; AC07)."""

import pytest
from sqlalchemy import select, update

from app.models import AgentOrgKycDocument, AuditLog
from app.services import agent_kyc as kyc
from app.services.storage import storage
from tests.agn001_helpers import PASSWORD, client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import mk_staff
from tests.agn009_helpers import PDF, PNG
from tests.agn024_helpers import kyc_rows, org_for, register_kyc_agent

STATUS = "/api/v1/agent/registration"
REUPLOAD = "/api/v1/agent/registration/documents/{}/file"


async def _registered(client, db):
    body = await register_kyc_agent(client)  # `client` now holds the new agent's cookies
    return body, await org_for(db, body["user"]["id"])


async def _reject(db, org_id, doc_type: str, reason: str = "Unreadable"):
    await db.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id, AgentOrgKycDocument.doc_type == doc_type).values(status="rejected", rejection_reason=reason))
    await db.commit()


@pytest.mark.asyncio
async def test_pending_master_sees_masked_status(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "aadhaar", "Blurred")
    data = (await client.get(STATUS)).json()
    assert data["org"] == {"name": org.name, "status": "pending", "kyc_required": True}
    by_type = {d["doc_type"]: d for d in data["documents"]}
    assert by_type["pan"]["doc_number_display"] == "ABCDE****F" and by_type["aadhaar"]["doc_number_display"] == "XXXX XXXX 1234"
    assert by_type["aadhaar"]["status"] == "rejected" and by_type["aadhaar"]["rejection_reason"] == "Blurred"
    assert "ABCDE1234F" not in str(data) and all("doc_number" not in d and "file_key" not in d for d in data["documents"])


@pytest.mark.asyncio
async def test_reupload_of_a_rejected_document_resets_it_to_pending(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "aadhaar")
    old_key = next(d for d in await kyc_rows(db_session, org.id) if d.doc_type == "aadhaar").file_key
    response = await client.put(REUPLOAD.format("aadhaar"), files={"file": ("aadhaar.png", PNG, "image/png")}, data={"doc_number": "9876"})
    assert response.status_code == 200 and response.json()["status"] == "pending" and response.json()["rejection_reason"] is None
    doc = next(d for d in await kyc_rows(db_session, org.id) if d.doc_type == "aadhaar")
    assert doc.doc_number == "9876" and doc.content_type == "image/png" and doc.file_key != old_key and doc.reviewed_by_user_id is None
    with pytest.raises(Exception):
        storage.read_bytes(old_key)  # the replaced file is gone
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "agent_kyc.reupload", AuditLog.entity_id == str(doc.id))) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "verified"])
async def test_only_rejected_documents_can_be_replaced(client, db_session, status):
    _body, org = await _registered(client, db_session)
    await db_session.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.doc_type == "pan").values(status=status))
    await db_session.commit()
    response = await client.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})
    assert response.status_code == 409 and response.json()["detail"] == kyc.ONLY_REJECTED


@pytest.mark.asyncio
async def test_no_reupload_once_the_org_is_not_pending(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "pan")
    org.status = "rejected"
    await db_session.commit()
    response = await client.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})
    assert response.status_code == 409 and response.json()["detail"] == kyc.NOT_PENDING_UPLOAD
    assert (await client.get(STATUS)).json()["org"]["status"] == "rejected"  # a rejected agency can still read its status


@pytest.mark.asyncio
async def test_bad_reupload_inputs(client, db_session):
    _body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "pan")
    assert (await client.put(REUPLOAD.format("pan"), files={"file": ("x.pdf", b"MZ\x90", "application/pdf")})).status_code == 415
    assert (await client.put(REUPLOAD.format("pan"), files={"file": ("x.pdf", PDF, "application/pdf")}, data={"doc_number": "bad"})).status_code == 422
    assert (await client.put(REUPLOAD.format("passport"), files={"file": ("x.pdf", PDF, "application/pdf")})).status_code == 422


@pytest.mark.asyncio
async def test_reupload_is_throttled(client, db_session):
    body, org = await _registered(client, db_session)
    await _reject(db_session, org.id, "pan")
    for _ in range(kyc.REUPLOAD_LIMIT):
        db_session.add(AuditLog(user_id=body["user"]["id"], action="agent_kyc.reupload", entity_type="agent_org_kyc_document", entity_id=str(uniq())))
    await db_session.commit()
    response = await client.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_non_master_and_non_agent_are_refused(client, db_session):
    ctx = await mk_active_org(db_session, name=f"Staffed {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], full_name="Plain Staff")
    student = await mk_user(db_session, role="overseas_student")
    admin = await mk_user(db_session, role="overseas_admin")
    for email in (staff["user"].email, student.email, admin.email):
        async with client_for(email) as c:
            assert (await c.get(STATUS)).status_code == 403
            assert (await c.put(REUPLOAD.format("pan"), files={"file": ("pan.pdf", PDF, "application/pdf")})).status_code == 403


@pytest.mark.asyncio
async def test_legacy_active_master_sees_no_documents(db_session):
    ctx = await mk_active_org(db_session, name=f"Legacy {uniq()}")
    async with client_for(ctx["master"].email) as c:
        data = (await c.get(STATUS)).json()
    assert data["org"]["kyc_required"] is False and data["documents"] == []
```

Check `mk_staff`'s return shape in `tests/agn002_helpers.py` (`staff["user"]`). Staff logins may need activation before `client_for` can sign in; if so, use whatever `agn002_helpers` provides (for example, a `password` set on creation).

- [ ] **Step 2: Run them and confirm they fail**

Run: `API_TEST "tests/test_agn_024_agent.py"`
Expected: 404 on `/agent/registration`.

- [ ] **Step 3: Implement the agent routes**

Append to `apps/api/app/api/agent_kyc.py`:

```python
async def _own_master_org(db: AsyncSession, user: User) -> UUID:
    membership = user.agent_membership if user.role == "agent" else None
    if membership is None or membership.role != "master" or membership.status != "active":
        raise HTTPException(403, "Only a Master of the agency can manage its registration")
    return membership.org_id


@router.get("")
async def my_registration(response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org = await db.get(AgentOrg, await _own_master_org(db, user))
    response.headers.update(NO_STORE)
    return {"org": {"name": org.name, "status": org.status, "kyc_required": org.kyc_required}, "documents": [kyc.agent_view(d) for d in await kyc.documents(db, org.id)]}


@router.put("/documents/{doc_type}/file")
async def reupload_kyc_document(
    doc_type: Literal["pan", "aadhaar", "business_license"],
    file: UploadFile = File(...),
    doc_number: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.agent_documents import wait_seconds

    org = await lock_org(db, await _own_master_org(db, user))  # serialises with the admin's review/approve
    if org.status != "pending":
        raise HTTPException(409, kyc.NOT_PENDING_UPLOAD)
    doc = await db.scalar(select(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.doc_type == doc_type))
    if doc is None:
        raise HTTPException(404, "Document not found")
    if doc.status != "rejected":
        raise HTTPException(409, kyc.ONLY_REJECTED)
    wait = await wait_seconds(db, user, ("agent_kyc.reupload",), kyc.REUPLOAD_LIMIT)
    if wait:
        raise HTTPException(429, kyc.REUPLOAD_THROTTLED, headers={"Retry-After": str(wait)})
    number = kyc.clean_number(doc_type, doc_number) if (doc_number or "").strip() else doc.doc_number
    data, content_type, name = await kyc.read_kyc_file(doc_type, file)
    key, old_key = kyc.store(data, content_type), doc.file_key
    try:
        doc.doc_number, doc.file_key, doc.original_filename, doc.content_type, doc.file_size = number, key, name, content_type, len(data)
        doc.status, doc.rejection_reason, doc.reviewed_by_user_id, doc.reviewed_at, doc.uploaded_by_user_id = "pending", None, None, None, user.id
        _audit(db, user, "agent_kyc.reupload", doc, "pending")
        await db.commit()
    except BaseException:
        await db.rollback()
        kyc.discard(key)
        raise
    kyc.discard(old_key)
    await db.refresh(doc)
    return kyc.agent_view(doc)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `API_TEST "tests/test_agn_024_agent.py tests/test_agn_024_admin.py"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/agent_kyc.py apps/api/tests/test_agn_024_agent.py
git commit -m "feat(agn-024): pending agency registration status and re-upload of rejected KYC documents

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Registration form (web)

**Files:**
- Create: `apps/web/lib/agentKyc.ts`
- Modify: `apps/web/components/RegisterForm.tsx`
- Test: `apps/web/tests/components/RegisterForm.test.tsx`

**Interfaces:**
- Produces (`@/lib/agentKyc`):
  - `KYC_DOCS: readonly KycDocSpec[]`
  - `KYC_MAX_BYTES`
  - `KYC_ACCEPT = ".pdf,.jpg,.jpeg,.png"`
  - `REGISTRATION_URL = "/api/v1/agent/registration"`
  - `REGISTRATION_STATUS_PATH = "/overseas/agent/registration-status"`
  - `adminKycUrl(orgId: string): string`
  - types `KycDocType`, `KycStatus`, `AgentKycDoc`, `AdminKycDoc`
  - `checkKycFile(label: string, file: File | null): string | null`

- [ ] **Step 1: Write the failing tests**

Replace the agent test in `apps/web/tests/components/RegisterForm.test.tsx` and add the KYC tests (keep the other two existing tests):

```tsx
function pdf(name = "doc.pdf", size = 20) {
  return new File([new Uint8Array(size)], name, { type: "application/pdf" });
}

function fillKyc(overrides: Partial<Record<"pan" | "aadhaar" | "license", File>> = {}) {
  fireEvent.change(screen.getByLabelText("PAN number"), { target: { value: "abcde1234f" } });
  fireEvent.change(screen.getByLabelText("Aadhaar (last 4 digits)"), { target: { value: "1234" } });
  fireEvent.change(screen.getByLabelText("Business licence number"), { target: { value: "LIC-2026/001" } });
  fireEvent.change(screen.getByLabelText(/^PAN card/), { target: { files: [overrides.pan ?? pdf("pan.pdf")] } });
  fireEvent.change(screen.getByLabelText(/^Aadhaar card/), { target: { files: [overrides.aadhaar ?? pdf("aadhaar.pdf")] } });
  fireEvent.change(screen.getByLabelText(/^Business licence \(/), { target: { files: [overrides.license ?? pdf("licence.pdf")] } });
}

it("shows the verification documents only for an education agent (AGN-024)", () => {
  render(<RegisterForm division="overseas" />);
  expect(screen.queryByLabelText("PAN number")).toBeNull();
  fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
  expect(screen.getByLabelText(/^PAN card/)).toHaveAttribute("accept", ".pdf,.jpg,.jpeg,.png");
  expect(screen.getByLabelText(/^PAN card/)).toBeRequired();
  expect(screen.getByText("Only the last 4 digits are stored.")).toBeInTheDocument();
});

it("sends an agent signup as multipart with the three files and numbers, then opens the status page", async () => {
  const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { role: "agent" } }), { status: 201 }));
  vi.stubGlobal("fetch", mock);
  render(<RegisterForm division="overseas" />);
  fill();
  fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
  fireEvent.change(screen.getByLabelText("Agency name (optional)"), { target: { value: "ABC Overseas" } });
  fillKyc();
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/agent/registration-status"));
  const init = mock.mock.calls[0][1] as RequestInit;
  expect(init.headers).toBeUndefined();
  const body = init.body as FormData;
  expect(body.get("account_type")).toBe("agent");
  expect(body.get("agency_name")).toBe("ABC Overseas");
  expect(body.get("pan_number")).toBe("ABCDE1234F");
  expect(body.get("aadhaar_last4")).toBe("1234");
  expect((body.get("license_file") as File).name).toBe("licence.pdf");
});

it("blocks an oversize or wrong-type file before sending, naming the document", async () => {
  const mock = vi.fn();
  vi.stubGlobal("fetch", mock);
  render(<RegisterForm division="overseas" />);
  fill();
  fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
  fillKyc({ aadhaar: pdf("aadhaar.pdf", 5 * 1024 * 1024 + 1) });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Aadhaar card: the file must be at most 5 MB.");
  fillKyc({ license: new File(["x"], "licence.exe", { type: "application/octet-stream" }) });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Business licence: upload a PDF, JPG or PNG file.");
  expect(mock).not.toHaveBeenCalled();
});
```

`"sends no agency_name for a student"` stays as is (JSON), and still parses `body` as JSON.

- [ ] **Step 2: Run them and confirm they fail**

Run: `WEB_TEST "npx vitest run tests/components/RegisterForm.test.tsx"`
Expected: FAIL (no "PAN number" label).

- [ ] **Step 3: Shared lib**

Create `apps/web/lib/agentKyc.ts`:

```ts
// AGN-024 (DEC-SCOPE-224): the three KYC documents an education agent uploads at signup (K1), their numbers (K2: only the last 4
// Aadhaar digits) and the 5 MB PDF/JPG/PNG rule (K8). The server re-checks everything; these checks only give fast feedback.
export type KycDocType = "pan" | "aadhaar" | "business_license";
export type KycStatus = "pending" | "verified" | "rejected";
export type KycDocSpec = {
  type: KycDocType; label: string; numberField: string; numberLabel: string; fileField: string;
  pattern: string; maxLength: number; inputMode?: "numeric"; hint?: string;
};
type KycDocBase = { id: string; doc_type: KycDocType; label: string; status: KycStatus; rejection_reason: string | null; original_filename: string | null; content_type: string; file_size: number; updated_at: string };
export type AgentKycDoc = KycDocBase & { doc_number_display: string };
export type AdminKycDoc = KycDocBase & { doc_number: string; reviewed_at: string | null };

export const KYC_DOCS: readonly KycDocSpec[] = [
  { type: "pan", label: "PAN card", numberField: "pan_number", numberLabel: "PAN number", fileField: "pan_file", pattern: "[A-Za-z]{5}[0-9]{4}[A-Za-z]", maxLength: 10, hint: "Format: ABCDE1234F." },
  { type: "aadhaar", label: "Aadhaar card", numberField: "aadhaar_last4", numberLabel: "Aadhaar (last 4 digits)", fileField: "aadhaar_file", pattern: "[0-9]{4}", maxLength: 4, inputMode: "numeric", hint: "Only the last 4 digits are stored." },
  { type: "business_license", label: "Business licence", numberField: "license_number", numberLabel: "Business licence number", fileField: "license_file", pattern: "[A-Za-z0-9/\\-. ]{3,64}", maxLength: 64 },
];
export const KYC_MAX_BYTES = 5 * 1024 * 1024;
export const KYC_ACCEPT = ".pdf,.jpg,.jpeg,.png";
export const REGISTRATION_URL = "/api/v1/agent/registration";
export const REGISTRATION_STATUS_PATH = "/overseas/agent/registration-status";
export const adminKycUrl = (orgId: string) => `/api/v1/overseas-admin/agent-orgs/${orgId}/kyc-documents`;
export const STATUS_LABEL: Record<KycStatus, string> = { pending: "Pending review", verified: "Verified", rejected: "Rejected" };

export function checkKycFile(label: string, file: File | null): string | null {
  if (!file || !file.size) return `${label}: choose a file.`;
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name)) return `${label}: upload a PDF, JPG or PNG file.`;
  if (file.size > KYC_MAX_BYTES) return `${label}: the file must be at most 5 MB.`;
  return null;
}
```

- [ ] **Step 4: Rewrite `RegisterForm.tsx`**

Replace `apps/web/components/RegisterForm.tsx` with a formatted (not minified) version:

```tsx
"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { KYC_ACCEPT, KYC_DOCS, REGISTRATION_STATUS_PATH, checkKycFile } from "@/lib/agentKyc";

function detail(value: unknown) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Registration failed.";
}

// AGN-001 (E2): an education agent may name their agency; blank falls back to their full name on the server.
// AGN-024 (DEC-SCOPE-224 K1/K2/K8): an agent also uploads PAN card, Aadhaar card and business licence, sent as multipart.
export default function RegisterForm({ division }: { division: "it" | "overseas" }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [accountType, setAccountType] = useState("student");
  const isAgent = division === "overseas" && accountType === "agent";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    const form = new FormData(event.currentTarget);
    const agency = String(form.get("agency_name") || "").trim();
    const base = { full_name: form.get("full_name"), email: form.get("email"), phone: form.get("phone") || null, password: form.get("password"), division, account_type: isAgent ? "agent" : "student" };
    let init: RequestInit;
    if (isAgent) {
      const body = new FormData();
      for (const [key, value] of Object.entries(base)) if (value) body.append(key, String(value));
      if (agency) body.append("agency_name", agency);
      for (const doc of KYC_DOCS) {
        const file = form.get(doc.fileField);
        const problem = checkKycFile(doc.label, file instanceof File ? file : null);
        if (problem) { setMessage(problem); return; }
        const number = String(form.get(doc.numberField) || "").trim();
        body.append(doc.numberField, doc.type === "pan" ? number.toUpperCase() : number);
        body.append(doc.fileField, file as File);
      }
      init = { method: "POST", body };
    } else {
      init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(base) };
    }
    setBusy(true);
    const response = await fetch("/api/v1/auth/register", init);
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) { setMessage(detail(data.detail)); return; }
    router.push(data.user.role === "agent" ? REGISTRATION_STATUS_PATH : division === "it" ? "/it/student/dashboard" : "/overseas/student/dashboard");
    router.refresh();
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="field"><label htmlFor="reg-full-name">Full name</label><input id="reg-full-name" name="full_name" autoComplete="name" required /></div>
      <div className="field"><label htmlFor="reg-email">Email</label><input id="reg-email" name="email" type="email" autoComplete="email" required /></div>
      <div className="field"><label htmlFor="reg-phone">Phone</label><input id="reg-phone" name="phone" type="tel" autoComplete="tel" /></div>
      {division === "overseas" && (
        <div className="field">
          <label htmlFor="reg-account-type">Account type</label>
          <select id="reg-account-type" name="account_type" value={accountType} onChange={(e) => setAccountType(e.target.value)}>
            <option value="student">Student</option>
            <option value="agent">Education agent</option>
          </select>
        </div>
      )}
      {isAgent && <div className="field"><label htmlFor="reg-agency-name">Agency name (optional)</label><input id="reg-agency-name" name="agency_name" maxLength={160} autoComplete="organization" /></div>}
      {isAgent && (
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600 }}>Verification documents</legend>
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>Upload all three. PDF, JPG or PNG, up to 5 MB each. EduSphere checks them before approving your agency.</p>
          {KYC_DOCS.map((doc) => (
            <div key={doc.type} style={{ display: "grid", gap: 8, marginBottom: 12 }}>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor={`reg-${doc.numberField}`}>{doc.numberLabel}</label>
                <input id={`reg-${doc.numberField}`} name={doc.numberField} required pattern={doc.pattern} maxLength={doc.maxLength} inputMode={doc.inputMode} autoComplete="off" aria-describedby={doc.hint ? `reg-${doc.numberField}-hint` : undefined} />
                {doc.hint && <span id={`reg-${doc.numberField}-hint`} className="muted" style={{ fontSize: 12 }}>{doc.hint}</span>}
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor={`reg-${doc.fileField}`}>{doc.label} (PDF, JPG or PNG, max 5 MB)</label>
                <input id={`reg-${doc.fileField}`} name={doc.fileField} type="file" accept={KYC_ACCEPT} required />
              </div>
            </div>
          ))}
        </fieldset>
      )}
      <div className="field"><label htmlFor="reg-password">Password</label><input id="reg-password" name="password" type="password" minLength={10} autoComplete="new-password" required /><span className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span></div>
      {message && <div className="form-error" role="alert">{message}</div>}
      <button className="btn" disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
    </form>
  );
}
```

`fireEvent.click` on submit inside jsdom does not run HTML constraint validation, so the client checks in `submit` are what the tests exercise. The label `"Business licence (PDF…"` is matched by `/^Business licence \(/` so it does not collide with "Business licence number".

- [ ] **Step 5: Run the tests, typecheck and lint**

Run: `WEB_TEST "npx vitest run tests/components/RegisterForm.test.tsx && npx tsc --noEmit && npx eslint components/RegisterForm.tsx lib/agentKyc.ts"`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/agentKyc.ts apps/web/components/RegisterForm.tsx apps/web/tests/components/RegisterForm.test.tsx
git commit -m "feat(agn-024): signup form asks agents for PAN, Aadhaar and licence uploads

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Admin review UI + Super Admin access

**Files:**
- Create: `apps/web/components/AgentKycReview.tsx`
- Modify: `apps/web/components/AgentApprovalPanel.tsx`, `apps/web/components/WorkflowPanel.tsx` (~line 439), `apps/web/lib/navigation.ts` (`SUPER_ADMIN_NAV` ~line 297)
- Test: `apps/web/tests/components/AgentKycReview.test.tsx`

**Interfaces:**
- Consumes: `adminKycUrl`, `AdminKycDoc`, `STATUS_LABEL` (Task 7); `sendRequest`, `sendJson` from `@/lib/apiErrors`
- Produces: `<AgentKycReview orgId={string} orgName={string} onChanged={() => void} />`

- [ ] **Step 1: Write the failing tests**

Create `apps/web/tests/components/AgentKycReview.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentKycReview from "@/components/AgentKycReview";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const doc = (doc_type: string, label: string, status = "pending", extra = {}) => ({ id: `${doc_type}-id`, doc_type, label, status, rejection_reason: null, original_filename: `${doc_type}.pdf`, content_type: "application/pdf", file_size: 10, updated_at: "2026-10-17T00:00:00Z", doc_number: doc_type === "aadhaar" ? "1234" : "ABCDE1234F", reviewed_at: null, ...extra });
const LIST = { kyc_required: true, org_status: "pending", items: [doc("pan", "PAN card"), doc("aadhaar", "Aadhaar card"), doc("business_license", "Business licence")] };

describe("AgentKycReview (AGN-024)", () => {
  it("lists each document with number, status and a View link to the streamed file", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(LIST)));
    render(<AgentKycReview orgId="org-1" orgName="ABC" onChanged={vi.fn()} />);
    expect(await screen.findByText("ABCDE1234F")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View PAN card for ABC" })).toHaveAttribute("href", "/api/v1/overseas-admin/agent-orgs/org-1/kyc-documents/pan-id/file");
    expect(screen.getAllByText("Pending review")).toHaveLength(3);
  });

  it("verifies a document and reports the change", async () => {
    const onChanged = vi.fn();
    const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? json(doc("pan", "PAN card", "verified")) : json(LIST)));
    vi.stubGlobal("fetch", mock);
    render(<AgentKycReview orgId="org-1" orgName="ABC" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Verify PAN card for ABC" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(mock.mock.calls.some(([u, i]) => String(u).endsWith("/pan-id/verify") && i?.method === "POST")).toBe(true);
  });

  it("requires a reason to reject and sends it", async () => {
    const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? json(doc("aadhaar", "Aadhaar card", "rejected", { rejection_reason: "Blurred photo" })) : json(LIST)));
    vi.stubGlobal("fetch", mock);
    render(<AgentKycReview orgId="org-1" orgName="ABC" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Reject Aadhaar card for ABC" }));
    const reason = screen.getByLabelText("Reason for rejecting Aadhaar card");
    expect(reason).toBeRequired();
    fireEvent.change(reason, { target: { value: "Blurred photo" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    await waitFor(() => expect(mock.mock.calls.some(([u, i]) => String(u).endsWith("/aadhaar-id/reject") && JSON.parse(String(i?.body)).reason === "Blurred photo")).toBe(true));
  });
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `WEB_TEST "npx vitest run tests/components/AgentKycReview.test.tsx"`
Expected: FAIL (module not found).

- [ ] **Step 3: The review component**

First check the `sendJson` signature in `apps/web/lib/apiErrors.ts` (`sendJson(url, method, body)`). Then create `apps/web/components/AgentKycReview.tsx`:

```tsx
"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { type AdminKycDoc, STATUS_LABEL, adminKycUrl } from "@/lib/agentKyc";
import { sendJson, sendRequest } from "@/lib/apiErrors";

// AGN-024 (DEC-SCOPE-224 K3): Overseas Admin / Super Admin check each KYC document of a pending agency -- View (streamed, audited),
// Verify, or Reject with a reason the agent is emailed. The panel's Approve stays disabled until all three are verified.
export default function AgentKycReview({ orgId, orgName, onChanged }: { orgId: string; orgName: string; onChanged: () => void }) {
  const [items, setItems] = useState<AdminKycDoc[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const outcome = await sendRequest(adminKycUrl(orgId), { method: "GET" });
    if (!outcome.ok) { setFailed(true); return; }
    setFailed(false);
    setItems((outcome.data as { items: AdminKycDoc[] }).items);
  }, [orgId]);

  useEffect(() => { void load(); }, [load]);

  async function decide(doc: AdminKycDoc, action: "verify" | "reject", reason?: string) {
    setBusy(doc.id); setNote(null);
    const outcome = await sendJson(`${adminKycUrl(orgId)}/${doc.id}/${action}`, "POST", action === "reject" ? { reason } : {});
    setBusy(null);
    if (!outcome.ok) { setNote(outcome.message); return; }
    setRejecting(null);
    setNote(`${doc.label} ${action === "verify" ? "verified" : "rejected"}.`);
    await load();
    onChanged();
  }

  function submitReject(event: FormEvent<HTMLFormElement>, doc: AdminKycDoc) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") || "").trim();
    void decide(doc, "reject", reason);
  }

  if (failed) return <p className="form-error" role="alert" style={{ fontSize: 13 }}>Unable to load verification documents.</p>;
  if (items === null) return <p className="muted" style={{ fontSize: 13 }}>Loading verification documents…</p>;
  return (
    <section aria-label={`Verification documents for ${orgName}`} style={{ marginTop: 8 }}>
      <h6 style={{ margin: "8px 0", fontSize: 13 }}>Verification documents</h6>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
        {items.map((doc) => (
          <li key={doc.id} style={{ fontSize: 13, overflowWrap: "anywhere" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <strong>{doc.label}</strong> <span>{doc.doc_number}</span> <span className="badge">{STATUS_LABEL[doc.status]}</span>
            </div>
            {doc.status === "rejected" && doc.rejection_reason && <div className="muted">Reason: {doc.rejection_reason}</div>}
            {rejecting === doc.id ? (
              <form onSubmit={(e) => submitReject(e, doc)} style={{ display: "grid", gap: 6, marginTop: 6 }}>
                <label htmlFor={`kyc-reason-${doc.id}`}>Reason for rejecting {doc.label}</label>
                <textarea id={`kyc-reason-${doc.id}`} name="reason" required minLength={3} maxLength={500} rows={2} autoFocus />
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn small" disabled={busy === doc.id}>{busy === doc.id ? "Working…" : "Confirm reject"}</button>
                  <button type="button" className="btn secondary small" onClick={() => setRejecting(null)}>Cancel</button>
                </div>
              </form>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                <a className="btn secondary small" href={`${adminKycUrl(orgId)}/${doc.id}/file`} target="_blank" rel="noopener noreferrer" aria-label={`View ${doc.label} for ${orgName}`}>View</a>
                {doc.status !== "verified" && <button type="button" className="btn small" disabled={busy === doc.id} aria-label={`Verify ${doc.label} for ${orgName}`} onClick={() => decide(doc, "verify")}>Verify</button>}
                {doc.status !== "rejected" && <button type="button" className="btn secondary small" disabled={busy === doc.id} aria-label={`Reject ${doc.label} for ${orgName}`} onClick={() => setRejecting(doc.id)}>Reject</button>}
              </div>
            )}
          </li>
        ))}
      </ul>
      <div role="status" aria-live="polite" style={{ fontSize: 13, marginTop: 6 }}>{note}</div>
    </section>
  );
}
```

`sendRequest(url, { method: "GET" })` is the never-throwing fetch. Check that it accepts a GET; if it assumes a body, use `fetch` plus `detailMessage` instead, following the pattern in `AgentDocumentsSection`.

- [ ] **Step 4: Mount it in the approval panel and gate Approve**

In `apps/web/components/AgentApprovalPanel.tsx`:
- extend `type Org` with `kyc_required?: boolean; kyc_summary?: { verified: number; rejected: number; pending: number }`
- import `AgentKycReview`
- inside each card, after the Masters `<ul>`, add:

```tsx
                  {status === "pending" && org.kyc_required && <AgentKycReview orgId={org.id} orgName={org.name} onChanged={load} />}
                  {status === "pending" && org.kyc_required === false && <p className="muted" style={{ fontSize: 12 }}>No documents (registered before AGN-024).</p>}
```

- in the action button map, compute `const kycBlocked = action === "approve" && org.kyc_required === true && (org.kyc_summary?.verified ?? 0) < 3;`
  - set `disabled={busy || kycBlocked}`
  - when `kycBlocked`, render `<span className="muted" id={`kyc-hint-${org.id}`} style={{ fontSize: 12 }}>Verify all 3 documents first</span>`
  - add `aria-describedby={kycBlocked ? `kyc-hint-${org.id}` : undefined}` on the button

  This applies on both the Pending and Rejected tabs, since rejected → approve is also gated server-side. Show the review block only on Pending; a rejected org's docs are read-only and not needed for v1.
- Use the panel's existing reload function name for `onChanged`. Check: it is `load` (used in the Retry button).

Add a test case to `apps/web/tests/components/AgentApprovalPanel.test.tsx` if that file exists (`ls apps/web/tests/components | grep -i approval`). Otherwise create it with one case: a pending org with `kyc_required: true, kyc_summary: {verified: 2, rejected: 0, pending: 1}` renders the `Approve <name>` button disabled and shows "Verify all 3 documents first". Stub `fetch` so the list URL returns `{items:[org], total:1, limit:20, offset:0}` and the kyc URL returns `LIST` from the test above.

- [ ] **Step 5: Super Admin access (K7)**

- `apps/web/components/WorkflowPanel.tsx`: `const showAgentApproval = ["overseas_admin", "super_admin"].includes(user.role) && section === "agents";`
- `apps/web/lib/navigation.ts`: in `SUPER_ADMIN_NAV`, next to the existing `{label:"School Analytics",href:"/overseas/admin/school-analytics"}` entry, add `{label:"Agent Approvals",href:"/overseas/admin/agents"}`.
- Run `grep -rn "SUPER_ADMIN_NAV" apps/web/tests` and update any test that pins the nav entries.

- [ ] **Step 6: Run the tests, typecheck and lint**

Run: `WEB_TEST "npx vitest run tests/components/AgentKycReview.test.tsx tests/components/AgentApprovalPanel.test.tsx tests/components/RegisterForm.test.tsx && npx vitest run -t navigation && npx tsc --noEmit && npx eslint components lib"`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/AgentKycReview.tsx apps/web/components/AgentApprovalPanel.tsx apps/web/components/WorkflowPanel.tsx apps/web/lib/navigation.ts apps/web/tests/components
git commit -m "feat(agn-024): admin verifies each KYC document; Approve waits for all three; Super Admin gets Agent Approvals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Pending agent's registration status page (web)

**Files:**
- Create: `apps/web/components/AgentRegistrationStatus.tsx`, `apps/web/app/overseas/agent/registration-status/page.tsx`
- Modify: `apps/web/components/AccessUnavailable.tsx` (~lines 20-36)
- Test: `apps/web/tests/components/AgentRegistrationStatus.test.tsx`, `apps/web/tests/components/AccessUnavailable.test.tsx`

**Interfaces:**
- Consumes: `REGISTRATION_URL`, `REGISTRATION_STATUS_PATH`, `AgentKycDoc`, `STATUS_LABEL`, `KYC_DOCS`, `KYC_ACCEPT`, `checkKycFile` (Task 7); `sendRequest`
- Produces: the `<AgentRegistrationStatus />` client component

- [ ] **Step 1: Write the failing tests**

Create `apps/web/tests/components/AgentRegistrationStatus.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentRegistrationStatus from "@/components/AgentRegistrationStatus";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn(), push: vi.fn() }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const doc = (doc_type: string, label: string, status: string, extra = {}) => ({ id: `${doc_type}-id`, doc_type, label, status, rejection_reason: null, original_filename: "f.pdf", content_type: "application/pdf", file_size: 10, updated_at: "2026-10-17T00:00:00Z", doc_number_display: "ABCDE****F", ...extra });
const pending = (docs: unknown[]) => ({ org: { name: "ABC Overseas", status: "pending", kyc_required: true }, documents: docs });

describe("AgentRegistrationStatus (AGN-024)", () => {
  it("shows each document's status and the rejection reason, with re-upload only for rejected", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(pending([doc("pan", "PAN card", "verified"), doc("aadhaar", "Aadhaar card", "rejected", { rejection_reason: "Blurred", doc_number_display: "XXXX XXXX 1234" }), doc("business_license", "Business licence", "pending")]))));
    render(<AgentRegistrationStatus />);
    expect(await screen.findByText("Reason: Blurred")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByLabelText(/^New Aadhaar card file/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^New PAN card file/)).toBeNull();
  });

  it("re-uploads a rejected document as multipart PUT", async () => {
    const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "PUT" ? json(doc("aadhaar", "Aadhaar card", "pending")) : json(pending([doc("aadhaar", "Aadhaar card", "rejected", { rejection_reason: "Blurred" })]))));
    vi.stubGlobal("fetch", mock);
    render(<AgentRegistrationStatus />);
    fireEvent.change(await screen.findByLabelText(/^New Aadhaar card file/), { target: { files: [new File([new Uint8Array(10)], "a.pdf", { type: "application/pdf" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload new Aadhaar card" }));
    await waitFor(() => expect(mock.mock.calls.some(([u, i]) => String(u).endsWith("/documents/aadhaar/file") && i?.method === "PUT" && i.body instanceof FormData)).toBe(true));
  });

  it("sends an active agency to the dashboard and tells a rejected one", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ org: { name: "ABC", status: "active", kyc_required: true }, documents: [] })));
    render(<AgentRegistrationStatus />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/overseas/agent/dashboard"));
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ org: { name: "ABC", status: "rejected", kyc_required: true }, documents: [doc("pan", "PAN card", "rejected", { rejection_reason: "Fake" })] })));
    render(<AgentRegistrationStatus />);
    expect(await screen.findByText("Registration rejected")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Upload new/ })).toBeNull();
  });
});
```

Add a case to `apps/web/tests/components/AccessUnavailable.test.tsx`, following its existing pattern (`render(await accessUnavailable(new ApiError(msg, 403)))` with `serverApi` mocked to return an agent user). It should check that:
- the message `"Agent registration is pending approval"` renders a link `View registration status` → `/overseas/agent/registration-status`
- `"Your agency's account is suspended"` does not render that link

- [ ] **Step 2: Run them and confirm they fail**

Run: `WEB_TEST "npx vitest run tests/components/AgentRegistrationStatus.test.tsx tests/components/AccessUnavailable.test.tsx"`
Expected: FAIL.

- [ ] **Step 3: The status component**

Create `apps/web/components/AgentRegistrationStatus.tsx`:

```tsx
"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { type AgentKycDoc, KYC_ACCEPT, KYC_DOCS, REGISTRATION_URL, STATUS_LABEL, checkKycFile } from "@/lib/agentKyc";
import { sendRequest } from "@/lib/apiErrors";

type Registration = { org: { name: string; status: string; kyc_required: boolean }; documents: AgentKycDoc[] };

// AGN-024 (DEC-SCOPE-224 K5): the one page a pending agency's Master can use -- each KYC document's status, the reason for a
// rejection, and a re-upload for rejected documents. Everything else in the agent portal stays blocked until approval.
export default function AgentRegistrationStatus() {
  const router = useRouter();
  const [data, setData] = useState<Registration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const outcome = await sendRequest(REGISTRATION_URL, { method: "GET" });
    if (!outcome.ok) { setError(outcome.message); return; }
    const value = outcome.data as Registration;
    if (value.org.status === "active") { router.replace("/overseas/agent/dashboard"); return; }
    setData(value);
  }, [router]);

  useEffect(() => { void load(); }, [load]);

  async function reupload(event: FormEvent<HTMLFormElement>, doc: AgentKycDoc) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    const problem = checkKycFile(doc.label, file instanceof File ? file : null);
    if (problem) { setNotes((n) => ({ ...n, [doc.doc_type]: problem })); return; }
    if (!String(form.get("doc_number") || "").trim()) form.delete("doc_number");
    setBusy(doc.doc_type);
    const outcome = await sendRequest(`${REGISTRATION_URL}/documents/${doc.doc_type}/file`, { method: "PUT", body: form });
    setBusy(null);
    setNotes((n) => ({ ...n, [doc.doc_type]: outcome.ok ? `${doc.label} uploaded. It will be reviewed again.` : outcome.message }));
    if (outcome.ok) await load();
  }

  if (error) return <p className="form-error" role="alert">{error}</p>;
  if (!data) return <p className="muted">Loading your registration…</p>;
  const rejectedOrg = data.org.status === "rejected";
  return (
    <div className="card">
      <h1 style={{ fontSize: "1.4rem" }}>{rejectedOrg ? "Registration rejected" : "Registration status"}</h1>
      <p>{data.org.name}</p>
      <p className="muted">
        {rejectedOrg
          ? "Your agency's registration was not approved. Contact EduSphere Overseas Admin if you think this is a mistake."
          : "EduSphere is reviewing your registration. You can use the agent portal once your agency is approved."}
      </p>
      {!data.org.kyc_required ? null : (
        <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 12 }}>
          {data.documents.map((doc) => {
            const spec = KYC_DOCS.find((d) => d.type === doc.doc_type)!;
            const canReplace = doc.status === "rejected" && !rejectedOrg;
            return (
              <li key={doc.id} className="card" style={{ overflowWrap: "anywhere" }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <strong>{doc.label}</strong> <span>{doc.doc_number_display}</span> <span className="badge">{STATUS_LABEL[doc.status]}</span>
                </div>
                {doc.status === "rejected" && doc.rejection_reason && <p style={{ fontSize: 13 }}>Reason: {doc.rejection_reason}</p>}
                {canReplace && (
                  <form onSubmit={(e) => reupload(e, doc)} style={{ display: "grid", gap: 8, marginTop: 8 }}>
                    <div className="field" style={{ margin: 0 }}>
                      <label htmlFor={`kyc-file-${doc.doc_type}`}>New {doc.label} file (PDF, JPG or PNG, max 5 MB)</label>
                      <input id={`kyc-file-${doc.doc_type}`} name="file" type="file" accept={KYC_ACCEPT} required />
                    </div>
                    <div className="field" style={{ margin: 0 }}>
                      <label htmlFor={`kyc-number-${doc.doc_type}`}>Corrected {spec.numberLabel} (optional)</label>
                      <input id={`kyc-number-${doc.doc_type}`} name="doc_number" pattern={spec.pattern} maxLength={spec.maxLength} inputMode={spec.inputMode} autoComplete="off" />
                    </div>
                    <button className="btn small" disabled={busy === doc.doc_type} aria-label={`Upload new ${doc.label}`}>{busy === doc.doc_type ? "Uploading…" : "Upload"}</button>
                  </form>
                )}
                <div role="status" aria-live="polite" style={{ fontSize: 13 }}>{notes[doc.doc_type]}</div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: The page and the pending link**

Create `apps/web/app/overseas/agent/registration-status/page.tsx`:

```tsx
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AgentRegistrationStatus from "@/components/AgentRegistrationStatus";
import { serverApi } from "@/lib/api";
import type { User } from "@/lib/types";

// AGN-024 (DEC-SCOPE-224 K5): reachable while the agency is pending or rejected; no portal navigation, since every other agent page
// is refused until approval.
export default async function Page() {
  let user: User;
  try { user = await serverApi<User>("/api/v1/auth/me"); } catch (e) { return accessUnavailable(e); }
  if (user.role !== "agent") return accessDenied(user, "Agent role required");
  return <div className="section"><div className="container" style={{ maxWidth: 720 }}><AgentRegistrationStatus /></div></div>;
}
```

Check the exact export names in `AccessUnavailable.tsx` (`accessDenied`, `accessUnavailable`) and `@/lib/types`, and copy the imports from `apps/web/app/overseas/admin/agent-deposits/page.tsx`.

In `apps/web/components/AccessUnavailable.tsx`, inside the button row of `AccessUnavailableCard`, before the dashboard/sign-in buttons, add:

```tsx
        {message === "Agent registration is pending approval" && home && <a className="btn" href="/overseas/agent/registration-status">View registration status</a>}
```

- [ ] **Step 5: Run the tests, typecheck and lint**

Run: `WEB_TEST "npx vitest run tests/components/AgentRegistrationStatus.test.tsx tests/components/AccessUnavailable.test.tsx && npx tsc --noEmit && npx eslint components app/overseas/agent"`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/AgentRegistrationStatus.tsx apps/web/app/overseas/agent/registration-status apps/web/components/AccessUnavailable.tsx apps/web/tests/components
git commit -m "feat(agn-024): registration status page with re-upload for a pending agency

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: E2E — migrate agent-registering specs, add the AGN-024 journey

**Files:**
- Modify: `apps/web/tests/e2e/helpers/agency.ts`, `apps/web/tests/e2e/agt-001-registration-approval.spec.ts`, `agn-001-multi-tenant.spec.ts`, `agn-004-agent-students.spec.ts`, `agt-002-referrals.spec.ts`, `mgmt-026-plans.spec.ts`
- Create: `apps/web/tests/e2e/agn-024-agent-kyc.spec.ts`

**Interfaces:**
- Produces (`helpers/agency.ts`):
  - `KYC_PDF`
  - `fillAgentKyc(page: Page): Promise<void>`
  - `kycMultipart(fields: Record<string, string>): Record<string, string | { name: string; mimeType: string; buffer: Buffer }>`
  - `verifyAllKyc(request: APIRequestContext, agency: string): Promise<void>` (caller must already be signed in as an admin in that request context)

- [ ] **Step 1: Helpers**

Append to `apps/web/tests/e2e/helpers/agency.ts`:

```ts
// AGN-024 (DEC-SCOPE-224): an agent signup carries PAN, Aadhaar and licence; approval needs all three verified.
export const KYC_PDF = { name: "kyc.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n") };
export const KYC_NUMBERS = { pan_number: "ABCDE1234F", aadhaar_last4: "1234", license_number: "LIC-2026/001" };

export async function fillAgentKyc(page: Page) {
  for (const [name, value] of Object.entries(KYC_NUMBERS)) await page.fill(`input[name="${name}"]`, value);
  for (const name of ["pan_file", "aadhaar_file", "license_file"]) await page.setInputFiles(`input[name="${name}"]`, KYC_PDF);
}

export function kycMultipart(fields: Record<string, string>) {
  return { ...fields, ...KYC_NUMBERS, pan_file: KYC_PDF, aadhaar_file: KYC_PDF, license_file: KYC_PDF };
}

export async function verifyAllKyc(request: APIRequestContext, agency: string) {
  const list = await (await request.get(`/api/v1/overseas-admin/agent-orgs?status=pending&q=${encodeURIComponent(agency)}`)).json();
  const org = list.items.find((o: { name: string }) => o.name === agency);
  expect(org, `pending org ${agency}`).toBeTruthy();
  const docs = await (await request.get(`/api/v1/overseas-admin/agent-orgs/${org.id}/kyc-documents`)).json();
  for (const doc of docs.items) expect((await request.post(`/api/v1/overseas-admin/agent-orgs/${org.id}/kyc-documents/${doc.id}/verify`)).ok()).toBeTruthy();
}
```

In `registerApprovedAgency`:
- after `selectOption(... "agent")` and filling the agency name, call `await fillAgentKyc(page);`
- change `waitForURL("**/overseas/agent/dashboard")` → `waitForURL("**/overseas/agent/registration-status")`
- after `signIn(...admin...)`, call `await verifyAllKyc(page.request, agency);` before `page.goto("/overseas/admin/agents")`

`page.request` shares the page's cookies, so it is now the admin session.

- [ ] **Step 2: Migrate the other specs**

For each of `agt-001-registration-approval.spec.ts`, `agn-001-multi-tenant.spec.ts`, `agn-004-agent-students.spec.ts`, `agt-002-referrals.spec.ts` and `mgmt-026-plans.spec.ts`:
- **UI registration** (`selectOption('select[name="account_type"]', "agent")`): add `await fillAgentKyc(page);` before clicking "Create account". Change the post-signup `waitForURL("**/overseas/agent/dashboard")` to `"**/overseas/agent/registration-status"`.
  - In `agt-001`'s first test (AGT-001-AC02), the pending agent who then visits `/overseas/agent/dashboard` must still see the pending message. Add `await page.goto("/overseas/agent/dashboard")` before the existing assertion if the spec relied on the redirect.
- **API registration** (`request.post("/api/v1/auth/register", { data: {...account_type: "agent"...} })`): change `data:` to `multipart: kycMultipart({...same string fields...})`.
- **Any approval of a freshly registered agency** (UI "Approve" click or API `/approve`): call `await verifyAllKyc(<admin request context>, <agency name>)` right before it. When the spec registered without an agency name, the org name is the agent's full name.

Find every site with:
`grep -n "account_type\|auth/register\|Approve\|/approve" apps/web/tests/e2e/{agt-001-registration-approval,agn-001-multi-tenant,agn-004-agent-students,agt-002-referrals,mgmt-026-plans}.spec.ts`

`apps/web/tests/doc-capture/s2-account-access.capture.ts` is docs tooling. Do not change it in this feature; record it as a follow-up in the final report.

- [ ] **Step 3: The AGN-024 journey spec**

Create `apps/web/tests/e2e/agn-024-agent-kyc.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

import { KYC_PDF, fillAgentKyc, signIn } from "./helpers/agency";

// AGN-024 (DEC-SCOPE-224): signup with three documents -> admin rejects Aadhaar -> agent re-uploads -> admin verifies all ->
// Approve enabled -> agent reaches the dashboard. A Super Admin variant covers K7; a 360 px check covers the signup form.

test("agent KYC journey: reject, re-upload, verify all, approve (AGN-024)", async ({ page }) => {
  const unique = Date.now();
  const email = `agn024-${unique}@example.local`;
  const agency = `KYC Agency ${unique}`;
  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "KYC Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await fillAgentKyc(page);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/registration-status");
  await expect(page.getByText("Pending review")).toHaveCount(3);

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`/overseas/admin/agents?q=${encodeURIComponent(agency)}`);
  const card = page.locator(".card", { hasText: agency });
  await expect(card.getByRole("button", { name: `Approve ${agency}` })).toBeDisabled();
  await card.getByRole("button", { name: `Reject Aadhaar card for ${agency}` }).click();
  await card.getByLabel("Reason for rejecting Aadhaar card").fill("Photo is blurred");
  await card.getByRole("button", { name: "Confirm reject" }).click();
  await expect(card.getByText("Reason: Photo is blurred")).toBeVisible();

  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard").catch(() => undefined);  // a pending agent lands on the access card
  await page.goto("/overseas/agent/registration-status");
  await expect(page.getByText("Reason: Photo is blurred")).toBeVisible();
  await page.getByLabel(/^New Aadhaar card file/).setInputFiles(KYC_PDF);
  await page.getByRole("button", { name: "Upload new Aadhaar card" }).click();
  await expect(page.getByText("Aadhaar card uploaded. It will be reviewed again.")).toBeVisible();

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`/overseas/admin/agents?q=${encodeURIComponent(agency)}`);
  for (const label of ["PAN card", "Aadhaar card", "Business licence"]) {
    await card.getByRole("button", { name: `Verify ${label} for ${agency}` }).click();
    await expect(card.getByText(`${label} verified.`)).toBeVisible();
  }
  await expect(card.getByRole("button", { name: `Approve ${agency}` })).toBeEnabled();
  await card.getByRole("button", { name: `Approve ${agency}` }).click();
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();

  await signIn(page, email, "Sup3r-Secret-Pass!");
  await expect(page).toHaveURL(/\/overseas\/agent\/dashboard/);
});

test("Super Admin sees Agent Approvals with the document review (AGN-024 K7)", async ({ page }) => {
  await page.goto("/admin/login");
  // use the seeded super admin credentials from demo-login-credentials / seed (check apps/api/app/seed.py for the email)
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  await page.getByRole("link", { name: "Agent Approvals" }).click();
  await expect(page.getByRole("heading", { name: "Agent Approvals" })).toBeVisible();
});

test("signup form with documents fits a 360 px screen (AGN-024)", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/overseas/register");
  await page.selectOption('select[name="account_type"]', "agent");
  await expect(page.getByLabel(/^PAN card/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
```

Before running, confirm the super admin's seeded email and the login page selectors (`grep -n "super_admin" apps/api/app/seed.py`, `apps/web/app/admin/login`), and adjust the second test to match. The pending agent's `signIn` lands on an access card rather than the dashboard, which is why it is wrapped. If `signIn` throws on the URL wait, sign in with the raw form steps instead.

- [ ] **Step 4: Run e2e**

Ask the user to bring up the worktree stack (they control docker), then run:
`WEB_TEST "npx playwright test tests/e2e/agn-024-agent-kyc.spec.ts tests/e2e/agt-001-registration-approval.spec.ts tests/e2e/agn-001-multi-tenant.spec.ts tests/e2e/agn-002*.spec.ts tests/e2e/agn-003-staff-permissions.spec.ts tests/e2e/agn-004-agent-students.spec.ts tests/e2e/agt-002-referrals.spec.ts tests/e2e/mgmt-026-plans.spec.ts"`
with `-e E2E_BASE_URL=http://host.docker.internal:<web port>`.
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web/tests/e2e
git commit -m "test(agn-024): e2e KYC journey; agent-registering specs upload documents and verify before approval

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Traceability docs and spec reconciliation

**Files:**
- Modify:
  - `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append after DEC-SCOPE-223 ~line 8774)
  - `docs/delivery/AGENT_CRM_BACKLOG.md` (add `### ang-024` after `### ang-022` ~line 753, and a row in §2)
  - `docs/architecture/API_CONTRACT.md` (add `## 12EK.` before `## 13. Traceability check`)
  - `docs/architecture/RBAC_MATRIX.md` (add `### 2.147` before section 3)
  - `docs/superpowers/specs/2026-10-17-agent-signup-kyc-design.md`

- [ ] **Step 1: Decision**

Copy the heading/field layout of DEC-SCOPE-223 and add `### DEC-SCOPE-224 — Agent signup KYC documents (AGN-024)`, with:
- Status: CONFIRMED by owner 2026-10-17 (Claude Code session)
- Evidence: owner request + answers K1–K8
- The K1–K8 table copied from spec §2
- The out-of-scope list copied from spec §4.8, marked NEEDS_CONFIRMATION

- [ ] **Step 2: Backlog**

Copy the layout of `### ang-022` and add `### ang-024 — Agent signup KYC documents (AGN-024)` with:
- AC01–AC10 copied from spec §7
- dependencies: AGN-001, AGN-009 (upload pattern)
- migration 0164, DEC-SCOPE-224, API §12EK, RBAC §2.147
- status "Built — feature/agn-024"

Add the matching row in the §2 summary table.

- [ ] **Step 3: API contract §12EK**

Add `## 12EK. Agent signup KYC documents (AGN-024) — addendum, 2026-10-17` documenting:
- `POST /auth/register` multipart (fields, 422/409/413/415 errors, JSON agent → 422)
- the six new routes, with request/response shapes as in Tasks 5–6
- the `kyc_required`/`kyc_summary` additions to `GET /overseas-admin/agent-orgs`
- the 409 approve gate
- the `/files/download` and `/local-files` refusal of `agent-kyc/`

- [ ] **Step 4: RBAC §2.147**

Add `### 2.147 Agent signup KYC documents *(added 2026-10-17 — DEC-SCOPE-224, AGN-024)*` with a matrix:

| Route | overseas_admin | super_admin | agent (active Master of own org) | agent staff | every other role | anonymous |
|---|---|---|---|---|---|---|
| GET/verify/reject/view admin KYC routes | ✓ | ✓ | 403 | 403 | 403 | 401 |
| GET /agent/registration | 403 | 403 | ✓ (pending, rejected or active org) | 403 | 403 | 401 |
| PUT /agent/registration/documents/{type}/file | 403 | 403 | ✓ only org pending + doc rejected (else 409) | 403 | 403 | 401 |

Then add the rules:
- the gate is in `set_org_status`
- KYC keys are never served via generic paths
- document numbers are never logged

- [ ] **Step 5: Reconcile the spec with the build**

In the spec, edit:
- **§4.4:** throttle = 20 re-uploads per agency per rolling 24 h (THROTTLE_WINDOW, the AGN-009 audit-window pattern) instead of 10 per hour. The status page has no portal navigation.
- **§4.6:** emails go through the existing Notification + `queue_deliveries` email outbox (ENH-014), not new mailer functions. They are queued in the same transaction, delivered after commit, and a delivery failure never affects the action.
- **§4.7:** no route-inventory matrix test covers `/overseas-admin` or `/agent` prefixes. Access is pinned by `test_agn_024_admin.py` and `test_agn_024_agent.py`.
- **§4.8:** add `tests/doc-capture/s2-account-access.capture.ts` (agent registration screenshots) as a follow-up.

- [ ] **Step 6: Re-check numbers against main, then commit**

```bash
git fetch origin
git show origin/main:docs/decisions/PRODUCT_DECISION_REGISTER.md | grep -c "DEC-SCOPE-224"   # expect 0
git ls-tree --name-only origin/main apps/api/alembic/versions/ | grep 0164                     # expect nothing
git add docs
git commit -m "docs(agn-024): DEC-SCOPE-224, ang-024 backlog item, API 12EK, RBAC 2.147, spec reconciled with the build

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

If either check finds a collision, re-chain (rename the migration and its `revision`, bump the decision, section and RBAC numbers), re-run the Task 1 migration test, and amend nothing. Make a new commit.

- [ ] **Step 7: Final lite verification**

Run: `API_TEST "tests/test_agn_024_migration.py tests/test_agn_024_service.py tests/test_agn_024_registration.py tests/test_agn_024_gate.py tests/test_agn_024_admin.py tests/test_agn_024_agent.py tests/test_agn_001_registration_and_gate.py tests/test_agn_001_org_admin.py tests/test_agn_001_tenancy.py tests/test_agt_001_registration_approval.py tests/test_agn_009_upload.py tests/test_enh_005_hardening.py"`
and `WEB_TEST "npx vitest run && npx tsc --noEmit && npx eslint ."`

Expected: all green. Report plainly that the full backend suite was not run (the user's standing choice), and list the lite files. Give the user `git push -u origin feature/agn-024` to run.
