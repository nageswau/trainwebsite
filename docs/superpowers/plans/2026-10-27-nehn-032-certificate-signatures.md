# nehn-032 Certificate Signatures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Founder + Coordinator signature images, names and designations on every newly issued certificate, managed by `certificates.manage`.

**Architecture:** A versioned `certificate_signatories` table; admin routes in `api/admin.py`; the ReportLab renderer in
`services/certificates.py` takes a `signatories` list and draws two slots; `_issue_certificate` refuses (409) without both and snapshots them.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, ReportLab + Pillow (already a reportlab dependency), Next.js client component, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-27-nehn-032-certificate-signatures-design.md`

## Global Constraints

- Numbering: DEC-SCOPE-300, migration `0207_certificate_signatories` (down_revision `0204_certificate_workflow`), API §12GX, RBAC §2.211.
- Slots: `founder`, `coordinator`. Name/designation 1–120 chars. Image 50–2000 px wide, 20–1000 px high, PNG with alpha, ≤ 1 MB.
- Image keys `signatures/<uuid32>.png`; never presigned; image route sends `Cache-Control: no-store`.
- Refusal copy: issue/preview without both slots → 409 `"Certificate signatures are not configured: <missing roles>"`.

## Review Focus

- A JPEG renamed `.png` / declared `image/png` → 415 (magic bytes) — test in Task 2.
- An opaque (RGB) PNG → 422 "transparent background" — Task 2.
- A very wide image (2000×20) still fits its 170×50 box — renderer test asserts scaled box within slot, Task 1.
- A student or coordinator calling the image route → 403 — Task 2.
- Bulk issue while a slot is empty → each item fails 409, nothing created — Task 3.

---

### Task 1: Model, migration, renderer slots

**Files:** Modify `apps/api/app/models.py`, `apps/api/app/services/certificates.py`, `apps/api/app/core/rbac.py`; Create
`apps/api/alembic/versions/0207_certificate_signatories.py`; Test `apps/api/tests/test_nehn_032_certificate_signatures.py`,
`apps/api/tests/test_nehn_032_migration.py`.

**Interfaces — Produces:**
- `CertificateSignatory` model (fields per spec S2); `Certificate.signatory_snapshot: dict | list | None` (JSON, nullable).
- `SIGNATORY_ROLES = ("founder", "coordinator")` in `services/certificates.py`.
- `generate_certificate_pdf(*, ..., signatories: list[CertificateSignatory]) -> str` (stores, returns URL as before);
  `render_certificate_pdf(*, certificate_no, student_name, program_title, issued_on, verification_code, signatories) -> bytes` (no storage).
- `active_signatories(db) -> list[CertificateSignatory]` ordered founder, coordinator; `missing_signatories(rows) -> list[str]`.
- `signatory_snapshot(rows) -> list[dict]` → `[{id: str, role, display_name, designation}]`.

- [ ] Tests: `render_certificate_pdf` with two signatories → PDF bytes contain both names, designations and two image XObjects
  (`/Subtype /Image` count == 2); a 2000×20 image renders without error; `rbac.parse_key("certificates.manage")` succeeds; migration
  test upgrade/downgrade round trip leaves the table/column present/absent.
- [ ] RED, implement, GREEN.

### Task 2: Admin signatory routes

**Files:** Modify `apps/api/app/api/admin.py`, `apps/api/app/schemas.py`. Test file from Task 1.

**Interfaces — Produces:** routes per spec "API"; `MANAGE_CERTIFICATES = require_permission("certificates", "manage", "You do not have permission to manage certificate signatures")`.
`check_signature_image(data: bytes) -> None` in `services/certificates.py` raising `HTTPException(422, ...)`.

- [ ] Tests: super_admin upload founder → 201, previous active row gets `active_to`; JPEG → 415; RGB PNG → 422; 10×10 PNG → 422;
  it_admin/coordinator/it_student → 403 on every route; PATCH name → 200, PATCH an inactive row → 409; image route returns PNG bytes
  with `no-store`; preview returns `application/pdf`; preview with a slot closed → 409; audit rows written.
- [ ] RED, implement, GREEN.

### Task 3: Issue uses signatories + seed

**Files:** Modify `apps/api/app/api/workflows.py` (`_issue_certificate`), `apps/api/app/seed.py`. Test file from Task 1.

- [ ] Tests: coordinator issue → certificate `signatory_snapshot` has founder then coordinator with the active ids; replace founder →
  next issue snapshots the new id, earlier certificate unchanged; with a slot closed → single issue 409 and bulk issue reports 409 per item
  and creates nothing (restore the slot after).
- [ ] Seed: when a slot has no active row, generate a transparent PNG (Pillow, script-like text) and insert "Demo Founder / Founder &
  Director", "Nisha Coordinator / IT Coordinator".
- [ ] RED, implement, GREEN; run existing certificate suites (adm-006, nehn-031, stu-007, enh-021, nehn-003, rec-036, nehn-005/030).

### Task 4: Web panel

**Files:** Create `apps/web/components/AdminCertificateSignatoriesPanel.tsx`; Modify `apps/web/components/WorkflowPanel.tsx`
(render when `isAdmin && section === "certificates"` and permissions include `certificates.manage`), `apps/web/lib/certificates.ts`
(`CertificateSignatory` type). Test `apps/web/tests/components/nehn032CertificateSignatures.test.tsx`, e2e
`apps/web/tests/e2e/nehn-032-certificate-signatures.spec.ts`.

- [ ] Vitest: loading text; both slots listed with image `alt="<name> signature"`; empty slot shows "No signature uploaded"; upload posts
  multipart and shows success; server error shows `role=alert`.
- [ ] e2e: super_admin uploads a PNG for founder, sees the new image, opens preview (200 application/pdf); it_admin does not see the card.

### Task 5: Docs

API_CONTRACT §12GX, RBAC_MATRIX §2.211, DATA_MODEL, PRODUCT_DECISION_REGISTER DEC-SCOPE-300, RTM, backlog status, FEEDBACK_TRACKER.
