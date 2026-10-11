# rec-037 — Recruiter deactivation + bulk reassignment (design)

**Date:** 2026-10-11 · **Branch:** `feature/rec-037` · **Gate:** GATE-09 (EVID-018 in scope, R1) · **Migration:** none

## 1. Source and intent

- Backlog §rec-037 (listed under "Added though not in the source"; R2 own-assignment scope + the tel-025 precedent): *a deactivated
  recruiter's companies, requirements and follow-ups must not be orphaned. Deactivating a recruiter with open companies or requirements is
  refused until they are reassigned (or reassigned in the same action, per Q-27). The manager bulk-reassigns companies (+ their
  requirements and open follow-ups) between their reports, with history.* AC1 deactivation is blocked with open work; AC2 reassignment
  moves everything, writes history, and the old recruiter loses access. Positive: move 12 companies from R1 to R2. Negative: a target
  outside the manager's team → 422. Edge: a recruiter with no manager.
- Dependencies rec-003 (`companies.assigned_recruiter_user_id`, `company_assignment_history`), rec-007 (`jobs.assigned_recruiter_user_id`),
  rec-009 (candidates — no owner: R11 pool, nothing to move) and rec-024 (follow-ups belong to the company, FU4) are merged on main.
- Closest as-built precedent: upc-032 (`DEC-SCOPE-171`, `services/partnership_lifecycle.py`, `PartnershipReassign.tsx`).

## 2. Decisions (recommended answers, `NEEDS_CONFIRMATION` at sign-off — registered as DEC-SCOPE-176)

| # | Question | Answer |
|---|---|---|
| RC1 | Q-27: what happens to a deactivated recruiter's work? | Nothing automatic. Plain deactivation is refused while they hold open work; a placement manager (or super_admin) reassigns it from the Team page, then deactivates. No "reassign in the same action" (the upc-032 RA1 shape; one rule, one place) |
| RC2 | What blocks deactivation | ≥ 1 **non-archived** company assigned to the recruiter, or ≥ 1 requirement assigned to them whose status is not `closed`/`cancelled` (rec-007 `ENDED`) |
| RC3 | Refusal shape | `PATCH /admin/users/{id}` `{active:false}` → `422` "This recruiter has N companies and M open requirements. A placement manager must reassign them (Team page) before deactivation." Parts with 0 are left out. 422, not 409 (the Users page reads 409 as the trainer cascade prompt, tel-025 D5). Applies to super_admin and it_admin alike |
| RC4 | Who reassigns | `placement_manager` (from and to their direct reports) and `super_admin` (any recruiter to any active recruiter). Everyone else → 403 (recruiter, it_admin, hr_team, bdm); signed out → 401 |
| RC5 | What moves | Every company assigned to the source (archived included: ownership must not point at an inactive person after a restore) → the target, one `company_assignment_history` row + one `recruiter_company.assign` audit each (`reason: "reassign"`). Every requirement assigned to the source → the target (any status: a closed one can be reopened, so leaving it would keep the old recruiter's write access — AC2 "the old recruiter loses access"; per-recruiter metrics come from activity, R10), one `recruiter_requirement.assign` audit each. Open follow-ups belong to the company (FU4) and move with it untouched; they are counted |
| RC6 | Requirements on a moved company held by a third recruiter | Stay with that recruiter (their work); unassigned ones stay unassigned (the company's recruiter reads them) |
| RC7 | Source state | Active or inactive (a recruiter deactivated before rec-037 can still be handed over) |
| RC8 | Invalid input | Source not a recruiter with a profile → `404`; source not the manager's direct report → `403`; target inactive, not a recruiter, outside the team, or equal to the source → `422` (one message, rec-003 `REASSIGN_INVALID`); nothing to move → `409` |
| RC9 | Edge: a recruiter with no manager | Only super_admin can reassign them (a manager gets the RC8 403); the RC3 sentence still says "a placement manager" — super_admin sees every recruiter on the same Team page |
| RC10 | Transaction and locks | One transaction. Lock order: the source's companies (by id, FOR UPDATE), then its requirements (by id, FOR UPDATE), then the target (FOR SHARE, rec-003 `locked_recruiter_target`) — the assign routes' row-then-recruiter order, so they cannot deadlock |
| RC11 | Deactivation race | The pre-check locks the user row FOR UPDATE before counting, so a concurrent assign (target read FOR SHARE) either commits first and is counted, or waits and then sees an inactive recruiter (422) |
| RC12 | Session | Plain deactivation of a recruiter also bumps `session_version` (tel-025 D1); reassignment does not touch sessions — the old recruiter loses access through scope (their company/requirement reads become 404) |
| RC13 | Audit / logs | One `recruiter.reassign` audit on the source user with the counts; logs carry ids and counts only |
| RC14 | Notifications | None (not in the source; `NEEDS_CONFIRMATION`) |
| RC15 | Preview | Team rows carry `work: {companies, requirements, follow_ups}` (three grouped queries per page); the response's `moved` is authoritative |

## 3. API

- `POST /recruiter/manager/reassign` body `{from_user_id, to_user_id}` (extra keys forbidden) → `200`
  `{from_user_id, to_user_id, moved: {companies, requirements, follow_ups}}`.
- `GET /recruiter/manager/team` rows gain `work` (additive; the reassign picker `recruiterSearch` ignores it).
- `PATCH /admin/users/{id}` `{active:false}` on a recruiter with open work → `422` (RC3). Other roles unchanged.

## 4. Web

- Team page (`/recruiter/manager/team`): new columns *Companies*, *Open requirements*, *Open follow-ups* and *Actions* with a
  *Reassign* button on rows with work, opening an inline group (`RecruiterReassign.tsx`, the `PartnershipReassign` conventions: no dialog
  library, focus moves to the group, Escape cancels, an error takes focus, 5xx in plain words, `role="status"` notice + `router.refresh()`).
  The picker is rec-003's `recruiterSearch(row.id)` (active team-mates, the source excluded). Rows get `data-label` (card layout < 640 px).
- `AdminRecruiterRow` already shows the server's 422 sentence on Deactivate; its comment is updated.

## 5. Tests

- API `test_rec_037_reassign.py`: refusal with companies / requirements (message + counts), allowed with only archived companies and ended
  requirements, allowed after reassignment and bumps `session_version`; reassign moves companies (archived too) + requirements (closed too), third-recruiter requirement stays, follow-ups counted, history + audits; 12 companies; old recruiter's company and requirement
  reads → 404 and the new recruiter's → 200; inactive source; super_admin moves a recruiter with no manager while a manager gets 403;
  422 target outside team / inactive / same / not a recruiter; 403 recruiter, it_admin, other manager; 404 unknown; 409 nothing; 401;
  team rows carry `work`.
- Web unit `RecruiterReassign.test.tsx`, `RecruiterTeamTable.test.tsx`.
- E2E `rec-037-recruiter-reassign.spec.ts`: admin deactivate refused → manager reassigns → deactivate succeeds.

## 6. Plan (TDD, one commit per step)

1. Schemas `RecruiterWork`, `RecruiterTeamMemberRow`, `RecruiterReassign(Out)`; `services/recruiter_lifecycle.py` (`work_counts`,
   `refuse_open_work_deactivation`, `load_source`, `reassign`, `log`) — tests first.
2. `admin.update_user` hook (RC3, RC12); `api/recruiter.py` team `work` + reassign route.
3. Web: `lib/recruiter.ts` types + URL, `RecruiterReassign.tsx`, `RecruiterTeamTable.tsx` columns — vitest first.
4. E2E spec; docs (DEC-SCOPE-176, API §12CQ, RBAC §2.102, backlog status) — numbers re-checked against main in Phase 9.
