# mgmt-001 — `partner` + `accountant` roles, sign-in, Command Center shell (design)

Date: 2026-10-12 · Backlog: `docs/delivery/MANAGEMENT_COMMAND_CENTER_BACKLOG.md` mgmt-001 · Source: `EVID-017` §1, §2, §33
(`DERIVED_BLUEPRINT`), scope authority M1–M14 (`EXPLICIT_APPROVAL`, 2026-10-08). Dependencies: none. Sequencing rule §5.1 (never in
parallel with rec-001 / upc-001): both merged to `main` long ago (checked at `452c54b1`). No migration (`users.role` is a free string).

## 1. What the item asks for

Two new global roles, their full account lifecycle on the existing provisioning path, sign-in at `/admin/login`, a landing page at
`/management`, the M13 tier helpers, `GET /management/me`, and the Command Center shell whose nav pillars follow §33.

Acceptance criteria (backlog): (AC1) `super_admin` creates two partners and an accountant, and all of them set passwords; (AC2) an
`it_admin` creating a partner → 403; (AC3) a partner lands on `/management`; (AC4) a signed-out `/management/*` redirects to
`/admin/login?next=`; (AC5) no existing role's access changes. Negative: an accountant opening a partner-only page → 403. Edge: a
deactivated partner's sessions end; the last active partner cannot be deactivated.

## 2. Decisions (recommended answers, applied under the owner's standing build-session instruction; `UNVERIFIED` / `NEEDS_CONFIRMATION` at sign-off)

| # | Point | Decision |
|---|---|---|
| MG1 (Q-01) | Partner cap; who creates the accountant | **No hard cap** (M2 already says "no hard cap of 2"). **Only `super_admin` creates partners and accountants** in mgmt-001. Partners have no `/admin/*` access (MG2), so letting them create accountants would widen `ensure_admin`; it can be a later item |
| MG2 (Q-02) | Partner powers outside management data | **Read + management-only.** No existing module gate admits `partner` or `accountant` (AC5) |
| MG3 (Q-34) | Paths | `/management/*`; both roles sign in at `/admin/login` and land on `/management`; set-password / reset links open the admin portal's pages (`ADMIN_PORTAL_ROLES`) |
| MG4 (M13) | Tiers | `services/management_access.py`: `can_view_operational` = partner, super_admin; `can_view_finance` = partner, accountant; `can_view_partner_only` = partner. Any other role has no tier: `GET /management/me` → 403 |
| MG5 | `GET /management/me` | `{id, full_name, role, tiers: {operational, finance, partner_only}}` for the three tier roles; 401 signed out; 403 otherwise |
| MG6 | Last active partner | `PATCH /admin/users/{id}` `active: false` on the last active partner → **422** "At least one partner must stay active". Active partner rows are locked `FOR UPDATE` before counting, so two concurrent deactivations of the last two serialise |
| MG7 | Session end | Deactivation already ends every session (`get_current_user` loads active users only; refresh likewise). No new mechanism |
| MG8 | Shell | `MANAGEMENT_PILLARS` in `lib/navigation.ts`: §33's five pillars + Business Intelligence (with §1's Strategy entries), each entry naming its item and tier, `live: false` until that item lands. The sidebar shows the Command Center home + live entries the tier allows; the home lists the pillars the tier allows, with upcoming entries as plain text (the upc-001 PU8 idiom, never a dead link) |
| MG9 | Entry tiers | Operational dashboards (§3, §11–§21), plans, discussions, to-do, meetings → operational. Ledger, revenue, expenses, P&L, salaries, marketing budget/ROI, accounts → finance. Investments, capital → partner-only. Mixed pages (health score, this-month performance, monthly review) → **partner-only until their own item decides** (conservative) |
| MG10 | super_admin | Operational tier (M13): may open `/management` and sees only operational pillars; a "Management Command Center" link joins `SUPER_ADMIN_NAV` |
| MG11 | Commission (M3) | Not changed here: `partnership_access.COMMISSION_ROLES` gets `partner` with mgmt-006 / 023 / 034, when a partner can reach those pages |
| MG12 | Demo data | Seed `partner.one@`, `partner.two@`, `accountant@edusphere.local` (global) for QA |

## 3. Design

Backend
- `core/rbac.py`: `partner: {"management:*"}`, `accountant: {"management:finance"}`.
- `api/admin.py` `create_user`: `role in {"partner","accountant"} and user.role != "super_admin"` → 403 (before the division gate, the
  BDM/telecaller idiom, so an `it_admin` gets AC2's 403 whatever division it sends); both added to the `global` role set.
  `update_user`: MG6 guard next to the other deactivation guards.
- `services/provisioning.py`: both roles join `ADMIN_PORTAL_ROLES` (set-password link + `login_portal: "admin"`).
- `services/management_access.py` (new): `MANAGEMENT_ROLES`, the three `can_view_*` helpers, `tiers(user)`, `require_management(user)`.
- `api/management.py` (new): `GET /management/me`; registered in `main.py`.
- `services/mailer.py`: no change (the welcome email prints the role string, as for every global manager).

Frontend
- `middleware.ts`: `/management` protected; signed out → `/admin/login?next=`.
- `lib/navigation.ts`: `ROLE_DASHBOARD_PATH` partner/accountant → `/management`; `SUPER_ADMIN_NAV` link. `lib/management.ts` (new, so
  the shared hot-spot `navigation.ts` stays a two-line change): types, role labels, `MANAGEMENT_PILLARS`, `pillarsFor(tiers)`,
  `managementNavFor(tiers)`.
- `app/management/page.tsx`: server page; `accessUnavailable(e, "/admin/login")` on 401/403; `PortalShell` with the tier nav (super_admin
  keeps `SUPER_ADMIN_NAV`). `components/ManagementPillars.tsx`: the pillar cards (data-only server component).
- `WorkflowPanel.tsx` `ROLES_BY_DIVISION.global` + both roles; admin login / forgot-password copy names Partners and Accountants.

## 4. Tests

- API (`tests/test_mgmt_001_*.py`): create partner ×2 + accountant by super_admin, set password via welcome token, login at `global`;
  `it_admin`/`overseas_admin` → 403 for both roles; wrong division → 422; `/management/me` per role (partner, accountant, super_admin,
  it_admin 403, anon 401); tier helper truth table; last-partner 422 and the 2-partner case; deactivated partner → 401; reset-password
  `login_portal: "admin"`; existing global roles still creatable (AC5 spot check).
- Web (vitest): middleware redirect; `dashboardPathFor`; `managementNavFor` by tier; `ManagementPillars` renders tier-filtered pillars, no
  links for non-live entries; the page's access-unavailable path.
- E2E (Playwright `mgmt-001-command-center.spec.ts`): super admin creates partner → set password → sign in → `/management`; signed-out redirect;
  accountant sees Finance but not partner-only entries.

## 5. Risks

Shared role files (admin user create/update, middleware, navigation): the change is additive. `SUPER_ADMIN_NAV` gains one link (exact-list
tests, if any, updated). No existing gate is widened, so AC5 holds by construction and by the it_admin/overseas_admin spot checks.
