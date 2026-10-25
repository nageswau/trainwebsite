# ccrm-034 — Management CRM reports (design)

NO-ASSUMPTION MODE. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-034` (source PDF §13 report table, §4 conversion by intake,
§18 AC 8; the PDF is `UNVERIFIED` and not in the repository — only the backlog's wording is used). Dependencies ccrm-014 (sub-status),
015 (outcomes), 019 (checklist readiness), 023 (offers), 026 (visa), 027 (confirmed enrolment) are merged on `origin/main`.

## Requirement (backlog, verbatim scope)

Six reports: application ageing (by stage/sub-status, days since last update); university performance (applications, offers, offer rate,
rejections, acceptances, enrolments); visa outcomes (submitted, pending, approved, refused, enrolled); document readiness (applications
blocked); lead conversion by intake; forecast by intake (method `NEEDS_CONFIRMATION`). Every report shows **student count and application
count separately** and its metric definitions. Filters: date, counselor, destination, university, course, intake — no team filter (CC3).
Roles: partner, super_admin, overseas_admin.

## Alternatives considered

1. **Extend `/management/applications` (mgmt-024)** with the six reports — rejected: that route is the operational tier only and its
   response contract is the funnel; overseas_admin would have to be added to a Command Center route it cannot otherwise open.
2. **Six routes, one per report** — rejected: one page shows all six with one filter set; six routes repeat the filter parsing and the
   access check six times.
3. **One read-only route `GET /management/crm-reports`, one service module, one shared React component on two pages**
   (`/management/crm-reports` for the Command Center, `/overseas/admin/crm-reports` for the Overseas Admin) — **chosen**. Nothing stored,
   no migration, a fixed number of SELECTs (one per report plus the options).

## Recommended defaults (`NEEDS_CONFIRMATION`; the owner asked for an autonomous run with recommended answers)

- **R1 Access.** partner, super_admin, overseas_admin read every report; accountant and everyone else 403. No revenue appears, so no
  finance tier. Counselors do not see this route (their own figures are ccrm-036).
- **R2 Filters.** All optional, ANDed. Date = the application's created date (IST, inclusive) — for the lead report the lead's created
  date; counselor = the application's counselor (`none` = no counselor) / the lead's owner; destination = the university's country / the
  lead's preferred country; university, course = the application's (not applicable to leads — the page says so); intake = the
  application's intake / the lead's qualification intake. End before start → 422. Malformed id → 422.
- **R3 People.** "Students" = distinct people behind the counted applications: the agency student, else the school student, else the user
  (mgmt-003 MS4 rule). A lead report's "students" = distinct converted students.
- **R4 Open application.** Not withdrawn, not enrolled, no terminal outcome (ccrm-015 `TERMINAL`). On hold and deferred are open.
- **R5 Ageing.** Open applications grouped by stage, then sub-status ("Not set" when none). Days since last update = IST today − the
  application's `updated_at` date. Bands 0–7, 8–14, 15–30, 31–60, over 60 days; plus the oldest.
- **R6 University performance.** Per university: applications, students, offers (mgmt-024 MF6 — the same predicate), offer rate =
  offers ÷ applications, rejections (outcome `rejected`), acceptances (an offer the student accepted, ccrm-025), enrolments (confirmed,
  ccrm-027 E4). Sorted by applications.
- **R7 Visa outcomes.** Per destination country, over applications with a visa case: submitted (visa status reached Submitted), pending
  (Submitted / Additional information requested / Decision pending), approved, refused, enrolled (approved and enrolment confirmed).
- **R8 Document readiness.** Open applications not yet submitted (stage before Offer, no submitted date, sub-status before Submitted),
  grouped by stage: ready (checklist with every required item complete, ccrm-019 AC1 rule in SQL), blocked (not ready, gate `block`),
  needs override (not ready, gate `warn`), no checklist.
- **R9 Lead conversion by intake.** Overseas-division leads per qualification intake ("Not recorded" when blank): leads, converted
  (status Converted now), conversion %, converted students, their applications.
- **R10 Forecast by intake (method).** Per application intake: confirmed enrolments; expected = open applications with the visa approved,
  not yet enrolled; possible = open applications at Offer or later without a visa approval; lost = terminal outcome or withdrawn;
  **forecast = confirmed + expected**. No probability weighting.

## API (§12FR)

`GET /api/v1/management/crm-reports?date_from&date_to&counselor&country&university&course&intake` → `{filters, as_of, options,
definitions: {report: [{key,label,definition}]}, ageing, universities, visa, readiness, leads, forecast}`. Each report has `rows` and a
`total` row; every row has `applications` and `students` (leads: `leads` and `students`). Read-only, no audit (reads are not audited
elsewhere in the Command Center).

## Frontend

`lib/managementCrmReports.ts` (types, filter parse — mgmt-024's idiom, URL builders), `components/ManagementCrmReports.tsx` (GET filter
form, six table sections each with its definitions, empty state per report), pages `app/management/crm-reports/page.tsx` and
`app/overseas/admin/crm-reports/page.tsx`. Command Center pillar entry "CRM reports" (Students), Overseas Admin sidebar "CRM reports",
Super Admin sidebar "Management CRM reports". Tables scroll horizontally on narrow screens inside their card.

## Security

Role check before any query; only counts, labels (university, country, intake, stage names) leave. No student names, no refusal reasons,
no money. SQL via SQLAlchemy only; intake is a bound parameter.

## Tests

`apps/api/tests/test_ccrm_034_reports.py` (each test makes its own university/intake so the shared seeded DB does not interfere): access
matrix; each report's definitions with seeded rows; students vs applications counted separately; filters narrow; 422s.
`apps/web/tests/lib/managementCrmReports.test.ts`, `tests/components/ManagementCrmReports.test.tsx`,
`tests/e2e/ccrm-034-crm-reports.spec.ts`.

## Regression risks

Reuses `management_metrics.FUNNEL_COUNTS["offer"]` and `application_options` read-only; no shared definition changes. Nav arrays gain one
entry each.
