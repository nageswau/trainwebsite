# AGN-013 — Enrollment confirmation + commission trigger (Step 9): Design

**Status:** Section 1 (data, API, backend, security) reviewed by the owner in-session 2026-10-02; Sections 2–3 (frontend, tests)
recorded here for the owner's review. **Branch:** `feature/agn-013-enrollment-confirmation` (from `origin/main` `268d132`).
**Decision:** `DEC-SCOPE-052` (provisional: `050` is AGN-008, `051` is AGN-014; renumber if another branch merges a `052` first).
**Builds on:** AGN-008 (`DEC-SCOPE-050`, agency applications, migration `0057`), AGN-014 (`DEC-SCOPE-051`, Master-only commission),
AGT-003 (`_maybe_trigger_agent_commission`, `DATA_MODEL.md` §6.3 / `ADR-012`), `DEC-SCOPE-005` (commission on the student joining).
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 Step 9; `docs/delivery/AGENT_CRM_BACKLOG.md`
ang-013 (`DERIVED_BLUEPRINT`). Approval is the owner's in-session answers below, not the documents.

## 1. Intent

**Owner's requirement:** enrollment confirmed, university, course, intake, enrollment date, university student ID, final status
ENROLLED.

**Owner's acceptance criteria:** enrolling creates exactly one estimated commission for the org; re-saving does not duplicate it; an
enrollment date is required; a future date beyond intake is flagged (a warning, not blocked).

**Owner's answers (in-session, 2026-10-02, `EXPLICIT_APPROVAL`):**

| # | Decision |
|---|---|
| E1 | Only an agency **Master** confirms enrollment. Staff see the enrollment details read-only; the action is `403` for them. This narrowly amends `DEC-SCOPE-050` A4 for a dedicated route only: the agent status route still refuses `enrolled`. |
| E2 | Intake stays free text. A best-effort parser recognises "Month YYYY" forms; the check warns, never blocks; an unparseable intake says so. |
| E3 | The commission trigger is unchanged: `agent_id` = the application's `agent_id`; every Master of the org sees it through `org_member_ids` (as `DEC-SCOPE-051` shipped). No `agent_commissions` change. |
| E4 | After enrollment a Master may correct the enrollment date and university student ID; a Master may also add them to an application a counselor/admin already enrolled. Neither creates a commission. |
| E5 | University, course and intake are shown read-only from the application; changes go through the existing Edit (AGN-008 PATCH). University stays fixed (A10). |
| E6 | Enrollment is confirmed from `offer`, `visa_documentation` or `status_tracking` only; earlier stages are `422`. |
| E7 | The university student ID is optional (it may be issued later) and returned only on the agency's application detail. |
| E8 | Approach A: a dedicated `PUT …/{id}/enrollment` in the AGN-008 router (rejected: extending `POST …/status`; a separate 1:1 table). |

## 2. Out of scope

- Commission reversal when an enrolled application is later changed (not modelled; an enrolled application cannot be withdrawn).
- Structured intake (D16) and any change to create/edit forms.
- Notifications to the student (D19: students get nothing) and any change to the counselor/admin/university-rep paths.
- A new rate limiter, a shared Master-check helper, or any dependency.

## 3. Data (migration `0058_agent_app_enrollment`)

`overseas_applications` gains three nullable columns; no existing row is read or written:

| Column | Type | Meaning |
|---|---|---|
| `enrollment_date` | `DATE` | The date the student enrolled (from the agency). |
| `university_student_id` | `VARCHAR(60)` | The university's student number (optional). |
| `enrollment_confirmed_at` | `TIMESTAMPTZ` | When the agency first recorded enrollment details. |

Adds are guarded (0057's idiom: `0001` builds a fresh database from the models). `downgrade()` refuses while any of the three
columns hold data, rather than silently dropping them. The actor is in the history row (`changed_by_id`) and the audit row.

## 4. API

`PUT /api/v1/workflows/overseas/agent/crm/applications/{id}/enrollment` — body `AgentApplicationEnrollment` (`extra="forbid"`):

| Field | Rule |
|---|---|
| `enrollment_date` | `date`, required (missing → 422 FastAPI). 2000–2100 (`_application_date`). Future allowed. |
| `university_student_id` | `str \| null`, optional; `clean_free_text(…, 60)` (trimmed; control characters → 422); blank → null. |
| `expected_status` | `str` (≤ 50), **required**: the status the caller saw. |
| `notes` | `str \| null`, optional (≤ 2000, `clean_free_text`); written to the history row on first confirmation only. |

Response `200 {"application": detail}` (the AGN-008 envelope). `detail()` gains, additively: `enrollment_date`,
`university_student_id`, `enrollment_confirmed_at`, `enrollment_check` (`"after_intake" | "intake_unrecognised" | null`). List
items are unchanged. No existing route, schema or response field changes.

### 4.1 Order of checks

1. Unauthenticated → `401` (`get_current_user`).
2. `_gate`: non-agent or inactive organisation/member → `403`.
3. Staff → `403 "Only an agency Master can confirm enrollment"` — before any load, so no id is probed.
4. `_locked`: organisation lock, then the row `FOR UPDATE`; outside the caller's scope (another org) → `404`.
5. `_refuse_closed`: archived student or withdrawn application → `409`.
6. `expected_status != status` → `409` (`STALE`).
7. Status `enquiry` / `eligibility_evaluation` / `university_selection` (or legacy free text) → `422 "An offer is needed before enrollment"`.
8. **Confirm** (status `offer` / `visa_documentation` / `status_tracking`): set the two fields, `enrollment_confirmed_at = now()`,
   `status = "enrolled"`; one `ApplicationStatusHistory` row (old → enrolled, notes, `changed_by` = Master);
   `_maybe_trigger_agent_commission(db, item, old, user)` (commission, Master notifications, `agent.commission_auto_create` audit);
   audit `overseas.application.enroll` `{from_status, to_status}`.
9. **Correct** (status `enrolled`): set changed fields only; `enrollment_confirmed_at` if still null; audit
   `overseas.application.enrollment_update` `{fields}`; no history row, no commission call. No change → no write, `200`.
10. One `commit`. Any failure (including the audit or commission insert) rolls the whole request back.

### 4.2 Exactly one commission

- Two Masters at once: the organisation lock serialises them; the second sees `enrolled` != its `expected_status` and gets `409`
  (stale); after a reload a re-save is a correction.
- Agent enrollment vs counselor PATCH/`/advance`: both hold the application row lock. A counselor landing first turns the agency call
  into a `409` (stale); an agency call landing first leaves the counselor's write with `old_status == "enrolled"`, so the trigger
  returns early.
- `agent_commissions.application_id` is `UNIQUE`: the database backstop.

### 4.3 Date check (E2)

`intake_end(text) -> date | None` (pure): `Sep 2027`, `Sept 2027`, `September 2027`, `09/2027`, `9/2027`, `2027-09`, `2027/09`
(case-insensitive, surrounding text such as "Fall" ignored only when a month and a year are both found) → the last day of that
month; anything else → `None`. `enrollment_check`: `null` when no `enrollment_date`; `"intake_unrecognised"` when `intake_end` is
`None`; `"after_intake"` when `enrollment_date > intake_end` **and** `enrollment_date > today (UTC)`; else `null`. Computed on read;
never stored, never blocks.

## 5. Frontend

- `AgentApplicationsSection` passes `memberRole` to `AgentApplicationsPanel`, which passes `isMaster` to `AgentApplicationDetail`
  (the AGN-004/007 `memberRole` pattern; the server stays the authority).
- New `AgentApplicationEnrollment.tsx`, rendered in the detail between the fields and `AgentApplicationStatusForm` (unchanged:
  `nextStages` still stops at `status_tracking`):
  - **Enrolled:** heading "Enrollment", a final-status badge (`badge badge-done`, text "Enrolled" — not colour alone), a `<dl>`
    with University, Course, Intake, Enrollment date, University student ID ("Not recorded"), Confirmed on. `enrollment_check`
    shows a `.form-warning` line. Master and not read-only: "Edit enrollment details" opens the form prefilled.
  - **Offer / visa / status tracking:** Master — "Confirm enrollment" opens the form (read-only University/Course/Intake summary,
    date `type="date"` required, university student ID optional `maxLength=60`, note optional); submit shows an inline confirmation
    ("Confirm enrollment? A commission will be estimated and the application can no longer be withdrawn." — Yes / Go back, Escape
    = Go back, focus returns). Staff — a muted line "An agency Master confirms enrollment."
  - **Earlier stages, withdrawn, archived:** nothing (read-only reasons already shown).
- States: a `useRef` in-flight guard and "Saving…" disabled button; `422` keeps the form and input with the server message
  (the detail's notice: `role="alert"`, focused); `409`/`404` go to the
  detail's existing `failed` (reload to the real state); network failure → `sendJson`'s message. Success → the detail's notice
  ("Enrollment confirmed." / "Enrollment details saved."), focus to the notice, and `onChanged` updates the list card.
- Every input has a `<label htmlFor>`; the form uses the existing `form`/`field`/`actions`/`btn` classes, which stack at 320 px.
- `lib/agentApplications.ts`: `ENROLLABLE_STAGES`, `canConfirmEnrollment(status)`, `ENROLLMENT_CHECK_TEXT`, and the four detail
  fields on `AgentApplicationDetail`.

## 6. Security

| Concern | Control |
|---|---|
| AuthN | existing cookie session (`get_current_user`). |
| AuthZ / role escalation | `_gate` + Master-only check; Staff `403`; body cannot set `status`, `agent_id`, `university_id` (`extra="forbid"`). Commission `agent_id` comes from the stored row. Payout still needs Overseas Admin approval (AGT-004 unchanged). |
| IDOR | scope in the `WHERE` of `load_scoped`; other org → `404`. |
| Input / XSS / SQLi | Pydantic at the boundary; `clean_free_text`; React escaping; ORM bound parameters only. |
| CSRF | platform `SameSite=Lax` cookie + JSON-only `PUT`, as every AGN-008 write (existing residual unchanged). |
| Sensitive logs | log lines and audit metadata carry ids, statuses and field names only — never the university student ID or notes. |
| Exposure | the student ID is only in the agency's detail allowlist; counselor/admin/rep responses unchanged. |
| Rate limiting | none added (none platform-wide; once per application; locks serialise corrections). Accepted risk, as AGN-008. |
| Audit | every confirmation and correction audited in the same transaction (SEC-001 fail-closed). |

Logging: `agent_application_enrolled` (org, actor, application, from_status) and
`agent_application_enrollment_updated` (fields) through the router's `_log`.

## 7. Acceptance criteria

1. **AC01** Master confirms from `offer`/`visa_documentation`/`status_tracking` → 200, status `enrolled`, the two fields and
   `enrollment_confirmed_at` set, one history row, one `estimated` commission (amount 0, `system_trigger`, `agent_id` = the
   application's agent), visible in the Master's `GET …/agent/commissions`.
2. **AC02** Re-saving (same or different values) → 200, still exactly one commission, no new history row; changes audited as
   `enrollment_update`.
3. **AC03** Missing `enrollment_date` → 422 and nothing written.
4. **AC04** `enrollment_check` = `after_intake` for a future date past the intake month; `intake_unrecognised` for "Next intake";
   `null` otherwise; the save still succeeds.
5. **AC05** Staff → 403; other org → 404; archived / withdrawn → 409; stale `expected_status` → 409; pre-offer stage → 422;
   unknown body field → 422 — each with no history, audit or commission row.
6. **AC06** A counselor-enrolled application: a Master adds details → 200, no commission created by the agency call.
7. **AC07** Concurrent confirmations by two Masters → one 200 and one 409, exactly one commission and one `enrolled` history row;
   a counselor's enrolment landing first → the agency call is 409 and creates no commission.
8. **AC08** The agent status route still returns 403 for `enrolled` (AGN-008 A4 unchanged).
9. **AC09** UI: Master sees Confirm on eligible stages, Staff do not; confirmation step; enrolled view with badge and warning;
   422 keeps input; keyboard (Escape) and labels.

## 8. Tests (lite runs per task; the owner runs full suites)

- `apps/api/tests/test_agn_013_intake.py` — `intake_end` and `enrollment_check` (pure).
- `apps/api/tests/test_agn_013_migration.py` — chain/single head, nullable columns, schema bounds.
- `apps/api/tests/test_agn_013_enrollment.py` — AC01–AC06, AC08, audit/log content.
- `apps/api/tests/test_agn_013_concurrency.py` — AC07.
- `apps/web/tests/lib/agentApplications.test.ts` (extend) and `apps/web/tests/components/AgentApplicationEnrollment.test.tsx`.
- `apps/web/tests/e2e/agn-013-enrollment.spec.ts` — written; run during the owner's browser validation.
- Regression lite set: `test_agn_008_status.py`, `test_agn_008_security.py`, `test_agt_003_commission_accrual.py`,
  `test_agn_014_commission_reports.py`, `AgentApplicationDetail.test.tsx`, `AgentApplicationsPanel.test.tsx`.

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| A4 (agents never enrol) | the status route is untouched; AC08 pins it. |
| Commission duplication | locks + trigger guard + `UNIQUE`; AC02, AC07. |
| `detail()` allowlist | additive fields only; the AGN-008 security allowlist test still forbids `agent_id`, `student_id`, email, phone. |
| Migration chain | `0058` after `0057`; AGN-009/016 branches may also claim `0058` → re-chain on merge. |
| Shared `workflows.py` | not edited; the trigger is imported, as `_notify_user` already is. |
