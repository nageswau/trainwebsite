# hrc-034: Skill demand, portal analytics and data-quality dashboards -- design

**Decision:** `DEC-SCOPE-416` (builder's recommended calls, `NEEDS_CONFIRMATION`). **Source:** `HR_RECRUITMENT_CRM_BACKLOG.md` hrc-034, Appendix B
(`UNVERIFIED`, a requirements draft). **Depends on:** hrc-013, 014, 018, 027, 032, all merged.

## Intent

§14 asks for skill demand, candidate portal analytics and a data-quality dashboard; §17 asks that failed imports and notifications are visible
and retryable. The AC: **each figure ties out to its definition; a skill with zero supply is highlighted.**

## Non-goals

- hrc-033's five operational boards, and its `reports.recruitment` grant (a different audience and record scope).
- Anonymous visitors: the public careers pages are cached and have no person to attribute a view to.
- A new retry mechanism. Failed notices keep hrc-032's page; a failed import row is corrected and re-uploaded through hrc-013's import.
- Exports (the backlog asks for report endpoints only).

## Design

### Access (I1)
New catalogue resource `reports.recruitment_insights` (`view`), seeded by the migration for `hr_manager`, `placement_manager` and `partner`
(the management role); `super_admin` holds it implicitly. All three pages count the whole recruitment pool, so the grant is the only gate. No row
carries a candidate's name, phone, email or pay: candidate rows show the candidate code only.

### Skill demand (I2)
`GET /recruiter/recruitment-insights/skill-demand`
- **Demand** = distinct open jobs (`JOB_OPEN_STATUSES`) listing the Skills-Master skill, split required and preferred.
- **Supply** = distinct active pool candidates holding that skill directly: `pool_filter`, not archived, not merged.
- **Zero supply** = demand above 0 and supply 0; the page highlights it in text, not colour alone.
- Free-text job skills cannot have a supply, so they are one separate figure.

`GET .../skill-demand/vacancies?n=5`: Appendix B's *vacancies with insufficient candidates* = open jobs where `matching.matches` finds fewer than N
candidates, the same count as the requirement's own Matching page (hard filters included). N defaults to 5 (`NEEDS_CONFIRMATION`). Matching is
per job, so the newest 200 open jobs are checked and the answer says when more exist.

### Portal analytics (I3)
`GET /recruiter/recruitment-insights/portal-analytics?from&to` (`telecaller_performance.date_range`: default this IST month, at most 366 days).

`portal_events`: `kind`, `user_id`, `job_id`, IST `day`, `created_at`. Ids only, no PII. One row per user, job, kind and day (unique index, `ON
CONFLICT DO NOTHING`), so refreshes and double clicks cannot inflate it and growth is bounded.

| Event | Written when |
|---|---|
| `job_view` | a job card is returned to a student or candidate on the Jobs page (the page has no separate detail view) |
| `apply_start` | Apply reached a visible job, before the eligibility gates; committed first, so a refused attempt stays as a real drop-off |
| `apply_submit` | the application is created, in its own transaction |

The legacy student route `/workflows/it/jobs/{id}/apply` writes start and submit when it succeeds.

- **Registrations** = portal candidate accounts (`role = candidate`) created in the period; **verified** = those with a verified email.
- **Profile completion** = hrc-010's weights in SQL, banded 0-24, 25-49, 50-74, 75-99, 100, for active portal candidates right now.
- **Funnel** = distinct people per event in the period; **drop-off** = the previous step minus this one, never below 0.

### Retention (I4, Q-31)
A daily beat job deletes events older than 400 days: past the 366-day report limit. `NEEDS_CONFIRMATION` with Q-31. No rollup.

### Data quality (I5)
`GET /recruiter/recruitment-insights/data-quality` and `GET .../data-quality/{figure}?limit&offset`. Each figure's value and its rows come from
one source, so they cannot disagree:

| Figure | Definition | Source |
|---|---|---|
| Duplicate queue | Open pairs | `candidate_duplicates.queue` (equals the Duplicate Review page) |
| Failed imports | `candidate_import_rows` in `error` | hrc-013's rows |
| Failed notifications | Failed recruitment deliveries and recruiter emails | `notification_exceptions.page` (equals Delivery exceptions) |
| Incomplete profiles | Active pool candidates under 60% (`NEEDS_CONFIRMATION`) | I3's expression |
| Jobs missing fields | Open jobs without a required skill, description, on-site location, qualification, minimum experience, employment type or vacancies (`NEEDS_CONFIRMATION`: no source defines "required") | `jobs` |

A figure links to its action page only if the caller holds that page's grant (`candidates.merge`, `candidates.import`, `notifications.retry`).

### Frontend (I6)
`/recruiter/insights/{skill-demand,portal-analytics,data-quality}`, server-rendered from GET forms, so refresh, back and shared links keep the
state. Existing `kpi-grid`, `report-tablist`, `table compact stack` and `accessUnavailable`. One nav entry, "Recruitment insights".

## Review notes

- **Security:** every route needs the grant; a Jobs page view writes only jobs the caller was already shown; `apply_start` comes after the visibility
  check, so no event reveals a hidden job. Reads only on the reports. Failed-notification rows drop the recipient and error text.
- **Transactions:** events use `ON CONFLICT DO NOTHING`, so two tabs cannot collide; `apply_start` commits before the gates raise.
- **Regression:** hrc-027 gains one insert per listing; hrc-002's key test and the rec-038 route matrix get rows.

## Plan

1. Model, migration 0294, catalogue key, defaults and migration test.
2. Events on the Jobs page and apply routes, retention job, tests.
3. Report service, routes, rec-038 rows, tests (tie-outs, zero supply, N, access, empty period).
4. Web lib, pages, navigation, vitest.
5. e2e and browser QA at three widths. 6. Register docs (DEC, API, RBAC, RTM, backlog, Appendix B).
