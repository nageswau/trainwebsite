# bdm-004 — Organization pipelines per BDM type + stage history — Design

**Status:** design approved in-session on 2026-10-05: seven owner answers (Q1–Q7), the approach, then six design
sections (data model, API, service/transactions, security, frontend, acceptance criteria/tests). The design was reviewed
against the `api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening` skills before approval.
No code has been written.

**Branch:** `feature/bdm-004-pipeline-stages`, created from `origin/main` @ `2e057b3a` (after bdm-009 #59).

**Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-004 (line 335). Depends on bdm-002 (PR #50) and bdm-003 (PR #55),
both merged.

**Source:** `functionalities/edusphere_markdown/BDM Functionalities.md` (`EVID-016`, `DERIVED_BLUEPRINT`) Agent §B status
(561–613), Agent §E (685–741), School §D (897–951), College §D (1136–1190). Decisions in force: `DEC-SCOPE-055` D7 / D8
(handover, later stages read live), D11 (read own type, edit assigned), D13 (one pipeline, agent status derived), D28
(MoU Signed advances the pipeline — bdm-005); `DEC-SCOPE-060` C2 (manager: no create or edit), C14 (super_admin edits
everything), C15 (archived is read-only); `DEC-SCOPE-065` (bdm-003 precedent: list rows unchanged).

**Decision record:** **`DEC-SCOPE-070`**, written in this change. Migration **`0072_bdm_pipeline`** (after
`0071_bdm_activities`, one head). Recheck `origin/main` before building and before the PR: renumber both if another
branch lands first.

**Gate:** `APPROVAL_GATES.md` GATE-09.

---

## 1. Scope

In scope:
- One stage catalogue per BDM type (Agent, School, College), 14 steps each, in source order and wording.
- `bdm_organizations.pipeline_stage` (manual stages only) and a Lost flag with a reason.
- Moving an organization between manual stages, marking it Lost, reviving it; each writes a history row and an audit row.
- The stage history per organization.
- `/bdm/pipeline` and `/bdm/manager/pipeline`: per-stage counts in scope and the organizations at a selected stage.
- The derived 8-value agent status (D13), computed on read.

Out of scope (owned elsewhere):
- Links to `schools` / `agent_orgs` and the live post-handover stages (bdm-018 / bdm-019). bdm-004 ships a read hook
  that returns nothing.
- The college funnel volumes (bdm-021) and agent volumes Students / Applications / Enrollments (bdm-019 / bdm-022).
- MoU "Signed" advancing the pipeline (bdm-005, D28). It will call this item's service.
- A `stage` filter on `GET /bdm/organizations` (the pipeline page lists by stage; not needed).
- Dashboard tiles (bdm-014), targets (bdm-016).

## 2. Approaches considered

- **A. Stage column + history table + a dedicated pipeline service and router (chosen).** Reuses `caller_scope`,
  `load_scoped`, `require`, `audit`; one row lock per write; counts from one `GROUP BY` on an index.
- **B. A 1:1 `bdm_org_pipeline` table.** Leaves the organization row alone, but every list, count and detail needs a join
  and a write holds two locks. Rejected.
- **C. Event-sourced (current stage = latest history row).** Cannot drift, but counts need window queries, no CHECK is
  possible, and bdm-005/018/019 read it awkwardly. Rejected.

## 3. Decisions (owner answers 2026-10-05, `EXPLICIT_APPROVAL`, recorded in `DEC-SCOPE-070`)

- **S1 Who moves.** The assigned BDM and super_admin (the `can_edit` rule; C2 and C14 unchanged). A `bdm_manager` reads
  stages, counts and history for their team and cannot write. This supersedes the backlog line "the manager can move any
  organization in their team".
- **S2 College.** Steps 1–8 are manual (College Activated is the last stage). Steps 9–14 (Course Promotion … Placement)
  are volumes, shown "Not tracked" until bdm-021.
- **S3 Live stages.** No link columns in bdm-004. Live stages exist in the catalogue, are refused by the move endpoint
  (422) and are shown "Awaiting handover". `live_status(org)` returns `None` until bdm-018/019 fill it.
- **S4 Agent status.** Derived on read, never stored:
  Prospect→Prospect · Contacted→Contacted · Meeting Scheduled, Meeting Completed→Meeting · Interested→Interested ·
  Proposal / Agreement, Agreement Signed→Agreement · Agent Onboarding, Master Login Created, Staff Logins Created→
  Onboarding · Active Agent→Active · Inactive = linked Agent Organization suspended or rejected (not reachable until
  bdm-019). Lost does not change the agent status.
- **S5 Lost.** A flag on top of the stage. Marking Lost needs a reason and keeps the stage; a Lost organization is
  counted only in the Lost bucket; moves on a Lost organization → 409. Revive needs a reason, clears the flag and returns
  to the same stage. Both write a history row and an audit row.
- **S6 Move rules.** Any manual stage may be chosen. Forward (skips allowed): note optional. Backward to any earlier
  manual stage: note required (422). The current stage → 422. The request carries `from_stage`; stale → 409.
- **S7 Count scope.** A BDM's pipeline page defaults to "assigned to me" with a toggle to the whole module (D11 read
  scope). A manager sees their team, filterable by BDM; super_admin sees everyone; both choose the type.
- **Defaults stated in the design and approved with it:** archived organizations are read-only (409 on any pipeline
  write, C15) and excluded from counts; every existing and new organization starts at Prospect with no history row;
  stages are stored as keys and shown with the source labels; no rate limit (as every other BDM route).

## 4. Catalogue — new `app/bdm_stages.py`

A constants-only module with no imports from the app. Each step is `(key, label, kind)`, kind ∈ `manual`, `live`,
`volume`. Order is source order.

| # | Agent (§E) | kind | School (§D) | kind | College (§D) | kind |
|---|---|---|---|---|---|---|
| 1 | `prospect` Agent Prospect | manual | `prospect` School Prospect | manual | `prospect` College Prospect | manual |
| 2 | `contacted` Contacted | manual | `contacted` Contacted | manual | `contacted` Contacted | manual |
| 3 | `meeting_scheduled` Meeting Scheduled | manual | `meeting` Meeting | manual | `meeting` Meeting | manual |
| 4 | `meeting_completed` Meeting Completed | manual | `presentation` Presentation | manual | `presentation` Presentation | manual |
| 5 | `interested` Interested | manual | `proposal` Proposal | manual | `proposal` Proposal | manual |
| 6 | `proposal_agreement` Proposal / Agreement | manual | `negotiation` Negotiation | manual | `mou_negotiation` MoU Negotiation | manual |
| 7 | `agreement_signed` Agreement Signed | manual | `mou` MoU | manual | `mou_signed` MoU Signed | manual |
| 8 | `agent_onboarding` Agent Onboarding | live | `signed` Signed | manual | `college_activated` College Activated | manual |
| 9 | `master_login_created` Master Login Created | live | `school_onboarding` School Onboarding | live | `course_promotion` Course Promotion | volume |
| 10 | `staff_logins_created` Staff Logins Created | live | `users_created` Teachers / Parents / Students Created | live | `student_leads` Student Leads | volume |
| 11 | `active_agent` Active Agent | live | `career_guidance` Career Guidance | live | `training` Training | volume |
| 12 | `students` Students | volume | `psychometric` Psychometric | live | `internship` Internship | volume |
| 13 | `applications` Applications | volume | `profile_building` Student Profile Building | live | `recruitment` Recruitment | volume |
| 14 | `enrollments` Enrollments | volume | `university_planning` University Planning | live | `placement` Placement | volume |

Totals: Agent 7 manual / 4 live / 3 volume; School 8 / 6 / 0; College 8 / 0 / 6.

Exports: `PIPELINES: dict[str, tuple[Step, ...]]`, `MANUAL_STAGES: dict[str, tuple[str, ...]]`, `AGENT_STATUS: dict[str,
str]` (S4) and `AGENT_STATUSES` (the 8 values in source order). `Step` is a `NamedTuple`.

## 5. Data model — migration `0072_bdm_pipeline`

### 5.1 `bdm_organizations` (additive; no row is rewritten except by the column default)

- `pipeline_stage` `String(40)` NOT NULL, `server_default 'prospect'` (valid for all three types).
- `lost_at` `DateTime(timezone=True)` NULL; `lost_reason` `String(500)` NULL.
- `ck_bdm_organizations_pipeline_stage`: `(bdm_type = 'agent' AND pipeline_stage IN (…agent manual…)) OR (… school …)
  OR (… college …)`, built from `MANUAL_STAGES` with `_in_list`. Live keys are deliberately not allowed; bdm-018/019
  widen this CHECK with their links.
- `ck_bdm_organizations_lost`: `(lost_at IS NULL) = (lost_reason IS NULL)`.
- `ix_bdm_organizations_type_stage` on `(bdm_type, pipeline_stage)`.

### 5.2 `bdm_pipeline_events` (model `BdmPipelineEvent`, append-only, after `BdmOrganizationContact`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `organization_id` | UUID FK `bdm_organizations.id` `RESTRICT` | organizations are archived, never deleted |
| `actor_user_id` | UUID FK `users.id` `RESTRICT` | |
| `kind` | `String(10)` CHECK `move`, `lost`, `revived` | |
| `from_stage` | `String(40)` NOT NULL | the stage before (equal to `to_stage` for lost / revived) |
| `to_stage` | `String(40)` NOT NULL | |
| `note` | `String(500)` NULL | the move note, or the lost / revive reason (required for those) |
| `position` | `BigInteger Identity` | orders rows; history sorts by it |
| `created_at` | timestamptz `server_default now()` | |

CHECK `ck_bdm_pipeline_events_note`: `kind = 'move' OR note IS NOT NULL`. Index
`ix_bdm_pipeline_events_org (organization_id, position)`. No stage CHECK on events (history must survive a future
catalogue change).

### 5.3 Migration rules (the `0069` pattern)

- Inspector guards (`_present()`) so a database built by `0001`'s `create_all` is not altered twice; an offline `as_sql`
  branch.
- A frozen copy of the manual-stage lists; a test asserts it equals `bdm_stages.MANUAL_STAGES`.
- Existing rows get `prospect` from the default. No event rows are written.
- `downgrade()` raises while any event row exists, any stage is not `prospect`, or any organization is Lost.

## 6. Backend

### 6.1 Schemas (appended to the BDM section of `schemas.py`)

- `StageKey = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,40}$")]`.
- `BdmPipelineNote`: trimmed, ≤ 500, `\r\n` → `\n`, other control characters rejected (`_BDM_MULTILINE_CONTROL`, as
  P14 / `TripNote`); blank → `None`.
- `BdmPipelineReason`: the same rule, required ("Reason is required").
- Inputs (`extra="forbid"`): `BdmStageMove {from_stage: StageKey, to_stage: StageKey, note: BdmPipelineNote = None}`,
  `BdmLostIn {reason}`, `BdmReviveIn {reason}`.
- Outputs: `BdmPipelineStepOut {key, label, kind, state}` with state ∈ `done`, `current`, `upcoming`,
  `awaiting_handover`, `not_tracked`; `BdmPipelineLost {at, reason}`; `BdmOrgPipelineOut {stage, stage_label, lost,
  agent_status, steps}`; `BdmOrganizationOut.pipeline: BdmOrgPipelineOut` (detail only; `BdmOrganizationRow` unchanged).
- `BdmStageEventOut {id, kind, from_stage, from_label, to_stage, to_label, note, actor: BdmPersonRef, created_at}` and
  its page `{items, total, limit, offset}`.
- `BdmPipelineStageCount {key, label, kind, count: int | None}`; `BdmPipelineItem {id, code, name, city, org_type,
  assigned_bdm, stage, stage_label, lost}`; `BdmPipelinePage` `{bdm_type, stages, lost_count, items, total, limit,
  offset}`.

Step `state` for a stored stage at index *i*: steps before *i* → `done`; *i* → `current`; later manual → `upcoming`;
live → `awaiting_handover`; volume → `not_tracked`. (When `live_status` returns a value in bdm-018/019, live steps take
`done` / `current` from it.)

### 6.2 Service — new `app/services/bdm_pipeline.py`

- `pipeline_out(org) -> dict` — the detail object (§6.1); `agent_status` only for `bdm_type == 'agent'`.
- `live_status(org) -> None` — the bdm-018/019 hook.
- `check_move(org, payload) -> bool` (returns "backward"): raises the 409 / 422 in §6.4 order after the lock.
- `move(db, user, org, payload)`, `mark_lost(db, user, org, reason)`, `revive(db, user, org, reason)` — mutate the row,
  add the event, call `bdm_organizations.audit`. They do not commit.
- `counts(db, user, bdm_type, assignee)` — one grouped query; `page(db, user, bdm_type, assignee, stage, limit, offset)`.
- `history_page(db, org_id, limit, offset)`.
- `organization_out` in `services/bdm_organizations.py` adds `"pipeline": pipeline_out(org)`.

### 6.3 Router — new `app/api/bdm_pipeline.py`, registered in `main.py`'s router tuple

| Route | Notes |
|---|---|
| `POST /bdm/organizations/{org_id}/stage` | body `BdmStageMove`; 200 `{organization}` (the archive/restore envelope) |
| `POST /bdm/organizations/{org_id}/lost` | body `BdmLostIn`; 200 `{organization}` |
| `POST /bdm/organizations/{org_id}/revive` | body `BdmReviveIn`; 200 `{organization}` |
| `GET /bdm/organizations/{org_id}/stage-history` | `limit` (50, ≤ 100), `offset`; newest first by `position` |
| `GET /bdm/pipeline` | `bdm_type`, `assigned` (`me` or a uuid; omitted = whole scope, the list's `_assigned` rule), `stage` (a step key of that type or `lost`; omitted = all non-lost), `limit`, `offset` |

`GET /bdm/pipeline` rules:
- BDM: `bdm_type` omitted or equal to their own, else 422. Manager / super_admin: `bdm_type` required (a team may mix
  types, D26), else 422.
- Scope = `caller_scope` ∧ `bdm_type` ∧ `archived_at IS NULL` ∧ the assignee filter.
- `stages[].count`: non-lost organizations per manual stage; `null` for live / volume steps. `lost_count`: Lost
  organizations.
- `stage` names an unknown key → 422; a live / volume key → an empty page.
- Items ordered by `name`, then `id` (as the organization list).
- The UI, not the API, defaults a BDM to `assigned=me`.

### 6.4 Authorization and error order (every write)

1. 401 not signed in (`get_current_user`).
2. 403 a role other than `bdm`, `bdm_manager`, `super_admin` (`caller_scope`).
3. 404 outside the caller's read scope (`load_scoped`) — no existence leak.
4. 403 in scope but not allowed (`require(user, org, "can_edit", route)`, logged) — a peer BDM, a manager.
5. 409 archived (`require`'s state check, C15).
6. 409 `{message, code: "organization_lost"}` (move, lost); 409 `{code: "organization_not_lost"}` (revive).
7. 409 `{message, code: "stage_changed", current_stage}` when `from_stage` ≠ the stored stage (move).
8. 422 (field errors via `RequestValidationError`): `to_stage` unknown or of another type; `to_stage` live or volume
   ("Set by the onboarding handover" / "Counted from live records"); `to_stage` equal to the current stage; backward
   without a note (`loc: body.note`).

Reads: `stage-history` uses `load_scoped` (404 out of scope); `pipeline` uses `caller_scope`.

### 6.5 Transactions and races

- One transaction per write: `load_scoped(lock=True)` (`FOR UPDATE OF bdm_organizations`, `populate_existing`) → checks
  on the locked row → mutate + event + audit → `commit` → `log`. A refused request writes nothing.
- The organization row is the only lock, and it is the first lock every organization write takes (reassign then takes
  the user row), so no lock cycle.
- Two concurrent moves serialize; the second sees the new stage → 409 `stage_changed`.
- A reassignment that commits first makes the old assignee's move a 403 (permission is checked after the lock).
- Retries: a repeated move → 409 `stage_changed` with `current_stage == to_stage` (the UI treats that as done); a
  repeated lost / revive → 409. No idempotency key.
- `updated_at` is bumped by the row change (TimestampMixin), as other writes.

### 6.6 Audit and logs

- One `AuditLog` per successful write, same transaction: `bdm_organization.stage_changed` `{from, to, backward,
  note: bool}`, `bdm_organization.lost` `{stage}`, `bdm_organization.revived` `{stage}`. Note / reason text is never in
  audit metadata or logs.
- Logs after commit: `bdm_org_stage_changed`, `bdm_org_lost`, `bdm_org_revived` (ids and stage keys).

## 7. Security (threat model summary)

| Threat | Mitigation |
|---|---|
| Spoofing | Existing cookie auth (`httpOnly`, `SameSite=lax`); no change. |
| IDOR | `load_scoped` on every organization route → 404 outside scope. |
| Elevation | `require(…, "can_edit")` after the lock; no new role or permission; `PATCH` / `POST` organization bodies are `extra="forbid"`, so stage / lost can only change here; live stages refused so a BDM cannot fake onboarding (D32 metrics). |
| Tampering / injection | Pydantic at the boundary; key regex + catalogue check; SQLAlchemy expressions only. |
| XSS | React escaping; notes rendered as text (`white-space: pre-line`); no `dangerouslySetInnerHTML`. |
| CSRF | Existing posture: `SameSite=lax` cookie + CORS allow-list (`frontend_url`) + JSON bodies (preflighted). |
| Information disclosure | Errors are fixed sentences; note / reason text kept out of logs and audit metadata. |
| Repudiation | Audit row + history row per write; refused writes logged by `require`. |
| DoS | Body limits (500 chars); no rate limiter — accepted, consistent with every BDM route (owner approved). |

## 8. Frontend

### 8.1 Navigation
`lib/navigation.ts`: "Pipeline" → `/bdm/pipeline` in `BDM_NAV` (after Organizations) and `/bdm/manager/pipeline` in
`BDM_MANAGER_NAV` (after Organizations); the comment block records bdm-004.

### 8.2 Organization detail (both roles) — `BdmOrganizationDetail.tsx`
A new `BdmOrganizationPipeline` section after the title / status region, before Details:
- **Stepper:** markup and CSS copied from `AgentStudentJourney`'s `Steps` (`.jny-steps`); `AgentStudentJourney` itself is
  not changed. `<ol aria-label="Pipeline">`, `aria-current="step"` on the current step, the state as text on every step
  (Done / Current / Upcoming / Awaiting handover / Not tracked) — never colour alone. Vertical below 640 px (existing
  CSS).
- **Agent status** badge (agent only) and a **Lost** banner with the reason and date.
- **Move form** (only when `permissions.can_edit` and not Lost): a labelled native `<select>` of manual stages (the
  current one disabled); a note `<textarea>` whose label becomes "Reason (required when moving back)" and which gets
  `required` when the choice is earlier than the current stage; submit disabled with "Saving…" while pending. 422 →
  message beside the field (`aria-describedby`); 409 `stage_changed` → "This organization moved to X meanwhile" and the
  organization is replaced with the fresh one; success → the existing `setNotice` / `focus(statusId)` live region.
- **Mark lost / Revive:** an inline confirm with a required reason, the archive-confirm pattern; focus moves to the
  reason field on open and back to the trigger on cancel.
- **History:** `BdmStageHistory`, cloned from `BdmAppointmentHistory` (`section aria-label="Stage history"`, `ol.jtl`):
  "from → to", actor, time, note. First page fetched on the server beside activities (`lib/bdmPipelineServer.ts`,
  `firstStageHistory`, the `firstActivityPage` pattern); "Show more" appends (`appendUnique`); empty "No stage changes
  yet"; error with Retry. After a write the first page is reloaded.

### 8.3 Pipeline pages — `app/bdm/pipeline/page.tsx`, `app/bdm/manager/pipeline/page.tsx`
Async server components (`serverApi` → access check → `PortalShell`, as the other BDM pages); filters in the URL.
- **BDM:** "Mine" / "All in module" as two links (`aria-current` on the active one); default Mine (`assigned=me`).
- **Manager / super_admin:** a GET form with Type (`<select>`, default the first type in the team) and BDM (`<select>`
  from `/bdm/manager/team`, default All) and an Apply button. A manager with no BDMs sees "No BDMs report to you yet"
  instead of tiles.
- **Stage tiles:** a responsive grid in source order plus a Lost tile; each tile is a link `?stage=key` showing the label
  and count; live tiles read "Awaiting handover", volume tiles "Not tracked" (not links); the selected tile has
  `aria-current="true"`.
- **List:** organizations at the selected stage (default: all non-lost), the existing organizations table style, stacking
  on small screens; rows link to the organization detail for that role; `PAGE_SIZE` with Previous / Next.
- **States:** `loading.tsx` skeleton; empty "No organizations at this stage" (BDM with none at all: "Add organization"
  link); error message with a retry link; wrong role → the existing access-denied view.
- No drag-and-drop board (new dependency, keyboard access, notes required for backward moves).

### 8.4 Client
`lib/bdmPipeline.ts`: types (`Pipeline`, `PipelineStep`, `StageEvent`, `PipelinePage`), `isBackward(steps, from, to)`,
URL builders. `Organization` (`lib/bdmOrganizations.ts`) gains `pipeline`. `lib/bdmPipelineServer.ts` (server only).

### 8.5 Responsive and accessible
No sideways scroll at 320 / 375 / 768 / 1366 px; every control labelled; keyboard-only operation of move, lost, revive,
history and filters; headings in order (h1 page, h2 sections); status text never colour-only.

## 9. Acceptance criteria

1. **Catalogues.** Each type's detail returns exactly 14 steps with the source labels in source order; Agent 7 manual /
   4 live / 3 volume, School 8 / 6 / 0, College 8 / 0 / 6.
2. **History + audit.** Every successful move, lost and revive writes exactly one event row and one audit row; a refused
   request writes neither.
3. **Backward note.** A backward move without a note (missing or blank) → 422 on `note`; with a note → 200.
4. **Live / volume / unknown.** A live, volume, unknown or other-type stage → 422; the DB CHECK rejects another type's
   stage; live steps show "Awaiting handover", volume steps "Not tracked".
5. **Counts in scope.** BDM `assigned=me` = their assigned; omitted = their whole module; manager = their team (and one
   BDM with a uuid); super_admin = everyone of the type; archived excluded; Lost only in `lost_count`.
6. **Authorization.** Writes: peer BDM 403, other module 404, manager 403, super_admin 200, signed out 401, other roles
   403. Reads follow the read scope.
7. **Concurrency.** A stale `from_stage` → 409 `stage_changed` with `current_stage`; of two concurrent moves exactly one
   succeeds.
8. **Lost / revive / archived.** Lost needs a reason and keeps the stage; a move while Lost → 409; revive needs a reason
   and returns to the same stage; lost twice / revive when not lost → 409; any pipeline write on an archived
   organization → 409.
9. **Agent status.** The S4 mapping for every agent stage; `null` for school / college.
10. **Migration.** Existing rows → `prospect`, no event rows; downgrade refuses with data; one head; the frozen lists
    equal `bdm_stages.MANUAL_STAGES`; model and migration CHECKs equal.
11. **UI.** Stepper, move form, lost / revive and history on both detail pages (writes only for `can_edit`); pipeline
    page counts and list; keyboard-only; no sideways scroll at 320 / 375 / 768 / 1366 px; loading, empty, error states.
12. **Compatibility.** List rows, the four permission keys, and every existing route and status code are unchanged; only
    the detail response gains `pipeline`.

## 10. Tests (written before the code, per task)

Backend (`apps/api/tests`, helpers from `bdm001/002/003_helpers.py`):
- `test_bdm_004_catalogue.py` — AC1, AC9 (pure, no DB).
- `test_bdm_004_migration.py` — AC10 (the `test_bdm_003_migration.py` pattern: revision, single head, parity, columns /
  checks in the shared DB, round trip on `isolated_db`, downgrade refusal).
- `test_bdm_004_schemas.py` — key regex, note / reason rules, `extra="forbid"`.
- `test_bdm_004_stage.py` — AC2, AC3, AC4, forward skip, same stage, detail `pipeline`.
- `test_bdm_004_lost.py` — AC8.
- `test_bdm_004_scope.py` — AC6.
- `test_bdm_004_pipeline.py` — AC5, `bdm_type` rules, `stage` filter, paging.
- `test_bdm_004_concurrency.py` — AC7 (the `test_bdm_009_concurrency.py` pattern).

Web (`apps/web/tests`): `components/BdmOrganizationPipeline.test.tsx`, `components/BdmStageHistory.test.tsx`,
`components/BdmPipelinePages.test.tsx`, `lib/bdmPipeline.test.ts`.

E2E: `apps/web/tests/e2e/bdm-004-pipeline.spec.ts` (API seeding as bdm-009): move forward, backward with a note, lost /
revive, history, pipeline counts, manager read-only, `noOverflow` at 320 / 375.

Existing tests edited (expected, not regressions):
- `tests/test_bdm_009_migration.py:37` — the head assertion becomes "one head, and `0071_bdm_activities` is an ancestor"
  so the next migration does not edit it again.
- `apps/web/tests/lib/navigation.bdm.test.ts:12,15` — the Pipeline item.
- `apps/web/tests/components/BdmOrganizationPages.test.tsx:82` (and the manager-page assertion) — the `stageHistory` prop.
- `apps/web/tests/components/BdmOrganizationDetail.test.tsx:11` — the fixture gains `pipeline`.

## 11. Regression risks

| Risk | Guard |
|---|---|
| `organization_out` is shared by every organization route | additive key only; bdm-002 / bdm-003 suites |
| `load_scoped` / `caller_scope` used by appointments and activities | not modified; bdm-006 / bdm-009 suites |
| The detail page serves both roles | role-specific tests for write controls; Playwright manager read-only |
| `models.py` / `schemas.py` / `main.py` are merge hot spots (`worktree-bdm-007` open) | append in the BDM sections; recheck `origin/main` before the PR |
| Migration on existing data | column default + guarded DDL; downgrade refusal; offline SQL reviewed |
| bdm-005 / 018 / 019 / 021 build on this | catalogue module, `live_status` hook and service functions documented here |

## 12. Documentation (updated in the same change)

`DEC-SCOPE-070` (decision register), `BDM_CRM_BACKLOG.md` bdm-004 status line, RTM row naming migration `0072`.

## 13. Completion gates

All AC1–AC12 evidenced; backend lite (all `test_bdm_*`) and web BDM + navigation suites green; `alembic heads` single;
offline SQL reviewed; ruff, `tsc`, `eslint`, `next build` clean; Playwright bdm-001/002/003/004/006/009/010 green;
browser checks of the pipeline UI at 320 / 375 / 768 / 1366 px, keyboard-only, RBAC as AC6.
