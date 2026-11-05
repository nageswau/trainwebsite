# hrc-029 — Interviewer and hiring-manager access with feedback (design)

**Decision:** `DEC-SCOPE-405` (builder's calls V1–V12, `NEEDS_CONFIRMATION`). **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md`
hrc-029 (PDF §3 Hiring Manager/Interviewer "View assigned vacancies and candidates, access necessary resumes, conduct interviews and submit
feedback"; §9 "Record attendance and interviewer feedback"; PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01 (backlog
Q-00); the owner said to proceed with the recommended answers, so Q-12 is answered by the calls below. Dependencies hrc-002
(`DEC-SCOPE-374`, the `interviewer` role) and hrc-028 (`DEC-SCOPE-400`) are merged.

## Intent
A recruiter names the people who interview a candidate — internal interviewers (the hrc-002 `interviewer` role) and the hiring company's
own employer users. Each of them sees only the interviews they are assigned to, with a candidate summary and the resume version shared
with them (download audited), and submits their own feedback: attendance, a score, a recommendation and notes. The recruiter sees every
panel member's feedback on the interview. The candidate never sees any of it.

**Non-goals:** result approval/release (hrc-030); a configurable feedback form; automatic panel decisions; email/overdue reminder jobs.
**Anti-goal:** an interviewer (or an employer user) reading any interview, candidate, contact detail or salary they are not assigned to.

## Builder's calls (V1–V12)
- **V1 Assignment table** `interview_interviewers` (id, interview_id, user_id, kind `internal`|`employer`, is_lead, resume_id — the
  candidate's current resume when assigned, assigned_by_user_id, created_at). Unique (interview, user); at most one lead per interview
  (partial unique index).
- **V2 Who can be assigned.** An active user with role `interviewer` (kind internal), or an active `employer` user whose employer profile
  is the requirement's company (kind employer). Anyone else is 422 on `interviewers`. At most 10 per interview, no duplicates, at most one
  lead.
- **V3 Who assigns.** `PUT /recruiter/interviews/{id}/interviewers {interviewers: [{user_id, is_lead}]}` replaces the panel; rec-017
  writers only (`load_for_write`: scope 404, then 403 for readers). `GET /recruiter/interviews/{id}/interviewer-options` lists the
  assignable users (writers only). A decided (Selected/Rejected) or cancelled interview is 409. Removing someone who has already submitted
  feedback is 409 (their feedback must stay attributable). Audited as `recruiter_interview.interviewers` (user ids only).
- **V4 Resume version.** The assignment keeps the resume current at assignment time (re-saving the panel keeps an existing member's
  version); a later upload is not shared until the recruiter removes and re-adds the person. No resume = "No resume shared".
- **V5 Resume access window (Q-12).** Download only while assigned, the interview is not cancelled, the candidate is not archived and
  until 7 days after the interview end (`ends_at`, else start + 60 min). Outside it: 404 "Resume not available". Every download writes
  `interviewer.resume_download` (interview id, candidate id, resume id) before a byte leaves.
- **V6 Workspace.** `GET /interviewer/interviews?view=upcoming|past` (paged, with both counts) and `GET /interviewer/interviews/{id}`
  for roles `interviewer` and `employer` (any other role 403); an interview not assigned to the caller is 404 — and so is an employer
  assignment once that user no longer belongs to the requirement's company. The item: code, round, when, mode, platform, the current
  meeting link (none once cancelled), location, phone details, instructions, status (decisions read Completed — hrc-001 H3), the
  candidate summary (name, code, location, qualification, experience, current company, skills — no phone, email, LinkedIn or salary), the
  requirement title and company, lead flag, `has_resume`, the caller's own feedback, `can_feedback`, `feedback_overdue`. Never the other
  panel members' feedback, the recruiter's rec-021 feedback, contacts or notes.
- **V7 Feedback (Q-12: one fixed form).** `interview_panel_feedback` (interview_id + interviewer_user_id key; attendance
  `attended`|`no_show`; score 1–5; recommendation `strong_yes`|`yes`|`no`|`strong_no`; notes ≤2000; timestamps). Attended needs score and
  recommendation; No-show needs neither (they are cleared). `PUT /interviewer/interviews/{id}/feedback` creates or replaces the caller's
  row: 409 before the start time, when cancelled, and once decided (Selected/Rejected). Audited by field name only; the notes are never
  logged. A configurable per-job/round form is `NEEDS_CONFIRMATION` (no evidence of which fields vary).
- **V8 Panel decision rule (Q-12).** Panel feedback is advisory: it never moves the interview or the application. The recruiter keeps
  deciding through rec-021 feedback / status (and hrc-030 release later). rec-021's `InterviewFeedback` and `can_feedback` stay as they are.
- **V9 Recruiter view.** Every recruiter interview read gains `interviewers` (name, kind, lead, their feedback or null) and `can_assign`.
  The recruiter item shows a Panel section and an "Assign interviewers" form.
- **V10 Notices.** A newly assigned person gets an in-app notification ("Interview assigned": candidate name and code, requirement,
  round, IST time) plus their allowed delivery channels; nobody else is notified. "Feedback overdue" is a flag (held more than 24 h ago,
  not cancelled or decided, no feedback) shown in the workspace, not a scheduled reminder.
- **V11 Candidate never sees it.** No student, candidate, employer-list or portal route reads the two new tables; a leak test checks the
  student portal and the employer list after feedback is saved.
- **V12 Web.** The interviewer's dashboard (`/it/interviewer/dashboard`) and the employer dashboard each carry the "My interviews"
  workspace (Upcoming/Past tabs, cards, resume download, feedback form; loading, empty and error states).

## Alternatives considered
- Extending rec-021 `can_feedback` to employers/interviewers: one row per interview cannot hold a panel, and a panel member's save would
  move the application — refused.
- A feedback-template table now: no evidence of which fields are configurable; refused under the no-assumption rule.
- Sharing every future resume version automatically: contradicts "only the resume version shared with them".

## Numbering
Migration `0280_interview_panel` (after `0278_commercial_grants`); API §12KX; RBAC §2.298.

## Acceptance criteria
1. An assigned interviewer (internal or employer) submits feedback after the interview time (200); before it 409.
2. The recruiter's interview read shows each panel member's feedback.
3. No candidate/student API returns panel feedback (leak test on the student portal and the employer list).
4. An unassigned interviewer gets 404 on the interview, its resume and its feedback; another role gets 403.
5. Assignment refuses ineligible users (422), decided/cancelled interviews (409) and removing a member with feedback (409).
6. The resume download is audited and refused outside the window (404).

## Plan (TDD)
1. Migration + models + checks (migration test).
2. Service + recruiter routes (assign, options, output) — tests first; rec-038 rows.
3. Interviewer routes (list, one, resume, feedback) — tests first, incl. leak test.
4. Portal dashboard subtitle; web types, workspace component, recruiter panel; vitest.
5. e2e spec hrc-029; docs (register, API, RBAC, RTM, backlog status).
