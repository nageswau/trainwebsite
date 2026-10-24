# ccrm-021 — Document status model, expiry and versions (design)

Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` ccrm-021 (source §8 status table, Appendix A — UNVERIFIED spec). Decision: `DEC-SCOPE-249`.
Migration `0174_document_status`. API §12FB, RBAC §2.164. Dependencies: none.

## Intent

A student document's status is free text today (the counselor verify route stores any string), has no expiry and cannot be replaced by a
counselor. ccrm-018 already fixed the status vocabulary (`app/document_checklists.ITEM_STATUSES`). This feature makes every stored
document status one of those codes, adds expiry, versions on replace, an archive flag and review metadata.

## Decisions

| # | Decision | Authority |
|---|---|---|
| S1 | Mapping: `pending` stays (a new upload awaiting review, label "Pending review"); `rejected` → `reupload_required`; `changes_required` → `incomplete`; any other value → `under_review`. CHECK on `student_documents.verification_status` IN `ITEM_STATUSES`. The review routes still accept `rejected` / `changes_required` as input aliases (agency API compatibility) and store the new codes. | Owner (2026-10-24) |
| S2 | `expiry_date` is optional on every upload/replace; a **passport** cannot be marked `verified` by a counselor/admin without one (sent with the review or already stored), nor with an expiry in the past. | Recommended, NEEDS_CONFIRMATION |
| S3 | Counselor/Overseas Admin **replace** = new row (`version_of_id` = old id, status `pending`, same owner/application/type/label/expiry unless a new expiry is sent); the old row gets `archived_at` and a `replaced` event; its file is kept. Archived rows are left out of every list and checklist computation; a review or replace of an archived row is 409. The AGN-009 agency in-place replace is unchanged. | Recommended, NEEDS_CONFIRMATION |
| S4 | Daily beat job (00:05 IST) marks non-archived documents whose `expiry_date` is before today (India date) and whose status is not `expired`/`not_required` as `expired`, with an `expired` event (actor NULL). Idempotent. | Recommended, NEEDS_CONFIRMATION |
| S5 | `reviewed_at` column set by every review (agent and counselor), backfilled from the latest review event. Counselor queue, student list and agency cards show reviewer, review date, notes and expiry. | Recommended |
| S6 | `draft` / `review` / `approved` may be set only on CV / SOP / Resume / Statement of Purpose documents until ccrm-019 links documents to checklist items (whose `allowed_statuses` then rule). | Recommended, NEEDS_CONFIRMATION |
| S7 | No delete route exists and none is added; `archived_at` is the only way a document leaves the lists. | Backlog |

Counselor/admin may set: `under_review`, `verified`, `incomplete`, `reupload_required`, `not_required` (+ S6). Agency members keep the
AGN-003 rules (pending only; staff verify only; a reason for anything else) with the codes `verified`, `incomplete`,
`reupload_required`. `expired` is set only by the job; `requested`/`uploaded` are reserved for ccrm-019/020.

## Changes

- **Model/migration 0174:** `student_documents.expiry_date` (date), `reviewed_at` (timestamptz), `archived_at` (timestamptz),
  `version_of_id` (self FK); data map + backfill; `ck_student_documents_status`; `document_events` event CHECK widened with the new
  status codes and `expired`; partial index for the expiry job. Downgrade maps the codes back (lossy for new codes → `pending`).
- **API:** `PATCH /workflows/overseas/documents/{id}/verify` validates the body (`DocumentReview`) for counselor/admin;
  `POST /workflows/overseas/documents/{id}/versions` (multipart `file`, optional `expiry_date`) for counselor/overseas_admin, same scope
  as verify; `POST /workflows/overseas/documents` takes optional `expiry_date`.
- **Lists:** `archived_at IS NULL` in portal document sections, dashboard counts, agency list/dashboard/journey, visa checklist,
  management metrics.
- **Web:** `lib/documentStatus.ts` (labels + legacy aliases); `CounselorDocumentReviewPanel` new decisions, expiry input, review
  metadata, Replace file; agency labels/classes/decisions updated.

## Reviews (Phase 3)

- **API:** the review body is now validated (unknown status → 422 instead of being stored); the response shape is unchanged. Aliases
  keep old clients working. The replace route returns 201 with the new document's id and status.
- **Security:** replace/verify reuse the existing `_assigned_application` / assigned-student checks before any write; the old row is
  locked (`FOR UPDATE`) so two replaces cannot both archive it (the second gets 409). Files go through `agent_documents.read_upload`
  (byte-sniffed type, size limit, EXIF strip) and a server-generated key; the file key is never returned. Audit `document.replace` in
  the same transaction; no file names or notes in logs.
- **Frontend:** existing panel and design language; loading/empty/error states already exist; new controls are labelled form fields;
  the replace form reuses the AGN-009 wording.

## Tests

`tests/test_ccrm_021_document_status.py` (verify validation, aliases, passport expiry, drafting types, replace versions + scope + 409,
lists hide archived, agent aliases, expiry job), `tests/test_ccrm_021_migration.py` (chain, constants, data map, round trip);
vitest for the panel and labels; e2e `ccrm-021-document-status.spec.ts`.
