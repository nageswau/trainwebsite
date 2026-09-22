# ENH-012 — Digital Portfolio Module — Design

## 1. Problem (audit result, gap confirmed)

`docs/delivery/ENHANCEMENT_BACKLOG.md:1238` (`DERIVED_BLUEPRINT`) already carries a full ENH-012 write-up
citing `School CRM.md §14` ("this should be a major feature"), `§8` (Career Passport: "Portfolio: 80%
completed"), `§23` (Parent Portal shows "Portfolio"), and Part B `§8` (Student Profile Central Record).
Confirmed `OPEN` in `docs/product/PRD_OPEN_ITEMS.md` item 77. That write-up's own **Existing behavior**
section is accurate and still holds: no portfolio entity, completion-percentage tracking, or
portfolio-section model exists anywhere in the codebase today.

A Graphify-oriented investigation this session (2026-09-22) found two things the original write-up did
not account for, both resolved in-session (§3):

1. **`school_student` is not a real login role.** `apps/api/app/core/rbac.py`'s `PERMISSIONS` dict defines
   `school_coordinator`, `school_principal`, `school_teacher`, `school_parent`, `academic_team`,
   `career_counselor`, `psychometric_team` — no `school_student`, and no frontend route tree for one. The
   backlog's "editable by the student" framing assumed a capability that doesn't exist and was never
   asked for as a separate build.
2. **"Portfolio" is already a term of art in this codebase**, meaning a staff member's assigned-schools
   caseload (`_student_in_portfolio()`, `_portfolio_school_ids()`, `list_portfolio_students()`,
   `GET /school/portfolio-students`, all in `apps/api/app/api/schools.py`). The new feature must not
   collide with that existing meaning.

## 2. Goals and non-goals

**Goals.** A per-student Digital Portfolio, readable by school staff/parent roles, combining
auto-populated data already recorded elsewhere with a small set of staff/teacher-entered achievement
records, plus a completion percentage that updates as sections are filled.

**Non-goals.**
- No `school_student` login/self-service portal (explicit user decision, §3).
- No aggregated "Student 360°" cross-module view — that is ENH-013's scope, which depends on this item;
  ENH-012 stays bounded to the portfolio entity, its completion tracking, and per-student read views.
- No new document/file-upload infrastructure — out of scope for this pass; if evidence/attachment support
  is wanted later, it should reuse `STU-011`'s existing upload pattern rather than building a second one.

## 3. Decisions confirmed in-session (2026-09-22)

1. **No student login.** The portfolio is visible to `school_coordinator`, `school_principal`,
   `school_teacher`, `school_parent`, `academic_team`, `career_counselor`, `psychometric_team` — modeled
   after `SCH-008`'s existing Student Journey Timeline (`student_timeline()`,
   `apps/api/app/api/schools.py:1040-1104`), which is read-only, computed live from existing tables, and
   reuses the same own-scope loader every other School screen already uses.
2. **Separate module.** New code lives in `apps/api/app/api/portfolio.py`, not `schools.py` — it only
   *calls* `_student_in_portfolio()` / `_load_readable_student()` / `_own_school_id()`, never modifies
   them, avoiding any collision with the existing "portfolio" meaning.
3. **Who writes self-entry content.** `school_coordinator` (own institution), `school_teacher`
   (assigned-students-only), and `academic_team` (own portfolio schools) can all create/edit/delete
   self-entry sections and the personal statement, each within their existing scope.
   `school_principal`/`school_parent`/`career_counselor`/`psychometric_team` are read-only.
4. **Completion formula.** Equal weight, binary per section: `filled sections / 16 * 100`, rounded,
   computed on every read — never cached or stored.
5. **Section classification** (16 total): 4 auto-populated (academic achievements, psychometric report,
   career guidance, languages — computed live from existing tables, always read-only), 1 computed
   (profile-completeness, from existing `SchoolStudent` fields, not user-editable), 10 self-entry via one
   generic table (`certification`, `project`, `internship`, `competition`, `sport`, `leadership`,
   `volunteering`, `award`, `extracurricular`, `skill`), 1 free-text field (personal statement).
6. **Data shape.** One generic `PortfolioEntry` table with a `section` discriminator (validated
   app-side, stored as a plain string — matching `SchoolActivity.activity_type`'s existing free-string
   precedent — so a future section needs no migration), plus one `PortfolioProfile` row-per-student table
   for the personal statement. Rejected: 10 near-identical dedicated tables (too much migration surface
   for one shape); a single JSON blob per student (no query/index-ability, weak validation).
7. **API conventions**, corrected against this codebase's actual house style during
   `api-and-interface-design` review (§6): `PATCH` for updates (this API has no `PUT` anywhere), real
   Pydantic request/response schemas in `schemas.py` (not the older `payload: dict` shortcut some SCH-004
   endpoints use), snake_case JSON (matches every existing endpoint), plain `HTTPException(status,
   "message")` errors (no new structured envelope), no pagination (bounded per-student cardinality,
   matching Timeline's precedent), no Idempotency-Key (no precedent for single-record creates in this
   API).
8. **Frontend conventions**, corrected against this codebase's actual house style during
   `frontend-ui-engineering` review (§7): no Tailwind/component library exists — plain CSS classes; no
   client data-fetching library — Server Components + `serverApi()`; forms follow
   `SchoolTransferRequestForm.tsx`'s exact pattern (manual `useState`, `busy`/`inFlight` guard, raw
   `fetch()`, `router.refresh()` on success — no optimistic UI, which would be a new, less-conservative
   pattern introduced for only one feature).

## 4. Approach

**Chosen:** one new FastAPI router module (`portfolio.py`) + two new additive tables + one new frontend
panel component + one new form component, reusing every existing scoping/error/formatting helper rather
than duplicating them.

**Rejected alternatives, and why:**
- **Extend `SchoolStudent` directly** (add `personal_statement`/`skills` columns to the existing model).
  Fewer tables, but `SchoolStudent` (`apps/api/app/models.py:985`) is already the largest, most
  heavily-shared model in the School domain; adding portfolio-specific columns to it mixes concerns into
  the module this feature is deliberately kept separate from, and raises migration risk on the hottest
  table in the domain.
- **Per-section dedicated tables** (`PortfolioProject`, `PortfolioCompetition`, ... one per section,
  mirroring `SchoolCareerRecord`/`SchoolPsychometricRecord`'s per-type pattern). Rejected as 9+
  near-identical tables/migrations for a single shared shape (title/description/organization/date range)
  — more migration surface and boilerplate than the one-table-with-a-discriminator design for no schema
  benefit, since none of the 10 section types actually need different columns from each other.
- **Single JSON-blob column per student.** Fewest migrations of all, but no query/index-ability by
  section, no DB-level structure or validation, and completion-percentage logic would have to parse the
  blob instead of querying rows — rejected as the highest long-term-maintenance option for the smallest
  short-term saving.

## 5. Data model and behavior

### `PortfolioEntry` (table: `portfolio_entries`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `default=uuid4`, matching every other model |
| `school_student_id` | UUID FK → `school_students.id` | `index=True`; composite index `(school_student_id, section)` |
| `section` | `String(40)` | App-validated against the 10-value allow-list; not a DB enum |
| `title` | `String(200)` | Required |
| `description` | `Text` | Nullable; app-validated max 2000 chars (unbounded `Text` + no rate limiting on this endpoint is an easy storage/payload-bloat vector otherwise — security review, §6) |
| `organization` | `String(200)` | Nullable |
| `date_from` | `Date` | Nullable |
| `date_to` | `Date` | Nullable; must be ≥ `date_from` when both are set (422 otherwise) |
| `created_by_user_id` | UUID FK → `users.id` | |
| `updated_by_user_id` | UUID FK → `users.id` | |
| + `TimestampMixin` | | `created_at`, `updated_at` |

### `PortfolioProfile` (table: `portfolio_profiles`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `school_student_id` | UUID FK → `school_students.id`, **UNIQUE** | one row per student |
| `personal_statement` | `Text` | Nullable; app-validated max 4000 chars (same rationale as `description` above); empty string is normalized to `NULL` on write |
| `updated_by_user_id` | UUID FK → `users.id` | Nullable |
| + `TimestampMixin` | | |

Migration: `apps/api/alembic/versions/0035_portfolio.py` (next sequential slot after `0034`). Purely
additive — two `CREATE TABLE`s, no `ALTER` on any existing table, no data migration. Preserves all
existing data.

### Completion percentage

`filled_count / 16 * 100`, rounded to the nearest integer, computed fresh on every `GET`:
- **Profile** (1): "filled" definition is an **open item**, §13.1.
- **Auto-populated** (4): "filled" = at least one corresponding row exists for the student
  (`SchoolAcademicResult` with `status="published"`, `SchoolPsychometricRecord`, `SchoolCareerRecord`,
  `SchoolLanguageRecord`).
- **Self-entry** (10): "filled" = at least one `PortfolioEntry` row exists with that `section` value.
- **Personal statement** (1): "filled" = `PortfolioProfile.personal_statement` is non-null and non-empty
  after trimming.

## 6. Authorization and security

**Read** — `GET /school/students/{id}/portfolio`:
- `school_coordinator` / `school_principal` / `school_teacher` / `school_parent`: reuse
  `_load_readable_student()` unchanged (own institution / assigned / own child).
- `academic_team` / `career_counselor` / `psychometric_team`: reuse `_student_in_portfolio()` unchanged
  (own portfolio schools).
- Any other role: 403.
- The response includes a server-computed `can_edit: bool` so the frontend never re-derives
  write-eligibility client-side — one source of truth for the authorization decision.

**Write** — all `POST`/`PATCH`/`DELETE` entry and personal-statement endpoints:
- `school_coordinator` (own institution, via `_own_school_id()`), `school_teacher` (assigned-only),
  `academic_team` (own portfolio schools, via `_student_in_portfolio()`) only.
- `school_principal`, `school_parent`, `career_counselor`, `psychometric_team`: 403 on any write attempt,
  even though they can read.
- Role/scope check happens **before** any entry-existence check — a caller who is the wrong role for a
  given student gets 403 before a 404 could leak whether an entry exists, matching
  `_require_transfer_admin`'s documented ordering in `school_transfers.py`.
- `PATCH`/`DELETE` on an entry additionally verify `entry.school_student_id == student_id` before
  mutating — a mismatch returns 404, not a silent no-op on the wrong row.

**Concurrency.** `PortfolioEntry` rows are independent; each request is a normal single-row transaction,
no cross-row locking needed. Concurrent edits to the *same* entry are last-write-wins, matching every
existing SCH-004/005/009 record update in this codebase (no optimistic locking exists anywhere else for
this record shape — preserving existing behavior rather than introducing a new pattern for one feature).

**Personal-statement upsert race.** Reuses `school_transfers.py:277-284`'s exact idiom —
`async with db.begin_nested(): db.add(row); await db.flush()`, catching `IntegrityError` from the unique
constraint on `school_student_id`. Unlike the transfer-filing case (a genuine duplicate-intent conflict →
409), a second concurrent "set the statement" is not a conflict — on `IntegrityError`, fall back to
loading and updating the existing row instead of rejecting.

**Completion percentage** is never stored, so it has no race condition of its own.

**Audit logging (required — matches every comparable write in this domain).** Every existing
create/update in the School domain calls `AuditLog` (`create_career_record`,
`create_psychometric_record`, `update_academic_result`, etc. — all in `schools.py`). This design
currently had none; adding it is not optional:
- `AuditLog(user_id=user.id, action="school.portfolio_entry_create", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"section": entry.section, "school_student_id": str(student_id)})`,
  and the equivalent `_update` / `_delete` actions.
- `AuditLog(user_id=user.id, action="school.portfolio_personal_statement_update", entity_type="portfolio_profile", entity_id=str(profile.id), metadata_json={"school_student_id": str(student_id)})`.
- `metadata_json` never carries `title`/`description`/`personal_statement` content — matching the
  existing convention exactly (`career_record_create` logs only `{"record_type": ...}`, never `notes`;
  `admin.py`'s `user.update` explicitly filters `password` out of its metadata). The same rule applies to
  any `logger.info(...)` calls added, matching `school_transfers.py`'s `extra_fields` pattern, which also
  never logs free text.

**Security review (2026-09-22), applying `security-and-hardening`.** Verified as already covered by
existing infrastructure, no new work needed: **CSRF** (the session cookie is `samesite="lax"`,
`httponly=True` — set in `auth.py:88-90` — so it's never attached to a cross-site state-changing request;
ENH-012 inherits this via the same `get_current_user` cookie dependency every endpoint uses). **SQL
injection** (all queries go through SQLAlchemy's parameterized `select()`/`where()`, no raw string SQL
anywhere in this codebase — a build-time discipline to hold, not a design change). **IDOR** (closed by
the ownership check in §6 above — role/scope checked against `student_id` before any entry lookup,
`entry.school_student_id == student_id` verified before every mutate). **Role escalation** (`can_edit` in
the `GET` response is a UI display hint only; every write endpoint independently re-checks role/scope
server-side — this must remain true through implementation, not be shortcut because "the GET already said
`can_edit: true`"). **XSS** (no `dangerouslySetInnerHTML` exists anywhere in this codebase; `title`/
`description`/`personal_statement` must render via plain JSX interpolation like `SchoolStudentTimeline.tsx`
does, never raw HTML). **Token/session handling, secret exposure** (no new auth flow or secret — reuses
`get_current_user` unchanged). **Rate limiting** (confirmed absent API-wide — no rate-limiting middleware
exists anywhere in this codebase today; this is a pre-existing condition ENH-012 inherits identically to
every other endpoint, not a gap this feature introduces or is in scope to fix).

The one place this review changes the calculus on an already-open item: **§13.2's hard-delete question.**
With no rate limiting and no soft-delete flag, a compromised or careless writer-role account could script
repeated deletes with no recovery path beyond the audit-log row added above. This doesn't flip the
recommendation (a single entry's hard delete stays low-blast-radius, and the audit trail now provides
forensic evidence), but it's a materially relevant fact for the open sign-off, not a silent decision.

## 7. Frontend

**Components.**
- `PortfolioPanel.tsx` (new, server-rendered, styled like `SchoolStudentTimeline.tsx`): renders all 16
  sections, embedded via the existing per-student `Promise.all` in `coordinator/students/[id]`,
  `principal/students/[id]`, `teacher/students/[id]`, `parent/children/[id]`. One component for both
  writer and reader roles — a single `can_edit` prop (from the API response, §6) conditionally renders
  Add/Edit/Delete affordances; no component duplication.
- `PortfolioEntryForm.tsx` (new, `"use client"`): one form parameterized by `section`, not 9 separate
  forms. Mirrors `SchoolTransferRequestForm.tsx` exactly: per-field `useState`, `busy` state, `inFlight`
  ref guard, raw `fetch()`, `detailMessage()`/`NOT_COMPLETED` from the existing `lib/apiErrors.ts`, a new
  `isPortfolioEntryBody()` guard following `isRequestBody()`'s pattern, `router.refresh()` on success (no
  optimistic UI).

**States.**
- Loading: none needed at the panel level — data rides the page's existing `Promise.all`/`loading.tsx`.
- Empty: `<p className="muted">No entries yet.</p>` per empty section (matching Timeline's empty-state
  wording exactly), with an inline "Add" affordance for writer roles only.
- Error: `role="alert"`, `detailMessage(data?.detail)`, focus moved to the alert (matching
  `SchoolTransferRequestForm`'s `alertRef.current?.focus()`).

**Accessibility.**
- Add/Edit/Delete are native `<button>`s; each disables itself during its own request and calls
  `refocus(id)` (existing `lib/focus.ts` helper) afterward.
- Delete needs a confirm step — the **first DELETE endpoint in this API**, so no existing confirm-dialog
  precedent exists, and no modal component exists anywhere in this codebase. Using an inline two-click
  pattern (Delete → "Confirm delete?" for a few seconds or until Escape/blur) rather than introducing a
  new Dialog component.
- Completion percentage rendered as visible text ("68% complete"), plus `role="progressbar"` with
  `aria-valuenow`/`aria-valuemin`/`aria-valuemax` if a visual bar is used — never color-only.

**Responsive.** No new breakpoints — reuses whatever `globals.css` already defines for `.card`/
`.portal-content` stacking.

## 8. Forced changes to existing behavior (the only ones)

**None.** This feature is purely additive: new tables, new router, new frontend components. No existing
endpoint, model, migration, or component is modified. `schools.py`'s existing `_student_in_portfolio()` /
`_portfolio_school_ids()` / `list_portfolio_students()` / `GET /portfolio-students` are called, never
changed.

## 9. Error states and edge cases

| Condition | Response |
|---|---|
| Student not found | 404 |
| Requester outside their read/write scope | 403 |
| `title` missing/empty on entry create | 422 |
| `date_from` after `date_to` | 422 |
| `section` not in the 10-value allow-list | 422 |
| Entry not found, or found but belongs to a different `student_id` | 404 |
| Two concurrent edits to the same entry | Last write wins (no error) |
| Two concurrent personal-statement writes | Both succeed; second overwrites first via the `IntegrityError`-fallback upsert |
| Auto-populated section with zero underlying records | Renders as an empty/unfilled section, no error |

## 10. Acceptance criteria (local IDs)

- **AC-01**: `GET /school/students/{id}/portfolio` returns all 16 sections; the 4 auto-populated sections
  reflect live data from `SchoolAcademicResult`/`SchoolPsychometricRecord`/`SchoolCareerRecord`/
  `SchoolLanguageRecord` with no duplication of that data into new tables.
- **AC-02**: `completion_percentage` equals `filled_sections / 16 * 100` (rounded) and changes correctly
  as sections go from empty → filled, verified for a 0%, partial, and 100% student.
- **AC-03**: `school_coordinator` (own institution), `school_teacher` (assigned student), `academic_team`
  (own portfolio school) can create/edit/delete `PortfolioEntry` rows and set the personal statement for
  students in their scope; the same actions outside their scope return 403.
- **AC-04**: `school_principal`, `school_parent`, `career_counselor`, `psychometric_team` can read (200)
  but any write attempt returns 403.
- **AC-05**: The frontend renders zero write affordances for read-only roles (`can_edit: false`), even
  though the backend already enforces 403 — verified as defense in depth, not the only control.
- **AC-06**: Editing or deleting an entry whose `school_student_id` does not match the URL's `student_id`
  returns 404.
- **AC-07**: A parent viewing their own child's portfolio never sees another child's data, matching
  `_load_readable_student()`'s existing own-child-only guarantee.
- **AC-08**: All existing `SCH-004`/`005`/`006`/`008`/`009` endpoints and the Timeline endpoint are
  unaffected — verified by running their existing test suites unchanged.
- **AC-09**: Every entry create/update/delete and every personal-statement update writes an `AuditLog`
  row with the correct `action`/`entity_type`/`entity_id`, and that row's `metadata_json` never contains
  `title`/`description`/`personal_statement` content.
- **AC-10**: `description` and `personal_statement` reject payloads over their length caps (2000 / 4000
  chars respectively) with 422.

## 11. Regression risks and test plan (written before code)

**Regression risks.**
- Low, by construction — no existing table, endpoint, or shared helper is modified, only called.
- The one real risk is authorization-surface growth: three roles (`academic_team`/`career_counselor`/
  `psychometric_team`) gain a *new* read capability (the portfolio) via their existing
  `_student_in_portfolio()` scope — verify this doesn't inadvertently widen what they can already see
  elsewhere (it shouldn't; it's a new endpoint, not a change to an existing one).

**Test plan.**
- `apps/api/tests/test_enh_012_digital_portfolio.py` (pytest, `enh005_helpers.py`-style fixtures):
  RBAC per role (all 7 read-capable roles × all 3 write-capable roles × out-of-scope denial), entry CRUD
  + ownership checks, completion-percentage correctness at 0/partial/full, personal-statement upsert
  including the concurrent-write race, 404/422 edge cases from §9, `AuditLog` rows written with correct
  action/entity fields and no free-text leakage (AC-09), and length-cap rejection (AC-10).
- Playwright: `enh-012-digital-portfolio.spec.ts` — coordinator adds an entry, completion percentage
  updates in the UI, parent viewing the same student sees it read-only with no edit controls, teacher
  sees 403/no access for a student outside their assignment.
- Per this repo's own regression cadence: full backend/E2E suites are *not* re-run after every feature —
  only every 3-4 (see project convention); this feature's own new tests run every time regardless.

## 12. Documentation deliverables

- Update `docs/delivery/ENHANCEMENT_BACKLOG.md`'s ENH-012 entry if the delivered shape diverges from the
  original write-up (the "student self-entry" framing already needs correcting to "staff/teacher-entry").
- Add this feature to the RTM per the project's required traceability chain (Evidence → Decision → BRD →
  PRD Requirement → Feature ID → Acceptance Criteria → UX/Screen → Architecture/DB/API/RBAC/Integration →
  Test → Code → Release Evidence).
- Update Graphify's knowledge graph after implementation (`/graphify --update`), matching the convention
  seen in recent commits (e.g. `24330b7 chore(enh-010): update graphify knowledge graph`).

## 13. Open items

1. **Exact "profile complete" definition — deferred to Task 1, not a design gap.** Which `SchoolStudent`
   fields determine the computed profile section is filled needs a short field audit against the current
   model (not `ENH-025`'s not-yet-built full field set) — this is the literal first implementation task
   (§14), not a decision to make blind here.
2. **Hard delete vs. soft-delete for `PortfolioEntry` — decided: hard delete.** `DELETE` → 204. No domain
   nuance requires a withdrawn-vs-removed distinction (unlike `JobApplication.withdrawn`, the one
   soft-delete precedent in this codebase, which exists for a specific dual-state reason that doesn't
   apply here); the `AuditLog` row required by §6 provides the forensic trail the security review asked
   for. Confirmed through two review passes with no objection.
3. **Auto-populated section payload shape — decided: embed full data.** `GET /portfolio` embeds the
   actual records for the 4 auto-populated sections (matching `student_timeline()`'s own depth) rather
   than a summary/count with links back to SCH-004/005/006/009 — simpler for the frontend, and consistent
   with the existing Timeline precedent it's modeled on.
