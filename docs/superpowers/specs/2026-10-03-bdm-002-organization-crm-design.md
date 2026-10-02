# bdm-002 — Organization CRM Core (common fields, contacts, assignment, scope) — Design

**Status:** design approved in-session on 2026-10-03, in four rounds: (1) approach, (2) data model + authorization, (3) API, transactions, races and errors, (4) frontend + tests. No code has been written.

**Revision 2 (2026-10-03):** reviewed against the `api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening` skills; findings applied inline and listed in §12. No approved decision changed.

**Branch:** `feature/bdm-002-organization-crm`, cut from `main` (`aad6b7c`, after bdm-001 #45); rebased on `ff27fa4` (after AGN-010 / AGN-012 #47, which took `DEC-SCOPE-056`/`057` and migrations `0062`/`0063`).

**Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-002.

**Source:** `functionalities/edusphere_markdown/BDM Functionalities.md` (`EVID-016`, `DERIVED_BLUEPRINT`) §9 "College/Agent/School Database".

**Scope authority:** `DEC-SCOPE-055` — D5 (a new `bdm_organizations` table), D11 / Q-02 (read every organization of your `bdm_type`, edit only those assigned to you), D12 / Q-03 (any BDM may create University / Corporate / Training Institute / Other; it belongs to the creator's module), D26 / Q-17 (managers own no work), D27 / Q-18 (duplicates: warn, never block, never merge, the BDM must acknowledge).

**Decision record:** **`DEC-SCOPE-058`** (next free number on `main` at `ff27fa4`; recheck before merge), written in this change. It holds the C1–C16 answers in §3.

**Gate:** `APPROVAL_GATES.md` GATE-09. Coding starts only after the implementation plan is approved.

**Migration:** `0064_bdm_organizations` (next free on `main` at `ff27fa4`; the later-merging branch renumbers).

---

## 1. Scope

**In scope:**
- An organization store for the institutions BDMs meet, with the §9 fields: Organization Name, Type, City, State, Contact Person, Designation, Phone, Email, Website, Existing Partner?, Courses Interested, Number of Students, Last Meeting, Next Meeting, Assigned BDM.
- The seven organization types: College, University, Agent, School, Corporate, Training Institute, Other.
- Named contacts per organization (Contact Person + Designation come from the primary contact).
- Create, read, edit, archive and restore, reassign, and contact add / edit / delete.
- The duplicate warning (Q-18).
- BDM pages under `/bdm/organizations` and manager pages under `/bdm/manager/organizations`.

**Out of scope (owned by other items, shown or enforced there):**

| Item | Owner | What bdm-002 does |
|---|---|---|
| §9 "MoU Status" | bdm-005 | Not stored, not shown |
| Pipeline stage and the list's "stage" filter | bdm-004 | Not built |
| Type-specific fields, Address, the `programs` catalogue for Courses Interested | bdm-003 | Not built; Courses Interested is free text |
| Last Meeting / Next Meeting values | bdm-006 | Returned as `null`, shown as "—" |
| "Archived organizations cannot receive new appointments" | bdm-006 | Documented as a rule bdm-006 must enforce (AC5b) |
| Bulk reassignment on BDM deactivation | bdm-025 | Manual reassign only |
| Links to `schools` / Agent Organizations | bdm-018 / bdm-019 | None |
| Any message to organization contacts | — (D29: nothing) | Contacts are data only |

---

## 2. Approaches considered

- **A. Two new flat files (chosen):** `app/api/bdm_organizations.py` + `app/services/bdm_organizations.py`, calling bdm-001's `bdm_context`, `require_manager` and `team_filter` unchanged. Matches what bdm-001 built (the codebase has no route packages) and leaves the security spine untouched.
- **B. Restructure into the backlog's `app/api/bdm/` package.** Rejected: moves working bdm-001 code (unrelated redesign, regression risk).
- **C. Add the routes to `app/api/bdm.py`.** Rejected: that module is documented as read-only with "no IDOR surface"; ten write routes would break the invariant and bloat it.

Manager pages live under `/bdm/manager/organizations` because a signed-out `/bdm/manager/*` visit goes to `/admin/login` (bdm-001 B9), where managers sign in; `/bdm/organizations` would send a manager to the BDM chooser.

---

## 3. Decisions (owner, in-session, 2026-10-03, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| C1 | AC1 "at least one contact" vs the backlog edge case "no contacts allowed, flagged" | **At least one contact.** Create without one → 422; the last contact cannot be deleted. The backlog edge case is superseded. |
| C2 | What a `bdm_manager` may do | **Read the organizations assigned to their team and reassign them** among their own BDMs of the same type. No create, no edit (D26). |
| C3 | Which organization types a BDM may create | **Any of the seven.** Ownership (`bdm_type`) is always the creator's type (Q-03). |
| C4 | Organization code | **Sequential `ORG-000123`** from a Postgres sequence. |
| C5 | Archive / restore | **The assigned BDM (or super_admin) archives; the team manager or super_admin restores.** Both audited. |
| C6 | Courses Interested | **Free text in bdm-002**; the `programs` multi-select is bdm-003. |
| C7 | Division admins | **No access** for `it_admin` / `overseas_admin`. Only `bdm`, `bdm_manager`, `super_admin`. |
| C8 | Does the duplicate check include archived organizations | **Yes**, labelled "archived" in the warning. |
| C9 | Assigned BDM on create | **Always the creator.** It changes only through the reassign route. |
| C10 | Contact Person / Designation / Phone / Email | **From the primary contact**; the organization also keeps its own phone, email and website. |
| C11 | Existing Partner? | **Manual yes/no** set by the BDM. |
| C12 | Approach | **A** (§2), including additive `bdm_type` / `q` filters on `GET /bdm/manager/team`. |
| C13 | Required fields | **Name and City** (plus type and ≥1 contact). |
| C14 | super_admin | **Reads, edits, archives, restores and reassigns everything; cannot create** (has no `bdm_type`). |
| C15 | Archived organizations | **Read-only** until restored (edit, contact changes and a second archive → 409). |
| C16 | Address | **Not in bdm-002** (§9 doesn't list it; Agent §B Address is bdm-003). |

Also approved with the design: `POST /{id}/restore` (follows from C5), `org_type` is editable, edit conflicts are last-write-wins (no ETag, as everywhere else).

---

## 4. Data model — migration `0064_bdm_organizations` (additive only)

### 4.1 `bdm_organizations`

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | |
| `code` | String(20) NOT NULL | `uq_bdm_organizations_code`. `f"ORG-{n:06d}"` with `n = nextval('bdm_organization_code_seq')`, computed in Python (grows past 6 digits; SQL `lpad` would truncate). Gaps after a rollback are accepted. Never client-supplied. |
| `org_type` | String(30) NOT NULL | `ck_bdm_organizations_org_type`: `college, university, agent, school, corporate, training_institute, other` |
| `bdm_type` | String(20) NOT NULL | `ck_bdm_organizations_bdm_type`: `agent, school, college`. Copied from the creator's profile; never changed. |
| `name` | String(200) NOT NULL | |
| `name_key` | String(200) NOT NULL | Server-set: `" ".join(unicodedata.normalize("NFKC", name).split()).casefold()` (stdlib; NFKC folds full-width and compatibility characters, §12.3) |
| `city` | String(120) NOT NULL | |
| `city_key` | String(120) NOT NULL | Server-set, same normalization |
| `state` | String(120) NULL | |
| `phone` | String(30) NULL | |
| `email` | String(255) NULL | |
| `website` | String(255) NULL | |
| `existing_partner` | Boolean NOT NULL | server default `false` |
| `courses_interested` | String(1000) NULL | free text (C6) |
| `student_count` | Integer NULL | `ck_bdm_organizations_student_count`: `student_count >= 0` |
| `assigned_bdm_user_id` | UUID NOT NULL | FK `users.id`, `ON DELETE RESTRICT` |
| `created_by_user_id` | UUID NOT NULL | FK `users.id`, `ON DELETE RESTRICT` |
| `archived_at` | timestamptz NULL | |
| `created_at`, `updated_at` | timestamptz | `TimestampMixin`, server default `now()` |

Indexes: `ix_bdm_organizations_type_assignee (bdm_type, assigned_bdm_user_id)`, `ix_bdm_organizations_duplicate_key (bdm_type, name_key, city_key)`.

The keys are stored, not a functional index, so the Python normalization and the stored value can never disagree.

### 4.2 `bdm_organization_contacts`

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | |
| `organization_id` | UUID NOT NULL | FK `bdm_organizations.id`, `ON DELETE RESTRICT`; `ix_bdm_organization_contacts_org` |
| `position` | BIGINT identity | Insertion order — contacts created in one request share `created_at`, so display order and "promote the oldest remaining contact" use this. Added in implementation (plan, Global Constraints). |
| `name` | String(200) NOT NULL | |
| `designation` | String(120) NULL | |
| `role` | String(30) NULL | `ck_bdm_organization_contacts_role`: `principal, dean, hod, placement_officer, counselor, management, owner, other` |
| `phone` | String(30) NULL | |
| `email` | String(255) NULL | |
| `is_primary` | Boolean NOT NULL | default `false`; `uq_bdm_organization_contacts_primary`: unique `(organization_id)` WHERE `is_primary` |
| `created_at`, `updated_at` | timestamptz | |

At most 20 contacts per organization (service rule).

### 4.3 Migration style (as `0061_bdm_profiles`)

- `upgrade()` skips a table that already exists (the dev schema-autocreate guard), creates the sequence, both tables, constraints and indexes.
- `downgrade()` raises `RuntimeError` while either table has rows, otherwise drops the contacts table, the organizations table, then the sequence.
- No existing table, column or row changes. `down_revision = "0063_agent_visa_details"`.

---

## 5. Backend

### 5.1 Schemas — `schemas.py` (after the bdm block)

- Reuse bdm-001's `_bdm_plain_text` / `_BDM_CONTROL` behaviour: strip, blank → `None`, reject control characters, cap length.
- `BdmOrgType`, `BdmContactRole` Literals.
- `BdmContactIn` (`extra="forbid"`): `name` (required), `designation`, `role`, `phone`, `email`, `is_primary` (default false).
- `BdmContactUpdate`: all optional; `name` cannot be set to null.
- `BdmOrganizationCreate` (`extra="forbid"`): `org_type`, `name`, `city` required; `state`, `phone`, `email`, `website`, `existing_partner` (default false), `courses_interested`, `student_count`; `contacts: list[BdmContactIn]` with 1–20 items; `confirm_duplicate: bool = False`.
- `BdmOrganizationUpdate` (`extra="forbid"`): every field optional, no `contacts`; `name`, `city`, `org_type`, `existing_partner` cannot be null; `confirm_duplicate`.
- Field rules: email uses the existing `_EMAIL_SHAPE` and is lower-cased; website must be an `http://` or `https://` URL (max 255); phone max 30 characters, digits, spaces and `+ - ( )` only; `student_count` 0–1,000,000.
- Sending `code`, `bdm_type`, `assigned_bdm_user_id`, `archived_at` or any unknown field → 422 "Unknown field: …".
- Output: `BdmOrgBdmRef {id, full_name, active}`, `BdmContactOut`, `BdmOrganizationRow` (list), `BdmOrganizationOut` (detail), `BdmOrganizationPage {items,total,limit,offset}`, `BdmOrgPermissions {can_edit, can_archive, can_restore, can_reassign}`.
- Routes take these as **typed body models** (the convention for new routes, e.g. `agent_students.py`; bdm-001 used `dict` only because `/admin/users` is an existing untyped contract). Failures are FastAPI's standard 422 list; custom validators word their own messages naming the field ("City is required", "Website must start with http:// or https://"), and the web shows them through the existing `lib/apiErrors.detailMessage`, which strips pydantic's "Value error," prefix. No global exception handler is added. The form also checks required fields client side, so a plain "Field required" is rarely seen.

### 5.2 Service — new `app/services/bdm_organizations.py` (never commits)

- `normalize_key(value) -> str`.
- `next_code(db) -> str`.
- `async load_scoped(db, user, org_id, *, lock=False) -> BdmOrganization` — the only way a route gets an organization:
  - `bdm`: `bdm_context(db, user)` (403 without a profile), then `bdm_type == profile.bdm_type`.
  - `bdm_manager`: join `BdmProfile` on `BdmProfile.user_id == assigned_bdm_user_id`, require `reporting_manager_user_id == user.id`.
  - `super_admin`: no filter.
  - any other role: 403 "BDM role required".
  - not found or out of scope → 404 "Organization not found". With `lock=True`: `SELECT … FOR UPDATE OF bdm_organizations` (`with_for_update(of=BdmOrganization)`), so the manager-scope join never locks the BDM's `bdm_profiles` row (which bdm-001's profile PATCH also locks) — §12.1.
- `scope_filters(db, user) -> list` — the same rules as SQL filters for the list.
- `permissions(user, org) -> dict`:
  - `can_edit` = not archived and (`user.id == assigned_bdm_user_id` or super_admin)
  - `can_archive` = same as `can_edit`
  - `can_restore` = archived and (manager in scope or super_admin)
  - `can_reassign` = not archived and (manager in scope or super_admin)
- `require(perm, org)` → 409 "Restore this organization first" when archived blocks the action, otherwise 403 with the action's message ("Only the assigned BDM can edit this organization", "Only the BDM's manager can restore this organization", "Only the BDM's manager can reassign this organization").
- `async find_duplicates(db, bdm_type, name_key, city_key, exclude_id=None) -> (matches ≤10, total)`; archived included.
- `duplicate_conflict(matches, total)` → 409 `{"message": "A similar organization already exists", "code": "possible_duplicate", "matches": [{id, code, name, city, archived, assigned_bdm_name}], "total": n}`.
- `async locked_reassign_target(db, org, actor, bdm_user_id) -> User` — `FOR SHARE` on the target user; requires role `bdm`, active, a profile with `bdm_type == org.bdm_type`, and (manager actor) `reporting_manager_user_id == actor.id`; else 422 "Choose an active BDM of this type from your team". Same as current assignee → 409 "Already assigned to this BDM".
- Contact rules: `primary_for_create(contacts)` (first contact is primary unless exactly one is flagged; more than one → 422 "Only one contact can be primary"); `set_primary(db, org, contact)` clears the old primary in the same transaction before setting the new one (flush order keeps the partial unique index satisfied); on delete of the primary, the oldest remaining contact (`created_at`, `id`) becomes primary.
- `snapshot_fields(org)` / changed-field lists for audit (field names only).

### 5.3 Router — new `app/api/bdm_organizations.py`, prefix `/bdm/organizations`

| Method + path | Who | Behaviour | Success |
|---|---|---|---|
| `GET ""` | bdm, manager, super_admin | Filters `q` (name or code), `org_type`, `city` (substring), `assigned` (`me` for a bdm, or a BDM user id), `include_archived` (default false), `limit` (1–100, default 50), `offset`. Scope filters ANDed first; ordered by `name, id`. One query: assignee and primary contact via outer joins. | 200 page |
| `POST ""` | bdm | Validate → duplicate check → `next_code` → insert organization + contacts → audit → commit. | 201 `{organization}` |
| `GET /{id}` | in scope | Detail with all contacts (primary first, then `created_at`), creator name, timestamps, permissions. | 200 `{organization}` |
| `PATCH /{id}` | `can_edit` | Lock → re-check duplicates only if `name` or `city` changed → apply → audit → commit. | 200 `{organization}` |
| `POST /{id}/archive` | `can_archive` | Lock → set `archived_at` → audit → commit. Already archived → 409 "Already archived". | 200 `{organization}` |
| `POST /{id}/restore` | `can_restore` | Lock → clear `archived_at` → audit → commit. Not archived → 409 "Already active". | 200 `{organization}` |
| `POST /{id}/assign` | `can_reassign` | Body `BdmOrganizationAssign {bdm_user_id: UUID}` (`extra="forbid"`). Lock org → `locked_reassign_target` → set → audit `{from, to}` → commit. | 200 `{organization}` |
| `POST /{id}/contacts` | `can_edit` | Lock → count < 20 else 409 "An organization can have at most 20 contacts" → insert (primary handling) → audit → commit. | 201 `{organization}` |
| `PATCH /{id}/contacts/{cid}` | `can_edit` | Lock org → contact must belong to it (else 404 "Contact not found") → apply (`is_primary: true` moves the flag; `false` on the primary → 422 "Choose another primary contact instead") → audit → commit. | 200 `{organization}` |
| `DELETE /{id}/contacts/{cid}` | `can_edit` | Lock org → belongs check → last contact → 409 "An organization needs at least one contact" → delete (promote if primary) → audit → commit. | 200 `{organization}` |

Every write returns the whole organization (`{organization: BdmOrganizationOut}`, permissions included), so the UI re-renders from one source of truth with no refetch. Every route declares a `response_model`, so `name_key`, `city_key` and `created_by_user_id` are never serialized. A `PATCH` whose values equal the stored ones (or an empty body) is 200 with no audit row and no `updated_at` change.

Rows and detail always include `last_meeting_at: null` and `next_meeting_at: null` (bdm-006 fills them; the field names are the contract bdm-006 implements).

**Archived and appointments (AC5b):** bdm-006 must call `load_scoped(..., lock=True)` and refuse an archived organization (409). Recorded here and in the backlog so bdm-006's spec inherits it.

Registration: one import and one entry in the `for r in (...)` router loop in `app/main.py`.

### 5.4 `GET /bdm/manager/team` — additive filters (`app/api/bdm.py`)

- New optional query params `bdm_type` (`agent|school|college`) and `q` (name, email or Employee ID; `SEARCH` length rule; `lookups._pattern` escape), ANDed with `team_filter(user)`.
- Without them the response is byte-for-byte what it is today (existing tests stay green unchanged).
- Used by the reassign picker; the picker shows active BDMs only (filtered client side from the `active` field, and enforced server side by `locked_reassign_target`).

### 5.5 Audit (same transaction as the write; fail closed)

`AuditLog(user_id=actor, action=..., entity_type="bdm_organization", entity_id=str(org.id), metadata_json=...)`:

| Action | Metadata |
|---|---|
| `bdm_organization.create` | `code`, `org_type`, `bdm_type`, `fields` (names set), `contact_count` |
| `bdm_organization.update` | `fields` (names changed) |
| `bdm_organization.duplicate_override` | `match_count` |
| `bdm_organization.archive` / `.restore` | — |
| `bdm_organization.assign` | `from`, `to` (user ids) |
| `bdm_organization.contact_create` / `.contact_update` / `.contact_delete` | `contact_id`, `fields`, `promoted_contact_id` (on delete of the primary) |

No names, phones or emails in audit metadata or logs. Logs (`app.bdm`) carry ids, route and counts only.

### 5.6 Transactions, races and authorization

- Each write is one transaction: scope → lock → change → audit → one `commit()` in the route. Services never commit.
- **Concurrent writes to one organization** (edit, archive, restore, reassign, any contact write) serialize on `SELECT … FOR UPDATE` of the organization row. This makes "≥1 contact" and "one primary" safe under two simultaneous deletes / primary changes; the partial unique index backstops the primary rule.
- **Reassign vs target deactivation:** `FOR SHARE` on the target user row (bdm-001's `locked_active_manager` pattern), so a BDM deactivated in the same instant is never committed as the assignee.
- **Concurrent creates of the same college:** both succeed (warn-only, never block); each later edit of name/city sees the other as a duplicate. No serialization lock.
- **Code uniqueness:** the sequence never repeats a value; `uq_bdm_organizations_code` is the backstop.
- **IDOR:** every `{id}` and `{cid}` resolves through `load_scoped` and the organization-ownership check of the contact; out of scope is 404 before any permission check can reveal existence.
- **Manager visibility follows the BDM:** when bdm-001's PATCH changes a BDM's manager, that BDM's organizations move to the new manager's scope automatically (computed by join, nothing to migrate).

### 5.7 Errors

| Status | When |
|---|---|
| 403 | Not `bdm` / `bdm_manager` / `super_admin`; BDM without a profile; create by a non-BDM; edit / archive by a non-assignee; restore / reassign by a non-manager |
| 404 | Unknown organization or contact id; out of scope |
| 409 | Possible duplicate (structured body); archived (`Restore this organization first`); already archived / active; last contact; 20-contact cap; already assigned |
| 422 | Validation (readable, names the field); unknown field; more than one primary; reassign target invalid |

---

## 6. Frontend

### 6.1 Pages (server components; gate = the API, as bdm-001)

| Path | Gate call | Login link | Renders |
|---|---|---|---|
| `/bdm/organizations` | `/api/v1/bdm/me` | `BDM_SIGN_IN` | `PortalShell` (`BDM_NAV`) + `<Suspense><BdmOrganizationsPanel basePath="/bdm/organizations" canCreate/></Suspense>` |
| `/bdm/organizations/new` | `/api/v1/bdm/me` | `BDM_SIGN_IN` | `BdmOrganizationForm` (create) |
| `/bdm/organizations/[id]` | `/api/v1/bdm/me` + `GET /bdm/organizations/{id}` | `BDM_SIGN_IN` | `BdmOrganizationDetail` |
| `/bdm/manager/organizations` | `/api/v1/auth/me` (manager or super_admin, else `accessDenied`) | `/admin/login` | `PortalShell` (`BDM_MANAGER_NAV`) + panel, `canCreate={false}` |
| `/bdm/manager/organizations/[id]` | `/api/v1/auth/me` + detail | `/admin/login` | `BdmOrganizationDetail` |

A detail 404 renders "Organization not found" with a link back to the list (no existence leak). Editing is inline on the detail page.

### 6.2 Components (client; shared by both portals)

- `BdmOrganizationsPanel` — the `AdminBdmPanel` pattern: URL state (`offset`, `q`, `org_type`, `city`, `assigned=me` for a BDM, `archived=1`), Back/Forward sync, `fetchPage` with the `isPage` guard. States: loading; error with Retry; empty ("No organizations yet" + "Add organization" for a BDM); no matches for the filters (+ "Clear filters"); past the end (+ "Go to the first page"); table. Columns: Code, Name (link), Type, City, Primary contact, Assigned BDM, Last meeting ("—"), Next meeting ("—"), plus an "Archived" badge. `BdmTeamTable`-style pager ("Showing a–b of n", Previous/Next).
- `BdmOrganizationForm` — create and edit. §9 fields with labels, hints (website must start with http:// or https://), the type select; on create a contacts repeater (add / remove, minimum 1, maximum 20, one "Primary" radio). Submit uses `sendJson`; button disabled with "Saving…" while busy; errors via `FormMessage` with focus moved to the message. On a `possible_duplicate` 409: an alert (focus moves to its heading) listing the matches as plain text (code, name, city, assigned BDM, "Archived" label — no links, so following one can't lose the unsaved entry; §12.2), "Save anyway" (resends with `confirm_duplicate: true`) and "Cancel"; Save stays disabled while the warning is open (the `AgentStudentForm` pattern).
- `BdmOrganizationDetail` — profile `<dl>` with "—" for blanks (Contact Person / Designation from the primary contact; Last / Next Meeting "—"); actions rendered from `permissions` only: Edit (toggles the form), Archive (inline confirm group, `AdminBdmRow` pattern), Restore, Reassign.
- `BdmOrganizationContacts` — list with "Primary" marker; add / edit inline; delete with inline confirm, disabled for the last contact with the reason shown; "Make primary".
- `BdmOrganizationReassign` — `SearchableSelect` in server mode over `/api/v1/bdm/manager/team?bdm_type=…&q=…` (inactive BDMs excluded); `Noun` union gains `"BDM"`; a confirm step ("Reassign ORG-000123 to …?"); focus via `useFocusAfterRender`.
- `lib/bdmOrganizations.ts` — types, `ORG_TYPE_LABEL`, `CONTACT_ROLE_LABEL`, URLs, `duplicateMatches(detail)` parser, `teamSearch(bdmType)` feed.

### 6.3 Navigation

- `BDM_NAV`: My Day · **Organizations** (`/bdm/organizations`) · Profile.
- `BDM_MANAGER_NAV`: Dashboard · Team · **Organizations** (`/bdm/manager/organizations`).
- `tests/lib/navigation.bdm.test.ts` is updated deliberately (a spec change, not a test bent to pass).
- `PortalShell`'s exact-match highlight is unchanged (shared by every portal; out of scope).
- `middleware.ts` unchanged: `/bdm/:path*` is already protected with the right sign-in redirects.

### 6.4 Responsive and accessibility

No horizontal page scroll at phone width (the table scrolls in its own labelled region, as bdm-001); every input has a label; errors use `role="alert"`, success `role="status"`; focus returns to the triggering control after confirm/cancel and to the message after an error; buttons have visible text (no icon-only actions).

---

## 7. Acceptance criteria

| ID | Criterion | Verified by |
|---|---|---|
| AC1 | A BDM creates an organization in their own `bdm_type` with ≥1 contact; the code is unique, sequential and server-generated (a client `code` → 422); Name and City are required; no contacts → 422. | `test_bdm_002_organizations.py`, e2e |
| AC2 | A likely duplicate (same `bdm_type` + normalized name + city, archived included and labelled) returns 409 `possible_duplicate`; resending with `confirm_duplicate` creates it and writes `duplicate_override`; nothing is merged. Also on a name/city edit. | `test_bdm_002_organizations.py`, form unit test, e2e |
| AC3 | A BDM lists and reads every organization of their type (other types → 404) and edits, archives and changes contacts only on those assigned to them (others → 403). | `test_bdm_002_scope.py` |
| AC4 | A manager reassigns an organization in their scope to an active BDM of the same type who reports to them, with an `assign` audit row; other type / other team / inactive / non-BDM → 422; a manager cannot edit (403). | `test_bdm_002_assign.py`, e2e |
| AC5a | Archived organizations are hidden by default, shown with `include_archived=true`, read-only, and restorable by the manager or super_admin. | `test_bdm_002_organizations.py`, e2e |
| AC5b | Archived organizations cannot receive new appointments — enforced by bdm-006 via `load_scoped`; recorded in the backlog for bdm-006. | bdm-006 tests (not this item) |
| AC6 | Last Meeting and Next Meeting are `null` in the API and "—" in the UI until bdm-006. | API + component tests |
| AC7 | Every write writes exactly one action audit row (plus `duplicate_override` when acknowledged) in the same transaction, with no contact PII. | `test_bdm_002_*` |
| AC8 | `GET /bdm/manager/team` without the new params is unchanged; with them it filters by type / search within team scope. | `test_bdm_001_reads.py` + new test |
| AC9 | Pages show loading, empty, no-match, error (Retry) and past-the-end states; work at phone width; actions appear only when permitted. | vitest, e2e |

---

## 8. Tests (written before the code)

### 8.1 Backend (`apps/api/tests`, shared DB, uuid-unique data via `bdm001_helpers` + a new `bdm002_helpers.py`)

- `test_bdm_002_migration.py` — chains after `0063_agent_visa_details` and is the single head; model matches migration (columns, CHECKs, indexes, partial unique); round trip on an isolated DB keeps existing rows identical; downgrade refuses while rows exist; the sequence exists and is dropped.
- `test_bdm_002_service.py` — `normalize_key`; `next_code` format incl. a value above 999999; `primary_for_create`; `permissions` table for each actor/state.
- `test_bdm_002_organizations.py` — AC1, AC2, AC5a, AC6, AC7; validation messages; list filters (`q`, `org_type`, `city`, `assigned`, `include_archived`), paging bounds 422, stable ordering.
- `test_bdm_002_scope.py` — every route × {assigned BDM, same-type other BDM, other-type BDM, team manager, other manager, super_admin, it_admin, student, BDM without profile} with the exact status code (AC3, IDOR).
- `test_bdm_002_assign.py` — AC4; same assignee 409; archived 409; concurrent reassigns of one organization serialize (both complete, final state = the later commit, two audit rows); reassign vs deactivation of the target.
- `test_bdm_002_contacts.py` — add/edit/delete; another organization's contact id → 404; last contact 409; two concurrent deletes of the last two contacts → exactly one succeeds; primary move; delete-primary promotion; 20-contact cap.
- Revision-2 cases (§12): a `javascript:` / `data:` website → 422; NFKC duplicate (full-width name matches); no-op PATCH writes no audit row; `assigned` garbage or `me` for a non-BDM → 422; every write response has the full `{organization}` shape; the reassign 422 text is identical for unknown id / wrong role / other type / other team / inactive; a manager-scope write does not block a concurrent bdm-001 profile PATCH of the assignee (lock `of`); refused writes log a WARNING with ids only (caplog asserts no email/phone).
- `test_bdm_001_reads.py` — new tests for `bdm_type` / `q` on the team route; existing tests unchanged.

### 8.2 Web unit (vitest)

`tests/lib/bdmOrganizations.test.ts`; `BdmOrganizationsPanel.test.tsx` (all states, URL sync, archived toggle, manager mode has no create); `BdmOrganizationForm.test.tsx` (validation, contacts repeater, duplicate flow, busy state); `BdmOrganizationDetail.test.tsx` (actions by permission flags, archive confirm, "—"); `BdmOrganizationContacts.test.tsx`; `BdmOrganizationReassign.test.tsx`; `BdmOrganizationPages.test.tsx` (gates, login links, not-found); `navigation.bdm.test.ts` (updated lists).

### 8.3 End to end (Playwright)

`tests/e2e/bdm-002-organization-crm.spec.ts`: super_admin provisions a manager + two College BDMs (`createAndActivate`); BDM 1 creates a college with Principal + Placement Officer; creating it again shows the duplicate warning → Save anyway; BDM 2 sees both but cannot edit; the manager reassigns one to BDM 2; BDM 1 archives the other → hidden, visible with "Show archived"; manager restores; phone-width check (no horizontal scroll).

### 8.4 Regression runs

All `test_bdm_001_*` + the new files + the lite backend set; Playwright bdm-001, auth-001, adm-001 specs; `tsc`, `eslint`, `next build`; full web unit suite. The full backend suite is run by the owner per the regression cadence.

---

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| `services/bdm.py` (security spine) | Not modified; only imported. |
| `app/api/bdm.py` team route | Additive optional params; existing tests unchanged + new tests. |
| `app/main.py` router list | One line; merge conflicts only. |
| `lib/navigation.ts` + its exact-list test | Deliberate update; bdm-001 page tests don't assert nav. |
| `SearchableSelect` `Noun` union | Additive literal; existing nouns unchanged. |
| Alembic chain | Single head after 0063; recheck `main` before merge and renumber if needed. |
| Shared test DB | uuid-unique data; no truncation; counts asserted on filtered queries only. |

No existing table, column, route contract, page or component behaviour changes.

---

## 10. Documentation (same change)

`DEC-SCOPE-058` in `PRODUCT_DECISION_REGISTER.md`; `BDM_CRM_BACKLOG.md` bdm-002 status line, C1 note on the superseded edge case, and the AC5b rule added to bdm-006; traceability entries; `docs/architecture/DATA_MODEL.md` for the two tables; API notes for the new routes.

---

## 11. Completion gates

COMPLETE only when: AC1–AC9 verified with fresh evidence; backend new + bdm-001 + lite set pass; web unit suite, `tsc`, `eslint`, `next build` pass; Playwright bdm-002 + regression specs pass; migration round trip verified; phone-width and accessibility checks pass; documentation updated.

---

## 12. Revision 2 — skill reviews (2026-10-03)

Reviewed against `api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening`. Findings are applied inline above and listed here. No approved decision (C1–C16) changed; nothing outside bdm-002 is touched.

### 12.1 API and interface design

| # | Finding | Resolution |
|---|---|---|
| A1 | Archive / restore / assign returned a bare 200 — the write responses had three shapes | Every write returns `{organization}` (§5.3). One shape for every organization response. |
| A2 | `FOR UPDATE` on a joined manager-scope query would also lock the `bdm_profiles` row; bdm-001's profile PATCH locks the same row → needless contention and a lock-order risk | `with_for_update(of=BdmOrganization)` (§5.2). Global lock order for every bdm-002 write: organization row → its contacts → target user (`FOR SHARE`). bdm-001's paths lock user/profile only, never an organization, so no cycle exists. |
| A3 | Error format | Kept the existing contract: string `detail` for 403/404/409, FastAPI's list for 422, and the structured `{message, code, matches, total}` only for `possible_duplicate` (the AGN-004 precedent). A new error envelope would fork the convention the web's `detailMessage` already reads. |
| A4 | Naming | snake_case fields and query params, as every existing route. Booleans `existing_partner`, `include_archived`, `confirm_duplicate`, `can_*`. |
| A5 | Retry safety of `POST` (create) | Not idempotent and documented so; **no idempotency key** (none is contracted anywhere — CLAUDE.md warns against uncontracted idempotency assumptions). A retry after a lost response returns the `possible_duplicate` 409 naming the organization just created, so the BDM sees it rather than silently getting two. Archive / restore repeated → 409 "Already archived / active" (AGN-004 convention). Contact `POST` is not retry-safe; the 20-contact cap bounds it. |
| A6 | No-op PATCH | 200, no audit row, no `updated_at` bump (§5.3), matching AGN-004's "audit only if changed". |
| A7 | Response field allowlist | `response_model` on every route; `name_key` / `city_key` / `created_by_user_id` are never returned (the creator is returned as a name only). |
| A8 | `assigned` mixes `me` and a UUID | Same convention as `agent_students._assigned_filter`; anything else → 422 "assigned must be me or a BDM id". `me` for a non-BDM → 422. Always ANDed with scope, so it can only narrow. |
| A9 | Team route change is additive | New params optional; default response identical; tested by the unchanged bdm-001 tests plus new ones (AC8). |
| A10 | Typed contracts on the web | `lib/bdmOrganizations.ts` types mirror the response models; `isPage` / an `isOrganization` id guard reject non-JSON success bodies (the browser QA N2 rule). |

### 12.2 Frontend UI engineering

Design language preserved: the existing global classes (`action-card`, `btn secondary small`, `table-wrap`, `form-error`, `form-message`, `empty`, `muted`, `visually-hidden`), `PortalShell`, `FormMessage`, `SearchableSelect`, the inline confirm-group pattern. No new CSS framework, tokens or dependency; any new rule goes in `globals.css` only if an existing class can't express it.

| # | Area | Resolution |
|---|---|---|
| F1 | Visual hierarchy | One `h1` per page ("Organizations", "Add organization", the organization's name). Detail: a header with name, code, type and an "Archived" text badge (not colour alone); `h2` sections "Details", "Contacts", "Assignment". |
| F2 | Loading | List: `aria-busy` + "Loading organizations…" status (the AdminBdmPanel pattern, not a new skeleton). Detail and form pages are server-rendered, so no client loading waterfall. Buttons show "Saving…" / "Archiving…" and are disabled while busy (no double submit). |
| F3 | Empty / no-match / past-end | Distinct messages: "No organizations yet" (+ "Add organization" for a BDM; managers: "Your team has no organizations yet"); "No organizations match these filters" (+ "Clear filters"); past the end (+ "Go to the first page"). |
| F4 | Errors | List load failure: alert + Retry. Form: `FormMessage` alert, focus moved to it; network drop uses the existing `NOT_COMPLETED` text and keeps the entry. Detail 404: "Organization not found" + back link. A 409 "Restore this organization first" (state changed under the user) re-renders from the returned/refetched organization. |
| F5 | Forms | `<fieldset>`/`<legend>` for "Organization" and each contact; visible labels; "(required)" in the label text and `aria-required`; `type="email"`, `type="tel"`, `type="url"`, `type="number" inputMode="numeric" min=0`; `autoComplete="organization"`, `address-level2` (city), `address-level1` (state), contact `name` / `tel` / `email`; client checks set `aria-invalid` + `aria-describedby` on the field; the entry is never cleared on error. |
| F6 | Keyboard | All actions are `<button>`/`<a>`; inline confirm groups take focus on open, Escape cancels, focus returns to the trigger (`useFocusAfterRender`); "Add contact" moves focus to the new contact's name; removing a contact moves focus to the previous contact's legend or the Add button. |
| F7 | Mobile | Filters wrap (`flex-wrap`, the existing pattern); the list table scrolls inside its labelled `table-wrap` region (bdm-001 behaviour, no page scroll at 320 px); contacts render as a list of blocks, not a table; action buttons wrap below the header on narrow widths. |
| F8 | Perceived performance | Writes re-render from the returned organization (no refetch); filters push URL state with `scroll:false`; search submits on Enter/button (no per-keystroke requests), the reassign picker uses `SearchableSelect`'s existing debounce/`minChars`. |
| F9 | After create | Navigate to the new detail page with a `role="status"` notice "Organization ORG-000123 created". |
| F10 | Component size | `BdmOrganizationForm` is split into `BdmOrganizationFields` + `BdmContactFields` to stay under ~200 lines each. |
| F11 | Website display | Rendered as a link only when it starts with `http://`/`https://` (`target="_blank" rel="noopener noreferrer"`, "(opens in a new tab)" visually hidden); otherwise plain text. Phones and emails are plain text (D29: no communication from the system). |

### 12.3 Security and hardening — threat model

**Trust boundaries:** JSON bodies of the 9 write routes; path ids (`{id}`, `{cid}`); query params (`q`, `org_type`, `city`, `assigned`, `include_archived`, `limit`, `offset`, team `bdm_type`/`q`); the session cookie; organization text rendered back to other BDMs of the type (stored-XSS vector).

**Assets:** contact PII (names, phones, emails), the assignment (who may edit), the team relationship (what a manager sees), the audit trail.

| Threat | Check | Result |
|---|---|---|
| Authentication / spoofing | Session handling | Unchanged: `get_current_user` (cookie `httponly`, `secure` from settings, `samesite=lax`), re-checks `active` per request, so a deactivated BDM/manager loses access on the next call. No new auth flow. |
| Token / session | New tokens? | None. No session or token change. |
| Authorization | Every route | Role gate first (`bdm` → `bdm_context`; `bdm_manager`/`super_admin`), then `load_scoped`, then the action permission. Server-side only; the UI's `permissions` flags are hints. |
| IDOR | Path ids | `{id}` only via `load_scoped` (out of scope → the same 404 as nonexistent: no existence oracle); `{cid}` must belong to that `{id}` (else 404). Covered by the 9-actor matrix on every route. |
| Role escalation / mass assignment | Can a caller widen their rights? | `extra="forbid"` rejects `bdm_type`, `assigned_bdm_user_id`, `code`, `archived_at`, `created_by_user_id`; assignment changes only via `/assign`, which requires manager-in-scope or super_admin and a target that reports to that manager; a manager cannot target another team's BDM; the reassign 422 is one message for every invalid target (no user/role enumeration). |
| Cross-type leakage via duplicates | Does the warning reveal another module's data? | Matches are limited to the organization's own `bdm_type`, which the caller can already read. |
| Input validation | Every field | Typed models; lengths; enums (`org_type`, `role`); email shape; website `http(s)` only (blocks `javascript:`/`data:`); phone character set; `student_count` bounds; control characters rejected; `contacts` 1–20; `q` ≤ 200, `city` ≤ 120; bounded `limit`/`offset`. Client checks are convenience only. |
| SQL injection | Query construction | SQLAlchemy ORM, bound parameters only; `ILIKE` through `lookups._pattern` (escapes `%`, `_`, `\`); the sequence name is a constant. No raw SQL with input. |
| XSS | Rendering stored text | React text nodes only; no `dangerouslySetInnerHTML`; website rendered as `href` only after the scheme check, on top of the server's `http(s)` rule. |
| CSRF | State-changing calls | JSON `POST`/`PATCH`/`DELETE` under the SameSite=Lax cookie and CORS limited to `frontend_url` — the existing posture (bdm-001 §12.3, `account.py`). No GET changes state. |
| SSRF | Is the website fetched? | Never fetched server-side (no preview, no validation request). |
| Secrets | Code/config | No new secret or setting. `git diff --cached` checked before each commit. |
| Sensitive logs | Logs and audit | Logs (`app.bdm`): ids, route, counts, refusal reason codes; never names, phones, emails or free text. Audit metadata: ids, field names, `from`/`to` user ids. Write refusals (403) are logged at WARNING with actor id, organization id and route (bdm-001 precedent). |
| Rate limiting / DoS | Abuse by an authenticated BDM | **No new limiter** (changing throttling needs approval; nothing in bdm-002 asks for one). Bounded by authentication, payload caps (20 contacts, field lengths), `limit ≤ 100`, indexed filters. |
| Audit / repudiation | Who did what | One action row per write, same transaction (fail closed); `duplicate_override` records an acknowledged warning; reassign records `from`/`to`. |
| Personal data | Purpose, retention, deletion | Fields are exactly §9's; contacts are business contacts. Contact delete is a hard delete (real erasure). Organizations are archived, not deleted (C5), so their PII is retained with the organization — a retention/erasure policy for BDM data is **NEEDS_CONFIRMATION** and out of bdm-002 scope (same as bdm-001's "retention follows the account"). |
