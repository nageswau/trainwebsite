# ENH-009 — School Profile: mandatory full field coverage — Design

**Status:** Approved in-session, 2026-09-22 (`DEC-SCOPE-025`). Superpowers architectural path:
brainstorming → this design doc → `writing-plans` next.

**Source requirement:** `School CRM.md §2` (`docs/sources/School CRM.md:64-116`, `EVID-014`).
**Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md:938-1084` (`ENH-009`, Revision 4 —
`EXPLICIT_APPROVAL` already recorded there for mandatory field coverage).
**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → `DEC-SCOPE-025`.

## 1. Scope

24 School Profile fields from `EVID-014`. Existing coverage (unchanged): `name`, `city`, `state`,
`tier`, `tier_valid_until`, Dedicated Counsellor (`SchoolStaffAssignment`). Full field-by-field
table: `ENHANCEMENT_BACKLOG.md:987-1012`.

Of the 15 fields the backlog marks genuinely missing, 4 are role-derived rather than stored today
(Principal, Vice Principal, Career Counsellor, School Coordinator) — an earlier draft of this
design left these "unchanged, no design gap," which is wrong: they are on the backlog's own
mandatory-coverage list and the design must say how each is satisfied, not silently continue
treating them as out of scope. Resolved as follows (§2/§3): Principal and School Coordinator are
already derivable from `User.profile["school_id"]` + role, and Career Counsellor from
`SchoolStaffAssignment` — these three are exposed as **computed, read-only fields in `SchoolOut`**
(same treatment as student/teacher counts), never stored, so there is nothing to desync. Vice
Principal has **no role and no account type anywhere in this system** — nothing to derive.
Creating a new role/account type for it would be materially bigger scope than a field-coverage
item; instead `vice_principal_name` ships as a plain nullable text field on `School` (no login, no
role, matching the same "field ships, larger structural question deferred" treatment already used
for `edusphere_bdm`).

**Out of scope for this item** (carved out explicitly, not silently dropped):
- Populating `edusphere_bdm`'s value — blocked on the separate, unapproved `BDM` role
  (`PRD_OPEN_ITEMS.md` item 61). The field itself ships as plain text.
- A real forward-looking visit-scheduling engine — `monthly_visit_schedule` ships as descriptive
  text only; automation is `ENH-019`.
- A School Coordinator/Principal self-service profile page — admin-only this pass (`DEC-SCOPE-025`).
- A document-upload feature for Agreement/MoU — ships as a plain reference string
  (`mou_reference`). A generic `ProfileDocumentUpload`/`StorageService` pattern exists in this
  codebase; generalizing it to `School` is judged excess scope for a field-coverage item.

## 2. Data model

One additive migration on the existing `schools` table. All new columns nullable — no backfill,
no data loss, existing rows unaffected.

```
school_code            String(8), unique, indexed   — business ID, generated once at creation,
                                                        immutable, reuses core/identifiers.py's
                                                        generate_student_code()/unique_student_code()
branch                 String(200), nullable          — free text (DEC-SCOPE-025: field, not entity)
address                String(500), nullable
contact_number         String(30), nullable
email                  String(255), nullable
website                String(255), nullable
grades_available       String(200), nullable          — free text, no confirmed structured format
board                  String(20), nullable            — app-level Literal["CBSE","ICSE","State","IB","Other"],
                                                          not a DB enum (matches how `tier` is a plain String)
partnership_date       Date, nullable
mou_reference          String(255), nullable          — plain reference, not a file upload (§1)
edusphere_bdm          String(200), nullable          — plain text, not a FK (§1)
monthly_visit_schedule String(200), nullable          — descriptive text, not a scheduler (§1)
vice_principal_name    String(200), nullable          — plain text, no role/account exists (§1)
```

**Not stored, computed at response time, exposed only in `SchoolOut`:** Number of students / Number
of teachers (live `COUNT`); Principal name (derived from `User.profile["school_id"]` +
`role="school_principal"`); School Coordinator name (same derivation, `role="school_coordinator"`);
Career Counsellor name(s) (derived from `SchoolStaffAssignment`, portfolio-scoped — a list, since a
counsellor's portfolio can span multiple schools and a school could in principle have more than
one assigned). None of these five are stored columns, avoiding a denormalized value that needs sync
logic every time a role assignment changes.

## 3. API & schemas

**New Pydantic schemas** (`schemas.py`): `SchoolCreate`, `SchoolUpdate`, `SchoolOut` — the first
real schemas for this entity, replacing `create_school`/`update_school_tier`'s untyped
`payload: dict`. `model_config = {"extra": "forbid"}` (verified exact syntax: this codebase uses a
plain dict literal, not `pydantic.ConfigDict`) — not a universal convention in this file (most
`*Create` schemas don't set it), but the deliberate pattern already used for ENH-005's most
security-sensitive create schemas (`TransferRequestCreate`/`IncomingTransferCreate`,
`schemas.py:611-622`) to block a smuggled unexpected field. Applying it here is justified the same
way: it closes the role-escalation check in §5 (a client-supplied `role`/`coordinator_password`
alongside the profile fields becomes a loud 422 by construction, not something to defend against
in handler code). `board` and `tier` both become `Literal[...]` fields (folding `tier`'s existing manual
`if tier not in {...}` check into the schema, so the whole entity validates one way, not two).
Email fields validate via the existing `_valid_email()` helper (via a field validator), not bare
`EmailStr` — preserves the existing error message text (`"A valid email address is required"`)
instead of introducing a second validation vocabulary. New string fields use the existing `_fit()`
length-cap helper's pattern (422 naming the field), matching how `name`/`full_name` already work.

**Endpoints** (all under the existing `/overseas-admin` prefix, admin-only —
`{"overseas_admin","super_admin"}`, manual in-handler role check, matching the existing
`create_school`/`update_school_tier` pattern — not refactored to `Depends(require_role(...))`,
which is an unrelated-module change):

- `POST /overseas-admin/schools` — unchanged URL, request body becomes `SchoolCreate`. Response
  grows additively (existing consumer `AdminSchoolCreatePanel.tsx` only reads specific keys, stays
  compatible).
- `PATCH /overseas-admin/schools/{id}` — **widened** from tier-only to all profile fields via
  `SchoolUpdate` (true partial-update semantics, every field optional). Old tier-only payloads
  still validate and behave identically. `name`/`city`/`state`/`coordinator_*` stay excluded from
  the update payload — they were never editable before and no acceptance criterion asks for that.
- `GET /overseas-admin/schools` — response items become `SchoolOut`. Still unpaginated (unrelated,
  pre-existing characteristic; low cardinality, out of scope to change here).
- `GET /overseas-admin/schools/lookup?code=` — **new**, models
  `GET /overseas-admin/school-students/lookup?code=` (`admin.py:1240`) but with a narrower role set:
  `{"overseas_admin","super_admin"}` only, **excluding `counselor`** (unlike the student-lookup
  endpoint, which grants Counselor access for the unrelated School→Overseas bridge use case —
  Counselor has no legitimate reason to see or edit a School's profile; `DEC-SCOPE-025`).

**`school_code` generation:** reuses `unique_student_code(db, School.school_code)` verbatim, called
inside the existing single-transaction creation flow (school + coordinator + role assignment +
audit logs still commit together — no change to transaction boundaries). The underlying
check-then-generate pattern has the same pre-existing TOCTOU gap `student_code` already has
(astronomically unlikely collision, 4.3B-code space, low-frequency admin-driven onboarding) —
deliberately not hardened here, to avoid asymmetric robustness vs. the identical existing pattern.

**Error semantics:** unchanged convention — plain `HTTPException(status, "message")` throughout,
not a new `{error:{code,message}}` envelope. 422 for validation (now mostly automatic via
Pydantic), 404 unchanged, 409 unchanged (duplicate coordinator email only).

## 4. Frontend

**List (read) — reuses the existing generic mechanism, no new component.** A read-only "Partner
Schools" list already exists: `services/portal.py:1360-1371`'s `section=="schools"` branch, served
through `GET /api/v1/portal/overseas/admin/schools` and rendered by the existing generic
`PortalSection`/`DataTable` components (`apps/web/app/overseas/admin/[section]/page.tsx` →
`PortalPage.tsx`). Widen that one `_payload(...)` call's columns/row-dict to include `school_code`,
`branch`, `board`, `tier`. This is what satisfies "School ID displayed everywhere a school is
currently identified only by name" for the one real list surface that exists.

**Create — extend `AdminSchoolCreatePanel.tsx`** with the 13 new stored fields (§2), grouped via
the existing `<fieldset className="question">` CSS (already defined in `globals.css`) into logical
groups (Identity, Academic, Partnership) for visual hierarchy at ~19 fields. Field rows use the existing
`.form-grid` class (2-column, collapses to 1 column at 640px via the existing global media query —
no new responsive work). `school_code` is never a form field — server-generated, shown only in the
success message and the list.

**Edit — new `AdminSchoolEditPanel.tsx`.** No existing UI supports clicking a generic-portal-section
table row to edit (that interaction doesn't exist anywhere in this codebase), and the established,
in-code-documented convention is "list is read-only, a separate panel writes." Design: a
lookup-by-`school_code` step (reusing the `GET .../schools/lookup?code=` endpoint, §3) loads one
school into an edit form using the same fieldset grouping as create, then `PATCH`es it.

**States:** loading/error/empty reuse existing conventions — `.form-message`/`.form-error` +
`role="status" aria-live="polite"` (already in `AdminSchoolCreatePanel.tsx`); the existing `.empty`
class already handles "no schools yet" in `PortalSection`'s table; lookup "not found" reuses the
shared `detailMessage()`/`toneClass` helper from `lib/welcomeLink.ts`.

## 5. Security review

Full detail already delivered in-session; summary of findings and disposition:

| Area | Finding | Disposition |
|---|---|---|
| Authentication | No change | ✅ unchanged |
| Authorization | Lookup endpoint role set | **Fixed in design**: `{"overseas_admin","super_admin"}`, excludes `counselor` (§3) |
| IDOR | Admin roles act on any school by design | ✅ not a gap — no ownership scoping needed |
| Role escalation | `edusphere_bdm` plain text, `extra="forbid"` blocks smuggled `role`/`password` fields | ✅ covered by schema design |
| Input validation | Email/Board/length caps | **Addressed**: reuse `_valid_email()`/`_fit()`, `Literal` for `board`/`tier` (§3) |
| XSS | New free-text fields rendered via React JSX only | ✅ no `dangerouslySetInnerHTML` anywhere touched |
| CSRF | `SameSite=Lax` + JSON `fetch()`, unchanged | ✅ inherits existing posture |
| SQL injection | SQLAlchemy ORM only, no raw SQL | ✅ not applicable |
| Token/session handling | Unchanged | ✅ unchanged |
| Secret exposure | No secrets among new fields | ✅ not applicable |
| Sensitive logs | Widened `PATCH` would log more partner-contact fields | **Addressed**: `school.profile_update` audit action logs changed **field names only**, not values (`DEC-SCOPE-025`) |
| Rate limiting | None exists anywhere in this API | Reported, not changed — pre-existing, codebase-wide, outside `ENH-009` scope |
| Audit requirements | Tier-only audit action didn't cover profile fields | **Addressed**: new `school.profile_update` action alongside existing `school.tier_update` |

Consistent with prior findings already on record for this codebase (`DEC-SCOPE` entries for
`ENH-005`): no rate limiting anywhere in the API, no CSRF token (`SameSite=Lax` only), admin routes
gate on `user.role` directly rather than active role assignments. All pre-existing and out of scope
for `ENH-009`.

## 6. Testing strategy (detail in the implementation plan)

- **Backend unit/integration:** extend `test_sch_003_school_onboarding.py` for the new
  create/update/lookup fields and validation; new tests for `school_code` uniqueness/generation,
  `board`/`tier` rejection of invalid values, `extra="forbid"` rejecting unknown fields, lookup
  endpoint's narrowed role set (403 for `counselor`), audit log entries for both `school.create` and
  the new `school.profile_update`.
- **Frontend unit:** extend `AdminSchoolCreatePanel.test.tsx` for the new fields; new
  `AdminSchoolEditPanel.test.tsx` covering lookup success/not-found/network-error and the PATCH
  submit path.
- **Playwright:** extend `sch-003-school-onboarding.spec.ts` for the new create fields and the list
  showing `school_code`; new coverage for the edit flow.
- Full backend/E2E regression **not** required for this single item per this project's regression
  cadence (every 3-4 features) — School-domain suites only, per the pattern already established for
  `SCH-007`/`SCH-008`.

## 7. Regression risks

- `schools` table migration touches a live table seeded by ~15 test files' shared fixtures
  (`_create_school_with_coordinator()`, `_school()`, `_create_school_with_roles()`) — additive
  nullable columns only, so existing fixtures continue to work unchanged.
- `create_school`/`list_schools` response shape grows additively — `AdminSchoolCreatePanel.tsx` and
  `sch-003-school-onboarding.spec.ts` read specific keys only, not the whole object shape.
- No RBAC/scoping regression risk — Branch stays a field, not a new tenant boundary
  (`DEC-SCOPE-025`), so `_own_school_id()` and every other School-domain authorization check in
  `schools.py` is untouched.

## 8. Open items carried forward (not blockers for this item)

- `edusphere_bdm`'s population path once the `BDM` role decision resolves separately.
- Whether to generalize `ProfileDocumentUpload` to `School` for a real MoU attachment, if a future
  item asks for it.
- Whether Super Admin's generic `/admin/[module]/page.tsx` should also gain a `schools` module
  entry (Overseas Admin already has a working list via the portal-section mechanism; Super Admin's
  separate generic page doesn't list schools today, and no acceptance criterion requires it) —
  noted as a possible, optional, small follow-up, not part of this item.
