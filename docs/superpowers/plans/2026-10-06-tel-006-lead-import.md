# tel-006 CSV Lead Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A telecaller manager uploads a CSV of leads for one campaign; each row is created, attached to a known person's lead, or rejected with its line and reason.

**Architecture:** A new router `api/telecaller_import.py` reuses ENH-028's bounded upload/CSV parser (`school_bulk._read_upload`, `_read_csv`) and tel-005's intake helpers through one new service function `lead_intake.import_row`. One transaction per upload with a SAVEPOINT per row; `lead_import_batches` stores counts and per-row outcomes (no PII) and gives Idempotency-Key replay. A manager page `/telecaller/manager/imports` hosts the upload panel and the history table.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL; Next.js 15 / React client components, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-tel-006-lead-import-design.md`

## Global Constraints

- Migration `0087_lead_import_batches`, `down_revision = "0086_lead_enquiries"`; decision `DEC-SCOPE-091`; API contract §12N.
- Max 1 MB (`school_bulk.MAX_FILE_BYTES`), max 500 filled-in rows, columns exactly: `name, phone, email, whatsapp_number, city, state, qualification, passing_year, institution, priority, subject, message`; required `name`, `phone`.
- Roles: `telecaller_manager`, `super_admin` only (`services.telecaller.require_manager`).
- Never store the file, names, phones or emails in the batch, logs or audit rows (R9).
- Created leads: queue `sync_enquiry_to_crm_task` after commit; attached rows queue nothing.

## Review Focus

- A file whose second row is the same person as the first row → the second attaches to the lead the first created (test in Task 2).
- A cell with only whitespace in an optional column (e.g. `passing_year`) → treated as empty, not a 422 (`_read_csv` trims; blanks dropped before validation; test in Task 2).
- A UTF-8 BOM / Excel-saved file → parsed (`utf-8-sig`), headers case-insensitive (test in Task 2).
- An `other` product without a team and no `division` → 422 before any row; with `division` → leads in that team (test in Task 2).
- Double-click on Upload → one request (the `inFlight` ref) and one Idempotency-Key per chosen file+campaign (vitest in Task 4).

---

### Task 1: Migration, model, migration test

**Files:**
- Create: `apps/api/alembic/versions/0087_lead_import_batches.py`
- Modify: `apps/api/app/models.py` (append `LeadImportBatch` after `LeadEnquiry`)
- Test: `apps/api/tests/test_tel_006_migration.py`

**Interfaces:** Produces `app.models.LeadImportBatch` with columns `id, campaign_id, division, uploaded_by_user_id, idempotency_key, file_sha256, total_rows, created_count, attached_count, rejected_count, results_json, created_at, updated_at`.

- [ ] Step 1: write `test_tel_006_migration.py` (tel-005 idiom): chain/one-head test; model-matches-migration column set test; round-trip in a throwaway DB (upgrade head → table exists with unique + checks; downgrade to `0086_lead_enquiries` → table gone; upgrade again).
- [ ] Step 2: run → FAIL (file missing).
- [ ] Step 3: model:

```python
class LeadImportBatch(Base, TimestampMixin):
    """tel-006 (DEC-SCOPE-091, IM1): one CSV lead import for a campaign. The file is never stored (R9): only its hash, the counts and each
    row's outcome {row_number, status, lead_id, error} -- no names, phones or emails. The Idempotency-Key is scoped to the uploader (R8)."""

    __tablename__ = "lead_import_batches"
    __table_args__ = (
        UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_lead_import_batches_key"),
        CheckConstraint("division IN ('it', 'overseas')", name="ck_lead_import_batches_division"),
        CheckConstraint("created_count + attached_count + rejected_count = total_rows", name="ck_lead_import_batches_counts"),
        Index("ix_lead_import_batches_uploader", "uploaded_by_user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tel_campaigns.id"))
    division: Mapped[str] = mapped_column(String(20))
    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    file_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    attached_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    results_json: Mapped[list] = mapped_column(JSON, default=list)
```

- [ ] Step 4: migration with the same columns (`server_default` 0 / `'[]'` / `now()`), guarded upgrade (`has_table` → return, 0086 idiom), downgrade drops index + table.
- [ ] Step 5: run migration test → PASS. Commit.

### Task 2: Import service + upload route + template

**Files:**
- Modify: `apps/api/app/schemas.py` (append `LeadImportRow` after `LeadEnquiryCreate`)
- Modify: `apps/api/app/services/lead_intake.py` (add `lead_team`, `import_row`; `create_lead` uses `lead_team`)
- Create: `apps/api/app/api/telecaller_import.py`
- Modify: `apps/api/app/main.py` (import + router tuple)
- Test: `apps/api/tests/test_tel_006_import.py`

**Interfaces:**
- `schemas.LeadImportRow(name, phone, email=None, whatsapp_number=None, city=None, state=None, qualification=None, passing_year=None, institution=None, priority="warm", subject=None, message=None)` — tel-005 field types, `extra="forbid"`.
- `lead_intake.lead_team(product: TelProduct, division: str | None) -> str` (422 messages unchanged from `create_lead`).
- `lead_intake.import_row(db, user, campaign: TelCampaign, product: TelProduct, division: str, row: LeadImportRow, batch_id: UUID) -> tuple[Enquiry, bool]`.
- Routes `GET /telecaller/imports/template`, `POST /telecaller/imports` → report dict `{id, campaign: {id, name}, division, total_rows, created_count, attached_count, rejected_count, created_at, rows: [{row_number, status, lead_id, lead_code, error}]}`.

Tests (each with fresh mobiles/emails; helpers `make_tl_manager`, `make_telecaller`, `as_user` from tel-004/bdm-017 helpers):
1. manager uploads 3 valid rows → 201, `created_count == 3`; each lead has campaign/source/product/division, `metadata_json["import_batch_id"]`; with an active IT telecaller reporting to the manager the leads are distributed (`telecaller_user_id` set) — otherwise unassigned `new`.
2. a row whose phone (other formatting) matches an existing lead → `attached`, a `LeadEnquiry` with campaign source/id, uploader, batch id; no new `Enquiry`.
3. two rows with the same email in one file → row 2 `attached` to the lead row 1 created.
4. invalid rows (bad mobile, missing name, bad priority, passing_year 1800) → `rejected` with `row_number` = file line and an error naming the field; valid rows still created; `results_json` contains no name/phone/email strings.
5. wrong/unknown/missing header → 422, no batch row; > 500 rows → 422; > 1 MB → 413; empty → 422; BOM + `Name,PHONE` headers → 201.
6. inactive campaign → 422 "Choose an active campaign"; `other` product without team: no division → 422, with `division=it` → created in `it`.
7. same key + same file → same report, no new leads; same key + different file → 422 `Idempotency-Key was already used for a different file`; missing key → 422.
8. telecaller → 403, counselor → 403, anonymous → 401; template returns the 12 columns as `text/csv`.
9. one audit row `lead.import` with counts; CRM task queued once per created lead (monkeypatch `sync_enquiry_to_crm_task.delay`).

- [ ] Steps: write tests → run (FAIL 404) → implement (code below) → run PASS → run tel-005 intake/public tests → commit.

```python
# services/lead_intake.py
def lead_team(product: TelProduct, division: str | None) -> str:
    """tel-005 R5 / tel-006 R2: the product's team, or the chosen division for an `other` product without one."""
    if product.team and division and division != product.team:
        raise HTTPException(422, f"{product.name} belongs to the {TEAM_LABEL[product.team]} team")
    team = product.team or division
    if team is None:
        raise HTTPException(422, "Choose the division (IT or Overseas) for this product")
    return team


async def import_row(db, user, campaign, product, division, row, batch_id) -> tuple[Enquiry, bool]:
    phone_key, email_key = identity(row.phone, row.email)
    await lock_identity(db, phone_key, email_key)
    known = await matching_leads(db, phone_key, email_key, limit=1)
    subject, message, trace = row.subject or product.name, row.message or "", {"import_batch_id": str(batch_id)}
    if known:
        db.add(LeadEnquiry(lead_id=known[0].id, subject=subject, message=message, source=campaign.source, campaign_id=campaign.id,
                           metadata_json=trace, created_by_user_id=user.id))
        await db.flush()
        return known[0], True
    lead = Enquiry(**row.model_dump(exclude={"subject", "message"}), division=division, product_id=product.id, campaign_id=campaign.id,
                   source=campaign.source, subject=subject, message=message, metadata_json=trace)
    db.add(lead)
    await db.flush()
    await lead_distribution.on_intake(db, lead)
    return lead, False
```

Phase 3 review additions: (a) a global `pg_advisory_xact_lock(LOCK_KEY)` after the claim serialises imports — two files naming the same people in different orders would otherwise deadlock on the per-person locks, and it bounds advisory locks held by imports to ≤ 1000; a wait past `lock_timeout` → 409 `IN_PROGRESS`. (b) In a row's savepoint, `DBAPIError` with sqlstate `55P03` (lock timeout) or `40P01` (deadlock with a concurrent manual/website intake) rejects only that row with `ROW_CONFLICT`.

Route: `require_manager` → `_read_upload` → `_read_csv(known=COLUMNS, required=("name","phone"), max_rows=500)` → `SET LOCAL lock_timeout` → campaign FOR SHARE (active) + `locked_active_product` + `lead_team` → claim (savepoint insert; IntegrityError → replay if `(sha, campaign_id, division)` match, else 422 `KEY_REUSED`; lock timeout → 409 `IN_PROGRESS`) → rows (pydantic → `validation_message`; savepoint per row; `DBAPIError` lock timeout → `ROW_CONFLICT`) → counts + `results_json` + audit → commit → CRM tasks → `_report`.

### Task 3: History + report routes

**Files:** Modify `apps/api/app/api/telecaller_import.py`; Test `apps/api/tests/test_tel_006_import.py`.

**Interfaces:** `GET /telecaller/imports?limit&offset` → `{items: [{id, campaign: {id, name}, division, uploaded_by: {id, full_name}, total_rows, created_count, attached_count, rejected_count, created_at}], total, limit, offset}` newest first; manager → own; super_admin → all. `GET /telecaller/imports/{id}` → report; other manager's → 404 "Import not found".

- [ ] Tests: own batch listed, other manager's not; super_admin sees both; detail 404 for other manager; telecaller 403. → FAIL → implement → PASS → commit.

### Task 4: Web library + upload panel + history (vitest)

**Files:**
- Create: `apps/web/lib/telecallerImport.ts` (URLs, `IMPORT_COLUMNS: BulkColumn[]`, types `ImportRow`, `ImportReport`, `ImportSummary`)
- Create: `apps/web/components/TelecallerLeadImportPanel.tsx`
- Create: `apps/web/components/TelecallerImportHistory.tsx`
- Test: `apps/web/tests/components/TelecallerLeadImportPanel.test.tsx`, `apps/web/tests/components/TelecallerImportHistory.test.tsx`

Panel behaviour (vitest): campaign select lists active campaigns (load error → Retry); Division select appears only for a campaign whose product group is `other`; precheck (no campaign / no file / not .csv / > 1 MB) shows `role="alert"` without fetching; upload posts FormData (`file`, `campaign_id`, `division`) with `Idempotency-Key`; a retry of the same file+campaign reuses the key, choosing a file again or another campaign makes a new key; double click → one fetch; 422 shows the server detail; network error shows the retry text; the report shows the summary and a row table (Row, Result, Lead ID, Detail) and focuses its heading; `onImported` is called. History: loading → rows; empty text; error + Retry; reloads when `version` changes.

### Task 5: Page, nav, Playwright

**Files:**
- Create: `apps/web/app/telecaller/manager/imports/page.tsx`
- Modify: `apps/web/lib/navigation.ts` (`{ label: "Lead import", href: "/telecaller/manager/imports" }` after Lead assignment)
- Create: `apps/web/tests/e2e/tel-006-lead-import.spec.ts`

E2E: super_admin creates a manager + IT telecaller and a campaign via API; manager signs in at `/admin/login`, opens Lead import, picks the campaign, uploads a 3-row file (new, duplicate of an existing lead, invalid mobile) → summary "1 created, 1 attached, 1 rejected"; table shows the line number and reason; history lists the batch; a telecaller visiting `/telecaller/manager/imports` sees access denied; mobile width has no side scroll; no console errors.

### Task 6: Docs

- `docs/decisions/PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-091` (IM1 + R1–R12).
- `docs/architecture/API_CONTRACT.md`: §12N.
- `docs/delivery/TELECALLER_CRM_BACKLOG.md`: tel-006 status line; §5.4 numbering note.
