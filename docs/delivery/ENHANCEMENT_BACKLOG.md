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

**Revision 6 (2026-09-28):** the user brought one slice of `Agent CRM Functionalities.md` (`EVID-015`,
Appendix B) into scope as **AGN-001** — agent organisation as tenant, with Master accounts — and gave the
approval and answers recorded as `DEC-SCOPE-038` (D1–D13). Only that slice leaves Appendix B; Staff logins
and the rest of `EVID-015` stay parked. AGN-001 keeps the ID the user gave it rather than an `ENH-` number.

**Revision 7 (2026-09-30):** the owner brought Staff logins (`EVID-015` §2 Staff, §3) into scope as
**AGN-002**, decided as `DEC-SCOPE-040` (S1–S6). Staff assignment/ownership, staff performance and CRM
settings stay parked.

**Revision 8 (2026-10-01):** the owner brought the `EVID-015` §6 Master-vs-Staff permission matrix into scope as
**AGN-003**, decided as `DEC-SCOPE-044` (P1–P9): two per-staff toggles (Verify Documents, Reports), enforced on existing
routes, plus agent document verification. Assignment/ownership, staff performance and CRM settings stay parked.

**Revision 9 (2026-10-01):** the owner brought "View staff activity" (`EVID-015` §2 Staff) into scope as **AGN-021**, decided as
`DEC-SCOPE-046` (A1–A5; drafted as `045`, renumbered on merging `main` because `ENH-020` holds `045`): a Master reads a staff member's student-journey activity from the existing audit log. Staff performance
and CRM settings stay parked.

**Revision 10 (2026-10-01):** the owner's `AGN-005` statement repeats AGN-003's word for word. AGN-003 is COMPLETE, so the owner scoped
**AGN-005** to closing the one gap: AGN-004's `/crm/students` routes were missing from the §6 matrix (Edit, Delete and Assign Student
still read N/A). Tests and docs only, no new decision; the owner later had four browser-QA findings fixed on the same branch
(QA5-01/02/03/05, see §AGN-005).

**Revision 11 (2026-10-02):** the owner's `AGN-008` statement ("create, edit, view, change status, application ID, submission date and
deadlines; Staff sidebar filters (§2, §4, §5)") is decided as `DEC-SCOPE-050` (A1–A15; `048`/`049` were held by
the then-unmerged `AGN-006`/`AGN-007` branches; both reached `main` first and `050` stayed free). It lifts `DEC-SCOPE-042` D8: agency students with no login can now have applications.
See §AGN-008.

**Revision 12 (2026-10-02):** the owner's `AGN-016` statement ("Tasks & Follow-ups" §4; "Pending Actions" KPI §2) is decided as
`DEC-SCOPE-053` (T1–T8; drafted as `051`, renumbered on merging `main` @ `d371865`, where AGN-014 holds `051` and AGN-009 `052`). See §AGN-016.

**Revision 13 (2026-10-02):** backlog item ang-010 "Offer details (Step 6)" (`EVID-015` §5 Step 6) is decided as `DEC-SCOPE-056`
(O1–O7, owner in-session; `054` was the next free number on `main` @ `9adcbca`). See §AGN-010.
**Revision 14 (2026-10-02):** the owner's `AGN-017` statement ("Notifications" §4; "Monitor deadlines" §2) is decided as `DEC-SCOPE-058`
(N1–N11; drafted as `055` / Revision 13, renumbered on merging `main` @ `ff27fa4`, where bdm-001, AGN-010 and AGN-012 hold `055`–`057`).
See §AGN-017.

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
| ENH-014 | Multi-channel Communication Centre (WhatsApp/SMS/Email/push) — **slice 1 COMPLETE (accepted 2026-10-01): Twilio WhatsApp + SMS, opt-in, queued delivery; release step: Twilio sandbox run (RAID D-03); help desk, Student/Teacher recipients, push and delivery callbacks are follow-ups** (`DEC-NOT-001` 2026-09-30 extension) | Large | High | Yes (resolved for slice 1) | — |
| ENH-015 | Reports & downloads (student/school/management exports) — **slice 1 complete (verified 2026-09-30)**; other §30 report types are later slices (`DEC-SCOPE-037` provisional) | Medium | Low | No | — |
| ENH-016 | School & Edusphere analytics dashboards *(scope corrected, Rev. 3 — see below)* | Medium | Low | Possibly (TBD) | — |
| ENH-017 | School-visible global education pipeline dashboard *(now owns Alumni Network)* — **Complete (verified 2026-09-29)** (2026-09-29, `DEC-SCOPE-036`; Alumni Network not built, follow-up) | Medium | Medium | No | SCH-010 (bridge, already built) |
| ENH-018 | School feedback capture | Small | Low | Yes | — |
| ENH-019 | School event calendar | Small | Low | Yes | — |
| ENH-020 | Financial support / loan assistance tracking — **Complete (verified 2026-10-01, `DEC-SCOPE-045`): audit found no Overseas equivalent; new School tracker** | Medium | Medium | Yes | — |
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
| AGN-001 | Multi-tenant Agent CRM — agent organisation as tenant, Master accounts (Rev. 6) | Large | High | Yes | AGT-001–004, SEC-001, RPT-002, ADM-001 (all change) |
| AGN-003 | Agent staff permissions — §6 Master-vs-Staff matrix, per-staff Verify Documents / Reports toggles (Rev. 8) | Medium | High | Yes | AGN-002 (staff routes), AGT-002/OVS-005 (document verify), RPT-002 (agent reports) |
| ENH-031 | Searchable reference pickers — student/application references picked from role-scoped searchable dropdowns | Medium | Medium | No | AGN-001 (agency scope) |
| AGN-004 | Agent students — Master/Staff create, edit, view and (Master) archive students who never log in; staff assigned-only | Large | High | Yes | AGT-002, AGN-001, ENH-031 (scope change); AGN-002 (merge) |
| AGN-021 | Agent staff activity — a Master views a staff member's student-journey activity (Rev. 9) | Small | Medium | Yes | AGN-001, AGN-002, AGN-003, AGN-004 |
| AGN-005 | Close the §6 staff matrix gap for agency student records — tests and docs, plus four browser-QA fixes (Rev. 10) | Small | Low | No | AGN-003, AGN-004 |
| AGN-006 | Agent student counseling record — completed, career interest, course/country preference, budget, remarks (§5 Step 2) | Medium | Medium | Yes | AGN-004 (student detail), AGN-021 (activity) |
| AGN-007 | Agent student university shortlist and agency-private university database (Master full / Staff view) | Large | Medium | Yes | AGN-001, AGN-002, AGN-003, AGN-004, AGN-021 |
| AGN-008 | Agent applications — Master/Staff create, edit, view, change status, Application ID, submission date and deadlines for agent students; Staff sidebar filters (Rev. 11) | Large | High | Yes | AGN-004, AGN-003, AGN-021, AGT-002, OVS-002/003/004, ENH-031, RPT-002 |
| AGN-009 | Agent documents — upload, download, verify, reject (with a reason), request additional, history; §5 Step 4 types; Staff sidebar Pending/Uploaded/Additional (`DEC-SCOPE-052`) | Large | High | Yes | AGN-003, AGN-004, AGN-008, OVS-005, VISA-001 |
| AGN-016 | Agent tasks and follow-ups — Master/Staff create, edit, complete and cancel tasks on agency students (task follows the student); "Pending actions" KPI (Rev. 12) | Medium | Medium | Yes | AGN-004, AGN-008, AGN-021 |
| AGN-010 | Agent offer details — conditional/unconditional, offer date, deadline, conditions, offer letter on an agency application; agent "Offers" count (Rev. 13) | Medium | Medium | Yes | AGN-008, AGN-009, AGN-021 |
| AGN-017 | Agency notifications (in-app + email) on assignment, document request/rejection, status change, new task; daily deadline reminders and overdue digest; Notifications page + unread badge (Rev. 14) | Medium | Medium | Yes | AGN-004, AGN-008, AGN-009, AGN-013, AGN-016, ENH-014 |

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
| 1 | School Dashboard (KPIs, charts) | ✅ Built — pending validation | **ENH-016** (`DEC-SCOPE-034`): KPI board on Coordinator + Principal dashboards; portfolios/skills (ENH-016) and internships (ENH-021) tracked |
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
| 16 | University Shortlisting (school-visible) | ✅ Complete (verified 2026-09-29) | **ENH-017** (2026-09-29, `DEC-SCOPE-036`): `SCR-SCH-038` shows each bridged student's high-level stage and a "University shortlisted" funnel count |
| 17 | Top 100 University Tracking dashboard | ⚠️ Partial — funnel complete (2026-09-29); Top 100 not tracked | **ENH-017** delivers the §17-shaped funnel; the Top 100 stage renders as *not tracked* (universities carry no ranking) — follow-up, not tracked |
| 18 | Scholarship Management (school-visible) | ⚠️ Partial | **ENH-017** shows Scholarships as *not tracked* (`ScholarshipApplication` has no school-student link) — follow-up, not tracked |
| 19 | Application Support (status-only, school-visible) | ✅ Complete (verified 2026-09-29) | **ENH-017**: high-level stage only, application detail never selected or returned (§19 boundary enforced at the API, key-set and planted-value tests) |
| 20 | Visa Tracking (school-visible) | ✅ Complete (verified 2026-09-29) | **ENH-017**: Visa funnel stage (a `VisaCase` exists) and a per-student visa stage label; visa outcomes are a follow-up, not tracked |
| 21 | Financial Support / Loan Assistance | ✅ Complete (verified 2026-10-01) | **ENH-020** (`DEC-SCOPE-045`) |
| 22 | Internship Management | ❌ Gap | See **ENH-021** |
| 23 | Parent Portal | ✅ Built | `SCH-007`; "Skills"/"Portfolio" sub-items depend on ENH-012, ENH-011 |
| 24 | School Event Calendar | ❌ Gap | See **ENH-019** |
| 25 | Edusphere School Counsellor tracking | ⚠️ Partial | `career_counselor` role exists; dedicated conversion/admission tracking not confirmed — rolled into **ENH-016** |
| 26 | School Partnership Package Tracking (quota table) | ⚠️ **Conflict** | Source shows Entitled/Used/Balance quotas; `DEC-SCOPE-017` (confirmed) made entitlements **unlimited, not quota-capped**. See Appendix A item 3 — this is a decision conflict, not an implementation gap |
| 27 | School Service Utilization | ✅ Built — pending validation | **ENH-016**: school-wise rows on `/overseas/admin/school-analytics` (delivered/pending/not tracked/utilization, participation, upcoming activities) |
| 28 | Student Progress Scorecard | ✅ Built — pending validation | **ENH-016**: per-student card + school-wide grid (Coordinator/Principal, D9/D10); Internship row follows ENH-021's progress rule; Scholarship row untracked until ENH-017 |
| 29 | School Performance Dashboard | ✅ Built — pending validation | **ENH-016**: Grade 8→12 comparison on the Reports page; four metrics are labelled estimates (D5, `NEEDS_CONFIRMATION`) |
| 30 | Reports & Downloads | ❌ Gap | See **ENH-015** |
| 31 | School Feedback | ✅ Built | See **ENH-018** |
| 32 | Communication Centre (WhatsApp/SMS/Email/push) | ❌ Gap | See **ENH-014** |
| 33 | School Admin Login (role matrix) | ✅ Built | `DEC-SCOPE-011`, `rbac.py` |
| 34 | Edusphere Admin Side (cross-school dashboard) | ✅ Built — pending validation | **ENH-016**: Overseas + Super Admin only (D1); schools/students/services/outcomes; internships tracked (ENH-021); scholarships untracked |
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
| B14 | School CRM Dashboard (activity + academic performance) | ✅ Built — pending validation | **ENH-016**: Completed/Pending table, grade/subject/term averages, at-risk and top performers (published results only, D4 thresholds) |
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

**Status (2026-10-01): SLICE 1 COMPLETE — accepted by the user on 2026-10-01 on `feature/enh-014-notification-channels` (not yet merged). Release step still open: the Twilio sandbox run (RAID `D-03`), the only evidence missing for AC06 and the live-provider parts of AC08/AC12/AC16.** **Completion evidence (fresh, 2026-10-01, at `935456b`):** backend suite 1994 passed / 14 failed — exactly the 14 credential-dependent Razorpay/Zoho tests, untouched by ENH-014 — 0 skipped; frontend 1087/1087; typecheck and lint clean (0 problems in ENH-014 files); `next build` OK; Playwright 16/17 (all 5 ENH-014 tests pass; the failure is pre-existing `I-38`); browser verification 12 PASS / 0 FAIL / 4 NOT TESTABLE (AC06, AC08, AC12 need a live provider; AC09 is covered by its unit test and an earlier browser run); migration round trip with existing rows preserved (verified as `0046`; renamed `0050_notification_channels` and chained after `0049_agent_students_crm` on the 2026-10-01 merges with `main`). **Fixed after browser QA (2026-09-30/10-01):** QA14-01 distinct hint when a saved phone can't be used; QA14-02 a saved-on channel stays toggleable (focus kept); QA14-03 channel toggles locked while saving; QA14-04 the section heading sits below the page title; QAF-01 a Redis outage now costs at most ~1.5 s once per 30 s per API process (bounded publish wait + 30 s back-off; was 4–8 s per request, stalling other users); O-1 worker and beat log through the app's JSON formatter so delivery lines carry id/channel/status/attempt (spec §6.1, §6.5, §7 "QA fixes" notes). Pre-existing issues found by the QA and left for separate changes: `I-43` (header overflow, upgraded), `I-44` (profile phone accepts any text), `I-45` (activity notification time shown in UTC). Design: `docs/superpowers/specs/2026-09-30-enh-014-notification-channels-design.md` (incl. §12 plan-time refinements); decision: `DEC-NOT-001`, extension of 2026-09-30 (D1–D14). **What slice 1 delivers:** `notification_preferences` table and `notification_deliveries.context` plus a sweeper index (migration `0050_notification_channels`, spec §4); `GET/PUT /api/v1/account/notification-preferences` (spec §5); Twilio WhatsApp and SMS via Messages REST over `httpx`, opt-in only with a recorded timestamp, email and in-app always on (D4); every trigger that sent email now queues one row per channel and publishes to Celery only after the root commit (D10, spec §6); retries 60 s / 300 s / 1500 s, at most 4 attempts (D11); a 5-minute Celery beat sweeper (stale `queued`/`retrying` re-published, stale `sending` → `failed` "worker interrupted"); GDPR erasure deletes preferences and the export includes them; a Notifications section on `/account/profile` (spec §7). Acceptance criteria `ENH-014-AC01…AC16` (`FEATURE_ACCEPTANCE_CRITERIA.md`). **Smoke check (2026-09-30):** against the real worker with Twilio unconfigured, school activity creation queued an email delivery that moved `queued` → `not_configured` with `attempt_count` 1, and a second task in the same worker process also completed. **Corrections to this entry:** Email is no longer "always inline" (it is queued too); the provider is Twilio for both WhatsApp and SMS (D2); push is out of scope (D3, no mobile app exists); the DPDP/privacy review was approved by the user in-session (D9); the "parent help desk" is a later slice (D12). **Follow-ups (open):**
- Platinum `parent_help_desk` slice (D12) — still the owner of the unbuilt Platinum channel.
- Student and Teacher recipients for result publish (D6) — students have no login or contact fields (`DEC-ROLE-004`).
- Mobile push (D3) — blocked on a mobile app existing.
- Twilio delivery-receipt callbacks (`delivered`/`undelivered`) with signature verification — `sent` currently means Twilio accepted the message.
- Per-event templates and WhatsApp/SMS template management in `ADM-011` (D13); OTP phone verification (D14).
- Twilio sandbox run (D8) and production account/template approval before release; the outcome (not the number) belongs in the release evidence.
- Pre-existing issues found during ENH-014, **not caused or fixed by it** (RAID): `I-42` fresh api/CI image builds break because `sqlalchemy>=2.0,<3` resolves to 2.1.x without `greenlet` (worked around locally only); `I-43` the shared `PublicShell` header overflows by 32 px at 320 px width on `/account/profile`; `I-38` `sch-007-parent-portal` "unlinked child denied" fails on an ambiguous 'Career guidance' heading selector (h3 + h4) in files ENH-014 did not change.

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

**Status (2026-09-30): SLICE 1 COMPLETE (verified 2026-09-30 at `d38dff6`: backend 1890 passed, 15 failed (all outside ENH-015: 11 Razorpay + 3 Zoho need real credentials; 1 `test_enh_003` count check disturbed by concurrent Playwright runs on the shared test DB -- its file passes 96/96 alone); web unit 1066/1066; `tsc` and `eslint` 0 errors (changed files 0 warnings); `next build` exit 0; Playwright `enh-015-reports-downloads` passes (related `sch-reports`, `enh-016`, `enh-017` pass; `sch-007` fails identically on `main` -- pre-existing duplicate "Career guidance" heading); browser AC01-AC12 (AC06 fail-closed clause and AC09 not browser-observable, covered by API tests); axe-core WCAG 2.0/2.1 A+AA: 0 violations in ENH-015 elements (existing page violations in ENH-016/SCH-008 components recorded); no new ruff/format/mypy findings vs `main`; no migration; `alembic check` drift (`ix_schools_school_code`) is pre-existing on `main`). Codex review waived by the owner.** History: implemented 2026-09-29; Built on `feature/enh-015-student-school-reports` per `docs/superpowers/specs/2026-09-29-enh-015-reports-downloads-design.md` and `DEC-SCOPE-037` (provisional). Slice 1 delivers the two reports the acceptance criteria need: a **School Summary PDF** (coordinator/principal, own school: the §30 management figures and the §29 grade-wise table) and a **Student Progress Report PDF** (parent — linked children only; coordinator/principal — own institution: the SCH-007 overview). **Corrections to this entry:** PDF only via the existing `reportlab` (no tooling decision needed); generated synchronously in memory and never stored (aggregate-only school output is bounded, so no background job, no report-log table, no migration); a `school_student` role does not exist (DEC-ROLE-004), so "own report" for students is not deliverable; teachers are refused (403), not auto-scoped, until "Limited" is defined. **Still `NEEDS_CONFIRMATION`:** the other §30 report types (later slices), teacher and service-team reports, a per-academic-year Annual report, scholarship figures, non-Latin fonts, Client Question #20. Evidence in the `RTM.md` ENH-015 row and `docs/quality/ENH-015_BROWSER_QA_2026-09-29.md`.

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

**Status (2026-09-28): IMPLEMENTED — NOT YET COMPLETE.** Built on `feature/enh-016-dashboards-analytics` per
`docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md` and `DEC-SCOPE-034` (recorded in-session as 031,
renumbered on the merge with `main`, which already held 031–033). After that merge, internships (ENH-021) are tracked in the
scorecard and the cross-school outcomes, and guidance/counselling count only delivered sessions (ENH-026 C5). Browser
validation and the independent Codex review are still to come. §25 (Edusphere School Counsellor tracking) was not in the
approved spec and is **not** covered by this build. Follow-ups: confirm D4 thresholds and D5 estimates with the client; a
terminal visa status for the scorecard's Visa row; `edusphere_school_manager` scoping (item 75); remove the unreachable code
after `return` in `school_reports` (`schools.py`).

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
the Platinum-exclusive `alumni_network` service (`TIER_SERVICES["platinum"]`, `schools.py:972`) has no
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

**Delivered scope (2026-09-29).** Built present-only under `DEC-SCOPE-036` (D1–D10, `EXPLICIT_APPROVAL` in-session; design `docs/superpowers/specs/2026-09-29-enh-017-global-education-pipeline-design.md`): read-only `GET /school/global-education/pipeline` and the Coordinator/Principal "Global Education" page (`SCR-SCH-038`) — a cumulative per-student funnel (pathway, profile evaluation, shortlisted, offer, visa, admitted), a "not tracked" group and a paged per-student high-level stage list, with the §19 boundary enforced by column-level selects and an allowlisted response. No migration. Status: **COMPLETE (verified 2026-09-29 at `949aa2c`)** — fresh test, browser and accessibility evidence in `docs/quality/ENH-017_BROWSER_QA_2026-09-29.md`; independent whole-branch review done and its findings fixed; the Codex review was set aside by the owner; API/E2E evidence ran on the locally pinned SQLAlchemy image (RAID `I-42`); QA17-03/QA17-04 (shared patterns) left open by decision. Not yet merged to `main`. Not built and not tracked (follow-ups, each `NEEDS_CONFIRMATION`): scholarship-to-school-student link; university ranking / Top 100; **alumni definition, `alumni_network` usage and the Platinum read gate (the Alumni Network ownership above is not delivered)**; visa outcomes; started/submitted/deposit statuses; `school_partnership_manager` access (PRD item 75).

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

**Audit result and decision (2026-10-01).** No Overseas-domain equivalent exists (no loan/funding model or route; the
`finance/` package is empty; `ScholarshipApplication` is overseas-only with no school-student link and a single
`submitted` status). Built as option (b), a new School tracker — `DEC-SCOPE-045`. Spec:
`docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md` (acceptance criteria AC01–AC20); plan:
`docs/superpowers/plans/2026-10-01-enh-020-funding-support-tracking.md`. The backlog's `school_student` viewer does not exist
(no student login, DEC-ROLE-004) and `require_tier()` does not exist (`require_school_entitlement` is used).

**Status (2026-10-01): COMPLETE (verified 2026-10-01 at merge `0f8ed2e`, `main` @ `6360dc0` merged in)** on
`feature/enh-020-funding-tracker`. Fresh evidence after the merge (isolated Compose project `enh020`, images rebuilt from that HEAD):
backend full suite **2700 passed / 14 failed** — all 14 the provider-credential baseline (11 Razorpay `test_pay_001_stu_010`,
3 Zoho "not configured"), no ENH-020 test among them; merge-sensitive set (all ENH-020, ENH-028, AGN-003, SCH-011, ENH-016/017,
migration tests) **435/435**. Web: vitest **133 files / 1391 tests**; `tsc` exit 0; `eslint` 0 errors (31 baseline warnings);
`next build` exit 0 (88/88 static pages; the funding route is dynamic). `ruff check` clean on every ENH-020 file; `mypy` adds no
error (266 repo-wide, none on ENH-020 lines). Migration `0053_school_funding_records` (cut as `0051`, re-chained after ENH-028's
`0051` and AGN-003's `0052`): single head; empty-DB upgrade → downgrade → upgrade OK; upgrade SQL is CREATE TABLE + 3 indexes only,
downgrade drops only that table; `alembic check` shows only two drifts that pre-date this branch (`0035`, `0049`). Playwright:
`enh-020-funding-support` 6/6 plus `enh-026`, `sch-011`, `enh-015`, `enh-016`, `enh-017`, `sch-007`, `enh-028`, `agn-003` all pass
(24 passed); `enh-022` QA-022-05 and `enh-023` downgrade fail identically on a base-commit build and their files are unchanged on
`main` and this branch (pre-existing, not ENH-020). Browser verification (isolated Chromium, every role): **49/49 checks** —
AC01–AC14, AC16, AC17, AC20 and QA-01..06 by browser behaviour; AC18/AC19 by browser-triggered actions plus database and log
checks (7 denial rows for 7 refusals, 4 tier rows; 0 audit rows, notifications or log lines with case contents); AC15 is not
browser-testable (database at `0053`). No skipped/focused tests, no debug code, no secrets (only the shared test fixture password)
in the diff. Independent Codex review waived by the user ("ignore codex review"); a fresh whole-branch review ran instead (2
Important accessibility findings fixed with tests). **Still `NEEDS_CONFIRMATION` (not blocking):** a case left open at a previous
school stays open after a transfer (follows from D7/D12); QA-07 (refused page reads audited) and QA-08 (counsellor notes visible
to parents) — product calls. Deferred minors: `expected_status: null` gives a 409; tier check runs before the final-case check;
`notes` accepts non-text JSON and bidi overrides; the card's "Updated by" falls back to the creator.

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

**Status (2026-09-28) — COMPLETE (verified; evidence in the `RTM.md` ENH-021 row, *Final verification*).** Designed with `ENH-026` in `docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md` (`DEC-SCOPE-032`); implemented on branch `feature/enh-021-026-internship-counselling-record`. **Correction to this entry:** internships already existed as ENH-012's portfolio `internship` section, so there is no `StudentInternship` table — the section was extended (migration `0043_portfolio_internship`); writers are the existing portfolio write roles; creating an internship or setting its tracking fields needs Platinum `internships`, while basic edits/deletes of existing entries keep Gold; the certificate is a PDF/JPEG/PNG ≤ 5 MB with audited downloads. The academic-year edge case needs nothing: promotion and transfer never touch portfolio entries. Browser validation done; the Codex review was waived by the owner; the full E2E regression runs on the regular cadence. FV-04 (owner decision) gave the shared ENH-012 portfolio entry form keyboard focus handling in every section. **Owner decisions from browser QA (2026-09-28):** QA-08 — a school without Platinum `internships` is told up front ("Internship tracking is part of the Platinum partnership"; no Add internship, tracking fields or certificate upload; basic edits/deletes of existing entries stay), via the portfolio payload's `can_track_internships`; known limitation: a school *downgraded* from Platinum may still finish tracking pre-downgrade entries server-side (ENH-023 grandfathering) but the page no longer offers those fields. QA-14 — the Internships KPI and status chart stay API-only here; rendering them is **follow-up for `ENH-016`** (School & Edusphere Analytics Dashboards).

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

**Status.** `COMPLETE on feature/enh-023-tier-change-workflow (DEC-SCOPE-030)`, 2026-09-26 (code at
`8541bbe`), on fresh verification evidence (`RTM.md` ENH-023 row; browser QA in
`docs/quality/ENH-023_BROWSER_QA_2026-09-26.md`); not merged. The independent Codex review was waived by the
owner ("ignore codex review", 2026-09-26). D1–D15 in `docs/superpowers/specs/2026-09-23-enh-023-tier-change-design.md`
§3 resolve the downgrade policy this item flagged as `NEEDS_CONFIRMATION` above: **grandfather** (D2) —
work already under way for a lost service can be finished; new work for it is refused (completion only,
D8). Full traceability: `PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-030`; `API_CONTRACT.md` §12A ENH-023
addendum; `RBAC_MATRIX.md` ENH-023 row; `SECURITY_CONTROLS.md` §6A ENH-023 row; `SCREEN_CATALOG.md`/
`screen_catalog.json` `SCR-SCH-036` and the `SCR-SCH-010` tier-fields note; `ROLE_NAVIGATION.md`
Principal section; `RTM.md` ENH-023 addendum (regression evidence); `ENH-023_BROWSER_QA_2026-09-26.md`
(QA-023-01..07, AC-1..AC-18 retested in the browser).

**Follow-ups (not built here, recorded for a later item):**
- (a) An Overseas Admin notifications page — this item added only the Principal's (D9); the acting
  admin still gets the in-app row plus email, with no dedicated inbox view of their own.
- (b) Closing the §8 residual concurrency window with a share lock across all 24 `ENH-022`-gated
  routes — out of scope here; a create whose transaction starts in the microseconds between the
  transition audit row's insert and the downgrade's commit can still get a `created_at` later than the
  downgrade row, so later updates to that one record are refused.
- (c) Notifying schools ahead of `tier_valid_until` expiry (pre-expiry notices) — expiry itself stays
  un-notified per `ENH-022` D2/D6, unchanged by this item.
- (d) A composite `audit_logs (action, entity_id)` index if tier-change volume ever makes the
  grandfather lookup slow — needs a migration, deliberately not added pre-emptively (D4: no migration
  in this item).
- (e) `create_school` still stores an empty-string `tier` as `""`, not `null` — D13's normalisation
  covers only the tier-change PATCH and the preview endpoint, not school creation.
- (f) A school name containing CR/LF makes `EmailMessage` reject the Subject header, so that school's
  tier notices are lost (logged; the tier change itself still stands) — existing `SCH-007` mailer
  behaviour, deliberately not changed here.
- (g) The email `From` display name is the admin-controlled school name — same existing mailer
  behaviour, deliberately not changed here.
- (h) **Needs a product decision (browser QA-023-01):** saving a past "valid until" date expires the
  partnership at once, with no warning to the admin and no notice to the school. The spec allows it (D6/D11:
  expiry is not a tier change), so it was not changed; whether the panel should warn, or the school be told,
  is the owner's call.
- (i) Copy, from the final browser pass: removal reads "Partnership is now no partnership tier.", and a
  preview failure shows the server's raw `detail` ("Internal Server Error") where the save path has friendlier
  wording.
- (j) The coordinator/principal Entitlements page did not reflect an expired partnership in the first browser
  pass (an `ENH-022` display gap; not rechecked in the final pass).

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

**Status (2026-09-28) — implemented, NOT complete.** Designed and decided in
`docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md` (`DEC-SCOPE-033`, D1–D16), plan
`docs/superpowers/plans/2026-09-28-enh-024-skill-india-certification.md`, built test-first on branch
`feature/enh-024-skill-india-certification`. The backlog's "Database impact" question resolved as a tag on ENH-012's
existing `certification` section (four nullable columns + CHECKs on `portfolio_entries`, migration `0044`), not a new
table; the "Integration impact" `NEEDS_CONFIRMATION` resolved as **none** (internal record, D9); the owning-role
`NEEDS_CONFIRMATION` resolved as the existing portfolio writers (D10). Evidence in `docs/quality/RTM.md` (ENH-024 row).
**Update (2026-09-28):** browser validation done; its findings QA24-01…08 fixed test-first and re-verified in the browser
(details in the RTM row); the independent Codex review was set aside by the owner. The Academic Team now has its own
student page with the editable Digital Portfolio. **Complete for ENH-024's scope (2026-09-28)** on fresh
verification evidence (RTM ENH-024 row). **Merged to `main` via PR #20 (`1ea4678`), 2026-09-28.** Found during verification, outside ENH-024: two E2E
specs broken on `main` by ENH-026 (`enh-022:43`, `sch-004:13` target the removed `#career-student`), and an ENH-012 layout
edge case (a long unbroken word in a portfolio title pushes that entry's Edit/Delete row past 320px).

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

**Status (2026-09-28) — COMPLETE (verified; evidence in the `RTM.md` ENH-026 row, *Final verification*).** Designed with `ENH-021` in `docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md` (`DEC-SCOPE-031`); implemented on branch `feature/enh-021-026-internship-counselling-record` (migration `0042_career_record_fields`, new `PATCH /school/career-counselor/records/{id}`). The skipped-state question is decided: strict order with a follow-up loop, create at Not Started/Scheduled/Completed, legacy rows (status NULL) only to Completed/Follow-up Required, and Completed, Follow-up Required and NULL count as completed. Corrections to this entry: the model is at `models.py` `SchoolCareerRecord` (the line numbers above were stale); recommendations are four JSON lists shared in shape with `ENH-027`. Browser validation done (FV-01..FV-04 fixed); the Codex review was waived by the owner; the transfer race is covered by a mutation-checked test; the full E2E regression runs on the regular cadence. **Owner decision from browser QA (2026-09-28), QA-13:** a session may be marked Completed before its scheduled date (sessions are brought forward); both dates are kept as the record of what was planned and what happened, with no block or warning.

**Regression risks.** `SCH-004`'s existing counselling-record read paths (including the
`/schools/entitlements` usage-count query at `schools.py:704`, which filters on `record_type ==
"counselling_note"`) must keep working unchanged.

**Complexity:** Medium. **Risk:** Low.

---

## ENH-027 — Psychometric Record: Structured Result Fields

**Status (2026-09-28):** built on `feature/enh-027-psychometric-full-record` per
`docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md` (`DEC-SCOPE-035`, migration `0045`);
**COMPLETE (verified 2026-09-28 on the branch merged with `main` at `bedbcce`)** — every acceptance criterion has fresh
test and browser evidence (`docs/quality/RTM.md` ENH-027 row); the independent Codex review was set aside by the owner.
Not yet merged to `main`. **Correction to the
count below:** today's record holds 3 of the 12 fields (Assessment type, Test status, Report); `created_at` is the
*assignment* day, only a proxy for Test date, so a real `test_date` column is added (9 fields, 10 columns). The shared
recommendation shape with `ENH-026` is settled: same names (`recommended_careers`, `recommended_stream`) and `list[str]`.

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

**Status (2026-10-01). COMPLETE for ENH-028's scope** on branch `feature/enh-028-bulk-entry` (verified at `cc16c04`; see the `RTM.md`
`ENH-028` row). Decided as `DEC-SCOPE-043` (user-approved, with simplifications S1–S5): create-only CSV bulk entry for Results,
Psychometric, Test Prep and Language; students named by `student_code`; pre-filled templates; idempotent replay per uploader;
per-row validation, portfolio scope, tier and duplicate checks that never block the batch; parent notices after the commit; one
generalized batch/row table pair (migration `0051`). The roster upload and every single-record endpoint are unchanged. The batch-size
question above is resolved: 1 MB / 500 filled-in rows for the new endpoints.

**Complexity:** Medium. **Risk:** Medium.

---

## ENH-029 — Bulk School Partner Onboarding (Admin, Multiple Schools at Once)

**Status (2026-10-01): COMPLETE on `feature/enh-029-bulk-school-onboarding` (verified at `842d4c8`; evidence in the `RTM.md`
ENH-029 row; not yet merged).** Open low-severity follow-ups: browser QA-029-04/05/06/07/08. Designed and decided in `docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md` (`DEC-SCOPE-047`); plan `docs/superpowers/plans/2026-10-01-enh-029-bulk-school-onboarding.md`.
**Corrections to this entry (2026-10-01):** the security note below is stale — `create_school` no longer sets
`"ChangeMe@12345"`; since ENH-003 it issues an unusable password + a 72 h set-password link, and bulk onboarding reuses that
path (`admin._provision_school`), so the ENH-003 dependency is met. Line references `admin.py:900-939`/`:920` predate later
changes (`create_school` is now `admin.py` ~1220). Final design: CSV of every `SchoolCreate` field, ≤ 100 rows, one
transaction with a savepoint per row, ENH-028's tables (`target_type = 'school_onboarding'`), welcome links after commit.

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

**Status (2026-09-30). COMPLETE for ENH-030's scope** on branch `feature/enh-030-class-attendance` (verified at `634b5e5`; browser
verification and a substitute independent review done — see the `RTM.md` `ENH-030` row). Designed and decided in
`docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md` (`DEC-SCOPE-041`, provisional number; plan
`docs/superpowers/plans/2026-09-30-enh-030-daily-attendance.md`). Corrections to this entry, all recorded in the spec:
"class" = the teacher's assigned students (no class/section entity exists; ENH-013 D3); the routes are
`GET`/`PUT /api/v1/school/attendance` (the school comes from the caller, never the path); statuses are
present/absent/late/excused (the IT set includes `excused`); writer = `school_teacher` only (Coordinator/Principal read);
"Student dashboard" = the Student 360° Attendance tab (school students have no login). Evidence: `RTM.md` `ENH-030` row.

---

## AGN-001 — Multi-Tenant Agent CRM: Agent Organisation as Tenant, Master Accounts

**Title.** Every agent company is a separate CRM tenant with Master logins that have full access.

**Business requirement.** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`): §1 "Master
Login — Agent Admin: full access to the agent's CRM account"; §3 example codes (`ABC-M001`); Best approach
"a multi-tenant Agent CRM: every agent gets their own separate CRM environment". Brought into scope by the
user's `AGN-001` statement and decided as `DEC-SCOPE-038` (D1–D13). The source's "one Master account"
conflicts with the user's criteria; the user chose up to three (D4).

**Existing behavior.** An agent is one `User` + `UserRoleAssignment(role='agent')`. Its `approval_status`
gates every agent route (`core/rbac.py:75`, `workflows.py:100`, `api/portal.py:31`). Every agent read and
write is scoped by `agent_id == user.id`. Overseas Admin approves/rejects the assignment by user id
(`admin.py:981-1026`), audited as `user_role_assignment`. No organisation, member or account code exists.

**Expected behavior.** Per `DEC-SCOPE-038`: an agent organisation (tenant) with status
`pending`/`active`/`rejected`/`suspended`; Master members with display codes `<PREFIX>-M###`; the
approval gate and all data scoping move to the organisation; Masters invite and deactivate Masters;
Overseas Admin approves, rejects, suspends and reinstates organisations.

**User roles affected.** `agent` (now an organisation Master), `overseas_admin`, `super_admin`; indirectly
`counselor`/`overseas_admin` where they attach an application or commission to an agent.

**Frontend impact.** `RegisterForm.tsx` (agency name), `AgentApprovalPanel.tsx` (organisation, code,
status, suspend/reinstate), a new Master team screen under `/overseas/agent/`, `lib/navigation.ts`.
Screens get `SCR-` IDs in the design spec.

**Backend impact.** `auth.register`, `_sync_role_assignment`, `rbac.agent_is_approved`, every agent-scoped
query in `workflows.py` and `services/portal._agent`, admin approve/reject/list, admin user-create,
commission notifications.

**Database impact.** New organisation and member tables; the scope key for `agent_students`,
`agent_commissions` and `overseas_applications.agent_id` moves to the organisation (column shape decided
in the design spec); backfill migration (D10).

**API impact.** New `/overseas-admin/agent-orgs/{org_id}/approve|reject|suspend|reinstate`; new Master
invite/deactivate/list endpoints; registration gains an agency name; existing
`/overseas-admin/agents/{agent_id}/approve|reject` kept and delegated (D7).

**Integration impact.** Invite email through the existing notification delivery and the `DEC-SCOPE-019`
set-password link. No new provider.

**Authentication/Authorization impact.** High. The approval gate moves to the organisation; suspension
must bite on the next request; tenant isolation on every agent route.

**Security impact.** High — cross-tenant data exposure is the main risk. **Performance impact.** One extra
organisation lookup per agent request (loaded with the user).

**Reusable existing modules.** `get_current_user` (already reloads the user each request),
`agent_is_approved` call sites, `DEC-SCOPE-019` set-password token, `_audit`, `_notify_user`.

**Dependencies.** Changes `AGT-001`–`004`, `SEC-001`, `RPT-002`, `ADM-001`. None must land first.

**Acceptance criteria.**
- **AGN-001-AC01** Registering as an agent creates exactly one `pending` organisation and one Master member
  with code `<PREFIX>-M001`, in one transaction; prefix per D5.
- **AGN-001-AC02** Until the organisation is `active`, its Master is denied every agent route (today's
  `AGT-001-AC02`, preserved).
- **AGN-001-AC03** Approve, reject, suspend and reinstate act on the organisation and each writes an audit
  row (`entity_type='agent_org'`) in the same transaction; the old per-agent routes act on the agent's
  organisation.
- **AGN-001-AC04** Suspending an organisation denies every member every agent route on their next
  request; `/auth/me`, logout and notifications still work; reinstating restores access.
- **AGN-001-AC05** After migration, each pre-existing agent is `M001` of its own organisation —
  approved → `active`, pending or rejected → `pending` — with unchanged data access.
- **AGN-001-AC06** No agent route returns or changes data from another organisation; a cross-tenant test
  exists for every agent read and write.
- **AGN-001-AC07** A 4th active-or-invited Master → `422`; deactivating the last active Master → `422`;
  a code is never reassigned (next = highest ever + 1); a deactivated Master cannot be reactivated.
- **AGN-001-AC08** Only an active Master of the organisation can invite or deactivate its Masters;
  the invite uses the `DEC-SCOPE-019` set-password link.
- **AGN-001-AC09** An admin-created `role='agent'` user gets a `pending` organisation and code `M001`.
- **AGN-001-AC10** Commission-estimated and commission-eligible notifications go to every active Master.

**Positive scenarios.** Register → pending → approved → Master sees org data; Master invites M002, who sets
a password and sees the same org data; suspend → denied → reinstate → allowed.
**Negative scenarios.** Master of org A reads/writes any org B student, application, document or
commission → `403`/`404`; pending/rejected/suspended org → `403`; non-Master or other-org Master invites
→ `403`; 4th Master and last-Master deactivation → `422`.
**Edge cases.** Prefix collisions and padding (D5); two registrations racing for the same prefix; invite
to an email that already exists; deactivated Master's open session; rejected legacy agent migrated to
`pending`.

**Regression risks.** High — `AGT-001`–`004`, `SEC-001` and `RPT-002` tests and E2E specs, the approval
routes used by `AgentApprovalPanel`, `ADM-001`'s agent role option, seed data.

**Complexity:** Large. **Risk:** High.

**Status (2026-09-29) — COMPLETE for AGN-001's scope; merge to `main` open.** Designed (`docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md`,
E1–E12), planned (`docs/superpowers/plans/2026-09-28-agn-001-multi-tenant-agent-crm.md`) and built test-first on branch
`feature/agn-001-multi-tenant-agent-crm` (migration `0046_agent_orgs`); review decisions R1–R3 added to `DEC-SCOPE-038`. Browser
QA (QA-01…13) fixed and re-verified, including after merging `main`; the independent Codex review was set aside by the owner
(in-session, 2026-09-29), as for ENH-024/ENH-027. Evidence in `docs/quality/RTM.md` (AGN-001 row). QA-01 replaced the admin
portal "Agent Registrations" table with "Agent Masters" (organisation + Master status). Internal-review minors #7, #8, #11, #12
accepted by the owner as known limitations (2026-09-29): #7 a fast tab switch can briefly show the previous tab's rows (a server 409 prevents acting on the wrong one); #8 a page emptied by another admin shows no Previous (the tab recovers); #11 the Team panel shows a generic load error on 403 (the portal page shows the reason); #12 the migration backfill's idempotence is verified by a manual round trip only (#10, a dead branch, was removed).

---

## AGN-004 — Agent Students: Master/Staff Create, Edit, View and Archive Students Who Never Log In

**Business requirement.** The owner's `AGN-004` statement (in-session, 2026-09-30): "Master/Staff create, edit, view and archive
students who never log in (§2 Students, §5 Step 1; DEC-ROLE-004; DEC-SCOPE-035 D3)." Acceptance: create/edit/view/archive work for
the right roles; an archived student leaves default lists but remains in history and reports; Staff cannot see a student assigned
to someone else (`404`); no `users` row is ever created for an agent student; the within-org duplicate warning fires. The cited
`DEC-SCOPE-035 D3` does not decide agent students (it is ENH-027's decision; `DEC-SCOPE-038` D3 is the account-code rule) —
recorded, not silently fixed; this feature's decisions are `DEC-SCOPE-042`.

**Source.** `functionalities/edusphere_markdown/Agent CRM Functionalities.md` (`EVID-015`, `DERIVED_BLUEPRINT`) §2 "Students",
§5 Step 1, §6. `DEC-ROLE-004` (no login for agent-referred students).

**Expected behavior.** Per `DEC-SCOPE-042`: students with no login live on `agent_students` (identity, academic, preference
fields; assignment; archive) and never get a `users` row; the existing "link a student who has an account" flow stays. A
student created or linked by Staff is assigned to them; a Master's starts unassigned; only a Master assigns, archives and
unarchives. Staff see only their assigned students on every agent path (new student routes, roster, applications, documents,
lookups, portal pages); Team and Commissions stay Master-only (AGN-002 S1). Same email (any case) or phone (≥ 7 digits) inside
the agency warns; saving again with confirmation proceeds (audited).

**Dependencies.** Independent of `AGN-002` (owner G1) with AGN-002's exact Staff names (G2); merge notes in the design spec §12.

**Acceptance criteria.** AGN-004-AC01…AC13, verbatim in `docs/superpowers/specs/2026-09-30-agn-004-agent-students-design.md` §8.

**Status (2026-10-01) — COMPLETE** (evidence: `docs/quality/AGN-004_BROWSER_QA_2026-10-01.md` post-merge and Assign sections). Browser QA done (QA-01…QA-10 found and fixed, `docs/quality/AGN-004_BROWSER_QA_2026-10-01.md`); the independent Codex review is pending. Designed (spec rev. 2), planned
(`docs/superpowers/plans/2026-09-30-agn-004-agent-students.md`) and built test-first on `feature/agn-004-agent-students`
(migration `0049_agent_students_crm`, re-chained after AGN-002's `0047_agent_org_staff` when main was merged 2026-10-01). The Master
Assign row action (spec §6) was built on 2026-10-01; Staff browser flows and Playwright verified on the merged build. Open, outside
the ACs: PRD open item 80 (erasure of students with no login) — moved to the backlog as `AGN-ERASE` below; the independent Codex review was set aside by the owner. Evidence in `docs/quality/RTM.md`.

---

## AGN-ERASE (provisional ID — `NEEDS_CONFIRMATION`) — Erasure of Agent Students Who Have No Login

**Status (2026-10-01) — BACKLOG, not scheduled** (owner: "move to backlog" — the whole feature). Origin: PRD open item 80, found by
the AGN-004 security review. The feature ID is provisional; the owner assigns AGN numbers.

**Business requirement.** A student recorded by an agency without a login (AGN-004, `agent_students.student_id IS NULL`) holds
personal data (name, email, phone, date of birth, education, preferences, notes) but has no way to have it erased: the SEC-002
data-request flow is keyed to the requester's own `users` account, and AGN-004 gives agencies archive only (no delete, D5).

**Owner decisions (in-session 2026-10-01, `EXPLICIT_APPROVAL` — answers to structured questions):**
- **Requester:** the agency's Master raises the erasure request for one of the agency's students (e.g. after the student asks them).
- **Verification:** the Master records how the student asked (free text); an EduSphere admin (Overseas Admin / Super Admin) approves
  or rejects with a reason; both steps audited.
- **Erasure:** anonymise the `agent_students` row in place — name becomes "Erased student", every other personal field cleared,
  status archived, row id kept so audit history and counts stay consistent. Audit rows already hold ids and field names only.

**Still `NEEDS_CONFIRMATION` before design:**
- **Admin screen:** the SEC-002 queue (`GET`/`PATCH /admin/data-requests`) has no admin UI today; options offered — a Data requests
  screen for both flows, a screen for agency requests only, or API-only like SEC-002. Not answered (deferred with the feature).
- **Export:** whether the Master can also request an export for such a student (the Master can already view every field).
- **Feature ID** and decision ID (next free is `DEC-SCOPE-044`).

**Design constraints already found (from reading the code, 2026-10-01):**
- `PATCH /admin/data-requests/{id}` anonymises the **requesting** `users` row. A Master's request on a student's behalf must carry
  the target `agent_students` id and branch on it — otherwise fulfilling it would anonymise the Master's own account.
- `data_subject_requests` needs a nullable target column (e.g. `agent_student_id`); the admin list scopes by the requester's
  division, and a Master is in `overseas`, so Overseas Admin sees these requests.
- Students with no login have no applications or commissions (those are keyed to student accounts), so erasure touches only the
  `agent_students` row; the within-agency duplicate check must not match on erased (blank) fields.

**Dependencies.** AGN-004 (merged into its branch, COMPLETE 2026-10-01); SEC-002 (data-request flow).

---

## ENH-031 — Searchable Reference Pickers (Student / Application References)

**Requirement:** the owner, in-session 2026-09-29 (`EXPLICIT_APPROVAL`): every student and application reference is a searchable dropdown of valid values. **Decision:** `DEC-SCOPE-039` (D1–D5). **Spec:** `docs/superpowers/specs/2026-09-29-enh-031-searchable-reference-pickers-design.md` (AC01–AC10). **Plan:** `docs/superpowers/plans/2026-09-29-enh-031-searchable-reference-pickers.md`.

**Status (2026-09-29):** implemented on `feature/agn-001-multi-tenant-agent-crm`; evidence in `docs/quality/RTM.md` (ENH-031 row).

---

## AGN-002 — Agent Staff Logins: Master Creates, Edits, Activates/Deactivates and Resets Staff

**Title.** An agency's Masters manage staff logins with auto-generated Staff IDs.

**Business requirement.** The owner's `AGN-002` statement (in-session, 2026-09-30): "Master creates, edits,
activates/deactivates and resets staff logins; Staff ID is auto-generated (§2 Staff, §3)", referring to
`EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2 and §3. Decided as `DEC-SCOPE-040`
(S1–S6).

**Existing behavior.** `AGN-001` members are Masters only (`ck_agent_org_members_role`); one `seq` per
organisation; Masters invite and deactivate Masters (`api/agent_team.py`, `services/agent_orgs.py`).
Every agent route is scoped to the whole organisation (`org_member_ids`). No staff concept exists.

**Expected behavior.** Per `DEC-SCOPE-040`: a Master creates a staff login (name, email, phone) with code
`<PREFIX>-S###` and a set-password email; edits name and phone; deactivates and reactivates it; resets it
(password unusable, new set-password link, sessions ended). Staff use the agent student/application
routes organisation-wide but not team management or commissions.

**User roles affected.** `agent` (Master and the new staff member role). Indirectly `overseas_admin` /
`super_admin` (agent list and approval routes, user reactivation).

**Frontend impact.** `AgentTeamPanel.tsx` (Staff section), the portal `team` section, possibly the agent
sidebar for staff (`lib/navigation.ts`, `WorkflowPanel.tsx`); screen `SCR-AGT-007`.

**Backend impact.** `services/agent_orgs.py` (staff functions; Master-only role filters in
`count_active_masters`, `deactivate_master`, `notification_recipients`), `api/agent_team.py` (staff
routes; Master-only guard), commission routes in `workflows.py` / `services/portal.py` (Master-only),
`rbac.agent_denial_reason` (message), `deps.get_current_user` and `auth.refresh` (session revocation),
`admin.py` agent list/approve/reject and user `PATCH` (staff handling).

**Database impact.** Migration after `0046_agent_orgs`: member role `master|staff`, per-role sequence
uniqueness, a staff counter on `agent_orgs`, member status allowing reactivation; session-revocation
field on `users` (design spec).

**API impact.** New staff endpoints under `/workflows/overseas/agent/team/staff` (list, create, edit,
deactivate, reactivate, reset), with a paginated staff list; the existing team `GET` keeps its shape and lists
Masters only. Design: `docs/superpowers/specs/2026-09-30-agn-002-staff-logins-design.md`.

**Integration impact.** Set-password email through the existing `DEC-SCOPE-019` delivery. No new provider.

**Authentication/Authorization impact.** High. Master-only vs staff checks on every agent route;
session revocation on reset; deactivation denies every API.

**Security impact.** High — privilege escalation (staff reaching Master-only actions), cross-tenant
access, mail abuse via create/reset loops. **Performance impact.** None significant (the session check
reads the already-loaded user).

**Reusable existing modules.** `_require_master`, `lock_org`, `issue_welcome_token`,
`deliver_welcome_link`, `revoke_welcome_tokens`, `unusable_password_hash`, `flush_unique_email`, the
`AGN-001` invite throttle pattern, `AuditLog`.

**Dependencies.** `AGN-001` (built, on `main`). None must land first.

**Acceptance criteria.**
- **AGN-002-AC01** Creating staff yields code `<PREFIX>-S001`, `S002`, … unique per organisation and never
  reused (next = highest ever issued + 1), independent of Master codes.
- **AGN-002-AC02** Creating staff sends a one-time set-password email (`DEC-SCOPE-019`), or the response
  reports that it could not be sent; the Master never receives the token.
- **AGN-002-AC03** A Master edits a staff member's name and phone; email cannot be changed.
- **AGN-002-AC04** Deactivated staff are denied every API (not only agent routes) on their next request,
  and their open set-password link is revoked.
- **AGN-002-AC05** Reactivation restores access.
- **AGN-002-AC06** Reset makes the current password unusable, emails a new set-password link and ends the
  staff member's existing sessions.
- **AGN-002-AC07** A Master of another organisation cannot list, see or change the staff member (`404`);
  staff cannot manage staff or Masters, or use commission routes (`403`).
- **AGN-002-AC08** Every staff action (create, edit, deactivate, reactivate, reset) writes an audit row
  (`entity_type='agent_org'`) in the same transaction.
- **AGN-002-AC09** Staff do not count toward the 3-Master limit or the last-Master rule and do not receive
  commission notifications; an active staff member of an `active` organisation reaches the agent
  student/application routes with organisation scope.
- **AGN-002-AC10** Staff creations and resets are throttled per agency on a rolling 24 hours (`429` with
  `Retry-After`).

**Positive scenarios.** Master creates S001 → staff sets password → sees org students/applications;
deactivate → denied → reactivate → allowed; reset → old password and session fail → new link works.
**Negative scenarios.** Other-org Master acts on the staff member → `404`; staff calls team or commission
routes → `403`; duplicate email → `409`; over the throttle → `429`.
**Edge cases.** Reset or deactivate of staff who never set a password; reactivation after the link
expired; concurrent creations (code uniqueness under the organisation lock); suspended organisation.

**Regression risks.** High — the `AGN-001` suite (`test_agn_001_*.py`, `AgentTeamPanel.test.tsx`,
`agn-001-multi-tenant.spec.ts`), every agent-scoped route (`AGT-001`–`004`), commission notifications,
Overseas Admin agent approval.

**Complexity:** Medium–Large. **Risk:** High.

**Status (2026-09-30):** implemented test-first on `feature/agn-002-staff-logins` (migration `0047_agent_org_staff`); evidence
in `docs/quality/RTM.md` (AGN-002 row). Browser QA pass done 2026-09-30 (QA-01…08 fixed, re-verified). **COMPLETE (2026-10-01,
verified at `2e7ac9a`)**; the owner waived the Codex review and runs the full backend suite in their 4-5-story batch.

---

## AGN-003 — Agent Staff Permissions: the Master vs Staff Matrix

**Title.** Staff are limited to the student journey; a Master switches two optional permissions on per staff member.

**Business requirement.** The owner's `AGN-003` statement (in-session, 2026-10-01): "the §6 matrix: Staff are limited to the
student journey, with no admin modules; 'Set permissions' / 'Permission Level'", referring to `EVID-015`
(`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2, §3, §4 and §6. Decided as `DEC-SCOPE-044` (P1–P9).

**Existing behavior.**
- Staff are refused only team management and commissions (`AGN-002`).
- Staff reach the agent Reports page.
- No agent can verify or reject documents.
- There is no permission storage.

**Expected behavior.** Per `DEC-SCOPE-044`:
- Every ❌ cell of §6 that has a route returns `403` for staff; every ✅ cell succeeds.
- Verify Documents and Reports are per-staff toggles, off by default, set by a Master and effective on the next request.
- Agents (Masters, and staff with Verify) may decide pending documents of their agency; staff may only mark them verified.
- §6 rows with no capability are N/A. The full matrix is in the design spec §3.

**User roles affected.**
- `agent` (Master and staff).
- Indirectly `counselor` / `overseas_admin` (shared document verify route; their behaviour is unchanged).

**Frontend impact.**
- `AgentStaffRow.tsx` (Permissions) and `AgentStaffPanel.tsx` (help text).
- `lib/navigation.ts` (staff Reports) and `PortalPage.tsx`.
- `CounselorDocumentReviewPanel.tsx`, generalised and reused on the agent Documents page.
- `WorkflowPanel.tsx`.
- Screens SCR-AGT-005, SCR-AGT-007.

**Backend impact.**
- `core/rbac.py` (`agent_may`, `agent_permissions`).
- `api/portal.py` (Reports).
- `api/workflows.py` `verify_document` (agent branch).
- `api/agent_team.py` and `services/agent_orgs.py` (set permissions).
- `api/auth.py` `/me` and `schemas.py`.

**Database impact.** Migration `0052_agent_staff_permissions`: `agent_org_members.can_verify_documents`, `can_view_reports`
(`BOOLEAN NOT NULL DEFAULT false`); additive, existing rows preserved.

**API impact.**
- New `PUT /workflows/overseas/agent/team/staff/{member_id}/permissions`.
- An agent branch on `PATCH /workflows/overseas/documents/{id}/verify`.
- Additive `permissions` on the staff shape and `agent_permissions` on `/auth/me`.
- Portal Reports `403` for staff without the toggle.

**Integration impact.** None (the existing student "Document reviewed" notification is reused).

**Authentication/Authorization impact.** High. Per-request permission checks from the database row; Master-only toggle route;
pending-only agent review under a row lock.

**Security impact.**
- High: staff escalation to Master-only actions, cross-tenant toggling, agents overwriting the counselor's review.
- Mitigations: spec §10.

**Performance impact.** None (the flags ride on the membership already loaded per request).

**Reusable existing modules.** `_require_master`, `_staff_org`, `_staff_member`, `_commit_staff_change`, `_staff_audit`, `_require`,
`_assigned_application`, `org_member_ids`, `CounselorDocumentReviewPanel`, `sendJson`/`staffFailure`.

**Dependencies.** `AGN-002` (built, on `main`). None must land first.

**Acceptance criteria.**
- **AGN-003-AC01** Every ❌ cell of §6 that has a route returns `403` for staff with both toggles off, each with a test.
- **AGN-003-AC02** Every ✅ cell succeeds for staff and for Masters; Masters also succeed on Verify, Reject and Reports.
- **AGN-003-AC03** Reports: staff toggle off → `403`, on → `200` without commission figures; Masters always `200`.
- **AGN-003-AC04** Verify: staff toggle off → `403`; on + `verified` → `200`; on + `rejected`/`changes_required` → `403`.
- **AGN-003-AC05** A toggle change applies on the staff member's next request without signing them out.
- **AGN-003-AC06** Only a Master of the staff member's organisation sets toggles (another agency or a Master id → `404`, staff → `403`,
  bad body → `422`); every change writes an `agent_org.staff_permissions` audit row in the same transaction.
- **AGN-003-AC07** Agents decide only `pending` documents in their agency's scope (`409` / `403` / `404` / `422` as in the spec); a
  counselor or Overseas Admin can still re-review; the student is notified and the decision audited.
- **AGN-003-AC08** `/auth/me` returns `agent_permissions`; the staff member shape returns `permissions`.
- **AGN-003-AC09** Migration `0052` follows ENH-028 `0051_school_bulk_uploads` as the single head (re-chained on merging `main` twice; drafted as `0048` after `0047`); defaults `false`; existing members preserved.

**Positive scenarios.**
- Master turns Reports on → the staff member's next page load shows Reports.
- Master turns Verify on → staff mark a pending document verified → the student is notified.
- Master rejects a pending document.

**Negative scenarios.**
- Staff open Reports with the toggle off → `403`.
- Staff reject → `403`.
- Staff call the permissions route → `403`.
- Another agency's Master toggles → `404`.
- An agent decides an already-reviewed document → `409`.

**Edge cases.**
- Toggling a deactivated staff member.
- A toggle switched off while the staff member's page is open.
- Two agents deciding the same document at once.
- A document not attached to an application.
- Upgrade with existing staff (Reports turns off).

**Regression risks.**
- High: the counselor/admin document verify path (`test_ovs_005_documents.py`).
- The two AGN-002 staff Reports tests (updated deliberately to Reports on).
- The agent nav (`navigation.test.ts`, `agn-002-staff.spec.ts`).
- The counselor review panel UI.

**Complexity:** Medium. **Risk:** High.

**Status (2026-10-01):** implemented test-first on `feature/agn-003-staff-permissions` (migration `0052_agent_staff_permissions`); verification evidence in `docs/quality/RTM.md` (AGN-003 row). **COMPLETE (2026-10-01, verified at `5cb16ad`)** — final verification-before-completion pass recorded in the RTM (AGN-003 row); the owner waived the independent Codex review.

---

## AGN-021 — Agent Staff Activity: a Master Views a Staff Member's Student-Journey Activity

**Title.** A Master opens a staff member's recent student-journey work from the Team page.

**Business requirement.** The owner's `AGN-021` statement (in-session, 2026-10-01): requirement **"View staff activity" (§2 Staff)**;
acceptance criteria: **a Staff member's actions appear within one page load; other orgs' users → 404.** Referring to `EVID-015`
(`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2. Decided as `DEC-SCOPE-046` (A1–A5).

**Existing behavior.**
- The seven student-journey actions are already audited with the staff user as `user_id` (`agent_student.create`/`update`/`duplicate_override`, `agent.student_link`, `overseas.application.create`, `document.upload`, `document.verify`).
- No route or screen reads them for a Master; `GET /admin/audit` is admin-only and not tenant-scoped.

**Expected behavior.** Per `DEC-SCOPE-046`:
- A Master sees a staff member's activity (time, plain label, subject; field names for an edit) newest first, read fresh on every request.
- Staff are refused (`403`); another agency's user, a Master's own member id and an unknown id are `404 "Staff member not found"`.
- Deactivated staff remain viewable. Notes, values, emails and ids are never shown.

**User roles affected.** `agent` (Master views; Staff refused).

**Frontend impact.** `AgentStaffActivity` (new), `AgentStaffRow.tsx` (Activity button and section), `lib/agentStaff.ts` (types, labels). Screen `SCR-AGT-007`.

**Backend impact.** `api/agent_team.py` (route), `services/agent_orgs.py` (`find_staff_member`), new `services/staff_activity.py`.

**Database impact.** None. No migration, no new audit writes, no new index (a composite `(user_id, created_at)` index is noted in RAID, not built).

**API impact.** New `GET /workflows/overseas/agent/team/staff/{member_id}/activity` (`limit` 1–100 default 25, `offset` 0–10000; `{items,total,limit,offset}`; `422` out of range).

**Integration impact.** None.

**Authentication/Authorization impact.** Medium. Master-only; tenant scope through the caller's organisation; no org id in the path.

**Security impact.**
- Medium: cross-tenant read (IDOR) and over-exposure of audit metadata.
- Mitigations: spec §8 (identical 404, allow-list of seven actions, subjects limited to what the Master can already see, field names only).

**Performance impact.** Paged read on the indexed `audit_logs.user_id`; subjects resolved in at most three batched queries per page.

**Reusable existing modules.** `_require_master`, `_staff_org`, `_staff_member` (lookup extracted), `AuditLog`, `staffFailure`/`detailMessage`, `formatDate`.

**Dependencies.** `AGN-001`, `AGN-002`, `AGN-003`, `AGN-004` (all on `main`).

**Acceptance criteria.**
- **AGN-021-AC01** Each allow-listed action a Staff member performs through the real API appears in the Master's next activity request, newest first.
- **AGN-021-AC02** Another agency's Master, a Master's own member id and an unknown id → `404 "Staff member not found"`; Staff → `403`; inactive agency → `403`.
- **AGN-021-AC03** Rows outside the allow-list (sign-in, profile/password change, link search, message) and another staff member's rows never appear.
- **AGN-021-AC04** Subjects resolve for each entity type; a missing entity reads "No longer available"; reviewer notes, emails, field values and ids other than the row id are never in the response.
- **AGN-021-AC05** Paging: `{items,total,limit,offset}`, stable order on equal timestamps (`id` tiebreak), `limit` 1–100 and `offset` 0–10000 else `422`.
- **AGN-021-AC06** Deactivated staff remain viewable.
- **AGN-021-AC07** UI: Activity opens from the staff row; loading / empty / error + Try again / paging / Refresh; stale responses ignored; keyboard + focus return; 320 px.

**Regression risks.**
- The `_staff_member` refactor (used by edit/deactivate/reactivate/reset/permissions): extraction only, lock behaviour unchanged; AGN-002/003 suites in the lite set.
- `AgentStaffRow` gains a mode: existing row tests keep passing; new cases added.
- Audit row shape changes in future: allow-list plus defensive parsing; a missing subject reads "No longer available".

**Status (2026-10-01) — COMPLETE on `feature/agn-021-staff-activity` (verified at `7b2b085`; evidence in `RTM.md`, AGN-021 row; not yet merged to `main`).** The independent Codex review was waived by the owner in-session 2026-10-01. Earlier status line, kept for history: IMPLEMENTED, NOT complete. Backend and web unit tests pass (evidence in `RTM.md`). Playwright e2e recorded as passed (see `RTM.md`, AGN-021 row). Browser QA done 2026-10-01: QA-01…QA-04 found, fixed (`aa11adc`) and re-verified in the browser (`docs/quality/AGN-021_BROWSER_QA_2026-10-01.md`). Independent Codex review: waived by the owner (2026-10-01). Full backend suite not run (owner cadence).

---

## AGN-007 — Agent Student University Shortlist and Agency University Database

**Title.** Agents shortlist universities for a student, from the shared catalogue or from their own agency's private list.

**Business requirement.** The owner's `AGN-007` statement (in-session, 2026-10-01): "add university, course, country, intake, tuition fee and
entry requirements to a student's shortlist. University DB: Master 'Full', Staff 'View'; 'Add University' is Master only (§6; DEC-SCOPE-035 D4)."
Referring to `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 "STEP 3 — University Shortlisting" and §6 rows "University Database" and
"Add University". Decided as `DEC-SCOPE-049` (D1–D10). The `DEC-SCOPE-035 D4` citation is a recorded mis-citation (see the decision); `DEC-SCOPE-044` P3
is superseded for those two §6 rows only.

**Existing behavior.**
- No agent-owned university or shortlist exists. Universities, courses and countries are an admin-managed, public catalogue (`GET /public/universities`).
- `RBAC_MATRIX.md` §2.8 recorded both §6 rows as N/A (`DEC-SCOPE-044` P3).
- `create_bridged_application` stores a `course_id` without the course-belongs-to-university check (out of scope; `RAID.md`).

**Expected behavior.** Per `DEC-SCOPE-049`:
- A Master adds, edits and deletes **agency-private** universities (never in the shared catalogue, never on `/public`); Master and Staff list them.
- Master and Staff add, edit and remove shortlist entries for students in their scope; each entry has one university (catalogue or agency) and an optional course, intake, tuition fee and entry requirements. Country comes from the university.
- A catalogue course must belong to the chosen catalogue university; a typed course is allowed with either kind. Caps: 50 entries per student, 500 universities per agency.
- An archived student's shortlist is read-only (`409`).

**User roles affected.** `agent` (Master: full; Staff: view the University Database, write the shortlist of assigned students).

**Frontend impact.** `AgentUniversitiesPanel`, `AgentUniversityForm` (new; `/overseas/agent/universities`, mounted by `PortalPage`), `AgentShortlistPanel`, `AgentShortlistForm`, `AgentShortlistCard` (new), one mount line in `AgentStudentDetailPanel`, `lib/agentShortlist.ts`, `lib/navigation.ts` (Universities item). Screens `SCR-AGT-008` (updated) and `SCR-AGT-009`.

**Backend impact.** New `api/agent_shortlist.py` and `services/agent_shortlist.py`; `schemas.py` (four request models); `models.py` (two models); `main.py` (router); `services/portal.py` (`universities` section); `services/staff_activity.py` (three whitelist actions). `api/agent_students.py` is imported, not edited.

**Database impact.** Migration `0056_agent_shortlist` (two new tables; additive; no existing row changes).

**API impact.** New `/workflows/overseas/agent/crm/universities` (GET, POST, PATCH, DELETE) and `/crm/students/{student_id}/shortlist` (GET, POST, PATCH, DELETE); `API_CONTRACT.md` §8.

**Integration impact.** None.

**Authentication/Authorization impact.** Medium. Master-only writes on universities; scope via `load_scoped` for shortlist routes; agency isolation via `org_id` in every WHERE clause.

**Security impact.**
- Medium: cross-agency IDOR (an agency university id in a body, an entry id on another student), staff writing outside their scope, leakage of agency-private universities to `/public`, mass assignment.
- Mitigations: spec §7 (scoped loads, identical `422`/`404` answers, `extra="forbid"`, role check after the scoped load, caps under the agency lock, audit with ids and field names only). `THREAT_MODEL.md`, `SECURITY_CONTROLS.md`.

**Performance impact.** Indexed paging (`ix_shortlist_student_created`, `agent_universities.org_id`); caps bound the lists.

**Reusable existing modules.** `agent_students._gate` / `_audit` / `_log` / `_locked_row`, `services/agent_students.load_scoped`, `services/agent_orgs.lock_active_org`, `is_agent_staff`, `clean_free_text`, the `AgentStudentsPanel` card, paging and confirm patterns, the `GET /public/universities` reads.

**Dependencies.** `AGN-001`, `AGN-002`, `AGN-003`, `AGN-004`, `AGN-021` (staff-activity whitelist).

**Acceptance criteria** (verbatim from `docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md` §8).
- **AGN-007-AC01** A catalogue-backed entry (catalogue university, its catalogue course, intake, fee, requirements) saves: 201; GET shows `source:"catalogue"` and the catalogue country.
- **AGN-007-AC02** A free-text entry (agency university, typed course) saves: 201; `source:"agency"`; the country comes from the agency university.
- **AGN-007-AC03** A course from another university returns 422 "Course does not belong to selected university". A catalogue course with an agency university, both or neither university, or both course forms each return 422. Nothing is written in any of these cases. The migration test proves the CHECK constraints at database level.
- **AGN-007-AC04** Invisible to other agencies: another agency's university id in a body returns 422; its university by id returns 404, and it is absent from the list; another agency's student shortlist returns 404.
- **AGN-007-AC05** Invisible to `/public`: `/public/universities`, `/public/universities/{slug}`, `/public/countries/{slug}` and `/public/overseas-courses` are unchanged after agency universities and entries are created.
- **AGN-007-AC06** University DB: Master and Staff can GET the list. Staff POST, PATCH and DELETE return 403, with no row and no audit row. Masters succeed, and each write is audited.
- **AGN-007-AC07** Shortlist scope: Staff can do all four operations for assigned students; any other student returns 404 (before any role check). Masters can do so for any agency student.
- **AGN-007-AC08** An archived student's shortlist is readable, and writes return 409. A linked (login) student is writable.
- **AGN-007-AC09** Deleting an agency university that is in use returns 409, and nothing is lost. A duplicate name and country in the same agency returns 409; the same name in another agency is allowed.
- **AGN-007-AC10** Caps: the 51st entry and the 501st university return 422. Two concurrent adds at 49 entries end at exactly 50.
- **AGN-007-AC11** Pagination: the envelope; stable order; 422 for out-of-range values; an offset past the end returns empty items with the true total.
- **AGN-007-AC12** Each write produces exactly one audit row in the same transaction, with no free-text values. Shortlist actions appear in AGN-021 staff activity; agency-university actions do not.
- **AGN-007-AC13** UI: Master and Staff add a catalogue entry and an agency entry from the detail view. Staff see no write controls in the University Database. Loading, empty and error-with-Retry states render. Keyboard-only use works, and the layout works at 375 px.
- **AGN-007-AC14** Regression: the AGN-001/003/004/005/021, OVS-001/002 and public catalogue suites pass. The only existing test edited is the AGN-003 matrix rows for University DB and Add University.

**Regression risks.**
- Merge collision with `AGN-006` / `AGN-008` (DEC number, migration number, `STAFF_ACTIVITY_ACTIONS`, `AgentStudentDetailPanel`): `agent_students.py` untouched, one mount line; renumber and re-chain at merge.
- A leak into the public catalogue: catalogue tables and `public.py` untouched; AC05 asserts it.
- The AGN-003 matrix rows change deliberately (recorded as the partial supersession of `DEC-SCOPE-044` P3).

**Complexity:** Large. **Risk:** Medium.

**Status (2026-10-02): COMPLETE** on `feature/agn-007-student-shortlist` — evidence in `docs/quality/RTM.md` (AGN-007 row, "Completion verification") and `docs/quality/AGN-007_BROWSER_QA_2026-10-02.md` (all acceptance criteria PASS in the browser; AC03 DB CHECKs and AC10's 500-university cap and concurrency covered by backend tests). Independent review waived by the owner. Owner-side, outside COMPLETE: the full backend suite (standing 4–5-story cadence), an `ovs-001-discovery` e2e re-run on a clean database, and the merge (re-chain against `AGN-008` `0057` if it lands first).

---

## AGN-005 — Close the §6 Staff Matrix Gap for Agency Student Records

**Title.** Put AGN-004's student routes into the §6 Master-vs-Staff matrix tests and docs.

**Business requirement.** The owner's `AGN-005` statement (in-session, 2026-10-01) repeats `AGN-003`'s: "the §6 matrix: Staff are
limited to the student journey, with no admin modules; 'Set permissions' / 'Permission Level'", with the same acceptance (every ❌ cell
`403` for Staff with a test, every ✅ cell succeeds, toggles flip the two optional rows, a toggle change applies on the next request).
AGN-003 met all of it except the student rows. The owner scoped AGN-005 to that gap: tests and docs only (Revision 10).

**Existing behavior.** AGN-004's `/workflows/overseas/agent/crm/students` routes already let staff create, view and edit their
assigned students and refuse them archive, unarchive and assign (`403`). AGN-003's matrix test, its spec §3 and `RBAC_MATRIX.md` §2.8
still marked Edit, Delete and Assign Student N/A, and no test covered unarchive by the assigned staff member or the staff UI on an
archived student.

**Expected behavior.** Unchanged. The matrix tests and docs now cover every §6 row that has an agent route. Delete Student maps to
archive and unarchive (no delete route; `DEC-SCOPE-042` D5).

**User roles affected.** `agent` (Master and staff) — tests and docs only.

**Frontend / backend / database / API / integration impact.** None (no production code, migration or contract change). Tests:
`apps/api/tests/test_agn_003_matrix.py` (+14 cases), `apps/web/tests/components/AgentStudentsPanel.test.tsx` (+1 case).

**Authentication/Authorization impact.** None changed; the staff refusals are now pinned in the matrix with their exact messages, an
unchanged record and no audit row.

**Security impact.** None changed. Recorded observation (spec §10): on `PATCH /crm/students/{id}` and `…/assign` a malformed body gets
`422` before the staff `403` (AGN-004 behaviour; reveals nothing) — a follow-up candidate, not changed here.

**Reusable existing modules.** `agn004_helpers.mk_record`, `RECORDS`; the matrix's `_world` / `_call` / `_fill`; the panel test's
`item` / `page` / `res`.

**Dependencies.** AGN-003, AGN-004 (both COMPLETE on `main`).

**Acceptance criteria** (verbatim from `docs/superpowers/specs/2026-10-01-agn-005-staff-matrix-gap-design.md` §6).
- **AGN-005-AC01** On a student assigned to them, staff get `403` with the exact message on archive, unarchive and assign; the record is
  unchanged and no `agent_student.*` audit row is written.
- **AGN-005-AC02** Staff create (`201`), list, open and edit (`200`) their assigned student with no login through `crm/students`.
- **AGN-005-AC03** A Master succeeds on every AC02 row plus archive, unarchive and assign (`200`).
- **AGN-005-AC04** In `RBAC_MATRIX.md` §2.8 no §6 row that has an agent route is N/A; only Edit Application, Change Application Status,
  Staff Performance and CRM Settings remain N/A.
- **AGN-005-AC05** No change under `apps/api/app`, `apps/api/alembic`, `apps/web/components`, `apps/web/lib` or `apps/web/app`; every
  pre-existing `test_agn_003_matrix.py` and `AgentStudentsPanel.test.tsx` case is unchanged and passing; the lite regression set is green.
  *Superseded in part by the owner's "Fix them" (2026-10-01): see "Browser QA fixes" below.*
- **AGN-005-AC06** Staff who show archived students see no Unarchive control on an archived card (the UI follows the server's `403`).

**Regression risks.** Low: the matrix's `_world` builds two extra students for every case (no email/phone, so no duplicate clash).

**Complexity:** Small. **Risk:** Low.

**Browser QA fixes (owner, in-session 2026-10-01: "Fix them").** The first browser QA pass
(`docs/quality/AGN-005_BROWSER_QA_2026-10-01.md`) found four issues in AGN-004 behaviour; the owner had them fixed on this branch,
which widens AGN-005 beyond tests and docs for these four only:
- **QA5-01** An agency student's phone follows the school mobile rule (7–20 characters of digits, spaces, `+ - ( )`, at least 7 digits),
  server `422 invalid_phone` and the same message in the form; a phone saved before the rule survives edits of other fields. API
  contract updated (`API_CONTRACT.md` AGN-004 rows). Deliberate test change: `test_agn_004_students.py::
  test_phone_formats_match_on_digits_only` now expects `422` for a 4-digit phone (was `201`).
- **QA5-02** The new-student form focuses Full name when it opens; focus returns to Add student after Cancel or a save.
- **QA5-03** Staff read "Students assigned to you, with or without a login…".
- **QA5-05** A non-agency user who can open the page (Super Admin) sees a note instead of a panel whose every action is refused.

**Status (2026-10-01): IMPLEMENTED, NOT COMPLETE** on `feature/agn-005-staff-permission-matrix` — evidence in `docs/quality/RTM.md`
(AGN-005 row). Browser QA done, the four fixes re-checked, and a final browser verification at `15d4047` passed (AC01, AC02, AC03,
AC06 PASS; AC04, AC05 not browser-testable). The owner waived the independent Codex review (2026-10-01). Remaining before COMPLETE:
the owner's full backend suite run (standing 4–5-story cadence) and the merge.

## AGN-006 — Agent Student Counseling Record

**Title.** Record and read back a student's counseling outcome (EVID-015 §5 Step 2).

**Business requirement.** The owner's `AGN-006` statement (in-session, 2026-10-01): "record counseling completed, career interest,
course preference, country preference, budget and remarks"; acceptance: "save and read back the record; a negative budget → 422;
out-of-scope → 404." Source: `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 "Staff Student Journey" STEP 2.
Decided as `DEC-SCOPE-048` (C1–C9).

**Existing behavior.** AGN-004 stores Step 1 (personal, academic, contact, preferred country/course/intake) for agency students; there
was no counseling record.

**Expected behavior.**
- One counseling record per agency student with no login, in a new table `agent_student_counseling` (migration
  `0055_agent_student_counseling`, create-table only; downgrade refuses while records exist).
- `PUT /workflows/overseas/agent/crm/students/{id}/counseling` replaces the record (idempotent; an unchanged save writes no audit row);
  the student detail carries `counseling` (null until the first save). Budget is an amount (0–99,999,999.99, 2 dp) + currency.
- The Master and the assigned staff member may save; out of scope → `404`; a student with a login or an archived student → `409`;
  invalid input → `422`. Completion is stamped (when, by whom) by the server.
- Audit `agent_student.counseling` with field names only; shown in AGN-021 Staff Activity as "Recorded counseling" (names, no values).
- The student detail panel shows a Counseling section (empty / record / form; one form open at a time; leave prompt; 320 px).

**User roles affected.** `agent` (Master and staff).

**Frontend / backend / database / API / integration impact.** Backend: `models.py`, `schemas.py`, `services/agent_students.py`,
`api/agent_students.py`, `services/staff_activity.py`, migration 0055. Frontend: `lib/agentStudents.ts`, `lib/agentStaff.ts`, new
`AgentStudentCounselingCard.tsx` / `AgentStudentCounselingForm.tsx`, `AgentStudentDetailPanel.tsx`, `AgentStudentsPanel.tsx` (notice).
No integration.

**Authentication/Authorization impact.** Reuses the AGN-004 gate, organisation-then-row lock and scope (404 before any other check).

**Security impact.** Reviewed with security-and-hardening (spec §8): no new auth path; IDOR closed by the scoped `WHERE`; `extra="forbid"`;
budget/remarks never in logs, audit or Staff Activity; no rate limit added (residual, `PRD_OPEN_ITEMS.md`).

**Acceptance criteria** (verbatim from `docs/superpowers/specs/2026-10-01-agn-006-counseling-record-design.md` §7).
- **AGN-006-AC01** A Master saves all six fields; `GET /students/{id}` returns them exactly (`budget_amount` "2500000.00", currency).
- **AGN-006-AC02** The assigned staff member can save; staff on another staff member's / an unassigned student, another agency's student, an unknown id → 404 and nothing written.
- **AGN-006-AC03** 422 for: negative budget, > 99,999,999.99, 3 decimals, NaN, unknown currency, currency without amount, unknown key, missing `counseling_completed`, text over its limit, NUL byte; amount without currency stores INR.
- **AGN-006-AC04** Student with a login → 409; archived student → 409; nothing written.
- **AGN-006-AC05** Completed stamp: no→yes sets `completed_at`/`completed_by`; yes→yes keeps them; →no clears them.
- **AGN-006-AC06** One `agent_student.counseling` audit row with `{fields}` names only (no values); a no-op save writes none; Staff Activity lists it with field names and no budget/remarks.
- **AGN-006-AC07** Non-agent, `super_admin`, pending / suspended organisation → 403.
- **AGN-006-AC08** PUT replaces: an omitted optional field becomes null; `counseling` is null before the first save; the list item shape is unchanged; the PATCH contract is unchanged.
- **AGN-006-AC09** Migration upgrade → downgrade → upgrade keeps existing rows, single head; downgrade refuses while a counseling record exists; the DB rejects a negative budget, a currency without an amount and an unknown currency written directly.
- **AGN-006-AC10** UI: empty / view / form states; buttons hidden for a login or archived student and while the student form is open; client errors send nothing and focus the field; currency not sent without an amount; unchanged Save sends nothing; 422 → field, 409 → alert, network → alert; success shows the record, the status message and focuses the heading; remarks `<script>` text renders literally; Escape does not close the panel while a form is open.
- **AGN-006-AC11** Browser: a Master records counseling, reloads and sees it; a negative budget shows the field error.
- **AGN-006-AC12** Security: a numeric-string budget is accepted; the response never contains the counseling row id or user ids; a staff member cannot write by guessing another student's id (404, nothing written, no audit).

**Regression risks.** The additive `counseling` key on every student-detail response (AGN-004/005 tests green); the detail panel's
Escape/focus behaviour (component tests green); migration numbering against parallel branches.

**Complexity:** Medium. **Risk:** Medium.

**Status (2026-10-02): COMPLETE** on `feature/agn-006-counseling-record` (verified at `d05fc15`; evidence in `docs/quality/RTM.md`,
AGN-006 row): AC01–AC12 met; lite backend set 286 passed; web 142 files / 1479 passed; `tsc`, lint, production build pass;
Playwright 7/7; browser QA done with QA6-01/02/03 fixed and re-verified. The independent Codex review was waived by the owner; the
owner's full backend suite is deferred to their batch run after the next few enhancements (2026-10-02, the AGN-021 precedent).
Remaining: the merge (recheck `main` for migration `0055` / `DEC-SCOPE-048` first). Deferred minors and open questions:
`PRD_OPEN_ITEMS.md` rows 81–83 and the review minors listed in `docs/quality/RTM.md`.

## AGN-008 — Agent Applications: Create, Edit, View and Change Status, With Application ID, Submission Date and Deadlines

**Title.** Let an agency Master, and Staff for their assigned students, manage overseas applications for agent students, including
students with no login, with a Staff sidebar filter group.

**Business requirement.** The owner's `AGN-008` statement (in-session, 2026-10-01): "create, edit, view, change status, application ID,
submission date and deadlines; Staff sidebar filters (§2, §4, §5)." Sources: `EVID-015` (`Agent CRM Functionalities.md`,
`DERIVED_BLUEPRINT`) §2 Applications, §4 Staff Sidebar, §5 Steps 5-6. Decision record: `DEC-SCOPE-050` (A1–A15, `EXPLICIT_APPROVAL`
in-session 2026-10-01/02).

**Existing behavior.** An agent can only create an application through the old `POST /workflows/overseas/applications` for a student with
a login; there is no agent edit, status change, Application ID, submission date or deadline, and about ten list/report/portal sites
inner-join `users` on `student_id`, so an application for a student with no login is invisible.

**Expected behavior.** New routes under `/workflows/overseas/agent/crm/applications` (create, list, detail, edit, forward-only status
change and withdraw); an agent Applications page with filters (Draft, Submitted, Offer received, Visa, Enrolled, Withdrawn) in the
sidebar for Master and Staff; the owner name is NULL-safe in every shared list. Agents never set `enrolled`.

**User roles affected.** `agent` (Master and Staff); `admin` and `university_rep` lists gain the agent-student applications; counselor
and admin endpoints refuse to revive a `withdrawn` application.

**Frontend / backend / database / API / integration impact.** Frontend: `AgentApplicationsSection`, `AgentApplicationsPanel`,
`AgentApplicationDetail`, edit and status forms, an extended create panel, sidebar `children` in `navigation.ts` and `PortalShell`.
Backend: `app/api/agent_applications.py`, `app/services/agent_applications.py`, schemas, `application_scope` widened for Staff, outer
joins in the shared lists. Database: migration `0057_agent_applications` (four nullable columns and one index). API: see
`API_CONTRACT.md` AGN-008. Integration: none new (no notification added).

**Authentication/Authorization impact.** Inline pattern (`agent_students._gate`, then `student_scope`/`application_scope` in the
`WHERE` clause); out-of-scope ids `404`; `super_admin`, counselor and university_rep `403`. AGN-003 matrix rows "Edit Application" and
"Change Application Status" are now enforced.

**Security impact.** Create throttle (A14), archived read-only (A15), `expected_status` precondition, `extra="forbid"` on every body,
response allowlists, audit in the same transaction with ids and field names only. Known limitations in `THREAT_MODEL.md` and
`SECURITY_CONTROLS.md`.

**Reusable existing modules.** `agent_students._gate`, `student_scope`, `application_scope`, `lock_active_org`, the `DEC-SCOPE-038` R1
audit-count throttle, `application_status_history`, the commission trigger, `SearchableSelect`, `lib/apiErrors`.

**Dependencies.** AGN-004, AGN-003, AGN-021, AGT-002, OVS-002/003/004, ENH-031, RPT-002.

**Acceptance criteria** (verbatim from `docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md` §8).
- **AGN-008-AC01** A Master creates an application for a student with no login and one with a login. The response is 201, `status = enquiry`, with one history row (`None → enquiry`), and the student's own portal shows it only when the student has a login.
- **AGN-008-AC02** Staff can create, edit and change status for an assigned student. For an unassigned student, or another org's student or application, the response is 404.
- **AGN-008-AC03** A duplicate (same student, university and course; status not withdrawn) returns 409. This includes an application made before this feature for a student with a login. After a withdrawal, the same combination can be created again (201).
- **AGN-008-AC04** Edit updates Application ID, the three dates, intake, course and next action. A course from another university returns 422. Changing the university returns 422. Editing a withdrawn application returns 409.
- **AGN-008-AC05** Forward status changes, including skips up to `status_tracking`, return 200 and write one history row each. Backward or same-stage changes return 422. An unknown status returns 422. `enrolled` returns 403. No commission row is ever created by an agent's status change.
- **AGN-008-AC06** Withdraw from any stage before `enrolled` returns 200 with a history row. After that, any edit or status change returns 409. Counselor `/advance` and the existing PATCH with `status` also return 409 on a withdrawn application.
- **AGN-008-AC07** Each filter (`draft`, `submitted`, `offer`, `visa`, `enrolled`, `withdrawn`, `all`) returns exactly the matching subset, within scope. Pagination totals are correct.
- **AGN-008-AC08** `/admin/applications`, the university_rep's `GET /workflows/overseas/applications`, and the rep and admin portal application sections list an application for a student with no login, with that student's name as owner.
- **AGN-008-AC09** No response crashes on a NULL `student_id`. This covers every endpoint and portal section listed in spec §5.6, plus inbound email matching. School-bridged rows stay excluded exactly where they are today.
- **AGN-008-AC10** When a counselor or admin later sets `enrolled`, the commission is accrued as today, and it appears in the agent and admin commission lists with the owner's name.
- **AGN-008-AC11** Each sidebar filter link shows the matching subset with `aria-current` on the active link. Staff and Masters both have the links. The mobile menu includes them.
- **AGN-008-AC12** The page shows correct loading, empty (unfiltered and filtered), error-with-retry, and write-error states. It has no horizontal scroll at 320px, and keyboard focus returns to the opener after actions.
- **AGN-008-AC13** Agent edit, advance and withdraw actions appear in AGN-021 staff activity with the student's name.
- **AGN-008-AC14** The 201st create by one agency within a rolling 24 hours returns 429 with `Retry-After`. Another agency is unaffected.
- **AGN-008-AC15** For an archived student's applications, create, edit, status change and withdraw return 409. Reads and listing still work.
- **AGN-008-AC16** A status change whose `expected_status` differs from the current status returns 409, and nothing changes.
- **AGN-008-AC17** The nine spec §7 abuse cases each return the stated code and leave no partial write: no history, audit or commission row.
- **AGN-008-AC18** Existing behaviour is preserved: OVS-002/003/004, AGT-002/003/004, SCH-010, UNI-001, RPT-002, ENH-031 and AGN-001/002/003/004/005/021 tests pass unchanged except the documented updates (spec §9); the old agent create path still works.

**Out of scope** (accepted by the owner, 2026-10-01): documents for no-login students; converting an AGN-007 shortlist entry; offer
details beyond the offer deadline; deadline reminders; new notifications on agent status change; agents setting `enrolled`; rejected,
waitlisted and deferred outcomes (`DEC-WF-001` stays open); backfilling `agent_student_id`.

**Regression risks.** Spec §10 (R1–R8): shared-list counts when rows are no longer dropped, wider Staff `application_scope`, shared
`PortalShell`/`navigation.ts`, ENH-031 picker ids, withdrawn guard on counselor/admin endpoints, nullable `student_id` in a list
response, merge anchors with AGN-006/007, the commission trigger.

**Complexity:** Large. **Risk:** High.

**Status (2026-10-02): COMPLETE** on `feature/agn-008-agent-applications` — completion verification in `docs/quality/RTM.md` (AGN-008
row). Codex review waived by the owner (2026-10-02). Outside COMPLETE, owner-side: the full backend suite (standing 4–5-story
cadence) and the merge to `main`. Browser QA pass 1 (QA8-01..13) is fixed, with owner rulings in `DEC-SCOPE-050` A16–A19 (reports: `.superpowers/sdd/2026-10-02-agn-008-agent-applications/qa-fix-*.md`, git-ignored, local only). Merge note (2026-10-02): `main` @ `3e06381` (`AGN-006`, `AGN-007`) merged in; `DEC-SCOPE-050` kept (free), `0057` re-chained after `0056_agent_shortlist`, the screen renumbered `SCR-AGT-010` (spec §12).

## AGN-014 — Commission is Master-only: Revenue on the Master dashboard and commission reports

**Title.** Agency commission Revenue and a filterable, exportable commission report for Masters (EVID-015 §2, §6).

**Business requirement.** The owner's `AGN-014` statement (in-session, 2026-10-02): "Commission is Master only (§6);
Commission/Revenue on the Master dashboard; commission reports"; acceptance: "existing commissions are visible to the migrated Master;
Staff → 403 on every commission route; the same-admin payout rules are unchanged." Source: `EVID-015` (`Agent CRM
Functionalities.md`, `DERIVED_BLUEPRINT`) §2 Dashboard "Commission / Revenue", §2 Reports "Commission reports", §6 "Commission ✅/❌".
Decided as `DEC-SCOPE-051` (R1–R7; provisional number).

**Existing behavior.** Commissions were already Master-only (`DEC-SCOPE-040` S1; AGN-003 matrix tests) and the `0046` backfill's
Masters already saw their older commissions. The Master dashboard showed "Claimable commission" and "Claims"; the Master reports page
one "Paid commission" row. There was no Revenue figure and no agent commission report.

**Expected behavior.**
- Master dashboard metric "Revenue" = total of `paid` commissions per currency (`INR 12,000`, `INR 12,000 · USD 500`, `INR 0`).
- `GET /workflows/overseas/agent/commissions/report?date_from&date_to` → totals and breakdowns by status (lifecycle order),
  university/country, country and intake, per currency; inclusive UTC days on the created date.
- `GET /workflows/overseas/agent/commissions/report.csv?date_from&date_to` → one row per commission, formula-safe cells,
  `attachment`, `no-store`.
- Order of checks: auth → agent of an active agency → Master → dates; staff get `403 "Only an agency Master can view commissions"`
  before any `422`.
- The agent Reports page shows Masters a Commission report panel (filters, loading/empty/error states, CSV of the applied range).

**User roles affected.** `agent` (Master: new figure, routes and panel; staff: refused, unchanged pages).

**Frontend / backend / database / API / integration impact.** Backend: `api/workflows.py` (two routes, one guarded query helper),
`schemas.py` (`CommissionReportOut` and rows), `services/portal.py` (one metric). Frontend: new `lib/agentCommissionReport.ts`,
`AgentCommissionReportPanel.tsx`; `ReportDownloadButton.tsx` (optional `contentType`/`busyLabel`, PDF defaults); `WorkflowPanel.tsx`
(mount). No migration, no dependency, no integration.

**Authentication/Authorization impact.** Reuses `_require` + `_require_agent_master` and the `org_member_ids` scope; no new helper.

**Security impact.** Spec §8: staff refused before any query; cross-agency rows excluded by scope; dates parsed after authorization;
CSV cells through `_safe_cell`; `Cache-Control: private, no-store`. No audit row on reads/exports (R7); one structured
`agent_commission_report` log line per request (actor, organisation, format, row count, range).

**Acceptance criteria** (verbatim from `docs/superpowers/specs/2026-10-02-agn-014-commission-master-reports-design.md` §9).
- **AGN-014-AC01** A Master created by the real `0046` backfill sees the old commission in the list, the dashboard Revenue, the report and the CSV.
- **AGN-014-AC02** Staff → `403` on list, claim, report, report.csv and the portal `commissions` page; `403` (not `422`) with invalid dates.
- **AGN-014-AC03** Same-admin payout rules unchanged (`test_agt_004_commission_payout.py` passes unedited).
- **AGN-014-AC04** Master dashboard Revenue = paid total per currency; `INR 0` when nothing is paid; other agencies excluded; staff dashboard has no Revenue and no "commission" wording.
- **AGN-014-AC05** Report breakdowns correct per currency; lifecycle status order; staff-created application's commission included; other agency excluded.
- **AGN-014-AC06** Created-date filter inclusive at both UTC-day boundaries; optional bounds; `date_to < date_from` → `422`; malformed date → `422`.
- **AGN-014-AC07** CSV: header + one row per commission, same filter, `_safe_cell` applied, `text/csv` attachment, `no-store`, header-only when empty.
- **AGN-014-AC08** New routes: unauthenticated → `401`; non-agent → `403`; suspended organisation → `403`.
- **AGN-014-AC09** Panel: loading, empty, error (401/403/5xx/network), data; client range error sends no request; stale response ignored; CSV URL follows applied filters; not mounted for staff.
- **AGN-014-AC10** `ReportDownloadButton` PDF behavior unchanged; CSV accepted with `contentType="text/csv"`.
- **AGN-014-AC11** End to end: Master sees Revenue, filters the report, downloads the CSV; staff get the 403 card on `/overseas/agent/commissions` and no Revenue.

**Regression risks.** Commission wording leaking to staff pages (guarded by `test_agn_002_qa_messages.py`); PDF downloads (defaults
kept); the payout rule (`admin.py` untouched).

**Complexity:** Medium. **Risk:** Low–Medium.

**Status (2026-10-02): COMPLETE** on `feature/agn-014-commission-master-only` (verified at `850a9f5`, after merging `main` with
AGN-007; evidence in `docs/quality/RTM.md`, AGN-014 row): AC01–AC11 met; lite backend set 274 passed; web 148 files / 1599 passed;
`tsc`, lint and the production build pass; Playwright 12/12; browser QA done with QA14-01…10 fixed and re-verified. The independent
Codex review was waived by the owner; the full backend suite stays with the owner's batch cadence. Remaining: the merge into `main`
(`main` with `AGN-007` and `AGN-008` merged in 2026-10-02; `DEC-SCOPE-051` was still free there).

## AGN-009 — Agent Documents: Upload, Download, Verify, Reject, Request Additional, History

**Business requirement.** The owner's `AGN-009` statement (in-session, 2026-10-02): "§2 Documents and §5 Step 4 document types; Staff
sidebar Pending/Uploaded/Additional; §6: Staff verify is optional and Staff cannot reject." Decision `DEC-SCOPE-052` (G1–G9). Source
`EVID-015` (`DERIVED_BLUEPRINT`) §2, §4, §5 Step 4, §6. Design spec `docs/superpowers/specs/2026-10-02-agn-009-agent-documents-design.md`;
plan `docs/superpowers/plans/2026-10-02-agn-009-agent-documents.md`.

**Scope.** Documents owned by an agency record (students with or without a login); fixed types + Other; server-stored files (PDF, JPEG,
PNG by bytes); replace (back to pending, old file kept); requests ("Additional") fulfilled by an upload made against them; per-document
history; a reason required when an agent rejects or asks for changes; Pending / Uploaded / Additional sidebar views. Migration
`0058_agent_documents`. Dependencies: AGN-003, AGN-004, AGN-008.

**Acceptance criteria** (owner's statement):
- **AGN-009-AC01** Upload → `pending`.
- **AGN-009-AC02** Verify/reject per the §6 matrix: Master verified/rejected/changes required; Staff verified only, with the Verify toggle.
- **AGN-009-AC03** Reject (or changes required) without a reason → `422` (agents; Staff get `403` first).
- **AGN-009-AC04** A request shows under "Additional" until an upload fulfils it.
- **AGN-009-AC05** History lists every event in order.
- **AGN-009-AC06** An out-of-scope download → `404`/`403`.
- **AGN-009-AC07** Existing student/counselor document flows unchanged.

**Status (2026-10-02): IMPLEMENTED, NOT COMPLETE** on `feature/agn-009-agent-documents`. Lite test sets pass (see `RTM.md` AGN-009 row).
Pending, owner-side: browser validation, the independent Codex review, the full backend/web/E2E suites, the merge.
## AGN-017 — Agency Notifications and Deadline Reminders

**Title.** Tell the right agency member, in-app and by email, when something about their student changes, and remind them daily of
upcoming deadlines and overdue tasks.

**Business requirement.** The owner's `AGN-017` statement (in-session, 2026-10-02): "Notifications" (§4); "Monitor deadlines" (§2).
Acceptance: "each event produces exactly one notification to the right person; reminders are not sent twice for the same deadline/day; a
failed email is recorded, never raised." Source: `EVID-015` (`DERIVED_BLUEPRINT`); channels `DEC-SCOPE-035` D19. Decision record:
`DEC-SCOPE-058` (N1–N10, `EXPLICIT_APPROVAL` in-session 2026-10-02).

**Existing behavior.** No agency member was notified of assignments, document requests/rejections, status changes or new tasks; no
scheduled job besides the ENH-014 delivery sweeper.

**Expected behavior.** Notices on assignment (new assignee only), document request, document rejected / changes required, status change
(agency or EduSphere actor), enrollment (no double notice with "Commission estimated"), task created by someone else. Recipient: the active
assignee, else the active Masters; never the actor. A daily 08:00 IST job: deadline reminders at 3/1/0 days and one overdue-task digest per
recipient per day, idempotent by `notifications.dedupe_key`. A Notifications page (Master and Staff) and an unread badge. Spec:
`docs/superpowers/specs/2026-10-02-agn-017-notifications-design.md`; plan `docs/superpowers/plans/2026-10-02-agn-017-notifications.md`.

**Roles.** Agency Master and Staff receive; students receive nothing new (D19).

**Acceptance criteria.** Spec §10 AC1–AC10.

**Regression risks.** Spec §12: shared `workflows.py` verify/PATCH/advance (additive hooks; students' notices unchanged), the enrollment
commission notice, the first crontab beat entry, `PortalShell`/`NavItem` (optional `badge`), every agency page now also reads the unread
count, the alembic head (`0064`).

**Complexity:** Medium. **Risk:** Medium.

**Status (2026-10-03): COMPLETE (AGN-017 scope; evidence below)** on `feature/agn-017-notifications`. Lite tests only, per the owner (the AGN-017 files
plus the touched features' files). Browser QA done (`docs/quality/AGN-017_BROWSER_QA_2026-10-02.md`: QA17-01/03/04/05/06 fixed and
re-verified; QA17-02 kept as designed, `DEC-SCOPE-058` N11); e2e `agn-017-notifications.spec.ts` 2/2. Codex review waived by the owner.

**Verification before completion (2026-10-03, fresh runs; final code `2a49676`).** Backend: 90 files (`test_agn_*`, `test_agt_*`,
`test_enh_014_*`, NOT-001, SCH-007, OVS-003/004/005, ENH-005 approve, ENH-023) 1229 passed / 1 failed — the failure,
`test_enh_023_tier_change.py::test_failing_email_never_fails_or_undoes_the_tier_change`, is **pre-existing and order-dependent**: it
fails after any migration test (alembic `env.py` `fileConfig` disables existing loggers, so its `caplog` sees nothing), reproduced on base
`e0395d6` with `test_agn_013_migration.py`; it passes alone and in the 188-test run without the migration files. After the type-only fix,
the 20 files that touch `agent_notifications.py` 209 passed; `alembic heads` = `0061_agent_notifications`; ruff clean on every changed
Python file; mypy 283 errors = the base's 283, none in AGN-017 code; `alembic check` drift = two pre-existing indexes only. Web: 168/168
test files (one AGN-017 omission fixed: `navigation.agent.test.ts` now lists Notifications), `tsc` 0, `npm run lint` 0 errors (31
pre-existing warnings; `--max-warnings=0` on AGN-017 files), `npm run build` exit 0 (88/88). Playwright on stack `agn017qa`: AGN-017, 016,
013, 009, 008, 004, ENH-005, ENH-023, SCH-007 — 22 passed (`--timeout=60000`, QA-grown demo agency); AGN-017 2/2 again on the final images.
Browser Use on the final images: live event → badge 9→10, open → 9 on the destination, 0 px overflow at 1280/375, signed-out redirect,
role refusal, Super Admin note without form, no console/network errors; daily job re-run 0 created / 2 duplicates; deliveries email-only.
Diff: 42 files, all AGN-017; no skipped/focused tests, debug code or secrets. **Status: COMPLETE for AGN-017's scope**; the owner's full
suite will show the pre-existing ENH-023 ordering failure above (not AGN-017's; recorded for its owner).

## AGN-016 — Agent Tasks and Follow-ups, "Pending Actions" KPI

**Title.** Let an agency Master, and Staff for their assigned students, record follow-up tasks on agency students and see what is open
and overdue; add "Pending actions" to the agent dashboard.

**Business requirement.** The owner's `AGN-016` statement (in-session, 2026-10-02): "Tasks & Follow-ups" (§4); "Pending Actions" KPI
(§2). Source: `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`), which names the two items only. Decision record:
`DEC-SCOPE-053` (T1–T8, `EXPLICIT_APPROVAL` in-session 2026-10-02; renumbered from `051` on merging `main` @ `d371865`).

**Existing behavior.** Only `OverseasApplication.next_action` free text; no task entity, no pending-actions count.

**Expected behavior.** Table `agent_tasks` owned only through the student (T1). Routes under `/workflows/overseas/agent/crm/tasks`:
list (`view` open/overdue/done/cancelled/all, `student`), create, read, PATCH (edit, or `status` done/cancelled alone). A Tasks page
(both roles), a Tasks section in the student detail, the dashboard metric, and task work in AGN-021 activity. Spec:
`docs/superpowers/specs/2026-10-02-agn-016-tasks-followups-design.md`; plan `docs/superpowers/plans/2026-10-02-agn-016-tasks-followups.md`.

**Roles.** Agency Master (whole agency), agency Staff (assigned students only). Not super_admin or other roles (403).

**Acceptance criteria.** Spec §10 `AGN-016-AC01`…`AC13`: create per role and student type; scope (404 outside, 403 for other roles);
reassignment moves tasks; overdue definition; edit and close; closed and archived read-only (409); application link (422); validation
(422); concurrent closes (one 200, one 409); KPI per role; audit/log without free text; UI states, keyboard and 320 px; per-student cap.

**Regression risks.** Spec §11: `portal._agent` dashboard (one metric added after "Applications"), `AgentStudentDetailPanel` (an extra
fetch; two existing unit tests now answer the tasks URL like the shortlist's), `searchStudents`/`assignedText` moved to
`lib/agentStudents.ts` (behaviour unchanged), `lib/navigation.ts` (Tasks after Documents), `STAFF_ACTIVITY_ACTIONS`, the alembic head
(parallel `AGN-009`).

**Complexity:** Medium. **Risk:** Medium.

**Status (2026-10-02): IMPLEMENTED, NOT COMPLETE** on `feature/agn-016-tasks-followups`. Lite tests only, per the owner: 79 backend
AGN-016 tests plus the four affected existing files (`test_agn_004_staff_scope`, `test_agn_001_team`, `test_agn_008_dashboard`,
`test_agn_021_activity`), web typecheck, zero-warning lint, and 104 unit tests across 11 files. The e2e spec `agn-016-tasks.spec.ts` passed
3/3 against the isolated stack (2026-10-02). Outstanding before COMPLETE: the full suites (owner, separate session).

**Verification before completion (2026-10-02, fresh runs at the final commit).** Backend: every `test_agn_*`/`test_agt_*` file
784 passed; AGN-016 files + AGN-007 shortlist 97 passed after the last (type-only) change. Web: `tsc` clean, `npm run lint` 0 errors
(31 warnings, identical count on the base image), 32 agent-related unit-test files 348 passed, `next build` exit 0. mypy: 283 errors =
the base commit's count, none in AGN-016 files (6 AGN-016 type errors were found here and fixed). `alembic heads` = `0059_agent_tasks`
only; `alembic check` drift is the base's (two pre-existing indexes), none on `agent_tasks`. Playwright: AGN-016 + AGN-004 + AGN-008
specs 12/12 on an idle machine; two neighbour tests failed intermittently in 2 of 4 loaded runs, not reproduced in 3 alternating
base-vs-branch runs (9/9 each side). Browser: Master 31/31, Staff/roles 13/13, re-check 6/6, Super Admin note. Diff: 45 files, all
AGN-016; no skipped/focused tests, debug code or secrets. **Status: VERIFIED — COMPLETE once the owner's full-suite run is green.**

**Browser QA (2026-10-02, isolated `agn016qa` stack, headless Chromium).** Pass 1 covered the 20-point checklist for Master, both
Staff, signed-out, wrong roles, Super Admin and another agency: no Critical/High issues. Findings, all fixed and re-verified in pass 2:
QA16-01 (Super Admin saw "Workspace not found" — now the section's note, the AGN-008 QA8-09 precedent), QA16-02 (the Student picker's
error was not on the picker — now its own linked `aria-invalid` message), QA16-03 (an archived student's open task now says why it is
read-only), QA16-04 (the closing time now carries its zone), QA16-05 (the open form has a visible "New task" heading). Codex review
waived by the owner (2026-10-02).

## AGN-013 — Enrollment confirmation + commission trigger (Step 9)

**Title.** An agency Master confirms an application's enrollment; the commission is estimated exactly once (EVID-015 §5 Step 9).

**Business requirement.** The owner's `AGN-013` statement (in-session, 2026-10-02): "enrollment confirmed, university, course, intake,
enrollment date, university student ID, final status ENROLLED"; acceptance: "enrolling creates exactly one estimated commission for the
org; re-saving does not duplicate it; an enrollment date is required; a future date beyond intake is flagged (a warning, not blocked)."
Source: `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 Step 9; `AGENT_CRM_BACKLOG.md` ang-013. Decided as
`DEC-SCOPE-054` (E1–E8; provisional number).

**Existing behavior.** Only a counselor, admin or university rep could set `enrolled` (`DEC-SCOPE-050` A4); the AGT-003 trigger then
created one `estimated` commission keyed to `application.agent_id`. No enrollment date, university student ID or confirmation was stored.

**Expected behavior.**
- `PUT /workflows/overseas/agent/crm/applications/{id}/enrollment` (Master only): from `offer`, `visa_documentation` or
  `status_tracking` it sets `enrolled`, the date, the optional student ID and `enrollment_confirmed_at`, writes one history row and runs
  the unchanged AGT-003 trigger; once `enrolled` it corrects the date and student ID (audited, no history, no commission).
- `enrollment_check` on the detail: `after_intake` (future date after the intake month) or `intake_unrecognised` (free-text intake not
  read as a month and year) — a warning, never a block.
- The application detail gains an Enrollment section: Masters confirm (with an explicit confirmation step) or correct; Staff read.

**User roles affected.** `agent` Master (new action), Staff (read-only section; `403` on the route); `overseas_admin` (sees the
estimated commission as before).

**Frontend / backend / database / API / integration impact.** Backend: `api/agent_applications.py` (one route), `services/agent_applications.py`
(`intake_end`, `enrollment_check`, detail fields), `schemas.py` (`AgentApplicationEnrollment`), `models.py` + migration
`0060_agent_app_enrollment` (three nullable columns). Frontend: `lib/agentApplications.ts`, new `AgentApplicationEnrollment.tsx`,
`AgentApplicationDetail.tsx` / `AgentApplicationsPanel.tsx` / `AgentApplicationsSection.tsx` (`isMaster`). No dependency; the existing
"Commission estimated" notification to the agency's Masters is reused.

**Authentication/Authorization impact.** `_gate` + `is_agent_staff` (`403` before any load); scope in the `WHERE` (`404` across agencies).

**Security impact.** Spec §6: no role escalation through the body (`extra="forbid"`); organisation then row lock; required
`expected_status`; one transaction with history, commission and audit; the student ID and notes never logged or audited.

**Acceptance criteria** (from `docs/superpowers/specs/2026-10-02-agn-013-enrollment-confirmation-design.md` §7).
- **AGN-013-AC01** Master confirms from offer / visa documentation / status tracking → `enrolled`, details set, one history row, one `estimated` commission visible to the Masters.
- **AGN-013-AC02** Re-saving → still one commission, no new history row; changes audited as `enrollment_update`.
- **AGN-013-AC03** Missing `enrollment_date` → `422`, nothing written.
- **AGN-013-AC04** `after_intake` / `intake_unrecognised` / `null` flags; the save succeeds.
- **AGN-013-AC05** Staff `403`; other agency `404`; archived / withdrawn / stale `409`; pre-offer `422`; unknown field `422`; nothing written.
- **AGN-013-AC06** Counselor-enrolled application: a Master adds details; no commission from that call.
- **AGN-013-AC07** Concurrent confirmations → one `200`, one `409`, one commission; a counselor landing first → the agency call is `409`.
- **AGN-013-AC08** `POST …/status` still refuses `enrolled` (A4 unchanged).
- **AGN-013-AC09** UI: Master confirm with a confirmation step, Staff read-only, enrolled view with badge and warning, 422 keeps input, keyboard and labels.

**Regression risks.** A4 (pinned by AC08 and `test_agn_008_status.py`), commission duplication (locks + trigger guard + `UNIQUE`), the
detail allowlist (additive only), the migration chain (`0058` may collide with parallel AGN branches).

**Complexity:** Medium. **Risk:** High (financial trigger).

**Status (2026-10-02, final verification @ `d871cdd`): VERIFIED, NOT COMPLETE.** Requirement and AC01–AC09 met with fresh evidence
(`docs/quality/RTM.md`, AGN-013 row); merged `main` @ `9adcbca` (migration now `0060_agent_app_enrollment`, decision `DEC-SCOPE-054`).
QA13-03…09 fixed and re-verified (`194e564`); the AGN-014 dashboard-order test (failing on `main` after AGN-016) updated. Only open item,
for the owner: the Browser Use gate (tool input fails after in-app navigation here; Playwright used instead). Earlier status: **IMPLEMENTED** on `feature/agn-013-enrollment-confirmation` (evidence in `docs/quality/RTM.md`,
AGN-013 row): lite backend set 200 passed; web lite set 52 passed; `tsc` and eslint clean. Browser QA first pass done
(`docs/quality/AGN-013_BROWSER_QA_2026-10-02.md`; Playwright `agn-013` 2/2); QA13-01 (UX repetition) and QA13-02 fixed. Pending:
the independent Codex review and the owner's full suites.

## AGN-010 — Agent Offer Details (Step 6)

**Title.** Let an agency Master, and Staff for their assigned students, record the offer on an agency application: conditional or
unconditional, offer date, deadline, conditions and the offer letter; count offers correctly on the agent dashboard and Reports.

**Business requirement.** Backlog item ang-010 (`AGENT_CRM_BACKLOG.md`), source `EVID-015` (`Agent CRM Functionalities.md`,
`DERIVED_BLUEPRINT`) §5 Step 6. Decision record: `DEC-SCOPE-056` (O1–O7, `EXPLICIT_APPROVAL` in-session 2026-10-02).

**Existing behavior.** Only an `offer_deadline` date (AGN-008) and the `offer` stage; the agent Reports "Offers" row counted only
`offer_received`/`accepted` (the §0 defect).

**Expected behavior.** Migration `0062_agent_offer_details` (four nullable columns). `PUT …/agent/crm/applications/{id}/offer` records
or replaces the one current offer, moves a pre-offer stage to `offer`, writes history and audit; an identical PUT writes nothing. The
detail gains `offer` and `offer_letters`; uploads accept "Offer letter" (bound to an application). An Offer block and form in the
application detail; "Offers" KPI after the commission metrics (Staff: after "Pending actions"); AGN-021 activity "Recorded an offer". Spec:
`docs/superpowers/specs/2026-10-02-agn-010-offer-details-design.md`; plan `docs/superpowers/plans/2026-10-02-agn-010-offer-details.md`.

**Roles.** Agency Master (whole agency), agency Staff (assigned students only). Not super_admin or other roles (403).

**Acceptance criteria.** Spec §8 `AGN-010-AC01`…`AC09`: deadline before offer date → 422 (PUT and PATCH); conditional needs conditions,
unconditional has none; a type switch is one history row naming both types and the removed conditions; stage sync and 409s; Offers
counts equal a hand count (incl. withdrawn-after-offer), staff scoped; scope/IDOR 404/422; identical PUT writes nothing;
`offer_letter_url` and non-agent counts unchanged; UI states, keyboard, focus and 320 px.

**Regression risks.** `portal._agent` (Reports row, one metric after the commission metrics), the AGN-008 PATCH (new 422), the AGN-009 upload
types, `AgentApplicationDetail` (one form at a time), `STAFF_ACTIVITY_ACTIONS`, the alembic head. Non-agent stale counts carried to
ang-018 (`RAID.md` I-48).

**Complexity:** Medium. **Risk:** Medium.

**Status (2026-10-02): IMPLEMENTED, NOT COMPLETE** on `feature/agn-010-offer-details`. Lite test sets green (see `RTM.md` AGN-010 row);
e2e `agn-010-offer-details.spec.ts` written, not run. Pending: browser validation, the owner's full suites, an independent Codex review.
The AGN-014 dashboard-order failure found earlier (`RAID.md` I-49) was fixed on `main` by AGN-013; after merging `main` @ `aad6b7c`
the "Offers" KPI follows the commission metrics so that order holds.
## AGN-012 — Visa for agent-managed applications (Step 8)

**Title.** An agency Master or Staff member runs the visa case of an application: document checklist, visa application date,
appointment, interview, stage and the authority's decision (EVID-015 §5 Step 8).

**Business requirement.** The owner's `AGN-012` statement (in-session, 2026-10-02): "visa documents, application date, appointment,
interview, status and decision"; acceptance: "a decision can be set only at stage decision; the interview date may not precede the
application date; the existing checklist rule blocks advancing past checklist with unverified documents." Source: `EVID-015`
(`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 Step 8; `AGENT_CRM_BACKLOG.md` ang-012. Decided as `DEC-SCOPE-057` (V1–V9;
drafted as `055`, renumbered on merging `main`, where `055` is BDM-001 and `056` is AGN-010).

**Existing behavior.** `VisaCase` (stages `checklist → documentation → interview_prep → tracking → decision`) is created and updated
by counselors and overseas admins only; agents get `403`. No application date, interview date or decision; the counselor create accepts
any starting stage; checklist items are free text matched to document types.

**Expected behavior.**
- `POST …/crm/applications/{id}/visa` starts a case at `checklist` from `offer`, `visa_documentation` or `status_tracking` (one per application).
- `PATCH …/crm/applications/{id}/visa` edits the dates (null clears), the checklist (at `checklist` only), moves forward (skips allowed;
  leaving `checklist` needs every item's newest attached document verified) and records the decision (`approved`/`refused`/`withdrawn`,
  only when already at `decision`; final).
- The application detail gains a `visa` block and a Visa section (start, edit, move with a skip confirmation, record decision with a
  confirmation; read-only when decided, withdrawn, archived or enrolled). The visa case never moves the application stage.

**User roles affected.** `agent` Master and Staff (Staff on assigned students); counselor, overseas admin, student and school views unchanged.

**Frontend / backend / database / API / integration impact.** Backend: new `services/agent_visa.py` (stage list and disclaimer moved
here unchanged from `api/workflows.py`, which imports them), `api/agent_applications.py` (two routes), `services/agent_applications.py`
(`visa` detail key), `schemas.py` (`AgentVisaStart`, `AgentVisaUpdate`), `services/staff_activity.py` (four actions), `models.py` +
migration `0063_agent_visa_details` (four nullable `visa_cases` columns + `ck_visa_cases_decision`). Frontend: `lib/agentApplications.ts`,
new `AgentApplicationVisa.tsx` and `AgentVisaDetailsForm.tsx`, `AgentApplicationDetail.tsx` (one section form at a time). No dependency,
no notification, no integration.

**Authentication/Authorization impact.** `_gate` (agent, overseas, active approved organisation; others `403`); scope through
`load_scoped` (`404` across agencies and for Staff on unassigned students); organisation then application row lock.

**Security impact.** Spec §10.3: `extra="forbid"` bodies, enum stage/decision/checklist values, dates 2000–2100; the case is read by
application id only (no client-supplied case id); one transaction per write with its audit row; logs carry ids and stages only (never
the decision or a date); the AGN-021 activity view shows field names only. No rate limit added (owner approval needed; writes are bounded).

**Acceptance criteria** (spec §7).
- **AGN-012-AC1** A decision only when already at `decision` → else `422`, nothing written.
- **AGN-012-AC2** Interview before the visa application date → `422` on `interview_date`; same day and either alone accepted.
- **AGN-012-AC3** Leaving `checklist` with an item whose newest attached document is not verified → `422` naming it; passes once all are verified.
- **AGN-012-AC4** A case starts at `checklist`; forward-only moves, skips allowed; backward/same `422`.
- **AGN-012-AC5** A recorded decision is final (`409`).
- **AGN-012-AC6** Start from an offer onwards (`422`) and only once (`409`).
- **AGN-012-AC7** Withdrawn/enrolled application or archived student `409`; stale screen or missing case `409`.
- **AGN-012-AC8** Master: organisation; Staff: assigned only; other agency/unassigned `404`; non-agents `403`; anonymous `401`.
- **AGN-012-AC9** Concurrent writes serialised on the application row: one case; a queued stale advance `409`.
- **AGN-012-AC10** Existing visa routes and responses, the list, the status and enrollment routes unchanged.
- **AGN-012-AC11** UI states, field errors, focus, one section form at a time, 320 px.
- **AGN-012-AC12** No decision or date in application logs.

**Regression risks.** `visa_cases` readers (portal, reports, school views) — additive nullable columns; the moved constants (pinned by
`test_agn_012_schemas.py` and `test_visa_001/003`); `AgentApplicationDetail` form gating (AGN-008/013 component tests green); the
migration chain (0061 may collide with AGN-010).

**Complexity:** Medium. **Risk:** Medium.

**Status (2026-10-03): VERIFIED, NOT COMPLETE** on `feature/agn-012-agent-visa` (evidence in `docs/quality/RTM.md`, AGN-012 row).
`main` merged (BDM-001, AGN-010): migration now `0063_agent_visa_details`, decision `DEC-SCOPE-057`. Browser QA done
(`docs/quality/AGN-012_BROWSER_QA_2026-10-02.md`; Playwright `agn-012` 2/2). Only open item, for the owner: the Browser Use gate (the
tool is not available here; Playwright Chromium used). Codex review waived by the owner; full suites are the owner's.

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
| ENH-020 | Audit-first: confirm whether this duplicates an existing Overseas-domain capability before any Decision ID is even drafted | **Resolved 2026-10-01: `DEC-SCOPE-045`** (audit: no Overseas duplicate) |
| ENH-022 | `DEC-SCOPE-027` — enforcement strictness (hard `403` vs. soft warning) for out-of-tier or expired-partnership access | **Resolved 2026-09-23:** hard `403`, expired = no tier (D1–D12, `PRODUCT_DECISION_REGISTER.md`) |
| ENH-023 | `DEC-SCOPE-0xx` — downgrade policy for in-flight Platinum-tier commitments (grandfather / wind-down / immediate) | None exists |
| ENH-010 | `DEC-SCOPE-025` — "School Master" (`School CRM.md` Part B §2) = `school_coordinator`; activate/deactivate scope mapping proposed, drafted 2026-09-22 | Drafted, `UNCONFIRMED` |
| ENH-011, ENH-012, ENH-013, ENH-015, ENH-017, ENH-018, ENH-019, ENH-021, ENH-024, ENH-026, ENH-027, ENH-028, ENH-029, ENH-030 | None structurally required — each operates within already-confirmed School-domain scope (`DEC-SCOPE-011/012/013/017`) as a completion/extension, not a new scope question. ENH-026/ENH-027 additionally need a *design* choice (shared shape for "Recommended..."/"Career recommendations" fields); ENH-028's batch-size limit and ENH-030's session-vs-period granularity are also design, not scope, questions | N/A |
| ENH-016 | None — corrected in Revision 3 to a narrower scope entirely within already-confirmed `DEC-SCOPE-017` | N/A |
| AGN-001 | `DEC-SCOPE-038` — tenant model, Master count, codes, migration, org status, notifications | **Resolved 2026-09-28** (D1–D13, `EXPLICIT_APPROVAL` in-session) |
| AGN-002 | `DEC-SCOPE-040` — staff access, model, reset, fields/limits, activation, tenancy/audit | **Resolved 2026-09-30** (S1–S6, `EXPLICIT_APPROVAL` in-session) |
| AGN-004 | `DEC-SCOPE-042` — students with no login, staff assignment, archive, duplicate warning, relation to AGN-002 | **Resolved 2026-09-30** (D1, D3–D5, D7, D8, G1–G5, `EXPLICIT_APPROVAL` in-session; number provisional) |
| AGN-003 | `DEC-SCOPE-044` — optional rows, toggle granularity, matrix reach, student scope, agent review, staff outcome | **Resolved 2026-10-01** (P1–P6 `EXPLICIT_APPROVAL` in-session; P7–P9 design assumptions) |
| AGN-021 | `DEC-SCOPE-046` — what counts as activity, viewers, detail, freshness, source | **Resolved 2026-10-01** (A1–A5, `EXPLICIT_APPROVAL` in-session) |
| AGN-005 | None — scope (tests + docs), Delete Student = archive/unarchive, test placement, and the QA5-01 phone rule / QA5-05 note set by the owner in-session 2026-10-01 | N/A |
| AGN-006 | `DEC-SCOPE-048` — storage, budget, separate preferences, access, completed stamp, API, activity, leave prompt | **Resolved 2026-10-01** (C1–C9, `EXPLICIT_APPROVAL` in-session; number provisional) |
| AGN-008 | `DEC-SCOPE-050` — statuses and withdrawn, Application ID, dates, agent status limits, link to the agency student, visibility, sidebar filters, throttle, archived read-only | **Resolved 2026-10-01/02** (A1–A15, `EXPLICIT_APPROVAL` in-session). `DEC-SCOPE-036` "submitted" stays `NEEDS_CONFIRMATION` |
| AGN-016 | `DEC-SCOPE-053` — task owner on reassignment, delete, due time and overdue, linkage, KPI and nav, edit rules, cap, retry | **Resolved 2026-10-02** (T1–T8, `EXPLICIT_APPROVAL` in-session) |
| AGN-010 | `DEC-SCOPE-056` — one offer per application, deadline column, offer document, `offer_letter_url`, Offers count, conditions, concurrent saves | **Resolved 2026-10-02** (O1–O7, `EXPLICIT_APPROVAL` in-session) |

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
| Agent CRM Functionalities.md | EVID-015 | `DERIVED_BLUEPRINT`, no `EXPLICIT_APPROVAL` for the rest. **Tenant + Master slice moved out to AGN-001 (Rev. 6); Staff logins moved out to AGN-002 (Rev. 7); staff assignment/ownership of students moved out to AGN-004 (`DEC-SCOPE-042`, 2026-09-30); the §6 permission matrix moved out to AGN-003 (`DEC-SCOPE-044`, Rev. 8); staff activity moved out to AGN-021 (`DEC-SCOPE-046`, Rev. 9); §5 Step 2 counseling moved out to AGN-006 (`DEC-SCOPE-048`).** Still parked: staff performance, CRM settings | `DEC-SCOPE-038` covers AGN-001, `DEC-SCOPE-040` covers AGN-002, `DEC-SCOPE-042` covers AGN-004, `DEC-SCOPE-044` covers AGN-003, `DEC-SCOPE-046` covers AGN-021, `DEC-SCOPE-048` covers AGN-006; none yet for the rest |
| BDM Functionalities.md | EVID-016 | Proposes a "BDM" role with zero supporting evidence; inside `PRD_OPEN_ITEMS.md` item-61 hard blocker | none yet |
| Management Functionalities.md | EVID-017 | "Partner" login with full P&L/capital visibility, zero evidentiary basis, highest-sensitivity `NEEDS_CONFIRMATION` | none yet |
| Recruiter Functionalities.md | EVID-018 | Duplicates already-shipped `placement_team`/`hr_team` scope — unclear if extension or duplicate | none yet |
| Telecaller Functionalities.md | EVID-019 | Proposes a "Telecaller" role with zero supporting evidence; inside item-61 blocker | none yet |
| University Partnership CRM.md | EVID-020 | Proposes "Partnership Manager" (distinct from confirmed `university_rep`) and a commission direction reversed vs. `DEC-SCOPE-005` | none yet — conflicts with `CONFLICT_MATRIX.md` C-10 |
