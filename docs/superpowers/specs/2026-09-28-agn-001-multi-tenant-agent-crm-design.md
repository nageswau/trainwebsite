# AGN-001 — Multi-Tenant Agent CRM: Agent Organisation as Tenant, Master Accounts — Design

**Status:** Design approved in-session, 2026-09-28, section by section (data model, gate and scoping, API,
frontend, testing). Superpowers architectural path: brainstorming → this design doc → `writing-plans` next.
Written spec awaiting user review.

**Source requirement:** `functionalities/edusphere_markdown/Agent CRM Functionalities.md` (`EVID-015`,
`DERIVED_BLUEPRINT`) §1, §3, "Best approach". **Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md`
§AGN-001 (AGN-001-AC01…AC10). **Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` →
`DEC-SCOPE-034` (D1–D13, `EXPLICIT_APPROVAL`, user, 2026-09-28; number provisional). This spec adds the
design decisions in §3 (E1–E12), also confirmed in-session.

**Branch:** `feature/agn-001-multi-tenant-agent-crm`.

## 1. Scope

**In scope:** agent organisation (tenant) with status; Master members with display codes; the approval gate
and all agent data scoping move to the organisation; Overseas Admin approve / reject / suspend / reinstate;
Master invite and deactivate; migration of existing agents; admin-created agents; commission notifications
to all active Masters.

**Out of scope (D13):** Staff logins (`S001`…), staff assignment and ownership, staff performance, CRM
settings, the rest of `EVID-015`. No change to `UserOut`, JWT/cookies, non-agent roles' scoping, ADM-001's
user PATCH (E9), the frozen `app/agents/` package, or any Zoho/CRM webhook code.

## 2. Approaches considered

| Approach | Summary | Verdict |
|---|---|---|
| **A. Membership scoping** | New `agent_orgs` + `agent_org_members`; existing rows keep `agent_id` = acting user; agent queries filter `agent_id IN (org member user ids)` | **Chosen (E1).** Business tables untouched; one source of truth (a user belongs to one organisation for good); admin/counselor paths that set `agent_id` keep working |
| B. `org_id` column | Add and backfill `org_id` on `agent_students`, `agent_commissions`, `overseas_applications` | Rejected: migrates three business tables and every write path must keep `org_id` and `agent_id` consistent — a new drift failure mode |
| C. Re-key `agent_id` to the organisation | Point `agent_id` at the org | Rejected: breaks the FK to `users`, loses attribution, breaks every consumer |

## 3. Decisions

`DEC-SCOPE-034` D1–D13 apply unchanged, except D2 as corrected by E2. Design decisions confirmed
in-session, 2026-09-28 (`EXPLICIT_APPROVAL`):

- **E1 — Scoping approach A** (§2).
- **E2 — Agency name optional.** Registration accepts an optional agency name; blank or missing falls back to
  the user's full name. Existing callers keep working. (Corrects D2's "requires an agency name".)
- **E3 — Deactivation disables login.** Deactivating a Master also sets `users.active = false` and revokes
  any open welcome link. The membership stays deactivated even if an admin re-enables the login.
- **E4 — Old approve/reject routes keep their semantics.** `POST /overseas-admin/agents/{agent_id}/approve|reject`
  keep any-state behaviour and their `agent.approve` / `agent.reject` audit rows, and additionally set that
  agent's organisation to `active` / `rejected`.
- **E5 — Invite = real account.** An invited Master is a `users` row with an unusable password and a
  `DEC-SCOPE-019` welcome token. "Active or pending invite" (D4) = member `status = 'active'`; no separate
  invite state.
- **E6 — Codes.** `code = f"{prefix}-M{seq:03d}"`; `seq = org.master_seq + 1` under the organisation row lock.
- **E7 — Missing organisations are created on sync.** `_sync_role_assignment` (registration and every login)
  and admin user-create call `ensure_agent_org`, using the migration's status mapping. Agents created by the
  seed, tests or any other path get an organisation on first login.
- **E8 — `UserOut` unchanged.** Organisation data is served by the team endpoint and the portal, never by
  login / refresh / me responses.
- **E9 — ADM-001 unchanged.** `PATCH /admin/users/{id}` still toggles login only; membership status is
  unaffected, so a re-enabled deactivated Master stays denied and does not count toward the limit.
- **E10 — Denial messages.** Pending and rejected keep the current text "Agent registration is pending
  approval"; suspended returns "Your agency's account is suspended"; a deactivated member returns
  "Your Master account is deactivated" (reachable only if an admin re-enabled the login, E9).
- **E11 — Legacy consistency.** Approve and reject (new and old routes) also set `approval_status` on the
  organisation's Master assignments. Suspend and reinstate do not touch assignments. The gate reads only
  the organisation and the member.
- **E12 — Linking a student is organisation-wide.** A student already linked by any member of the
  organisation → `409 "Student is already linked to this agency"`. Two different organisations may still
  refer the same student (today's behaviour).

## 4. Data model — migration `0045_agent_orgs` (after `0044_skill_india_certification`)

**`agent_orgs`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(160) | agency name |
| `prefix` | String(8), unique | D5, e.g. `ABC`, `ABC2` |
| `status` | String(20), indexed | CHECK in (`pending`, `active`, `rejected`, `suspended`) |
| `master_seq` | Integer, default 0 | highest Master number ever issued; CHECK `>= 0` |
| `status_changed_by_user_id` | UUID FK `users.id`, nullable | |
| `status_changed_at` | timestamptz, nullable | |
| `created_at`, `updated_at` | `TimestampMixin` | |

**`agent_org_members`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK `agent_orgs.id`, indexed | |
| `user_id` | UUID FK `users.id`, **unique** | one organisation per user, for good |
| `role` | String(20) | CHECK = `master` (room for Staff later) |
| `seq` | Integer | unique with `org_id` |
| `code` | String(16), unique | `ABC-M001` |
| `status` | String(20) | CHECK in (`active`, `deactivated`) |
| `invited_by_user_id` | UUID FK `users.id`, nullable | |
| `deactivated_by_user_id` | UUID FK `users.id`, nullable | |
| `deactivated_at` | timestamptz, nullable | |
| `created_at`, `updated_at` | `TimestampMixin` | |

**ORM:** `User.agent_membership` — view-only, `uselist=False`; `AgentOrgMember.org` relationship.

**Prefix (D5):** Latin letters `[A-Za-z]` of the name, first three, uppercased, right-padded with `X` to three
(`A1 Consultants` → `ACO`, `AB` → `ABX`, no Latin letters → `AGT`). Collision: the lowest free of `ABC`,
`ABC2`, `ABC3`, … among existing prefixes.

**Backfill (D10):** for every `users.role = 'agent'`, ordered by `users.created_at, users.id`: one
organisation named `profile->>'agency_name'` if non-blank, else `full_name`; prefix as above; status
`active` if that user's `(division='overseas', role='agent')` assignment is `approved`, else `pending`
(pending, rejected or missing); one member `seq = 1`, code `<prefix>-M001`, status `active`;
`master_seq = 1`. A legacy agent whose login is disabled (`users.active = false`) is still migrated as an
active `M001` (D10); its login stays disabled, as today. No existing row is modified. The prefix function is copied into the migration (migrations
do not import app code).

**Downgrade:** drop `agent_org_members`, then `agent_orgs`. Only rows in the new tables are lost.

**Runtime creation (`ensure_agent_org`, E7):** idempotent — returns the existing member if any. Otherwise
computes the prefix, inserts the organisation and `M001` inside a savepoint; on a unique violation on
`prefix` it recomputes and retries, at most 5 attempts, then `409 "Please try again"`.

## 5. Backend

### 5.1 New module `app/services/agent_orgs.py` (functions only, no class layer)

- `derive_prefix_base(name) -> str` and `next_free_prefix(db, base) -> str`
- `ensure_agent_org(db, user, *, agency_name=None, status=None) -> AgentOrgMember` (no commit)
- `org_member_ids(user)` → `select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == …)` subquery
- `lock_org(db, org_id) -> AgentOrg` (`SELECT … FOR UPDATE`; 404 if missing)
- `agent_denial_reason(user) -> str | None` (E10)
- `active_master_users(db, org_id) -> list[User]` (notifications, D12)
- `transition_org(db, org, action, actor)` — validates the move, sets status/actor/time, writes the
  `agent_org.<action>` audit row, applies E11
- `invite_master(db, org, actor, full_name, email, phone)` and `deactivate_master(db, org, member, actor)`

### 5.2 Gate

- `deps.get_current_user` adds `selectinload(User.agent_membership).selectinload(AgentOrgMember.org)`.
- `rbac.agent_is_approved(user)` → `agent_denial_reason(user) is None`: a non-agent passes; an agent passes
  only with `membership.status == 'active'` and `membership.org.status == 'active'`.
- `workflows._require` and `portal()` raise `403` with `agent_denial_reason(user)` (E10).
- Suspension is effective on the next request because the membership and organisation are re-read each
  request.

### 5.3 Scoping — every agent read and write

| Site | Today | After |
|---|---|---|
| `workflows._assigned_application` (agent branch; reached from document upload and download) | `item.agent_id == user.id` | `item.agent_id` in the caller's organisation's member ids |
| `POST /workflows/overseas/applications` link check | `AgentStudent.agent_id == user.id` | member ids; `agent_id` stored = `user.id` |
| `GET /workflows/overseas/applications` | `agent_id == user.id` | member ids |
| `POST /workflows/overseas/documents` link check | `AgentStudent.agent_id == user.id` | member ids |
| `GET /workflows/overseas/documents/{id}/download` | `AgentStudent.agent_id == user.id` | member ids |
| `GET /workflows/overseas/agent/students` | `agent_id == user.id` | member ids |
| `POST /workflows/overseas/agent/students` | per-user duplicate check | lock org; organisation-wide duplicate check (E12); `agent_id = user.id` |
| `GET /workflows/overseas/agent/commissions` | `agent_id == user.id` | member ids |
| `POST /workflows/overseas/agent/commissions/{id}/claim` | `item.agent_id != user.id` → 404 | not in member ids → 404 |
| `services/portal._agent` (dashboard, students, applications, documents, commissions, reports) | `agent_id == user.id` | member ids |

### 5.4 Endpoints

**Registration** — `RegistrationRequest.agency_name: str | None` (trimmed, max 160). `register` calls
`_sync_role_assignment`, which calls `ensure_agent_org(..., agency_name=…)` for `role='agent'`. Response
unchanged.

**Admin user-create** — for `role='agent'`, `ensure_agent_org(..., agency_name=profile.get('agency_name'),
status='pending')` in the same transaction. Response unchanged.

**Overseas Admin** (`overseas_admin` or `super_admin`, else `403`), new router in `admin.py` beside
`agents_router`:

| Route | Transition | Notes |
|---|---|---|
| `GET /overseas-admin/agent-orgs?status=` | — | `[{id, name, prefix, status, created_at, masters: [{id, code, full_name, email, status}]}]`, newest first; not paginated (as `/overseas-admin/agents`); invalid `status` filter → 422 |
| `POST /overseas-admin/agent-orgs/{id}/approve` | `pending`/`rejected` → `active` | |
| `POST …/reject` | `pending` → `rejected` | |
| `POST …/suspend` | `active` → `suspended` | |
| `POST …/reinstate` | `suspended` → `active` | |

Each transition: lock the org row, `404` if unknown, `409 "Cannot <action> an organisation that is <status>"`
if not allowed (including repeats), audit `action='agent_org.<action>'`, `entity_type='agent_org'`,
`entity_id=<org id>`, `outcome=<new status>`, `metadata_json={'from': <old status>}`, same transaction (fail
closed, `SEC-001`). Response `{id, status}`.

**Old routes (E4):** unchanged responses and audit rows; additionally set the agent's organisation to
`active` / `rejected` (via `ensure_agent_org` first, so a legacy agent without an organisation gets one).

**Master team** — new `app/api/agent_team.py`, mounted under `/workflows`, gated exactly like other agent
routes (`_require(user, {"agent"}, "overseas")`) plus `membership.role == 'master'`:

| Route | Behaviour |
|---|---|
| `GET /workflows/overseas/agent/team` | `{org: {id, name, prefix, status}, masters: [{id, code, full_name, email, status, invite_pending}], limit: 3}`; `invite_pending` from `provisioning_statuses` |
| `POST /workflows/overseas/agent/team/masters` `{full_name, email, phone?}` | lock org; `422 "This agency already has 3 active Masters"` if ≥3 active; `409 "Email already exists"`; create `User(role='agent', division='overseas', password_hash=unusable_password_hash(), active=True)`, its assignment (`approval_status='approved'`, `assigned_by_user_id=actor`), member `seq = master_seq + 1`; `issue_welcome_token`; audit `agent_org.master_invite`; commit; then `deliver_welcome_link`; `201 {member, **delivery}` |
| `POST /workflows/overseas/agent/team/masters/{member_id}/deactivate` | lock org; `404` if the member is not in the caller's organisation; `409 "Already deactivated"`; `422 "An agency must keep at least one active Master"` if it is the last active one; set member `deactivated`, `users.active = false`, `revoke_welcome_tokens`; audit `agent_org.master_deactivate`; commit; `200 {member}` |

Validation errors use the project's standard error shape (`API_CONTRACT.md` §0.3). No new dependency.

### 5.5 Notifications (D12)

`_maybe_trigger_agent_commission` ("Commission estimated") and the admin manual commission create
("Commission eligible") notify every active Master of the organisation that `agent_id` belongs to; if
`agent_id` has no membership, the agent user alone (today's behaviour).

## 6. Frontend

- **`RegisterForm.tsx`** — `account_type` becomes a controlled select; when `agent`, an "Agency name
  (optional)" input (`maxLength=160`, `autoComplete="organization"`) is shown and sent as `agency_name`.
- **`AgentApprovalPanel.tsx`** — reads `GET /overseas-admin/agent-orgs`; groups Pending / Active /
  Suspended / Rejected; card = agency name, prefix, each Master's code, name, email; actions: Pending →
  Approve / Reject, Rejected → Approve, Active → Suspend (inline confirm), Suspended → Reinstate.
  States: loading ("Loading agent organisations…"), **error with Retry** (replaces today's silent empty list),
  per-group empty text, per-card busy ("Working…") with a ref-based double-click guard (`SchoolTeamPanel`
  ENH010-QA-01 precedent), per-card inline error (`role="status"`, `aria-live="polite"`).
- **New `AgentTeamPanel.tsx`** at `/overseas/agent/team` — `lib/navigation.ts` adds "Team";
  `services/portal._agent` adds a read-only `team` section (code, name, email, status); `WorkflowPanel`
  mounts the panel for `role === "agent" && section === "team"`. Invite form (full name, email, phone);
  disabled with "Limit reached: 3 active Masters. Deactivate one to invite another." at the limit; list with
  "Invite pending" badge; Deactivate with inline confirm, hidden for the last active Master (server `422`
  still displayed on a race); self-deactivation redirects to `/overseas/login`. States: loading, error with
  Retry, busy + ref guard, per-row inline errors, delivery result after invite ("Invite sent." /
  "Invite created, but the email was not delivered. Ask Overseas Admin to re-send the link.").
- **Dashboard** — one added metric "Your code" (`ABC-M001`).
- Layout at 320 / 768 / 1280 px with no horizontal scroll; every control labelled.

## 7. Security

- Tenant isolation on every agent read and write (§5.3), proved by the §9 matrix; cross-organisation IDs
  return `404` (claim, deactivate) or `403` (existing route semantics), never data.
- Gate evaluated server-side each request; no client-side trust.
- Transitions and member changes lock the organisation row; audit rows share the transaction (fail closed).
- Invite reuses `DEC-SCOPE-019`: hashed single-use token, 72-hour expiry, never logged; mail sent after
  commit so a mail failure cannot roll back the account.
- A deactivated Master cannot log in (E3) and, if re-enabled by an admin, is still denied (E9, E10).

## 8. Acceptance criteria

AGN-001-AC01…AC10 in `ENHANCEMENT_BACKLOG.md` §AGN-001, read with E2 (agency name optional) and E4 (old
routes). Testable restatement:

| AC | Pass condition |
|---|---|
| AC01 | Registering as an agent (with or without agency name) yields exactly one `pending` org and one active `M001` member; prefix per D5 |
| AC02 | A `pending`/`rejected` org's Master gets `403` "Agent registration is pending approval" on every agent route and portal section |
| AC03 | Each new transition returns 200 and writes one `agent_org.<action>` audit row; invalid moves → 409 with no audit row and no change; old routes keep `agent.*` rows and set the org |
| AC04 | After suspend, the member's next request to any agent route → `403` "Your agency's account is suspended"; `/auth/me`, logout, notifications → 200; after reinstate → allowed |
| AC05 | After `0045`, each pre-existing agent is `M001` of its own org (approved → active; pending/rejected/missing → pending) and sees exactly the rows it saw before |
| AC06 | For every route in §5.3 and the team routes, org A's Master never receives or changes org B's data |
| AC07 | 4th active Master invite → 422; last active Master deactivation → 422; codes strictly increase and are never reassigned; no reactivation path exists |
| AC08 | Only an active Master of the org can invite/deactivate; the invite issues a `DEC-SCOPE-019` welcome token and email |
| AC09 | Admin-created agent → `pending` org + `M001` |
| AC10 | Commission estimated/eligible notifications reach every active Master and no one else in or outside the org |

## 9. Tests (written first, per behaviour; real runs, never judged by reasoning)

Existing tests must pass **unchanged**; a needed edit to an existing test is treated as a regression signal
and brought back to the user.

- `apps/api/tests/test_agn_001_registration_and_gate.py` — AC01, AC02, AC04 (incl. `/auth/me`, logout,
  notifications), AC09, E2 fallback, D5 prefix cases (padding, `AGT`, `ABC2`), E7 legacy agent without org,
  E10 messages.
- `apps/api/tests/test_agn_001_org_admin.py` — AC03: every valid/invalid transition, audit rows, 403/404,
  old-route E4 behaviour, E11 write-through.
- `apps/api/tests/test_agn_001_team.py` — AC07, AC08: invite (token, audit, delivery after commit), limit,
  409 email, last-Master 422, E3 login disabled + link revoked, `M004` after deactivating `M002`, non-Master
  and other-org 403/404.
- `apps/api/tests/test_agn_001_tenancy.py` — AC06 parametrised matrix over the 8 workflow routes, 7 portal
  sections and 3 team routes; in-org sharing (`M002` sees and claims `M001`'s commission); AC10.
- Race tests (`asyncio.gather`): two invites for the last place → one 201 + one 422; cross-deactivation →
  one 200 + one 422; same-prefix registrations → two 201 with distinct prefixes; same-student link by two
  Masters → one 201 + one 409.
- `apps/api/tests/test_agn_001_prefix.py` — unit tests for `derive_prefix_base` / `next_free_prefix`.
- Migration (AC05): `upgrade → downgrade 0044 → upgrade` on a throwaway database seeded with approved,
  pending, rejected and login-disabled agents (and one with `profile.agency_name`); verify organisations,
  statuses, prefixes, and unchanged data access.
- Vitest: `AgentTeamPanel`, `AgentApprovalPanel`, `RegisterForm` (loading, error+retry, empty, limit, success,
  failure, confirm, 422 display, agency-name field).
- Playwright `apps/web/tests/e2e/agn-001-multi-tenant.spec.ts`: register with agency name → pending message →
  admin approves org → Master invites → team shows `M002` → admin suspends → suspended message → reinstate.

## 10. Regression risks

| Risk | Guard |
|---|---|
| AGT-001-AC02 pending deny lost in the gate rewrite | unchanged `test_agt_001_*`, `test_role_assignments` + AC02 tests |
| SEC-001 audit rows | old routes keep `agent.*` rows (E4); unchanged `test_sec_001_*` |
| Scope re-key hides or leaks data | AC05 migration check + AC06 matrix + unchanged `test_agt_002/003/004`, `test_rpt_002` |
| Async lazy-load crash on `agent_membership` | eager-load in `get_current_user`; `UserOut` unchanged (E8) |
| Legacy/seed/test agents without an org denied | E7 creation on sync; unchanged fixtures must pass |
| `AgentApprovalPanel` / `adm-001` / `agt-*` e2e | kept routes (E4); agent role option unchanged; e2e rerun |
| Migration on live data | additive only; reversible; throwaway-db round trip |

## 11. Completion gates (not claimed by implementation alone)

All AGN-001 ACs green; full backend suite (baseline: the 14 provider-credential failures) and full e2e
suite; `tsc`, eslint (no new errors), `npm run build`; single alembic head `0045`; migration round trip;
browser check at 320 / 768 / 1280; docs updated (`DATA_MODEL.md` §6.8a from planned to built,
`API_CONTRACT.md` §8, `RBAC_MATRIX.md` §2.8, `SCREEN_CATALOG.md` / `screen_catalog.json` /
`ROLE_NAVIGATION.md` for the Team screen, RTM row, backlog status).
