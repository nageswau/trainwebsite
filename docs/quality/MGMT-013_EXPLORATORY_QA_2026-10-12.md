# mgmt-013 Accounts dashboard — exploratory browser QA (2026-10-12)

- **Build:** `feature/mgmt-013` on an isolated Docker Compose stack (`mgmt013`, web `http://localhost:13313`), with seeded demo
  accounts.
- **Method:** an independent pass with no code changes, run as a scripted Playwright (Chromium) session. It covers 29 checks across the
  partner, accountant, super_admin and signed-out roles at 1366×900, 820×1180 and 390×844, and captures console and network events.
  Defects were then fixed with TDD and the same pass was re-run.

## Results

| Area | Result |
|---|---|
| Happy path (partner via the "Accounts" nav entry; accountant; current and far-past month) | Pass |
| Empty month: all three balances "Not entered", profit ₹0.00, "Nothing entered for … yet" | Pass |
| Invalid inputs: `abc`, `1.234`, `1,000`, `99999999999999`, `-1` for tax. Each gives exactly one message, on its own field | Pass |
| Duplicate submission (double click) | Pass: one PUT |
| Save, then refresh: values persist, "Last saved by Ravi Accountant" | Pass |
| Enter key submits the form; clearing every field brings back "Not entered" | Pass |
| Month change, then Back | Pass |
| Future month (`?month=2099-01`): the message shows and the month form stays usable | Pass |
| Malformed month (`?month=abc`): falls back to the current month | Pass |
| super_admin: "Access unavailable" with "Finance access required"; no nav entry | Pass |
| Signed out: redirected to `/admin/login?next=…` | Pass |
| No horizontal page scroll at desktop, tablet or phone; no broken images | Pass |
| Console | Only the deliberate 422s from the invalid-input checks |
| Network | No 4xx/5xx on page loads. The `net::ERR_ABORTED` entries are Next.js `_rsc` link prefetches cancelled on navigation (framework behaviour) |

## Issues found and fixed

| ID | Severity | Role | Page | Steps | Expected | Actual (before) | Fix |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | partner, accountant | `/management/accounts` | Open any month; read "Receivables by source" | "Student fees: ₹83,400.00" | "Student fees₹83,400.00": label and amount run together | Rendered as "label: amount"; vitest asserts it |
| QA-02 | Medium | partner, accountant | same, 390px phone | Open the page on a phone | Each figure on one line | "₹3,34,400.↵00", "-↵₹1,93,800.↵00", and the pending-invoices tile split mid-value | The mgmt-011 phone rule now also covers `.accounts-tiles` (17px figures). The pending-invoices tile shows the amount as the figure and "N invoices" beneath |
| QA-03 | Low | partner, accountant | same | A category whose month nets to 0 (an entry and its reversal) | Not listed in the head's "From" column | Listed as "Cat … ₹0.00" | `_section` drops labels that net to 0; a pytest covers it |

After the fixes, the re-run passed with the same triaged non-defects only. `mgmt-013-accounts.spec.ts` (3 tests) passes.

## Re-verification on main (2026-10-13)

Run against main after mgmt-007 merged. The accountant and partner.one were checked at 1280, 768 and 375px, looking for console errors,
4xx/5xx responses, failed requests, horizontal page scroll and broken images. The 1280px and 768px views passed. The 375px view showed
two layout defects:

| ID | Severity | Role | Page | Steps | Expected | Actual (before) | Fix |
|---|---|---|---|---|---|---|---|
| QA-P1 | Medium | partner, accountant | `/management/accounts`, 360–375px phone | Read "Expenses" | Each head's amount in view | Only HEAD showed. With "From" all "—", the 650px-wide table gave HEAD the spare width, so amounts started off screen | `.accounts-heads`: on a phone, head and amount columns fit their text and "From" takes the rest |
| QA-P2 | Medium | partner, accountant | same | Read "Financial position" | Each figure on one line | "₹1,76,900.0↵0" at 375px, and "Not entered" split at 360px. The 17px rule from QA-02 was only enough at 390px | Below 420px the tiles go one across at the usual 22px. `.accounts-tiles` was dropped from the 17px rule |

A new e2e test, "on a 360/375px phone the figures fit and the amounts are in view", was seen failing first and passes now. All five tests
in `mgmt-013-accounts.spec.ts` pass, as do the 11 vitest tests and the 21 pytest tests.
