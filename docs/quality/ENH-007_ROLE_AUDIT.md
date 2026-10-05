# ENH-007 — Profile Self-Service: Cross-Role Completion Audit

Persists the per-role audit `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-007's own acceptance criteria
requires ("Audit finding documented per role: adequate / needs extension / needs new screen"). The audit
itself was performed before any code was written, in the same session that produced
`docs/superpowers/specs/2026-09-22-enh-007-profile-self-service-design.md`; this file is that audit's
record, added retroactively after an independent review (Codex) correctly found no searchable artifact
for it existed in the repo.

## Method

Read `apps/api/app/api/auth.py`, `apps/api/app/schemas.py`, `apps/api/app/core/rbac.py`,
`apps/api/app/api/schools.py`, and every `apps/web/app/**` and `apps/web/components/**` file reachable
from each role's portal shell. Confirmed via `RBAC_MATRIX.md` and `PRD_OPEN_ITEMS.md` which roles have
real RBAC grants versus which are named but unimplemented.

## Pre-implementation finding (before this feature)

| Role | Login exists? | Backend field mechanism | Frontend self-edit surface | Finding |
|---|---|---|---|---|
| `school_coordinator` | Yes | `/auth/me` only | None | needs new screen |
| `school_principal` | Yes | `/auth/me` only | None | needs new screen |
| `school_teacher` | Yes | `/auth/me` only | None | needs new screen |
| `school_parent` | Yes | `/auth/me` only | None | needs new screen |
| `academic_team` | Yes | `/auth/me` only | None | needs new screen |
| `career_counselor` | Yes | `/auth/me` only | None | needs new screen |
| `psychometric_team` | Yes | `/auth/me` only | None | needs new screen |
| `school_partnership_manager` | **Not implemented** — no RBAC grants (`core/rbac.py`'s `PERMISSIONS` dict has no entry), explicitly excluded from `SCHOOL_DOMAIN_ROLES` in `apps/api/app/api/schools.py:69-77` with a code comment citing `RBAC_MATRIX.md:239-241`: "Not modeled — explicitly deferred... Do not invent a grant for either", duties `OPEN` per `PRD_OPEN_ITEMS.md` item 75 | N/A | N/A | **out of scope** — cannot be given a working profile screen without first resolving item 75; not a gap in this feature |
| (student, for comparison — not a School-domain role, included because the backlog's original confirmed-baseline claim about it was itself unverified) | Yes | `/auth/me` + `/it/student/profile/documents` (document upload only) | `ProfileDocumentUpload.tsx`, documents only | The backlog's "already confirmed" claim about student profile self-service overstated what existed — `API_CONTRACT.md:105`'s `GET/PATCH /student/profile` route does not exist in code; only document upload does. Flagged `NEEDS_CONFIRMATION`, not resolved by ENH-007 (STU-011's own scope) |

## Post-implementation status (this feature, `feature/enh-007-profile-self-service-audit`)

| Role | Status | Evidence |
|---|---|---|
| `school_coordinator` | **adequate** | `/account/profile`, reachable via `PortalShell`'s "My profile" link; verified in browser (`ENH-007_BROWSER_QA_2026-09-22.md`) |
| `school_principal` | **adequate** | same |
| `school_teacher` | **adequate** | same |
| `school_parent` | **adequate** | same |
| `academic_team` | **adequate** | same |
| `career_counselor` | **adequate** | same |
| `psychometric_team` | **adequate** | same |
| `school_partnership_manager` | **out of scope, unchanged** — still blocked on `PRD_OPEN_ITEMS.md` item 75; no code, no grant, no screen added for it, by design |

## Authorization boundary (the acceptance criteria's second requirement)

"No role can self-edit a field that School CRM.md or an existing Decision ID reserves for admin/
coordinator control." `PATCH /auth/me`'s `SERVER_OWNED_PROFILE_KEYS`
(`apps/api/app/api/auth.py:174`) blocks `school_id`, `university_id` (pre-existing, `DEC-SCOPE-020`
era) and, as of the fix accompanying this document, `assigned_grade`/`assigned_section` — the exact
negative scenario the backlog names (`ENHANCEMENT_BACKLOG.md:727-730`, `:749`). Covered by
`apps/api/tests/test_enh_007_profile_self_service.py::test_a_teacher_cannot_self_assign_a_reserved_scheduling_field`.
Neither field is read anywhere in the codebase for an authorization decision today (teacher-to-student
scoping is `SchoolStudent.assigned_teacher_user_id`, set only by admin/coordinator routes, never touched
by `/auth/me`) — the guard is pre-emptive, not a fix to a currently-reachable privilege escalation.
