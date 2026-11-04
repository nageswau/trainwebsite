# hrc-009 — Eligibility-change review and vacancy-change notices (design)

- **Feature:** hrc-009 (`docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md`). **Decision:** `DEC-SCOPE-390` (builder's calls R1-R9 below,
  `NEEDS_CONFIRMATION`). **Migration:** `0267_application_review`. **API:** §12KJ. **RBAC:** §2.286 (no new permission).
- **Dependencies (merged):** hrc-004 (#445, before/after audit), hrc-006 (#453, job owners), itc-002 (#409, `notify()` event types).
- **Source:** §4.3 "Significant changes to eligibility criteria should trigger a review of affected applications rather than silently
  disqualifying"; §12/§13 "Notify relevant owners when a vacancy changes".

## Intent
Matching is live, so an eligibility edit silently changes who fits a vacancy. Nothing tells the people already working its applications.
hrc-009 flags the open applications for review, notifies the vacancy's owners once with a count, and lets the recruiter **confirm** each
flagged application (it stays where it is) or **move** it (any status change). Nothing is ever rejected automatically.

## Acceptance criteria (backlog AC + edge)
1. A required-skill change flags the open applications (`needs_review_since` set).
2. A cosmetic change (description, title, salary, ...) flags nothing.
3. The owners are notified once per change, with the count.
4. A job with 0 open applications produces no notice.
5. Nothing is rejected automatically: statuses are untouched by the flag.

## Builder's calls (DEC-SCOPE-390, NEEDS_CONFIRMATION)
- **R1 eligibility** = what `matching.plan` uses plus qualification: the required skills (case-insensitive names), the experience range
  (min, max months), the qualification (trimmed, case-insensitive) and the location as matching sees it (`location` lower/trim; none when
  `work_mode` is remote). City/state/country edits count through the derived `location` (hrc-005 V3). Preferred skills, skill weights,
  certifications and every other field are not eligibility.
- **R2 open applications** = `applications.OPEN` (sourced, screened, shortlisted, profile shared, interview). Selected/joined/rejected/
  withdrawn are never flagged.
- **R3 the flag** = `job_applications.needs_review_since` (timestamptz, NULL = no review). One bounded `UPDATE ... RETURNING` per job edit;
  an application already flagged keeps its first time and is not counted again.
- **R4 clearing:** any status move (recruiter route, legacy writers, joining) clears it ("moved"); `POST /recruiter/applications/{id}/
  confirm-review` clears it without a move ("confirmed"), audited `recruiter_application.review_confirmed`. Confirming an unflagged
  application = 409.
- **R5 recipients** = the vacancy's owners (hrc-006: primary recruiter, placement-officer owner, collaborators) minus the editor (the
  hrc-012 O10 precedent: the editor sees the result on the page). One notice per owner per edit (`notify()` dedups per transaction).
- **R6 event** `it.requirement.review_needed` (entity `job`), fixed text with only the count: "Applications to review: {count}. A
  vacancy's eligibility criteria changed. Open EduSphere to confirm or move them." `notify()` gains an optional `count` (an int, never
  free text) that fills `{count}`; events without the placeholder refuse it. Link: `/recruiter/requirements/{id}`.
- **R7 hooked paths:** every job edit path — recruiter `PATCH /recruiter/requirements/{id}`, employer `PATCH /employer/jobs/{id}`, legacy
  `PATCH /workflows/it/jobs/{id}` — snapshot eligibility before the change, flag after, same transaction.
- **R8 review list:** `GET /recruiter/requirements/{id}/candidates?needs_review=true` (same scope/404 as the list); every list response
  carries `needs_review_count`; every application item carries `needs_review_since`.
- **R9 who confirms:** the application writers (`applications.WRITERS`: the requirement's recruiter, super_admin) — the same gate as a
  status move. Readers see the badge only.

## Alternatives considered
- A separate review table (who/why/when per change) — richer, but the backlog asks for one column; the audit log carries the confirm.
- Re-scoring candidates (before/after match) to flag only those who stop matching — the source says review, not disqualify; flagging
  every open application is simpler and never hides one. Rejected.

## Design
- `services/matching.py`: `eligibility(db, job) -> tuple` (R1), reusing the location rule.
- `services/application_review.py` (new): `flag(db, actor, job, before) -> int` — compare, bulk UPDATE, notify owners (R5/R6), log
  `application_review_flagged` (ids and counts only); `confirm(db, actor, application)`.
- `services/applications.py`: `_record` clears `needs_review_since`; `item_out` adds it.
- Routes as R4/R7/R8. Transactions: each route keeps its one commit; the recruiter PATCH already holds the job row lock.
- Web: `RecruiterRequirementCandidates` shows a "Needs review" badge per flagged item, a banner "N applications need review after an
  eligibility change" with a "Show only these" toggle (server filter), and a "Confirm review" button for writers. The detail page passes
  `r.updated_at` so the list re-reads after an edit.

## Tests
- pytest `test_hrc_009_review.py`: AC1-AC5, R1 field-by-field (experience, qualification, location, remote), preferred-skill-only change,
  already-flagged not recounted, confirm/409/403/404, status move clears, list filter + count, employer path, notify count validation.
- pytest `test_hrc_009_migration.py`: chain + round trip.
- vitest: candidates component badge/banner/filter/confirm. Playwright e2e `hrc-009-eligibility-review.spec.ts`.

## Plan (small tasks, TDD)
1. Migration + model column; migration test. 2. `notify(count=)` + event; unit test. 3. `matching.eligibility` + `application_review`;
service tests. 4. Hook the three edit paths; route tests. 5. Clear on status move; confirm route; list filter/count. 6. Web lib types +
component; vitest. 7. e2e. 8. Docs: decision register, API §12KJ, RBAC §2.286, backlog status.
