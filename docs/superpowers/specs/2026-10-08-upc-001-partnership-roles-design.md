# upc-001 — Partnership Manager and Partnership Head Roles, Profile, Provisioning, Sign-in, Shell, Menu — Design

**Status:** design written 2026-10-08. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So the item answers PU1–PU11 (§3) are the **recommended defaults, accepted under that instruction**.
They are not separate per-question approvals, and they are recorded that way in `DEC-SCOPE-116`.

**Branch:** `feature/upc-001`, cut from `origin/main` @ `99ec1c38` (after #142).

**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-001 (dependencies: none). It shares role files with
rec-001. No rec-001 branch or worktree exists, and nothing is registered for it, so this item takes the next free numbers (§5.4 idiom).

**Source:** `functionalities/edusphere_markdown/University Partnership CRM.md` (`EVID-020`, `DERIVED_BLUEPRINT`):
- "Partnership Manager" in §4, §7, §19 and §27;
- "Management" in §21, §22 and §31;
- the §32 main menu (source lines 1060–1100).

Scope authority: the backlog's U0–U15 (`EXPLICIT_APPROVAL`, 2026-10-08), in particular U2 (commission visibility) and U3 (roles).

**Decision record:** **`DEC-SCOPE-116`**, written in this change. It registers U0–U15 (the backlog says "registered as one DEC-SCOPE
when upc-001 starts") and PU1–PU11. Numbering:
- migration `0100_partnership_profiles` (after `0099_tel_settings`);
- API contract §12AI;
- RBAC §2.42.

The Recruiter backlog reserves these numbers provisionally for rec-001, but nothing is registered. Whichever item merges first takes
them, and the other re-chains at merge time.

**Gate:** `APPROVAL_GATES.md` GATE-09. **Template:** tel-001 (`2026-10-05-tel-001-telecaller-roles-design.md`, `DEC-SCOPE-073`). Where
this spec says "as tel-001", that spec's section applies with telecaller → partnership manager and telecaller manager → partnership head.

---

## 1. Scope

**In scope:**
- Two new roles:
  - `partnership_manager` (division `overseas`);
  - `partnership_head` (division `global`, created only by `super_admin`).
- A 1:1 `partnership_profiles` row per manager, holding the Employee ID and the reporting head. Name, email, mobile and active status
  stay on `users`.
- Provisioning through `POST /admin/users` with a nested `partnership_profile` (tel-001 approach A). The welcome set-password link
  (`DEC-SCOPE-019`), forgot password and change password are reused unchanged.
- Admin edits through `PATCH /admin/users/{id}`. The manager may change only their phone, through `PATCH /partnership/profile`.
- Read routes:
  - `GET /partnership/me`
  - `GET /partnership/head/team`
  - `GET /admin/partnership-managers`
  - `GET /admin/partnership-heads`
- The shell:
  - `/partnership/dashboard` (the manager's landing page) and `/partnership/profile`;
  - `/partnership/head/team` (the head's landing page);
  - the admin "Partnership managers" page at `/admin/partnership-managers` and `/overseas/admin/partnership-managers`;
  - the §32 menu (PU8).
- Gates for later items: `services/partnership.py` (`partnership_context`, `require_head`, `team_filter`) and
  `services/partnership_access.py` (`can_see_commission`, U2).

**Out of scope, owned by later items:** each §32 page (upc-003 … upc-031); the university `scope(user)` (upc-003, which needs the
owner columns); `strip_commission` and the commission fields (upc-016); targets (upc-021); deactivation with reassignment (upc-032); the
permission sweep (upc-033); the `partner` role's commission access (Management M3, which owns that role).

**Unchanged:**
- the `auth.login` division rule (it already produces the wrong-portal 403);
- `get_current_user` and the token claims;
- the `users` columns;
- `university_rep`;
- every BDM and telecaller path;
- the `GET /admin/users` response.

## 2. Approaches

| | Approach | Verdict |
|---|---|---|
| **A** | Nested `partnership_profile` branch in `POST/PATCH /admin/users` + `partnership_profiles` table + read-only admin routes | **Chosen (PU4)** — one provisioning path; same as bdm-001/tel-001 |
| B | Separate `POST/PATCH /admin/partnership-managers` | Rejected — duplicates provisioning (password ban, welcome token, audit, delivery) |
| C | `users.profile` JSON | Rejected — no DB-enforced unique Employee ID, no FK to the head |

## 3. Decisions (recommended defaults, accepted under the session instruction)

| # | Question | Answer |
|---|---|---|
| PU1 | Q-29: workspace paths | **`/partnership/*`** for managers, who sign in at `/overseas/login`. **`/partnership/head/*`** for heads, who sign in at `/admin/login`. This mirrors `/telecaller/manager/*` and `/bdm/manager/*`; the backlog's `/admin/partnerships/*` alternative would mix a head workspace into the Super Admin's `/admin` pages. Signed out: `/partnership/head*` → `/admin/login?next=…`, any other `/partnership/*` → `/overseas/login?next=…`. No chooser is needed, because managers have one portal. |
| PU2 | Where active status lives | **`users.active` only** (tel-001 TL2). The backlog's `active` profile column is not added, because a second flag could disagree with the login flag. |
| PU3 | What a manager edits about themselves | **Phone only**: `PATCH /partnership/profile`, plus the same rule on the generic `PATCH /auth/me` (tel-001 TL8), so it cannot be bypassed. |
| PU4 | Approach | **A** (§2). The backlog's route list is unchanged; create and edit go through `/admin/users`. |
| PU5 | Does a head have a profile row? | **No** (tel-001 TL5). |
| PU6 | Required profile fields | **Employee ID and reporting head**, both required. Mobile stays optional on `users`. |
| PU7 | Who creates a manager | **`super_admin` and `overseas_admin`** (the manager's division is overseas). `it_admin` → 403 "Cannot create users in another division" (existing gate). **Only `super_admin` creates a head** (AC2), from the generic Users form. |
| PU8 | §32 menu "each enabled as its item lands" | `PARTNERSHIP_MENU` (in `lib/navigation.ts`) holds the 19 entries in source order, each naming its owning item. Only entries whose item has landed (`live`) appear in the sidebar: today that is Dashboard, plus Profile. The dashboard lists the other 18 as "Coming soon", as plain text without links, so there are no dead links. Each later item flips its entry to `live`. Labels drop the source's emoji, following the existing nav style. |
| PU9 | Commission helper in upc-001 | Only **`can_see_commission(user)`**: `super_admin`, `partnership_manager` and `partnership_head` (U2). `strip_commission` is upc-016's, which owns the fields; a stub with nothing to strip would be dead code. `partner` joins when Management M3 lands that role. |
| PU10 | Deactivation | The existing plain `PATCH active` for both roles, with no reassignment (upc-032). A manager whose head is inactive shows **"No active head"** (`head_active: false`). |
| PU11 | Employee ID uniqueness | Case-insensitive and unique within `partnership_profiles` (like `bdm_profiles` and `telecaller_profiles`, each separate). One person holds one `users.role`, so no cross-table rule is needed. |

## 4. Data model — migration `0100_partnership_profiles`

New table `partnership_profiles`, model `PartnershipProfile` with `TimestampMixin`:

| Column | Type | Constraint |
|---|---|---|
| `user_id` | UUID → `users.id` | **PK** (backlog: "user_id PK") |
| `employee_id` | String(40) | NOT NULL; unique index **`uq_partnership_profiles_employee_id` on `lower(employee_id)`**; stored trimmed, case kept |
| `reporting_head_user_id` | UUID → `users.id` | NOT NULL; index `ix_partnership_profiles_reporting_head` |
| `created_at` / `updated_at` | timestamptz | from the mixin |

- The migration only adds a table, behind an inspector guard (the 0061 pattern).
- `downgrade()` refuses while any row exists.
- "The head is an active `partnership_head`" spans tables, so the service enforces it under `FOR SHARE`.

## 5. Backend

- **`rbac.PERMISSIONS`:** `partnership_manager: {"partnership:self"}`, `partnership_head: {"partnership:team"}`.
- **`schemas.py`:**
  - `PartnershipProfileCreate` (`employee_id: BdmEmployeeId`, `reporting_head_user_id: UUID`, `extra="forbid"`);
  - `PartnershipProfileUpdate` (the same fields, optional, with explicit null → 422);
  - the self-update reuses `TelecallerSelfUpdate` (the phone rule);
  - outputs `PartnershipMeOut`, `PartnershipTeamPage`, `PartnershipAdminPage` (row + `reporting_head` + `head_active`) and
    `PartnershipHeadPage`;
  - `PARTNERSHIP_FIELD_LABELS`.
- **`services/partnership.py`** (functions only; nothing commits; logs carry ids, never email, phone or Employee ID):
  - `CREATOR_ROLES = {"super_admin", "overseas_admin"}`;
  - `require_creator_may(actor, route)` → 403 "Your role cannot manage partnership managers";
  - `parse_profile_create` / `parse_profile_update` reuse tel-001's `_parse` / `_readable` with this item's labels;
  - `locked_active_head(db, id)` → 422 "Reporting head must be an active partnership head";
  - `flush_profile` → 409 "Employee ID already exists";
  - `profile_snapshot` and `profile_out`;
  - `apply_profile_update` re-checks the head only when it changes;
  - `partnership_context(db, user)` → 403 "Partnership manager role required" / "Partnership profile not set up — contact your
    administrator";
  - `require_head(user)` (`partnership_head` or `super_admin`, else 403 "Partnership head role required");
  - `team_filter(user)` (`[]` for super_admin, else `reporting_head_user_id == user.id`);
  - `require_admin_reader(actor)` (super_admin / overseas_admin, else 403).
- **`services/partnership_access.py`:** `COMMISSION_ROLES` and `can_see_commission(user)`.
- **`admin.create_user`:**
  - The new block sits after the telecaller block and before the cross-division gate. Its order is: profile 422 → creator 403 →
    division 422 "Division must be overseas for a partnership manager".
  - A stray `partnership_profile` → 422 "Only a partnership manager has a partnership profile".
  - A head created by anyone other than `super_admin` → 403 "Only a Super Admin can create partnership heads".
  - `allowed_by_division`: `overseas` gains `partnership_manager`, `global` gains `partnership_head`.
  - The head is locked, the profile is flushed (409), and the audit metadata gains `partnership_profile`.
  - The response gains `"partnership_profile"` (null for other roles), which is backward compatible.
- **`admin.update_user`:** the same shape as the telecaller branch: lock the profile, run the creator check, then
  `apply_profile_update`, with audit `partnership_profile_before/after`.
- **`provisioning.ADMIN_PORTAL_ROLES`** gains `partnership_head`. Its set-password and reset links then open `/admin/reset-password`,
  and `login_portal` is `"admin"`.
- **`auth.update_me`:** the phone-only rule for `partnership_manager`, with its own message.
- **`api/partnership.py`** (`router` `/partnership`, `admin_router` `/admin`):

| Route | Who | Returns |
|---|---|---|
| `GET /partnership/me` | manager | `{id, full_name, email, phone, active, division, partnership_profile: {employee_id, reporting_head: {id, full_name, active}}}` |
| `PATCH /partnership/profile` | manager | Phone only. Audit `partnership.profile_update` `{"fields": ["phone"]}`. Returns the `/me` shape |
| `GET /partnership/head/team` | head (direct reports), super_admin (all) | `{items: [{id, full_name, email, phone, active, employee_id}], total, limit, offset}`, inactive included; `q` |
| `GET /admin/partnership-managers` | super_admin, overseas_admin | Items add `reporting_head` and `head_active`; filters `active` and `q` (name, email, Employee ID) |
| `GET /admin/partnership-heads` | super_admin, overseas_admin | Active heads `{id, full_name, email}`; `q`. The picker |

All routes paginate with `limit` (default 50, max 100) and `offset`, sorted by name then id, in one joined query with no N+1. No
`/partnership` route takes a user id, so there is no IDOR surface. The `require_*` dependencies stay unused (2026-09-28 convention).

**Transactions and races** (as tel-001 §5.8):
- The user, profile, token and audit row are written in one commit, and the email is sent after the commit.
- The unique index decides a duplicate Employee ID, which comes back as a 409.
- `FOR SHARE` on the head row against a concurrent deactivation.
- No role writes its own Employee ID or head.

## 6. Frontend

- **`lib/navigation.ts`:**
  - `ROLE_DASHBOARD_PATH` gains `partnership_manager: "/partnership/dashboard"` and `partnership_head: "/partnership/head/team"`.
  - `PARTNERSHIP_MENU` (19 entries, PU8), `PARTNERSHIP_NAV` (the live entries + Profile), `PARTNERSHIP_HEAD_NAV` (Team).
  - A "Partnership managers" entry in `SUPER_ADMIN_NAV` and `PORTAL_NAV["overseas/admin"]`.
- **`middleware.ts`:** the protected regex and the matcher gain `partnership`, with the PU1 redirects. `/partnershipx` is not matched.
- **`WorkflowPanel` `ROLES_BY_DIVISION.global`** gains `partnership_head`. Only super_admin sees the global roles, and the API enforces
  it.
- **Admin login wording:** "For Super Admins, BDM Managers, Telecaller Managers and Partnership Heads." The tel-001 e2e assertion is
  updated to match.
- **Pages** (server components; `serverApi` → `accessUnavailable` → `PortalShell`):

| Page | Data | Content and states |
|---|---|---|
| `/partnership` | — | Redirects to `/partnership/dashboard` |
| `/partnership/dashboard` | `GET /partnership/me` | Greeting; the profile card; a "Your CRM menu" card listing the 18 coming-soon areas. A 403 shows the message |
| `/partnership/profile` | `/partnership/me` | `PartnershipProfileCard` (`<dl>`), plus the reused `TelecallerPhoneForm` with a `url` prop |
| `/partnership/head` | — | Redirects to `/partnership/head/team` |
| `/partnership/head/team` | `/auth/me` + `/partnership/head/team` | `PartnershipTeamTable` (caption, labelled `.table-wrap`, Previous/Next links). Empty state: "No partnership managers report to you yet." Past the end: a "Go to the first page" link |
| `/admin/partnership-managers`, `/overseas/admin/partnership-managers` | `AdminPartnershipPage` → `AdminPartnershipPanel` | The AdminTelecallerPanel pattern: create form, list (loading, error with Retry, empty, pager, search) and rows with Edit, Deactivate and Reactivate |

- **Create form:** full name, email, mobile, Employee ID and reporting head (`SearchableSelect` against `/admin/partnership-heads`).
  - With no heads, it shows "No active partnership head — a Super Admin must create one first" and the submit is disabled.
  - It double-submit guards with a ref, shows `welcomeLinkFeedback`, moves focus to the feedback, and keeps the typed values on error.
- **Row edit:** name, mobile, Employee ID and head; Esc cancels.
- **Deactivate:** an inline confirm, then `PATCH active:false`.
- **Rows on a phone:** below 640 px they become labelled cards, through `data-label` and the existing `.telecaller-list` CSS class,
  which is reused.

## 7. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | `super_admin` creates a head and a manager, and both set passwords from the link | `test_upc_001_provisioning.py`; e2e |
| AC2 | An `overseas_admin` creating a head → 403 (and an `it_admin` creating a manager → 403; an `overseas_admin` creating a manager → 201) | `test_upc_001_provisioning.py` |
| AC3 | The manager signs in at `/overseas/login` and lands on `/partnership/dashboard`; the head lands on `/partnership/head/team` from `/admin/login` | `test_upc_001_login.py`; `navigation.partnership.test.ts`; e2e |
| AC4 | The head sees direct reports only | `test_upc_001_reads.py`; e2e |
| AC5 | Existing roles are unaffected | lite regression set (§9) |
| N1 | Head FK not a head (or inactive) → 422 | provisioning + update tests |
| N2 | Duplicate Employee ID (any case) → 409 | provisioning + update tests |
| N3 | A manager calls a head route → 403 | reads tests |
| M1 | Signed out `/partnership/*` → the PU1 sign-in with `next` | `middleware.test.ts`; e2e |
| M2 | §32 menu: 19 entries in source order; only live ones linked | `navigation.partnership.test.ts` |

## 8. Tests

- **pytest:** `test_upc_001_migration.py`, `test_upc_001_provisioning.py`, `test_upc_001_update.py`, `test_upc_001_reads.py`,
  `test_upc_001_login.py`, `test_upc_001_access.py` (`can_see_commission`).
- **vitest:** `middleware.test.ts` (new cases), `navigation.partnership.test.ts`, `AdminPartnershipCreateForm.test.tsx`,
  `AdminPartnershipRow.test.tsx`, `PartnershipTeamTable.test.tsx`, `TelecallerPhoneForm.test.tsx` (url prop).
- **Playwright:** `upc-001-partnership-roles.spec.ts`:
  - super_admin creates a head (Users form) and a manager (Partnership managers page);
  - each activates from its link;
  - the manager lands on the dashboard and edits their phone;
  - the head lands on Team and sees the manager;
  - the signed-out redirects;
  - a 390 px check.

## 9. Regression risks (lite set)

| Risk | Guard |
|---|---|
| `create_user` rule order for other roles | `test_adm_001_admin_crud`, `test_bdm_001_*`, `test_tel_001_provisioning`, `test_enh_003_first_time_provisioning` |
| Reset link / `login_portal` | `test_bdm_001_reset_portal`, `test_bdm_001_admin_portal_links`, `test_tel_001_*` |
| `update_me` rule | `test_enh_006_change_password`, the tel-001 TL8 tests |
| Roles page lists the new roles | `test_adm_012_roles_permissions`, `test_rbac` |
| Middleware regex, landing map | `middleware.test.ts`, `navigation*.test.ts`, `LoginForm.next.test.tsx` |
| Admin login subtitle | `tel-001-telecaller-roles.spec.ts` (updated) |

## 10. Documentation (same change)

- `PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-116`.
- `RBAC_MATRIX.md`: §2.42.
- `API_CONTRACT.md`: §12AI.
- `ROLE_NAVIGATION.md`: Partnership Manager and Partnership Head sections.
- `SCREEN_CATALOG.md`: the new screens.
- The backlog's upc-001 status.

## 11. Completion gates

COMPLETE only when all of these pass:
- AC1–AC5, N1–N3, M1 and M2;
- the RBAC 403s;
- `alembic upgrade head` and the guarded downgrade;
- the lite regression set;
- `tsc`, eslint and `next build`;
- the 390 px and accessibility checks;
- the docs updated.
