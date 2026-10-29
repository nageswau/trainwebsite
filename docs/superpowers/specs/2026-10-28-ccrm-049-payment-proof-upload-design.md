# ccrm-049 — Payment receipt / proof upload on the student 360's Finance tab (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` `ccrm-049` (owner line L6, Q4). Follows ccrm-048 (deposit receipt, DEC-SCOPE-322).
Decision `DEC-SCOPE-326`; API §12HX; RBAC §2.229.
The owner asked the session to proceed on the backlog's recommended defaults; every default below is marked as such.

## Intent

Staff record offline payments (bank transfer, cash) against a student's fee, but there is nowhere to keep the proof the student sent.
The counselor (students in their caseload) and the Overseas Admin attach a receipt file to a payment row on the Finance tab's
"Fees and payments" card; the student sees it on the portal Payments page and in their Documents. The system-generated PDF receipt
is unchanged and shown as a different thing ("System receipt" vs "Uploaded proof").

## Decisions

- **D1 Route.** `POST /api/v1/counselor/students/{student_id}/payments/{payment_id}/proof`, multipart `file`, 201
  `{"payment": <the finance tab's payment row>}`. The gate is the 360's `staff_student`: another role 403, an unknown student or a
  counselor outside the caseload 404 (no disclosure). *Deviation:* the backlog's AC4 says 403 for a counselor outside the caseload;
  every 360 route (ccrm-041 matrix `STUDENT = {"cns_out": 404}`) answers 404, so this one does too (`NEEDS_CONFIRMATION`, default 404).
- **D2 Payment scope.** The payment must be the student's (`payments.user_id`) and not an AGN-011 agency deposit payment
  (`reference_type`); otherwise 404 "Payment not found" (AC3).
- **D3 Which payments.** Manual payments only (`provider == "manual"`, backlog default): a gateway payment already has its system
  receipt → 409. Any status (a pending payment's proof of an offline transfer is allowed, backlog default). Archived student → 409.
- **D4 Storage.** One transaction: a `StudentDocument` (student, no application, type **"Payment receipt"**, label = the payment's
  description, `pending`, uploaded by the actor) via the AGN-009 upload rules (`read_upload`: sniffed type, 20 MB, server key);
  `payments.proof_document_id` set; document event + audit `payment.proof_attached` `{replaced, document_id, student_id}`. The payment
  row is locked (`FOR UPDATE`) so two replaces serialise. On failure nothing is written and the stored object is discarded.
  Amount/status are never touched. A replaced proof stays one of the student's documents (as ccrm-048).
- **D5 Finance payload (additive).** Each payment gains `proof: {id, name, can_download} | null` and `can_upload_proof`
  (manual payment, student not archived). `can_download` is true: the document download route lets the Admin and a caseload counselor
  fetch an application-less student document (ccrm-045), which is exactly who passes the gate.
- **D6 Student portal.** The overseas Payments section gains an "Uploaded proof" column: the document's name and "download from
  Documents" (never a file key, as the Downloads section); the file itself is downloaded from Documents (the audited route).
- **D7 Migration** `0216_payment_proof_documents` (0212 is taken; next free after 0215): nullable `payments.proof_document_id` FK →
  `student_documents.id` `ON DELETE SET NULL`, added only when missing (0001 builds from the models). Downgrade drops it.
- **D8 UI.** The ccrm-048 upload control becomes a shared `ReceiptUpload` (url + subject); the payment row shows "Uploaded proof: name
  [Download]" and the control where `can_upload_proof`; the system receipt download is labelled "System receipt".

## Non-goals

Recording or editing payments by a counselor; Razorpay proofs; notifications to the student; proof review workflow beyond the
document's normal verification.

## Acceptance (tests)

AC1 counselor attaches a PDF proof to a manual payment → stored, linked, student sees it (portal Payments + Documents);
AC2 Admin replaces it, audited `replaced: true`; AC3 another student's payment → 404; AC4 counselor outside caseload → 404 (D1);
AC5 migration up/down clean; AC6 system receipt unaffected; plus gateway payment 409, archived 409, bad file 415/422, other roles 403,
unauthenticated 401, deleted document → proof null.
