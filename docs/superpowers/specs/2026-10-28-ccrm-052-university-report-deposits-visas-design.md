# ccrm-052 — University-wise report: deposits, visas and drill-down (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` `ccrm-052` (owner line A6 "university wise report for overseas admin", Q9 — no
commission). Builds on ccrm-034 (`DEC-SCOPE-267`) and ccrm-035 (`DEC-SCOPE-268`). The owner pre-authorised the recommended answers;
every builder's default below is `NEEDS_CONFIRMATION`.

## Intent

The Overseas Admin (and the existing readers: partner, super_admin) need one university-wise view: how many applications paid a
deposit and how their visas went, and which applications make up a row.

## Behaviour

1. `GET /management/crm-reports` → `universities` rows and total gain four additive counts (existing keys unchanged):
   - `deposits_paid` — applications with a paid deposit: the counselor's record (ccrm-025) `paid_to_university` / `paid_via_edusphere`,
     or the agency deposit (AGN-011) `paid` / `remitted`. An application has at most one of each and never both, and the count is of
     applications, so a deposit counts once per application (AC2).
   - `visas_approved`, `visas_refused`, `visas_pending` — per application, from its visa cases, first match wins: any case approved →
     approved; else any refused → refused; else any case submitted / additional info requested / decision pending → pending. An
     application is in at most one bucket. Withdrawn applications are not counted in the visa columns.
2. The export (`/crm-reports/export?report=universities`) appends the four columns after the existing ones (order preserved).
3. New `GET /management/crm-reports/universities/{university_id}/applications` — the same filters and roles (`require_crm_reports`);
   the applications behind that university's row: application code, student, course, intake, stage, counselor, deposit paid, visa
   bucket. Newest first, 100 per `page` (1-based); `total` equals the row's Applications count (AC5). Unknown university → 404; bad
   filters → 422 like the report.
4. UI: on both report pages the university name links to `<home>/universities/<id>?<filters>`, a page listing those applications
   with a back link to the report (filters kept), empty / error / access states as the report page has them.

## Defaults (`NEEDS_CONFIRMATION`)

- D1 a refunded agency deposit is not "paid".
- D2 visa first-match rule above; withdrawn excluded (backlog edge).
- D3 a university with no matching applications is not listed (as today).
- D4 the drill-down is not exported (the backlog asks the report's export to carry the new columns only).

## Non-goals

No commission (Q9). No migration. No RBAC change: same three readers. No change to other reports.

## Plan (TDD)

1. RED/GREEN pytest `tests/test_ccrm_052_university_report.py`: AC1 visas 2/1, AC2 deposit once, AC3 filters, AC4 export columns,
   AC5 drill-down rows = count, 404/422/403/401, pagination. Update the pinned export header in `test_ccrm_035_exports.py`; add the
   new route to the ccrm-041 matrix.
2. Service `_universities` + `university_applications`; schemas; route.
3. RED/GREEN vitest: report links the university; drill-down component renders rows / empty state.
4. Pages under both homes; Playwright `ccrm-052-university-report.spec.ts`.
5. Docs: DEC-SCOPE, API §, RBAC note, RTM, backlog status.
