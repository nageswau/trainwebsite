# ccrm-039 — Student finance tab on the counselor's student 360 (design)

NO-ASSUMPTION MODE. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` §`ccrm-039` (spec PDF §5 Finance + §13 revenue, both optional,
`UNVERIFIED`; owner answer CC6 puts the finance tab in scope). Dependencies `ccrm-009` (PR #315) and `ccrm-025` (PR #317) are merged.
Decision: `DEC-SCOPE-272`. API §12FY. RBAC §2.186. **No migration.**

## Intent

The counselor (and the Overseas Admin) see, on the student 360, what the student has been billed and paid by EduSphere, what was
refunded, and each application's university deposit — without leaving the page. It closes ccrm-009's B1 ("Finance not shown until built").

## Open questions from the backlog → recommended defaults (`NEEDS_CONFIRMATION`, owner's standing "proceed with recommended answers")

- **F1 Read-only.** The tab records nothing. Service fees stay recorded by the Overseas Admin through the existing `POST /admin/payments`
  (and discount / EMI routes); refunds of a gateway payment arrive by the Razorpay webhook; the AGN-011 deposit refund stays the Overseas
  Admin's (`DEC-SCOPE-058`); the ccrm-025 deposit record stays the counselor's on the application page. Rationale: money (risk high), and
  who-may-record is the backlog's unanswered question — a read view needs no answer to it.
- **F2 Service fee = a free amount**, as the existing admin route already takes. No fee catalogue.
- **F3 Who sees.** ccrm-009's gate (`student_profiles.staff_student`): the overseas counselor with the student in csc-001 scope or the
  Overseas Admin; another counselor's student `404`; every other role (student, agent, university_rep, IT counselor) `403`. The agent keeps
  seeing only agency deposits through its existing AGN-011 routes (unchanged); the university_rep sees nothing (unchanged).
- **F4 Deposits on every application of the student** (ccrm-009 V1: the page shows all applications, marked `mine`). One row per
  application that has a deposit: the ccrm-025 counselor record if present, else the AGN-011 agency deposit (they never coexist).
- **F5 Downloads keep their route's rule.** Invoice / receipt PDFs: `GET /payments/{id}/invoice|receipt` allows the payer and the
  division's admin, so the Overseas Admin gets the buttons and the counselor sees only the numbers. A ccrm-025 deposit receipt is a
  student document: `can_download` follows the documents tab rule (own application, or admin).
- **F6 Refunds** = payments in status `refunded` (date = the payment's last update) + AGN-011 deposits with a refund (amount, date,
  reason). No new refund model.
- **F7 Payments shown** = the student's own `Payment` rows (`user_id` = student), except `agent_deposit` ones (AGN-011 D4: an agency's
  deposit payment is the agency's and appears on the deposit). Newest first, no paging (a student has a handful).

## API

`GET /api/v1/counselor/students/{id}/finance` — same gate as the other 360 reads.

```
{
  "payments": [{ id, description, amount, currency, status, status_label, due_date, created_at,
                 installment_no, invoice_no, receipt_no, can_download }],
  "deposits": [{ application_id, application_code, university, mine, source: "counselor"|"agency",
                 required, amount, currency, due_date, status, status_label, paid_on,
                 refund: { amount, refunded_on, reason } | null,
                 receipt: { id, name, can_download } | null }],
  "refunds":  [{ kind: "payment"|"deposit", description, amount, currency, refunded_on, application_code }]
}
```

Amounts are strings with 2 decimals (`money()`), never floats. No `file_url` is ever returned.

## UI

New tab **Finance** between Applications and Activities (link tab, `?tab=finance`, fetched only when selected). Three cards:
"Fees and payments", "University deposits", "Refunds"; each says in words when empty; a failed load is ccrm-009's inline error card.
A note says the tab is read-only and where records are made. Admin download buttons reuse `StudentDocumentDownload` with a URL.

## Acceptance

1. Counselor in scope and Overseas Admin read `/finance`; another counselor's student → 404; student / agent / university_rep / IT
   counselor → 403.
2. Lists the student's service fees with status, invoice and receipt numbers; never another user's payments nor agent-deposit payments.
3. A refunded payment and a refunded agency deposit appear under refunds.
4. Each application's deposit: the counselor record (status label, paid on, receipt) or the agency deposit (read-only).
5. `can_download` false for the counselor on payments, true for the Overseas Admin; deposit receipt follows the document rule.
6. The 360 shows a Finance tab with empty states; works at 375 px; no console errors.

## Non-goals

No writes, no new tables, no change to payment, deposit or download routes, no agent or student UI change.
