# hrc-001 — Access-control hardening for recruitment data (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-001 (PDF §3, §10.2, §15; PDF classified `UNVERIFIED`). Scope approved by the
  owner 2026-11-01 (backlog Q-00: all phases, hrc-001 first). Dependencies: none. Decision `DEC-SCOPE-371`.
- **Status of the open questions:** the owner said to proceed with the recommended answers, so H1–H6 below are **the builder's calls
  (`NEEDS_CONFIRMATION`)**. The owner's private findings were not available to this session; the rules below come from a fresh
  read-only audit of the as-built code against the backlog's expected behaviour. This document states the rules now enforced, not
  the audit's evidence.

## Rules

**H1 — Legacy IT placement writes use the recruiter record scope (Q-02).** The legacy `/workflows/it/*` routes stay (the portal forms use
them), but every write that changes a requirement, an application, an interview or an offer loads its record through the same scope as
`/recruiter/*` (`recruiter_requirements.caller_scope`, via `load_scoped` / `applications.load_scoped`). Out of scope is the same 404 as
missing.
- Writers: `placement_team` (own or assigned requirements, a recruiter profile required — as every `/recruiter/*` write) and
  `super_admin`. **`it_admin` keeps IT-wide access** (the IT division admin; its "Create recruiter requirement" form uses this route).
- `hr_team` no longer writes through these routes (403). HR has no record ownership, so any write it held was global; it is blocked
  from the recruiter CRM already (recruiter Q-28). HR's read views are unchanged.
- Creating a requirement: an existing company (by id or by name) must be in the caller's company scope (404 otherwise); a recruiter's
  new requirement is assigned to themself, and a company the recruiter creates here is assigned to them — so they can see what they made.
- Not changed: `PUT /it/placement/profiles/{student_id}` (a student-pool record with no requirement link), the student's own apply.

**H2 — Candidate compensation behind a grant (Q-03).** A new catalogue resource `candidates.compensation` with the action `view`
(`deps.require_permission` / `permissions.user_has_grant`; an admin can grant or override it on the existing nehn-005/007 screens).
Default holders: `placement_team` and `placement_manager` (super_admin holds every key). `hr_team` and `bdm` lose it.
Without the grant:
- `current_salary` and `expected_salary` are **absent** from the candidate detail (and the create/update/archive/restore answers),
  from Find Candidates and talent-pool cards, and `expected_salary` is absent from the application screening.
- Sending a salary (candidate create/update, screening save) or a salary range filter (Find Candidates) is a **403** — a range filter
  would reveal the value by narrowing.
- Data migration `0250` seeds the default rows (no schema change; a row already there is left alone; the downgrade removes the
  resource's grants and overrides).

**H3 — Interview outcomes are not shown to students or employers (Q-30 is hrc-030's).** No release step exists yet (hrc-030 adds it), so
until then the legacy free-text `result` is not returned by the student's interview schedule or the employer's interview list, and
the employer list reports a decided status (`selected`, `rejected`, `on_hold`) as `completed`. The application pipeline status the
student already sees is unchanged here (hrc-030 owns its release).

**H4 — Recruitment documents only through their own routes.** `GET /files/download?key=` and `/local-files/{key}` withhold (404) the
recruitment prefixes `candidate-resumes/`, `career-resumes/`, `student-resumes/`, `job-offers/`, `job-joinings/` and
`recruiter-contracts/`. Each already has an authenticated, scope-checked and audited route, which calls the storage layer directly
and is not affected.

**H5 — Leak tests.** A serializer allow-list test signs in as an IT student, an employer and an anonymous caller and reads every
recruitment route they can reach, after recording a sentinel result, feedback, screening note, internal note and salary on their own
records; none of those values (or the restricted keys) may appear.

**H6 — Frontend.** Restricted columns and inputs are hidden: the candidate detail shows salary rows only when the API sent them; the
candidate form, the screening form and the Find Candidates salary filter show the salary inputs only when
`/auth/me/permissions` includes `candidates.compensation.view`. The employer interview card shows the status label, not a result.

## Alternatives considered
- Retire the legacy write routes (Q-02's other answer): breaks the placement and admin portal forms; larger than this item.
- `null` instead of absent for restricted fields: the backlog AC asks for absent; a `null` is indistinguishable from "not recorded".
- Silently ignoring a salary filter without the grant: a search that quietly returns other results is worse than a clear 403.

## Regression risks
`test_adm_008_hr_shortlists` (HR closing-date edit, now 403), `test_emp_005_interview_list` (asserted the employer sees `result`),
`test_rec_007/020/022` (legacy writers), `test_rec_009/013/018` (salary readers), the WorkflowPanel placement forms.

## API / RBAC
API §12JQ records the narrowing as a breaking change for out-of-scope callers. RBAC §2.270 adds the grant and the legacy writer rule.
