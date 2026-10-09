# upc-020 — Tasks + follow-ups, auto-generated (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". The item answers TK1–TK16 (§1), including **Q-22** (the auto-task rules), are **recommended defaults
accepted under that instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals). They are registered that way in
`DEC-SCOPE-138`.

**Branch:** `feature/upc-020`, cut from `origin/main` @ `f4207d39` (after #181).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-020, U11, Q-22, Appendix A L639–L693.
**Dependencies:** upc-003 (`0105`, `DEC-SCOPE-120`) and upc-006 (`0108`, `DEC-SCOPE-123`) are merged on main. This was verified in code. The
item also hooks the merged upc-007 stage engine (`api/partnership_pipeline.py`) and upc-010 visits (`api/university_visits.py`, VS16).
**Source:** `EVID-020` §19 (L639–L671: "The CRM should automatically generate tasks", 12 examples, "Task → Employee → Due Date → Priority →
Status") and §20 (L673–L693: "Next Action + Next Action Date", the XYZ example, Overdue / Due Today / Due Tomorrow / Upcoming).
**Numbering:** migration `0123_partnership_tasks`, `DEC-SCOPE-138`, API §12BF, RBAC §2.64 (renumbered at merge if another item lands first).
**Gate:** `APPROVAL_GATES.md` GATE-09.
**Template:** bdm-008 (`BdmTask`, `services/bdm_tasks.py`, `api/bdm_tasks.py`, `BdmTasksPanel` / `BdmTaskItem` / `BdmTaskForm`): the same
bucket filters, lock-then-check writes and audit idiom, applied to universities. The BDM code itself is not changed.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| TK1 | What a task belongs to | **One university, always** (§20 "every university should have"; every §19 example is about a university). `kind` = `follow_up` or `task` (bdm-008's two kinds) |
| TK2 | Fields (§19 L671) | Title ("Task"), assignee ("Employee"), due date, priority, status, plus notes, kind and source. Priority is `high / medium / low` (default `medium`; the XYZ example's "High"). Status is `open / done / cancelled` |
| TK3 | The 12 §19 examples | A **title catalogue** the form offers as suggestions; the title stays free text (≤ 200). No catalogue key is stored (nothing reads it) |
| TK4 | Q-22: which event creates which task | Entering a stage creates one task (table below); completing a visit creates "Follow up after visit" due on the visit's follow-up date (upc-010 VS16). Sources `meeting` and `agreement` are reserved in the CHECK for upc-009 / upc-014, which add their own rules |
| TK5 | Q-22: due offsets | Calendar days after the IST day of the event (table below). No working-day calendar exists in the product |
| TK6 | Auto assignee | The university's primary manager when active; else the backup manager when active; else the person who triggered the event when they are a partnership manager or head; else no task (logged `partnership_task_auto_skipped`, e.g. super_admin moving an unowned university) |
| TK7 | Duplicate auto-tasks | At most **one open task per (university, rule)**. Moving back and forward again does not add a second "Follow up on proposal" while the first is open. Once it is done or cancelled, re-entering the stage creates a new one. Enforced in the service under the university (stage) or visit (visit) row lock, with a partial unique index as the backstop |
| TK8 | Who reads | `partnership_manager` (with a profile), `partnership_head` and `super_admin` read **every** task (the backlog's "a manager reads every university"; upc-010 VS7). `overseas_admin` and every other role get a 403 on the task routes |
| TK9 | Who creates by hand | `partnership_manager` and `partnership_head`, on an active university in their edit scope (the upc-006 `can_edit_contacts` rule, as visits VS6). super_admin reads only |
| TK10 | Assignee ("the head assigns to reports") | A manager assigns only themselves; a head assigns themselves or an **active direct report** (upc-010 `lead_filter`). Anyone else is a 422 (the backlog's negative scenario) |
| TK11 | Who changes a task | The **assignee**, or the assignee's **reporting head**. Any other caller is a 403. Auto tasks are changed like manual ones (they have no other owner) |
| TK12 | Commands | `PATCH` title / notes / priority / assignee; `reschedule` (due date, today or later); `complete`; `cancel` (reason 1–500). A task that is not open is a 409. The due date changes only through `reschedule`, so the history of moves is explicit in the audit log |
| TK13 | Bands (§20, IST) | `overdue` (open, due before today), `today`, `tomorrow` (today + 1), `upcoming` (later), plus `done` and `cancelled`. A done or cancelled task is never overdue (AC3) |
| TK14 | Next Action (§20) | The university's **earliest open follow-up** (kind `follow_up`; ties by priority, then creation): title, date, assignee ("Owner"), priority and band |
| TK15 | Last Action (§20) | The later of the university's latest completed task (its title) and its latest stage move ("Moved to <stage>"). upc-013's timeline replaces this when it lands |
| TK16 | Visit follow-up date edited later | While the visit's auto follow-up is open, a change of the visit's follow-up date moves the task's due date in the same transaction (one source of truth for the date) |

**Q-22 stage rules** (`app/partnership_task_rules.py`, constants only):

| Stage entered | Kind | Title | Due (days) | Priority |
|---|---|---|---|---|
| Initial Contact | follow_up | Follow up with university | 3 | medium |
| Interested | task | Schedule meeting | 2 | high |
| Meeting Completed | task | Send partnership proposal | 3 | high |
| Proposal Sent | follow_up | Follow up on proposal (AC1) | 7 | high |
| Commercial Discussion | task | Negotiate commission | 7 | medium |
| Documents Shared | task | Send MoU | 5 | medium |
| Agreement Under Review | follow_up | Follow up on MoU | 7 | high |
| Agreement Signed | task | Activate university | 7 | high |
| Partner Activated | task | Conduct training | 14 | medium |
| Student Recruitment Started | task | Send student applications | 14 | medium |

The other stages create nothing. "Arrange university visit", "Collect documents" and "Follow up on offers" are manual-only catalogue
titles (offers arrive with upc-018).

## 2. Data model — migration `0123_partnership_tasks`

`partnership_tasks`:
- id; university_id FK RESTRICT; kind String(20); title String(200); notes String(2000) null;
- assignee_user_id FK users RESTRICT; created_by_user_id FK users RESTRICT (the actor; for an auto task, who triggered it);
- due_on Date; priority String(10) default `medium`; status String(20) default `open`;
- source String(20) (`manual / stage / meeting / visit / agreement`); rule String(80) null (`stage:<key>` or `visit:<id>`);
- completed_at, cancelled_at timestamptz null; cancel_reason String(500) null; created_at / updated_at.
- CHECKs: kind, priority, status, source in their lists; `(source = 'manual') = (rule IS NULL)`; `(status = 'done') = (completed_at IS
  NOT NULL)`; `(status = 'cancelled') = (cancelled_at IS NOT NULL)`; `cancel_reason IS NULL OR status = 'cancelled'`.
- Indexes: `ix_partnership_tasks_assignee_status_due` (assignee, status, due_on) (backlog performance note);
  `ix_partnership_tasks_university_status_due`; partial unique `uq_partnership_tasks_open_rule` (university_id, rule) WHERE status =
  'open' AND rule IS NOT NULL (TK7).
- Downgrade refuses while any task exists. No backfill: existing universities have no tasks (inventing them would invent facts).

## 3. Backend

`app/partnership_task_rules.py` (catalogue + rules), `services/partnership_tasks.py` (scope, bands, rules, auto-create, output; never
commits), `api/partnership_tasks.py` (prefix `/partnership/tasks`, owns the transaction).

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/tasks` | readers (TK8) | `band` (default `today`; also `open`), `assignee` (`me` / `team` / uuid), `university_id`, `kind`, `limit`, `offset` → `{items,total,limit,offset,today,counts:{overdue,today,tomorrow,upcoming,done,cancelled}}`. Counts use every filter but the band |
| `GET /partnership/tasks/catalogue` | readers | `{titles:[…12]}` for the form |
| `POST /partnership/tasks` | creators (TK9) | `{university_id, kind, title, due_on, priority?, assignee_user_id?, notes?}` → 201 task |
| `PATCH /partnership/tasks/{id}` | actor (TK11) | title / notes / priority / assignee_user_id; `extra="forbid"` |
| `POST /partnership/tasks/{id}/reschedule` | actor | `{due_on}` |
| `POST /partnership/tasks/{id}/complete` | actor | no body |
| `POST /partnership/tasks/{id}/cancel` | actor | `{reason}` |

- **Every write:** `require_reader` → lock the task `FOR UPDATE` (404 when missing) → actor check (403, logged ids only) → open check
  (409) → validation (422) → change + `AuditLog` (`partnership_task.<action>`: ids, kind, source, field names; never title, notes or
  reason) → one commit → structured log.
- **Hooks (same transaction as the event):**
  - `api/partnership_pipeline.move_stage`: after `pipeline.move`, `tasks.on_stage_entered(db, user, uni)`.
  - `api/university_visits.complete`: after the status change, `tasks.on_visit_completed(db, user, v)`; `edit` with a changed
    `follow_up_date` calls `tasks.sync_visit_due(db, v)` (TK16).
  - Auto-create = rule lookup → assignee (TK6) → open duplicate check (TK7) → insert + audit `partnership_task.auto_create`. A skipped
    rule is logged, never an error: the stage move or visit completion must not fail because of a task.
- **University detail:** `UniversityDetail` gains `follow_up: {next_action, last_action}` (TK14/TK15) for every university reader (it
  holds titles, dates and staff names only).
- Unknown band/assignee value → 422. A manager's `assignee=team` is the same as `me`.
- Daily bound: 200 manual tasks per creator per IST day (bdm-008's abuse bound) → 409.

## 4. Frontend

- `lib/partnershipTasks.ts`: types, `BANDS` + labels + empty texts, `PRIORITIES`, URLs, `isTask` / `isTaskPage`, the option searches
  (reusing upc-010's `university-options` and `lead-options`, which already apply the TK9/TK10 scope).
- `components/PartnershipTasksPanel.tsx` (client): band tabs with counts, the assignee filter (Mine / My team for a head / All), the add
  form, the list and the pager. With `universityId` it lists that university's open items without tabs (the university page).
- `components/PartnershipTaskItem.tsx` (client): title, kind, priority and band badges (text, never colour alone), university link,
  assignee, source ("Auto: stage", "Auto: visit", "Added by hand"); actions from `permissions` only: Done, Reschedule (inline date
  form), Edit, Cancel (reason form, the bdm-008 `BdmAppointmentReasonForm`).
- `components/PartnershipTaskForm.tsx` (client): university (SearchableSelect, or fixed), kind, title with the catalogue as a
  `<datalist>`, due date (IST, today or later), priority, assignee (heads only), notes. 422 field errors, a double-submit guard and the
  leave guard.
- `/partnership/tasks` page (server; PortalShell via `shellFor`).
- University page: a **Follow-ups & tasks** section — Next action / Last action facts (§20 XYZ layout) and the panel (task readers only).
- Nav: `PARTNERSHIP_MENU` "Follow-ups & Tasks" goes live; `PARTNERSHIP_HEAD_NAV` gains it.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | Moving a university to Proposal Sent creates "Follow up on proposal" (follow-up, due +7, assigned to the primary manager) | `test_upc_020_auto.py`; e2e |
| AC2 | The bands follow IST dates (overdue / today / tomorrow / upcoming) | `test_upc_020_tasks.py` (bands computed from `india_today`) |
| AC3 | A completed task is never overdue and is not in the overdue band | `test_upc_020_tasks.py` |
| P1 | The XYZ example: last action "Moved to Proposal Sent" (or the completed task), next action "Follow up on proposal", date, owner, priority High on the university page | `test_upc_020_auto.py`; e2e |
| N1 | A head assigning to someone outside their team → 422; a manager assigning someone else → 422 | `test_upc_020_tasks.py` |
| E1 | Duplicate auto-task suppression: proposal → back → proposal keeps one open task | `test_upc_020_auto.py` |
| R1 | Other roles 403; a non-actor write 403; a closed task 409; past due 422; an out-of-scope university 403; an unknown task 404 | `test_upc_020_tasks.py` |
| V1 | Completing a visit creates "Follow up after visit" due on its follow-up date; editing that date moves it | `test_upc_020_auto.py` |
| M1 | Migration: CHECKs and indexes equal the model; downgrade guard | `test_upc_020_migration.py` |

## 6. Tasks (TDD, in order)

1. Rules module + model + migration + parity test (`test_upc_020_migration.py`).
2. Schemas, service and routes: list/bands/create/access tests, then the command tests, then the code (`test_upc_020_tasks.py`).
3. Auto-creation hooks + university `follow_up` summary (`test_upc_020_auto.py`).
4. Frontend: lib, form, item, panel, page, university section, nav, with vitest.
5. Playwright `upc-020-partnership-tasks.spec.ts`.
6. Docs: DEC-SCOPE-138, API §12BF, RBAC §2.64, DATA_MODEL, SCREEN_CATALOG, backlog status.

## 7. Regression set (lite)

`test_upc_007_*` (the stage route gains a hook), `test_upc_010_*` (complete/edit gain hooks), `test_upc_003_*` (detail output),
`test_bdm_008*` (untouched template), `navigation.partnership.test.ts`, `UniversityDetailPage.test.tsx`, the upc-007/010 e2e specs.

## 8. Engineering review notes (Phase 3)

- **API:**
  - Responses use the partnership envelope (`{task}`), as `{visit}` / `{university}` do. Each task carries `permissions`
    (`can_edit, can_reschedule, can_complete, can_cancel`), computed from the same actor + open rule the routes enforce.
  - 404 only for a missing task (every reader reads every task, so there is no scope-hiding 404). 403 for a role or actor refusal, 409
    for a closed task or the daily bound, 422 for validation. `extra="forbid"` on every body.
  - Not idempotent: a retried create adds a second task (bdm-008's accepted behaviour; the form's double-submit guard and the daily
    bound limit it). Complete/cancel retried after success meet a closed task → 409, which the UI treats as "changed elsewhere".
- **Transactions and locks:** the hooks run inside the stage-move / visit transaction, so a failure rolls both back (fail closed). Lock
  order is always parent first (university or visit, then the task insert/update); a task route locks only the task and never a
  university or visit, so the orders cannot cross. The partial unique index decides any race the service check misses (IntegrityError
  → the event still fails closed, retried by the user).
- **Security:**
  - Reads are role-gated (TK8); writes re-check the actor after `FOR UPDATE` (no TOCTOU). The assignee check is a SQL filter
    (`lead_filter`), and the option endpoints only return what the caller may submit.
  - Free text (title, notes, reason) is never logged or put in audit metadata; React escapes it (no `dangerouslySetInnerHTML`).
  - CSRF follows the app's existing cookie + same-origin `sendJson` path; nothing new.
  - No secrets, no new dependencies.
- **Frontend:**
  - Reuses `SearchableSelect`, `BdmAppointmentReasonForm`, `ReturnToLoginLink`, `useLeaveGuard`, `useFocusAfterRender`, the
    `.action-card` / `.badge` / `.form-error` styles and bdm-008's write-failure handling (`writeFailure`).
  - Band tabs are buttons with `aria-current`; the list region is `aria-busy` while loading; notices are `role=status`, errors
    `role=alert`. Badges carry text, never colour alone. Every action is a button reachable by keyboard; Escape closes a form.
  - Loading, empty (per band), past-the-end, error (Retry) and session-ended states, as bdm-008's panel.
  - Wraps on mobile (flex-wrap; long titles `overflow-wrap: anywhere`).
