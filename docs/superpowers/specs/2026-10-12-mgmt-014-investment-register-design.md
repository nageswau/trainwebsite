# mgmt-014 — Investment register + ROI — design

- **Feature:** `mgmt-014` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-014). Depends on mgmt-001 (merged, PR #243) and mgmt-002
  (merged, PR #245).
- **Evidence:** `EVID-017` §23 (lines 931–969, `DERIVED_BLUEPRINT`): 11 fields, the ROI example ₹5,00,000 → ₹18,00,000 = 260%, "where
  company money is being invested and what it produces". Management M2/M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`): partner-only.
- **Decision:** `DEC-SCOPE-190` (provisional number). Answers MI1–MI14 below are **recommended defaults, `UNVERIFIED`**, taken on the
  owner's instruction to proceed with recommended answers. Q-16 (status values) is answered by MI3 as an interim default.

## 1. Intent

Partners record every investment EduSphere makes and see what it produced. One register (list + totals + add) and one detail page
(view + edit), backed by `GET/POST/PATCH /management/investments`. Partner-only: `super_admin`, the accountant and every other role are
refused at the route, so no investment figure ever reaches them. Every add and change is written to the management audit trail
(mgmt-002 kind `mgmt.investment`, already registered and already hidden from `/admin/audit`).

## 2. Decisions (MI1–MI14)

| # | Point | Answer |
|---|---|---|
| MI1 | Investment ID | `INV-000001` from `investment_code_seq` (the `VIS-`/`UNV-` idiom); a rolled-back create skips a number. Never edited |
| MI2 | Fields (§23) | `invested_on` (date), investor, `amount`, `purpose` (single line, 2–200), `vertical`, `expected_return`, `actual_return`, `status`, `notes` (multi-line, ≤ 2000), ROI (computed, never stored) |
| MI3 | Status (Q-16 interim) | `planned`, `active`, `completed`, `cancelled`; default `active`. Any status may change to any other (no workflow in the source) |
| MI4 | Investor/Partner | `investor_kind` `partner` or `company`. `partner` needs `investor_user_id` = a user whose role is `partner` and who is active when chosen; `company` has none (DB CHECK keeps the pair consistent). The form offers the active partners |
| MI5 | Vertical | mgmt-004's list: `abroad` (Abroad Education), `it` (IT Training), `recruitment` (Recruitment & Placement), `school` (Schools), `shared` (Company-wide), `other` (Other) |
| MI6 | Money | INR only (Q-06 interim), `Numeric(12,2)`. Amount > 0; expected and actual return ≥ 0 and optional; at most 2 decimals |
| MI7 | ROI (Appendix B I1) | `(actual − amount) ÷ amount × 100`, rounded half-up to 2 decimals; `null` (shown "—") while the actual return is not known. Source example gives `260.00` |
| MI8 | Totals | Over every investment matching the filters (not just the page), **cancelled excluded**: count, total invested, total actual return and overall ROI = `(Σ actual − Σ amount) ÷ Σ amount × 100` over the investments whose actual return is known (`null` when none) |
| MI9 | Register filters | `date_from` / `date_to` (on `invested_on`, inclusive; `date_to` before `date_from` → `422`), `vertical`, `status`; `limit` 1–100 (25), `offset` 0–10 000; newest `invested_on` first, then code |
| MI10 | Edit | `PATCH` changes only the fields sent (`extra="forbid"`); the row is locked (`FOR UPDATE`) so two partners' edits serialise. A PATCH that changes nothing writes no audit entry. No delete: a mistake is set to `cancelled` |
| MI11 | Audit (§2 "who added an investment") | create → `mgmt.investment.create` with every field set and its value; update → `mgmt.investment.update` with only the changed fields and before/after values (MA3: partner-only kinds keep values). Same transaction as the write (MA10). `created_by` / `updated_by` on the row |
| MI12 | Access (M13) | Partner → `200`/`201`. `super_admin`, accountant → `403` "Only partners can open this"; any other role → `403` "Management access required"; signed out `401`; unknown id → `404` |
| MI13 | Pages | `/management/investments` (totals, filter form as GET, table, "Add investment" form) and `/management/investments/[id]` (all fields, ROI, created/updated by, edit form). The Command Center's "Investments & ROI" entry goes live (partner-only) |
| MI14 | Demo data | `app.seed` adds the §23 example once (Marketing Campaign, ₹5,00,000 → expected ₹15,00,000, actual ₹18,00,000, completed, by a demo partner) |

## 3. Components

- `models.py`: `INVESTMENT_*` constants, `investment_code_seq`, `Investment` (`investments`; CHECKs on status, vertical, investor pair,
  amount > 0, returns ≥ 0; index `ix_investments_invested_on`).
- Migration `0151_investments` (after `0150_management_ledger`, mgmt-004), guarded like 0115; `downgrade()` refuses while any investment exists.
- `schemas.py`: `InvestmentCreate`, `InvestmentUpdate`, `InvestmentOut`, `InvestmentPageOut` (+ totals, investor choices).
- `services/investments.py`: `roi`, `create`, `update`, `get`, `page` — validation against the DB (investor), audit, totals.
- `api/management.py`: `GET /management/investments`, `POST /management/investments`, `GET/PATCH /management/investments/{id}`.
- Web: `lib/investments.ts` (types, labels, URLs, money/ROI text, filters), `components/InvestmentRegister.tsx` (table + totals + filter
  form), `components/InvestmentForm.tsx` (add/edit client form), pages, `lib/management.ts` entry `href`.

## 4. Error handling

`401` signed out; `403` with the M13 message (pages show the access card); `404` unknown id (detail page shows "not found"); `422` names
the field ("The amount must be more than ₹0", "Choose a partner for a partner investment", …) and the form keeps the entry; a dropped
network keeps the entry (`NOT_COMPLETED`); a double click sends once.

## 5. Testing

- Backend `tests/test_mgmt_014_investments.py`: AC1 (260%), ROI null, totals (cancelled excluded, filters), create/update audit rows with
  values, no-op PATCH writes nothing, investor rules, validation 422s, 401/403 per role, 404, paging and filters.
  `tests/test_mgmt_014_migration.py`: model ↔ migration CHECKs, round trip, downgrade refusal.
- Web `investments.test.ts` (ROI/money text, filters, URLs), `InvestmentRegister.test.tsx`, `InvestmentForm.test.tsx`,
  `management.test.ts` (live entry for partners only).
- Playwright `mgmt-014-investments.spec.ts`: partner adds and edits an investment and sees 260% for the demo; accountant and super_admin
  get "Access unavailable".
