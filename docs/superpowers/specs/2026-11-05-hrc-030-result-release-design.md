# hrc-030 — Result approval and release (design)

**Decision:** `DEC-SCOPE-409` (builder's calls R1–R13, `NEEDS_CONFIRMATION`). **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md`
hrc-030 (PDF §9 "publish only after release conditions"; §10.2 "Release results automatically only if configured; otherwise require
approval and a Publish Result action"; §13 "Feedback submitted → approval queue; Result approved → publish + notify"; §17 QA "results
remain hidden until … release … appear only in the correct candidate account"; PDF classified `UNVERIFIED`). Scope approved by the owner
2026-11-01 (backlog Q-00); the owner said to proceed with the recommended answers, so Q-30 and the open points are answered by the calls
below. Dependencies hrc-002 (`DEC-SCOPE-374`), hrc-028 (`DEC-SCOPE-400`) and hrc-029 (`DEC-SCOPE-405`) are merged.

## Intent
Today a recruiter's interview decision (rec-020 status / rec-021 feedback: Selected or Rejected) moves the application at once, and the
candidate's own view of the application (`candidate_status`, hrc-026 A4) moves with it — the candidate learns the outcome before anyone
approved telling them. hrc-030 puts a release step between the decision and the candidate: the decision becomes a **result** that waits for
an approver holding `results.release` (the HR Manager by default), who publishes it with a candidate-facing message. Only then does the
candidate see it (application stage, "My results", interview card) and get notified. A global setting can switch to auto-release.

**Non-goals:** a full candidate portal "My Results" section (hrc-031 builds the portal; this adds one card); withdrawing a released result;
employer/interviewer views of decisions; backfilling past decisions.
**Anti-goal:** an unreleased result (outcome, message, or the Selected/Rejected stage it causes) reaching any candidate or student API,
notification or offer.

## Builder's calls (R1–R13)
- **R1 Result record.** `interview_results`: one row per decided interview (unique `interview_id`) — `application_id`, `outcome`
  (`selected`|`rejected`), `is_final` (the decision decides the application: any Rejected, or Selected on a deciding round — rec-020 IV8),
  `state` (`pending_approval`|`released`), `candidate_message` (≤1000), `release_mode` (`auto`|`approval`, set on release),
  `decided_by_user_id`, `released_by_user_id`, `released_at`, timestamps. Checks: released ⇔ `released_at`, `released_by`, `release_mode`
  and a message are set. The round result and the application's final decision are the same row (`is_final` marks the final decision) —
  one table, no second "final decision" table.
- **R2 "Draft" is not stored.** A result exists only once a decision is recorded, and recording the decision *is* the submission (§13
  "Feedback submitted → approval queue"). No evidence of a pre-submission stage.
- **R3 What the decision does now.** `interviews.change_status` into Selected/Rejected (the status route and rec-021 feedback) and the
  legacy `/workflows/it/interviews` PATCH that moves the status record the result. The application still moves internally exactly as
  before (offers, pipelines, reports unchanged), but `candidate_status` is **held** (`applications.follow(..., visible=False)`) until
  release. On Hold is not a result (hrc-001 H3 keeps showing it as Completed).
- **R4 The setting (Q: per-job or global).** One global row `result_release_settings` (`auto_release`, default **false** = approval, as
  the PDF's default). `results.release` holders read it; only super_admin changes it (hrc-007's settings precedent). A per-job override is
  `NEEDS_CONFIRMATION` (no evidence which jobs differ). With auto-release on, the decision is released in the same transaction
  (`release_mode=auto`, released by the decider, the default message).
- **R5 Approver.** `results.release` (declared by hrc-002 R4), default holder `hr_manager` (migration seeds it; super_admin holds all). The
  queue is division-wide like `jobs.approve`. An approver cannot publish a decision they recorded themselves (403, hrc-007's "own job"
  precedent) — `can_release` is false on those.
- **R6 Release.** `POST /recruiter/interview-results/{id}/release {candidate_message?}`: the message (default text if omitted/blank) is
  stored; state → released; if `is_final` and the application is still at that outcome, `candidate_status` moves to it; the candidate is
  notified once — in-app plus their delivery channels for a portal user (student/candidate), else a queued email when SMTP is configured
  and the candidate has an email. The notice carries the candidate-facing message only, never feedback or scores. Audited as
  `interview_result.release` (ids, outcome, mode; never the message). Releasing twice is 409.
- **R7 Q-30: no withdrawal.** A released result is final (it has already been sent). A correction is a new message by the recruiter.
  `NEEDS_CONFIRMATION`.
- **R8 Offers.** `rec-022` offer creation is refused (409 "Publish the interview result before making an offer") while the application
  has an unreleased final result — an offer is visible to the student and would reveal the selection.
- **R9 Candidate view.** `GET /api/v1/candidate/results` (candidate and IT student, hrc-027's `_job_seeker` gate): the caller's own
  released results only — round, role, company, outcome label ("Selected" / "Not selected"), message, released date. The student's
  interview schedule shows the outcome label once released (still Completed before).
- **R10 Recruiter view.** Every recruiter interview read gains `result` (outcome, state, labels, message, released_at, release_mode) — the
  recruiter sees whether the candidate has been told.
- **R11 Queue read.** `GET /recruiter/interview-results?state=pending_approval|released` (paged; pending oldest first, released newest
  first; `counts` for both): code, round, outcome, `is_final`, candidate name/code, requirement, company, decided by/at, the message
  (default shown for pending), `can_release`. `GET|PUT /recruiter/interview-results/settings`.
- **R12 No backfill.** Decisions made before this migration have no result row; they keep today's behaviour.
- **R13 Web.** HR Manager "Result approvals" page (`/it/hr-manager/results`, nav item): Pending/Released tabs, each pending card with an
  editable candidate message and a "Publish result" button, and the auto-release setting (editable by super_admin). The recruiter
  interview card shows "Result: waiting for approval / released to the candidate". A "My results" card on the student's Job Applications
  section and the candidate portal Jobs page. Loading, empty and error states throughout.

Default messages: Selected + final — "Congratulations! You have been selected for {role} at {company}."; Selected on an earlier round —
"You have cleared the {round} for {role} at {company}. We will contact you about the next step."; Rejected — "Thank you for interviewing for
{role} at {company}. We will not be moving forward with your application this time."

## Alternatives considered
- Not moving the application until release: breaks rec-021/022 (offers need Selected; pipelines and reports read it). Holding only the
  candidate's view keeps every staff flow.
- A per-job setting: needs per-requirement UI and has no evidence of variation; the global switch satisfies "per-job (or global)".
- Separate approve and publish actions: no evidence of a gap between them; one "Publish result" action is the approval.

## Numbering
Migration `0287_interview_results` (after `0284_interview_panel`; pob-002/pob-023 hold 0285/0286 in flight); API §12LC; RBAC §2.302.

## Acceptance criteria
1. With approval required, a decided result is invisible to the candidate (application stage, results, interview card, notifications,
   offers refused) until published; after publishing the candidate sees it and is notified once.
2. With auto-release on, the decision is released immediately.
3. Only the right candidate sees the result (another candidate's `/candidate/results` is empty; staff and other roles 403 on candidate route).
4. Only `results.release` holders read the queue and publish (403 otherwise); own decision 403; second release 409; settings PUT super_admin only.

## Plan (TDD)
1. Migration + models + checks + grant seed (migration test).
2. Results service; `change_status` async + hold; legacy path; offers guard — tests first (incl. leak test).
3. Queue / release / settings routes; candidate results route; rec-038 rows; hrc-002 owned keys.
4. Portal schedule label; web lib, queue page, recruiter result line, My results card; vitest.
5. e2e hrc-030; docs (register, API, RBAC, RTM, backlog status).
