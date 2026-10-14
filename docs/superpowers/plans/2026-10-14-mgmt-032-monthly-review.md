# mgmt-032 Monthly Business Review Implementation Plan

> Executed inline (the owner's standing instruction for feature sessions). TDD per task: failing test → minimal code → green.

**Goal:** a partner-only monthly review: drafted by beat on the 1st (IST), frozen snapshot of §32 sections 1–8 + §10's computed
parts, partner narrative (§9, §10), finalise (immutable, partners emailed a link), on screen + PDF.
**Architecture:** one `monthly_reviews` row per month; `services/monthly_review.py` composes existing services; routes in
`api/management_reviews.py`; pure `reporting/pdf.render_monthly_review`; Next.js server pages + one client editor.
**Spec:** `docs/superpowers/specs/2026-10-14-mgmt-032-monthly-review-design.md` (MR1–MR14).

## Global Constraints
- Partner only on every route (MR1). Money as Decimal strings (2 dp) like the other management schemas. Days are IST.
- No new metric definitions: every figure is an existing service's figure. No new dependency.
- Numbers: migration `0163_monthly_reviews`, `DEC-SCOPE-220`, API §12EH, RBAC §2.145 (re-check main before writing docs).

## Review Focus
- Two partners saving narrative while the other finalises → row lock; the loser gets 409 (test in Task 2).
- A month in the future / current month / malformed → 422 / 422 / 422 path pattern (Task 2).
- Narrative with markup (`<b>`, `&`) reaches the PDF escaped and the screen as text (Task 3, Task 5).
- Beat rerun the same day → no second row, no overwrite of a draft's narrative (Task 2).
- Empty month (no data) → zeros / "None" values render, no crash in PDF (Task 3).

---

### Task 1: model + migration
Files: `apps/api/app/models.py`, `apps/api/alembic/versions/0163_monthly_reviews.py`, `apps/api/tests/test_mgmt_032_migration.py`.
`MonthlyReview(month Date unique, status draft|final CHECK, snapshot JSONB, narrative JSONB default {}, generated_at, finalised_at,
finalised_by_user_id FK users RESTRICT, updated_by_user_id FK users RESTRICT, CHECK day=1, CHECK final ⇔ finalised_at)`.
Test: upgrade creates table + constraints; downgrade refuses with a final review.

### Task 2: service + routes
Files: `services/monthly_review.py`, `api/management_reviews.py`, `main.py` (router), `schemas.py`, `services/management_audit.py`
(kind `mgmt.review`), `tests/test_mgmt_032_monthly_review.py`.
- `compute(db, month) -> dict` sections `revenue, expenses, profitability, sales, partnerships, people, marketing, investments,
  next_month` (MR5–MR13), each figure checked against its source endpoint in tests.
- `generate(db, month, actor|None) -> (review, created)`, `update_narrative`, `finalise`, `out`, `run_monthly_reviews(today)`.
- Tests: access matrix; 201/200/409/422; AC1 (1 Oct → September draft, idempotent); AC2; finalise 422 without Problems; PATCH
  final 409; notifications + email deliveries for each active partner; audit rows.

### Task 3: PDF + worker
Files: `reporting/pdf.py` (`render_monthly_review(review: dict) -> bytes`), `worker.py` (task + beat), tests in the same file +
`tests/test_mgmt_032_pdf.py` (text extraction via `pypdf` if present, else reportlab-free byte checks on uncompressed text).
- `GET /{month}/pdf`: `application/pdf`, `Cache-Control: no-store`, audit download.

### Task 4: web lib + list page
Files: `apps/web/lib/managementReviews.ts`, `lib/management.ts` (BI entry live), `app/management/reviews/page.tsx`,
`components/ManagementReviews.tsx` (list + generate form), vitest for both and the nav test update.

### Task 5: review page + editor
Files: `app/management/reviews/[month]/page.tsx`, `components/ManagementReview.tsx` (sections, server-safe),
`components/ManagementReviewEditor.tsx` (client: textareas, Save, Regenerate figures, Finalise with confirm; form-error / status),
`ReportDownloadButton` for the PDF. vitest for rendering and editor flows.

### Task 6: e2e + docs
`apps/web/tests/e2e/mgmt-032-review.spec.ts`; DEC-SCOPE-220, API §12EH, RBAC §2.145, backlog status, QA evidence doc.
