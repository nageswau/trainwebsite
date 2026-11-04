# hrc-008 — Vacancy visibility (internal, portal, segment, public)

**Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-008` (PDF §4.2 Visibility, §4.3, §13; PDF classified `UNVERIFIED`).
Dependency hrc-007 (`DEC-SCOPE-380`) is merged. The owner said to proceed with the recommended answers, so V1–V8 are **the builder's
calls (`NEEDS_CONFIRMATION`)** answering Q-08. Decision `DEC-SCOPE-385`, migration `0262_job_visibility`, API §12KD, RBAC §2.281.

## Builder's calls

| # | Call |
|---|---|
| V1 | `jobs.visibility` is one of `internal`, `portal`, `segment`, `public`. A `segment` job names one talent pool (`segment_pool_id`, rec-015); no other job does (check constraint). |
| V2 | A "candidate segment" is a **talent pool** (rec-015). A program cohort is not offered (no cohort is a candidate set today; `NEEDS_CONFIRMATION`). A pool's members are computed on read, so a student who stops matching stops seeing the job; an application already made stays (E). An inactive pool has no members. |
| V3 | Q-08: every **existing** job and every **new** job defaults to `public` (server default), so no current listing disappears and no create path changes. A manager narrows it afterwards. |
| V4 | Changing visibility needs `jobs.publish`. First default holder: `placement_manager` (migration 0262 seeds it; super_admin implicit; grantable to any role). A holder may change any job (a division-wide grant, like `jobs.approve`). |
| V5 | Readers: `/public/jobs` and `POST /public/jobs/{id}/apply` → `public` only. The student surfaces (`/workflows/it/jobs/open` for `it_student`, `POST /workflows/it/jobs/{id}/apply`, the student portal's "Open jobs" panel) → `portal`, `public`, and `segment` when the student's candidate is a member. A job outside the caller's visibility is the same 404 as a missing one. Staff lists and dashboards are unchanged (internal staff see every job). |
| V6 | Visibility never touches existing applications: the student's own application rows read through `job_applications` and stay visible (AC3). |
| V7 | `PUT /recruiter/requirements/{id}/visibility` `{visibility, segment_pool_id?}` → the requirement detail. 403 without the grant (before the body is read), 404 unknown job, 422 a segment without an active pool or a pool on a non-segment job. Same values = no change (no audit). A change is one audit row `recruiter_requirement.visibility` with a `changes` diff (pool by name), bumps `updated_at`/`updated_by`. |
| V8 | The sitemap lists no job URLs (verified: `apps/web/app/sitemap.ts` holds fixed paths only), so an internal job cannot leak there; a vitest pins it. The employer's `visible_to_students` is false for an `internal` job. |

## Design

- **DB:** `jobs.visibility varchar(10) NOT NULL DEFAULT 'public'` + `ck_jobs_visibility`; `jobs.segment_pool_id uuid NULL` FK
  `talent_pools(id) ON DELETE RESTRICT` + `ck_jobs_segment_pool`; index `ix_jobs_status_visibility (status, visibility)`.
- **Service:** `app/services/job_visibility.py` — `public_filter()`, `student_filter(db, student)` (one query for the student's candidate,
  one resolution of the referenced active pools' terms, one FILTERed count per pool) and `visible_to_student(db, student, job)`.
- **API:** the readers in `public.py`, `workflows.py`, `services/portal.py` add the filter; `recruiter_requirements.py` adds the PUT; the
  detail gains `visibility {key, label, segment_pool, can_change}` and list rows gain `visibility`.
- **FE:** `RequirementVisibility` card on the requirement detail page: the current visibility for every reader; a holder gets a select
  (and a talent-pool select for Segment) with a Save button, loading/error states and a success notice.

## Acceptance criteria → tests

1. Internal job absent from public + portal endpoints and the sitemap → `test_hrc_008_visibility.py`, `sitemap` vitest.
2. Segment job visible only to the segment's members → `test_segment_job_is_visible_only_to_pool_members`.
3. Closed job leaves public views; existing applications stay → `test_closed_job_leaves_public_views_application_stays`.
4. `+` a public job is on `/public/jobs`; `−` applying to an internal job through the public route is 404; `E` a student who stops matching keeps the application.
5. Grant: recruiter 403, manager 200, audit row; 422 validation.

## Regression risks

The careers page, `test_emp_*`, the student job list, the rec-007 requirement detail shape (additive keys only).
