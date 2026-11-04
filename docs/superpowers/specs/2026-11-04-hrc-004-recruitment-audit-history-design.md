# hrc-004 — Before/after audit for recruitment records (design + plan)

**Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` §hrc-004 (DERIVED_WORKBOOK of the HR & Recruitment CRM PDF §4.3, §5.1,
§10.2, §15, §17 QA #18). Dependency **itc-001** (`services/audit_changes.py`, DEC-SCOPE-335) is merged (PR #408).
**Decision:** `DEC-SCOPE-372` (builder's calls B1–B8 below are `NEEDS_CONFIRMATION`; the owner asked the session to proceed with
recommended answers).

## Intent
A recruiter, manager or HR Manager opening a job requirement or a candidate can see **what changed, from what to what, by whom and when**
— the PDF's "preserve previous values for material edits" — while compensation and contact values are never kept as values.

## Acceptance criteria (backlog, verbatim intent)
- **AC1** Changing a job title shows the old and new values in the job's history.
- **AC2** A salary change shows "changed" without values.
- **E** A bulk reassignment produces one history row per job.
- AuthZ: the history follows the record's read scope (out of scope = 404, a non-reader role = 403), PII redacted.
- Performance: the history query uses `ix_audit_logs_entity (entity_type, entity_id, created_at)` (exists, verified in `models.py`).

## Builder's calls (NEEDS_CONFIRMATION)
- **B1 Access.** The backlog says both "roles holding `audit.view` for recruitment" and "the history tab follows the record's read
  scope". No `audit.view` key exists in `rbac.CATALOGUE`, and the backlog lists hrc-004 as needing **no migration** (a new grant needs a
  seed migration, as hrc-001's 0250 did). Call: the history is readable by exactly the record's readers — a requirement through
  `recruiter_requirements.load_scoped`, a candidate through `candidates.require_reader` + `load`. No new grant, no migration.
- **B2 Endpoints.** `GET /recruiter/requirements/{id}/history` and `GET /recruiter/candidates/{id}/history` (the two pages with the
  tab). Application and interview audits gain before/after values too (visible in the admin Audit log), but get no new route:
  `GET /recruiter/applications/{id}/history` already exists as the application's *status* history and is left unchanged.
- **B3 Backward compatibility.** Existing audit metadata keys (`fields`, `from`/`to`, ids) stay; `changes` is **added**. hrc-003's
  `require_fresh` reads `fields`, and the admin Audit log already renders `changes` (itc-001).
- **B4 Redaction.** Recorded as `"changed"`: compensation (`salary_min`, `salary_max`, `current_salary`, `expected_salary`); contact
  (`mobile`, `email`, `linkedin`, `meeting_url`, `contact_id`); free-text interview feedback (`strengths`, `weaknesses`,
  `recruiter_comments`, `company_feedback`); plus itc-001's own PII names (`phone`, `email`, `notes`, `remarks`, `reason`, `*_<those>`).
  Done with a new optional `redact=` keyword on `audit_changes.changes/audit_change` (default unchanged).
- **B5 Readable values.** Ids a person can't read are stored as names at write time: job category, candidate source and the assigned
  recruiter (`recruiter: [old name, new name]`). Statuses are stored as their keys.
- **B6 What is history.** Rows of the record's entity (`job` → `recruiter_requirement.*` and `job_description.*`; `candidates` →
  `candidate.*`), **downloads excluded** (a read). Newest first, `{items, total, limit, offset}` (default 20, max 100). Each item:
  `id, action, created_at, actor {id, full_name} | null, changes | null, fields | null`. Raw metadata is never returned.
- **B7 UI.** The detail pages have no tab strip (they stack `action-card` sections), so "History tab" = a **Change history** section at
  the end of each page, following `RecruiterCandidateJourney`'s loading / error + Retry / empty states and a "Show older" button. The
  field-diff rendering is reused from `AdminAuditLog` (exported).
- **B8 Creates** keep their field-name audit (there is no "before"); only edits, status moves, reassignment and JD versions gain values.

## Write sites (MUST CHANGE)
| Entity | Site | Change |
|---|---|---|
| Job | `api/recruiter_requirements.py` update / status / assign | `changes` from the stored vs sent values (category by name) / `status` / `recruiter` names |
| Job (bulk) | `services/recruiter_lifecycle.py` reassign | one row per job, `recruiter` names |
| JD | `api/recruiter_job_descriptions.py` create (new version) | diff of the previous current version's `REC_JD_FIELDS` vs the new |
| Candidate | `api/recruiter_candidates.py` update | diff of applied fields (source by name), redacted |
| Application | `api/recruiter_applications.py` status | `status` from → to |
| Interview | `services/interviews.py` update / reschedule / status / feedback | diff; `scheduled_at` old → new; `status`; feedback redacted |

SHOULD NOT CHANGE: `stale_guard.py`, the AuditLog model/indexes, admin Audit log API. HIGH REGRESSION RISK: rec-* tests asserting
`metadata_json == {...}` exactly for the touched actions (update them to include `changes`; behaviour otherwise unchanged).

## Review notes (API / frontend / security)
- **API:** read-only GET, list envelope as every recruiter list (`LIMIT`/`OFFSET` from `api/bdm.py`); the role check (403) before scope
  (404) exactly as the record's own GET; `Cache-Control: no-store` (staff names and history, like nehn-016's training read). The audit
  row stays in the write's transaction (fail closed, itc-001).
- **Security:** IDOR — the id resolves only through the record's scope loader; raw `metadata_json` never leaves the server (it may hold
  ids/notes); redaction happens at **write** time, so no value to leak exists; React escapes every value (no XSS); no new write route
  (no CSRF surface); no logging of values.
- **Frontend:** a labelled `<section>` (`aria-labelledby`), `role="status"` loading, `role="alert"` error + Retry, an explicit empty
  state, `<ul>` rows readable on mobile (no wide table — the global `.table` has a 650 px min-width), "Show older" is a real button.

## Plan (TDD, one slice at a time)
1. `redact=` keyword on the helper — unit test (RED → GREEN).
2. Job update/status/assign/bulk + JD version adopt `changes` — API tests incl. AC1/AC2/E.
3. Candidate update, application status, interview writes adopt `changes` — API tests (redaction of salary/contact/feedback).
4. History endpoints — tests: AC1/AC2 visible, newest first, downloads excluded, metadata not returned, 404 out of scope, 403 non-reader,
   pagination.
5. Web: `lib/recruiterHistory.ts` (URL, type guard, labels) + `RecruiterRecordHistory.tsx` — vitest (loading, error/retry, empty,
   values, "changed", show older); mount on both pages.
6. Fix exact-shape assertions in affected rec-* tests; Playwright e2e (job title + salary edit → history).
7. Docs: DEC-SCOPE-372, API contract §, RBAC note, RTM row.
