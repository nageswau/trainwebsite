# pob-015 — Vacancy sharing with institutions, campus calendar and outcomes (design)

- **Feature:** `pob-015` (`docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md`), decision `DEC-SCOPE-426`.
- **Source:** backlog §6.2 "share relevant vacancies with the institution and coordinate student applications, screening and interview
  schedules", "track MoUs, campus recruitment calendars, student participation and placement outcomes"; §15 TPO widget. Source
  classified `UNVERIFIED`.
- **Authority:** the owner assigned pob-015 on 2026-11-07 and said to proceed with the recommended answers, so V1–V14 below are **the
  builder's calls (`NEEDS_CONFIRMATION`)** answering Q-12. Dependencies pob-013 (`DEC-SCOPE-410`), pob-014 (`DEC-SCOPE-425`) and hrc-008
  (`DEC-SCOPE-385`) are merged.

## Intent

The placement team tells a college's TPO about open vacancies and needs a record of what was shared, when, how, with which template and
what the college answered. The team and the college BDMs also need one place that shows every campus date (drives, the colleges'
placement calendars and graduating batches), and per college the outcomes of its students: how many applied, were shortlisted,
interviewed, offered and joined.

## Goals / non-goals

- AC1 a shared vacancy appears on the college's timeline (the placement view's "Vacancies shared" list, newest first).
  AC2 outcomes count the institution's external candidates (pob-014 imported students and drive-tagged applicants).
  AC3 the campus calendar shows drives and batches (and the pob-013 placement calendar entries).
- Also: a TPO partnerships widget (feeds pob-028), an ICS download of the calendar.
- Non-goals: sending the message (the pob-023 composer sends; this records the share); new drive statuses; drives across several
  colleges; changing the bdm-021 college business metric; any BDM route.
- Anti-goals: sharing an `internal` (staff-only, hrc-008) or closed requirement; an institution student the viewer may not see (pob-014
  S6) counted or named anywhere; a placement write that touches the BDM organisation row or BDM metrics.

## Builder's calls (`NEEDS_CONFIRMATION`)

- **V1 Share record.** `institution_vacancy_shares`: college (a pob-013 college), requirement (`jobs.id`), shared on (a date, not in the
  future, IST), channel (`email`, `whatsapp`, `call`, `meeting`, `visit`, `other` — pob-013's TPO channels minus none), optional template,
  notes ≤ 500, response (`awaiting` default, `interested`, `declined`, `no_response`), response note ≤ 500, responded at/by, creator.
- **V2 Who shares.** The college's pob-013 writers (placement team, super_admin, the assigned BDM; managers read only) **and** the
  requirement must be in the caller's requirement scope (`recruiter_requirements.load_scoped`, 404 "Requirement not found").
- **V3 Only visible vacancies (hrc-008).** The requirement must be live (`_ACTIVE` statuses: received through selected) and not
  `internal` — 422 "Only open vacancies that are not internal can be shared".
- **V4 Template.** Optional; one the caller may use in a composer (pob-023 `usable_template`, else 404) of category `college_tpo` (422
  otherwise). Recording marks the template used (pob-023 G7).
- **V5 Duplicates.** Unique `(organization_id, job_id, shared_on, channel)`: a double submit is 409 "This vacancy was already recorded as
  shared on that day by that channel" (the unique index decides a race).
- **V6 Response.** `PATCH …/vacancy-shares/{id}` `{response, response_note}` by the same writers (requirement scope not re-checked: the
  response belongs to the college). Same values = no change (no audit). Shares are never deleted.
- **V7 Outcomes.** Per college: applications whose candidate is the college's (`candidates.institution_org_id`) **or** that were added
  through a drive at the college (`job_applications.drive_id` → `recruitment_drives.college_org_id`), counted once. Stages reuse rec-029's
  definitions: applications, shortlisted (reached shortlisted+), interviewed (a held interview), offered (an offer row, or reached
  selected/joined), joined. Plus `external` = of those, applications by candidates with no EduSphere login. Institution students the viewer
  may not see (pob-014 `institution_pool.visible`) are left out, so a viewer outside the agreement gets smaller figures, never names.
- **V8 Calendar.** `GET /recruiter/campus-calendar?from&to` (≤ 92 days; default this month) over the caller's pob-013 college scope:
  drives at those colleges (code, date, job role, status; no company, as P14), placement calendar entries (overlapping the window), batch
  pass-out dates. Optional `college_id`. Each item: kind, date, end date, title, detail, the college (id, code, name). At most 500 items
  with `truncated`. Ordered by date, kind, title.
- **V9 ICS.** `GET /recruiter/campus-calendar.ics` with the same parameters, all-day events through `services.calendar_ics`.
- **V10 TPO widget.** `GET /recruiter/campus-summary`: colleges in scope, vacancies shared in the last 30 days, shares awaiting a
  response, campus entries in the next 30 days, and the V7 outcomes over every college in scope.
- **V11 Drive statuses / several institutions (Q-12).** Unchanged: a drive stays one company at one college; a vacancy shared with several
  colleges is one share per college, and V7 counts each college's own students wherever they applied. More statuses stay `NEEDS_CONFIRMATION`
  (the source's labels are not in the repository).
- **V12 Readers.** pob-013 P3 for everything here (placement team, placement manager, college-module BDMs in their bdm-002 scope,
  super_admin; others 403; out of scope 404).
- **V13 Audit/logs.** `bdm_organization.placement_vacancy_share` / `placement_vacancy_response` in the write's transaction, ids only.
- **V14 Web.** A `CollegeVacancies` section (shares + share form + outcomes) under the placement section on the recruiter college page and
  the BDM organisation detail; `/recruiter/campus-calendar` and `/bdm/campus-calendar` (same component) with the TPO widget on top; menu
  entries "Campus calendar" for recruiters, placement managers and BDMs.

## API (`/api/v1`, §12LS)

| Method | Path | Who |
|---|---|---|
| GET | `/recruiter/colleges/{org_id}/vacancies` | V12 readers |
| GET | `/recruiter/colleges/{org_id}/vacancy-options?q=` | college writers (V2) |
| POST | `/recruiter/colleges/{org_id}/vacancy-shares` | college writers + requirement scope |
| PATCH | `/recruiter/colleges/{org_id}/vacancy-shares/{share_id}` | college writers |
| GET | `/recruiter/campus-calendar`, `/recruiter/campus-calendar.ics` | V12 readers |
| GET | `/recruiter/campus-summary` | V12 readers |

Writes: scope (404), org row lock, role (403), archived (409), validation, change, audit, one commit; they return the vacancies view.

## Data (migration `0307_institution_vacancy_shares`, guarded, additive)

One table, FKs `ON DELETE RESTRICT`, checks on channel/response/notes, the V5 unique index, index `(organization_id, shared_on)` and
`(job_id)`. Downgrade drops it.

## Tests

API: AC1–AC3, V2–V6 refusals, V7 (external, drive-tagged, counted once, hidden institution students), V8 window/scope, ICS, widget,
audit, migration guard, rec-038 rows. Web: vitest for the section and calendar; Playwright: share → listed → respond; calendar shows a
drive and a batch.
