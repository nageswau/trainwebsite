# hrc-026 — Application record completion (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-026` (PDF §9 stage table, §16 "unique IDs for … Application", §17 QA
  "New applications appear … with a unique Application ID"; PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01
  (backlog Q-00). Dependency hrc-004 (`DEC-SCOPE-376`) merged (PR #445).
- **Decision:** `DEC-SCOPE-394`. The owner said to proceed with the recommended answers, so Q-27, Q-28 and A1–A10 below are **the
  builder's calls (`NEEDS_CONFIRMATION`)**.
- **Numbering:** migration `0271_application_record`; API §12KM; no new permission (AuthZ unchanged, so no RBAC section).

## Intent

Make a job application a record people can name and reason about: a human ID, where it came from and who owns it, a structured reason
when it is rejected, a receipt when a candidate applies, and a per-stage rule that keeps internal stages (Profile Shared) away from the
candidate — neither shown in the portal nor notified.

## Acceptance criteria (backlog, verbatim intent)

1. Each application has a unique human ID.
2. Moving to Profile Shared sends no candidate notice.
3. Rejection requires a reason.
4. A receipt is sent on apply.

## Builder's calls

- **Q-27 / A1 — ID.** `application_code` = `JA-000001` (`JA` = job application; `APP-` is ccrm-011's overseas prefix). The database numbers
  every row from `job_application_code_seq` as a server default (the `INT-` idiom of migration 0133), so legacy routes, employers, the seed
  and tests are all covered. Existing rows are numbered in creation order; unique constraint.
- **Q-28 / A2 — stages.** No stored status is added, removed or renamed (no CHECK change: the rec-005/017 pipeline, offers, interviews and
  the 9 statuses stay). Interview scheduled/completed/next round and offer issued/accepted stay **derived** from the interview and offer
  records, which already have their own sections. The catalogue (`GET …/candidates` → `statuses[]`) gains `candidate_visible` and
  `candidate_label` per stage.
- **A3 — candidate-visible stages.** Every stage except **Profile Shared** is candidate-visible. Candidate wording follows the PDF where it
  differs: Sourced → "Received", Screened → "Screening"; the rest keep their label.
- **A4 — what the candidate sees.** A stored `candidate_status` column holds the last candidate-visible stage. It moves with every visible
  move and stays put on an internal one. The student portal's Job Applications list and the status notice read it, never `status`. A
  notice is sent only when `candidate_status` changes (so Shortlisted → Profile Shared → Shortlisted sends nothing). Backfill: the status
  when visible, else the last visible `to_status` in the history, else `sourced`.
- **A5 — source.** `source` ∈ `portal` (the candidate applied), `recruiter`, `employer`, `drive` (added through a campus drive). Derived in
  `applications.create`: a drive tag → drive; the candidate's own login → portal; an employer → employer; else recruiter. Server default
  `recruiter` for direct inserts. Backfill: drive tag → drive; no `added_by_user_id` → portal; an employer adder → employer; else recruiter.
  `website` and `import` are not added until something creates such applications (hrc-023's public applications stay `CareerApplication`
  rows; converting them is a follow-up).
- **A6 — owner.** `owner_user_id`: the adding recruiter (`placement_team`) when a recruiter adds it, else the requirement's assigned
  recruiter (NULL when none). Backfill the same way. Shown on the board; no reassignment endpoint (not in the backlog's AC).
- **A7 — rejection reasons.** `rejection_reason` ∈ skills_mismatch, experience_mismatch, qualification_mismatch, salary_mismatch,
  location_mismatch, screening_not_cleared, interview_not_cleared, not_reachable, client_rejected, position_filled, other. Required (422)
  on every explicit move to Rejected — the recruiter status route and the legacy `PATCH /workflows/it/job-applications/{id}`; "other" also
  needs a note. Side-effect moves set it themselves: a screening result of Rejected → screening_not_cleared; an interview result of
  Rejected → interview_not_cleared. Reopening (Rejected → Sourced) clears it. CHECK: a reason only on a rejected row, and only a listed key.
  Existing rejected rows keep NULL ("not recorded"). The reason is internal: never in the portal or a notice.
- **A8 — receipt.** Only when the candidate applies (the student portal's apply): an in-app notice "Application received" with the code,
  the job title and the company, plus the usual queued deliveries. A recruiter- or employer-added application sends none (Q-28).
- **A9 — history.** The status history and audit carry the reason (`rejection_reason` on the history row, the audit's metadata), so hrc-004's
  change history shows it.
- **A10 — UI.** The requirement board shows the code, source and owner on each row and asks for a reason (a required select, plus the note
  being required for "Other") when Rejected is chosen; the rejected row shows its reason. The candidate's Applications list (recruiter)
  shows the code. The student portal list gains an Application ID column and uses the candidate wording.

## Non-goals

New stored stages, a stage CHECK change, owner reassignment, external-candidate (hrc-022) application lists and apply (hrc-027), converting
website applications (hrc-023) into job applications, email templates beyond the existing delivery queue.

## API and security review

- Payload changes are additive: `item_out` gains `code`, `source`, `source_label`, `owner`, `rejection_reason`, `rejection_reason_label`;
  `RecApplicationStatusChange` gains optional `rejection_reason` (Literal; `extra="forbid"` kept). The only stricter rule is AC3 (422 on a
  move to Rejected without a reason), which the backlog requires.
- No new route, no AuthZ change; scope and writer gates unchanged (`load_scoped`, `require_writer`). The reason, source and owner are
  staff-only; the student portal reads `candidate_status` and the code only (no IDOR: it is still filtered by `student_id == user.id`).
- Transactions: every change still happens in the caller's single transaction under the row lock; the code comes from a sequence (no race).
- Logs/audit keep ids, statuses and reason keys only, never names or contacts.

## Regression risks

rec-017 tracking/legacy and hrc-009 review tests that reject without a reason (updated to send one: requirement change), the portal's
"Sourced" row (now "Received"), the rec-017 e2e reject step, rec-005 pipeline, rec-018 screening, rec-020/021 interviews.

## Plan (TDD, small steps)

1. Model + migration 0271 (sequence, code, source, owner, candidate_status, rejection_reason, history reason; backfills; checks) — migration
   round-trip test.
2. Service: create (source/owner), `_record` (candidate_status, reason clear), `change_status` reason rule, `follow` system reasons,
   `notify_student` only on candidate change, `send_receipt`, `item_out`/`catalogue`/`history_out` fields.
3. Routes: recruiter status (reason), legacy PATCH (reason), screening (system reason), apply (receipt), portal list (candidate label + code).
4. Web: types + board (code/source/owner, reason select) + candidate applications code; vitest.
5. Update affected tests; e2e for the board reject-with-reason and the student portal list.
