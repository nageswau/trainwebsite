# hrc-002 — Recruitment roles and configurable permission scope (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-002 (PDF §3, §15; PDF classified `UNVERIFIED`). Scope approved by the owner
  2026-11-01 (backlog Q-00). Dependency hrc-001 is built (`DEC-SCOPE-371`). Decision `DEC-SCOPE-374`.
- **Open questions:** the owner said to proceed with the recommended answers, so R1–R7 below are **the builder's calls
  (`NEEDS_CONFIRMATION`)** for Q-01 and Q-04.

## Intent
The PDF's §3 names six recruitment roles (Super Admin, HR Manager, Recruiter, Placement Officer, Hiring Manager/Interviewer, Candidate)
and asks for permissions configurable by role and scope. Today only Recruiter (`placement_team`), the team lead (`placement_manager`), HR
(`hr_team`), employers and super_admin exist. hrc-002 creates the missing internal roles and the grant keys the later items (hrc-007, 008,
013, 014, 020, 030) enforce, without widening anyone's access.

**Non-goals:** the approval, publish, export, import, merge and release *features* (their own items wire the routes); co-ownership
(hrc-006/012); interviewer assignment and feedback (hrc-029); the external candidate portal (hrc-022).
**Anti-goal:** a new role that can read candidate or vacancy data it has no business with.

## Rules

**R1 — Three new IT roles (Q-01).**
- `hr_manager` — HR Manager. A new role, not a relabelled `placement_manager`: `placement_manager` is the recruiters' team lead
  (reporting-manager scope, `/recruiter/manager/*`), and the Placement Officer backlog lists "HR Manager" and "Recruitment Team Lead" as
  different users. Created by a **super_admin only** (it will approve vacancies and release results).
- `placement_officer` — Placement Officer, separate from `placement_team` (the PDF lists Recruiter and Placement Officer separately; QA
  #1/#2 has them see each other's work). Created by `it_admin` or super_admin.
- `interviewer` — internal Hiring Manager/Interviewer. Created by `it_admin` or super_admin. Employer contacts keep interviewing through
  the existing `employer` login (hrc-029, Q-12).
- `hr_team` and `placement_manager` are unchanged. All three new roles are division `it`.

**R2 — Least privilege.** The new roles get no default grants and are in no existing role set (`services/recruiter.py`, `hr_students`,
`management_access`), so every recruiter CRM route, legacy placement route and HR route refuses them (403), exactly as for any other
non-recruitment role. The rec-038 route matrix gains the three roles to prove it.

**R3 — Own dashboards (AC1), read-only.** Each role signs in at `/it` and lands on `/it/<segment>/dashboard` (generic portal page):
- **HR Manager** (`/it/hr-manager/dashboard`): oversight of all recruitment ("the HR Manager sees all", hrc-025) — counts of open
  requirements, applications, interviews and offers, and the open requirements (Job ID, role, company, location, status).
- **Placement Officer** (`/it/placement-officer/dashboard`): the open requirements with their shared Job ID (§4.1 mutual visibility,
  QA #1) and their count. No candidate data until ownership arrives (hrc-006/012).
- **Interviewer** (`/it/interviewer/dashboard`): no data yet; "No interviews are assigned to you yet." (assignment is hrc-029).
No salary, candidate, feedback or note field appears on any of them.

**R4 — Recruitment grant keys (AC2).** The catalogue gains `jobs` (`approve`, `publish`), `candidates` (`export`, `import`, `merge`) and
`results` (`release`); `ACTIONS` gains `publish`, `export`, `import`, `merge`, `release`. `candidates.compensation.view` already exists
(hrc-001). No route uses the new keys yet, so they have **no default holders** (super_admin holds all) and no seed rows; each owning item
adds `require_permission` to its route and sets its defaults then. A super_admin can already grant them on the permission screen and
via `PUT /admin/roles/{role}/permissions` (e.g. `jobs.approve` to `hr_manager`). This departs from nehn-005 P1 ("only wired resources")
on purpose: the backlog asks for the keys now, so roles can be configured ahead of the features.

**R5 — Scope dimension (Q-04): none added now.** No branch or department list exists in any evidence, and inventing one would be a guess.
Client scope already means the job's company (recruiter company assignment, `caller_scope`). AC3 ("branch B cannot see branch A") is
therefore **not built**; it stays `NEEDS_CONFIRMATION` until the owner names the branches/departments.

**R6 — A user with two roles (edge case).** Portals, recruiter gates and grants read `User.role` only; an extra `UserRoleAssignment` row
does not widen recruitment access (an interviewer with an extra `placement_team` assignment is still refused the recruiter CRM).

**R7 — No migration.** `users.role` is a plain string (no CHECK constraint), and R4 seeds no rows.

## Alternatives considered
- Relabel `placement_manager` as HR Manager: changes what existing manager accounts mean and merges two PDF roles.
- Treat `placement_team` as Placement Officer (the pob backlog's observation): then QA #1/#2 (recruiter vs officer) cannot be told apart.
- Free-text `branch` columns now: an unbounded value nobody has defined; refused under the no-assumption rule.
- Give new roles read access to the recruiter CRM: violates least privilege before ownership rules exist.

## Regression risks
`test_nehn_005_permissions` / PermissionMatrix (new resources and five more action columns), rec-038 and tel-026 matrices (new roles
must be refused), admin user creation (`allowed_by_division`), the web middleware's protected-path list, navigation tests.

## API / RBAC
API §12JT: `GET /admin/permissions/catalogue` lists the new roles, resources and actions (additive); `/portal/it/{hr-manager|
placement-officer|interviewer}/dashboard`; `POST /admin/users` accepts the roles. RBAC §2.273 records R1–R6.

## Plan (TDD, small tasks)
1. API tests (red): role creation rules; each role's dashboard (and 403 on other roles' portals); catalogue keys; admin grants
   `jobs.approve` to `hr_manager`; interviewer 403 on candidate search; two-role edge; rec-038 matrix with the new roles.
2. Backend: `rbac.py`, `admin.py`, `api/portal.py`, `services/portal.py`, `seed.py` (one demo user per role).
3. Web tests (red): `dashboardPathFor`, `PORTAL_NAV`, role options. Then `navigation.ts`, `middleware.ts`, `PortalPage` labels,
   `WorkflowPanel`, admin roles table, three dashboard pages.
4. e2e: each role signs in and lands on its dashboard; interviewer is refused `/recruiter/find-candidates`.
5. Docs: decision register, API contract, RBAC matrix, RTM, backlog status.
