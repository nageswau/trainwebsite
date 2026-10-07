# bdm-015 — Daily activity report (derived + note + submit) — design

- **Feature:** bdm-015 (`docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-015; Appendix B M-rows)
- **Decision:** `DEC-SCOPE-096` (drafted; renumbered on merge if another item takes it). Migration `0092_bdm_daily_reports` after
  `0091_lead_appointments`.
- **Evidence:** `DEC-SCOPE-055` D9 (derived + log + note + submit), D22 / Q-13 (not enforced; submitting snapshots and locks the report
  and that day's activity edits; the manager can comment), D31 (School daily sessions = the BDM's completed presentation appointments).
- **Dependencies:** bdm-007, bdm-009, bdm-010 (all on `main`); bdm-005 (MoU events) and bdm-017 (lead attribution) are on `main`, so
  their counts are computed. bdm-019 (agent onboarding link) and the Agent CRM counts (M-21) are not built: "Not tracked".
- **Status of answers:** the owner directed this session to proceed with the recommended answers; R1–R10 below are those
  recommendations (`NEEDS_CONFIRMATION` by the owner at sign-off, not `EXPLICIT_APPROVAL`).

## 1. Understanding

A BDM ends the day by opening **Daily report**, seeing the day's counts computed from what they recorded (activities, appointments,
trips, MoU changes, leads, follow-ups, school students), adding a short note and **submitting**. Submission freezes the counts
(history never rewrites) and locks that day's activity log. The reporting manager sees, for the team, who submitted and who did
not, opens a report, and may leave a comment. Nothing is enforced (no blocking reminders) — "missing" is information.

## 2. Owner-facing recommendations (R1–R10)

| # | Question | Recommended answer (used) |
|---|---|---|
| R1 | Which counts per BDM type | Exactly the source lists: **College** = §11 common (11 counts); **Agent** = Agent §G (11); **School** = School §G (11). Each count is one Appendix B M-row (§3). |
| R2 | "Calls made" | **Outbound calls** — bdm-009 V6's tightened wording of M-01, so the report equals the Activities page tile. |
| R3 | Late submission window | Today or up to **7 IST days back** (bdm-009's backdate window). Older days: read-only preview, no submit. Future day → 422. |
| R4 | Note | Optional, trimmed, ≤ 2000 characters (a no-activity day may be submitted with a note such as "leave"). |
| R5 | What submission locks | That day's activities: edit, delete **and backdated create** onto that day → 409. Other records (appointments, trips, tasks) are not locked (D22 names activities only). |
| R6 | Resubmit / unsubmit | Neither. A second submit → 409. No un-submit (keeps the snapshot meaningful). |
| R7 | Manager comment (D22) | One comment per submitted report, set/replaced by a manager in team scope (or super_admin); ≤ 1000 characters; audited. A missing report can't be commented. |
| R8 | Manager team view | A **7-day grid** (the chosen date and the six days before) × team BDMs: Submitted (time) / Missing / "—" for days before the BDM's profile existed. |
| R9 | Who is "the BDM" for a count | The record's BDM column (`bdm_user_id` / `assignee_user_id` / `created_by_user_id` / MoU event `actor_user_id`); for M-27 the BDM's assigned organizations linked to a School. After a bdm-025 handover live previews follow the current owner; submitted snapshots never change. |
| R10 | Not tracked | Shown as the label "Not tracked" with its reason, never 0; stored in the snapshot as `tracked: false, count: null`. |

## 3. Metric catalogue (wording tightened from Appendix B; meaning unchanged)

Window = the IST day `[00:00, 24:00)` as an instant range. "Own" = the BDM.

| Key | Label | M-row | Definition (exact) |
|---|---|---|---|
| `calls_made` | Calls made / Calls | M-01 | own `bdm_activities`, channel `call`, direction `outbound`, `occurred_at` in window |
| `school_visits` | School visits | M-04 | own activities, channel `visit`, in window |
| `colleges_contacted` / `agents_contacted` / `schools_contacted` | … contacted | M-05 | distinct organizations of that `org_type` with ≥ 1 own activity in window or ≥ 1 own completed appointment with `starts_at` in window |
| `meetings_completed` | Meetings completed / Meetings | M-06 | own appointments, status `completed`, `starts_at` in window |
| `appointments_fixed` | Appointments fixed | M-07 | own appointments `created_at` in window, minus those with a `cancelled` event in the same window |
| `travel_completed` | Travel completed | M-08 | own trips, `travel_status = completed`, `completed_at` in window |
| `proposals_sent` | Proposals sent / Proposals | M-09 | MoU events by the BDM with `to_status = proposal_sent` and `from_status` NULL or different, in window |
| `mous_discussed` | MoUs discussed | M-10 | own completed appointments of type `mou_discussion` / `agreement_discussion`, `starts_at` in window |
| `mous_signed` | MoUs signed / Agreements / MoUs | M-11 | MoU events by the BDM with `to_status = signed`, `from_status` NULL or different, in window |
| `student_leads` | Student leads generated | M-12 | `enquiries` with `bdm_user_id` = the BDM, `created_at` in window |
| `follow_ups_completed` | Follow-ups completed / Follow-ups | M-13 | own `bdm_tasks` kind `follow_up`, status `done`, `completed_at` in window |
| `new_prospects` | New prospects | M-14 | `bdm_organizations` of `org_type = agent` created by the BDM in window |
| `new_agents` | New agents | M-15 | **Not tracked** — agent onboarding links arrive with bdm-019 |
| `agent_training` | Agent training | M-20 | own completed appointments of type `product_training`, `starts_at` in window |
| `applications_generated` / `enrollments_generated` | … generated | M-21 | **Not tracked** — Agent CRM records are not linked to BDM organizations yet |
| `presentations` | Presentations | M-18 | own completed School presentation appointments (career guidance / psychometric / profile building) in window |
| `students_generated` | Students generated | M-27 | `school_students` created in window in Schools linked (`bdm_organizations.school_id`) to organizations assigned to the BDM |
| `career_guidance_sessions` | Career guidance sessions | M-25 | own completed `career_guidance_presentation` appointments in window (D31) |
| `psychometric_sessions` | Psychometric sessions | M-26 | own completed `psychometric_presentation` appointments in window (D31) |

Per type (order as the source):
- **college:** calls_made, colleges_contacted, agents_contacted, meetings_completed, appointments_fixed, travel_completed, proposals_sent, mous_discussed, mous_signed, student_leads, follow_ups_completed
- **agent:** calls_made, agents_contacted, meetings_completed, new_prospects, new_agents, mous_signed (label "Agreements"), agent_training, follow_ups_completed, student_leads, applications_generated, enrollments_generated
- **school:** schools_contacted, calls_made (label "Calls"), meetings_completed (label "Meetings"), school_visits, presentations, proposals_sent (label "Proposals"), mous_signed (label "MoUs"), follow_ups_completed (label "Follow-ups"), students_generated, career_guidance_sessions, psychometric_sessions

Computation: **one SELECT of scalar subqueries** (the bdm-021 pattern) — a constant query count whatever the data size. The module
`app/services/bdm_metrics.py` gains `daily_counts(db, bdm_user_id, bdm_type, day)`; bdm-016/023/024 reuse its subquery builders with a
month window.

## 4. Data

`bdm_daily_reports` (migration `0092_bdm_daily_reports`, additive, guarded create, downgrade refuses while rows exist):

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| bdm_user_id | uuid FK users RESTRICT | |
| report_date | date | the IST day |
| bdm_type | varchar(20) | the type at submission (CHECK agent/school/college) |
| counts | JSON | the snapshot: list of `{key, label, definition, tracked, count}` |
| note | varchar(2000) NULL | |
| submitted_at | timestamptz | server `now()` |
| manager_comment | varchar(1000) NULL | |
| manager_comment_by_user_id | uuid FK users RESTRICT NULL | |
| manager_commented_at | timestamptz NULL | CHECK: the three comment columns are all NULL or all set |
| created_at / updated_at | timestamptz | TimestampMixin |

`UNIQUE (bdm_user_id, report_date)` (`uq_bdm_daily_reports_bdm_date`) — also the manager grid's index. A row exists only when
submitted (a draft is never stored — the preview is live).

## 5. API (`app/api/bdm_daily_reports.py`, prefix `/bdm`)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/bdm/daily-reports/{report_date}` | `bdm` (own) | `BdmDailyReportOut`: live preview (status `draft`) or the snapshot (`submitted`). Future → 422. |
| POST | `/bdm/daily-reports/{report_date}/submit` | `bdm` (own) | 201 + `BdmDailyReportOut`. Body `{note?}`. Future → 422; older than 7 days → 422; already submitted → 409. |
| GET | `/bdm/manager/daily-reports?date=&limit=&offset=` | `bdm_manager` (team) / super_admin | `BdmDailyReportGrid`: `{dates[7], items:[{bdm, bdm_type, days:[{date, status, submitted_at}]}], total, limit, offset}`. Future → 422. |
| GET | `/bdm/manager/daily-reports/{bdm_user_id}/{report_date}` | manager (team) | `BdmDailyReportOut` (preview or snapshot). Outside team → 404. |
| PUT | `/bdm/manager/daily-reports/{bdm_user_id}/{report_date}/comment` | manager (team) | `{comment}` 1–1000 chars → `BdmDailyReportOut`. Not submitted → 409; outside team → 404. |

`BdmDailyReportOut`: `report_date, bdm {id, full_name}, bdm_type, status (draft|submitted), submitted_at, note, counts[],
can_submit, submit_window_days, manager_comment {text, by {id, full_name}, at} | null`.

Any other role on BDM routes → 403 (`bdm_context` / `require_manager`). A manager calling the submit route → 403 ("submitting for
another BDM"). There is no path that names another BDM for submission.

### Transactions and races
- Submit: take `pg_advisory_xact_lock(hashtextextended('bdm_daily_report:<bdm>:<date>', 0))`, check no row, compute counts, insert,
  audit (`bdm_daily_report.submitted`, ids + date only, never the note), commit. A concurrent duplicate that slips past (it can't,
  given the lock) still hits the unique constraint → 409.
- Activity create / update / delete take the same advisory lock for the activity's day after their existing locks and refuse with
  409 "This day's report has been submitted — its activities can't be changed" when a report exists. So an activity write and a
  submit for the same day serialize: either the activity is in the snapshot, or it is refused.
- `editable(activity, now, submitted=False)` gains the "report not submitted" condition (bdm-009 AC4), so `permissions.can_change`
  is false on a submitted day (one extra query per list: whether today's report exists for the activity owner).

## 6. Web

- **`/bdm/daily-report?date=`** (BDM nav "Daily report"): date picker form (GET, `max=today`, invalid/future → today with a note,
  the activities-page rule), the count tiles (`.kpi-grid` / `.kpi-tile`, "Not tracked" with its reason under the label), each
  tile's definition available as small muted text, the note textarea with a counter, and **Submit report** → inline `BdmConfirm`
  ("Submitting saves these counts and locks this day's activities. You can't undo it.") → success notice, read-only state. Submitted:
  the submitted time, the note, the manager's comment if any. Outside the window: "Reports can be submitted up to 7 days back."
- **`/bdm/manager/daily-reports?date=`** (manager nav "Daily reports"): a table (BDMs × 7 days) with Submitted / Missing / —; each
  Submitted or Missing cell links to the detail page; a phone layout uses the existing horizontal table scroll wrapper.
- **`/bdm/manager/daily-reports/[bdmId]?date=`**: the same report card read-only + comment form (submitted only).
- States: loading via server rendering; API down → `accessUnavailable`; wrong role → `accessDenied`; empty team → empty text.

## 7. Security
Own-scope reads are by the session user only; team reads use `team_filter` (404 outside the team, as other manager detail routes).
Note and comment are stored as text and rendered as text (React escaping). Audit rows and logs carry ids and dates only.
No new auth, CSRF or secret surfaces (existing cookie session and CSRF middleware apply to POST/PUT).

## 8. Acceptance criteria → tests
1. Every §11/§G count is computed exactly or labelled "Not tracked" — service tests per type with seeded records inside and outside
   the window and of other BDMs.
2. Submit twice → 409 — API test.
3. Snapshot unchanged by later record edits — submit, then add/complete records directly in the DB; GET returns the old counts.
4. Manager sees who has not submitted — grid test (submitted, missing, before-start, other team excluded).
5. Future → 422; older than 7 days → 422; manager on submit → 403; another team's BDM → 404.
6. Activity lock: create (backdated), edit, delete on a submitted day → 409; `can_change` false.
7. Comment: manager comment on submitted; on missing → 409; out of team → 404; BDM can't comment (403).
8. Migration: chain, model/migration parity, guarded create, downgrade refusal.
9. Web: unit tests for the helpers and components; Playwright journey BDM submit → manager sees Submitted and comments.
