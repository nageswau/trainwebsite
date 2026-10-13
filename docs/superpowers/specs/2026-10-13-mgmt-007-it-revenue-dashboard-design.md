# mgmt-007 — IT Training revenue dashboard — design

- **Feature:** `mgmt-007` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-007). Depends on mgmt-005 (PR #249, merged on `main`).
- **Evidence:** `EVID-017` §5 "IT Training Revenue" (revenue per course; course-wise, batch-wise, student-wise payments; trainer /
  marketing / operational cost; placement revenue if applicable; Course | Students | Revenue table — `DERIVED_BLUEPRINT`); Management
  M4/M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`); mgmt-004 ML6 (`program_id` / `batch_id` tags on manual entries); mgmt-005 MA1–MA11
  (`ledger.lines()`); mgmt-010 ME1/ME4 (expense heads, Indian financial year).
- **Decision:** one new DEC-SCOPE (number taken at merge). IR1–IR12 answer Q-11 and the open points of the backlog item with
  **recommended defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers. Q-32 (student PII in
  drill-downs) stays open, so the payment list carries no names.

## 1. Intent

The finance tier sees what IT Training earned and spent, per course and per batch, for a month or the financial year to date, and can
open the payments behind any course or batch. Read-only; every money figure comes from `services/ledger.lines()`. Nothing is stored.

## 2. Decisions (IR1–IR12)

| # | Point | Answer |
|---|---|---|
| IR1 | Period | `month` (`YYYY-MM`, IST, default the current IST month; January 2000 to this month, as mgmt-010) and `period` = `month` (default) or `year` (the Indian financial year from 1 April through the end of `month`, ME4) |
| IR2 | Which lines | Counted `ledger.lines()` rows whose vertical is **IT** in the period: approved manual entries (a reversal negative) and rupee automatic lines (IT-division paid payments, college-BDM trip expenses). A line tagged with a course but booked to another vertical is not IT money here (R1/R2: vertical = X) |
| IR3 | Revenue kinds | **Enrolment fees** (payments whose reference is an enrolment: `enrollment_fee`, legacy `enrollment`); **Other IT fees** (every other IT payment, e.g. an IT `service_fee`, Q-08/MA5); **Manual income** (approved manual IT income) |
| IR4 | Course and batch attribution (Q-11) | A payment belongs to the batch of the enrolment it references (`Payment.reference_id` → `Enrollment` → `Batch` → `Program`, `workflows.py:437`). A manual entry belongs to its `batch_id`, else its `program_id` (ML6). Anything else is **Not linked to a course** |
| IR5 | Reconciliation (AC) | A course's revenue / costs = the sum of its batch rows + its course-level row (a manual entry tagged with the course only). Courses + Not linked = the IT totals |
| IR6 | Students (AC) | **Enrolments** made in the period (`Enrollment.enrolled_on` in range, any status) per batch, summed per course. Shown as "New enrolments" because revenue in a month also comes from earlier enrolments (EMI) |
| IR7 | Costs (Q-11) | IT expense lines grouped by the mgmt-010 heads: **Trainer** (Trainers head), **Marketing** (Marketing head), **Operational** (every other head). Per course: the total |
| IR8 | Contribution | Revenue − costs, IT-tagged only. Shared costs are not allocated (Q-04, mgmt-009) — the page says so |
| IR9 | Placement revenue | **Not tracked**: rec-031 invoices are per job, not per candidate, so they cannot be traced to IT-sourced students. The page says "Not tracked — recruitment revenue is on the Recruitment dashboard (mgmt-008)" |
| IR10 | Rows shown | A course (and a batch) is listed when it has revenue, costs or enrolments in the period; largest revenue first, then title. A course with no fee shows ₹0 revenue with its enrolments |
| IR11 | Payments drill-down | `GET /management/revenue/it/payments` (same period) + exactly one of `program_id`, `batch_id`, `unlinked=true`: IT payment lines (counted, newest first, paged 25): date, enrolment code, course, batch, kind, instalment, receipt no., amount. **No student names or emails** (Q-32 open, MA7 precedent). Manual entries are not listed (they are in the ledger) |
| IR12 | Other currencies | IT payments in another currency are not counted and are summed per currency in `not_counted` (MA8) |

## 3. API

- `GET /management/revenue/it?month=&period=` → `{month, period, start, end, label, totals: {revenue, costs, contribution,
  enrolments}, income: [{key, label, amount}], costs: [{key, label, amount}], courses: [{program_id, title, enrolments, revenue,
  costs, contribution, batches: [{batch_id, name, enrolments, revenue, costs}], unbatched: {revenue, costs}}], unlinked: {revenue,
  costs}, placement: null, not_counted: [{currency, amount, count}]}`.
- `GET /management/revenue/it/payments?month=&period=&program_id=|batch_id=|unlinked=true&limit=&offset=` → `{items, total, limit,
  offset}`.
- Finance tier only (`ledger.require_finance`): partner, accountant; super_admin "Finance access required"; others 403 "Management
  access required"; signed out 401. `422` for a bad month/period, a future month, not exactly one scope, an unknown course/batch.

## 4. Web

`/management/revenue/it` (server-rendered, GET form: month + period). Summary tiles (Revenue, Costs, Contribution, New enrolments);
income and cost tables; the course table (course rows with their batch rows beneath, Not linked row, total row); placement "Not
tracked" note; a "Payments" link per course/batch/Not linked opens the payment list on the same page (`?program=…#payments`), paged.
Empty state when the period has no IT money or enrolments. Command Center entry "IT Training revenue" goes live.

## 5. Tests

pytest: access matrix, validation, attribution (enrolment fee → its batch; legacy `enrollment` reference; manual tagged batch/course;
unlinked service fee), reversal, unapproved excluded, other vertical excluded, non-INR not counted, AC invariants (course = Σ batches +
course-level; courses + unlinked = totals; enrolments = rows), year period spans the FY, payments list scope/paging/no names. vitest:
lib URL/param helpers, component states (data, empty, error). Playwright: accountant opens the page, sees a seeded course, opens its
payments; super_admin sees the access card.
