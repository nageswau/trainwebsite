# hrc-007 — Vacancy approval workflow and Filled status (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-007` (PDF §4.2 Workflow, §4.3 Lifecycle; PDF classified `UNVERIFIED`).
  Scope approved by the owner 2026-11-01 (backlog Q-00). Dependencies hrc-002 (`DEC-SCOPE-374`, declares `jobs.approve` with no holder)
  and hrc-004 (`DEC-SCOPE-376`) are merged.
- **Decision:** `DEC-SCOPE-380`. The owner said to proceed with recommended answers, so A1–A11 are **the builder's calls
  (`NEEDS_CONFIRMATION`)** answering backlog Q-07.

## Intent

Only approved, open vacancies may take new applications (§4.3). Today an employer publishes its own draft and the legacy staff route
publishes immediately, so nobody checks a vacancy before candidates see it. Separation of duties: the approver is never the person whose
job it is. "Filled" closes a vacancy to new applications once every seat has a joined candidate.

## Builder's calls

| # | Topic | Call |
|---|---|---|
| A1 | Statuses | Two new internal statuses: `pending_approval` (Pending Approval) and `filled` (Filled) — 13 in all. Neither is in `JOB_OPEN_STATUSES`, so no student/public/apply path changes (AC1 holds by construction). |
| A2 | Label mapping (Q-07) | A `phase` per status, the PDF's seven: Draft = `new`; Pending Approval; Open = `requirement_received`…`selected`; On Hold; Filled = `joined`, `filled`; Closed; Cancelled. Returned beside `status_label`; the 13 internal statuses stay. |
| A3 | Job source | New `jobs.source` (`recruiter` / `employer` / `legacy`), set by each create path. Backfill: a job whose "created" history row was written by an employer user → `employer`; created as `requirement_received` (the legacy route's start) → `legacy`; else `recruiter`. |
| A4 | Which sources need approval (Q-07) | A `job_approval_settings` row per source, seeded **employer = on, recruiter = off, legacy = off**: the employer's self-publish is the gap the PDF names; staff flows keep today's behaviour. Read by `jobs.approve` holders; changed by super_admin only (audited). |
| A5 | When approval applies | Approval is needed when the source's setting is on **and the job has never been live** (no history row into an open/selected status). A job that was approved once can go on hold and reopen without re-approval. |
| A6 | Submit | `POST /recruiter/requirements/{id}/submit` `{note?}` — the requirement's writer (`can_edit`), from Draft (`new`) or On Hold while approval applies → Pending Approval; stores `submitted_by_user_id`/`submitted_at`. Otherwise 409. The legacy writers' "open" word (employer `PATCH /employer/jobs/{id}`, `PATCH /workflows/it/jobs/{id}`) means **submit** when approval applies. |
| A7 | Gate | While approval applies, the status route refuses a move into an open status (409, "needs approval") and `allowed_statuses` leaves those moves out. |
| A8 | Approve / reject | `POST …/{id}/approve` `{note?}` → Requirement Received (fires rec-005's company stage as today); `POST …/{id}/reject` `{reason}` (required) → Draft. Caller must hold `jobs.approve` (403); any pending job in the IT recruitment (no recruiter scope — the HR Manager has none), missing = 404, not pending = 409. **Never one's own** (403): the submitter, the creator or the assigned recruiter. History row + audit row with the note/reason. |
| A9 | Queue | `GET /recruiter/requirement-approvals` (`jobs.approve` holders, 403 otherwise): pending jobs, oldest submission first, `{items,total,limit,offset}`; each row says whether the caller may decide it. New page `/it/hr-manager/approvals` (nav "Approvals"); super_admin decides from the requirement detail page too. |
| A10 | Setting off while pending (E) | Pending jobs stay pending; an approver still decides them; the owner may cancel. Nothing auto-opens. |
| A11 | Filled | `filled` is reachable by hand from any open/selected status and Joined; from Filled → Requirement Received (reopen) or Closed. **Automatic:** when an application becomes Joined and `vacancies` is set and the joined count reaches it, the (locked) job moves to Filled with note "All vacancies filled". The employer's legacy word for Filled is `closed`, for Pending Approval `draft`. |
| A12 | Default approver | `jobs.approve` gets its first default holder, `hr_manager` (migration seed, frozen copy). super_admin holds it implicitly. |

Not built: notifications (hrc-032), visibility (hrc-008), a per-company approval rule.

## Data (migration `0256_job_approval`)
Guarded (0001 builds from current models). `jobs.source` (String(10) NOT NULL default `recruiter`, CHECK), `jobs.submitted_by_user_id`,
`jobs.submitted_at`; table `job_approval_settings(source PK, required bool, updated_by_user_id, created_at, updated_at)` seeded; `ck_jobs_status`
recreated with the 13 statuses (frozen copy); `role_permissions (hr_manager, jobs, approve)`. Downgrade maps `pending_approval`→`new`,
`filled`→`closed`, restores the 11-status check and drops the rest. No existing data is changed except the backfilled `source`.

## Concurrency / transactions
Every write locks the job row (`load_scoped(lock=True)` / `SELECT … FOR UPDATE` for approvers), checks state after the lock and commits
once in the route. Two approvers at once: the second sees "not pending" (409). Auto-fill locks the job before counting joins.

## Tests (TDD)
`tests/test_hrc_007_approval.py`: AC1 pending job refuses student apply (404); AC2 approve → open + history; AC3 reject → Draft with
reason; AC4 history kept after closure; + employer publish → pending → HR Manager approves → visible to students; − recruiter
approving own job 403; − no grant 403; E setting off while pending; gate 409; auto-Filled; queue scope; settings super_admin only.
`tests/test_hrc_007_migration.py`: chain, frozen copies, round trip. Updated: `test_rec_007_migration` (0114's frozen status check now
differs from the model by design), employer tests that publish directly. Vitest for the phase/approval helpers; Playwright e2e for the
employer → HR Manager approval flow.

## Plan
1. Model + migration + migration test (RED → GREEN).
2. Service: statuses, phases, source, approval rules, auto-fill; routes submit/approve/reject/queue/settings; legacy paths.
3. Fix affected existing tests (rec-007, emp-*), only where they assert the old employer self-publish.
4. Web: types + helpers, detail page Submit / Approve / Reject cards, employer panel pending state, HR Manager approvals page + nav.
5. Docs: decision register, API_CONTRACT §12JY, RBAC_MATRIX §2.279, RTM, backlog status.
