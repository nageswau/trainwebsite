# tel-025 — Telecaller deactivation, team move and bulk reassignment — design

**Date:** 2026-10-07 · **Backlog item:** `tel-025` (`docs/delivery/TELECALLER_CRM_BACKLOG.md`) · **Business rules:** T21, T22, T23; EVID-019 §13 "when staff changes".
**Decision:** `DEC-SCOPE-104` (LC1–LC4, owner answers of 2026-10-07; number reserved on `main`).
**Dependencies (all merged):** tel-007 (PR #90), tel-011 (PR #100), tel-016 (PR #103), tel-018 (PR #114). **Migration:** none.

## 1. Owner answers

| ID | Question | Answer |
|---|---|---|
| LC1 | Who may deactivate or move a telecaller? | **Admins only.** `super_admin` covers any team; `it_admin` and `overseas_admin` cover their own team (the tel-001 `CREATOR_TEAMS` rule). A team move needs **both** teams in the actor's scope, which in practice means `super_admin`. Only `super_admin` deactivates a `telecaller_manager`. Telecaller managers get no lifecycle power. |
| LC2 | What is "open work"? | A lead with `telecaller_user_id` = the telecaller whose stage is **not closed and not `converted`**. This includes leads handed over to a counselor: the counselor stays the owner, and a later return then reaches an active telecaller. Open follow-ups (tel-011 F3) and appointments (tel-016) belong to the lead, so they move with it and nothing is rewritten. Closed and converted leads, calls, stage history and audit rows keep the original actor (AC2). |
| LC3 | Target | Required when open work exists. Either an **active telecaller of the same team** (`target=telecaller` with `reassign_to`; another team → 422) or the **team's unassigned queue** (`target=queue`). There is no "keep with them" option. |
| LC4 | Reactivation and inactive telecallers who already hold work | Reactivation stays allowed (Users page, or the Telecallers row's Reactivate). Moved work does not come back. An inactive telecaller who still holds open leads gets **Reassign open work** (`POST /admin/telecallers/{id}/handover`). That covers accounts deactivated before tel-025 and leads routed to them during the deactivation itself. |

Derived (no owner question needed, following the bdm-025 precedent):
- **D1:** deactivation sets `active=false`, increments `session_version` (AGN-002, so the session ends at once) and revokes open welcome links (ENH-003).
- **D2:** a team move also increments `session_version`, because the token's `division` claim changes. The telecaller signs in again at the new portal.
- **D3:** the telecaller's tel-007 distribution rules are deleted, with an audit row, on deactivation and on a team move. They could never fire again, because rules only pick active same-team telecallers, and keeping them would show dead routing on the Rules page.
- **D4:** a telecaller manager with direct reports is deactivated only together with a replacement active manager. Every report moves, active or not.
- **D5:** `PATCH /admin/users/{id}` with `active:false` is refused with 422 for a telecaller who holds open leads and for a manager who still has reports. A telecaller with no open work can still be deactivated there; that path also increments `session_version`.
- **D6:** the target telecaller gets an in-app and email notice (ENH-014 queue) when leads move to them.

## 2. API (`api/telecaller_lifecycle.py`, prefix `/admin`)

Every route uses `ensure_admin`, then the team scope (403), then the write. Each route is one transaction, and every refusal happens before any write.

| Route | Body | Result |
|---|---|---|
| `GET /admin/telecallers/{id}/open-work` | — | `{leads, follow_ups, appointments}` (preview) |
| `POST /admin/telecallers/{id}/deactivate` | `{target?: "telecaller"\|"queue", reassign_to?}` | `{id, active:false, target, moved:{…}, rules_removed}` |
| `POST /admin/telecallers/{id}/handover` | `{target, reassign_to?}` | `{id, target, moved}`. Returns 409 if the telecaller is active or holds nothing. |
| `POST /admin/telecallers/{id}/move-team` | `{team, target?, reassign_to?, reporting_manager_user_id?}` | `{id, team, target, moved, rules_removed}` |
| `POST /admin/telecaller-managers/{id}/deactivate` | `{reassign_to?}` | `{id, active:false, moved_telecallers}` (super_admin) |

Errors:
- 404: not a telecaller with a profile, or not a manager.
- 403: the actor's team scope does not cover the telecaller.
- 422: open work but no `target` (AC3); `target=telecaller` without `reassign_to`; an invalid target (one message for every case, "Choose an active telecaller of the same team"); the same team on a move; a reporting manager who is not active.
- 409: the telecaller is already inactive (deactivate), or still active (handover).

## 3. Service (`services/telecaller_lifecycle.py`)

The service is functions only and never commits. Lock order: the source's open leads (FOR UPDATE, by id), then the source profile, then the user (FOR UPDATE), then the target (FOR SHARE). tel-007's `assign` uses the same lead-before-profile order, so the two cannot deadlock.

- **Moving to a telecaller:** each lead goes through `lead_distribution.assign`. That writes the `assigned` event for a `new` lead and one `lead.assign` audit row per lead, with the method `deactivation`, `team_move` or `handover`.
- **Moving to the queue:** `telecaller_user_id` becomes NULL and one `lead.assign` audit row is written (`to: null`). The stage is left as it is.
- **Logs:** ids and counts only.

## 4. Frontend

- `AdminTelecallerLifecycle.tsx` follows the `AdminBdmHandover` pattern: an inline group with focus management and Escape to cancel. It has three modes: `deactivate`, `handover` and `move`. It loads the open-work counts first, then offers a radio choice between "Another telecaller" (a server-search picker of active same-team telecallers, excluding the source) and "Unassigned queue". In move mode it names the other team (there are two) and offers an optional new-manager picker.
- `AdminTelecallerRow`:
  - **Deactivate** opens the group; the old inline confirm goes.
  - **Move team** shows only when the actor can manage both teams.
  - **Reassign open work** shows on inactive rows.
- `AdminTelecallerManagersCard` (super_admin only, on the Telecallers page) lists active managers with `telecaller_count` (added to `GET /admin/telecaller-managers`). Deactivate shows the report count and requires a replacement when there are reports.

## 5. Acceptance criteria → tests

1. No open lead or follow-up stays with an inactive telecaller. Tested for deactivate, handover and move, on both the telecaller and the queue targets.
2. Calls, stage history and closed or converted leads keep the original telecaller.
3. Deactivating without a target when open work exists → 422, and nothing changes.
4. A target on another team → 422; a division admin acting on another team → 403; a non-admin → 403.
5. A manager with reports cannot be deactivated without a replacement (422); with one, every report moves.
6. A plain PATCH deactivation is refused when work exists (D5); other roles' PATCH deactivation behaves as before.
7. The session ends: the old cookie gets 401 after deactivation and after a team move.

## 6. Plan (TDD, in order)

1. Schemas (`TelecallerDeactivate`, `TelecallerTeamMove`, `TelecallerManagerDeactivate`, outputs).
2. Service and routes for the open-work preview and deactivate, plus tests: AC1, AC2, AC3, the target rules, scope and session.
3. Handover (LC4), plus tests.
4. Move-team, plus tests.
5. Manager deactivation, plus tests.
6. The `admin.update_user` guard (D5), plus a regression test for other roles.
7. Frontend: lib, lifecycle component, row and managers card; unit tests where the repo has them; lint, typecheck and build.
8. Playwright e2e spec, then browser QA.
9. Docs: the decision register, API_CONTRACT §12Y, RBAC_MATRIX §2.31 and the backlog status.

## 7. Risks

- `admin.update_user` is shared by every role. The guard runs only for `telecaller` and `telecaller_manager`.
- A lead routed to the telecaller in the instant they are deactivated is covered by LC4's handover.
- Queue leads keep their stage (for example `assigned`). There is no pipeline event to undo `assigned`; tel-007's next manual assignment applies.
