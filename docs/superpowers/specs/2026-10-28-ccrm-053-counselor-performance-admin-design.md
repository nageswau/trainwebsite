# ccrm-053 — Counselor performance: Overseas Admin view, intake filter, Overseas/IT lead split (design)

NO-ASSUMPTION MODE. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` §3 `ccrm-053`; owner answers Q7, Q7b (2026-10-28,
`MEETING_TRANSCRIPT_REQUEST`-equivalent). Builds on ccrm-036 (`DEC-SCOPE-269`) and mgmt-018. Decision: `DEC-SCOPE-325`. API §12HW,
RBAC §2.228. The owner asked this session to proceed with the recommended answers; every "my call" below is a default, not an approval.

## Intent

Owner line A10: "counsellor performance ---> leads, overseas/it, students, intake(filter), visas, enrollments". The overseas counselor
keeps their own report and gains the lead split and two filters; the Overseas Admin gets every overseas counselor on one page, can open
any counselor's full report, and can export the list.

## Decisions (PF1–PF10)

| ID | Decision | Basis |
| --- | --- | --- |
| PF1 | New period figures **Leads**, **Overseas leads**, **IT leads**: leads the counselor owns now (`Enquiry.owner_id`) created in the period (IST), split by `Enquiry.division`. Leads is Overseas + IT, so the split always sums to the total (AC3). | Q7b; definition mirrors ccrm-034 R9 "leads created in the period, owner = counselor" — my call |
| PF2 | **Intake** filter (`?intake=Sep 2027`, ccrm-047 format, else 422 with ccrm-047's message). It narrows the lead figures by `LeadQualification.intake` and the application figures (Now: applications, students, offers, visas, enrolments, documents pending; and the stage table) by `OverseasApplication.intake`. The mgmt-018 figures, follow-ups and tasks have no intake and are unchanged. Legacy free text that is not "Mon YYYY" never matches. | backlog Expected behaviour; edge case "legacy excluded" |
| PF3 | **Lead division** filter (`?division=overseas|it`, else 422) narrows the three lead figures only. | backlog "also usable as a filter" |
| PF4 | The counselor route stays self-only: `GET /counselor/performance` names nobody; an extra `counselor_id` is ignored (AC5). | backlog Authorization |
| PF5 | Admin routes under the existing admin prefix convention: `GET /overseas-admin/counselor-performance` (list), `.csv` / `.xlsx` (export, audited `counselor_performance.export`, committed before the file is returned), `GET /overseas-admin/counselor-performance/{counselor_id}` (that counselor's ccrm-036 report with the same filters). The backlog's `/overseas/admin/…` path is a page path; API admin routes are `/overseas-admin/…` (reminder rules, checklists) — my call. | backlog API impact |
| PF6 | Readers: Overseas Admin and Super Admin (Super Admin `NEEDS_CONFIRMATION` in the backlog; default included, as the CRM reports page). Everyone else 403, anonymous 401. A detail id that is not an overseas counselor is 404. | backlog roles |
| PF7 | Rows: every **active** overseas counselor (zeros listed), plus an inactive one only when any figure is non-zero ("included if any activity"). Sorted by name. | backlog edge cases |
| PF8 | Columns: Leads, Overseas leads, IT leads, Leads assigned, Calls, Counseling sessions, Conversions, Conversion %, Students, Applications, Visas pending, Visas approved, Visas refused, Enrolments. A Total row: counts summed; Students distinct across counselors; Conversion % from summed parts. No revenue. | Q7; mgmt-018 CS1/CS9 |
| PF9 | One grouped query per figure family over all counselors (mgmt-018 `_counts`, one lead query, one caseload query via `management_crm_reports._report`) — no per-counselor loop. | backlog Performance |
| PF10 | No migration. The optional `ix_overseas_applications_counselor_id` is deferred: the admin aggregation scans every application anyway, and open sibling branches hold migrations 0213/0214. | backlog "optional" |

## Screens

- `/overseas/counselor/reports` (counselor): ccrm-036 page + Intake (IntakePicker month/year) + Lead division select in the GET form;
  the period tiles gain Leads / Overseas leads / IT leads.
- `/overseas/admin/counselor-performance` (new, Overseas Admin nav "Counselor performance"): same filter form, the table (counselor name
  links to the detail with the same filters), Download CSV / Excel. Empty: "No overseas counselors yet."
- `/overseas/admin/counselor-performance/{id}`: the ccrm-036 report component for that counselor, with a back link.

## Acceptance criteria

AC1 counselor sees own report with intake filter; AC2 admin sees all counselors with correct counts; AC3 Overseas + IT = Leads;
AC4 intake narrows application figures; AC5 counselor cannot read another's figures (admin routes 403; `counselor_id` ignored);
AC6 CSV rows/columns match the screen. Plus: malformed intake/division 422; inactive counselor with no activity hidden.

## Non-goals

No revenue; no change to mgmt-018 `/management/counseling`; no Super Admin nav entry (they reach the page by URL — my call).
