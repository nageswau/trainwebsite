# mgmt-033 — Drill-down navigation — exploratory QA (2026-10-14)

- **Build:** `feature/mgmt-033` (API `64e332cd`, web `6df2df32`), isolated Docker stack `mgmt033` (web `localhost:13333`, API `:18333`).
- **Tools:** a Playwright QA script (Chromium/Edge) and the `tests/e2e/mgmt-033-drill-down.spec.ts` spec.
- **Data:** the seed, plus one QA row per chain dated this IST month: an abroad service fee on an agency application, an IT enrolment
  fee on a batch with a trainer, and a recruiter invoice payment on a requirement with one selected and one joined candidate.
- **Accounts:**
  - `partner.one@` and `partner.two@` (partner);
  - `accountant@` (accountant);
  - `superadmin@` (super_admin);
  - `bdm.manager@` (a management-excluded role).

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Partner walks the abroad chain: country → university → agency → staff → student → application → payment → record. Each level lists one row (the QA application) with the breadcrumbs so far; the record shows date, amount, receipt, application status and intake | Pass |
| 2 | Accountant walks the recruitment chain: company → recruiter → requirement → payment → record. The record lists the selected and joined candidates (not the sourced one) | Pass |
| 3 | Accountant walks the IT chain: course → batch → trainer → student → payment → record. The record shows the enrolment code and "Placement: None recorded." | Pass |
| 4 | Level 0 equals the dashboard's revenue (e2e: IT for the financial year); every level's rows add up to its total (AC1) | Pass |
| 5 | Refresh on the record, then Back, Forward, a middle breadcrumb, and switching the period to the financial year all keep the path | Pass |
| 6 | Entry links: Abroad (month + financial year), IT, Recruitment (partner). The recruitment link is hidden for the super admin and anyone else without money | Pass |
| 7 | Invalid inputs: a future month shows the API's "Choose this month or an earlier one"; a garbage `path` is dropped, so the page shows the top level; an unknown chain is a 404 page; a random UUID path shows "Nothing to show for this selection in this period" + "Start again from the top" | Pass |
| 8 | Paging past the end (`page=999`) | **QA33-01**, fixed |
| 9 | Unattributed row ("No course linked") listed and drillable | Pass |
| 10 | Audit: Management activity (accountant) lists "Drill-down read" | Pass |
| 11 | super_admin → "Access unavailable · Finance access required"; bdm_manager → "Management access required" (AC3) | Pass |
| 12 | Desktop 1280, tablet 820, phone 375: no horizontal page overflow | Pass after **QA33-02/03** |
| 13 | Console errors, failed requests (excluding Next `_rsc` prefetches) and 5xx responses | None |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA33-01 | Low–Medium | Any finance role, `/management/drill/it?period=year&page=999` | Open a page past the last row | Say the page is past the end, with a link back | "No counted IT Training revenue in the financial year…", while the tiles show ₹60,000 across 3 lines | Fixed: "This page is past the last of N rows. First page" (vitest) |
| QA33-02 | Low | Phone 375 px, any level | Open a level | The money figure on one line | "₹27,000.0 / 0" broke across lines in a half-width tile | Fixed: tiles stack on a phone (`accounts-tiles`) |
| QA33-03 | Low | Phone 375 px, a level table | Open a level | Amount visible without scrolling sideways | Four columns: Amount started off-screen | Fixed: three columns (Lines, or Date at the payment level, then Amount) with `min-width: 0` and the amount on one line |

Re-verified after the fixes: the e2e spec passes 3/3, the QA script re-run shows 0 px overflow at 375/820, and the screenshots were
checked.
