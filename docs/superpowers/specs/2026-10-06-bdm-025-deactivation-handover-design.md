# bdm-025 — BDM deactivation, portfolio handover, manager change (design)

- **Item:** `bdm-025` (`docs/delivery/BDM_CRM_BACKLOG.md` §4). Depends on bdm-002, bdm-006, bdm-008, bdm-010 — all merged on
  `main` @ `442ce465`. The owner confirmed in-session (2026-10-06) that "merged with verified QA evidence" counts as completed for
  bdm-006 (status line stale) and bdm-008 ("VERIFIED — ready for owner sign-off").
- **Decision:** `DEC-SCOPE-082`. **Migration:** `0082_bdm_assignment_history` (down_revision `0081_lead_stage_pipeline`). Last renumbered on merging `main` @ `3986958c`
  (tel-004 took `081` / `0081_lead_stage_pipeline`). Drafted as
  `DEC-SCOPE-076` / `0078`, after `0077_bdm_tasks_followups`. It was renumbered on merging `main` @ `230a043f`, where tel-017,
  tel-003 and bdm-005 took `076`–`078` and `0078`–`0079`, so it became `079`. Then it became `080` on merging `main` @ `6655e284`,
  where bdm-013 (no migration) took `079`. Then it became `081` / `0081` on merging `main` @ `a38955d5`, where tel-022 took
  `080` / `0080_tel_targets`. Per the backlog's §6.2 rule, the branch that merges second renumbers.
- **Branch / worktree:** `worktree-bdm-025` at `.claude/worktrees/bdm-025`, from `origin/main` @ `442ce465`.
- **Evidence:** `EVID-016` (`BDM Functionalities.md`, `DERIVED_BLUEPRINT`) §1 BDM Management, lines 5–25 (Reporting Manager,
  Active/Inactive); backlog `DEC-SCOPE-055` D3, D4, D10 (Q-01); bdm-001 B7 (type fixed, transfers are bdm-025); bdm-010 T2/T3
  (the approver is resolved at decision time; super_admin decides only while the manager is inactive).
- **Skills applied:** superpowers:brainstorming, api-and-interface-design, frontend-ui-engineering, security-and-hardening.

## 1. Goal

An admin can deactivate a BDM without stranding their live work. Either it moves, in one atomic and audited step, to another
active BDM of the same module (who is notified), or it is explicitly kept with the deactivated BDM and handed over later.
History stays with the person who did it. A BDM manager who still has BDMs cannot be deactivated until a replacement manager takes
them over, and pending travel approvals follow the BDM's current manager.

## 2. Scope

| In | Out |
|---|---|
| `GET /admin/bdms/{id}/portfolio` (counts preview) | A queue screen for "unassigned" work (owner: keep + hand over later) |
| `POST /admin/bdms/{id}/deactivate` `{mode, reassign_to}` | Changing a BDM's type (B7 stands: 422) |
| `POST /admin/bdms/{id}/handover` `{reassign_to}` (inactive BDM) | Reminder owner resolution (bdm-012 reads owners at fire time) |
| `POST /admin/bdm-managers/{id}/deactivate` `{reassign_to}` (super_admin) | A reader for `bdm_assignment_history` (data + audit only) |
| `PATCH /admin/users/{id}` refuses deactivating a BDM, or a manager with BDMs (422) | GDPR erasure's `active = False` (a separate, rare admin flow; unchanged) |
| `GET /admin/bdm-managers` rows gain `bdm_count` (additive) | A new `/activate` route: the existing PATCH `active: true` reactivates |
| `bdm_assignment_history`, also written by bdm-002's single reassign | |
| Admin BDMs page: deactivate dialog with counts, "Hand over" for inactive BDMs, a "BDM managers" card (super_admin) | |

## 3. Owner decisions (2026-10-06, in-session, `EXPLICIT_APPROVAL`, structured questions)

| # | Question | Answer |
|---|---|---|
| L1 | Dependencies not formally COMPLETE (bdm-006, bdm-008) | **Proceed:** merged on `main` with verified QA evidence counts as completed |
| L2 | The deactivated BDM's trips | **Cancel the ones not yet started** (`travel_status = planned`, any approval state) with the reason "BDM deactivated". A trip in progress stays with the original BDM |
| L3 | "Leave unassigned for the manager's queue" | **Keep + hand over later:** `mode=leave` keeps items on the inactive BDM (already shown "(inactive)" in organization views). "Hand over" stays available on the inactive BDM's row |
| L4 | A manager who has BDMs | **Bulk move:** a super_admin-only action moves every BDM (active or not) to a replacement active manager in one transaction. The generic Users page refuses with a 422 that says where to do it |
| L5 | What moves | **Live items only:** non-archived organizations; appointments that are scheduled, confirmed or rescheduled and start in the future; open follow-ups and tasks. Archived organizations, past appointments with no outcome, and every finished record stay with the original BDM |

**Defaults taken (consistent with bdm-001/002/010):**
- Who may act: `super_admin`, plus the creator roles per Q-01 (`it_admin` → College, `overseas_admin` → Agent/School) via
  `require_creator_may` (403). Managers are deactivated by `super_admin` only.
- An invalid target gets one 422 message ("Choose an active BDM of the same module"), so the route cannot probe users (bdm-002 §12.3).
- No idempotency key: a repeat finds the BDM inactive → 409.
- No new rate limiter (admin-only, bounded by portfolio size).

## 4. Data model — migration `0082_bdm_assignment_history`

| Column | Type | Rule |
|---|---|---|
| `id` | uuid PK | |
| `entity_type` | varchar(20) | CHECK in (`organization`, `appointment`, `task`) |
| `entity_id` | uuid | no FK: polymorphic. Rows are never deleted, and neither are the entities (archived / cancelled instead) |
| `from_user_id`, `to_user_id`, `actor_user_id` | uuid FK users RESTRICT | |
| `reason` | varchar(30) | CHECK in (`bdm_deactivated`, `portfolio_handover`, `organization_reassigned`) |
| `created_at` | timestamptz default now() | |

Indexes: `(entity_type, entity_id)` and `(from_user_id)`. The `0001` `create_all` guard follows 0072's idiom. The downgrade refuses
while rows exist (history would be lost); otherwise it drops the table. Existing tables are untouched.

## 5. Rules

### 5.1 Open portfolio (L5) — one definition, used by preview, deactivate and handover
- organizations: `assigned_bdm_user_id = A AND archived_at IS NULL`
- appointments: `bdm_user_id = A AND status IN (scheduled, confirmed, rescheduled) AND starts_at > now()`
- tasks: `assignee_user_id = A AND status = 'open'`
- trips (preview + deactivate only): `bdm_user_id = A AND travel_status = 'planned'` → cancelled (L2)

### 5.2 `POST /admin/bdms/{id}/deactivate` — `BdmDeactivate {mode: "reassign" | "leave", reassign_to: UUID | null}`, extra fields forbidden
Order (every refusal happens before any write):
1. `ensure_admin`; the target user must be a `bdm` with a profile, otherwise 404 "BDM not found". The division rule matches `update_user`.
2. `require_creator_may(actor, profile.bdm_type)` → 403.
3. Body: no `mode` → 422 "Choose who takes over this BDM's open work" (AC1). `reassign` without `reassign_to`, or `leave` with one → 422.
4. Lock: the source's open organizations `FOR UPDATE`, then the source user `FOR UPDATE` (with `populate_existing`). This is the
   same order as bdm-002's reassign (organization, then user), so the two cannot deadlock.
5. Source already inactive → 409 "This BDM is already inactive".
6. `reassign`: the target is locked `FOR SHARE`. It must be an active `bdm` with a profile of the same `bdm_type` and not the
   source → else 422 "Choose an active BDM of the same module".
7. Writes in one transaction:
   - `reassign`: bulk `UPDATE … RETURNING id` for each entity in §5.1, plus one history row per moved item
     (`reason = bdm_deactivated`).
   - Trips: cancel each not-started trip (`travel_status = cancelled`, `cancelled_at`) with a `bdm.trip_cancel` audit row whose
     metadata carries `reason: "BDM deactivated"` (travel's own `audit`).
   - `user.active = False`; `revoke_welcome_tokens`.
   - Audit `bdm.deactivate` on entity `user`, with metadata `{mode, reassign_to, moved: {organizations, appointments, tasks}, trips_cancelled}`.
   - When something moved, the target gets an in-app + email notification (`workflows._notify_user`): "Work handed over to you",
     with the counts and the deactivated BDM's name, linking to `/bdm/organizations`.
8. Response 200: `{id, active: false, mode, moved: {...}, trips_cancelled}`.

### 5.3 `POST /admin/bdms/{id}/handover` — `BdmHandover {reassign_to: UUID}`
Same steps 1–2, 4 and 6. The source must be **inactive** (active → 409 "Deactivate this BDM first"). Nothing open → 409 "No open
work to hand over". The writes are the same moves with `reason = portfolio_handover`, audit `bdm.portfolio_handover`, and the
notification. Trips are not touched (an inactive BDM's not-started trips were already cancelled).

### 5.4 `GET /admin/bdms/{id}/portfolio`
Steps 1–2, then `{organizations, appointments, tasks, trips}` counts (§5.1), readable for active and inactive BDMs.

### 5.5 Manager change and approvals (AC3)
This already works: `PATCH /admin/users/{id}` `bdm_profile.reporting_manager_user_id` (bdm-001). Pending trips are decided by the
**current** manager (T2), so they follow with no data change. bdm-025 adds tests that prove it.

### 5.6 `POST /admin/bdm-managers/{id}/deactivate` — `BdmManagerDeactivate {reassign_to: UUID | null}` (AC4, L4)
`super_admin` only (403). The source must be a `bdm_manager` (404) and active (409). Lock its BDM profiles `FOR UPDATE`, then the
source user `FOR UPDATE`. If any BDM (active or not) reports to it: `reassign_to` is required and must be another **active**
`bdm_manager`, locked `FOR SHARE` → else 422 "Choose another active BDM manager". Then:
- every profile moves to the target manager;
- the source is deactivated and its welcome tokens revoked;
- audit `bdm_manager.deactivate` `{reassign_to, moved_bdm_ids}`;
- if any BDMs moved, the target is notified: "N BDMs now report to you" → `/bdm/manager/team`.

With no BDMs, `reassign_to` may be omitted.

### 5.7 `PATCH /admin/users/{id}` (existing route; one new refusal before any write)
- `active: false` on an active `bdm` → 422 "Deactivate a BDM from the BDMs page, choosing who takes over their open work".
- `active: false` on an active `bdm_manager` with ≥1 BDM → 422 "This manager has N BDM(s). Move them to another manager first
  (BDMs page → BDM managers)".
- **422, not 409:** the Users page treats a 409 as the trainer "confirm cascade" prompt.
- Reactivation (`active: true`) is unchanged and restores login only, never the old portfolio.

### 5.8 bdm-002 single reassign
`POST /bdm/organizations/{id}/assign` also writes one history row (`organization_reassigned`). Its behaviour is otherwise unchanged.

### 5.9 Residual race (documented)
An insert by BDM A that commits in the same instant as A's deactivation (for example a new organization) can land on the now
inactive A. Login is already refused for A, and the row is caught by "Hand over" (§5.3). No BDM route is changed to lock the user row.

## 6. Frontend (admin BDMs page; existing design language and components)
- `AdminBdmRow`: "Deactivate" opens the inline group `AdminBdmHandover` (replacing the bare confirm), which:
  - loads the counts (loading / error + Retry);
  - offers two radio choices: "Hand over to another BDM" (`SearchableSelect`, server search on
    `/admin/bdms?bdm_type=<type>&active=true&q=`, the BDM itself excluded) and "Keep with <name> for now (hand over later)";
  - shows a trips note when trips > 0;
  - has "Confirm deactivate" and "Keep active" buttons. Escape cancels and returns focus.
- An inactive row shows "Hand over" (the same component in handover mode: picker only, "Nothing to hand over." when the counts
  are zero) next to "Reactivate".
- `AdminBdmManagersCard` (super_admin only) lists active managers with their BDM count, and each row has a "Deactivate" action
  that opens a group with a manager picker (`managerSearch`, the manager itself excluded) when the count is > 0.
- Success notices go through the panel's existing `role=status` line. Errors go into `role=alert` inside the group, and focus moves
  there.

## 7. Acceptance criteria (backlog AC1–AC5, made testable)

| AC | Test |
|---|---|
| AC1 deactivation without a choice → 422 (both `/deactivate` without `mode` and the PATCH path) | `test_bdm_025_deactivate.py` |
| AC2 the target owns every open item; no history row changes owner (completed / cancelled / no-show / past appointments, done / cancelled tasks, archived organizations, meeting reports, activities, an in-progress trip) | `test_bdm_025_deactivate.py` |
| AC3 pending approvals follow a manager change | `test_bdm_025_managers.py` |
| AC4 a manager with BDMs cannot be deactivated without moving them; the bulk move works | `test_bdm_025_managers.py` |
| AC5 every change is audited (deactivate, handover, trip cancel, manager deactivate, history rows) | all of the above |
| Negative: wrong type, inactive, self, non-BDM target → 422; out-of-type admin → 403; repeat → 409 | `test_bdm_025_deactivate.py` |
| Leave + later handover; reactivation restores login, not the portfolio | `test_bdm_025_handover.py` |
| Migration up / down guard | `test_bdm_025_migration.py` |
| Concurrent double deactivate → one 200, one 409 | `test_bdm_025_concurrency.py` |
| UI dialogs | `AdminBdmHandover.test.tsx`, `AdminBdmManagersCard.test.tsx`, e2e `bdm-025-deactivation.spec.ts` |

## 8. Classification (Phase 1)
- **MUST CHANGE:** `models.py` (+`BdmAssignmentHistory`), new migration, `schemas.py` (3 bodies, `BdmManagerOption.bdm_count`),
  new `services/bdm_lifecycle.py`, new `api/bdm_lifecycle.py` + `main.py`, `api/admin.update_user` (refusal),
  `api/bdm.bdm_managers` (count), `lib/bdm.ts`, `AdminBdmRow`, `AdminBdmPanel`, new `AdminBdmHandover`, new `AdminBdmManagersCard`.
- **MAY CHANGE:** `api/bdm_organizations.py` assign (history row); tests that set up an inactive BDM or manager through PATCH
  (setup moves to direct DB writes; assertions unchanged).
- **SHOULD NOT CHANGE:** the appointment, task and travel services' rules; BDM-facing routes; `rbac.py`; reminder/worker.
- **HIGH REGRESSION RISK:** `admin.update_user` (every admin user flow, ADM-001 trainer cascade, ENH-003 revoke-on-active),
  `AdminUserManagementPanel` 409 handling, bdm-001 admin list tests.

## 9. Security review summary
- **IDOR:** every id is checked against the actor's creator types (or super_admin); the target is validated with one message.
- **Escalation:** a manager cannot reach these routes (`ensure_admin`). Manager deactivation is super_admin only.
- **Integrity:** one transaction, row locks, re-checks after the locks, CHECK constraints.
- **Logs:** ids and counts only, no names, emails or task text. Notification text names the deactivated BDM (internal staff, the
  same as bdm-002's reassign UI).
- **XSS:** React escaping only.
- **CSRF:** the existing cookie + same-origin posture.
- **Session:** a deactivated user's next request is 401 (existing `get_current_user`), and welcome links are revoked.
