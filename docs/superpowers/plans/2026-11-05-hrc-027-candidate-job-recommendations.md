# hrc-027 Candidate job recommendations and apply — Implementation Plan

> **For agentic workers:** executed inline (native) in the hrc-027 session. Steps use checkbox syntax.

**Goal:** one Jobs page for IT students and external candidates with Recommended / Matching Your Skills / All Open Jobs and a gated apply.
**Architecture:** hrc-018's pure `evaluate` split into `skill_hits` + `hard_filter_gaps`; a new `services/candidate_jobs.py` builds the
listing and the apply; two routes on the existing `candidate_portal` router; one shared React board under two shells.
**Tech Stack:** FastAPI, SQLAlchemy async, pytest; Next.js App Router, vitest, Playwright.
**Spec:** `docs/superpowers/specs/2026-11-05-hrc-027-candidate-job-recommendations-design.md`

## Global Constraints
- Visible = `JOB_OPEN_STATUSES`, `closes_on` NULL or ≥ today, `job_visibility.student_filter`. Outside = 404 "Open job not found".
- `RECOMMENDED_MIN_SCORE = 50`. Views: `recommended` | `matching` | `all` (other → 422). `q` ≤ 100 chars. `limit` 1–100 default 20.
- Never a salary field or amount in any candidate response; disclaimer = `matching.DISCLAIMER`.
- No migration, no new permission. DEC-SCOPE-398, API §12KQ, RBAC §2.292.

## Review Focus
- Shared test DB is never truncated: tests assert membership of their own tagged jobs, use `q=<tag>` for exact sets.
- A student with no candidate row: GET must not insert one (assert count unchanged).
- Segment/internal job: absent from every view and 404 on apply (both routes).
- Double-click apply: second POST 409, button disabled while busy.
- Card for a job with a hard experience filter and a candidate without experience: `can_apply` false with the reason; POST 422.

### Task 1: matching refactor
**Files:** `apps/api/app/services/matching.py`; test `apps/api/tests/test_hrc_027_candidate_jobs.py`
**Produces:** `skill_hits(spec, facts) -> dict[UUID, bool]`; `hard_filter_gaps(spec, facts, *, today) -> list[str]` (keys in
`HARD_FILTERS` order); `evaluate` unchanged in behaviour.
- [ ] tests: hard gap for missing experience → `["experience"]`; hrc-018 + rec-016 suites stay green.
- [ ] implement, run `test_hrc_018_matching_engine.py test_rec_016_matching.py test_hrc_027_candidate_jobs.py`.

### Task 2: listing service + GET route
**Files:** create `apps/api/app/services/candidate_jobs.py`; modify `apps/api/app/api/candidate_portal.py`.
**Produces:** `GET /api/v1/candidate/jobs?view&q&limit&offset` → `{view, q, items[], total, counts{recommended,matching,all}, limit,
offset, reason: "no_skills"|null, disclaimer, threshold}`; item keys `id,title,company,location,work_mode,employment_type,
required_skills,preferred_skills,experience_min_months,experience_max_months,closes_on,match{score,explanation}|null,skills_text,
matches_skills,recommended,application{code,status_label}|null,can_apply,blocked[]`.
- [ ] tests (RED first): AC1 recommended contains a matching job; AC2 non-matching job only in `all`; AC3 explanation present;
  AC4 disclaimer; no-skills reason; segment job hidden; 403 for recruiter; candidate role works; no salary keys; student GET creates no
  candidate; search by tag; 422 bad view.
- [ ] implement; run tests.

### Task 3: apply
**Files:** `services/candidate_jobs.py`, `api/candidate_portal.py`, `api/workflows.py` (legacy gate), `services/applications.py`
(candidate notice link).
- [ ] tests: candidate applies → 201 code `JA-`, receipt notice action_url `/it/careers/portal/jobs`; duplicate 409; hard filter 422 on
  both routes; past deadline/segment 404; card shows `application` afterwards.
- [ ] implement; run tests + `test_hrc_026_application_record.py test_hrc_008_visibility.py`.

### Task 4: web board + pages + nav
**Files:** create `apps/web/lib/candidateJobs.ts`, `apps/web/components/CandidateJobsBoard.tsx`, `apps/web/app/it/careers/portal/jobs/page.tsx`,
`apps/web/app/it/student/jobs/page.tsx`; modify `apps/web/lib/candidatePortal.ts` (nav), `apps/web/lib/navigation.ts` (student "jobs");
tests `apps/web/tests/components/CandidateJobsBoardHrc027.test.tsx`.
- [ ] vitest: tabs with counts; card explanation + disclaimer; no-skills prompt; apply success replaces button with "Applied"; error
  shown; disabled with reason when `can_apply` false.
- [ ] implement; tsc, eslint, vitest affected; fix nav tests that pin exact menus.

### Task 5: e2e + docs
- [ ] `apps/web/tests/e2e/hrc-027-candidate-jobs.spec.ts`: student sees views, applies; candidate portal page loads.
- [ ] Docs: DEC-SCOPE-398, API §12KQ, RBAC §2.292, RTM row, backlog status line.
