# pob-012 — Vendor commercials, payables and performance (DEC-SCOPE-433)

**Evidence:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-012 (`UNVERIFIED` requirements draft). The owner asked to proceed
with the recommended answers; W1–W10 are the builder's calls and are `NEEDS_CONFIRMATION`.
**Dependencies:** pob-010 (vendor master, vendor agreement), pob-011 (`jobs.via_vendor_id`, vendor shares) are merged.

**Non-goals:** vendor-supplied candidates (a vendor submitting profiles to us); GST/PDF invoices (rec-031 R9: track only); automatic
bills from joinings; a period filter on the report; vendor merge.

## Decisions

- **W1 Fee model = the pob-010 vendor agreement.** Its `direction` (we pay vendor / vendor pays us), fee, `payment_terms` (payment
  milestones) and `replacement_policy` are already the fee model, behind `commercials.vendor.*`. No new agreement columns.
- **W2 Vendor bills.** `vendor_bills` records, by hand, an amount we owe a vendor (`kind = payable`) or a vendor owes us
  (`kind = receivable`): number, bill date, due date, amount, optional `milestone` (the payment milestone it settles, ≤120 chars),
  optional requirement (must be one that came via this vendor), note. Never edited or deleted: a mistake is cancelled with a reason,
  only while unpaid (rec-031 RV8). The number is unique per vendor ignoring case. Only a vendor-type company (`vendor`, `vendor_client`)
  has bills (else 422). Both kinds are allowed whatever the agreement direction (a replacement refund flows the other way).
- **W3 Payments.** `vendor_bill_payments` (paid on, amount, reference), append-only; under the bill lock the total never exceeds the
  amount (422). Not on a cancelled bill (409). Dates not in the future nor before the bill date.
- **W4 AuthZ.** Reads need `commercials.vendor.view`; writes need `commercials.vendor.edit` (pob-010 V9 holders: placement_team,
  placement_manager; super_admin implicitly). The vendor resolves through the company scope (`load_scoped`, 404 outside it).
  Refusals log actor/role/route only.
- **W5 Ledger (Q-09 = yes).** Bill payments feed the management ledger as automatic lines, computed on read like `recruiter_payment`:
  a payable payment is a `vendor_payment` **expense**, a receivable payment a `vendor_receipt` **income**, both vertical
  `recruitment`, in rupees. The description carries the bill number only (no vendor name, like rec-031's line). Cancelled bills have
  no payments, so nothing to exclude.
- **W6 Metrics (per vendor, all time).** Over the requirements via the vendor in the caller's requirement scope, and the applications
  shared to the vendor (`profile_shares.recipient = 'vendor'`, `company_id` = the vendor):
  - *response time* — hours from the requirement's creation to its first share to the vendor; the report shows the average over
    requirements with a share (the backlog's "requirement shared with vendor → first submission"; we only have submissions *to* vendors);
  - *submitted* — distinct applications shared to the vendor;
  - *interview conversion* — of those, the ones that ever reached Interview (now Interview/Selected/Joined, or entered Interview);
  - *placements* — of those, the ones that ever reached Selected (rec-031's selected rule);
  - *joining rate* — Joined ÷ placements;
  - *payment history* — per kind: billed, paid, outstanding (open bills), and the last payment date.
  A rate with a zero denominator is `null` and shows "—", never 0% (+/−/E).
- **W7 Tie-out (AC).** The drill-down returns the rows the figures are counted from (requirements with their response hours;
  submitted applications with interviewed/placed/joined flags). Both the report and the drill-down compute the figures from the same
  rows in one function, so every figure equals its drill-down count.
- **W8 API (§12LZ).** `GET/POST /recruiter/companies/{id}/vendor-bills`, `POST /recruiter/vendor-bills/{id}/payments`,
  `POST /recruiter/vendor-bills/{id}/cancel`, `GET /recruiter/vendors/performance` (paged vendors), `GET /recruiter/vendors/{id}/performance`.
- **W9 UI.** A "Vendor commercials" section on a vendor's company page (totals, bills with payments, record bill / payment / cancel)
  for holders of the view grant; a "Vendor performance" page linked from the Vendors page, each row opening the drill-down page.
- **W10 Migration `0314_vendor_bills`.** Additive and guarded (0001 runs `create_all`); the downgrade drops both tables.

## Security review

IDOR: vendor via `load_scoped`, bill via its company's scope (404). Escalation: no new roles; grants checked server-side. Validation:
pydantic bounds, control characters refused on text. Audit: ids and amounts only (never notes, references, reasons). XSS: React escapes.
CSRF/session unchanged. Concurrency: bill row `FOR UPDATE` on payment and cancel; the unique index backs the number check.

## Plan (TDD)

1. `tests/test_pob_012_vendor_commercials.py`: bills CRUD rules, grants, scope, payments cap, cancel, ledger lines, metrics + tie-out,
   "—" rates, migration shape. RED.
2. Models + migration + schemas + `services/vendor_commercials.py` + `api/vendor_commercials.py` + ledger source. GREEN.
3. Web: `lib/vendorCommercials.ts`, `RecruiterVendorCommercials.tsx`, `RecruiterVendorPerformance.tsx`, two pages; vitest.
4. Playwright `pob-012-vendor-commercials.spec.ts`.
5. Docs: DEC-SCOPE-433, API §12LZ, DATA_MODEL, RBAC §2.324, RTM, backlog status.

## Regression risks

Ledger/management finance tests (a new union source), the ledger web source labels, the company detail page.
