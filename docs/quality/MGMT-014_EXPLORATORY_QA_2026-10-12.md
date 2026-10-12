# mgmt-014 — Investment register + ROI — exploratory browser QA (2026-10-12)

- **Build:** `feature/mgmt-014`, Docker Compose project `mgmt014` (web `localhost:13414`, api `127.0.0.1:18414`), seeded (`app.seed`, MI14).
- **Tools:** Playwright (Chromium) scripted exploratory pass + `tests/e2e/mgmt-014-investments.spec.ts`.
- **Roles:** partner (`partner.one`, `partner.two`), accountant, super_admin, it_admin (backend), signed out.
- **Viewports:** desktop 1366×900, tablet 820×1180, mobile 375×812.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Happy path: register → Add investment → detail → Edit → Save | Pass: opens the new INV-code; "Investment saved."; ROI updates; Management activity shows "Investment changed" |
| 2 | §23 example (seeded): ₹5,00,000 → ₹18,00,000 | Pass: 260.00% (AC1) |
| 3 | Actual return unknown | Pass: ROI "—" on the row, the detail and (when no actual is known) the overall ROI |
| 4 | Invalid inputs: empty form, "abc" amount, negative return, partner without a partner, too-large return (server) | Pass: worded message, field marked `aria-invalid`, entry kept; server 422 "The amount is too large" shown |
| 5 | Script in Purpose | Pass: rendered as text (React escaping), stored as typed, audit keeps it as a string |
| 6 | Duplicate submission (double click) | Pass: one POST |
| 7 | Offline save | Pass: "The request did not complete…; your entry is kept."; the next online save succeeds |
| 8 | Cancel / refresh / back | Pass: Cancel discards edits; refresh keeps the record; Back returns to the register; filters live in the address |
| 9 | Unknown id, malformed id | Pass: "Investment not found" with a link back |
| 10 | Reversed dates; junk filters | Pass: "The end date must be on or after the start date"; junk dropped, rows shown |
| 11 | Signed out | Pass: `/admin/login?next=%2Fmanagement%2Finvestments` |
| 12 | Accountant, super_admin | Pass: no Command Center entry; page "Access unavailable — Only partners can open this"; API `403` |
| 13 | Desktop / tablet / mobile | Pass after QA-03: no page overflow; the table scrolls inside its region |
| 14 | Console errors, 5xx, broken images | None besides the deliberate 422 (scenario 4) and the deliberate offline request (scenario 7) |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Medium | partner | `/management/investments?offset=999999` | Open the address | A page, no raw error | "[object Object]" (the API's 422 list for offset > 10 000) | **Fixed**: `investmentFilters` caps the offset at 10 000 (unit test) |
| QA-02 | — | partner | detail | Save after an offline attempt; read the record at once | Updated figures | Script read before `router.refresh` finished | **Not a defect**: DB and audit had the change; re-checked with a wait (ROI 200.00%) and by the e2e spec |
| QA-03 | Medium | partner | register, mobile 375 | Open the register on a phone | No horizontal page scroll | 49 px overflow: "₹1,15,00,000.00" widened its tile; the 10-column table was squeezed | **Fixed**: `money-tiles` wraps the figure; table `minWidth` 1040 inside its scroll region |
| QA-04 | Low | partner | add / edit form | Save with a bad amount | Focus on the field to fix | Focus stayed on the button | **Fixed**: the first invalid field is focused (component test) |

Note: the shared dev database also holds investments written by the backend test run (random dates 1990–2022), so totals exceed the demo.
