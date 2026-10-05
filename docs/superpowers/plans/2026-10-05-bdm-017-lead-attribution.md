# bdm-017 Lead Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (owner chose in-session execution). Steps use
> checkbox (`- [ ]`) syntax for tracking. TDD per behavior: RED (write, run, see the expected failure) → GREEN → REFACTOR.

**Goal:** BDM-entered student leads stored as attributed `enquiries` rows, visible on the organization profile and the admin lead
list, with an explicit admin conversion link to one student account.

**Architecture:** Additive columns on `enquiries` (migration `0072`), a new BDM router/service pair mirroring bdm-009
(`load_scoped` scope, organization row lock, one commit per write, audit in the same transaction), additive changes to
`admin.leads` plus two conversion routes, and React components reusing the bdm-009 timeline and `lib/apiErrors`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, PostgreSQL; Next.js/React, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-bdm-017-lead-attribution-design.md`

## Global Constraints

- No new dependencies. No change to `public.create_enquiry`, `EnquiryIn`, `update_lead`'s field allow-list, the CRM payload, or
  the admin count queries (L4, L7).
- Existing `GET /admin/leads` keys, cap (500) and ordering unchanged; new keys only.
- Logs/audit: ids, route, status, counts — never name/email/phone/interest/note.
- Lite tests only in this session (owner runs full suites). Backend runs in the `bdm017` compose project
  (`api-test` image, source bind-mounted).

## Review Focus

1. Website enquiry posted with smuggled `bdm_organization_id`/`converted_user_id` keys → stored NULL (Task 1/2 test).
2. Two admins linking two leads to the same student at once → one 200, one 409, never a 500 (Task 4 race test).
3. Archived organization: list still readable, add refused 422; leads kept (Task 3).
4. Email case: `Asha@X.com` vs `asha@x.com` is a duplicate in the same organization; conversion lookup is case-insensitive (Tasks 3, 4).
5. CRM broker down at enqueue → 201 and lead `pending`, not 500 (Task 3).

---

### Task 1: Migration + model columns
**Files:** Create `apps/api/alembic/versions/0073_enquiry_bdm_attribution.py`; Modify `apps/api/app/models.py` (`Enquiry`);
Test `apps/api/tests/test_bdm_017_migration.py`.
- [ ] RED: tests — chains after `0072_bdm_meeting_reports` and is the single head; model columns/constraints/indexes/FK ondelete match;
  columns exist in the shared DB; isolated DB round trip (upgrade → downgrade with no attributed rows) and downgrade refusal
  when a row is attributed (bdm-009 migration test pattern).
- [ ] GREEN: migration (guarded `add_column`s, two CHECKs, index, partial unique index; downgrade refusal) + model columns.
- [ ] Run `alembic upgrade head` on the shared test DB; tests pass.

### Task 2: Schemas
**Files:** Modify `apps/api/app/schemas.py` (after the bdm-009 block); Test `apps/api/tests/test_bdm_017_schemas.py`.
**Produces:** `BdmLeadCreate`, `BdmLeadOut`, `BdmLeadPage`, `AdminLeadConversionIn`.
- [ ] RED: extra field → error; blank name/interest → "is required"; bad email → "Enter a valid email address"; email lowered;
  phone shape; lengths (160/255/40/180/5000); note keeps line breaks; `acknowledge_duplicate` strict bool.
- [ ] GREEN: types built from `_trimmed`, `_BDM_CONTROL`, `_BDM_MULTILINE_CONTROL`, `_EMAIL_SHAPE`, `_BDM_PHONE` with a
  `BDM_LEAD_LABELS` map.

### Task 3: BDM routes + service
**Files:** Create `apps/api/app/services/bdm_leads.py`, `apps/api/app/api/bdm_leads.py`; Modify `apps/api/app/main.py`;
Create `apps/api/tests/bdm017_helpers.py`, `apps/api/tests/test_bdm_017_leads.py`, `apps/api/tests/test_bdm_017_scope.py`.
**Produces:** `svc.page(db, org_id, limit, offset)`, `svc.create(...)`, `ORG_LEADS(org_id)` helper URL.
- [ ] RED (scope): other type 404; non-assignee BDM 403; manager/super_admin POST 403 (`bdm_context`); manager reads team org
  200; other role 403; archived → 422 on POST, 200 on GET.
- [ ] RED (leads): create → 201 with server fields (source `bdm`, division by type, attribution); list newest first; exact
  `total` across pages and only this organization (AC4); duplicate 409 shape then acknowledge 201; case-insensitive duplicate;
  cap 409 (monkeypatched cap); CRM enqueue called after commit; enqueue failure → 201 + `pending`; audit row without PII.
- [ ] GREEN, then REFACTOR against bdm-009 idioms.

### Task 4: Admin list + conversion
**Files:** Modify `apps/api/app/api/admin.py` (`leads`, new conversion routes); Create `apps/api/tests/test_bdm_017_conversion.py`.
- [ ] RED: admin list has `organization`/`bdm`/`converted_user` (null for website rows; AC1/AC2); filter narrows and stays
  division-scoped; public enquiry with smuggled keys → NULLs; PATCH with smuggled keys → NULLs.
- [ ] RED (conversion): link → 200 + status converted + audit; already linked 409; invalid target (missing / inactive / wrong
  role / wrong division) one 422; other division 403; missing lead 404; same student to second lead 409; concurrent links → 200
  + 409; unlink → 200, status kept; unlink not linked 409; non-admin 403.
- [ ] GREEN, REFACTOR.

### Task 5: Frontend lib + organization leads section
**Files:** Create `apps/web/lib/bdmLeads.ts`, `apps/web/lib/bdmLeadsServer.ts`, `apps/web/components/BdmOrganizationLeads.tsx`,
`apps/web/components/BdmLeadForm.tsx`; Modify `BdmOrganizationDetail.tsx`, both `organizations/[id]/page.tsx`;
Tests `apps/web/tests/components/BdmOrganizationLeads.test.tsx`, `BdmLeadForm.test.tsx`.
- [ ] RED: empty / list / load error + retry / load more; Add lead only when `canAdd`; field 422 shown on its field; duplicate
  409 → matches + Save anyway resends with `acknowledge_duplicate`; network loss keeps entry; saved → `onNotice("Lead added.")`.
- [ ] GREEN, REFACTOR.

### Task 6: Admin panel
**Files:** Modify `apps/web/components/AdminLeadManagementPanel.tsx`; Test `apps/web/tests/components/AdminLeadManagementPanel.test.tsx`.
- [ ] RED: Organization column (Website for null); filter narrows rows; Link student posts email and shows the student;
  422 message in the row; Unlink returns the row to unlinked.
- [ ] GREEN, REFACTOR.

### Task 7: Playwright + docs
**Files:** Create `apps/web/tests/e2e/bdm-017-lead-attribution.spec.ts`; Modify `docs/decisions/PRODUCT_DECISION_REGISTER.md`
(`DEC-SCOPE-071`), RTM, `docs/architecture/DATA_MODEL.md` / `API_CONTRACT.md` entries.
- [ ] Spec written (BDM adds lead → admin filters → links → unlink), run when the browser stack is up.
- [ ] Lite regression: `test_pub_002`, `test_adm_002`, `test_cns_001`, `test_rpt_001`, bdm-002/009 scope; Vitest for touched
  components; `tsc`, eslint, ruff.
- [ ] Not claimed complete: browser validation and independent Codex review remain.
