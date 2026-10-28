# ccrm-048 — University deposit receipt upload on the Finance tab (design + plan)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` § `ccrm-048` (owner line L1: "add a document upload option next to the University
Deposit section"). Owner pre-authorised the recommended answers; every default below is the builder's call (`NEEDS_CONFIRMATION`).
Decision: `DEC-SCOPE-322`; API §12HT; RBAC §2.225.

## Intent

The student 360's Finance tab (ccrm-039) shows each application's university deposit read-only. Today the counselor can attach the
deposit receipt only inside the application's evaluation panel (ccrm-025 `ApplicationDepositPanel`), and the Overseas Admin has no
edit UI at all. ccrm-048 puts an "Upload receipt" / "Replace receipt" control on the deposit card itself.

## Behaviour

- Shown on a **counselor-recorded** deposit (`ApplicationDepositRecord`) that is **required**, to the application's counselor or the
  Overseas Admin, while the application is open (not withdrawn / terminally decided) and the student is not archived. `finance()`
  returns `can_upload` per deposit with exactly those rules; the agency (AGN-011) deposit is always `false`.
- New route `POST /workflows/overseas/applications/{id}/deposit/receipt` (multipart `file`) — one transaction: store a "Deposit
  receipt" `StudentDocument` on the application (ccrm-025 upload rules: sniffed PDF/JPEG/PNG, 20 MB, server-generated key) and set
  `receipt_document_id` on the deposit record. Returns 201 `{"record": <deposits.view>}`.
- Order of checks: `_writable` (role 403; counselor not on the application 403; unknown 404; withdrawn / terminal 409; archived agency
  record 409) → archived student 409 → AGN-011 deposit beside it 409 → no record or `required=false` 422 → the file (415 / 413).
- Side effects as for a deposit save: a status-history note ("Deposit receipt uploaded." / "replaced."), the student is told, the
  agency side told for an agency application (`offer_changed`), audit `overseas.application.deposit_receipt` (`replaced`,
  `document_id`), plus the document's own upload audit/event. On any failure the stored object is discarded.
- **Replace (call, NEEDS_CONFIRMATION):** the record points at the new document; the old receipt stays a current document of the
  student (the same as `PUT /deposit` today). It is not made a ccrm-021 version.
- Not required: no button (the card already says "No deposit is required."); the API answers 422. No record: no card (unchanged).
- Student sees the receipt in Documents (every non-archived `StudentDocument` — unchanged).

## Alternatives considered

1. Frontend-only: `POST deposit-receipts` then `PUT deposit` with the record's other values echoed back — two requests, not atomic,
   and the client must reproduce every field exactly (risk of overwriting a concurrent edit). Rejected.
2. Attach-only endpoint taking an existing document id — still two requests. Rejected.
3. **Chosen:** one multipart route reusing `_writable` and the shared `_upload` (refactored to take the locked application and an
   optional attach step inside its transaction).

## Security

Same upload controls as ccrm-045 (`read_upload`). The row lock from `_writable` serialises against `PUT /deposit`. No new data exposed;
`file_url` never returned. No antivirus scan (platform residual risk). No rate limit (staff route, as ccrm-045).

## Frontend

`OverseasStudentFinance` stays a server component; a small client component `DepositReceiptUpload` (file input + button, busy state,
in-flight guard against double submit, `form-error`/`form-message` with roles alert/status, `router.refresh()` on success) renders in
the deposit card when `can_upload`. The F1 banner is reworded: fees remain read-only; a deposit's receipt can be uploaded here.

## Plan (TDD)

1. Backend RED: `tests/test_ccrm_048_deposit_receipt.py` — counselor upload 201 + attached + student sees it; admin replace; agency 409;
   other counselor 403; not required 422; no record 422; archived student 409; withdrawn 409; bad type 415; student role 403;
   `finance()` `can_upload` matrix. GREEN: refactor `_upload`, add route, add `can_upload`.
2. Update ccrm-039 finance tests (new key), ccrm-041 matrix row.
3. Web RED: `OverseasStudentFinance.test.tsx` — button only when `can_upload`, label Upload vs Replace, posts multipart, error shown,
   refresh on success. GREEN: component + type.
4. Docs: API_CONTRACT §12HT, RBAC §2.225, DEC-SCOPE-322.
5. Playwright `e2e/ccrm-048-deposit-receipt-upload.spec.ts`; browser QA desktop/tablet/mobile.
