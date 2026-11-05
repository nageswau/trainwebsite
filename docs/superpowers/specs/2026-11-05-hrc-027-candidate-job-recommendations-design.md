# hrc-027 — Candidate-facing job recommendations and apply (design)

Status: builder's design. Source `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-027` (PDF §7.1, §11 Recommended Jobs / All Open Jobs,
§13 "New matching vacancy", §17 QA #4–5; PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01 (backlog Q-00). The owner
said to proceed with the recommended answers, so J1–J12 below are **the builder's calls (`NEEDS_CONFIRMATION`)**.
Dependencies merged: hrc-008 (`DEC-SCOPE-385` visibility), hrc-018 (`DEC-SCOPE-392` engine, E12 `jobs_for_candidate`), hrc-022
(`DEC-SCOPE-386` candidate portal), hrc-026 (`DEC-SCOPE-394` application record).

## Intent
An IT student or an external candidate opens one Jobs page and sees, in three views, the open jobs they may see: the ones recommended for
them, the ones that match at least one of their skills, and all of them. Each card says why it matches and lets them apply.

## Acceptance criteria (backlog)
1. A candidate with matching skills sees the job under Recommended (§17 #4).
2. Non-matching open jobs are still listed under All Open Jobs.
3. The explanation is shown.
4. "Not a guarantee" text is shown (§17 #5).
- Edge: a profile with no skills → Recommended is empty, with a prompt to add skills.

## Builder's calls
| # | Question | Call |
|---|---|---|
| J1 | Who | `it_student` (division it) and hrc-022's `candidate`; anyone else 403. The caller's own candidate record only (no id in any URL, C10). |
| J2 | Which jobs | Exactly what hrc-008 lets a student apply to: open status, deadline not passed, visibility `portal`/`public`/their segments (`job_visibility.student_filter`, which works for any login linked to a candidate). |
| J3 | Recommended | The hrc-018 rule passes (all required skills, the job's switched-on hard filters) **and** score ≥ 50 (`RECOMMENDED_MIN_SCORE`, a constant; no admin setting yet). Highest score first, then newest. |
| J4 | Matching Your Skills | At least one required skill held (with its hrc-017 minimum level and related skills); a job with no required skill: one preferred skill. Includes the recommended ones. Score first (scored ones), then required skills matched, then newest. |
| J5 | All Open Jobs | Every job in J2, newest first, never hidden by score. Search `q` (title, company, location, skill names; case-insensitive; ≤ 100 characters) narrows all three views. The page answers `counts` per view for the tab labels. Paged: `limit` 1–100 (default 20), `offset`. |
| J6 | Card fields | Title, company (the public listing already publishes it), location, work mode, employment type, required and preferred skill names, experience range, deadline (`closes_on`), the match (score + hrc-018 candidate-audience explanation, or the skills sentence when it does not match), and the caller's application (code + candidate-visible stage) if any. **No salary** (no job salary is published today; hrc-018 E9). No requirement code, owner, client contact or internal note. |
| J7 | Apply gate | `POST /candidate/jobs/{id}/apply`: outside J2 (missing, closed, past deadline, not visible) = the same 404; already applied = 409; a switched-on hrc-018 hard filter not met (unknown value fails, E6) = 422 naming what is missing, salary without amounts. Required skills do **not** block applying (profiles are often incomplete; the recruiter screens) — they only rank. The card carries `can_apply` and the same reasons so the button is disabled before a click. |
| J8 | Legacy route | `POST /workflows/it/jobs/{id}/apply` (student) uses the same gate, so the rule cannot be bypassed. Its response is unchanged. |
| J9 | Creating a candidate | Reading never creates rows: a student without a linked candidate reads as a profile with no skills. Applying creates/links it as today (`applications.candidate_for_student`). A candidate uses `candidate_portal.own`. |
| J10 | Notices | The hrc-026 receipt is sent on apply. A candidate's notices link to `/it/careers/portal/jobs` (a student's keep `/it/student/job-applications`). The optional "new matching job" notice is **not built**: hrc-032 owns every §13 trigger. |
| J11 | Analytics | No `job_views` table (hrc-034 may add one). |
| J12 | Pages | `/it/careers/portal/jobs` (candidate shell, nav "Jobs") and `/it/student/jobs` (student shell, nav "Jobs"), one shared client board. The legacy job-reference apply form stays. |

## Shape
- `services/matching.py`: the skill test inside `evaluate` becomes `skill_hits(spec, facts)` and the hard-filter test becomes
  `hard_filter_gaps(spec, facts, today)`; `evaluate` calls both (behaviour identical, hrc-018 tests guard it).
- `services/candidate_jobs.py` (new): `listing(db, user, view, q, limit, offset)` and `apply(db, user, job_id)`.
  Performance: one query for the visible open jobs with their company, one for their job skills, one for the candidate's skills plus
  related skills; the full hrc-018 `spec`/`facts` only for jobs that share a skill with the candidate or have a hard filter on.
- `api/candidate_portal.py`: `GET /candidate/jobs`, `POST /candidate/jobs/{job_id}/apply` (no `main.py` change).
- Web: `lib/candidateJobs.ts`, `components/CandidateJobsBoard.tsx`, two pages, two nav entries.

## Non-goals / anti-goals
Never show internal/other-segment jobs or a salary; never reveal another candidate; no score caching; no new permission; no migration.

## Numbering
`DEC-SCOPE-398`; API §12KQ; RBAC §2.292; no migration.
