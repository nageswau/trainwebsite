# ENH-008 — Parent Account Linked to Children Across Multiple Schools

**Status:** Design approved (brainstorming session, 2026-09-22). Ready for `writing-plans`.
**Evidence classification:** `ORIGINAL_REQUIREMENT` (user's direct quote, see below) + `DERIVED_BLUEPRINT` (`docs/delivery/ENHANCEMENT_BACKLOG.md:764-858`). No Decision ID contradicts this scope; `docs/decisions/PRODUCT_DECISION_REGISTER.md:2177` independently flags the gap this closes as `NEEDS_CONFIRMATION`, deferred to this item by name.

## 1. Business requirement

User's explicit instruction: *"parent may [have] children from different schools."* `School CRM.md §4` ("Parent Login," `docs/sources/School CRM.md:1432-1476`) shows a parent switching between two children's profiles but never states — and never rules out — that those children attend different schools. Genuinely open, not contradicted by any recorded Decision ID.

## 2. Current behavior (why this is blocked today)

The database already supports this: `SchoolParentLink` (`apps/api/app/models.py:1027-1036`) is many-to-many (`UniqueConstraint(parent_user_id, school_student_id)`). The block is entirely application-level, and wider than it first appears:

- `_parent_email_conflict()` (`schools.py:600-609`) rejects linking a parent email to a student at School B if the existing account's `profile.get("school_id")` names a different school.
- `link_parent()` (`schools.py:1195-1215`) duplicates the same rejection inline, independently.
- **The deeper issue:** `_own_school_id()` (`schools.py:264-270`) is called unconditionally at the top of `list_students()`, `_load_readable_student()`, and `_readable_students()` (the functions that back a parent's own dashboard, child-detail page, and career/counselling/psychometric/results reads) and raises `403` whenever `profile.school_id` is falsy. Relaxing only the conflict checks, without also fixing this, would let a second `SchoolParentLink` row be created and then immediately 403 the parent's own dashboard the moment `profile.school_id` stops naming "the" school.
- `accept_invite()` (`schools.py:207-260`) writes `profile.school_id` on first provisioning.
- `school_transfers.py:_approve()` (`school_transfers.py:389-427`) writes `profile.school_id` when a transferred child was a parent's only link at the losing school — built entirely on the single-school-per-parent assumption this feature removes.

## 3. Target design

**Core decision:** `profile.school_id` is fully deprecated for the `school_parent` role — never read for authorization, never written, anywhere — while remaining exactly as-is, unchanged, for `school_coordinator`/`school_principal`/`school_teacher`. Parent scope is derived 100% from `SchoolParentLink` rows. No schema change, no data migration/backfill (existing stale values are simply never read again — zero risk of a migration touching data incorrectly).

### 3.1 `_parent_email_conflict()` (`schools.py:600-609`)
Drop the cross-school comparison. Reject only when an existing user with that email has `role != "school_parent"`. Update the error message (it currently says "...not a Parent **at this school**" — no longer accurate once the school qualifier is gone).

### 3.2 `link_parent()` (`schools.py:1195-1215`)
Delegate the conflict/role check to `_parent_email_conflict()` instead of its own inline duplicate — **but** keep a separate, explicit "does a `school_parent` user actually exist for this email" check alongside it. `_parent_email_conflict()`'s contract is "`None` = safe to use," which is `None` both for a valid existing parent *and* for an email nobody has used yet (fine for its other caller, `_link_or_invite_parent()`, which falls back to an invite) — `link_parent()` has no invite fallback, so it must not treat "unknown email" as a pass. Update its own current message ("...must be an existing Parent **at your own school**") to match.

### 3.3 `list_students()`, `_load_readable_student()`, `_readable_students()` (`schools.py:835-840, 870-878, 1536-1543`)
Skip the `_own_school_id(user)` call when `user.role == "school_parent"`; `_scoped_students_query()`'s existing parent branch (built in ENH-005) already derives scope from `SchoolParentLink.parent_user_id == user.id` alone and ignores the `school_id` parameter for that role. Widen `_scoped_students_query()`'s `school_id: UUID` type hint to `UUID | None` for honesty (parent callers now pass `None`). Before implementing, confirm `_load_readable_student()`'s full body doesn't reference `school_id` again later in its parent branch (only the first ~15 lines were read during design).

**Defense-in-depth property to preserve, not just an accident:** if a future bug ever mis-routed a parent into `_scoped_students_query()`'s non-parent branch, passing `school_id=None` compiles to `IS NULL` in SQLAlchemy; `school_students.school_id` is `NOT NULL`, so that branch would return zero rows, not leak all schools. Fails closed.

### 3.4 `accept_invite()` (`schools.py:207-260`)
Skip writing `profile["school_id"]` when `invite.role == "school_parent"`. No change for any other invited role.

### 3.5 `school_transfers.py:_approve()` (`school_transfers.py:389-427`)
Remove the profile-write block entirely (parent links themselves are never touched by a transfer — nothing to migrate). `request.outcome`'s `parents_moved`/`parents_kept` response fields **stay in the API contract**, recomputed as a read-only query, at the *same point in the transaction* as today's `others_at_from` check (before `student.school_id` is reassigned at line 443, explicitly excluding the transferring student's own row — getting this ordering wrong would read post-move state and mislabel every parent as "moved"): "moved" = parent has no other link at the losing school after this transfer; "kept" = parent still has ≥1 link there.

The per-parent `AuditLog(action=ACTION_SCOPE_CHANGED, ...)` rows disappear (nothing is written to audit anymore) — but the affected parent **IDs** (UUIDs, never emails) must be folded into the existing `ACTION_TRANSFER` audit entry's metadata (which already includes `request.outcome`'s aggregate counts at line 446), so per-parent traceability isn't silently lost, only its shape changes from N rows to one list field.

### 3.6 No response-shape changes elsewhere
`list_students()`/`_student_out()` stay as-is. AC2 ("dashboard shows each child's school") is already satisfied by the existing per-child overview endpoint's `school_name` field, built in ENH-005, which the frontend already calls per child.

## 4. Frontend

No functional/data changes needed — the parent dashboard and child-detail pages already handle a parent whose children span schools (built by ENH-005, confirmed by reading `childrenSpanSchools()` in `apps/web/components/SchoolChildOverview.tsx:31-35` and its use in `apps/web/app/school/parent/dashboard/page.tsx:34,57`). Two UI-quality improvements, scoped to this change, from the frontend audit:

- **Group child cards by school** on the dashboard when `childrenSpanSchools()` is true (today it's a flat list with school named only in body text — buries the grouping once a parent has several children across schools). Reuse existing `h2`/`.muted` conventions already in the file; zero visual change when `false`.
- **Add `loading.tsx`** for `/school/parent/dashboard` and `/school/parent/children/[id]/` (neither exists anywhere in the app today, and none of these pages have one) — a multi-school parent now has strictly more parallel `loadChildOverview()` calls on first paint. Reuse the existing `.skeleton-line` CSS utility (`apps/web/app/controls.css:46-48`, already `prefers-reduced-motion`-safe) rather than inventing a new loading pattern.

Two additional, smaller pre-existing gaps surfaced by the audit (inconsistent `<th scope="col">` usage across tables in `SchoolChildOverview.tsx`/`notifications/page.tsx`, and no `:focus-visible` rule on `.portal-nav a`) are **not caused by this change** and are out of scope — noted for a separate follow-up, not part of this implementation.

## 5. Security posture (from the specialist review)

The core authorization change here — a `school_coordinator` at any school can now link an existing `school_parent` account regardless of which school(s) they're already linked at — **is the feature**, not a defect (AC1). Two residual risks are explicitly accepted, not fixed, as part of this design:

- **Widened email-enumeration surface.** `_parent_email_conflict()` already distinguishes "no such account" / "account exists but wrong role" / "valid parent" in its response; this was previously scoped to the coordinator's own school, and becomes platform-wide once the school comparison is dropped. Bounded by requiring an authenticated `school_coordinator` role (not anonymous); every *successful* link is already audited. No rate limiting exists anywhere in this codebase today, and adding it here would be infrastructure unrelated to this feature — explicitly out of scope.
- **Rejected conflict checks are never audit-logged** (only successful links are). Pre-existing pattern, not changed by this design. Noted, not fixed, to stay in scope.

Confirmed **not** at risk: the read-side IDOR boundary (`SchoolParentLink.parent_user_id == user.id`, i.e. the authenticated user's own ID) is untouched by §3.3 — `_own_school_id()`'s parent branch was never the actual protection (its return value was already discarded downstream), so removing the redundant pre-check removes no protection. The write-side student-ownership check (`student.school_id != coordinator's own school_id → 404`) is also untouched.

## 6. Acceptance criteria (from the backlog item, unchanged)

1. A parent email already linked to a `school_parent` account at School A can be successfully linked to a student at School B, producing a second `SchoolParentLink` row, not a rejection.
2. The parent's dashboard shows both children, each correctly attributed to their own school.
3. A parent cannot see any data for a school they have zero `SchoolParentLink` rows at.
4. A non-`school_parent` account (e.g. an `academic_team` member's email) is still correctly rejected when used as a `parent_email` — this existing protection must not regress.

## 7. Regression risks

- `apps/api/tests/test_enh_005_scope.py::test_link_parent_refuses_a_parent_from_another_school` and `::test_adding_a_student_refuses_a_parent_email_that_belongs_to_another_school` currently assert `422` for exactly the scenario AC1 requires to succeed — must be rewritten to assert success + a second `SchoolParentLink` row, not merely kept passing.
- `apps/api/tests/test_sch_roster_parent_invite.py::test_parent_email_belonging_to_a_non_parent_account_is_rejected` must keep passing unchanged (AC4 pin).
- `school_transfers.py:_approve()`'s interaction with a parent who already has legitimate multi-school links before a transfer — the transaction-ordering note in §3.5 is the concrete failure mode to guard against in tests.
- `SCH-002` (roster/bulk-upload) and `SCH-007` (Parent Portal) both exercise `_link_or_invite_parent()`/`_parent_email_conflict()` directly.

## 8. Testing plan (detail in the implementation plan / TDD execution)

Rewrite the two `test_enh_005_scope.py` tests named above. Add: parent-with-2-schools sees both in `/school/students`; parent-with-0-links-at-a-school sees none of it; transfer approval's `parents_moved`/`parents_kept` reflect link state correctly with no profile write and the new audit metadata carries parent UUIDs. Re-run the School-domain test files (`SCH-001`, `SCH-002`, `SCH-007`, `SCH-008`, `SCH-011`, `ENH-004`, `ENH-005`) as a targeted regression gate given this is an authorization-model change, ahead of the project's usual batched 3-4-feature cadence.

## 9. Explicitly out of scope

No new Pydantic schemas, no new DB columns, no data migration/backfill, no new external integrations, no rate-limiting infrastructure, no fix to the two pre-existing frontend accessibility gaps noted in §4, no change to `get_current_user()`/session/cookie handling.
