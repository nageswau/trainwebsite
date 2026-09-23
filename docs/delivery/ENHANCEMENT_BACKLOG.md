# Enhancement Backlog — School Portal User Lifecycle & Academic Team Completion

NO-ASSUMPTION MODE. Prepared per user request 2026-09-17, cross-checked against
`graphify-out/GRAPH_REPORT.md` (the `graphify` CLI itself is blocked by a Windows Application
Control policy in this environment and could not be run — this is an environment limitation, not
a skipped step), `docs/evidence/EVIDENCE_REGISTER.md`, `docs/decisions/PRODUCT_DECISION_REGISTER.md`,
`docs/decisions/APPROVAL_GATES.md`, `docs/features/MASTER_FEATURE_CATALOG.md`, and the live codebase
(`apps/api/app/**`). **No code was written or changed to produce this document.** Every item below is
still behind `APPROVAL_GATES.md` GATE-02 (Decision IDs) at minimum; none has cleared GATE-09 (Coding).

**Revision 2 (same day):** the first pass of this document (ENH-001–ENH-008) was scoped only to the
user-account-lifecycle theme the user specifically called out, not to a full read of
`docs/sources/School CRM.md`. The user then asked, correctly, whether *every* functionality and field
(specifically calling out School ID and Branch) had been considered. It had not. This revision adds
§1.5, a full section-by-section coverage audit of the entire 1,928-line source document (both its
"brochure" pass, §§1–36, and its separately-renumbered "role/login" pass, §§1–15), and ENH-009 through
ENH-021 for the gaps that audit surfaced. ENH-001–ENH-008 are otherwise unchanged except where noted.

**Revision 3 (same day):** the user asked to recheck this backlog with entitlements and tier-based
access levels treated strictly, to explicitly surface hidden requirements like a Gold→Platinum tier
change, and to incorporate a new evidence file, `c:\Users\admin\Downloads\SCHOOL BROUCHER (5).pdf` — the
actual 4-page marketing brochure `School CRM.md` repeatedly cites but that had never itself been read.
Reading it, and re-reading `apps/api/app/api/schools.py`'s entitlement code against it, found that one
of Revision 2's own conclusions was **wrong** — see the correction to Appendix A item 3 and to ENH-016
below — and surfaced the real, narrower gap: tier entitlements are correctly modeled and *reported*, but
never *enforced*, and changing a school's tier has no safety net at all. This revision corrects those
two items and adds ENH-022, ENH-023, and ENH-024. Produced following this session's `/plan` invocation
(`agent-skills:planning-and-task-breakdown`); the underlying research plan is preserved at
`C:\Users\admin\.claude\plans\inherited-knitting-bumblebee.md` for traceability.

**Revision 4 (same day):** the user asked directly whether every `School CRM.md §2` School Profile
field was covered, and — on finding it wasn't — gave an explicit, direct instruction that full field
coverage is now **mandatory**, not merely a scope question to defer to a future decision. This is a
genuine `EXPLICIT_APPROVAL`-grade confirmation from the person running this project, distinct from a
source document's own use of a word like "approved." This revision updates ENH-009 accordingly (field
coverage is mandatory; only Branch's design and the Edusphere-BDM role blocker remain open questions,
not scope), and adds **ENH-025** after auditing `School CRM.md §3` Student Master the same way, per the
user's instruction to "check others like student." A follow-up pass the same day extended this
field-by-field method to `§6` (Psychometric) and `§7` (Career Counselling) at the user's request, adding
**ENH-026**/**ENH-027** and correcting two more rows in the §1.5 coverage table that had been marked
`✅ Built` without being checked field-by-field.

**Revision 5 (same day):** the user asked to check for bulk-upload opportunities across data-entry
surfaces (naming Results and Psychometric Tests specifically) and for bulk school onboarding, "and
similarly check for other possibilities." Verified directly against the code (not assumed) that exactly
one bulk pattern exists anywhere (`bulk_upload_students`/`SchoolRosterUploadBatch`), that
`mark_attendance` already handles a many-at-once shape correctly under a different name, and that
Results/Psychometric/Career/Test-Prep records and school onboarding are all single-record-only. Also
surfaced, while researching this, a gap adjacent to but distinct from bulk upload: there is no routine
daily/period attendance entity for School students at all, only per-scheduled-activity attendance —
despite "Attendance" being a recurring field across the Teacher/Parent/Student dashboards and the
Student 360° view. Added **ENH-028** (generalized bulk data-entry for Results/Psychometric/Test-Prep),
**ENH-029** (bulk school onboarding), and **ENH-030** (the new attendance entity, deliberately designed
bulk-first so it doesn't repeat the pattern of needing bulk retrofitted later).

## 0. Scope and exclusions (read this before the backlog)

**In scope — School CRM only.** `functionalities/edusphere_markdown/School CRM.md` is byte-identical
to `docs/sources/School CRM.md` (`EVID-014`, classified `DERIVED_BLUEPRINT`, provenance itself
`NEEDS_CONFIRMATION` in `EVIDENCE_REGISTER.md`). Large parts of it have since been formalized into
`CONFIRMED_CURRENT` Decision IDs (`DEC-ROLE-006/007`, `DEC-SCOPE-011/012/013/014/015/016/017/018`)
and shipped as `SCH-001`–`SCH-011`. Where an item below rests on one of those confirmed decisions, it
is treated as approved scope, not guessed. Where it rests only on the raw blueprint prose with no
matching decision, it is marked `NEEDS_CONFIRMATION` and still requires a Decision ID before GATE-09.

**Out of scope — the other 6 source files.** `Agent CRM Functionalities.md` (`EVID-015`),
`BDM Functionalities.md` (`EVID-016`), `Management Functionalities.md` (`EVID-017`),
`Recruiter Functionalities.md` (`EVID-018`), `Telecaller Functionalities.md` (`EVID-019`), and
`University Partnership CRM.md` (`EVID-020`) are all identical to their `docs/sources/` copies, all
classified `DERIVED_BLUEPRINT`, none carries `EXPLICIT_APPROVAL`, and several sit inside the
`PRD_OPEN_ITEMS.md` item‑61 "Internal CRM" hard blocker and `CONFLICT_MATRIX.md` C‑10. Turning these
into fully-detailed ENH items (acceptance criteria, complexity/risk, migrations) would treat an
unapproved blueprint as final truth — exactly what the project constitution forbids. **They are not
converted into ENH items in this pass.** Appendix B lists them at theme level only, each tagged with
the Decision ID that must exist before it can re-enter this backlog.

**Already complete — excluded, not re-listed as an enhancement.** Forgot-password
(`POST /auth/forgot-password`, `POST /auth/reset-password`, `apps/api/app/api/auth.py:155,179`) is
built, traced to `AUTH-001`/`NOT-001`, and its notification-delivery bug is already fixed (RTM:
221/221 tests passing). No gap found — verified, not assumed.

**New evidence — the source brochure (Revision 3).** `c:\Users\admin\Downloads\SCHOOL BROUCHER (5).pdf`
is the 4-page EduSphere partnership brochure. Classified `COMMERCIAL_QUOTATION` (it is the literal
definition of what a school's partnership fee buys), cross-referenced to `EVID-014` since
`School CRM.md` repeatedly cites it by name ("the brochure specifically includes..."). Its "School
Partnership Model" page names the same four tiers with the same service labels, word-for-word, as
`TIER_SERVICES` in `apps/api/app/api/schools.py:638-667` (e.g. "Dedicated EduSphere counselor," "Monthly
campus visits," "Parent help desk"), drawn explicitly as **cumulative** ("EVERYTHING IN BRONZE PLUS,"
"EVERYTHING IN SILVER PLUS") — a checklist, never a numeric quota. This is strong, near-certain
confirmation that the brochure the user just supplied is the same one the code was already built
against.

**Standing conflict that several items below inherit.** `DEC-ROLE-004` (2026-09-14, `CONFIRMED_CURRENT`)
says only EduSphere-direct students get a login — school-affiliated and agent-referred students never
do. `DEC-SCOPE-011` (same day, also `CONFIRMED_CURRENT`) adopts the full four-role School set
*including* an individual Student login. Neither supersedes the other in the register. Any item that
assumes a school student logs in themselves (flagged inline below) inherits this unresolved conflict
and cannot reach GATE-09 until it is reconciled with a new Decision ID.

## 1. Backlog summary

| ID | Title | Complexity | Risk | Migration? | Depends on |
|---|---|---|---|---|---|
| ENH-001 | Academic-Year / Promotion-Cycle foundation model | Large | High | Yes | — |
| ENH-002 | Academic Team — capability completion & actor-separation audit | Medium | Medium | Possibly (TBD) | — |
| ENH-003 | First-time user provisioning — welcome email + set-password link, all admin-provisioned roles | Medium | High | Possibly (TBD) | — |
| ENH-004 | Student promotion to next academic year / grade | Large | High | Yes | ENH-001 |
| ENH-005 | Student school transfer / reassignment | Medium | Medium | Yes | — (coordinate with ENH-004) |
| ENH-006 | Self-service change password (authenticated) | Small | Low | No | — |
| ENH-007 | Profile self-service — cross-role completion audit | Medium | Low | Possibly (TBD) | ENH-003 (shares provisioning fields) |
| ENH-008 | Parent account linked to children across multiple schools | Medium | Medium | Yes | — |
| ENH-009 | School profile — **mandatory** full field coverage (School ID, Branch, +21 more; see corrected entry below) | Large | High | Yes | — (should land early; see §2) |
| ENH-010 | Account activation / deactivation (School Master capability) | Small | Medium | No | — |
| ENH-011 | School-domain skills tracker generalization (Soft Skills, Digital/Web Skills) | Medium | Low | Yes | Reuses SCH-009 pattern |
| ENH-012 | Digital Portfolio module | Large | Medium | Yes | ENH-001 (portfolio entries reference academic year) |
| ENH-013 | Student 360° unified profile / Career Passport view | Large | Medium | Possibly (TBD) | ENH-011, ENH-012 |
| ENH-014 | Multi-channel Communication Centre (WhatsApp/SMS/Email/push) | Large | High | Yes | — |
| ENH-015 | Reports & downloads (student/school/management exports) | Medium | Low | No | — |
| ENH-016 | School & Edusphere analytics dashboards *(scope corrected, Rev. 3 — see below)* | Medium | Low | Possibly (TBD) | — |
| ENH-017 | School-visible global education pipeline dashboard *(now owns Alumni Network)* | Medium | Medium | No | SCH-010 (bridge, already built) |
| ENH-018 | School feedback capture | Small | Low | Yes | — |
| ENH-019 | School event calendar | Small | Low | Yes | — |
| ENH-020 | Financial support / loan assistance tracking | Medium | Medium | Yes | — |
| ENH-021 | Internship management | Medium | Low | Yes | — |
| ENH-022 | Tier-gated feature access enforcement | Medium | Medium | No | — (build early) |
| ENH-023 | Partnership tier change (upgrade/downgrade) workflow | Medium | High | No (history table optional) | ENH-022 |
| ENH-024 | Skill India certification tracking | Small | Low | Yes | ENH-012, ENH-013 |
| ENH-025 | Student Master — mandatory full field coverage (Photo, Gender, Roll Number, City, +8 more) | Medium | Medium | Yes | Coordinates with ENH-001 (Grade/Section split) |
| ENH-026 | Career Counselling record — structured fields & status workflow (corrects a wrong Rev. 2 audit row) | Medium | Low | Yes | — |
| ENH-027 | Psychometric record — structured result fields (corrects a wrong Rev. 2 audit row) | Medium | Low | Yes | Coordinates with ENH-026 (shared recommendation shape) |
| ENH-028 | Bulk data-entry — Academic Results, Psychometric, Test Prep/Language records | Medium | Medium | Yes | ENH-011 (Test Prep/Language part only) |
| ENH-029 | Bulk school partner onboarding (multiple schools at once) | Medium | Medium | Yes | Coordinates with ENH-003, ENH-028's design |
| ENH-030 | Daily/period attendance tracking (new entity, built bulk-first) | Medium | Low | Yes | Feeds ENH-013, ENH-016 |

---

## ENH-001 — Academic-Year / Promotion-Cycle Foundation Model

**Title.** Introduce an explicit academic-year/term entity as the substrate for promotion, results,
and enrolment history.

**Business requirement.** **Correction (Revision 2):** this was originally written up as a purely
engineering-inferred item with no source citation. A full read of `School CRM.md` found it *is*
directly sourced: §4 "Grade & Class Management" (`docs/sources/School CRM.md:178-202`) explicitly
states the hierarchy **"Grade → Section → Academic Year → Student"** and gives the worked example
"Grade 10 → Section A → 2026–27 → 42 Students" — an explicit academic-year concept, not an inferred
one. §3 "Student Master" also lists "Academic Year" as its own profile field
(`docs/sources/School CRM.md:142`). Still `EVID-014`/`DERIVED_BLUEPRINT`, still needs its own Decision
ID (`DEC-DATA-0xx`, next free slot after `DEC-DATA-003`) before GATE-09 — specifically whether academic
years are global-shared or per-school, and whether they're EduSphere-managed or school-coordinator-managed
— but it is sourced requirement, not a silent engineering addition.

**Existing behavior.** `SchoolStudent.grade`/`grade_or_class` is a free-text string
(`apps/api/app/models.py:221,992,1157`) with no ordering, no year/term association, and no history —
each row reflects only the student's *current* label.

**Expected behavior.** A new `AcademicYear` (or `SchoolAcademicYear`, pending the scope decision above)
entity with `label`, `start_date`, `end_date`, `status` (`draft`/`active`/`closed`); `SchoolStudent`
gains an `academic_year_id` FK and an ordered `grade_level` (numeric or enum) distinct from the
free-text display label, so "promote by one level" becomes a well-defined operation instead of string
manipulation.

**User roles affected.** `school_coordinator` (manages the roster this sits under), `super_admin` /
`overseas_admin` (year lifecycle), indirectly every role that reads `SchoolStudent.grade`.

**Frontend impact.** None directly (no new screen) — but every screen currently rendering
`grade`/`grade_or_class` as a bare string (roster views, parent "My Children" cards, teacher assigned-
student lists) must be audited so the migration doesn't silently break existing display logic.

**Backend impact.** New model + migration; touches every query/serializer that reads `grade`.

**Database impact.** New table(s); new FK column(s) on `SchoolStudent`; backfill migration assigning
all existing rows to a default "current" academic year and deriving `grade_level` from the existing
free-text label (lossy — needs a mapping table, since labels like "Grade 10-A" mix level and section).

**API impact.** No new public endpoint by itself; existing roster/read endpoints' response shape gains
`academic_year` and `grade_level` fields (additive, non-breaking if done correctly).

**Integration impact.** None identified.

**Authentication impact.** None.

**Authorization impact.** None beyond existing `school:coordinator:own_institution` scoping.

**Security impact.** Low directly; the backfill migration must not leak cross-school data during the
grade-label-to-level mapping step.

**Performance impact.** One-time backfill cost proportional to student count; negligible steady-state
cost (indexed FK).

**Reusable existing modules.** Existing Alembic migration tooling (`alembic upgrade head` already
wired into `docker-compose.yml:26`); existing `SchoolStudent` model and its per-school query scoping
pattern (`RBAC_MATRIX.md §2.12`).

**Dependencies.** None upstream. Blocks ENH-004.

**Acceptance criteria.**
- `DEC-DATA-0xx` confirms scope (global vs per-school academic year) before any migration is written.
- Every pre-existing `SchoolStudent` row has a non-null `academic_year_id` and a derived `grade_level`
  after migration; zero data loss on the free-text label (kept alongside, not replaced).
- No existing roster/read endpoint response breaks (contract diff reviewed against `API_CONTRACT.md`).

**Positive scenarios.** A coordinator views the roster and sees the same grade labels as before, now
also carrying a machine-readable level and year.

**Negative scenarios.** Migration run against a school with non-standard grade labels (e.g. "LKG",
"Pre-Nursery") that don't map to a numeric level — must fail loudly per-row (logged, not silently
defaulted) rather than corrupt data.

**Edge cases.** Schools with mid-year admissions; schools whose academic year doesn't follow the
April–March Indian standard (international/CBSE-vs-state variance) — genuinely `NEEDS_CONFIRMATION`,
not assumed.

**Regression risks.** Any frontend or report that parses `grade` as a raw string.

**Complexity:** Large. **Risk:** High (schema foundation others build on; hard to reverse once
`SchoolStudent` rows are backfilled).

---

## ENH-002 — Academic Team Role: Capability Completion & Actor-Separation Audit

**Title.** Complete and verify the Academic Team role against its full source capability list and its
governing separation-of-duties decision.

**Business requirement.** `School CRM.md §13` (`EVID-014`): *"Academic Team — Can: Upload academic
results · View academic progress."* Role existence and portfolio scoping are already
`CONFIRMED_CURRENT` (`DEC-ROLE-006`, `DEC-SCOPE-013`, `DEC-SCOPE-014`); the actor-separation rule is
`DEC-ROLE-007` (CONFIRMED_CURRENT): the member who uploads a result may never also verify/publish it.

**Existing behavior.** Role is live in code: `apps/api/app/core/rbac.py:47` grants one coarse
permission, `school:academic_team:portfolio`. `SCH-006` (Academic Results, Draft→Verified→Published
gate) is status `CURRENT` per `MASTER_FEATURE_CATALOG.md`, so "Upload academic results" is built.
**Correction, this turn:** `DEC-ROLE-007`'s different-actor rule *is* confirmed enforced —
`SchoolAcademicResult`'s own docstring (`models.py:1143-1147`) states outright that
`verified_by_user_id`/`published_by_user_id` must each differ from `uploaded_by_user_id`, "enforced at
the application layer (SCH-006-AC04)" — this is no longer an open audit question. What remains genuinely
unconfirmed: whether "View academic progress" exists as its own portfolio-wide trend/summary view (as
opposed to just the per-result records the upload flow already produces). **Also found this turn, a
real field gap:** `SchoolAcademicResult` has no `teacher_remarks` field at all, even though
`School CRM.md` Part B §9's own Result Entry field list explicitly includes "Teacher Remarks"
(`docs/sources/School CRM.md:1680`) — every other field in that list (`Academic Year`, `Term`,
`Subject`, `Maximum Marks`, `Marks Obtained`, `Grade`, `Uploaded By`) is present in the model
(`models.py:1149-1163`); this one is missing.

**Expected behavior.** Confirm or build a portfolio-wide "view academic progress" surface (trends
across a member's assigned schools, not just individual Draft/Verified/Published records); add the
missing `teacher_remarks` field to `SchoolAcademicResult`, editable by the uploading Academic Team
member alongside the marks entry, visible wherever the result itself is visible (Parent/Student/Teacher,
once published).

**User roles affected.** `academic_team`; indirectly `school_parent`/`school_student` who consume
published results, and `school_coordinator`/`school_principal` who view school-level reports.

**Frontend impact.** `SchoolAcademicTeamDashboardPage` (confirmed present via graphify community
detection) — extend if the progress view is missing; no new page if it already exists.

**Backend impact.** Possible new read endpoint (portfolio progress aggregation); possible new guard
clause in the existing publish/verify endpoint.

**Database impact.** One new nullable `teacher_remarks` column on `SchoolAcademicResult` (small,
additive migration); separately, TBD if the progress-view aggregation needs a materialized/summary
table for performance at scale.

**API impact.** Possible new `GET` endpoint under the academic-team namespace; no breaking change to
existing upload/verify/publish endpoints.

**Integration impact.** None identified.

**Authentication impact.** None.

**Authorization impact.** Tightens enforcement of `DEC-ROLE-007` if currently unenforced — this is the
core of the item.

**Security impact.** Medium — a missing actor-separation check is a real integrity control gap (single
person could self-approve fraudulent results).

**Performance impact.** Low, unless the progress view requires cross-portfolio aggregation over a large
result set without an index — profile before shipping if so.

**Reusable existing modules.** Existing `SchoolStaffAssignment` portfolio-scoping pattern
(`DEC-SCOPE-013`); existing Draft/Verified/Published state machine from `SCH-006`.

**Dependencies.** None.

**Acceptance criteria.**
- Audit finding documented on the one remaining open question (progress view exists / doesn't) before
  any code is written for it — the separation-enforcement question is already closed, confirmed
  enforced.
- `teacher_remarks` can be set by the uploading Academic Team member and is visible to Teacher/Parent/
  Student once the result is published, matching every other field's existing visibility rule.
- If the progress view is missing: an Academic Team member can see aggregate progress across their
  full portfolio, scoped only to schools in their `SchoolStaffAssignment`.

**Positive scenarios.** Member A uploads, Member B verifies and publishes — succeeds.

**Negative scenarios.** Member A uploads, Member A attempts to verify/publish the same result —
rejected.

**Edge cases.** A school's Academic Team portfolio has exactly one assigned member — per `DEC-ROLE-007`
this member can never publish anything for that school; this is a known, decision-confirmed
operational consequence, not a bug, but must be surfaced (e.g. a clear UI message, not a silent stuck
state) rather than left to look like an error.

**Regression risks.** Existing `SCH-006` upload/verify/publish tests must keep passing after any guard
clause is added.

**Complexity:** Medium. **Risk:** Medium (security-integrity control, but narrow blast radius).

---

## ENH-003 — First-Time User Provisioning: Welcome Email + Set-Password Link for All Admin-Provisioned Roles

**Title.** Guarantee every admin-created account — not just school-invited ones — receives a secure,
emailed, single-use, expiring set-password link on first creation.

**Business requirement.** User's explicit instruction: *"send an email for first time user creation and
updates the password from mail link."* `DEC-SCOPE-014` (CONFIRMED_CURRENT) mandates that
`academic_team`/`career_counselor`/`psychometric_team` accounts are created **only** by Overseas Admin
or Super Admin via the existing Admin console pattern (`admin.py:create_user()`), explicitly **not**
via `SchoolAccountInvite`.

**Existing behavior.** Two provisioning paths exist and diverge:
1. `SchoolAccountInvite` + `accept_invite()` (`apps/api/app/api/schools.py:189-218,510-535`) — used for
   `school_coordinator`/`school_teacher`/`school_parent`. Confirmed: hashed, single-use, expiring
   token; email sent; `accept_invite(token, payload)` sets the password on first use (min length 10).
2. Admin-provisioned accounts — **audit result 2026-09-18: gap CONFIRMED** (`DEC-SCOPE-019`). Three
   routes in `apps/api/app/api/admin.py` fall back to the hard-coded password `ChangeMe@12345` and send
   no email: `POST /admin/users` (`create_user`), `POST /overseas-admin/schools` (Coordinator seed) and
   `POST /overseas-admin/school-staff` (`create_school_staff`). Correction to this item's first draft:
   the route `DEC-SCOPE-014` mandates for `academic_team`/`career_counselor`/`psychometric_team` is
   `create_school_staff`, not `create_user`. The admin UI displays the default password
   (`AdminSchoolStaffPanel.tsx`, `AdminSchoolCreatePanel.tsx`) and `WorkflowPanel.tsx` asks for a
   "Temporary password". `forgot_password()` sends its token via the generic webhook only, and
   `mailer.py` has no password-link template.

**Expected behavior.** If path 2 currently returns/sets a plaintext or admin-visible temporary
password: replace it with the same security properties as path 1 (hashed, single-use, expiring,
emailed link) — reusing the existing token/email primitive rather than duplicating it, but **not**
routing through the `SchoolAccountInvite` table/entity itself, per `DEC-SCOPE-014`'s explicit routing
constraint. If path 2 already does this correctly, this item closes as "audited, no gap" (same
treatment as forgot-password above) rather than being implemented for its own sake.

**User roles affected.** `academic_team`, `career_counselor`, `psychometric_team`, and any other role
provisioned via `admin.py:create_user()` (e.g. `it_admin`, `overseas_admin` peers) rather than an
invite flow.

**Frontend impact.** Remove the displayed default password (`AdminSchoolStaffPanel.tsx`,
`AdminSchoolCreatePanel.tsx`) and the "Temporary password" field (`WorkflowPanel.tsx` create-user
form). Add an "Expired link" status, filter and Re-send action to `AdminUserManagementPanel.tsx`, and a
count + list of expired-unused welcome links on the Super Admin, IT Admin and Overseas Admin
dashboards (division-scoped as `GET /admin/users` is today). Reset pages may show "Set your
password" copy for `welcome` tokens.

**Backend impact.** Extend/reuse the token-issuance and email-send primitives from
`_create_and_send_invite()` (`schools.py`) in a role-agnostic form, called from `admin.py:create_user()`.

**Database impact.** Decided (`DEC-SCOPE-019`): extend `password_reset_tokens` (`PasswordResetToken`)
with a `purpose` column (`reset` | `welcome`, existing rows backfilled to `reset`) and a nullable
`superseded_at` (set when Re-send replaces an unused token, so a superseded token never reads as an
unresolved expired link). New migration `0032`. No new table; `SchoolAccountInvite` is untouched.
New accounts are created with a random, discarded, unusable password hash — never a constant.

**API impact.** `POST /admin/users`, `POST /overseas-admin/schools` and `POST /overseas-admin/school-staff`
stop accepting `password`/`coordinator_password`; their responses gain `email_status` and `expires_at`
(mirroring the invite response) and never contain a password. New admin Re-send endpoint. `GET /admin/users`
exposes a derived provisioning status. `development_welcome_token` is returned in `development`/`test`
only, following the existing invite/forgot-password pattern.

**Integration impact.** Reuses the existing transactional-email integration already wired for invites/
forgot-password.

**Authentication impact.** Directly — this is account-provisioning security.

**Authorization impact.** None (provisioning is already Super Admin/Overseas Admin gated per
`DEC-SCOPE-014`).

**Security impact.** **High** if the audit finds a plaintext/admin-visible temporary password today —
that's a credential-handling gap (the password would exist in cleartext in a response payload, logs,
or admin memory) worth prioritizing regardless of the rest of this backlog's sequencing.

**Performance impact.** Negligible.

**Reusable existing modules.** `_create_and_send_invite()` and its token hashing/expiry logic
(`schools.py`); existing email-template infrastructure (`password_reset` template pattern from
`auth.py`).

**Dependencies.** None upstream; ENH-007 should follow this item since profile completion assumes a
correctly provisioned account.

**Acceptance criteria.**
- Audit result documented explicitly (gap confirmed / not confirmed) before implementation begins.
  **Done, 2026-09-18: gap confirmed** (see Existing behavior; `DEC-SCOPE-019`).
- No endpoint, response, UI message or log ever contains a plaintext password for an admin-provisioned
  account, and no route falls back to a default password.
- The set-password link is single-use, hashed at rest, and expires after **72 hours**
  (`DEC-SCOPE-019`; forgot-password resets stay at 30 minutes).
- Consuming a `welcome` link sets `email_verified = True`.
- An admin can Re-send; the old token is superseded and unusable.
- Welcome links that expired unused are visible to admins in the Users directory (status, filter,
  Re-send) and as a count + list on the Super Admin, IT Admin and Overseas Admin dashboards, scoped by
  division; a superseded or used token never appears as expired.
- A failed or `not_configured` email send never blocks or rolls back account creation, and is
  recorded with its status/error (never the raw token, and with URLs redacted) in the audit log.
- Security hardening (`DEC-SCOPE-019` addendum, 2026-09-19): create routes reject malformed emails
  (`422`); a welcome link is refused for a deactivated account and revoked whenever an admin changes
  `active`; Re-send is throttled to once per 60 s per account after the first (`429` + `Retry-After`); the
  reset page is excluded from Google Analytics and served with `Referrer-Policy: no-referrer`; the API's
  `ENVIRONMENT` is `production` in every deployed environment.

**Positive scenarios.** Super Admin creates an Academic Team account; the new user receives an email,
clicks the link once, sets a password meeting the existing minimum-length rule, and can log in.

**Negative scenarios.** A second click on an already-used link is rejected; an expired link is
rejected with a clear "request a new invite" path.

**Edge cases.** Admin creates an account with an email that already belongs to an existing user under
a different role — must reuse the same conflict-handling discipline already proven in
`_parent_email_conflict()` (`schools.py:498-507`), not invent a new rule.

**Regression risks.** Existing `SchoolAccountInvite` flow (path 1) must not be altered by this change.

**Complexity:** Medium. **Risk:** High (credential-handling; prioritize the audit even if the rest of
the backlog is resequenced).

**Implementation status (2026-09-19): IMPLEMENTED and VERIFIED — deliberately not declared COMPLETE.** Built test-first on
branch `feature/enh-003-first-time-provisioning` per `docs/superpowers/plans/2026-09-19-enh-003-first-time-provisioning.md`
(see its "Implementation notes"). Evidence gathered fresh on the final tree: full backend suite **789 passed**; frontend
**13 files / 81 tests** passed; `tsc --noEmit` clean; ESLint **0 errors** (31 warnings, all pre-existing); production
`next build` succeeds; migration `0032` upgrades a legacy table without losing a row (existing tokens read `reset`), passes
`alembic check`, and downgrades and re-upgrades cleanly; the project's local CI runs the **full Playwright suite: 240 passed,
0 failed** (the base commit: 233 passed, 0 failed; +7 new); real-browser verification (Browser Use) passed **191 checks with
0 failures** across all 29 acceptance criteria. An independent code review was performed and its seven HIGH/MEDIUM findings
were verified and fixed; its LOW findings were the missing `RTM.md`/`SCREEN_CATALOG.md` entries (now added) and that the
Playwright spec has no successful reset-password UI submission (covered by the browser verification instead).

**Why this is not marked COMPLETE.** (1) The repository's own CI gate is red at the *base commit* and stays red with identical
counts: `ruff format --check` (55 files), `ruff check` (33 errors) and `mypy app` (154 errors). ENH-003 adds none of them
(verified by running the same tools on both trees), but "lint/type-check passes" cannot be claimed for the repo until that
existing debt is fixed or formally accepted — a decision for the owner. (2) Two acceptance criteria cannot be observed in the
QA environment: the API's `ENVIRONMENT=production` behaviour (AC-29, a deployment check) and the Google Analytics skip on the
reset page (AC-27, needs a GA id). (3) Six items are not observable from a browser and rest on backend tests alone (AC-15,
AC-17, AC-22, AC-25, and two review findings: delivery-audit failure and the reset/Re-send lock order). `DEC-SCOPE-014`'s
`SchoolAccountInvite` flow is untouched.

---

## ENH-004 — Student Promotion to Next Academic Year / Grade

**Title.** Bulk/individual promotion of students to the next grade at academic-year rollover.

**Business requirement.** User's explicit instruction to think broadly about user lifecycle: *"promoted
to upper grade in next year if required."* No matching Decision ID or Feature ID exists today
(confirmed by both the implementation survey and the governance survey) — this is genuinely new scope,
not a completion of partial work.

**Existing behavior.** None. `SchoolStudent.grade`/`grade_or_class` is a plain string set at roster
creation/edit time with no promotion workflow, no year concept, and no history of prior grades
(`apps/api/app/models.py:221,992,1157`).

**Expected behavior.** A `school_coordinator` (or `super_admin`/`overseas_admin`, pending role
decision) can advance a student — or bulk-advance an entire grade/section — to the next `grade_level`
under a new `AcademicYear`, preserving a history of prior grade/year assignments per student rather
than overwriting.

**User roles affected.** `school_coordinator` (initiator, consistent with its existing bulk-upload
authority per `bulk_upload_students`, `schools.py:1145`), `school_principal` (read/oversight),
`school_teacher` (their assigned-student view changes), `school_parent`/`school_student` (dashboard
reflects new grade). **Note:** if `school_student` login is in scope, this item inherits the unresolved
`DEC-ROLE-004`/`DEC-SCOPE-011` conflict flagged in §0 — promotion of the underlying `SchoolStudent`
*record* does not require that conflict to be resolved, but a student *self-viewing* their own
promotion via their own login does.

**Frontend impact.** New coordinator UI: promote-single / promote-bulk-by-grade action; updated parent
"My Children" card and student dashboard to reflect new grade/year.

**Backend impact.** New promotion endpoint(s); new authorization check restricting promotion to the
student's own school's coordinator/admin.

**Database impact.** Requires ENH-001's `academic_year_id`/`grade_level` columns to exist first; add a
`StudentGradeHistory` (or similar) table recording `student_id, academic_year_id, grade_level,
promoted_by_user_id, promoted_at` so history isn't lost on each promotion.

**API impact.** New `POST` endpoint(s), e.g. `POST /schools/{school_id}/students/{id}/promote` and a
bulk variant; additive to `API_CONTRACT.md`.

**Integration impact.** None identified.

**Authentication impact.** None.

**Authorization impact.** Must enforce the same "own institution only" scoping already used elsewhere
(`school:coordinator:own_institution`, `RBAC_MATRIX.md §2.12`) — a coordinator must not be able to
promote students at a school they don't manage.

**Security impact.** Medium — an unscoped promotion endpoint would let one school's coordinator alter
another school's roster data.

**Performance impact.** Bulk promotion of a large grade/section must not lock the roster table for an
extended period — batch the writes; needs a plan reviewed against `bulk_upload_students`'s existing
idempotency-key pattern (`schools.py:1145`, requires `Idempotency-Key` header) as precedent.

**Reusable existing modules.** `bulk_upload_students`'s batching/idempotency pattern; existing
`school:coordinator:own_institution` scoping; ENH-001's academic-year model.

**Dependencies.** **Hard dependency on ENH-001** — cannot be built before the academic-year/grade-level
model exists. Should be sequenced after ENH-001 lands, not in parallel with it.

**Acceptance criteria.**
- A coordinator can promote a single student or an entire grade/section in one action, scoped to
  their own school only.
- Each student's prior grade/year is preserved in history, retrievable, not overwritten.
- Parent and student dashboards reflect the new grade immediately after promotion.
- A coordinator cannot promote students at a school outside their own institution (`403`).

**Positive scenarios.** End-of-year bulk promotion of Grade 8 → Grade 9 for an entire section succeeds
and history is recorded for every student.

**Negative scenarios.** Attempted promotion by a coordinator scoped to a different school is rejected;
attempted promotion beyond the school's terminal grade (e.g. Grade 12) is rejected or routed to a
distinct "graduate/alumni" state — `NEEDS_CONFIRMATION` on the terminal-state behavior, not assumed.

**Edge cases.** A student held back a year (not promoted) — the workflow must support "no promotion
this cycle" as a deliberate action, not force every student forward; mid-year transfers interacting
with promotion timing (coordinate with ENH-005).

**Regression risks.** Any existing report, dashboard, or filter keyed off the raw `grade` string.

**Status (2026-09-20).** Designed and decided in `docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md` (`DEC-SCOPE-020`); implemented on branch `feature/enh-004-student-grade-promotion`; browser-validated 2026-09-20 on an isolated stack: the ENH-004 Playwright spec passes repeatedly (and restores the active academic years afterwards); every school/enhancement spec passes (per file, and 27/27 in one process); an earlier intermittent `POST /auth/logout` hang is **unexplained** and was not observed in the final runs (`RTM.md`); an independent exploratory browser pass found nine issues, seven fixed and re-verified and two app-wide and left open (record: `docs/quality/ENH-004_BROWSER_QA_2026-09-20.md`; the raw screenshots and scripts are not committed); the independent code review's four findings were addressed 2026-09-20. **COMPLETE for ENH-004's scope (2026-09-20)** on fresh evidence (full backend suite: the only failures are the 22 that also fail on the base commit); the recorded exclusions are listed in `RTM.md`. The line references above (`models.py:221,992,1157`, `schools.py:1145`) were stale when this item was drafted; the current definitions are `SchoolStudent` in `models.py` and `bulk_upload_students` in `schools.py`. The endpoint paths differ from the example above: the school is derived from the caller, never a path parameter (`POST /school/students/promotions`). A pre-existing exposure that would have defeated its cross-school guarantee (`PATCH /auth/me` could change `profile.school_id`, and, found by the code review, `profile.university_id`) was fixed (the first with the user's approval); the remaining out-of-scope security follow-ups are recorded in `DEC-SCOPE-020`.

**Complexity:** Large. **Risk:** High.

---

## ENH-005 — Student School Transfer / Reassignment

**Title.** Move a student's roster record from one school to another under proper authorization and
history.

**Business requirement.** User's explicit instruction: *"changing of schools etc."* No matching
Decision ID or Feature ID exists today (confirmed by both research passes) — genuinely new scope.

**Existing behavior.** None. `SchoolStudent.school_id` is a plain FK set at creation
(`apps/api/app/models.py:955,984`) with no transfer/reassignment endpoint anywhere in `apps/api`.

**Expected behavior.** An authorized actor (scope `NEEDS_CONFIRMATION` — likely `overseas_admin`/
`super_admin` rather than either school's own coordinator, to avoid one school unilaterally "pulling"
a student from another) can move a `SchoolStudent` record's `school_id` from School A to School B,
preserving a transfer history and correctly re-scoping every dependent relationship: `SchoolParentLink`
rows, `SchoolStaffAssignment`-scoped Academic Team/Career Counselor/Psychometric Team visibility, and
any in-flight Draft-status academic results at the old school.

**User roles affected.** Whichever role is confirmed as the transfer initiator; `school_coordinator` at
both the losing and gaining school (visibility change); `school_parent` (must re-consent or be
re-notified, since a transfer changes which institution their child's data lives under);
`school_teacher` (assigned-student list changes).

**Frontend impact.** New transfer-initiation UI (wherever the initiating role is confirmed to sit);
notification to both schools' coordinators.

**Backend impact.** New transfer endpoint with cross-school authorization; re-scoping logic for every
dependent relationship listed above.

**Database impact.** New `StudentTransferHistory` (or similar) table; requires deciding what happens to
in-flight Draft (unpublished) academic results at the losing school — carry them, discard them, or
freeze them read-only — `NEEDS_CONFIRMATION`, not assumed.

**API impact.** New `POST` endpoint, e.g. `POST /schools/{school_id}/students/{id}/transfer`.

**Integration impact.** None identified.

**Authentication impact.** None.

**Authorization impact.** This is the crux of the item: transfer must not be initiable by either
school's own coordinator unilaterally (that would let School B "steal" a student's enrolment record by
simply reassigning it) — needs a cross-school-authority actor, which is exactly why the initiator role
is `NEEDS_CONFIRMATION` rather than assumed to be `school_coordinator`.

**Security impact.** Medium-High — incorrect scoping here is a direct cross-tenant data-isolation risk,
the same class of risk `RBAC_MATRIX.md §2.12` was written to prevent for the rest of the School domain.

**Performance impact.** Low (single-row operation plus a bounded set of dependent-row updates).

**Reusable existing modules.** `SchoolStaffAssignment` portfolio-scoping pattern; `SchoolParentLink`
table (already many-to-many capable, per ENH-008's finding); `AuditLog` pattern already used for
password resets (`auth.py`) — reuse for transfer events too.

**Dependencies.** None hard-blocking, but shares `apps/api/app/api/schools.py` and
`apps/api/app/models.py` (`SchoolStudent`) with ENH-004 and ENH-008 — see §2 for sequencing guidance.

**Acceptance criteria.**
- A confirmed-authorized actor can transfer a student between schools in one action.
- All dependent relationships (`SchoolParentLink`, staff portfolio visibility, in-flight results) are
  handled per the decided policy, not left dangling or silently cross-visible.
- Transfer history is retrievable per student.
- Neither school's own coordinator can unilaterally transfer a student without the confirmed authority
  role.

**Positive scenarios.** Overseas Admin transfers a student from School A to School B; School A loses
visibility, School B gains it, parent link is preserved, history is recorded.

**Negative scenarios.** School B's coordinator attempts to transfer a student directly — rejected.

**Edge cases.** Student has a Draft (unpublished, per `DEC-ROLE-007`'s workflow) academic result at the
losing school at transfer time — policy `NEEDS_CONFIRMATION`; student has an active `SchoolParentLink`
to a parent who does *not* have a link at the gaining school — must not silently drop parent access.

**Regression risks.** `SCH-006` results workflow, `SCH-007` Parent Portal, `SCH-008` Student Journey
Timeline — all read `SchoolStudent.school_id` and must keep working after a transfer.

**Status (2026-09-21, re-verified; code unchanged since `5aa27bf`).** Designed and decided in `docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md` (`DEC-SCOPE-022`); implemented on branch `feature/enh-005-student-school-transfer`. **COMPLETE for ENH-005's scope (2026-09-21), with the recorded exclusions below.** The workflow is: a coordinator of either school files a request, an Overseas Admin or Super Admin approves or rejects it, approval is one transaction, and neither school can move a student alone. Fresh evidence (see `RTM.md` and `docs/quality/ENH-005_FINAL_BROWSER_VERIFICATION_2026-09-21.md`): web 291 tests, `tsc`, `eslint` (0 errors), `next build` pass; backend `mypy`, `ruff check` and `ruff format` at or better than `main` and clean on every ENH-005 file; backend 977 passed / 14 failed (the 14 provider-credential failures also fail on `main`); migration `0034` verified on a scratch database; Browser Use 90 PASS / 12 NOT TESTABLE / 1 FAIL (AC-18, resolved). **AC-18 resolved (no regression):** the 4 failing existing Playwright tests were built and run on the baseline `550c4fe7` (the commit ENH-005 was cut from, no ENH-005 code, the same three spec files and `SchoolStudentsPanel.tsx` byte-identical) against the same database, and fail identically there: `sch-004-005-006:189`/`:241` (expected 1 school, received 5 and 6), `sch-team-management:79` (`#edit-teacher` is `""`, line 101), `enh-003:91` (1 pass, 1 fail of 2). They are pre-existing under used-database conditions, not caused by ENH-005 (`ENH-005_FINAL_BROWSER_VERIFICATION_2026-09-21.md`, "Baseline comparison"). Full Playwright suite (244 tests, `api` rebuilt for HEAD): **240 passed / 4 failed** in 9.3m; the 4 failures are 3 proven pre-existing on the baseline `550c4fe7` (`sch-004-005-006:189`/`:241`, `sch-team-management:79`) and 1 `@external` Razorpay test that needs real credentials (excluded by the owner for now). **Recorded exclusions, not hidden:** the provider-credential tests that need real Razorpay/Zoho keys (14 backend, which fail identically on `main`, and 1 Playwright, not compared with the baseline); 12 browser checks that a browser cannot observe (fault injection, promotion race, the 50-request cap, query counts, e-mail body, logs, audit metadata, a linked non-parent, the one-hour throttle lapse), covered by backend tests; the Browser Use pass ran on the `api` build before the typing refactor `5aa27bf` (the refactor is covered by the 94 ENH-005 backend tests, the 977-pass backend suite and this full Playwright run on the rebuilt `api`); browsers other than Chrome, screen readers and touch devices were not covered; the branch has not been merged into `main`; a pull request is being opened from it. **Re-verified on the merge with `main` (ENH-006), 2026-09-21, merge commit `65d1a2d`:** web 35 files / 333 tests, `tsc` 0, `eslint` 0 errors, `next build` 0; backend 1023 passed / 14 failed (the same 14 provider-credential tests); `ruff check` 33 and `mypy` 154 in 11 files, both equal to `main`; full Playwright 259 tests on rebuilt `api`/`web`: 252 passed / 7 failed, the 7 being the 4 known plus `enh-003:91` (flaky, fails on the baseline too) plus `ovs-001:7` and `stu-007:8`, which were scratch-database state and pass 3 of 3 each after it was repaired (record: `docs/quality/ENH-005_FINAL_BROWSER_VERIFICATION_2026-09-21.md`, last section). `ENH-005`'s decision ID became `DEC-SCOPE-022` because `ENH-006` holds `DEC-SCOPE-021`. **Nothing else is outstanding.** **Decided (owner, 2026-09-21):** parents invited but not yet accepted at transfer time keep today's behavior with the admin warning (`DEC-SCOPE-022`); the invite is not carried to the gaining school. Deliberately not decided or built: consent from the other school, bulk transfer, branch moves (`ENH-009`), multi-school parents beyond the recorded rule (`ENH-008`).

**Complexity:** Medium. **Risk:** Medium.

---

## ENH-006 — Self-Service Change Password (Authenticated)

**Title.** Let a logged-in user change their own password without going through the forgot-password
email flow.

**Business requirement.** User's explicit instruction: *"change password."* Confirmed gap: `auth.py`
has only the forgot/reset pair (`forgot_password()` line 155, `reset_password()` line 179) — no
`change-password` route exists for an already-authenticated user.

**Existing behavior.** A logged-in user who wants to change their password today has no in-session
path; they would have to log out and use forgot-password, which is poor UX and also weaker (it doesn't
require knowing the *current* password, which a proper change-password flow should).

**Expected behavior.** `POST /auth/change-password` (or similar), authenticated, requiring the current
password plus a new password meeting the existing minimum-length rule (10 chars, matching
`accept_invite`'s rule), invalidating other active sessions optionally (`NEEDS_CONFIRMATION` on
session-invalidation policy).

**User roles affected.** All authenticated roles — this is role-agnostic.

**Frontend impact.** New "Change password" form in account/profile settings, available to every role's
portal shell.

**Backend impact.** New endpoint in `auth.py`, reusing existing password-hashing utilities.

**Database impact.** None — writes to the existing `password_hash` field.

**API impact.** New endpoint, additive to `API_CONTRACT.md §1`.

**Integration impact.** None.

**Authentication impact.** Direct — must re-verify the current password before accepting a new one
(standard defense against a hijacked-but-still-authenticated session).

**Authorization impact.** Self-only; no cross-user concern.

**Security impact.** Positive (closes a real gap) if implemented with current-password verification and
rate-limiting on failed attempts; negative if either is skipped — both must be in the acceptance
criteria, not left implicit.

**Performance impact.** Negligible.

**Reusable existing modules.** Existing password-hashing/verification utilities already used by
`register()`/`reset_password()`; existing `AuditLog(action="auth.password_reset")` pattern — add a
parallel `auth.password_change` action for audit consistency.

**Dependencies.** None. No shared files with the School-domain items — safe to run fully independently
and first.

**Acceptance criteria.**
- Authenticated user can change their password by supplying current + new password.
- Wrong current password is rejected with a generic error (no hint about what's wrong beyond
  "incorrect current password"), rate-limited after repeated failures.
- New password enforces the same minimum-length rule as the rest of the system.
- Change is audit-logged.

**Positive scenarios.** User supplies correct current password and a valid new password; password
updates; user can log in with the new password afterward.

**Negative scenarios.** Wrong current password rejected; new password below minimum length rejected;
repeated failed attempts rate-limited.

**Edge cases.** New password identical to current password — decide reject-vs-allow
(`NEEDS_CONFIRMATION`, minor); changing password while other sessions are active —
session-invalidation policy `NEEDS_CONFIRMATION`.

**Regression risks.** Minimal — isolated new endpoint, no existing behavior modified.

**Complexity:** Small. **Risk:** Low.

**Status (2026-09-21).** Designed and decided in `docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md` (`DEC-SCOPE-021`); implemented and verified on branch `feature/enh-006-change-password` (complete for ENH-006's scope, 2026-09-21; evidence in the `RTM.md` `ENH-006` row). Corrections to this entry: the routes are now at `forgot_password()` line 175 / `reset_password()` line 198; the minimum-length rule is the registration/reset rule (10–128), not `accept_invite`'s; the audit actions are `auth.change_password` / `auth.change_password_failed`, not `auth.password_change`; database impact is still none (the limiter counts existing audit rows); other sessions are **not** invalidated. Open, not decided here: login/forgot/reset throttling, session invalidation, a notification email, and the public header hiding its secondary buttons on phones (the portal menu now carries the entry point; the header link itself was removed after browser QA, spec §13).

---

## ENH-007 — Profile Self-Service: Cross-Role Completion Audit

**Title.** Confirm every School-domain role has an appropriate, working self-service profile view/edit
surface, not just the two roles already confirmed.

**Business requirement.** User's explicit instruction to think broadly about *"user profile, updating
profile."* Confirmed today: `GET/PATCH /auth/me` (generic, `API_CONTRACT.md:52-53`) and
`GET/PATCH /student/profile` + document upload (`STU-011`, IT-student-specific,
`API_CONTRACT.md:104-105`). **Not confirmed** whether `school_coordinator`, `school_principal`,
`school_teacher`, `school_parent`, `academic_team`, `career_counselor`, `psychometric_team`, and
`school_partnership_manager` each have adequate self-editable profile fields and a working frontend
surface, or fall back to the generic `/auth/me` with fields that don't actually fit their role.

**Existing behavior.** Generic `/auth/me` exists for every authenticated user; a School-domain-specific
profile experience is unconfirmed beyond that.

**Expected behavior.** Each School-domain role has a profile view/edit experience with fields relevant
to that role (e.g. a teacher's assigned-subject list is read-only/admin-set but their contact details
are self-editable; a parent's own contact details are self-editable but their linked-children list is
not, since that's roster-driven per ENH-008).

**User roles affected.** The 7 School-domain roles with real RBAC grants (`school_coordinator`,
`school_principal`, `school_teacher`, `school_parent`, `academic_team`, `career_counselor`,
`psychometric_team`). **Correction, post-audit:** the eighth role named above, `school_partnership_manager`,
has no RBAC grants and is explicitly deferred (`RBAC_MATRIX.md:239-241`, `PRD_OPEN_ITEMS.md` item 75) — it
cannot be given a working profile screen and is out of this item's scope; see
`docs/quality/ENH-007_ROLE_AUDIT.md`.

**Frontend impact.** Audit existing portal shells per role; build missing profile screens.

**Backend impact.** Possibly extend `/auth/me`'s field set per role, or confirm it's already
sufficient — audit first.

**Database impact.** None expected; TBD if role-specific fields are found missing from `User.profile`
(the existing JSON blob already used for `school_id`, per `schools.py:505`).

**API impact.** Possibly none if `/auth/me` already suffices per role; possibly additive field support.

**Integration impact.** None.

**Authentication impact.** None.

**Authorization impact.** Self-only edits; must not allow a role to edit fields reserved for admin/
coordinator control (e.g. a teacher editing their own `assigned_grade`/`assigned_section` would bypass
the "assigned by coordinator" model implied by School CRM.md's teacher-scoping example,
`docs/sources/School CRM.md:1423-1430`).

**Security impact.** Low, contingent on the authorization boundary above being respected.

**Performance impact.** Negligible.

**Reusable existing modules.** Existing `/auth/me` endpoint and `User.profile` JSON field.

**Dependencies.** Should follow ENH-003 (a correctly provisioned account is a precondition for a
meaningful profile-completion flow) and be aware of ENH-008's change to how `school_parent.profile`
represents school affiliation.

**Acceptance criteria.**
- Audit finding documented per role: adequate / needs extension / needs new screen.
- No role can self-edit a field that School CRM.md or an existing Decision ID reserves for
  admin/coordinator control.

**Positive scenarios.** A `school_teacher` updates their contact phone number via profile self-service;
change persists and is visible to the coordinator.

**Negative scenarios.** A `school_teacher` attempts to self-edit their assigned grade/section —
rejected.

**Edge cases.** `school_student` self-profile inherits the `DEC-ROLE-004`/`DEC-SCOPE-011` login
conflict flagged in §0 — if reconciliation lands on "school students don't get a login," this role
falls out of this item's scope entirely.

**Regression risks.** Existing `/auth/me` and `/student/profile` behavior must not change for roles
outside the School domain.

**Complexity:** Medium. **Risk:** Low.

**Status (2026-09-22).** Designed and decided in
`docs/superpowers/specs/2026-09-22-enh-007-profile-self-service-design.md`; implemented via strict TDD on
branch `feature/enh-007-profile-self-service-audit` (7 tasks, each with an implementer + reviewer cycle,
all reviewed clean; a final whole-branch review found no Critical issues, and this status block records
that review's fix wave). **Browser validation complete, 2026-09-22** (real Chrome via `browser-use`
against the live stack, :3020): all 7 School-domain roles individually verified (correct dashboard
landing, "My profile" front-loaded in the desktop sidebar footer right after "Change password", page
renders with current name/phone, edit + save + reload-persistence, then restored to seeded values); the
mobile menu at 375px confirmed "My profile" front-loaded there too, no overflow; a 1-character full name
submission produced a real inline 422 error with nothing saved server-side (confirmed via the API
directly); a simulated offline network showed the "Network error. Try again." message with no false
success; a signed-out visit showed "Sign in required" with working sign-in links. No defects found in any
of the 7 roles or the 4 cross-cutting states. **Independent Codex review run and dispositioned, 2026-09-22**
(`codex review --base main`): one real finding (P2) -- a padded single-character `full_name` (e.g. `"A "`)
passed raw `min_length=2` and the blank-check, then saved post-trim as one character, bypassing AC-04.
Fixed test-first (3 parametrized RED cases, reproduced live against the API before the fix), full ENH-007
suite and the targeted regression scope re-run clean after. **COMPLETE for ENH-007's scope, 2026-09-22.**
Final evidence: `apps/api/tests/test_enh_007_profile_self_service.py` (23 passed), full backend suite (1043
passed / 14 failed, the 14 being the same pre-existing Razorpay/Zoho credential-gated failures recorded
against ENH-005/006, none in ENH-007), `apps/web/tests/components/{ProfileForm,AccountProfilePage,
PortalShell}.test.tsx` plus the full frontend suite (351 passed, 37 files), `apps/web/tests/e2e/
enh-007-profile-self-service.spec.ts` + regression scope (14 passed), `tsc --noEmit` and `eslint` (0
errors/warnings), `next build` (exit 0, `/account/profile` present in the route table), no migration
(`alembic check` confirms no drift), no disabled tests/debugging code/exposed secrets, 16 files changed,
all ENH-007-scoped. Full detail: `docs/quality/RTM.md` `ENH-007` row.

---

## ENH-008 — Parent Account Linked to Children Across Multiple Schools

**Title.** Allow one parent account to be linked to children enrolled at different schools, not just
one.

**Business requirement.** User's explicit instruction: *"parent may [have] children from different
schools."* `School CRM.md §4` ("Parent Login," `docs/sources/School CRM.md:1432-1476`) shows a parent
switching between two children's profiles but never states — and never rules out — that those children
attend different schools. No Decision ID addresses this either way; genuinely open, not contradicted.

**Existing behavior.** **Hard-blocked today.** `_parent_email_conflict()`
(`apps/api/app/api/schools.py:498-507`) rejects linking a parent email to a student if the existing
account under that email has `role != "school_parent"` **or**
`(existing_user.profile or {}).get("school_id") != str(school_id)` — i.e. a `school_parent` account
carries exactly one `school_id` in its profile, and any attempt to link that same email to a student at
a *different* school is rejected with "belongs to an existing account that is not a Parent at this
school" (`schools.py:505-506`). The underlying `SchoolParentLink` join table itself is already
many-to-many capable (`UniqueConstraint("parent_user_id", "school_student_id")`,
`models.py:1010`) — the constraint is purely in the single-`school_id`-per-profile application logic,
not the schema.

**Expected behavior.** A parent's school affiliation should be derived from the set of their
`SchoolParentLink` rows (which schools their linked children actually attend), not a single value
stored on their profile. `_parent_email_conflict()` should allow linking as long as the email either
belongs to a genuinely new account or an existing `school_parent` account regardless of which school(s)
it's already linked to — only rejecting non-`school_parent` roles.

**User roles affected.** `school_parent`; indirectly `school_coordinator` at each school the parent is
linked to (roster edit/bulk-upload flows that call `_link_or_invite_parent`).

**Frontend impact.** Parent dashboard's "My Children" view must group/label children by school (School
CRM.md's own example already implies a switcher UI, `docs/sources/School CRM.md:1466-1476` — extend it
to show which school each child belongs to, not just grade).

**Backend impact.** Remove/relax the single-`school_id` check in `_parent_email_conflict()`
(`schools.py:498-507`); any other code path currently reading `User.profile["school_id"]` as if a
parent has exactly one school must be found and updated to derive scope per-request from
`SchoolParentLink` instead.

**Database impact.** No new table needed (`SchoolParentLink` already supports this).

**Correction (design session, 2026-09-22, `EXPLICIT_APPROVAL`):** this entry originally said a
migration was still required, to deprecate/backfill `school_parent` accounts' now-ambiguous
`profile["school_id"]`. Put to the user directly during design (`docs/superpowers/specs/2026-09-22-
enh-008-parent-multi-school-design.md` §3), the decision was: leave existing `profile["school_id"]`
values alone, no migration, no backfill -- the field is simply never read for authorization for the
`school_parent` role again (confirmed by direct code audit: every read site derives parent scope from
`SchoolParentLink` rows only). Zero risk of a migration touching production data incorrectly, and
nothing downstream can accidentally resurrect the old behavior since the reading code is gone, not
merely bypassed. `accept_invite()` also stops *writing* `profile["school_id"]` for new `school_parent`
accounts (`schools.py:262`); existing stale values on older accounts are inert.

**API impact.** Parent-facing "my children" read endpoint(s) must return each child's school
explicitly rather than assuming one school for the whole response.

**Integration impact.** None identified.

**Authentication impact.** None.

**Authorization impact.** **This is the core of the item.** Every place that currently authorizes a
`school_parent` action by comparing `profile["school_id"]` to the target school must instead check
"does a `SchoolParentLink` row exist linking this parent to a student at this school" — a strictly
per-request, per-school-student check rather than a single cached value on the profile. Getting this
wrong in either direction is a real cross-tenant risk: too loose leaks another school's data, too
strict keeps the current bug.

**Security impact.** Medium — this item is specifically about correcting an authorization model, so it
needs the same scrutiny as any RBAC change, including a check that a parent linked at School A cannot
see School B's data merely by virtue of also being linked at School B for a different, unrelated
reason (scope must stay per-child, not "any linked school").

**Performance impact.** Negligible — `SchoolParentLink` lookups are already indexed by the existing
unique constraint.

**Reusable existing modules.** `SchoolParentLink` table and its existing unique constraint;
`_link_or_invite_parent()`'s existing linked-vs-invited-vs-reused branching logic
(`schools.py:510-538`) — only the conflict check needs to change, not the rest of that function.

**Dependencies.** Shares `apps/api/app/api/schools.py` and the `SchoolParentLink`/`User.profile` model
with ENH-004 and ENH-005 — see §2 for file-overlap sequencing.

**Acceptance criteria.**
- A parent email already linked to a `school_parent` account at School A can be successfully linked to
  a student at School B, producing a second `SchoolParentLink` row, not a rejection.
- The parent's dashboard shows both children, each correctly attributed to their own school.
- A parent cannot see any data for a school they have zero `SchoolParentLink` rows at.
- A non-`school_parent` account (e.g. an `academic_team` member's email) is still correctly rejected
  when used as a parent_email — this existing protection must not regress.

**Positive scenarios.** Parent with Child 1 at School A and Child 2 at School B logs in once and
switches between both, each showing correct school-scoped data.

**Negative scenarios.** Attempt to link a parent email that belongs to a `school_coordinator` account —
still rejected (role check preserved).

**Edge cases.** A parent linked at two schools where one school later transfers a shared child (interacts
with ENH-005) — must not accidentally drop the parent's link at the losing school if they still have a
child there.

**Regression risks.** `SCH-002` (roster/bulk-upload), `SCH-007` (Parent Portal) — both exercise
`_link_or_invite_parent()`/`_parent_email_conflict()` directly and must keep passing.

**Complexity:** Medium. **Risk:** Medium.

---

## 1.5 Full functional coverage audit

Every numbered section of `docs/sources/School CRM.md` (both its §§1–36 "brochure" pass and its
separately-renumbered §§1–15 "role/login" pass), checked against the live codebase and
`MASTER_FEATURE_CATALOG.md`. `✅ Built` = confirmed in code/decisions. `⚠️ Partial` = some of the
section is built, rest isn't. `❌ Gap` = not found anywhere; now has an ENH item. `— No action` = a
gap, but deliberately not converted into a full ENH item this pass (reason given).

| § | Section | Status | Evidence / disposition |
|---|---|---|---|
| 1 | School Dashboard (KPIs, charts) | ⚠️ Partial | Rolled into **ENH-016** (analytics dashboards) |
| 2 | School Master / School Profile (incl. **School ID**, **Branch**) | ❌ Gap | `models.py:923-943` has only `id`/`name`/`city`/`state`/`tier` — see **ENH-009** |
| 3 | Student Master | ✅ Built | `SchoolStudent`, `SCH-002`; `student_code` per `DEC-DATA-003` |
| 4 | Grade & Class Management (Grade→Section→Year) | ❌ Gap | See **ENH-001** (corrected sourcing above) |
| 5 | Career Awareness / Guidance | ✅ Built | `SCH-004` |
| 6 | Psychometric Test Module | ❌ **Gap, corrected** — this row was wrong | Originally marked fully built. Verified this turn against `SchoolPsychometricRecord` (`models.py:1097-1105`): only 4 of the source's 12 "Store:" fields exist (`assessment_type`, `report_url`, `status`, and `created_at`≈Test date). Missing: Strengths, Interest areas, Personality indicators, Career recommendations, Recommended streams, Counsellor remarks, Parent discussion, Follow-up. See **ENH-027** |
| 7 | Individual Career Counselling | ❌ **Gap, corrected** — this row was wrong | Originally marked "likely covered, no item needed." Verified this turn against `SchoolCareerRecord` (`models.py:1085-1094`): it's a flat `school_student_id`/`counselor_id`/`record_type`/free-text-`notes` table — none of §7's 17 fields are structured beyond Student/Counsellor/Date, and the entire Not-Started→Scheduled→Completed→Follow-up-Required→Completed status workflow is absent. See **ENH-026** |
| 8 | Student Career Profile / Career Passport | ❌ Gap | See **ENH-013**, checked this turn: its aggregation covers most of §8's example fields via existing tabs, but two are not explicitly covered anywhere — a distilled single "Career Goal" field (distinct from ENH-026's more granular Recommended-careers list) and a standalone "Achievements" entity (ENH-013's original sub-entity list only named Skills/Activities/Certificates/Teacher-Remarks/Parent-Communication — Achievements was missed). Both added to ENH-013 below |
| 9 | Soft Skills Module | ❌ Gap | See **ENH-011** |
| 10 | Web Designing / Digital Skills | ❌ Gap | See **ENH-011** |
| 11 | Foreign Language Management | ✅ Built | `SCH-009` |
| 12 | English / IELTS Training | ✅ Built | `SCH-009` |
| 13 | SAT / Test Preparation | ✅ Built | `SCH-009` |
| 14 | Digital Portfolio | ❌ Gap | Confirmed `OPEN` in `PRD_OPEN_ITEMS.md` item 77 — see **ENH-012** |
| 15 | Global Education Module | ✅ Built | `SCH-010` (bridge) |
| 16 | University Shortlisting (school-visible) | ⚠️ Partial | Bridge exists (`SCH-010`); school-facing dashboard view not confirmed — see **ENH-017** |
| 17 | Top 100 University Tracking dashboard | ❌ Gap | See **ENH-017** |
| 18 | Scholarship Management (school-visible) | ⚠️ Partial | See **ENH-017** |
| 19 | Application Support (status-only, school-visible) | ⚠️ Partial | See **ENH-017**; note source text itself says school should NOT see full detail — respect that boundary |
| 20 | Visa Tracking (school-visible) | ⚠️ Partial | See **ENH-017** |
| 21 | Financial Support / Loan Assistance | ❌ Gap | See **ENH-020** |
| 22 | Internship Management | ❌ Gap | See **ENH-021** |
| 23 | Parent Portal | ✅ Built | `SCH-007`; "Skills"/"Portfolio" sub-items depend on ENH-012, ENH-011 |
| 24 | School Event Calendar | ❌ Gap | See **ENH-019** |
| 25 | Edusphere School Counsellor tracking | ⚠️ Partial | `career_counselor` role exists; dedicated conversion/admission tracking not confirmed — rolled into **ENH-016** |
| 26 | School Partnership Package Tracking (quota table) | ⚠️ **Conflict** | Source shows Entitled/Used/Balance quotas; `DEC-SCOPE-017` (confirmed) made entitlements **unlimited, not quota-capped**. See Appendix A item 3 — this is a decision conflict, not an implementation gap |
| 27 | School Service Utilization | ❌ Gap | Rolled into **ENH-016** |
| 28 | Student Progress Scorecard | ❌ Gap | Rolled into **ENH-016** |
| 29 | School Performance Dashboard | ❌ Gap | Rolled into **ENH-016** |
| 30 | Reports & Downloads | ❌ Gap | See **ENH-015** |
| 31 | School Feedback | ✅ Built | See **ENH-018** |
| 32 | Communication Centre (WhatsApp/SMS/Email/push) | ❌ Gap | See **ENH-014** |
| 33 | School Admin Login (role matrix) | ✅ Built | `DEC-SCOPE-011`, `rbac.py` |
| 34 | Edusphere Admin Side (cross-school dashboard) | ❌ Gap | Rolled into **ENH-016** |
| 35 | Student 360° View | ❌ Gap | See **ENH-013** |
| 36 | Complete School CRM Flow (pipeline diagram) | — No action | Conceptual/architectural map, not itself a buildable feature |
| B1 | School CRM Login Hierarchy (diagram) | — No action | Conceptual; matches confirmed role structure |
| B2 | School Master Login capabilities | ✅ Built | Fully covered by `SCH-002`/`SCH-003`; **"Activate/deactivate users"** verified 2026-09-22 (`ENH-010`, `DEC-SCOPE-025` drafted) — see the `ENH-010` backlog entry |
| B3 | Teacher Login | ✅ Built | `DEC-SCOPE-011`, `school_teacher` |
| B4 | Parent Login | ⚠️ Partial | Built for one school; multi-school case is **ENH-008** |
| B5 | Student Login | ⚠️ Partial | Inherits the `DEC-ROLE-004`/`DEC-SCOPE-011` conflict, §0. Dashboard field breadth feeds **ENH-013** |
| B6 | Edusphere Staff Access (cross-role result visibility) | ✅ Built | `SCH-006` publish gate |
| B7 | Result Visibility Workflow (diagram) | ✅ Built | `SCH-006` |
| B8 | Student Profile Central Record (15 tabs) | ❌ Gap | See **ENH-013** |
| B9 | Academic Results Module (field list) | ✅ Built | `SCH-006`, `models.py:1144` |
| B10 | Result Status (Draft→Submitted→Verified→Published) | — No action | Implemented as a deliberate 3-state `Draft→Verified→Published` (`models.py:1144` docstring names it explicitly) — a conscious simplification, not an oversight; no ENH needed |
| B11 | Notifications (multi-channel, on publish) | ❌ Gap | See **ENH-014** |
| B12 | Permission Matrix (table) | ✅ Built | Matches `RBAC_MATRIX.md §2.12`; used as reference, not a gap itself |
| B13 | Edusphere Staff Permissions (5 roles) | ✅ Built | `DEC-ROLE-006`; `edusphere_school_manager`/`school_partnership_manager` exact duty split still `OPEN` per that same decision — not re-litigated here |
| B14 | School CRM Dashboard (activity + academic performance) | ❌ Gap | Rolled into **ENH-016** |
| B15 | Student Journey Timeline | ✅ Built | `SCH-008` |

**Net result (revised again after two more corrections — §6 and §7 were both wrongly marked in earlier
passes of this audit):** of the 51 sections audited, 15 are `✅ Built`, 3 need `— No action`
(conceptual/diagrams or a deliberately-resolved simplification), and the remaining 33 are
`⚠️ Partial`, `❌ Gap`, or the one `⚠️ Conflict` (§26, now resolved — see Appendix A item 3). Of those
33, only two areas were already addressed by the original ENH-001–ENH-008 pass (§4 via ENH-001, and
Parent Login's multi-school case via ENH-008) — every other row now has an explicit disposition: a new
item (ENH-009 through ENH-027), a "rolled into" pointer to one of those, or a documented resolution.
**This audit itself has needed correcting three times (§26's conflict, §7's Career Counselling, and
§6's Psychometric Module were each first marked as fine and later found not to be) — treat this table
as reliable only up to the sections it has actually verified against the model/code, not as proof that
every remaining `✅ Built` row has been re-checked field-by-field.**

---

## ENH-009 — School Profile: Business-Facing School ID & Branch/Campus Model

**Title.** Decide and build the confirmed subset of the School Profile field list, starting with a
business-facing School ID and a Branch/campus model.

**Business requirement.** `School CRM.md §2` (`docs/sources/School CRM.md:64-116`, `EVID-014`) lists a
full School Profile: School ID, School Name, **Branch**, Address, City, State, Principal, Vice
Principal, Career Counsellor, School Coordinator, Contact numbers, Email, Website, Number of students,
Number of teachers, Grades available, Board (CBSE/ICSE/State/IB/Other), partnership date, package,
MoU, validity, Edusphere BDM, dedicated counsellor, monthly visit schedule.

**Existing behavior.** `School` (`apps/api/app/models.py:923-943`) has exactly seven fields: `id`
(UUID, not a business code), `name`, `city`, `state`, `created_by_user_id`, `tier`, `tier_valid_until`.
The model's own docstring is explicit that this is deliberate: *"Minimal, confirmed-scope-only fields
-- EVID-014's elaborate profile field list ... is DERIVED_BLUEPRINT only, not confirmed
(DEC-SCOPE-012). Add fields as BRD/PRD confirms them, not preemptively from that document."* There is
**no business-facing School ID** anywhere (`Student` has one via `student_code`/`DEC-DATA-003`;
`School` does not), and **no Branch/campus field or table exists anywhere in the codebase** (verified:
the only "branch" hit in `apps/api/app/**` is an unrelated git-branch reference in a code comment).

**Expected behavior.** **Elevated to mandatory scope (Revision 4):** the user has explicitly directed
that every field in this list must be covered — this is a real, direct instruction from the person
running this project, which satisfies this project's own `EXPLICIT_APPROVAL` bar (a genuine user
confirmation, not the source document's own use of a word like "approved"). This supersedes this item's
earlier framing of "most fields still need their own BRD/PRD confirmation pass" — all 24 fields below
are now in scope; only two of them (Branch, Edusphere BDM) carry a *design* question that must be
answered before they can be built, not a *scope* question about whether to build them at all:
1. **School ID** — a business-facing code, analogous to `DEC-DATA-003`'s Student ID pattern (8-char
   alphanumeric), distinct from the internal UUID primary key, referenced in reports/UI/communications.
2. **Branch** — requires a *design* decision, not a scope decision (scope is now mandatory): does
   "Branch" mean a single free-text field on `School`, or a separate `SchoolBranch` entity with its own
   roster/coordinator scoping? The two have very different RBAC and data-isolation implications
   (`RBAC_MATRIX.md §2.12`'s own-institution scoping currently assumes one `School` row = one isolated
   tenant) — resolve the design question, then build.
3. **Edusphere BDM** — the only field in this list with a *second* blocker beyond design: it names an
   internal role (`BDM`) that `Appendix B` explicitly marks as unapproved/blocked (`EVID-016`,
   `BDM Functionalities.md`, zero supporting evidence, inside the `PRD_OPEN_ITEMS.md` item-61 hard
   blocker). The field itself (a reference from `School` to the internal staff member who originated the
   partnership) is in scope per the mandatory directive above; storing a value in it naturally waits on
   the `BDM` role question in Appendix B, which is unchanged by this directive.
4. **All 21 remaining fields** — Address, Contact numbers, Email, Website, Number of students, Number
   of teachers, Grades available, Board, School partnership date, Agreement/MoU (Principal, Vice
   Principal, Career Counsellor, and School Coordinator are covered below under "Existing behavior,"
   with a note on how each is actually represented) — are plain additive columns/fields with no design
   fork and no blocker; build them as part of this item's migration.

**Field-by-field coverage as of this revision** (checked directly against `models.py:923-943`, the only
place `School`'s fields are defined):

| Field | Status | Note |
|---|---|---|
| School ID | ❌ Missing | No business-facing code exists (unlike `Student`'s `student_code`) |
| School Name | ✅ Covered | `name` |
| Branch | ❌ Missing | Needs the design decision above |
| Address | ❌ Missing | |
| City | ✅ Covered | `city` |
| State | ✅ Covered | `state` |
| Principal | ❌ Missing as a field | `school_principal` is a *role* held by a `User`, linked to this school via that user's `profile["school_id"]` — derivable, but the School record itself stores no "who is the Principal" reference |
| Vice Principal | ❌ Missing entirely | No role, no field — this role does not exist anywhere in the system today |
| Career Counsellor | ❌ Missing as a field | `career_counselor` is a role, portfolio-scoped via `SchoolStaffAssignment` — derivable by query, not stored on `School` |
| School Coordinator | ❌ Missing as a field | Same pattern as Principal — derivable via `User.profile["school_id"]`, not stored on `School` |
| Contact numbers | ❌ Missing | `User.phone` exists per-person (`models.py:26`) but `School` itself has no contact-number field |
| Email | ❌ Missing | |
| Website | ❌ Missing | |
| Number of students | ⚠️ Computable, not stored | A live `COUNT` of `SchoolStudent` rows, not a persisted field — reasonable as a computed value, but confirm it's actually exposed somewhere if this field is meant to be quickly readable without a query |
| Number of teachers | ⚠️ Computable, not stored | Same treatment |
| Grades available | ❌ Missing | No configured "which grades does this school offer" value distinct from individual students' grades |
| Board (CBSE/ICSE/State/IB/Other) | ❌ Missing | |
| School partnership date | ❌ Missing | `TimestampMixin`'s `created_at` is a loose proxy (record-creation time) but not an explicit business field, and may not equal the actual partnership start date |
| Partnership package | ✅ Covered | `tier` (Bronze/Silver/Gold/Platinum) |
| Agreement/MoU | ❌ Missing | No document/file-reference field |
| Partnership validity | ✅ Covered | `tier_valid_until` |
| Edusphere BDM | ❌ Missing | Field itself in scope; see the BDM-role blocker above |
| Dedicated Edusphere Counsellor | ✅ Covered | Modeled properly as a real relationship, `SchoolStaffAssignment` — confirmed via the existing `dedicated_counselor` check in `GET /schools/entitlements` (`schools.py:718`) — better than a flat field would have been |
| Monthly visit schedule | ⚠️ Retrospective only | `campus_visit` activity type is counted after the fact (`schools.py:717`); no forward-looking schedule exists — that's **ENH-019**'s job |

**Net: 6 of 24 fields are directly covered (`name`, `city`, `state`, `tier`, `tier_valid_until`, and the
`SchoolStaffAssignment` relationship for Dedicated Counsellor), 3 are covered relationally or as a
computed value rather than a stored field (Number of students, Number of teachers, Monthly visit
schedule — reasonable, not necessarily a defect), and 15 are genuinely missing** (School ID, Branch,
Address, Principal, Vice Principal, Career Counsellor, School Coordinator, Contact numbers, Email,
Website, Grades available, Board, School partnership date, Agreement/MoU, Edusphere BDM). All 15 are now
mandatory per the user's explicit directive, subject only to the Branch design question and the
Edusphere BDM role blocker noted above.

**User roles affected.** `school_coordinator`/`school_principal` (profile visibility), `super_admin`/
`overseas_admin` (school onboarding), indirectly every role whose data is scoped by `school_id`.

**Frontend impact.** School profile view/edit screen (partner onboarding flow) needs new fields once
confirmed; any UI currently displaying a school only by `name` may need a School ID display.

**Backend impact.** New model fields (and possibly a new `SchoolBranch` entity, pending the Branch
scope decision); onboarding endpoint updates.

**Database impact.** Migration adding `school_code` (unique, indexed, mirroring `student_code`'s
pattern) at minimum; a `SchoolBranch` table only if the multi-campus interpretation is confirmed —
**do not build both interpretations speculatively; the scope decision must come first.**

**API impact.** Additive fields on school-profile read/write endpoints; new endpoints only if
`SchoolBranch` is confirmed as a separate entity.

**Integration impact.** None identified for School ID; none identified for a free-text Branch field. A
`SchoolBranch` entity would ripple into every school-scoped endpoint's authorization query.

**Authentication impact.** None.

**Authorization impact.** Significant only under the multi-campus interpretation: if a Branch is a
separate scoping boundary, `school:coordinator:own_institution`-style checks throughout `schools.py`
would need to become branch-aware, not just school-aware — this is the main reason this item is rated
High risk despite looking like a simple field addition.

**Security impact.** Low for School ID; potentially Medium for Branch if the multi-campus
interpretation is chosen and any existing query forgets to add the branch-scoping clause (cross-branch
data leak within the same school).

**Performance impact.** Negligible for School ID; negligible for a free-text Branch; a `SchoolBranch`
entity adds one more join to already-scoped queries if chosen.

**Reusable existing modules.** `DEC-DATA-003`'s School/Student ID generation pattern (8-char
alphanumeric hex) can be directly reused for a School ID; existing per-institution RBAC scoping pattern
if Branch stays a simple field rather than a new entity.

**Dependencies.** None hard, but the Branch scope decision affects how ENH-005 (school transfer) and
ENH-009 itself should be sequenced relative to each other — recommend resolving Branch's scope
*before* ENH-005 starts, since "transfer between schools" behaves differently if a branch move within
the same legal school entity is also a kind of transfer.

**Acceptance criteria.**
- A Decision ID resolves, field-by-field, which of the ~17 profile fields are in scope for this
  release vs. deferred.
- School ID is generated, unique, and displayed everywhere a school is currently identified only by
  name.
- Branch's scope (field vs. entity) is explicitly decided and documented before any migration ships.

**Positive scenarios.** A new school partner is onboarded and receives a business-facing School ID
immediately, displayed on their dashboard.

**Negative scenarios.** An attempt to onboard a school with a duplicate School ID is rejected.

**Edge cases.** A school with genuinely multiple physical campuses under one partnership/MoU — this is
exactly the case the Branch-scope decision must resolve; do not silently assume it away.

**Regression risks.** Every existing school-scoped query and every school-identifying UI string.

**Complexity:** Large. **Risk:** High.

**Addendum, 2026-09-22 (`DEC-SCOPE-025`) — Branch design decision resolved, implementation in
progress.** The Branch design question above is resolved: `DEC-SCOPE-025`
(`PRODUCT_DECISION_REGISTER.md`) confirms Branch as a free-text field on `School`, not a separate
`SchoolBranch` entity — the user's explicit, in-session choice, made before any migration shipped,
so `RBAC_MATRIX.md §2.12`'s one-`School`-row-per-tenant assumption is preserved unchanged. The same
decision also confirms all 24 `EVID-014` fields in scope (per Revision 4 above), the admin-only
access model, and the introduction of real `SchoolCreate`/`SchoolUpdate`/`SchoolOut` Pydantic
schemas. Full design: `docs/superpowers/specs/2026-09-22-enh-009-school-profile-design.md`.
Implementation plan and status: `docs/superpowers/plans/2026-09-22-enh-009-school-profile-field-coverage.md`
(13 tasks, each independently TDD'd and reviewed, plus a whole-branch review and one fix wave — all
complete on branch `feature/enh-009-school-profile-field-coverage`). **Not yet complete:** real
browser validation of the finished feature and an independent Codex review disposition are still
outstanding before this item can be marked `COMPLETE` (see `docs/quality/RTM.md`'s ENH-009 addendum
for current status).

---

## ENH-010 — Account Activation / Deactivation (School Master Capability)

**Title.** Let a School Master/Coordinator activate or deactivate accounts under their institution.

**Business requirement.** `School CRM.md`, Part B §2 (`docs/sources/School CRM.md:1361`): School
Master capabilities explicitly include *"Activate/deactivate users."*

**Existing behavior.** Not confirmed as a coordinator-facing capability. `UserRoleAssignment.is_active`
exists and is checked by `_assignment_is_usable()` (per the earlier implementation survey), but that
survey found it gates permission grants at the assignment level — whether a `school_coordinator` has
any endpoint to toggle it for their own institution's users was not confirmed either way; this item is
an audit-then-build, not a presumed gap.

**Resolution, 2026-09-22 (SUPERSEDES the "not confirmed" reading above):** audit found the
capability already shipped under the `SCH-003` addendum (`apps/api/app/api/schools.py`
`update_team_account`, `PATCH /api/v1/school/team/accounts/{user_id}`), predating this backlog
entry. All four acceptance criteria verified — 9/9 automated tests
(`apps/api/tests/test_sch_team_account_activation.py`, including two new mutation-checked
characterization tests for AC2 and mass-assignment immunity) plus a live browser QA pass. A
defensive per-row re-entrancy guard was added to `SchoolTeamPanel.tsx` after a rapid-click QA
observation (`ENH010-QA-01`); the duplicate `PATCH` requests it guards against are idempotent
server-side (same `active` value each time), so the exposure was duplicate `AuditLog` rows, not a
state flip — the guard is real defense-in-depth, matching `ChangePasswordForm`'s pattern, and
becomes load-bearing if this button is ever switched from `disabled` to `aria-disabled`. Decision
`DEC-SCOPE-025` (drafted, `UNCONFIRMED`) records the
`School CRM.md` Part B §2 → `school_coordinator` mapping this relies on. See
`docs/superpowers/specs/2026-09-22-enh-010-account-activation-design.md`.

**Expected behavior.** A coordinator can deactivate a user (teacher/parent/student, scoped to their own
institution) such that the account can no longer authenticate or be granted permissions, and reactivate
it later, with the action audit-logged.

**User roles affected.** `school_coordinator` (actor), `school_teacher`/`school_parent`/`school_student`
(subject).

**Frontend impact.** Toggle/action in the roster management UI.

**Backend impact.** New endpoint(s) if missing; must enforce "own institution only" scoping.

**Database impact.** None expected if `UserRoleAssignment.is_active` already exists and just needs a
new authorized write path; none if confirmed already sufficient.

**API impact.** New `PATCH`/`POST` endpoint, e.g. `PATCH /schools/{school_id}/users/{id}/status`.

**Integration impact.** None.

**Authentication impact.** A deactivated user's existing session/tokens should be invalidated, not just
blocked from future logins — `NEEDS_CONFIRMATION` on exact mechanism (token blacklist vs. short-lived
tokens naturally expiring).

**Authorization impact.** Must be scoped to the coordinator's own institution; must not allow
deactivating a School Master/Principal account via this coordinator-level action.

**Security impact.** Medium-positive (closes a real access-control gap — today, per this audit, there
may be no way to revoke a compromised or offboarded school-side account short of a database change).

**Performance impact.** Negligible.

**Reusable existing modules.** `UserRoleAssignment.is_active` flag and its existing check in
`_assignment_is_usable()`; existing `AuditLog` pattern.

**Dependencies.** None.

**Acceptance criteria.**
- Coordinator can deactivate/reactivate a user within their own institution.
- A deactivated user cannot authenticate.
- Action is audit-logged with actor, target, timestamp.
- Coordinator cannot deactivate a user outside their institution or above their own authority level.

**Positive scenarios.** Coordinator deactivates a teacher who has left the school; that teacher's next
login attempt fails.

**Negative scenarios.** Coordinator attempts to deactivate a School Master account — rejected.

**Edge cases.** Deactivating a `school_parent` who is linked to children at multiple schools
(interacts with ENH-008) — must not silently affect their standing at the other school.

**Regression risks.** Existing login/permission checks that read `is_active` must keep working.

**Complexity:** Small. **Risk:** Medium (authentication/session-invalidation correctness).

---

## ENH-011 — School-Domain Skills Tracker Generalization (Soft Skills, Digital/Web Skills)

**Title.** Extend the existing Test Prep/Language tracker pattern to Soft Skills and Digital/Web
Skills.

**Business requirement.** `School CRM.md §9` (Soft Skills: Communication, Presentation, Public
speaking, Leadership, Teamwork, Time management, Interview skills, Problem solving, Professional
etiquette) and `§10` (Web Designing / Digital Skills: Web Designing, Digital skills, Technology
workshops, Coding, Digital projects) — both structurally identical trackers to the already-built
`SCH-009` (student → course/batch → attendance → assessment → certification/completion).

**Existing behavior.** `SCH-009` (Test Prep/Language modules, delivered by `academic_team`) is built
for Foreign Language, IELTS/English, and SAT. No equivalent tracker exists for Soft Skills or Digital/
Web Skills.

**Expected behavior.** Generalize `SCH-009`'s tracker to a configurable module type (rather than one
hard-coded per subject area), so Soft Skills and Digital/Web Skills reuse the same student→batch→
attendance→assessment→completion shape instead of bespoke new tables.

**User roles affected.** `academic_team` (or whichever role delivers these — `NEEDS_CONFIRMATION`
whether Soft Skills/Digital Skills are academic_team-delivered like the existing SCH-009 modules, or a
distinct trainer role), `school_student`, `school_parent` (progress visibility).

**Frontend impact.** Reuse existing SCH-009 UI components with a new module-type parameter.

**Backend impact.** Generalize SCH-009's model/service layer to a module-type enum/table rather than
hard-coded tables per subject, if not already generalized that way — audit first.

**Database impact.** Likely a new `module_type` column/enum on the existing SCH-009 tracking table(s),
or two new rows in an existing module-type lookup table if one already exists — audit before assuming
a full new table is needed.

**API impact.** Existing SCH-009 endpoints extended with a module-type parameter, or new endpoints
mirroring the existing ones exactly.

**Integration impact.** None.

**Authentication impact.** None. **Authorization impact.** Same portfolio-scoping as SCH-009.

**Security impact.** Low. **Performance impact.** Negligible.

**Reusable existing modules.** `SCH-009`'s entire tracker pattern — this item is explicitly about
maximizing that reuse, not building new infrastructure.

**Dependencies.** None hard; benefits from ENH-001 (academic year) for consistent period tracking.

**Acceptance criteria.** A Soft Skills or Digital Skills batch can be created, students enrolled,
attendance/assessment tracked, and completion certified — using the same data shape as SCH-009.

**Positive scenarios.** A Soft Skills batch is created and tracked identically to an existing IELTS
batch. **Negative scenarios.** A student enrolled in a batch at a different school is rejected (same
scoping as SCH-009). **Edge cases.** A student enrolled in overlapping Soft Skills and Digital Skills
batches simultaneously — must not conflict.

**Regression risks.** Existing SCH-009 Foreign Language/IELTS/SAT trackers must not break if the
underlying model is generalized.

**Status (2026-09-22) — implemented, NOT complete.** The audit found this entry's premise does not hold:
SCH-009 has no batch, enrolment or per-session attendance (two per-student tables), and there is no "IELTS
batch" to copy. The user therefore decided a new school-scoped batch model, left SCH-009 unchanged, and chose
`career_counselor` as the delivering role (`DEC-SCOPE-026`; design
`docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md`; plan
`docs/superpowers/plans/2026-09-22-enh-011-skills-tracker.md`). Implemented test-first on branch
`feature/enh-011-skills-tracker-generalization`: migration `0037_school_skills`, `app/api/school_skills.py`, the
counselor Skills pages, the Parent Portal Skills section, timeline categories and entitlement usage.

**Verified (2026-09-22):**
- **Browser QA:** 14 findings, all fixed. QA-14 was fixed app-wide on the owner's instruction. Record: `docs/quality/ENH-011_BROWSER_QA_2026-09-22.md`.
- **Backend:** 1119 passed / 14 failed. The 14 are the provider-credential tests that also fail on `main`.
- **Web:** 43 files / 405 tests.
- **Static checks:** `tsc` clean; lint 0 errors; `ruff check` 33 and `mypy` 154, both equal to `main`.
- **Migration:** `0037` upgrade, downgrade and `alembic check` pass.
- **Full Playwright:** 249/259 on a reused database. On a fresh one, the remaining failures are a flaky pair and `stu-007`, which also fails on `main` (a spec/API mismatch).

**Confirmed by the owner, 2026-09-22:** D10–D12 (one session per batch per day; `certified` is terminal; the route skeletons), and the two QA observations kept as designed (`DEC-SCOPE-026` D13).

**Not done:**
- The independent Codex review was waived by the owner (2026-09-22).
- Branch pushed, no pull request opened yet; not merged.

**Complexity:** Medium. **Risk:** Low.

---

## ENH-012 — Digital Portfolio Module

**Title.** Build the Digital Portfolio as its own tracked entity per student.

**Business requirement.** `School CRM.md §14` (dedicated section — *"This should be a major feature"*),
referenced again in §8 (Career Passport: "Portfolio: 80% completed"), §23 (Parent Portal shows
"Portfolio"), and Part B §8 (Student Profile Central Record). Confirmed `OPEN` in
`docs/product/PRD_OPEN_ITEMS.md` item 77 alongside "Skills" — this is a known, already-flagged gap,
not newly discovered here, but it had no ENH item until now.

**Existing behavior (as of `ENH-012`'s build).** A per-student Digital Portfolio entity aggregating
profile, academic achievements, psychometric report, career guidance, languages, and 10 self-entry
sections (project, internship, competition, sport, leadership, volunteering, extracurricular, award,
certification, skill), plus a personal statement, now exists. `school_student` has no login at all
(`DEC-ROLE-004`) and is not, and was never going to be, the editor — there is no student-facing surface
anywhere in the codebase for this or any other School-domain feature.

**Expected/built behavior.** A per-student Digital Portfolio with a completion-percentage indicator
(computed over 16 sections). The 10 self-entry sections and the personal statement are entered **on the
student's behalf** by staff — `school_coordinator` (own institution), `school_teacher` (own institution,
assigned students only), and `academic_team` (own school portfolio) — not by the student. The
auto-populated sections (academic achievements, psychometric report, career guidance, languages)
pull from existing data rather than duplicating it, exactly as originally proposed. Read access is
extended to `school_principal`, `school_parent` (own child(ren) only), `career_counselor`, and
`psychometric_team`, alongside the three writer roles above (7 read-capable roles total, per the
design spec's AC-04).

**User roles affected.** `school_coordinator`/`school_teacher`/`academic_team` (writers, entering
content on the student's behalf); `school_principal`/`school_parent`/`career_counselor`/
`psychometric_team` (read-only viewers). **Not** `school_student` — no such login exists
(`DEC-ROLE-004`/`DEC-SCOPE-011`, §0).

**Frontend impact.** New portfolio screen with section-by-section editing and a completion meter.

**Backend impact.** New model and endpoints; aggregation logic pulling from existing psychometric/
career-guidance/results data rather than duplicating it.

**Database impact.** New `StudentPortfolio` (or per-section tables) with a migration; FK to
`SchoolStudent`.

**API impact.** New CRUD endpoints for self-entry sections; new read endpoint aggregating pulled-in
data.

**Integration impact.** None identified, unless file/document upload for portfolio artifacts requires
the existing document-upload infrastructure (`STU-011`'s pattern) — reuse it, don't build a second one.

**Authentication impact.** None.

**Authorization impact.** `school_coordinator`/`school_teacher` (assigned-only)/`academic_team` (own
school portfolio) write on the student's behalf; `school_principal`/`school_parent`/`career_counselor`/
`psychometric_team` get read access — per the existing per-role scoping already established elsewhere
in the School domain.

**Security impact.** Medium if file uploads are included (same considerations as any user-uploaded
content — validate file type/size, scan if the existing document-upload path already does).

**Performance impact.** Negligible.

**Reusable existing modules.** `STU-011`'s document-upload pattern; existing psychometric/career-
guidance/results read models for the auto-populated sections.

**Dependencies.** Benefits from ENH-001 (academic year, for dating portfolio entries) but not hard-
blocked by it.

**Acceptance criteria.** A writer (Coordinator/assigned Teacher/Academic Team) can build a student's
portfolio across the defined sections on their behalf; completion percentage updates as sections are
filled; Principal/Parent/Career Counselor/Psychometric Team can view (not edit) it.

**Positive scenarios.** Coordinator adds a project and an award for a student; completion percentage
increases; parent sees the update. **Negative scenarios.** A parent attempts to edit the portfolio
directly — rejected. **Edge cases.** Auto-populated sections (psychometric, career guidance)
conflicting with a manually entered one for the same area — pull-only, no manual override of
system-sourced sections.

**Regression risks.** None on existing modules if this stays purely additive.

**Complexity:** Large. **Risk:** Medium.

---

## ENH-013 — Student 360° Unified Profile / Career Passport View

**Title.** Build the single aggregated student view combining every existing and new data source.

**Business requirement.** `School CRM.md §8` ("Career Passport": Academic + Psychometric + Counselling
+ Skills + Activities + Achievements + Career Goal), `§35` ("Student 360° View"), and Part B `§8`
("Student Profile Central Record" — 15 tabs: Overview, Personal Details, Academic Records, Attendance,
Examination Results, Career Guidance, Psychometric Assessment, Skills, Foreign Languages, English
Testing, Activities, Certificates, Documents, Teacher Remarks, Parent Communication, Edusphere
Programs).

**Existing behavior.** The underlying data for several tabs already exists in separate modules
(academic results/`SCH-006`, psychometric/`SCH-005`, career guidance/`SCH-004`, language-testing/
`SCH-009`, timeline/`SCH-008`). Several others do not exist as discrete trackable entities yet: a
standalone Skills list, an Activities log, a Certificates registry, a Teacher Remarks log, and a Parent
Communication log. No single aggregated view exists today. **Correction, this turn:** re-checking §8's
"Student Career Passport" example against this list found two more gaps this item had missed: a
standalone **Achievements** entity (§8, §14, and §35 all name it as its own concept, distinct from
Certificates/Activities, but it wasn't in the original 5-entity list above), and a single distilled
**Career Goal** field (§8's example shows "Career Interest: Technology" as one summary value, distinct
from `ENH-026`'s more granular structured Recommended-careers/streams/skills list on the underlying
counselling record).

**Expected behavior.** A single "Student 360°" screen presenting all of the above as tabs, pulling
from each existing module's data and, for the modules that don't yet exist (Skills, Activities,
Certificates, Achievements, Teacher Remarks, Parent Communication — now six, corrected from five), a
minimal new tracked entity for each, plus a single `career_goal` field on the Overview tab summarizing
the student's current target (settable by the counsellor, distinct from the detailed recommendation
fields `ENH-026` adds to the underlying counselling record).

**User roles affected.** `school_coordinator`/`school_principal`/`academic_team` (full view, per
existing scoping), `school_teacher` (assigned-students-only), `school_parent`/`school_student` (own/
own-child only).

**Frontend impact.** New aggregated profile screen — the single most user-visible item in this batch.

**Backend impact.** New lightweight endpoints for Skills/Activities/Certificates/Achievements/Teacher-
Remarks/Parent-Communication (each a simple list-per-student entity); a `career_goal` field on
`SchoolStudent` or a dedicated overview record (design choice, not scope); an aggregation endpoint
pulling all tabs together for the 360° view.

**Database impact.** New small tables for the six missing sub-entities listed above, plus one
`career_goal` column; no changes to existing modules' tables.

**API impact.** New endpoints per missing sub-entity; one new aggregation endpoint.

**Integration impact.** None.

**Authentication impact.** None.

**Authorization impact.** Must respect the same per-role, per-relationship scoping already
established for every underlying module (assigned-students-only for teachers, own-child-only for
parents, etc.) — this view must not become a way to bypass those existing boundaries by aggregating
data the viewer couldn't otherwise see module-by-module.

**Security impact.** Medium — an aggregation endpoint is exactly the kind of surface where an
authorization check is easy to forget for one sub-source while getting the others right; needs
explicit per-tab scope testing, not just an overall "is this the right student" check.

**Performance impact.** An aggregation endpoint pulling from 8+ sources needs to avoid N+1 queries —
worth a specific performance test once implemented, not assumed fine.

**Reusable existing modules.** Every existing School-domain module's read layer; `STU-011`'s document-
upload pattern for Certificates.

**Dependencies.** Builds on ENH-011 (Skills as a generalized tracker) and ENH-012 (Portfolio) for
richer content, but can ship a first version with just the already-built modules' tabs plus the new
minimal sub-entities.

**Acceptance criteria.** Every listed tab renders correctly scoped data for the viewing role; a teacher
cannot see a tab's content for a student not assigned to them; a parent cannot see a tab for a child
not their own.

**Positive scenarios.** A coordinator opens a student's 360° view and sees all 15 tabs populated
correctly. **Negative scenarios.** A teacher attempts to open the 360° view for a student outside their
assigned grade/section — rejected. **Edge cases.** A student with no data yet in several tabs (new
enrolment) — tabs render as empty states, not errors.

**Regression risks.** None on underlying modules if this is a pure read-aggregation layer plus five
small additive entities.

**Complexity:** Large. **Risk:** Medium.

**Build note, 2026-09-23 (`DEC-SCOPE-028`).** Split on the owner's decision: **ENH-013a** (built on
`feature/enh-013-student-360-view`) is the 16-tab view plus `career_goal`, over existing data only; **ENH-013b** (not
started) is the Documents registry, Teacher Remarks log and Parent Communication log. Recorded rather than silently
resolved: the source says "15 tabs" but lists 16 names (all 16 kept); the acceptance criterion's "outside their assigned
grade/section" is implemented as the existing per-student teacher assignment (no section field exists; grade/section
assignment is a future decision); `school_student` has no login (`DEC-ROLE-004`), so the view's readers are the ENH-012
portfolio's 7 roles, each seeing only what it already reads elsewhere. Of the six "missing" entities above, Skills,
Activities, Certificates and Achievements are now served by ENH-011/ENH-012 data; Parent Communication stays "not tracked
yet" (no student-keyed log exists). Spec: `docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md`.

---

## ENH-014 — Multi-Channel Communication Centre (WhatsApp / SMS / Email / Push)

**Title.** Integrate WhatsApp, SMS, and push-notification channels alongside the existing email
channel for School-domain notifications.

**Business requirement.** `School CRM.md §32` ("Communication Centre" — explicitly names WhatsApp,
Email, SMS, Notifications as required integrations) and Part B `§11` (on result publish: notify
Student/Parent/Teacher via "CRM notification, Email, WhatsApp, SMS, Mobile app push notification").

**Existing behavior.** Email notifications exist (invite emails, password reset, likely result-publish
notifications per `SCH-006`/`SCH-007`). No WhatsApp, SMS, or push-notification integration was found in
this or prior research passes.

**Expected behavior.** Notifications triggered by existing events (result published, session scheduled,
assessment assigned, deadline approaching) are deliverable over WhatsApp and SMS in addition to email,
with push notifications if a mobile app exists (`NEEDS_CONFIRMATION` — no evidence of a mobile app
elsewhere in this codebase; push may be out of scope until one exists). **Explicitly in scope
(Revision 3):** the Platinum-exclusive `parent_help_desk` service (`TIER_SERVICES["platinum"]`,
`schools.py:665`) has no dedicated channel or tracking anywhere today and always reports `used: None`
via `/schools/entitlements` — this item is its owner, as a priority/dedicated support channel available
only to Platinum-tier schools' parents (enforced via **ENH-022** once it lands), distinct from the
general-purpose channels the rest of this item builds.

**User roles affected.** All School-domain roles as notification recipients.

**Frontend impact.** Notification-preference settings (which channel(s) a user wants) if not already
present for email.

**Backend impact.** New provider integrations; a channel-abstraction layer if the existing email-only
notification service isn't already structured to add channels easily — audit its current shape first.

**Database impact.** Possibly a `notification_preferences` field/table per user; delivery-log table per
channel (useful for the same kind of delivery-failure debugging the forgot-password fix already
required, per RTM's note on the notification-delivery bug).

**API impact.** Likely none public-facing beyond a preferences endpoint; this is mostly backend
integration work.

**Integration impact.** **This is the core of the item and the reason it's flagged High risk.** Per
CLAUDE.md's own Scope section: *"Do not assume... provider selections."* WhatsApp Business API and SMS
gateway are both paid, third-party, provider-specific integrations (e.g. Twilio, Gupshup, MSG91 —
none implied or selected here) requiring their own Decision ID, cost approval, and — since this
involves parent/student personal contact data going to a third party — a DPDP/privacy-compliance review
before any provider is chosen.

**Authentication impact.** None. **Authorization impact.** None beyond existing per-user opt-in scoping.

**Security impact.** Medium — phone numbers become a new class of PII flowing to an external provider;
needs the same care as the email provider already in place, plus provider-specific consent handling
(WhatsApp Business API in particular has strict opt-in/template-approval rules).

**Performance impact.** Negligible for the app itself; delivery latency depends entirely on the chosen
provider's SLA.

**Reusable existing modules.** Existing email-notification trigger points (result-publish, invite,
password-reset) — the *triggers* are reusable, the *channels* are net-new.

**Dependencies.** None hard, but should not start provider integration work before
`DEC-INTEGRATION-0xx` (provider selection) is confirmed — this is the textbook case of the "do not
generate provider-specific infrastructure until decisions are confirmed" rule in the project
constitution's Technology section.

**Acceptance criteria.** A Decision ID confirms provider(s) before any integration code is written; once
confirmed, existing trigger points (result publish, session scheduling, etc.) can deliver over the
newly added channel(s) in addition to email, per user preference.

**Positive scenarios.** A parent who opted into WhatsApp notifications receives a result-published
message on WhatsApp. **Negative scenarios.** A user who hasn't opted into SMS does not receive one.
**Edge cases.** A phone number format invalid for the chosen provider — must fail gracefully per
recipient, not block the whole notification batch (same "never block the batch" discipline already
established for `SCH-002-AC04`'s bulk upload).

**Regression risks.** Existing email notifications must keep working unchanged.

**Complexity:** Large. **Risk:** High (provider selection, cost, and privacy/consent — not primarily a
coding risk).

---

## ENH-015 — Reports & Downloads

**Title.** Student, school, and management-level report generation and export.

**Business requirement.** `School CRM.md §30` — Student Reports (Individual Career Report, Psychometric
Report, Counselling Report, Progress Report, Digital Portfolio), School Reports (Grade-wise, Career
Guidance, Psychometric Completion, Counselling, Skills, Foreign Language, IELTS/SAT, Global Education,
University Application, Scholarship, Internship), and an annual Management Report.

**Existing behavior.** Not confirmed as a distinct export/report-generation capability anywhere in the
research so far; the underlying data for most report types already exists in their respective built
modules.

**Expected behavior.** Downloadable (PDF/CSV, `NEEDS_CONFIRMATION` on format) reports generated from
existing module data, scoped per the requesting role (a coordinator can generate school-wide reports;
a parent only their own child's).

**User roles affected.** `school_coordinator`/`school_principal` (school reports), `academic_team`/
`career_counselor`/`psychometric_team` (their domain's reports), `school_parent`/`school_student` (own
report only).

**Frontend impact.** New "Reports" section with report-type selection and download action.

**Backend impact.** New report-generation endpoints/jobs pulling from existing modules' data — no new
source-of-truth data, purely a presentation/export layer.

**Database impact.** None expected for report content; possibly a lightweight generated-report-log
table for audit/re-download purposes.

**API impact.** New endpoints, likely one per report category, or one parameterized endpoint.

**Integration impact.** None, unless a PDF-generation library/service needs to be introduced — flag as
a small tooling decision, not a scope decision.

**Authentication impact.** None. **Authorization impact.** Same per-role scoping as the underlying data
each report pulls from — critical that a report export doesn't become a way to bypass existing
row-level scoping (same caution as ENH-013's aggregation view).

**Security impact.** Medium — exported files (especially PDFs containing student PII) need the same
scoping discipline as the live UI, and if emailed/downloaded need to be handled per whatever data-
retention/PII policy applies elsewhere in the system.

**Performance impact.** Report generation for a large school (1,000+ students) should be async/
background, not a synchronous request — reuse whatever background-job infrastructure already exists
(Celery is already in the stack per `docker-compose.yml`'s `worker`/`beat` services).

**Reusable existing modules.** Existing Celery worker (`docker-compose.yml:38-48`) for
background generation; every underlying module's existing read layer.

**Dependencies.** None hard; more valuable once ENH-013 (360° view) and ENH-012 (Portfolio) exist, since
several report types reference their data.

**Acceptance criteria.** A coordinator can generate and download a school-wide report scoped to their
institution; a parent can generate a report for their own child only.

**Positive scenarios.** Coordinator downloads a Grade-wise Student Report for their school.
**Negative scenarios.** A teacher attempts to generate a school-wide report beyond their assigned
students — rejected or auto-scoped down.

**Edge cases.** Report generation for a school with 1,000+ students — must not time out; should run as
a background job with a "ready for download" notification.

**Regression risks.** None on source modules; this is a pure read/export layer.

**Complexity:** Medium. **Risk:** Low.

---

## ENH-016 — School & Edusphere Analytics Dashboards

**Title.** Consolidated analytics dashboards: School Dashboard KPIs, Student Progress Scorecard, School
Performance Dashboard, School Service Utilization, and the Edusphere cross-school Admin dashboard.

**Business requirement.** `School CRM.md §1` (School Dashboard KPIs/charts), `§27` (Service
Utilization), `§28` (Student Progress Scorecard), `§29` (School Performance Dashboard, grade-wise
comparison), `§34` (Edusphere Admin cross-school dashboard), and Part B `§14` (School CRM Dashboard —
activity Completed/Pending table, at-risk/top-performer analytics). Consolidated into one item because
all five are read-model aggregations over data that mostly already exists in built modules, rather than
five separate new data sources.

**Existing behavior.** **Corrected, Revision 3:** the Service Utilization piece (§27) is *not* a full
gap as Revision 2 stated. `GET /schools/entitlements` (`schools.py:679-724`) already exists and returns,
per service, whether it's included at the school's cumulative tier and a real usage count wherever a
confirmed module produces one — 12 of 20 services (`psychometric_test`, `individual_counselling`,
`ielts_coaching`, `sat_coaching`, `foreign_language_classes`, `application_support`, `visa_support`,
`career_seminar`, `career_awareness_session`, `parent_orientation`, `monthly_campus_visits`,
`dedicated_counselor`) already have real counts today. It is scoped to the requesting school's own
coordinator/principal only — no cross-school view exists. No dedicated KPI/chart dashboard (§1, §28,
§29, §34, Part B §14) is confirmed for any of the other four views in this item.

**Expected behavior.** Narrowed accordingly: (1) an Edusphere-side cross-school rollup of the same
`/entitlements` data (§27's "Edusphere management should see... school-wise" angle — the one part of
Service Utilization that's genuinely missing); (2) role-scoped KPI/chart dashboards for §1/§28/§29/§34/
Part-B-§14 (school-level for coordinators/principals, cross-school for Edusphere admin roles,
per-student progress scorecards, grade-wise performance comparison). The remaining 8 services that
`/entitlements` correctly reports as `used: None` (`soft_skills`, `web_designing`,
`scholarship_assistance`, `digital_portfolio_creation`, `internships`, `loan_assistance`,
`alumni_network`, `parent_help_desk`) are **not** this item's job to fix — each is already owned by
ENH-011, ENH-012, ENH-017, ENH-020, or ENH-021, and will start reporting real usage once those land.
(Appendix A item 3's entitlement-model question, referenced here in Revision 2, is now resolved — see
the correction there.)

**User roles affected.** `school_coordinator`/`school_principal` (school-level), `super_admin`/
`overseas_admin`/`edusphere_school_manager` (cross-school).

**Frontend impact.** New dashboard screens with charts — coordinate with `frontend-design`/
`dataviz`-style guidance when built, not scoped here.

**Backend impact.** New aggregation endpoints/materialized views over existing modules' data.

**Database impact.** Possibly a materialized/summary table for performance at scale if live aggregation
proves too slow — `NEEDS_CONFIRMATION`, build the simple version first and measure.

**API impact.** New read-only aggregation endpoints, one or a few per dashboard.

**Integration impact.** None. **Authentication impact.** None.

**Authorization impact.** School-level dashboards scoped to own institution; cross-school dashboard
restricted to Edusphere-internal roles only — must not leak one school's aggregate data into another's
view even in summary form.

**Security impact.** Low-Medium (aggregate data is lower-sensitivity than row-level, but cross-school
comparison data could still be commercially sensitive between competing school partners — scope
strictly).

**Performance impact.** The main engineering risk here — cross-school aggregation over a growing
dataset needs an explicit performance plan (indexing, caching, or materialization), not just a live
`GROUP BY` that gets slower every semester.

**Reusable existing modules.** `GET /schools/entitlements` (`schools.py:679-724`) and its
`_cumulative_services()`/`TIER_SERVICES` logic — the cross-school rollup should reuse this endpoint's
per-service usage-counting logic across every school rather than reimplementing it, not just aggregate
its output; every other existing School-domain module's data as the aggregation source for the KPI
dashboards.

**Dependencies.** None hard; naturally follows once the underlying modules (ENH-011 through ENH-013,
and ENH-017/ENH-020/ENH-021 for the remaining untracked services) add more trackable data.

**Acceptance criteria.** Each dashboard renders correctly scoped aggregate data for its intended role;
cross-school dashboard is inaccessible to school-side roles.

**Positive scenarios.** A principal views their school's KPI dashboard and sees accurate counts.
**Negative scenarios.** A school coordinator attempts to access the cross-school Edusphere dashboard —
rejected. **Edge cases.** A brand-new school with near-zero data — dashboard renders zero/empty states,
not errors.

**Regression risks.** None on source modules.

**Complexity:** Medium. **Risk:** Low.

---

## ENH-017 — School-Visible Global Education Pipeline Dashboard

**Title.** Surface school-facing visibility into the bridged Overseas pipeline: Top 100 University
Tracking, University Shortlisting, Scholarship, Application status, and Visa status.

**Business requirement.** `School CRM.md §16` (University Shortlisting), `§17` (Top 100 University
Tracking dashboard), `§18` (Scholarship Management), `§19` (Application Support — explicitly:
*"School management should NOT necessarily see all sensitive application details... they can see
high-level status"*), `§20` (Visa Tracking).

**Existing behavior.** `SCH-010` (School→Overseas bridge, `DEC-SCOPE-018`) already links a
`SchoolStudent` to an Overseas-domain record via a nullable `school_student_id` FK, initiated only by
Overseas Admin/Counselor. Whether a school-facing dashboard actually surfaces shortlisting stage,
scholarship status, high-level application stage, or visa status for bridged students was not confirmed
by this research pass — the bridge (the data link) is built; the school-facing view over it is not
confirmed.

**Expected behavior.** A read-only, high-level-status-only dashboard (per §19's own explicit
restriction — never full application detail) for school roles, showing bridged students' progress
through: Global Education Interest → Profile Evaluation → University Shortlisted → Application Started/
Submitted → Offer → Scholarship → Visa → Admitted → **Alumni**, matching the `§17` funnel example and
`§36`'s own pipeline diagram, which explicitly ends at "ALUMNI." **Explicitly in scope (Revision 3):**
the Platinum-exclusive `alumni_network` service (`TIER_SERVICES["platinum"]`, `schools.py:664`) has no
tracking module anywhere today and always reports `used: None` via `/schools/entitlements` — this item
is its owner. An admitted, bridged student who has completed their journey should be trackable as an
alumnus, visible to Platinum-tier schools only (enforced via **ENH-022** once it lands).

**User roles affected.** `school_coordinator`/`school_principal` (view), `school_partnership_manager`
(view, per its "View school-level reports" capability from `School CRM.md` Part B §13, line 1816-1822).

**Frontend impact.** New funnel-style dashboard, reusing `§17`'s worked example shape.

**Backend impact.** New read endpoint aggregating bridged students' high-level Overseas-domain status —
**must deliberately exclude** application detail fields per §19's own restriction.

**Database impact.** None expected — reads existing Overseas-domain data through the existing
`SCH-010` bridge FK; no new tables.

**API impact.** New read-only endpoint(s), explicitly high-level-status-only in their response shape.

**Integration impact.** None beyond the existing `SCH-010` bridge.

**Authentication impact.** None.

**Authorization impact.** **Core of this item.** Must enforce the §19 boundary at the API layer (field-
level exclusion of sensitive application detail), not rely on the frontend to simply not display it —
a school role must never receive the detailed fields in the response payload at all.

**Security impact.** Medium — getting the field-level exclusion wrong would leak Overseas-domain
application detail (which may include financial/personal document status) to school-side roles who
were never meant to see it.

**Performance impact.** Negligible for a per-school bridged-student count.

**Reusable existing modules.** `SCH-010`'s bridge FK and its existing Overseas-Admin/Counselor-only
initiation scoping (for confirming which students are legitimately bridged and visible at all).

**Dependencies.** None hard; depends on `SCH-010` (already built).

**Acceptance criteria.** School role sees high-level stage only, for bridged students only, never
detailed application/document fields.

**Positive scenarios.** A coordinator sees their school's Grade 12 funnel (Interested → Shortlisted →
Applications → Offers → Admitted) matching §17's example shape. **Negative scenarios.** A coordinator's
API response for a bridged student never contains detailed application fields, even if requested
directly. **Edge cases.** A student not yet bridged to the Overseas domain — excluded from this
dashboard entirely, not shown with empty/null fields.

**Regression risks.** None on the Overseas domain or `SCH-010`'s existing bridge behavior.

**Complexity:** Medium. **Risk:** Medium (field-level authorization correctness).

---

## ENH-018 — School Feedback Capture

**Title.** Let a School Coordinator submit feedback after each Edusphere-delivered activity.

**Business requirement.** `School CRM.md §31` — after every Edusphere activity, track: Activity, Date,
Trainer/Counsellor, Student participation, School satisfaction, Feedback, Suggestions, Rating.

**Existing behavior.** Not confirmed as an existing capability.

**Expected behavior.** A coordinator can submit structured feedback (rating + free text) tied to a
specific delivered activity (career session, psychometric camp, workshop, etc.), visible to Edusphere
management.

**User roles affected.** `school_coordinator` (submitter), `super_admin`/`edusphere_school_manager`
(viewer).

**Frontend impact.** Feedback form attached to each activity record.

**Backend impact.** New endpoint + model.

**Database impact.** New small `ActivityFeedback` table, FK to whichever activity/session entity
already backs `SCH-004`'s Career Guidance sessions.

**API impact.** New `POST`/`GET` endpoints.

**Integration impact.** None. **Authentication impact.** None.

**Authorization impact.** Coordinator can only submit feedback for their own school's activities.

**Security impact.** Low. **Performance impact.** Negligible.

**Reusable existing modules.** `SCH-004`'s activity/session entity as the FK target.

**Dependencies.** None.

**Acceptance criteria.** Coordinator submits feedback tied to a specific activity; Edusphere management
can view it.

**Positive scenarios.** Coordinator rates a completed career seminar. **Negative scenarios.**
Coordinator attempts to submit feedback for another school's activity — rejected. **Edge cases.**
Duplicate feedback submission for the same activity — decide reject-vs-update
(`NEEDS_CONFIRMATION`, minor).

**Implementation note, 2026-09-23 (original text above kept as written).** Resolved in-session; see
`docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md` §3. Corrections to this entry: the FK
target is SCH-001's `SchoolActivity` (SCH-004 has no activity/session entity); the viewer is Overseas Admin + Super
Admin, because `edusphere_school_manager` has no RBAC grants (`RBAC_MATRIX.md:239`); feedback applies to typed
(Edusphere) activities only, after they have taken place; the principal reads their own school's feedback; a duplicate
is **rejected** (`409`), resolving the `NEEDS_CONFIRMATION` above. Status: **complete** (2026-09-23): implemented, browser-QA'd
with every QA finding fixed, merged with `main` and re-verified; the Codex review was waived by the owner. Evidence and
recorded exclusions: `docs/quality/RTM.md`, ENH-018 row. Feedback submission is not tier-gated (spec D10).

**Regression risks.** None.

**Complexity:** Small. **Risk:** Low.

---

## ENH-019 — School Event Calendar

**Title.** Consolidated calendar view of all scheduled School-domain activities.

**Business requirement.** `School CRM.md §24` — career seminars, psychometric camps, parent
orientations, counselling days, workshops, foreign language classes, IELTS/SAT classes, university
sessions, internship programs, monthly Edusphere campus visits.

**Existing behavior.** Individual activity types are scheduled within their own modules (`SCH-004`
sessions, `SCH-005` psychometric assignments, `SCH-009` batches); no consolidated calendar view
confirmed.

**Expected behavior.** A single calendar aggregating all scheduled activity types across modules,
filterable by type/grade/section.

**User roles affected.** `school_coordinator`/`school_principal` (view), `school_teacher`/
`school_parent`/`school_student` (relevant-to-them view).

**Frontend impact.** New calendar screen.

**Backend impact.** New aggregation endpoint pulling scheduled-date fields from each existing module —
no new source data.

**Database impact.** None expected — pure aggregation of existing date fields.

**API impact.** New read endpoint.

**Integration impact.** None (unless external calendar export — e.g. `.ics` — is wanted;
`NEEDS_CONFIRMATION`, not assumed).

**Authentication impact.** None. **Authorization impact.** Same per-role scoping as each underlying
module.

**Security impact.** Low. **Performance impact.** Negligible for a single school's calendar.

**Reusable existing modules.** Every existing module's scheduled-date fields.

**Dependencies.** None.

**Acceptance criteria.** A coordinator sees all their school's scheduled activities in one calendar
view, correctly typed and dated.

**Positive scenarios.** Coordinator sees this month's IELTS batch start date and a scheduled career
seminar together. **Negative scenarios.** N/A (read-only aggregation). **Edge cases.** Two activities
on the same day/time — both render, no collision handling needed beyond correct display.

**Regression risks.** None.

**Complexity:** Small. **Risk:** Low.

---

## ENH-020 — Financial Support / Loan Assistance Tracking

**Title.** Track students requiring education loan/financial assistance guidance.

**Business requirement.** `School CRM.md §21` — track Required → Counselling → Documents → Application
→ Approved → Completed for education loan, financial assistance, scholarship, funding guidance.

**Existing behavior.** Not confirmed. **Possible overlap with the Overseas domain** — if an equivalent
financial-assistance/loan tracking capability already exists there (e.g. under `VISA-*`/`OVS-*`
features), this item may be a school-side *view* of that existing capability rather than a wholly new
one — audit the Overseas domain first before building new tables; do not assume duplication is
required.

**Expected behavior.** Either (a) a school-facing view into an existing Overseas-domain financial-
assistance tracker, or (b) if none exists, a new tracker following the source's status pipeline.

**User roles affected.** `academic_team`/`career_counselor` (initiators, `NEEDS_CONFIRMATION` on exact
owning role), `school_student`/`school_parent` (subject/viewer).

**Frontend/Backend/Database/API impact.** Entirely contingent on the audit finding above —
`NEEDS_CONFIRMATION` before any of these can be scoped concretely.

**Integration impact.** Possibly a lending-partner integration if this extends beyond internal
guidance-tracking into actual loan applications — `NEEDS_CONFIRMATION`, likely out of scope for a first
version (guidance-tracking only).

**Authentication/Authorization impact.** Standard per-student/per-school scoping, pending role
confirmation.

**Security impact.** Medium — financial-need information is sensitive; scope access tightly.

**Performance impact.** Negligible.

**Reusable existing modules.** Whatever the Overseas domain already has for scholarship/financial
tracking, if the audit finds it (reuse, don't duplicate).

**Dependencies.** Audit of Overseas domain must happen before this item's design is finalized.

**Acceptance criteria.** Deferred pending audit outcome — cannot be written responsibly before knowing
whether this duplicates existing Overseas-domain functionality.

**Positive/Negative scenarios, edge cases.** Deferred pending audit outcome, same reason.

**Regression risks.** Building a duplicate tracker alongside an existing Overseas one would itself be a
regression risk (data fragmentation) — the primary reason this item leads with an audit requirement.

**Complexity:** Medium (pending audit). **Risk:** Medium.

---

## ENH-021 — Internship Management

**Title.** Track student internships: company, role, dates, mentor, attendance, completion, feedback,
skills acquired.

**Business requirement.** `School CRM.md §22` — Internship company, Role, Start/End date, Mentor,
Attendance, Completion, Certificate, Feedback, Skills acquired. Also referenced in `§1`'s dashboard KPI
("Internships: 40") and `§35`'s Student 360° example ("Internship: Not started").

**Existing behavior.** Not confirmed as an existing tracked entity anywhere in the codebase.

**Expected behavior.** A per-student internship record with the fields above, contributing to the
School Dashboard KPI count (`ENH-016`) and the Student 360° view (`ENH-013`).

**User roles affected.** `career_counselor`/`academic_team` (record-keeping, `NEEDS_CONFIRMATION` on
exact owning role), `school_student` (subject), `school_parent`/`school_teacher` (viewers).

**Frontend impact.** New internship record screen; contributes a tab to ENH-013's 360° view.

**Backend impact.** New endpoint + model.

**Database impact.** New `StudentInternship` table, FK to `SchoolStudent`.

**API impact.** New CRUD endpoints.

**Integration impact.** None identified (no employer/placement-portal integration implied by the
source text — this is internal record-keeping, not a matching/placement feature; do not conflate with
the unrelated `EMP-*` Employer domain).

**Authentication impact.** None. **Authorization impact.** Standard own-student/own-school scoping.

**Security impact.** Low. **Performance impact.** Negligible.

**Reusable existing modules.** `STU-011`'s document-upload pattern for internship certificates.

**Dependencies.** None hard; feeds ENH-013 and ENH-016.

**Acceptance criteria.** An internship record can be created, tracked through completion, and a
certificate attached; contributes correctly to dashboard counts.

**Positive scenarios.** A completed internship with a certificate uploads correctly and shows on the
student's profile. **Negative scenarios.** A teacher outside the student's assigned section attempts to
edit the record — rejected. **Edge cases.** An internship spanning an academic-year boundary
(interacts with ENH-001) — must not be silently reset by a promotion event (`ENH-004`).

**Regression risks.** None.

**Complexity:** Medium. **Risk:** Low.

---

## ENH-022 — Tier-Gated Feature Access Enforcement

**Title.** Actually enforce a school's partnership tier at the point of use, not just report it.

**Business requirement.** User's explicit instruction (this turn): *"consider the entitlement and there
access levels strictly."* `School CRM.md §26` and the brochure's "School Partnership Model" page both
define tier as what a school is *entitled to use*, not merely informed about.

**Existing behavior.** Verified by grepping every reference to `TIER_ORDER`, `TIER_SERVICES`, and
`_cumulative_services` across `apps/api/app/`: all three are used **only** inside
`GET /schools/entitlements` (`schools.py:679-724`), a read-only reporting endpoint. No
module-creation/action endpoint anywhere in the School domain — not test-prep batch creation, not
career-guidance session scheduling, not psychometric assignment, not the future modules this backlog
proposes — checks `school.tier` before allowing the action. A Bronze-tier school's coordinator can
create a Gold- or Platinum-exclusive service record today with nothing stopping them. Separately,
`School.tier_valid_until` (`models.py:943`) is stored but never read anywhere outside the two admin
endpoints that set it — an expired partnership still reports full entitlements via `/entitlements`.

**Expected behavior.** A reusable access check — e.g. a FastAPI dependency
`require_tier(service_key: str)`, mirroring the existing `Depends(get_current_user)` pattern already
used throughout `schools.py` — applied to every endpoint whose action corresponds to a key in
`TIER_SERVICES`. The check must (a) look up the acting school's `tier`, (b) confirm the requested
`service_key` is in that tier's cumulative set via the existing `_cumulative_services()` helper (reuse,
don't reimplement), and (c) confirm `tier_valid_until` (if set) has not passed. **Strictness is
explicitly `NEEDS_CONFIRMATION`:** no source states whether an out-of-tier or expired-partnership
request should hard-fail (`403`) or soft-warn-and-allow (e.g. flagged for a later billing
reconciliation) — this needs a Decision ID before GATE-09, not a default assumption either way.

**User roles affected.** Every role that can trigger a tier-gated action:
`school_coordinator`/`school_principal` (most creation actions), `academic_team`/`career_counselor`/
`psychometric_team` (their respective service deliveries).

**Frontend impact.** UI should ideally hide/disable out-of-tier actions proactively (better UX than a
server-side 403 after the fact), but the server-side check is the actual security boundary and must
exist independent of any frontend behavior.

**Backend impact.** New shared dependency/helper; applied across every existing and future tier-gated
endpoint — this is the largest-blast-radius item in this backlog by number of call sites touched, even
though each individual change is small.

**Database impact.** None — reads existing `School.tier`/`tier_valid_until`, no schema change.

**API impact.** No new endpoints; existing and future endpoints gain a new possible `403` (or a new
response field, if the strictness decision favors soft-warning) response.

**Integration impact.** None.

**Authentication impact.** None.

**Authorization impact.** This item *is* an authorization change — it is the concrete implementation of
"entitlement access levels," extending the existing per-institution/per-portfolio scoping already
enforced elsewhere (`RBAC_MATRIX.md §2.12`) with a new tier dimension.

**Security impact.** Medium-positive: closes a real gap where a lower-paying partner can access
higher-tier services at no cost today. Getting the cumulative-set check wrong (e.g. comparing tiers as
a flat set instead of via `_cumulative_services()`) would either over-block (Platinum schools losing
Bronze access) or under-block (the current bug persisting) — must reuse the existing helper exactly, not
reimplement the ordering logic.

**Performance impact.** Negligible — one extra indexed lookup per gated request.

**Reusable existing modules.** `TIER_ORDER`, `TIER_SERVICES`, and `_cumulative_services()`
(`schools.py:635-676`) — this item's entire job is to make these three already-correct pieces of logic
into an enforced gate instead of a read-only report, not to redesign them.

**Dependencies.** None upstream, but every future ENH item that adds a tier-gated service
(ENH-011, ENH-012, ENH-017's alumni tracking, ENH-014's parent help desk, ENH-020, ENH-021) should build
its creation endpoint against this item's `require_tier()` dependency from day one rather than adding
enforcement retroactively — sequence this item early. **ENH-023 depends on this item** (you need to know
what's gated before you can safely handle a downgrade revoking it).

**Acceptance criteria.**
- Every `TIER_SERVICES`-listed action is rejected (per the confirmed strictness policy) for a school
  whose cumulative tier doesn't include that service.
- An expired `tier_valid_until` is treated per the confirmed policy, not silently ignored.
- `/schools/entitlements`'s existing reporting behavior is unchanged — this item adds enforcement
  elsewhere, it does not modify that endpoint.

**Positive scenarios.** A Platinum-tier school's coordinator successfully creates an internship record
(Platinum-exclusive). **Negative scenarios.** A Bronze-tier school's coordinator attempts to create an
IELTS coaching batch (Gold-exclusive) — rejected per the confirmed strictness policy.

**Edge cases.** A school with `tier = None` (created but not yet assigned a partnership tier, which
`create_school` explicitly allows, `admin.py:911-915`) — `_cumulative_services()` already returns `[]`
for this case; every gated action must correctly reject for a tier-less school, not silently allow it.
A tier change happening mid-request (race condition between ENH-023's tier-change endpoint and a
concurrent gated action) — low priority, note but don't over-engineer for v1.

**Regression risks.** Every existing endpoint this check gets applied to — a mis-scoped `service_key`
mapping could incorrectly block an already-working, already-entitled action. Roll out per-endpoint with
its own test, not as one giant sweeping change.

**Complexity:** Medium. **Risk:** Medium (correctness-critical, but narrow and well-scoped once the
strictness Decision ID lands).

**Status (2026-09-23): IMPLEMENTED on `feature/enh-022-tier-gated-access-enforcement` — pending browser
validation and independent review; not merged.** Strictness resolved as `DEC-SCOPE-027` (hard `403`,
expired = no tier on the India date, all writes, every actor; D1–D12). Design:
`docs/superpowers/specs/2026-09-23-enh-022-tier-enforcement-design.md`; plan:
`docs/superpowers/plans/2026-09-23-enh-022-tier-enforcement.md`. Two corrections to this entry's own text:
a route-level `Depends(require_tier())` could not work (most gated routes learn the school only after
loading a student/record/batch, and several take the service key from the body), so the check is a helper
called inside each handler; and staff assignment is **not** gated here (D6, below).

**Before deploying:** every school with no tier or an expired one loses write access to every gated
service. List them first (read-only) and confirm with the business:
`SELECT id, name, tier, tier_valid_until FROM schools WHERE tier IS NULL OR tier_valid_until < (now() AT TIME ZONE 'Asia/Kolkata')::date;`

**Follow-ups raised by ENH-022 (not built here):**
- **Dedicated counselor (D6).** Platinum schools may have a dedicated counselor, other schools shared ones,
  but no data model says which assignment is "dedicated" — a `SchoolStaffAssignment` row is the same for
  both. Needs its own item: how "dedicated" is recorded, and what exclusivity it implies.
- **`/school/entitlements` and expiry (QA-022-02).** The report is unchanged by ENH-022's acceptance criteria,
  so after `tier_valid_until` passes it still shows e.g. "Platinum Partner — valid until 20 Sept 2026" with every
  service ticked while every write returns `403`. Decide whether the report should show the partnership as expired.
- **No admin UI for tier or expiry after creation (QA-022-07).** The create form has a tier but no valid-until
  date; the edit form has neither, so expiry — now enforced — can only be set through the API. Belongs with ENH-023.
- **No UI path to a visa case on a bridged application (QA-022-08).** The counselor Visa page excludes bridged
  applications (SCH-010's rule) and `/overseas/admin/visa` renders no form; ENH-022's bridged-visa gate was verified
  through the API only.
- **"Record score" with an empty score does nothing (QA-022-09).** No request and no feedback (academic team,
  test-preparation table). Pre-existing.
- **E2E failures found while verifying ENH-022, none caused by it** (each reproduced on an untouched `origin/main`
  stack or shown to pass on a fresh database): `sch-007-parent-portal` fails on `main` too — ENH-012's
  `PortfolioPanel` added a second "Career guidance" heading (`<h4>`) beside `SchoolChildOverview`'s `<h3>`, so the
  spec's `getByRole('heading')` is ambiguous; `ovs-006:15`, `pub-004:7` and the `@external` Razorpay case in
  `pay-001` fail on `main` too; `sch-team-management:80` passes on a fresh database but fails on a large one —
  `SchoolStudentsPanel`'s `#edit-teacher` uses an uncontrolled `defaultValue` that can apply before the async
  teacher list arrives, so an assigned (inactive) teacher shows as "Unassigned" (a real, timing-dependent bug);
  `ovs-007:8` is flaky on first load (search typed before hydration); `sch-004-005-006:190` and `:243` pass on a
  database where the spec has not run before but fail on every re-run — the spec searches for the fixed text
  "Search Alpha" / "Search Beta" while each run creates "E2E Search Alpha School <timestamp>", so earlier runs'
  schools also match (fresh DB: 1 match, pass; next run: 2 matches, fail). Make the search term unique per run.

---

## ENH-023 — Partnership Tier Change (Upgrade/Downgrade) Workflow

**Title.** Give tier changes real business-process handling instead of a bare field flip.

**Business requirement.** User's explicit instruction (this turn): *"hidden requirements as well like
change of gold to platinum etc."*

**Existing behavior.** `PATCH /overseas-admin/schools/{school_id}` (`admin.py:950-969`,
`update_school_tier`) lets an Overseas Admin or Super Admin set `school.tier` to any value and
optionally `tier_valid_until`, audit-logged (`school.tier_update`). It makes **no distinction between
upgrade and downgrade**, sends no notification to the school, and has no awareness of any in-flight
commitment tied to the school's *previous* tier.

**Expected behavior.** **Upgrade** (e.g. Gold → Platinum): safe under the already-correct cumulative
model — new entitlements simply become available the moment `tier` changes; this item's job here is
just to notify the school (reusing ENH-014's notification infrastructure once it exists, or the current
email channel today) and audit-log clearly which services newly became available. **Downgrade** (e.g.
Platinum → Gold): genuinely needs policy, not just code — what happens to an already-assigned dedicated
counselor (`SchoolStaffAssignment` rows created under `dedicated_counselor`), already-scheduled monthly
campus visits, a student mid-internship, an active visa-support case, or existing alumni-network access?
None of these should be silently and immediately cut off mid-commitment. `NEEDS_CONFIRMATION`/requires a
Decision ID: does an in-flight Platinum-tier commitment (a) complete regardless of the downgrade
("grandfather" existing engagements, block only *new* ones — the safer default), (b) get a defined
wind-down/grace period, or (c) end immediately? Do not default to any of the three without an explicit
decision.

**User roles affected.** `overseas_admin`/`super_admin` (actor), `school_coordinator`/`school_principal`
(notified), indirectly every role whose access ENH-022 gates by tier.

**Frontend impact.** Tier-change UI (if one doesn't already exist beyond raw API access) should
distinguish upgrade vs. downgrade and, for a downgrade, surface exactly what's about to become
unavailable before confirming — a downgrade should never be a silent, unreviewed action.

**Backend impact.** Extend `update_school_tier` to detect upgrade-vs-downgrade (compare old/new position
in `TIER_ORDER`), trigger the appropriate notification, and — once the Decision ID above lands — apply
the confirmed downgrade policy to in-flight records.

**Database impact.** A `SchoolTierChangeHistory`-style table (or reuse the existing `AuditLog` row this
endpoint already writes, extended with an old-tier field) for a proper change history, since the current
audit entry only records the new tier, not the transition.

**API impact.** `update_school_tier`'s response could additively include which services were
gained/lost by the change, for frontend confirmation-dialog use.

**Integration impact.** None beyond whatever notification channel is used.

**Authentication impact.** None.

**Authorization impact.** Unchanged — same Overseas Admin/Super Admin gate `update_school_tier` already
has.

**Security impact.** Low directly, but a wrong downgrade policy (e.g. immediately revoking a student's
in-progress visa support) would be a real service-continuity failure, not just a security one — treat
the Decision ID requirement as a hard blocker, not a nice-to-have.

**Performance impact.** Negligible.

**Reusable existing modules.** `update_school_tier`'s existing structure and audit-log pattern
(`admin.py:950-969`); `TIER_ORDER` for upgrade/downgrade direction detection; `SchoolStaffAssignment` as
the existing entity representing a "dedicated counselor" commitment that a downgrade policy must
account for.

**Dependencies.** **Hard dependency on ENH-022** — you need an enforcement layer that actually knows
what's tier-gated before you can correctly identify what a downgrade would revoke.

**Acceptance criteria.**
- Upgrade triggers a notification listing newly-available services; audit log records the transition
  (old tier → new tier), not just the new value.
- Downgrade behavior matches whatever the Decision ID confirms — grandfathering, wind-down, or immediate
  — and is never silent (school is always notified of exactly what changed).
- No in-flight commitment is destroyed by a downgrade without the confirmed policy explicitly saying so.

**Positive scenarios.** A Gold school upgrades to Platinum; coordinator receives a notification listing
the 7 newly-available Platinum services. **Negative scenarios.** A downgrade attempt with an
unconfirmed policy is blocked at the API layer until GATE-02 resolves it (fail closed on an unresolved
policy question, not open). **Edge cases.** A school downgraded and then re-upgraded within the same
billing cycle — history should show both transitions, not collapse them.

**Regression risks.** `update_school_tier`'s existing basic set/audit behavior must keep working for the
"no policy question raised" case (e.g. setting a tier for the first time on a previously tier-less
school, which is an upgrade-from-nothing, not a downgrade).

**Complexity:** Medium. **Risk:** High (the downgrade policy gap is a genuine business-continuity risk,
not just a coding risk, until a Decision ID resolves it).

---

## ENH-024 — Skill India Certification Tracking

**Title.** Track Skill India certification issuance per student.

**Business requirement.** Found only in the brochure (page 2, "Skill India Certification" — a
prominent, standalone callout), with **no corresponding section anywhere in the 1,928-line
`School CRM.md`**. Genuinely new content this revision's brochure read surfaced, not previously captured
in any prior pass of this backlog.

**Existing behavior.** None — no certification-tracking entity of any kind exists for this program.

**Expected behavior.** A per-student record of Skill India certification status/completion, surfaced on
the Digital Portfolio (ENH-012) and Student 360° view (ENH-013) as a certificate entry, consistent with
how other certifications (IELTS, language, internship) are expected to appear there.

**User roles affected.** `academic_team` (or whichever role delivers Skill India-aligned training —
`NEEDS_CONFIRMATION`, the brochure doesn't specify an owning internal role), `school_student` (subject),
`school_parent`/`school_teacher` (viewers).

**Frontend impact.** Small addition to the Portfolio/360° view's Certificates tab.

**Backend impact.** New minimal endpoint/model, following the same shape as other certification records
this backlog already proposes (e.g. ENH-021's internship certificate).

**Database impact.** New small table or, if a generic `StudentCertificate` entity already exists from
ENH-012/ENH-013's build, a new row type there instead of a bespoke table — build ENH-012/013 first and
reuse their shape rather than adding a fourth parallel certificate table.

**API impact.** New CRUD endpoints, or extension of whatever generic certificate endpoint ENH-012/013
produce.

**Integration impact.** None identified — `NEEDS_CONFIRMATION` whether "Skill India" implies integration
with an external government certification registry/API, or is purely an internal record of completion;
the brochure gives no detail either way.

**Authentication/Authorization impact.** Standard own-student/own-school scoping.

**Security impact.** Low. **Performance impact.** Negligible.

**Reusable existing modules.** Whatever certificate entity ENH-012/ENH-013 establish.

**Dependencies.** Should follow ENH-012/ENH-013 so it reuses their certificate shape instead of
duplicating one.

**Acceptance criteria.** A Skill India certification can be recorded per student and appears correctly
on their Portfolio/360° view.

**Positive scenarios.** A completed certification displays on the student's profile.
**Negative scenarios.** N/A beyond standard scoping (no role outside the student's own school can view
it). **Edge cases.** None beyond the standard certificate-record shape.

**Regression risks.** None.

**Complexity:** Small. **Risk:** Low.

---

## ENH-025 — Student Master: Missing Identity & Demographic Fields

**Title.** Cover the remaining `School CRM.md §3` Student Master fields that ENH-009's sibling audit
(this turn) found missing from `SchoolStudent`.

**Business requirement.** User's explicit instruction (this turn): *"check others like student etc."*
after confirming the School Profile field gap. `School CRM.md §3` (`docs/sources/School CRM.md:118-177`)
lists 26 Student Master fields. Same mandatory-scope directive as ENH-009 applies here.

**Existing behavior.** `SchoolStudent` (`apps/api/app/models.py:967-1002`) stores exactly: `id`,
`school_id`, `student_code`, `full_name`, `date_of_birth`, `grade_or_class`, `created_by_user_id`,
`assigned_teacher_user_id`, `pending_parent_email`. **Correction (2026-09-23, ENH-025 design):** ENH-001
has since added `academic_year_id` and `grade_level` (`models.py:1030-1031`); the Grade/Section split therefore
reduces to adding `section`. See `DEC-SCOPE-029`. Checked field-by-field against §3:

| Field | Status | Note |
|---|---|---|
| Student ID | ✅ Covered | `student_code` (`DEC-DATA-003`) |
| Student Name | ✅ Covered | `full_name` |
| Photo | ❌ Missing | |
| Date of Birth | ✅ Covered | `date_of_birth` |
| Gender | ❌ Missing | |
| Grade | ⚠️ Combined | `grade_or_class` stores grade+section together (e.g. "10-A") |
| Section | ⚠️ Combined | Same field as Grade — no independent column; **ENH-001** already plans to split this properly as part of its grade-level model |
| Roll Number | ❌ Missing | |
| Academic Year | ❌ Missing | Owned by **ENH-001**, not duplicated here |
| School | ✅ Covered | `school_id` FK |
| Parent Name | ⚠️ Relational, not a field | Via `SchoolParentLink` → `User.full_name` — reasonable, not a defect |
| Parent Contact | ⚠️ Relational, not a field | Via `SchoolParentLink` → `User.phone` (`models.py:26`, confirmed present) — reasonable |
| Parent Email | ⚠️ Relational, not a field | Via `SchoolParentLink` → `User.email`; `pending_parent_email` is a separate, temporary invite-only field, not a duplicate of this |
| Student Mobile | ❌ Missing | Distinct question from Student Email below — a plain contact number does not require a login and is not blocked by `DEC-ROLE-004` |
| Student Email | — Deliberately absent | `DEC-ROLE-004`: a school-affiliated student never gets a login/User row at all, so there is no identity to hold an email against — this is a confirmed decision, not an oversight; do not add without reopening that decision |
| City | ❌ Missing | |
| Academic performance | ⚠️ Relational, not a field | Via `SCH-006` result records — reasonable |
| Subjects | ❌ Missing | No enrolled-subjects list independent of individual result records |
| Career interests | ❌ Missing on this table | May be captured inside a `SCH-004` career-guidance record — not confirmed either way this turn, flagged rather than assumed |
| Global education interest | ❌ Missing | `SCH-010`'s bridge is binary (bridged or not), not an "interested" flag prior to bridging |
| Preferred countries | ❌ Missing | |
| Preferred courses | ❌ Missing | |
| Skills | ❌ Missing | Owned by **ENH-011**/**ENH-013**, not duplicated here |
| Extracurricular activities | ❌ Missing | Owned by **ENH-013** |
| Achievements | ❌ Missing | Owned by **ENH-013** |
| Certifications | ❌ Missing | Owned by **ENH-012**/**ENH-013**/**ENH-024** |

**Net:** of 26 fields, 4 are directly covered, 4 are relational-not-a-field (reasonable), 1
(Student Email) is deliberately absent per a real Decision ID, 5 are already owned by other ENH items
(Academic Year, Skills, Extracurricular, Achievements, Certifications — **not** duplicated here), and
**this item's actual, additive scope is 12 fields**: Photo, Gender, Roll Number, Student Mobile, City,
Subjects, Career interests, Global education interest, Preferred countries, Preferred courses, plus
splitting Grade/Section into two real columns (the last one coordinates with ENH-001, doesn't duplicate
it).

**Expected behavior.** Add the 12 fields above as new `SchoolStudent` columns (or, for Career
interests/Global education interest/Preferred countries/Preferred courses, confirm first whether they
belong on `SchoolStudent` directly or as part of a `SCH-004`-owned career-guidance record — a design
question, not a scope question, since scope is mandatory per the user's directive).

**User roles affected.** `school_coordinator` (data entry, incl. bulk upload — `bulk_upload_students`,
`schools.py:1145`), `school_teacher`/`school_principal` (read), `school_parent` (read, own child only),
`academic_team`/`career_counselor` (career/interest fields, pending the design question above).

**Frontend impact.** Roster entry/edit forms and the bulk-upload template/CSV headers
(`ROSTER_TEMPLATE_HEADERS`, referenced at `schools.py:745`) need the new fields; Student
360°/Portfolio views (ENH-013/012) should surface Photo once it exists.

**Backend impact.** Extend the student-create/edit endpoints and the bulk-upload parser.

**Database impact.** Migration adding the fields above to `SchoolStudent`; splitting `grade_or_class`
into `grade_level`/`section` needs a backfill migration (coordinate with **ENH-001**, don't run two
separate migrations against the same column split).

**API impact.** Additive fields on existing student read/write/bulk-upload endpoints.

**Integration impact.** Photo implies file/image upload — reuse `STU-011`'s existing document-upload
pattern rather than building a second one.

**Authentication impact.** None. **Authorization impact.** None beyond existing per-role student
scoping (`_load_readable_student`, `schools.py:750-764`).

**Security impact.** Low-Medium — Photo and demographic fields (Gender, City) are additional PII;
apply the same access scoping already enforced for the rest of the student record, not a looser one.

**Performance impact.** Negligible for plain columns; Photo storage should reuse existing file-storage
infrastructure (`uploads` volume, `docker-compose.yml:31,43`), not a new mechanism.

**Reusable existing modules.** `bulk_upload_students`'s existing CSV-parsing/idempotency pattern
(extend its header set, don't rebuild it); `STU-011`'s document-upload pattern for Photo.

**Dependencies.** Coordinates with **ENH-001** (Grade/Section split, Academic Year) — do not duplicate
its migration; explicitly excludes the 5 fields already owned by ENH-011/012/013/024 above.

**Acceptance criteria.**
- All 12 additive fields can be set via both single-student edit and bulk upload.
- `grade_or_class` is split into two real, independently queryable columns without losing any existing
  data (migration is additive + backfill, not destructive).
- Bulk-upload template/CSV headers are updated and documented.

**Positive scenarios.** A coordinator bulk-uploads a roster including Gender, City, and Roll Number for
every student; all fields save correctly. **Negative scenarios.** A roster row missing a now-required
field (if any of the 12 are made mandatory — `NEEDS_CONFIRMATION` on which, if any, are required vs.
optional) is rejected per the existing "never block the batch" bulk-upload discipline
(`SCH-002-AC04`) — that row fails, the rest of the batch proceeds. **Edge cases.** A student with no
photo uploaded yet — must render a sane empty state everywhere Photo is displayed, not an error.

**Regression risks.** The `grade_or_class` split is the highest-risk single change here — every
existing query, report, or UI string that parses that field as one combined value must be found and
updated; audit before migrating, don't discover callers after the fact.

**Complexity:** Medium. **Risk:** Medium (mostly straightforward additive fields; the Grade/Section
split is the one genuinely risky piece, shared with ENH-001).

---

## ENH-026 — Career Counselling Record: Structured Fields & Status Workflow

**Title.** Replace the Career Counselling record's flat notes blob with the structured fields and
status workflow `School CRM.md §7` actually specifies.

**Business requirement.** User's explicit instruction (this turn): apply the same field-by-field check
to other sections with an explicit field list. `School CRM.md §7` ("Individual Career Counselling,"
`docs/sources/School CRM.md:302-344`) specifies a 17-field Counselling Record plus an explicit status
lifecycle: **Not Started → Scheduled → Completed → Follow-up Required → Completed.**

**Existing behavior.** **Correction, this turn:** the §1.5 coverage audit (Revision 2) marked this
section "likely covered by `SCH-004`'s scope, no new item needed" without verifying the model directly.
That was wrong. `SchoolCareerRecord` (`models.py:1085-1094`) is a flat table: `school_student_id`
(Student), `career_counselor_user_id` (Counsellor), `record_type` (a coarse type tag — confirmed used
as `"counselling_note"` elsewhere, e.g. `schools.py:704`, so it does map to "Counselling type"), and a
single free-text `notes` field, plus `created_at` (≈ Date) from `TimestampMixin`. Every other field in
§7's list — Career interests, Academic strengths, Weak areas, Recommended careers, Recommended
courses, Recommended subjects/stream, Recommended skills, Global education interest, Parent
participation, Counsellor notes (distinct from the generic `notes`?), Next follow-up, and the entire
Status workflow — has no structured column. It may exist today only as unstructured prose inside
`notes`, which is not queryable, reportable, or usable to drive a follow-up reminder.

**Expected behavior.** Add structured columns for the fields above (grouped sensibly — e.g. a single
`recommendations` JSON field for the four "Recommended..." fields may be reasonable, or four separate
columns — `NEEDS_CONFIRMATION`/design choice, not a scope question since coverage is mandatory) and a
real `status` column with the exact five-state lifecycle the source specifies, plus a `next_follow_up_date`
field so follow-ups are queryable/schedulable (feeds **ENH-019**'s event calendar once that exists).

**User roles affected.** `career_counselor` (record owner), `school_student`/`school_parent` (read,
per existing scoping), `school_coordinator`/`school_principal` (aggregate visibility).

**Frontend impact.** Counselling-record entry form needs the new structured fields instead of a single
free-text box; any existing UI reading `notes` as the whole record needs updating.

**Backend impact.** Extend `SchoolCareerRecord`'s create/update endpoints with the new fields; a
migration to add them (existing `notes` field stays, for any genuinely free-text remarks that don't fit
a structured column — don't force everything into structured fields if some of it is genuinely
freeform).

**Database impact.** Migration adding ~10 new columns (or a mix of columns + one JSON field) to
`SchoolCareerRecord`; no backfill needed for new columns on existing rows (nullable/default).

**API impact.** Additive fields on the existing Career Counselling record endpoints.

**Integration impact.** None. **Authentication impact.** None.

**Authorization impact.** Unchanged — same portfolio/own-child/assigned scoping already enforced for
this table elsewhere.

**Security impact.** Low. **Performance impact.** Negligible.

**Reusable existing modules.** `SchoolCareerRecord`'s existing `record_type` discriminator pattern
(already correctly distinguishes counselling-note from other Career-domain record types — keep it,
extend the record it tags rather than replacing the pattern).

**Dependencies.** `next_follow_up_date` feeds **ENH-019** (School Event Calendar) once that exists —
soft dependency, not blocking.

**Acceptance criteria.**
- A counselling record can be created/updated with the full structured field set from §7, not just
  free text.
- `status` follows the exact five-state lifecycle from the source, in order, with no skipped-state
  ambiguity (`NEEDS_CONFIRMATION` on whether states can be skipped, e.g. Not Started → Completed
  directly, or must pass through Scheduled — the source lists them as a sequence but doesn't say
  explicitly).
- Existing `notes`-only records (created before this migration) remain readable, with new fields simply
  empty/null, not corrupted.

**Positive scenarios.** A counsellor records a session with structured recommendations and sets status
to "Completed"; a parent viewing their child's profile sees the structured recommendations, not a wall
of prose. **Negative scenarios.** An invalid status transition (`NEEDS_CONFIRMATION`'d policy) is
rejected. **Edge cases.** A record created under the old flat-notes shape, then edited under the new
structured shape — must not lose the original free-text content.

**Regression risks.** `SCH-004`'s existing counselling-record read paths (including the
`/schools/entitlements` usage-count query at `schools.py:704`, which filters on `record_type ==
"counselling_note"`) must keep working unchanged.

**Complexity:** Medium. **Risk:** Low.

---

## ENH-027 — Psychometric Record: Structured Result Fields

**Title.** Add the structured psychometric-result fields `School CRM.md §6` specifies but
`SchoolPsychometricRecord` doesn't store.

**Business requirement.** User's explicit instruction (this turn): same field-by-field check extended
to `§6` ("Psychometric Test Module," `docs/sources/School CRM.md:254-300`). Its "Individual Student"
subsection lists a 12-field record to "Store."

**Existing behavior.** **Correction, this turn:** the §1.5 coverage audit (Revision 2) marked this
section `✅ Built` outright. That was wrong — it checked that `SCH-005` exists as a feature, not that
its record captures the fields the source specifies. `SchoolPsychometricRecord`
(`models.py:1097-1105`) stores only: `school_student_id` (Student), `psychometric_team_user_id`,
`assessment_type` (✅ Assessment type), `report_url` (✅ Report, as a link), `status` (✅ Test status),
and `created_at` (≈ Test date). Missing entirely: **Strengths, Interest areas, Personality indicators,
Career recommendations, Recommended streams, Counsellor remarks, Parent discussion, Follow-up** — 8 of
12 source fields, all currently un-structured (at best buried inside whatever the `report_url` PDF
contains, which is not queryable, reportable, or usable to drive the Career Passport/360° view's
Psychometric tab with anything beyond a status badge).

**Expected behavior.** Add the 8 missing fields as structured columns (Strengths/Interest
areas/Personality indicators/Recommended streams as text or JSON list fields; Career recommendations
possibly shared shape with `ENH-026`'s recommendation fields — coordinate, don't duplicate the design;
Counsellor remarks as text; Parent discussion as a boolean/date/text — `NEEDS_CONFIRMATION` on exact
shape; Follow-up as a date, feeding `ENH-019`'s calendar same as `ENH-026`'s `next_follow_up_date`).

**User roles affected.** `psychometric_team` (record owner), `school_student`/`school_parent`/
`school_teacher` (read, per existing scoping), `career_counselor` (consumes Career recommendations as
an input to their own counselling record).

**Frontend impact.** Psychometric result entry form needs the new structured fields; the
Portfolio/360° view's Psychometric tab (`ENH-012`/`ENH-013`) should surface them once they exist, not
just the status badge it can show today.

**Backend impact.** Extend the psychometric-record create/update endpoints; migration to add the 8
fields (nullable/additive, no backfill needed for existing rows).

**Database impact.** ~8 new columns (or a mix of columns + one JSON field for the list-shaped ones) on
`SchoolPsychometricRecord`.

**API impact.** Additive fields on the existing psychometric endpoints.

**Integration impact.** None. **Authentication impact.** None.

**Authorization impact.** Unchanged — same portfolio scoping already enforced for this table.

**Security impact.** Low. **Performance impact.** Negligible.

**Reusable existing modules.** `ENH-026`'s recommendation-field design (coordinate shape for "Career
recommendations" so the Psychometric and Counselling records don't each invent their own incompatible
structure for what is conceptually the same kind of data feeding the same Career Passport/360° view).

**Dependencies.** Coordinate with `ENH-026` (shared recommendation-field shape) and `ENH-019` (Follow-up
date feeding the calendar). Feeds `ENH-013`'s Psychometric tab.

**Acceptance criteria.** A psychometric result can be recorded with all 12 source fields, not just the
4 that exist today; the Psychometric tab in the 360° view (once built) shows structured data, not just
a status badge.

**Positive scenarios.** A psychometric team member records a full assessment including Strengths and
Recommended streams; a parent viewing their child's profile sees these, not just "Completed."
**Negative scenarios.** N/A beyond standard scoping. **Edge cases.** A legacy record created before this
migration, with only the original 4 fields populated — must render sensibly with the new fields empty,
not as an error.

**Regression risks.** Existing `SCH-005` read paths and the `/schools/entitlements` usage count for
`psychometric_test` (`schools.py:702`) must keep working unchanged.

**Complexity:** Medium. **Risk:** Low.

---

## ENH-028 — Bulk Data-Entry: Academic Results, Psychometric Records, Test Prep/Language Records

**Title.** Generalize the existing bulk-upload pattern beyond student rosters to every other
per-student, per-batch data-entry surface in the School domain.

**Business requirement.** User's explicit instruction (this turn): *"check for the possibility of bulk
uploads for various pages like results, exams, psychometrics tests etc."* This maps directly onto real
operational need: an Academic Team member entering a whole class's exam marks, or a Psychometric Team
member recording a whole batch's assessment results, one row at a time is not how this actually gets
used in practice.

**Existing behavior.** Exactly one bulk pattern exists in the whole codebase: `POST
/school/students/bulk-upload` (`bulk_upload_students`, `schools.py:1144-1230`), backed by
`SchoolRosterUploadBatch`/`SchoolRosterUploadRow` (`models.py:1045-1057` and the row table beside it).
Its discipline: CSV file upload, a required `Idempotency-Key` header (a repeat with the same key replays
the original result instead of reprocessing), per-row validation where a failing row is recorded and
skipped without blocking the rest of the batch (`SCH-002-AC04`), and a batch/row audit trail
(`total_rows`/`accepted_count`/`rejected_count` on the batch, `row_number`/`status`/`error_message` per
row). Verified directly (not assumed) that **no equivalent exists** for `SchoolAcademicResult`
(`SCH-006`), `SchoolPsychometricRecord` (`SCH-005`), `SchoolCareerRecord` (`SCH-004`), or the Test
Prep/Language records (`SCH-009`) — grepping the entire file for `bulk` returns matches only in the
roster-upload context. **One related surface already handles a "many at once" shape correctly without
using the word "bulk":** `POST /activities/{activity_id}/attendance` (`mark_attendance`,
`schools.py:1091-1116`) already accepts a JSON list of `{student_id, present}` records in one call,
upserting each — this is fine as-is and is not part of this item's scope.

**Expected behavior.** Extract the roster-upload pattern's reusable shape (batch/row tracking entity
pair, idempotency-key discipline, never-block-the-batch validation) into a form the other three modules
can reuse, then add a bulk-entry endpoint for each: a CSV or JSON-list upload of exam marks for a whole
class/subject/term at once (Results); a CSV or JSON-list of assessment assignments/results for a whole
batch at once (Psychometric); a CSV or JSON-list of test-prep/language scores for a whole batch at once
(once `SCH-009`/`ENH-011` exist in their generalized form).

**User roles affected.** `academic_team` (Results), `psychometric_team` (Psychometric), whichever role
delivers Test Prep/Language per `ENH-011`.

**Frontend impact.** A bulk-entry screen per module (CSV upload or a spreadsheet-style multi-row form),
mirroring the existing roster-upload UI's template-download-first pattern.

**Backend impact.** New bulk endpoints per module, each reusing the same batch/row tracking shape as
`SchoolRosterUploadBatch`/`Row` rather than three independent one-off implementations.

**Database impact.** New batch/row tracking tables per module (or one generalized
`SchoolBulkUploadBatch`/`Row` pair with a `target_type` discriminator, reused across all three —
**preferred**, avoids three near-identical table pairs; design choice, not a scope question).

**API impact.** New `POST .../bulk-upload` endpoints for Results, Psychometric, and Test Prep/Language,
each requiring an `Idempotency-Key` header per the existing convention.

**Integration impact.** None.

**Authentication impact.** None.

**Authorization impact.** Each bulk endpoint must enforce the same per-portfolio scoping its existing
single-record endpoint already enforces (`SchoolStaffAssignment`-based for Results/Psychometric) — a
bulk path must never become a way to write records for a school outside the actor's own portfolio just
because validation happens in a loop instead of a single check.

**Security impact.** Medium — same class of risk as the existing roster upload (a malformed or
oversized file, or a row referencing a student outside the actor's scope) — reuse its existing
mitigations (per-row scope check, `SCH-002-AC04`'s discipline) rather than re-deriving them.

**Performance impact.** Batch size limits should be considered (`NEEDS_CONFIRMATION` on a max row
count per upload) so one upload can't process an unbounded number of rows synchronously — the existing
roster upload has no stated limit either; worth setting one for all of these together rather than
inconsistently per module.

**Reusable existing modules.** `SchoolRosterUploadBatch`/`SchoolRosterUploadRow`'s exact shape and the
`_batch_report()` helper (`schools.py:1130-1141`) — generalize, don't reimplement; `SCH-002-AC04`'s
never-block-the-batch discipline; the existing `Idempotency-Key` convention already used identically
elsewhere (`PAY-001`'s checkout replay, per the roster upload's own comment).

**Dependencies.** Test Prep/Language bulk entry depends on `ENH-011` existing in its generalized form
first.

**Acceptance criteria.** Each of the three modules gets a bulk-entry path with: idempotent replay on
repeated key, per-row validation that never blocks the batch, and a batch/row audit trail matching the
existing roster-upload shape.

**Positive scenarios.** An Academic Team member uploads a CSV of 40 students' Term 1 Mathematics marks
in one action; all 40 create as Draft results. **Negative scenarios.** A row referencing a student
outside the actor's portfolio is rejected for that row only, the rest of the batch proceeds.
**Edge cases.** Re-submitting the exact same file with the same `Idempotency-Key` after a client-side
timeout — replays the original result, does not create duplicate results.

**Regression risks.** The existing single-record create endpoints for each module must keep working
unchanged — bulk is additive, not a replacement.

**Complexity:** Medium. **Risk:** Medium.

---

## ENH-029 — Bulk School Partner Onboarding (Admin, Multiple Schools at Once)

**Title.** Let Overseas Admin/Super Admin onboard multiple school partners in one action instead of
one `POST` per school.

**Business requirement.** User's explicit instruction (this turn): *"Admin also may on-board multiple
schools at a time."*

**Existing behavior.** `POST /overseas-admin/schools` (`create_school`, `admin.py:900-939`) creates
exactly one `School` plus its seed Coordinator account per call. Verified directly: `admin.py` contains
zero references to `bulk` anywhere — no bulk variant exists.

**Expected behavior.** A bulk variant — CSV or JSON list, one row per school (name, city, state, tier,
tier_valid_until, coordinator name/email) — creating each school + seed coordinator pair, reusing
`create_school`'s existing per-row logic (email-conflict check, tier validation, audit logging) inside
a loop with the same never-block-the-batch discipline as `ENH-028`/the existing roster upload, rather
than a bespoke one-off implementation.

**User roles affected.** `overseas_admin`/`super_admin` (actor).

**Frontend impact.** A bulk-onboarding screen (CSV upload or multi-row form) in the Admin console,
mirroring the coordinator-facing roster-upload UI's template-download-first pattern.

**Backend impact.** New `POST /overseas-admin/schools/bulk-upload` reusing `create_school`'s validation
per row.

**Database impact.** A batch/row tracking table pair (or reuse `ENH-028`'s generalized
`SchoolBulkUploadBatch`/`Row` design with a `target_type` of "school_onboarding" — preferred, one
mechanism for every bulk surface in this backlog rather than a fourth bespoke one).

**API impact.** New endpoint, additive.

**Integration impact.** None. **Authentication impact.** None.

**Authorization impact.** Unchanged — same Overseas Admin/Super Admin gate `create_school` already has.

**Security impact.** Medium — this endpoint creates login-capable Coordinator accounts with a default
password (`"ChangeMe@12345"` today per `admin.py:920`) exactly like the single-school path already
does; a bulk path multiplies that exposure across many accounts at once — coordinate with **ENH-003**
(first-time provisioning security) so bulk-created coordinator accounts get the same secure
set-password-link treatment as any other admin-provisioned account, not the current default-password
pattern at greater scale.

**Performance impact.** Same batch-size-limit consideration as `ENH-028`.

**Reusable existing modules.** `create_school`'s existing per-row validation logic
(`admin.py:900-939`); `ENH-028`'s generalized batch/row tracking design, if built first.

**Dependencies.** Should coordinate with `ENH-003` (don't multiply the plaintext-default-password
pattern, if that audit confirms it's a real issue, across a bulk path before fixing it in the
single-school path).

**Acceptance criteria.** An Overseas Admin can onboard N schools in one upload; each row creates its
school + coordinator pair independently, with per-row failure isolated per the never-block-the-batch
discipline; a batch report shows accepted/rejected counts per row.

**Positive scenarios.** An Overseas Admin uploads a CSV of 10 new school partners; all 10 are created
with their seed coordinators. **Negative scenarios.** A row with a coordinator email that already
exists is rejected for that row only. **Edge cases.** Two rows in the same file using the same
coordinator email — the second should be rejected as a duplicate within the batch, not just against
pre-existing data.

**Regression risks.** The existing single-school `create_school` endpoint must keep working unchanged.

**Complexity:** Medium. **Risk:** Medium.

---

## ENH-030 — Daily/Period Attendance Tracking for School Students (New Entity)

**Title.** Add routine attendance tracking for School-domain students — a gap surfaced while checking
for bulk-upload opportunities, not itself a bulk-upload request, but the natural home for one.

**Business requirement.** Found while researching `ENH-028`/`ENH-029`, not from a single named source
line: `School CRM.md` repeatedly references "Attendance" as a routine, ongoing metric — Teacher
Dashboard ("Student Attendance," Part B §3), Parent Dashboard ("Attendance," §23), Student Dashboard
("Attendance," Part B §5), and the Student 360°/Profile Central Record's own "Attendance" tab (§35,
Part B §8) — consistently alongside Academic Performance and Examination Results as one of the small
set of always-shown metrics, not as an occasional activity-specific thing.

**Existing behavior.** Verified directly: the base codebase's `Attendance` model
(`models.py:144-152`) is scoped to the IT/Overseas training domain's `batches` table (`student_id` →
`User`, `batch_id` → `batches`) — not the School domain at all. `SchoolActivityAttendance`
(`models.py:1035-1042`) exists, but it records attendance at a specific *scheduled activity* (a career
seminar, a workshop) — a one-off event, not routine day-to-day or period-wise class attendance. There
is **no** School-domain entity for "was this student present in school/in this class today," despite
every dashboard and profile view that references School students expecting one.

**Expected behavior.** A `SchoolAttendanceRecord`-style entity: `school_student_id`, `session_date` (or
`period`, if period-level granularity is wanted — `NEEDS_CONFIRMATION`, design choice), `status`
(present/absent/late — mirror the base codebase's existing `Attendance.status` shape rather than
inventing a new one), `marked_by_user_id` (the `school_teacher`). **Built bulk-first from day one**,
per the lesson of this whole exercise: a teacher marks their entire assigned class's attendance for a
day in one action — mirror `mark_attendance`'s existing "list of `{student_id, present}` records in
one call" shape (`schools.py:1091-1116`), not a one-row-at-a-time endpoint that then needs a bulk
variant retrofitted later.

**User roles affected.** `school_teacher` (marks, assigned students only), `school_coordinator`/
`school_principal` (aggregate view), `school_parent`/`school_student` (own/own-child read).

**Frontend impact.** A "take attendance" screen for teachers (whole-class, one action), and an
attendance history view surfaced on the Student 360°/Profile view (`ENH-013`) and Parent/Student
dashboards.

**Backend impact.** New endpoint(s), following `mark_attendance`'s existing list-payload shape.

**Database impact.** New `SchoolAttendanceRecord` table with a `UniqueConstraint("school_student_id",
"session_date")` (mirroring the base `Attendance` table's own uniqueness pattern) — or per-period if
that granularity is confirmed.

**API impact.** New endpoint(s), e.g. `POST /schools/{school_id}/classes/{grade_or_class}/attendance`
accepting a list of records for the whole class at once.

**Integration impact.** None. **Authentication impact.** None.

**Authorization impact.** `school_teacher` restricted to their own assigned students (same pattern as
every other teacher-scoped action, `_load_readable_student`, `schools.py:750-764`).

**Security impact.** Low. **Performance impact.** Negligible for a single class-sized batch.

**Reusable existing modules.** `mark_attendance`'s existing list-of-records, upsert-per-row pattern
(`schools.py:1091-1116`) — copy this shape exactly, it already solves the "bulk from day one" problem
this item is deliberately built around; the base codebase's `Attendance`/`AttendanceCorrection` pair
as a precedent for whether a correction/appeal workflow is also wanted here (`NEEDS_CONFIRMATION`,
likely a later phase, not v1).

**Dependencies.** Feeds `ENH-013`'s Attendance tab and every dashboard item in `ENH-016` that
references attendance.

**Acceptance criteria.** A teacher can mark their whole assigned class's attendance for a given day in
one action; the record is visible on the relevant Parent/Student/360° views.

**Positive scenarios.** A teacher marks 40 students present/absent in one call; each student's own
dashboard reflects it immediately. **Negative scenarios.** A teacher attempts to mark attendance for a
student outside their assigned class — rejected. **Edge cases.** Attendance marked twice for the same
student on the same day — second call should update, not duplicate (enforced by the unique constraint).

**Regression risks.** None — this is a wholly new entity with no existing behavior to preserve.

**Complexity:** Medium. **Risk:** Low.

---

## 2. Dependency graph

**Must be sequential:**
- `ENH-001 → ENH-004` (promotion cannot be built without the academic-year/grade-level model existing
  first — hard schema dependency, not a scheduling preference).
- `ENH-009 (Branch scope decision) → ENH-005` (school transfer's semantics change materially if a
  "Branch" turns out to be a separate scoping entity rather than a text field — resolve Branch's scope
  before finalizing transfer's design).
- `ENH-011 → ENH-013` and `ENH-012 → ENH-013` (the 360° view's Skills/Portfolio tabs need those two
  items' entities to exist first, even though a first cut of ENH-013 can ship with only the
  already-built modules' tabs).
- ~~A Decision ID resolving Appendix A item 3...~~ — **no longer applicable (Revision 3):** that
  question is already resolved; see the correction to Appendix A item 3 and to ENH-016 above.
- `ENH-022 → ENH-023` (tier-change downgrade handling needs the enforcement layer to exist first so it
  knows what a downgrade would actually revoke — hard dependency, not a preference).
- `ENH-028 → (Test Prep/Language part)` depends on `ENH-011` landing first (can't bulk-upload into a
  module that doesn't exist in generalized form yet); its Results and Psychometric parts have no such
  dependency and can start immediately.
- `ENH-029` should design its batch/row tracking table *with* `ENH-028` (same mechanism, different
  target), not before it independently — soft-sequence together, not a hard blocker either direction.
- `ENH-001` and `ENH-025` both touch `SchoolStudent.grade_or_class` (one to add `academic_year_id`, the
  other to split it into `grade_level`/`section`) — must be designed and migrated together, not as two
  independent migrations against the same column.

**Recommended-but-not-hard sequential:**
`ENH-003 → ENH-007` (auditing per-role profile completeness is more meaningful once provisioning itself
is confirmed correct).

**Can run fully independently / in parallel:**
- `ENH-002` (Academic Team audit) — touches `rbac.py`/academic-results endpoints only, no overlap with
  any other item.
- `ENH-006` (change password) — fully isolated (`auth.py` + new frontend form), zero shared files with
  any School-domain item. Safe to build anytime, by anyone, first.
- `ENH-001` and `ENH-003` can run in parallel with each other (different files, different concerns).
- `ENH-010` (activate/deactivate), `ENH-014` (Communication Centre, once its Decision ID lands),
  `ENH-015` (Reports), `ENH-018` (Feedback), `ENH-019` (Event Calendar), `ENH-020` (Financial/Loan,
  pending its own audit), and `ENH-021` (Internship) are all read/write layers over already-distinct
  data with no file overlap with each other or with the ENH-001–ENH-008 set — the largest pool of
  genuinely parallelizable work in this backlog.
- `ENH-022` (tier enforcement) is self-contained new infrastructure (one new dependency/helper, reusing
  existing `TIER_SERVICES` logic) — no file overlap with anything except the endpoints it's later
  applied to, which is coordination, not a blocking dependency.
- `ENH-024` (Skill India) can start independently but is most efficient once ENH-012/ENH-013 exist to
  reuse their certificate shape.

**Touch common files/modules (coordinate, don't necessarily block):**
- `apps/api/app/api/schools.py` and `apps/api/app/models.py` (`SchoolStudent`, `SchoolParentLink`,
  `School`) are shared by **ENH-001, ENH-004, ENH-005, ENH-008, ENH-009, and ENH-025**. Six items on
  the same two files — recommend landing them one at a time against `main` rather than parallel
  long-lived branches, with **ENH-001 and ENH-025 landing together** per the hard dependency above.
- `admin.py:create_user()` and the invite/email primitives are shared by **ENH-002** (Academic Team
  provisioning, incidentally) and **ENH-003** (the item that actually changes that code) — sequence
  ENH-003 before relying on its output in ENH-002's audit conclusions.
- `apps/api/app/api/auth.py` is shared by **ENH-006** and, loosely, **ENH-003** (both touch
  password-related code, but in different functions) — low collision risk.
- **ENH-011, ENH-012, ENH-013, ENH-016** all read from the same growing set of School-domain modules —
  no write conflicts (each adds its own new tables), but coordinate on the shared aggregation-query
  patterns so four different endpoints don't each reinvent how to join `SchoolStudent` to its results/
  psychometric/career-guidance data.
- `SCH-010`'s existing bridge FK is read by both **ENH-017** (school-visible pipeline dashboard) and,
  indirectly, **ENH-013** (360° view's Global Education tab) — no conflict, just shared context.
- `admin.py:update_school_tier` and `schools.py`'s `TIER_SERVICES`/`_cumulative_services` are shared by
  **ENH-022** (adds the enforcement gate) and **ENH-023** (extends the tier-change endpoint) — land
  ENH-022 first per the hard dependency above, then ENH-023 builds directly on it in the same area of
  `admin.py`.
- **ENH-017**'s alumni tracking and **ENH-014**'s parent help desk both depend on **ENH-022** existing
  before their Platinum-only gating is meaningful — soft dependency, can be built in parallel with
  ENH-022 and wired to it last.
- **ENH-028** shares `schools.py`'s existing `SchoolRosterUploadBatch`/`Row` pattern (generalizing it)
  with the Results/Psychometric/Test-Prep endpoints it extends — coordinate with whoever owns
  ENH-002/ENH-011/ENH-027 so the bulk path and the single-record path stay consistent.
- **ENH-029** shares `admin.py`'s `create_school` with nothing else in this backlog — low collision
  risk, but should reuse ENH-028's generalized batch/row design rather than inventing a fourth one.
- **ENH-030** is a new, self-contained entity with no file overlap, but its endpoint shape should be
  copied from `mark_attendance` (`schools.py:1091-1116`) — read that function before designing this
  one's payload shape, don't redesign from scratch.

**Require migrations:** ENH-001, ENH-004, ENH-005 (as before); **ENH-008 no longer requires one** --
see the corrected Database impact note under ENH-008 below (design-time decision, not an oversight);
**ENH-009** (School ID column,
possibly a new `SchoolBranch` table), **ENH-011** (module-type column/table), **ENH-012** (new
portfolio tables), **ENH-013** (five small new sub-entity tables), **ENH-014** (notification-
preference/delivery-log tables), **ENH-018/ENH-019/ENH-020/ENH-021** (each a small new table),
**ENH-024** (new certificate row/table, or none if it reuses ENH-012/013's entity); **ENH-025** (12 new
`SchoolStudent` columns plus the `grade_or_class` split, migrated together with ENH-001); **ENH-026**
(~10 new `SchoolCareerRecord` columns/JSON field); **ENH-027** (~8 new `SchoolPsychometricRecord`
columns/JSON field, coordinate shape with ENH-026); **ENH-028** (batch/row tracking table(s), reusing
or generalizing `SchoolRosterUploadBatch`/`Row`'s shape); **ENH-029** (same batch/row tracking,
school-onboarding target); **ENH-030** (new `SchoolAttendanceRecord` table). **No migration:**
ENH-006, ENH-015 (pure export layer), **ENH-022** (reads existing `School.tier`/`tier_valid_until`
only). **Possibly none — audit first:** ENH-003, ENH-007, ENH-016, **ENH-023** (a proper
tier-change-history table is recommended but optional for a first version that just extends the
existing `AuditLog` entry). **ENH-002 now requires one small migration** (a nullable `teacher_remarks`
column on `SchoolAcademicResult`, confirmed this turn — no longer "audit first" for that part of the
item, only for the progress-view question).

**Recommended implementation order:**
1. **ENH-006** — zero dependencies, closes a real security/UX gap, smallest and lowest-risk; good
   first PR to establish the pattern for this backlog.
2. **ENH-003** — flagged High risk specifically because the audit might reveal a plaintext-password
   handling gap; resolve the audit question early regardless of the rest of the sequence.
3. **ENH-009** — resolve School ID + Branch scope early: several later items (ENH-005 especially)
   behave differently depending on the Branch decision, and School ID is low-effort to add once decided.
4. **ENH-022** — tier enforcement is foundational, self-contained infrastructure with no migration and
   no hard dependencies; land it early so every subsequent tier-gated item (ENH-011, ENH-012, ENH-014's
   parent help desk, ENH-017's alumni tracking, ENH-020, ENH-021) can build its creation endpoint against
   `require_tier()` from day one instead of retrofitting enforcement later.
5. **ENH-023** — immediately after ENH-022, since it hard-depends on it; this is also the item that
   most directly answers the user's "hidden requirement" callout, worth prioritizing for that reason
   alone once its downgrade-policy Decision ID is confirmed.
6. **ENH-001 together with ENH-025** — foundation for promotion, and the mandatory Student Master field
   completeness the user directly required; both touch `grade_or_class` and must land as one
   coordinated migration. Nothing in the promotion line can start before this and its Decision ID
   (`DEC-DATA-0xx`) is confirmed.
7. **ENH-002, ENH-010, ENH-018, ENH-019, ENH-021, ENH-026, ENH-027** — independent, low/medium-risk
   items that can fill parallel capacity at any point after step 1. Land ENH-026 and ENH-027 in the
   same window if possible, since they should agree on a shared recommendation-field shape.
8. **ENH-004** — only after ENH-001 is fully migrated.
9. **ENH-008** then **ENH-005** — both touch `schools.py`/`SchoolStudent`; land ENH-008 first (better-
   grounded, fewer open policy questions), then ENH-005 once its `NEEDS_CONFIRMATION` items (initiator
   role, in-flight-results policy, terminal-grade interaction, Branch interaction from ENH-009) are
   resolved.
10. **ENH-011 → ENH-012 → ENH-013 → ENH-024** — build the skills-tracker generalization and the
    portfolio before the 360° aggregation view that depends on both, then Skill India certification once
    it has a certificate entity to reuse.
11. **ENH-016 → ENH-017 → ENH-015** — analytics dashboards (now correctly scoped to the cross-school
    rollup, not rebuilding what `/schools/entitlements` already does), then the pipeline-specific
    dashboard (including its new Alumni Network ownership), then general reports/exports.
12. **ENH-014** and **ENH-020** — both gated on an external decision (provider selection; Overseas-
    domain duplication audit, respectively) — start their audits/decisions early even though the build
    itself lands last, so the decision isn't the last thing blocking an otherwise-ready team.
13. **ENH-030** — build early-ish alongside step 7's independent pool; it has no dependencies and its
    "bulk-first" design should inform ENH-028's shape (build the simpler, self-contained one first,
    then generalize its pattern outward).
14. **ENH-028** then **ENH-029** — generalize the bulk-entry mechanism against Results/Psychometric
    first (both already exist as single-record modules to extend), then apply the same mechanism to
    school onboarding. Sequence ENH-028's Test Prep/Language part after ENH-011.
15. **ENH-007** — last; it's most useful once provisioning (ENH-003), promotion (ENH-004), transfer
    (ENH-005), and multi-school parenting (ENH-008) have all settled their respective profile-relevant
    fields.

## 3. Decision IDs required before any item reaches GATE-09

| Item | Decision needed | Current status |
|---|---|---|
| ENH-001 | `DEC-DATA-0xx` — academic-year scope (global vs per-school), ownership | None exists |
| ENH-004 | Terminal-grade / "graduate" state behavior; held-back-a-year handling | None exists |
| ENH-005 | `DEC-SCOPE-0xx` — transfer-initiator role; in-flight Draft-result policy at transfer | None exists |
| ENH-008 | Whether parent-multi-school is even desired policy (evidence shows it's merely
  *not ruled out*, not affirmatively requested by any confirmed decision) | None exists |
| ENH-003 | None structurally required — this is a security-hardening audit of an already-decided
  provisioning path (`DEC-SCOPE-014`), not a new scope question | N/A |
| ENH-002, ENH-006, ENH-007 | None — these operate entirely within already-`CONFIRMED_CURRENT` scope | N/A |
| ENH-009 | Scope is now mandatory per the user's explicit directive (this turn) — no scope decision needed. Design decision on whether "Branch" is a field or a new scoping entity | **Resolved: `DEC-SCOPE-025`** (2026-09-22, Branch is a field) |
| ENH-025 | Scope is mandatory (same directive). Needs a *design* decision on whether Career interests/Global education interest/Preferred countries/Preferred courses live on `SchoolStudent` directly or inside a `SCH-004` career-guidance record | None exists |
| ENH-014 | `DEC-INTEGRATION-0xx` — WhatsApp/SMS provider selection, plus a DPDP/privacy-consent review | None exists |
| ENH-016 | Indirectly blocked on Appendix A item 3 (entitlement quota vs. `DEC-SCOPE-017`) before its Service Utilization view is meaningful | See Appendix A |
| ENH-020 | Audit-first: confirm whether this duplicates an existing Overseas-domain capability before any Decision ID is even drafted | None exists |
| ENH-022 | `DEC-SCOPE-027` — enforcement strictness (hard `403` vs. soft warning) for out-of-tier or expired-partnership access | **Resolved 2026-09-23:** hard `403`, expired = no tier (D1–D12, `PRODUCT_DECISION_REGISTER.md`) |
| ENH-023 | `DEC-SCOPE-0xx` — downgrade policy for in-flight Platinum-tier commitments (grandfather / wind-down / immediate) | None exists |
| ENH-010 | `DEC-SCOPE-025` — "School Master" (`School CRM.md` Part B §2) = `school_coordinator`; activate/deactivate scope mapping proposed, drafted 2026-09-22 | Drafted, `UNCONFIRMED` |
| ENH-011, ENH-012, ENH-013, ENH-015, ENH-017, ENH-018, ENH-019, ENH-021, ENH-024, ENH-026, ENH-027, ENH-028, ENH-029, ENH-030 | None structurally required — each operates within already-confirmed School-domain scope (`DEC-SCOPE-011/012/013/017`) as a completion/extension, not a new scope question. ENH-026/ENH-027 additionally need a *design* choice (shared shape for "Recommended..."/"Career recommendations" fields); ENH-028's batch-size limit and ENH-030's session-vs-period granularity are also design, not scope, questions | N/A |
| ENH-016 | None — corrected in Revision 3 to a narrower scope entirely within already-confirmed `DEC-SCOPE-017` | N/A |

All items also individually require whatever their own BRD/PRD/AC delta needs per `APPROVAL_GATES.md`
GATE-03–05 before GATE-09, even where no new Decision ID is needed, since none of this scope exists in
the currently-approved BRD/PRD/Feature Catalogue.

## Appendix A — Standing conflicts to resolve, not silently pick a side on

1. `DEC-ROLE-004` vs `DEC-SCOPE-011` on school/agent-student login existence (see §0). Affects: whether
   `school_student` is in scope for ENH-007, and secondarily how ENH-004/ENH-005 communicate a change
   to the student themselves.
2. `School CRM.md`'s own provenance is `NEEDS_CONFIRMATION` (unattributed/undated per
   `EVIDENCE_REGISTER.md`) even though large parts of it have been formalized into confirmed decisions.
   Items above that cite the raw blueprint text directly (not just a confirmed decision) inherit this
   caveat.
3. ~~Entitlement model conflict~~ — **CORRECTED, Revision 3 (was wrong in Revision 2).** Revision 2
   flagged `School CRM.md §26`'s illustrative Entitled/Used/Balance quota table as an unresolved
   conflict against `DEC-SCOPE-017`'s "unlimited, not quota-capped" decision, and said it needed a new
   Decision ID. That was a mistake, caught this turn by reading the brochure PDF and the actual
   entitlement code together. It is already resolved: `schools.py:679-686`'s own docstring states
   outright *"the user explicitly confirmed 'included = unlimited, count usage' -- no numeric
   entitlement ever existed in any source, School CRM.md's own table was illustrative only,"* and
   `TIER_SERVICES`/`_cumulative_services` (`schools.py:635-676`) already implement exactly the brochure's
   cumulative, non-quota model, with a code comment explicitly citing "the brochure's own image." No
   Decision ID is needed here — this item is closed. (What *is* still open, and genuinely new: whether
   tier inclusion is actually *enforced* anywhere it's checked for access rather than just reported — see
   **ENH-022**.)

## Appendix B — Deferred source material (not converted to ENH items this pass)

Each requires an explicit Decision ID resolving the relevant open item/conflict before it can re-enter
this backlog with full field-level detail. Listed at theme level only — intentionally not fleshed out
with acceptance criteria, complexity, or risk ratings, since doing so would imply a readiness these
have not earned per GATE-02.

| Source | Evidence ID | Blocker | Decision ID needed |
|---|---|---|---|
| Agent CRM Functionalities.md | EVID-015 | `DERIVED_BLUEPRINT`, no `EXPLICIT_APPROVAL` | none yet |
| BDM Functionalities.md | EVID-016 | Proposes a "BDM" role with zero supporting evidence; inside `PRD_OPEN_ITEMS.md` item-61 hard blocker | none yet |
| Management Functionalities.md | EVID-017 | "Partner" login with full P&L/capital visibility, zero evidentiary basis, highest-sensitivity `NEEDS_CONFIRMATION` | none yet |
| Recruiter Functionalities.md | EVID-018 | Duplicates already-shipped `placement_team`/`hr_team` scope — unclear if extension or duplicate | none yet |
| Telecaller Functionalities.md | EVID-019 | Proposes a "Telecaller" role with zero supporting evidence; inside item-61 blocker | none yet |
| University Partnership CRM.md | EVID-020 | Proposes "Partnership Manager" (distinct from confirmed `university_rep`) and a commission direction reversed vs. `DEC-SCOPE-005` | none yet — conflicts with `CONFLICT_MATRIX.md` C-10 |
