# rec-031 — Revenue / commercial tracking (track only): design

- **Feature:** rec-031 (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-031). **Source:** EVID-018 §23 (lines 918–940: Requirement,
  Candidates selected, Candidates joined, Fee per hire, Total invoice, Invoice date, Payment due, Payment received, Outstanding amount).
  `DERIVED_BLUEPRINT`, in scope by R9 ("track only": no invoice PDF, no accounting sync, no GST computation).
- **Dependencies:** rec-023 (joining, PR #213, owner-confirmed JN1–JN10) and rec-030 (contracts, PR #208). Both are merged.
- **Decision:** `DEC-SCOPE-176` (RV1–RV10). Migration `0147_recruiter_revenue`, API §12CQ, RBAC §2.102.
- **Answers:** the owner said "proceed with recommended answers". RV1–RV10 are the recommended answers to Q-24. They are **UNVERIFIED**
  until the owner confirms them.

## 1. Decisions (RV1–RV10, UNVERIFIED)

| # | Question | Recommended answer |
|---|---|---|
| RV1 | Fee per hire (Q-24) | A requirement override (`jobs.fee_basis` + `jobs.fee_value`, the rec-030 CT4 shape) wins; otherwise the company's **current** contract fee (any status, shown with its status); otherwise "No fee set" and no expected revenue. |
| RV2 | Percentage of CTC | Per joined hire: the accepted offer's `compensation` × % ÷ 100, rounded to paise. A hire without an INR compensation is **unpriced**: counted, shown, and left out of expected revenue. |
| RV3 | Currency / GST (Q-24) | INR only. Amounts are recorded as invoiced; EduSphere computes no GST. |
| RV4 | Joined only (AC3) | Joined = applications on the requirement with status `joined` (the rec-007 `joined_count` rule; an offer's Joined joining moves the application there, JN7). Expected revenue = Σ fee of joined hires. |
| RV5 | Selected | Applications that ever entered Selected (status history), or are Selected / Joined now (legacy rows without history). |
| RV6 | Invoices | Manual, per requirement: number (1–40, unique ignoring case, never reused), invoice date (≤ today IST), due date (≥ invoice date), amount (> 0, 2 decimals), note (≤ 500). Payment status is derived: Unpaid, Part paid, Paid; Overdue when not paid and due before today (IST). |
| RV7 | Payments (AC2) | Received date (≥ invoice date, ≤ today IST), amount (> 0), reference (≤ 100). A payment can't take the received total over the invoice amount: 422 on `amount` naming the outstanding. Checked under the invoice row lock. |
| RV8 | Corrections | Invoices and payments are never edited or deleted. An unpaid invoice can be **cancelled** with a reason (2–500); it then counts nowhere and its number stays used. A cancelled invoice or one with payments can't be cancelled (409). |
| RV9 | Did Not Join after invoicing (Q-24) | Nothing changes automatically. When the open invoices exceed the expected revenue, the revenue view says so ("Invoiced more than the expected revenue"), so the recruiter can cancel and re-issue. |
| RV10 | Roles (Q-24 "manager?") | Read and record invoices/payments: `placement_team`, `placement_manager`, `super_admin`, within the rec-007 requirement scope (out of scope = 404). Set the fee override: `placement_manager` and `super_admin` (a pricing exception to the contract). The BDM, HR, students and employers get 403 / see nothing. |

## 2. Data (migration 0147)

- `jobs` gains `fee_basis` String(20) and `fee_value` Numeric(12,2), both nullable, with CHECKs: both null or both set; basis in
  (`fixed`, `percent_of_ctc`); value ≥ 0, ≤ 100 for a percentage.
- `recruiter_invoices`: id, job_id (FK RESTRICT), invoice_number String(40), invoice_date, due_date, amount Numeric(12,2), note String(500),
  created_by_user_id, cancelled_at, cancelled_by_user_id, cancel_reason String(500), created_at, updated_at. CHECKs: amount > 0;
  due ≥ invoice date; cancelled_at, cancelled_by and reason set together. Unique index on `lower(invoice_number)`; index (job_id, invoice_date).
- `recruiter_payments`: id, invoice_id (FK RESTRICT), received_on, amount Numeric(12,2) > 0, reference String(100), created_by_user_id,
  created_at. Index (invoice_id, received_on).
- The downgrade refuses while any invoice or fee override exists.

## 3. API (§12CQ)

| Method | Path | Notes |
|---|---|---|
| GET | `/recruiter/requirements/{id}/revenue` | Selected, joined, fee (+ source), hires (candidate, joined date, fee), expected revenue, unpriced hires, invoiced, received, outstanding, `over_invoiced`, invoices with payments, permissions. |
| PUT | `/recruiter/requirements/{id}/fee` | `{fee_basis, fee_value}`; both null clears the override. Manager / super_admin. |
| POST | `/recruiter/invoices` | `{requirement_id, invoice_number, invoice_date, due_date, amount, note}` → 201 `{invoice}`. 409 `invoice_number_taken`. |
| POST | `/recruiter/invoices/{id}/payments` | `{received_on, amount, reference}` → 201 `{invoice}`. 409 when cancelled. |
| POST | `/recruiter/invoices/{id}/cancel` | `{reason}` → `{invoice}`. 409 when paid in part or already cancelled. |
| GET | `/recruiter/companies/{id}/revenue` | The company's requirements in the caller's requirement scope, one row each, plus totals. |
| GET | `/recruiter/invoices?view=outstanding\|overdue\|paid\|cancelled&limit&offset` | The receivables list in scope, with counts per view and the outstanding total. |

Every write is one transaction: role check (403), scoped load with a row lock (404), rules (422 / 409), the write, an audit row
(`recruiter_revenue.*`: ids and amounts, never notes or names), one commit, one log line (ids only). Out-of-scope ids are the same 404 as
unknown ones.

## 4. UI

- **Requirement page — "Revenue" section** (after Candidates): the §23 figures in a detail list (Candidates selected, Candidates joined,
  Fee per hire with its source, Expected revenue, Total invoiced, Payment received, Outstanding), the over-invoiced notice, the joined hires,
  a fee override form (manager), "Add invoice", and the invoices, each with its payments, "Record payment" and "Cancel invoice".
- **Company page — "Revenue" section** (after Contract / MoU): totals and one row per requirement linking to it.
- **New page `/recruiter/receivables` ("Receivables")**: Outstanding / Overdue / Paid / Cancelled tabs with counts, the outstanding total,
  rows linking to the requirement; tab and page in the URL. Nav entry for the recruiter and the manager.
- Every section has loading, empty and error-with-retry states; a 422 lands on its field; amounts are shown as `₹1,50,000.00` (Indian grouping).

## 5. Tests

- Backend `test_rec_031_revenue.py`: AC1 (₹1,50,000 invoiced, ₹1,00,000 received → ₹50,000 outstanding), AC2 (over-payment 422), AC3
  (Did Not Join / selected-only hires don't count), fee resolution (override > contract > none, percent with and without CTC), negative
  amounts 422, duplicate number 409, cancel rules, roles (BDM 403, other recruiter 404, recruiter can't set the fee), receivables views,
  company totals. `test_rec_031_migration.py`: chain, model parity, round trip, downgrade guard.
- Web vitest: lib helpers, the requirement section (figures, forms, field errors), the receivables panel. Playwright: invoice → payment →
  outstanding on the requirement page, then the receivables list.

## 6. Out of scope

- invoice PDFs, GST, accounting sync (R9); editing or deleting payments; currencies other than INR;
- revenue dashboards and the period figure B12 (rec-033, mgmt-008).

## 7. QA evidence (2026-10-11)

Exploratory pass with Playwright (Chromium) on the worktree's Docker stack, seeded recruiter / manager / hr accounts, a company with a
₹50,000 contract fee and a requirement with 3 joined hires and 1 selected:
- Recruiter: figures (4 selected, 3 joined, ₹1,50,000 expected, fee "from the company contract (Negotiation)"); negative amount and blank
  fields refused on their fields; ₹1,50,000 invoice saved once on a double click; duplicate number (other case) refused; over-payment refused
  naming ₹1,50,000.00 outstanding (AC2); ₹1,00,000 received → ₹50,000 outstanding, Part paid (AC1); refresh keeps it; no Cancel on a
  part-paid invoice; no fee override; Receivables tab in the URL and Back; company totals and "Receivables for this company".
- Manager: a fee value without a basis is refused on Fee basis; ₹60,000 override → ₹1,80,000 expected; clearing returns to the contract fee.
- hr_team: Receivables shows "Access unavailable — Revenue is visible to recruiters and their managers"; the revenue API is `403`. Signed
  out: redirected to `/it/login?next=…`.
- Tablet (820) and mobile (390): no horizontal overflow on the requirement or Receivables; no console errors other than the browser's own
  log lines for the 4xx answers the pass provoked on purpose; no 5xx.

| ID | Severity | Finding | Outcome |
|---|---|---|---|
| QA31-01 | Low | A blank invoice number (or cancel reason) said "Input should be a valid string": the form sends `null` for a blank field | Fixed: `null` is read as blank, so the message is "Invoice number is required" / "Reason is required" (test `test_blank_required_text_says_it_is_required`), re-verified in the browser |

Pre-existing, not rec-031: `RecruiterCompanies.test.tsx` "archives after confirming" fails on `main` too (its first write is rec-030's
contract read).
