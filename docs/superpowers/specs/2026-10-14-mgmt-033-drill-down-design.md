# mgmt-033 — Drill-down navigation (business → transaction) — design

- **Feature:** `mgmt-033` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-033). Depends on mgmt-006 (PR #255), mgmt-007 (PR #254),
  mgmt-008 (PR #257) and mgmt-016 (PR #270), all merged on `main`.
- **Evidence:** `EVID-017` "The key difference" (lines 1439–1480: Business → Department → Employee → Student/Application/Transaction;
  the Abroad, IT and Recruitment chains — `DERIVED_BLUEPRINT`); §1/§33 structure; Management M3/M4/M13 (`EXPLICIT_APPROVAL`,
  `DEC-SCOPE-186`); mgmt-005 MA1–MA11 (`ledger.lines()`); mgmt-006 MR5/MR7, mgmt-007 IR4/IR9/IR11, mgmt-008 RR3/RR9.
- **Decision:** one new DEC-SCOPE (number taken at merge). DD1–DD14 answer Q-32 and the open points of the backlog item with
  **recommended defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.

## 1. Intent

From each revenue dashboard's headline figure, a finance-tier user drills one level at a time down the source's chain to the single
transaction behind it. Each level is a table of rows whose amounts add up to the figure above it, with an "unattributed" row where the
data cannot say. The final level shows that transaction read-only. Nothing is stored; every rupee comes from `ledger.lines()`.

## 2. Decisions (DD1–DD14)

| # | Point | Answer |
|---|---|---|
| DD1 | Chains | Three, as in the source: **abroad** (country → university → agency → staff → student → application → payment), **it** (course → batch → trainer → student → payment, with placement on the record), **recruitment** (company → recruiter → requirement → payment, with the requirement's selections and joinings on the record) |
| DD2 | Which money | The same counted income lines as the parent dashboard: `ledger.lines()` with `kind = income`, `counted`, the chain's vertical (`abroad`, `it`, `recruitment`), in the period. So level 0 = the dashboard's revenue figure (AC1) |
| DD3 | Period | `month` (`YYYY-MM`, default this IST month; Jan 2000 to this month — mgmt-010 ME9) + `period` = `month` (default) or `year` (Indian FY to the end of `month`), as mgmt-007/008 |
| DD4 | Who (AC3) | **Finance tier only** (partner, accountant): all three chains are money chains. `super_admin` gets 403 "Finance access required" (M13); anyone else 403 "Management access required" |
| DD5 | University commission | Partners only (M3, MR7): for anyone else the abroad chain never reads commission lines, so its level 0 equals that user's Abroad dashboard revenue |
| DD6 | Attribution | Abroad: a payment through the application its `reference_id` names (mgmt-006 MR5); a commission receipt through its university; manual entries unattributed. IT: a payment through its enrolment → batch → course (IR4); a manual entry through its batch/course tags. Recruitment: an invoice payment → invoice → requirement → company. **Agency** = the application's agent's organisation; **staff** = the agency staff member (application/record agent), else the EduSphere counselor; **student** = the payment's `user_id`; **trainer** = the batch's trainer; **recruiter** = the requirement's assigned recruiter, else the company's |
| DD7 | Unattributed (edge case) | A line whose value at a level is unknown falls in one row per level, keyed `none` and labelled per level ("Unknown country", "No agency", "No course linked", …), so rows always add up to the parent |
| DD8 | Candidate money | Not tracked per candidate: rec-031 invoices are per requirement (IR9). The recruitment chain's money ends at the payment; its record lists the requirement's **selected** and **joined** candidates (source: candidate → selection → joining) |
| DD9 | Final level (AC2) | The payment level's rows are individual lines; choosing one shows its **record read-only** in the drill page: date, amount, description (receipt / invoice no.), the breadcrumb chain, and chain details (abroad: application status, intake, offer; IT: enrolment code + the student's placement outcomes; recruitment: selections/joinings). Existing module record screens are not opened (their RBAC excludes partner/accountant; opening them would widen access) |
| DD10 | PII (Q-32) | Partners and accountants see **names only** (student, staff, trainer, recruiter, candidate) — no email, phone or document. Same as the ledger's "who paid" need |
| DD11 | Audit (Q-32) | Every read that lists individual students or anything below (student, application, payment levels, and the record) writes one `AuditLog` row: kind `mgmt.drill` (finance tier), verb `view`, entity = the last chosen id (or the chain), fields = `[chain, level]`. Shown in Management activity |
| DD12 | Path | URL-held: `path` = the chosen keys in level order, comma-separated; each a UUID or `none`. Max = the chain's level count. Bad chain → 404; malformed key, too many keys, or `none` for a payment → 422; a well-formed path with no counted line in the period → 404 |
| DD13 | Paging & order | Rows largest amount first, then name; `limit` 25 (≤100), `offset`. One grouped query per level |
| DD14 | Entry points | A "Drill down" link beside the revenue figure on the Abroad, IT and Recruitment revenue dashboards (the latter only when money is visible); no new menu entry |

## 3. API

`GET /management/drill/{chain}?month=&period=&path=&limit=&offset=` →

```
{chain, chain_label, month, period, label, start, end, total, count,
 breadcrumbs: [{level, level_label, key, name}],
 level: {key, label} | null,              # the level listed next; null at the record
 rows: [{key, name, amount, count, latest}], total_rows, limit, offset,
 record: null | {source, id, entry_date, amount, currency, description, details: [{label, value}],
                 outcomes: null | {title, items: [{name, detail, status}]}}}
```

## 4. Frontend

`/management/drill/[chain]?month=&period=&path=&page=` (server page, as the revenue pages) renders `ManagementDrillDown`: the period form,
a breadcrumb `<nav aria-label="Drill-down path">` (chain root + each chosen level, the active filter shown), the total, the next level's
table (each row a link one level down; the unattributed row too), a pager, or the record. Loading = server render; error = `.form-error`
alert; empty = `role="status"` text. `lib/managementDrill.ts` parses/builds the address.

## 5. Tests

Backend (`test_mgmt_033_drill.py`): tier (partner, accountant 200; super_admin, it_admin 403); AC1 rows sum to the parent at every
level of each chain, incl. the unattributed row; level 0 equals the dashboard revenue; commission hidden from the accountant; record at
the last level; tampered paths (unknown chain 404, bad key 422, too deep 422, `none` payment 422, unknown id 404); audit rows only at
student level and below. Web: vitest for the address helpers and the component (breadcrumbs, rows, record, empty, error); a Playwright
spec walking the IT chain to a record.

## 6. Plan

1. Service `management_drill.py` (levels table, `drill()`), audit kind/verb — TDD with the backend tests.
2. Schema + route in `api/management.py`.
3. Web lib + component + page; links from the three dashboards — vitest.
4. e2e spec; exploratory browser QA; docs (DEC/API/RBAC/backlog) after merging main.
