# mgmt-022 — School dashboard + school revenue / contract / renewal value (design)

NO-ASSUMPTION MODE. 2026-10-14, `feature/mgmt-022`. Source: `EVID-017` §18 (lines 683–715), backlog
`docs/delivery/MANAGEMENT_COMMAND_CENTER_BACKLOG.md` § mgmt-022 and Q-23. Dependencies mgmt-003 (PR #244) and mgmt-005 (PR #249) are
merged on `main`.

**Status of the answers below:** SD1–SD16 are the recommended answers applied under the owner's standing instruction for build sessions
("proceed with recommended answers"). They are `UNVERIFIED` until the owner confirms them; SD13/SD14 answer Q-23.

## 1. What exists (verified in code)

| Need | Existing source | Reuse |
|---|---|---|
| Schools contacted, meetings, proposals, MoUs | mgmt-020 `management_bdm.dashboard(db, "school", …)` (bdm-024 / bdm-015/016 builders) | Called as is, so the figures equal the BDM dashboard's School BDM figures |
| Active schools, students, career guidance, psychometric | ENH-016 `school_analytics`: `_is_active`, `student_indicators` (`guidance`, `psych_completed`, `published_results`, …) | Same functions, so totals equal `GET /overseas-admin/analytics/summary` |
| Teachers, parents | ENH-008 `schools._account_belongs_to_school` (teacher by `profile.school_id`; parent by `SchoolParentLink`, else a stale `profile.school_id`) | Same rule, in bulk |
| Profile completion | ENH-012 `portfolio.portfolio_completion` (as ENH-016 `build_scorecards` computes it in bulk) | Same inputs |
| School money | `School` has no contract/renewal value; the ledger has the `school` vertical ("School projects") but no school tag (mgmt-004 ML6 deferred it to Q-23) | New, SD11–SD14 |

## 2. Decisions

| ID | Topic | Answer |
|---|---|---|
| SD1 | Access | `GET /management/schools`: every management role (partner, super_admin, accountant), as mgmt-012/mgmt-025. Anyone else 403 "Management access required". Money only for the finance tier (partner, accountant, M13); the super admin's response has `money_visible: false` and every money value `null`, and the service never reads the ledger or the value columns for them |
| SD2 | Period | `from` / `to` IST calendar dates, default this month, through the shared `bdm_performance.period` (same 422s as mgmt-020/021) |
| SD3 | Schools contacted / Meetings / Proposals / MoUs | mgmt-020's School BDM figures for the period: `school_leads`, `meetings`, `proposals`, `mous` (equal by construction) |
| SD4 | Active schools | ENH-016 / ENH-022 rule: a tier set and not past `tier_valid_until`, today (IST). Basis "now" |
| SD5 | Students | Every school student record now (= ENH-016 `students.total`) |
| SD6 | Teachers, Parents | `school_teacher` / `school_parent` accounts belonging to a school by the ENH-008 rule, now. The total counts each account once (a parent with children at two schools is in both rows), so the parents total can be below the sum of the rows |
| SD7 | Career guidance | Students with a completed career guidance session (ENH-016 `career_guidance`) |
| SD8 | Psychometric tests | Students with a completed psychometric test (ENH-016 `psychometric`) |
| SD9 | Academic results | Students with at least one published academic result |
| SD10 | Student profile completion | The average ENH-012 portfolio completion % over the students (whole number); `null` ("No students") when there are none |
| SD11 | School revenue (figure) | Finance tier: the counted ledger income of the School projects vertical dated in the period (mgmt-005 `ledger.lines()`: approved manual entries, rupee automatic lines) |
| SD12 | School-wise revenue | Per school: the approved manual income entries tagged with the school (SD14), dated in the period, a reversal negative. The rest of SD11 is shown as "Not tagged to a school", so the rows plus that line equal SD11 |
| SD13 | Contract value, renewal value (Q-23) | Two new nullable columns on `schools`: `contract_value`, `renewal_value` (₹, ≥ 0, two decimals). Entered by the finance tier on this dashboard: `PATCH /management/schools/{id}` (partial; explicit `null` clears). Not period-bound. `null` reads "Not entered"; the totals add the entered values and count the schools not entered. Every change writes one `mgmt.school_value` audit row (finance kind, before/after values, MA3). The school admin forms and `SchoolOut` are untouched |
| SD14 | Ledger school tag (Q-23) | Optional `ledger_entries.school_id` (FK `schools`, RESTRICT), allowed only on **income** entries of the **School projects** vertical (422 on the field otherwise; DB CHECK). Part of the entry's editable fields, so create / edit / reversal copy / audit field names work as for the course tag. Ledger options list the schools; the form shows "School (optional)" for School projects income; the entry page shows it |
| SD15 | School table | Every school, ordered by name then id: name, tier, active, renewal due (ENH-016 D6: tier ends within 60 days or has ended), valid until, students, teachers, parents, career guidance, psychometric, academic results, profile completion; for the finance tier also revenue, contract value, renewal value. Student-based totals are the sum of the rows |
| SD16 | Data | Read side is read-only and returns counts, percentages, school names and rupees only — no student, parent or teacher identity |

Not added: per-school payment collection (no school payer exists), GST (M4), contract documents (the MoU reference stays as is).

## 3. API

- `GET /api/v1/management/schools?from=&to=` → `{from, to, as_of, money_visible, figures[{key,label,definition,basis}], totals{…},
  untagged_revenue, schools[…]}`.
- `PATCH /api/v1/management/schools/{school_id}` body `{contract_value?, renewal_value?}` (extra forbidden) → the school's values.
  Finance tier only (super_admin "Finance access required"; others "Management access required"); unknown school 404; negative or more
  than two decimals 422 on the field. Row lock, one commit with its audit row.
- Ledger: `LedgerEntryCreate/Update.school_id`, `LedgerEntryOut.school`, options `schools[{id,name}]`.

## 4. Data

Migration `0160_school_values`: `schools.contract_value`, `schools.renewal_value` `NUMERIC(14,2) NULL` with CHECK ≥ 0;
`ledger_entries.school_id UUID NULL` FK RESTRICT, CHECK `school_id IS NULL OR (kind = 'income' AND vertical = 'school')`, partial index
on `school_id`. Additive and nullable — no existing row changes. Downgrade refuses while any value or tag is set.

## 5. Tests (written first)

Backend `test_mgmt_022_schools.py`: access per role; figure order; SD3 equality with `GET /management/bdm?type=school`; SD4/SD5/SD7/SD8
equality with the ENH-016 summary; a built school's row (students, teachers, parents incl. a linked parent, guidance, psychometric,
results, completion); totals are the sums; super admin gets no money; tagged revenue, reversal and untagged line reconcile with SD11;
PATCH values (finance only, 404, 422s, clear, audit). Ledger tag: expense/other vertical/unknown school 422; reversal copies the tag;
options list schools; migration CHECKs equal the models. Web: vitest for the lib, the dashboard component (money / no-money, not entered,
empty) and the values editor; ledger form shows the school field only for School projects income; Playwright e2e for the page.

## 6. Plan

1. Migration + models + schemas (RED: migration/tag tests).
2. Ledger tag in `services/ledger.py` + `api/management_ledger.py` (RED → GREEN).
3. `services/management_schools.py` + routes (RED → GREEN).
4. Web lib + dashboard component + values editor + page + nav; ledger form/detail school field (vitest RED → GREEN).
5. Docs: DEC-SCOPE, API contract, RBAC matrix, backlog status. Browser QA + e2e.
