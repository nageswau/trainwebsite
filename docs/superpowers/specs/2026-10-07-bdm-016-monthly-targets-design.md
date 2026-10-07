# bdm-016 — Monthly targets (manager-set, achieved computed) — design

- **Feature:** bdm-016 (`docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-016; Appendix B.3 K-rows → B.1 M-rows)
- **Decision:** `DEC-SCOPE-100`. Migration `0095_bdm_targets` after `0094_bdm_daily_reports`; API §12U; RBAC §2.27.
- **Branch:** `worktree-bdm-016` from `origin/main` @ `b1495fa2` (bdm-015 merged, PR #111).
- **Evidence:** `DEC-SCOPE-055` D4 (manager = reporting manager, team scope; super_admin all), D21 / Q-12 (fixed catalogue per type, each
  with a written metric definition, monthly only), D31 (School Career Guidance / Psychometric KPIs = students served in linked
  schools), D32 (Active Agents / Active Schools / New Agents from linked partner records; "not tracked" until a link exists).
- **Dependency:** bdm-015 (`bdm_metrics` builders) — merged. bdm-019 (agent onboarding link) and the Agent CRM counts (M-21) are not
  built: those KPIs are "Not tracked".
- **Status of answers:** the owner directed this session to proceed with the recommended answers; R1–R12 below are those
  recommendations (`NEEDS_CONFIRMATION` by the owner at sign-off, not `EXPLICIT_APPROVAL`).

## 1. Understanding

A BDM manager opens **Targets**, picks a month, sees the team's active BDMs and opens one to set a target per KPI of that BDM's
type. Achieved is computed live from the records for that month (never stored), shown as Target → Achieved → Achievement %. The
manager can copy last month's targets for the team. A BDM sees their own month's progress on **My Day**. Every change is audited.

## 2. Recommendations (R1–R12)

| # | Question | Recommended answer (used) |
|---|---|---|
| R1 | Catalogue per type | The type's own §A list (source order), then the §12 common list (K-C01…K-C07) — Appendix B.3 says the common list is offered to every type. A common KPI whose metric **and filter** are identical to one already in the type's list is shown once (Agent: K-C02≡K-A02, K-C04≡K-A03; School: K-C06≡K-S05; College: K-C06≡K-K04, K-C07≡K-K06). Agent 13, School 15, College 14 KPIs. |
| R2 | Month | `YYYY-MM`; the window is the IST month `[1st 00:00 IST, next 1st 00:00 IST)`. Default: the current IST month. |
| R3 | Which months a manager edits (AC4) | The current month and up to 12 months ahead. A **past** month only by `super_admin`; a manager → 422 "Past months' targets can only be changed by a super admin". More than 12 months ahead → 422 for everyone. |
| R4 | Target value | Whole number 0–100000 (the tel-022 bound). `null` in a batch clears the target (deletes the row). |
| R5 | Achievement % | `round(achieved × 100 / target)`; target 0 or not set → `null` ("—"); not tracked → `null`. It may exceed 100. |
| R6 | Future month | Achieved and % are `null` ("Month not started"); targets are editable. |
| R7 | Not-tracked KPIs | In the catalogue, so a target can be set; achieved shows "Not tracked" with its reason, never 0. |
| R8 | Copy last month | `POST /bdm/manager/targets/copy {month}` copies the previous month's targets of the actor's **active team BDMs** into `month`, only for (BDM, KPI) pairs that have no target there yet (never overwrites) and only KPIs in the BDM's catalogue. Same month rules as R3. |
| R9 | Scope | Writes and team reads: `bdm_manager` for BDMs reporting to them, `super_admin` all. A BDM outside the team → 404. Writes for an inactive BDM → 422. A BDM reads only their own (`GET /bdm/targets`). Other roles → 403. |
| R10 | Who is "the BDM" for an achieved count | bdm-015 R9: the record's BDM column; linked Schools = organizations assigned to the BDM with a `school_id`; attributed users = `converted_user_id` of enquiries with `bdm_user_id` = the BDM. Achieved is live (no snapshot): after a bdm-025 handover it follows the current owner, and a KPI definition changed in a later release re-computes past months. |
| R11 | Dating the School KPIs (M-23 / M-24) | Career Guidance: a `guidance_session` record that counts as completed (ENH-026 C5 `counts_as_completed`) dated by `completed_on`, or by `created_at` (IST) when it has none. Psychometric: a record with status `completed` dated by `test_date`, or `created_at` when it has none. Distinct students in the BDM's linked Schools. |
| R12 | Active Schools (M-17) | Linked Schools with a tier set and `tier_valid_until` NULL or ≥ the as-of date; as-of = the month's last day, or today for the current month. |

## 3. KPI catalogue (wording tightened from Appendix B; meaning unchanged)

Window = the IST month. "Own" = the BDM. Builders are the bdm-015 ones (shared, unchanged behaviour), generalized by org type
where Appendix B filters by type.

| Key | Label | K-rows | Metric | Definition |
|---|---|---|---|---|
| `college_meetings` | College Meetings | K-C01 | M-06 (college) | own completed appointments at college organizations, `starts_at` in month |
| `agent_meetings` | Agent Meetings | K-C02, K-A02 | M-06 (agent) | same, at agent organizations |
| `new_colleges` | New Colleges | K-C03 | M-14 (college) | college organizations created by the BDM in month |
| `new_agents` | New Agents | K-C04, K-A03 | M-15 | **Not tracked** — agent onboarding links arrive with bdm-019 |
| `appointments` | Appointments | K-C05 | M-07 | own appointments booked in month, minus those cancelled within the month |
| `mous` | MoUs | K-C06, K-S05, K-K04 | M-11 | MoU events by the BDM moving a MoU to `signed`, in month |
| `student_leads` | Student Leads | K-C07, K-K06 | M-12 | enquiries with `bdm_user_id` = the BDM created in month |
| `new_agent_leads` | New Agent Leads | K-A01 | M-14 (agent) | agent organizations created by the BDM in month |
| `agreements_signed` | Agreements Signed | K-A04 | M-11 (agent) | M-11 limited to agent organizations |
| `active_agents` | Active Agents | K-A05 | M-16 | **Not tracked** (bdm-019) |
| `agent_students` / `applications` / `enrollments` | Agent Students / Applications / Enrollments | K-A06–08 | M-21 | **Not tracked** — Agent CRM records are not linked to BDM organizations |
| `schools_contacted` | Schools Contacted | K-S01 | M-05 (school) | distinct school organizations with an own activity or own completed appointment in month |
| `school_meetings` | School Meetings | K-S02 | M-06 (school) | own completed appointments at school organizations |
| `school_presentations` | Presentations | K-S03 | M-18 (school) | own completed career guidance / psychometric / profile building presentations |
| `proposals` | Proposals | K-S04 | M-09 | MoU events by the BDM moving a MoU to `proposal_sent` |
| `active_schools` | Active Schools | K-S06 | M-17 | R12 |
| `students_onboarded` | Students Onboarded | K-S07 | M-22 | `school_students` created in month in the BDM's linked Schools |
| `career_guidance` | Career Guidance | K-S08 | M-23 | R11 |
| `psychometric_tests` | Psychometric Tests | K-S09 | M-24 | R11 |
| `colleges_contacted` | Colleges Contacted | K-K01 | M-05 (college) | as `schools_contacted`, college |
| `meetings` | Meetings | K-K02 | M-06 | own completed appointments, any organization |
| `college_presentations` | Presentations | K-K03 | M-18 (college) | own completed `it_training_presentation` appointments |
| `course_promotions` | Course Promotions | K-K05 | M-19 | own completed `course_promotion` appointments |
| `training_registrations` | Training Registrations | K-K07 | M-28 | distinct attributed users with an enrollment created in month |
| `internship_students` | Internship Students | K-K08 | M-29 | **Not tracked** — no IT internship model |
| `placement_candidates` | Placement Candidates | K-K09 | M-30 | distinct attributed users with a placement profile created in month |

Per type (order): **agent** new_agent_leads, agent_meetings, new_agents, agreements_signed, active_agents, agent_students,
applications, enrollments, then college_meetings, new_colleges, appointments, mous, student_leads. **school** schools_contacted,
school_meetings, school_presentations, proposals, mous, active_schools, students_onboarded, career_guidance, psychometric_tests, then
college_meetings, agent_meetings, new_colleges, new_agents, appointments, student_leads. **college** colleges_contacted, meetings,
college_presentations, mous, course_promotions, student_leads, training_registrations, internship_students, placement_candidates,
then college_meetings, agent_meetings, new_colleges, new_agents, appointments.

Computation: `bdm_metrics.monthly_counts(db, bdm_user_id, bdm_type, month, today)` — **one SELECT of scalar subqueries** (constant
query count). The daily builders take an instant window, so they are reused as is.

## 4. Data

`bdm_targets` (migration `0095_bdm_targets`, additive, guarded create, downgrade refuses while rows exist):

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| bdm_user_id | uuid FK users RESTRICT | |
| month | date | CHECK first day of the month |
| kpi_key | varchar(40) | validated against the BDM's catalogue in the service (the catalogue lives in code) |
| target | integer | CHECK 0 ≤ target ≤ 100000 |
| set_by_user_id | uuid FK users RESTRICT | the last writer |
| set_at | timestamptz | server `now()` on each write |
| created_at / updated_at | timestamptz | TimestampMixin |

`UNIQUE (bdm_user_id, month, kpi_key)` (`uq_bdm_targets_bdm_month_kpi`) — also the read index.

## 5. API (`app/api/bdm_targets.py`)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/bdm/targets?month=` | `bdm` (own) | `BdmTargetSheet` |
| GET | `/bdm/manager/targets?month=&limit=&offset=` | manager (team) / super_admin | `BdmTargetTeam`: `{month, month_status, editable, items:[{bdm, bdm_type, targets_set, kpi_count}], total, limit, offset}` (active team BDMs; two queries) |
| GET | `/bdm/manager/targets/{bdm_user_id}?month=` | manager (team) | `BdmTargetSheet`; outside team → 404 |
| PUT | `/bdm/manager/targets` | manager (team) | body `{month, items:[{bdm_user_id, kpi_key, target: int|null}]}` (1–200 items, no duplicate pair) → `{month, changed}` |
| POST | `/bdm/manager/targets/copy` | manager (team) | body `{month}` → `{month, copied}` |

`BdmTargetSheet`: `{month, month_status (past|current|future), editable, bdm {id, full_name}, bdm_type, kpis:[{key, label,
definition, tracked, target, achieved, percent}]}`. `editable` is false for the BDM's own read.

Errors: malformed month → 422; KPI not in the BDM's catalogue → 422 naming the KPI; target outside 0–100000 → 422; past month by a
manager → 422; > 12 months ahead → 422; BDM outside team → 404; inactive BDM write → 422; other roles → 403.

### Transactions and races
PUT: validate the whole body first (nothing written on any error); lock the affected existing rows `FOR UPDATE` to read their old
values; upsert with `INSERT … ON CONFLICT (bdm_user_id, month, kpi_key) DO UPDATE` (two managers saving at once cannot create a
duplicate; last write wins); delete cleared ones; one `AuditLog` row per BDM changed (`bdm_target.set`, metadata `{month, changes:
[{kpi, from, to}]}`); unchanged values are not written or audited; one commit. Copy: `INSERT … SELECT … ON CONFLICT DO NOTHING`
then one audit row per BDM that received targets (`bdm_target.copied`, `{month, from_month, kpis}`).

## 6. Web

- **`/bdm/manager/targets?month=`** (manager nav "Targets"): month picker (GET form, `type=month`), "Copy last month's targets"
  (inline `BdmConfirm`, then a notice "Copied N targets." / "Nothing to copy."), a table of active team BDMs: name + type,
  "Targets set n / m", **Set targets** link. Past month for a manager: "Past months are read-only." and no copy.
- **`/bdm/manager/targets/[bdmId]?month=`**: the KPI table — KPI (+ definition muted), Target (number input when editable), Achieved
  ("Not tracked" / "Month not started"), % ("—"); **Save targets** (one PUT of the changed rows; a blank input clears); client
  check of whole numbers 0–100000 before sending; success notice and re-read.
- **My Day:** a "Monthly targets" card (read alongside the page; never rejects): the KPIs with a target this month as
  "Label — achieved / target (percent)"; none set → "No targets set for this month."; read failure → "Unable to load your targets
  right now."
- States: server rendered; API down → `accessUnavailable`; wrong role → `accessDenied`; empty team → empty text. Mobile: the
  `.table-scroll` wrapper.

## 7. Security
Own reads are by the session user only; team reads/writes use `team_filter` (404 outside the team). The body never chooses
`set_by` or time. KPI keys are checked against the code catalogue (no free text stored). Audit rows and logs carry ids, the month,
KPI keys and numbers only. The existing cookie session and CSRF middleware cover PUT/POST. No new secrets or external calls.

## 8. Acceptance criteria → tests
1. KPI lists per type match §3 (R1) — service test of the three catalogues.
2. A target for a KPI outside the BDM's type → 422 — API test.
3. Achieved equals the definition — service tests per KPI builder new in this item, with records inside/outside the month and of
   another BDM; not tracked → `tracked false, achieved null`; constant query count.
4. Past months editable only by super_admin — manager 422, super_admin 200.
5. Positive: manager sets College Meetings 30, BDM completes 22 → achieved 22, percent 73.
6. Negative: another team's BDM → 404; negative target → 422; BDM on manager routes → 403; manager on `/bdm/targets` → 403.
7. Copy: copies missing pairs only, never overwrites, audited.
8. Audit: a change writes `bdm_target.set` with from/to; an unchanged save writes nothing.
9. Migration: chain, model/migration parity, guarded create, downgrade refusal.
10. Web: unit tests for the lib, editor, card and pages; Playwright journey manager sets → BDM sees on My Day.
