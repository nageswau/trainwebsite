# tel-003 Lead Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every enquiry is a lead with a unique `LD-000001` Lead ID and the 12 EVID-019 §2 fields, and the admin lead list is paginated and filterable.

**Architecture:** One guarded migration adds the columns to `enquiries`. The Lead ID is a database default built on a sequence, and
`phone_normalized` is derived by a model validator, so every insert path is covered without caller changes. `/admin/leads` becomes a
`{items,total,limit,offset}` page that reuses the bdm list idioms. The panel reads the page from the API, with its state in the URL.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16, pytest; Next.js 15 / React 19, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-tel-003-lead-record-design.md`

## Global Constraints

- Lead ID default: `'LD-' || translate(format('%6s', nextval('enquiry_lead_code_seq')), ' ', '0')`; unique `uq_enquiries_lead_code`.
- Sources: exactly `app/tel_sources.TEL_SOURCES` (13); the migration keeps a frozen copy; legacy unknown → `other` + `metadata_json.legacy_source`.
- Priority `hot|warm|cold`, default `warm`; `passing_year` NULL or 1950–2100.
- List paging: `LIMIT = Query(50, ge=1, le=100)`, `OFFSET`, `SEARCH` from `app/api/bdm.py`; order `created_at desc, id desc`.
- Inline authorization only (`ensure_admin` + division `WHERE`); no `require_*` dependencies.
- Logs and audit carry ids only — never name, email, phone.
- No change to `PATCH /admin/leads/{id}` or the conversion routes' behaviour.
- Tests run in the `tel003` compose project (`api-test` / `web-test` containers, Windows-form mount path).

## Review Focus

1. Lead codes past `LD-999999` must keep growing (`LD-1000000`), never truncate → covered in Task 1 (an expression test with `setval`).
2. An admin filtering by another division's telecaller/product must see nothing outside their division → Task 3 test.
3. Search text containing `%` or `_` is literal → Task 3 test.
4. Editing a lead's phone re-derives `phone_normalized` → Task 2 test.
5. Paging past the end returns an empty `items` with the true `total` → Task 3 test.

---

### Task 1: Model columns + migration 0077 (AC1, AC4, AC5, L2)

**Files:**
- Modify: `apps/api/app/models.py` (Enquiry; `ENQUIRY_LEAD_CODE_SEQ`; `LEAD_PRIORITIES`)
- Create: `apps/api/alembic/versions/0078_enquiry_lead_record.py`
- Test: `apps/api/tests/test_tel_003_migration.py`, `apps/api/tests/test_tel_003_lead_code.py`

**Interfaces — Produces:** `Enquiry.lead_code`, `.phone_normalized`, `.whatsapp_number`, `.city`, `.state`, `.qualification`,
`.passing_year`, `.institution`, `.product_id`, `.campaign_id`, `.telecaller_user_id`, `.priority`, `.stage_changed_at`;
`models.LEAD_PRIORITIES = ("hot", "warm", "cold")`; `models.LEAD_CODE_DEFAULT` (the SQL text).

- [ ] Step 1: Write `test_tel_003_migration.py` (pattern: `test_bdm_017_migration.py`, throwaway DB): the chain `0076 → 0077` with a single
  head; upgrade on a DB holding legacy rows (`source` values `'Website'`, `'facebook ads'`, `'bdm'`; phones `'98765 43210'`, `'12'`,
  NULL) → codes `LD-000001..3` oldest-first, the next insert gets `LD-000004`; sources `website`, `other` (+`legacy_source`), `bdm`;
  phones `+919876543210`, NULL, NULL; `stage_changed_at = created_at`; downgrade with a `city` set → RuntimeError; a clean downgrade
  restores `'facebook ads'`; the model's CHECK strings match the migration's.
- [ ] Step 2: Write `test_tel_003_lead_code.py`: a direct `Enquiry(...)` insert gets `^LD-\d{6,}$`; 20 concurrent inserts (separate
  sessions, `asyncio.gather`) → 20 distinct codes; `SELECT 'LD-' || translate(format('%6s', 1234567::bigint), ' ', '0')` = `LD-1234567`;
  a source outside the list raises IntegrityError; priority defaults to `warm`.
- [ ] Step 3: Run both → FAIL (no revision file / no column).
- [ ] Step 4: Implement the model columns (spec §3) with `__mapper_args__ = {"eager_defaults": True}`, the sequence on the metadata,
  and the migration: guarded upgrade (skip when `lead_code` exists), the ordered steps of spec §3, a frozen `_normalise_phone` copy,
  and a downgrade guard.
- [ ] Step 5: Run `alembic upgrade head` + both tests + `test_bdm_017_migration.py` → PASS.
- [ ] Step 6: Commit `feat(tel-003): enquiries lead record columns, LD- Lead ID, migration 0077`.

### Task 2: Public intake + phone validator + CRM payload (AC2, edge)

**Files:** Modify `app/models.py` (`@validates("phone")`), `app/schemas.py` (`EnquiryIn.source: TelSource`), `app/api/public.py`,
`app/worker.py`. Test `tests/test_tel_003_intake.py`.

- [ ] Step 1: Tests: POST returns 201 with keys `{id,status,crm_sync_status,lead_code}`; `source="tiktok"` → 422 and no row; a phone
  `"098765 43210"` → `phone_normalized="+919876543210"`; updating `phone` on a loaded row re-derives it; the CRM payload captured from
  `sync_crm_enquiry` (monkeypatched) includes `lead_code`; a BDM lead (`add_lead`) gets a code and a normalised phone.
- [ ] Step 2: Run → FAIL.
- [ ] Step 3: Implement (`from app.notifications.phone import normalise_phone`; the validator sets `self.phone_normalized`).
- [ ] Step 4: Run + `test_pub_002_enquiry_crm.py` + `test_bdm_017_leads.py` → PASS.
- [ ] Step 5: Commit `feat(tel-003): website enquiries return lead_code; source list enforced; CRM payload adds lead_code`.

### Task 3: Paginated, filterable admin lead list (AC3, AC4)

**Files:** Modify `app/api/admin.py` (`leads`), `app/services/bdm_leads.py` (`admin_rows`, `admin_out`). Test
`tests/test_tel_003_admin_leads.py`; update `tests/test_adm_002_lead_management.py`, `tests/test_bdm_017_conversion.py` to read `["items"]`.

- [ ] Step 1: Tests: the page shape; `limit=101` → 422; `offset` past the end → empty items, true total; filters `status`, `source`,
  `product_id`, `campaign_id`, `telecaller_user_id`, `bdm_organization_id`, `q` (by Lead ID, phone, literal `%`); an it_admin
  filtering by an overseas telecaller's id sees 0; a row carries the new keys and the objects `product`, `campaign`, `telecaller`,
  `counselor`; super_admin `division=` still narrows; the conversion answer contains `lead_code`.
- [ ] Step 2: Run → FAIL.
- [ ] Step 3: Implement (count with the same filters; the join list in `admin_rows`).
- [ ] Step 4: Run + adm-002 + bdm-017 conversion/leads + cns-001 + rpt-001 → PASS.
- [ ] Step 5: Commit `feat(tel-003): /admin/leads paginated with stage/product/campaign/telecaller/source/search filters`.

### Task 4: Admin panel + module table (AC3 UI)

**Files:** Modify `apps/web/components/AdminLeadManagementPanel.tsx`, `apps/web/app/admin/[module]/page.tsx`,
`apps/web/lib/telecallerCatalogue.ts` (`activeCampaigns`, shared `readAll`). Test `apps/web/tests/components/AdminLeadManagementPanel.test.tsx`.

- [ ] Step 1: vitest: the request URL carries the URL filters + `limit=50&offset=`; the columns render Lead ID / Source · Campaign /
  Telecaller / Priority; changing Stage pushes `?status=`; the search submits `?q=`; the pager appears only when `total > 50`;
  load error → "Unable to load leads." + Retry; empty → "No leads found."; a filtered empty → "No leads match these filters.";
  the existing status-update and link tests still pass with the page shape.
- [ ] Step 2: Run → FAIL. Step 3: Implement. Step 4: vitest + tsc + eslint → PASS.
- [ ] Step 5: Commit `feat(tel-003): admin lead panel pages and filters through the API`.

### Task 5: E2E

**Files:** Update `apps/web/tests/e2e/pub-002-enquiry.spec.ts` (`.items` + `q=`), `adm-002-lead-management.spec.ts`,
`bdm-017-lead-attribution.spec.ts` (the organization filter); create `apps/web/tests/e2e/tel-003-lead-record.spec.ts` (submit the website form →
the admin sees `LD-` in the list, filters by Source and searches by Lead ID; mobile 390px has no page overflow).

- [ ] Run the specs against `http://host.docker.internal:3073` → PASS. Commit `test(tel-003): e2e`.

### Task 6: Docs

`PRODUCT_DECISION_REGISTER.md` DEC-SCOPE-077; the API contract for `/admin/leads` + public enquiries; backlog tel-003 status; RBAC
unchanged note; screen catalog; QA log in the spec §9. Commit `docs(tel-003): ...`.
