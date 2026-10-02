# AGN-012 — Visa for agent-managed applications (Step 8): Design

**Status:** Sections 1 (data, API, rules) and 2 (frontend, errors, tests) reviewed by the owner in-session 2026-10-02; this written
spec awaits the owner's review. **Branch:** `feature/agn-012-agent-visa` (from `origin/main` `e0395d6`).
**Decision:** `DEC-SCOPE-055` (next free on `main` @ `e0395d6`; the open `feature/agn-010-offer-details` branch may claim it too —
whichever merges second renumbers).
**Builds on:** AGN-008 (`DEC-SCOPE-050`, agency applications, D8 forward-only), AGN-009 (`DEC-SCOPE-052`, agency documents and
verification), AGN-013 (`DEC-SCOPE-054`, the route/panel pattern), VISA-001/002/003 (`DEC-SCOPE-006`, `VisaCase`, checklist gate,
`VISA_DECISION_DISCLAIMER`).
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 Step 8; `docs/delivery/AGENT_CRM_BACKLOG.md`
ang-012 and Q-08/D14 (`DERIVED_BLUEPRINT`). Approval is the owner's in-session answers below, not the documents.

## 1. Intent

**Owner's requirement:** visa documents, application date, appointment, interview, status and decision.

**Owner's acceptance criteria:** a decision can be set only at stage `decision`; the interview date may not precede the application
date; the existing checklist rule blocks advancing past `checklist` with unverified documents.

**Owner's answers (in-session, 2026-10-02, `EXPLICIT_APPROVAL`):**

| # | Decision |
|---|---|
| V1 | **Master and Staff** both start, edit, advance and decide a visa case (D8). Staff only on students assigned to them (G4); out of scope is `404`. |
| V2 | Decision outcomes are **approved / refused / withdrawn**, set only at stage `decision`, and **final once recorded**: the case becomes read-only. (Confirms backlog D14, which was never in this register.) |
| V3 | A new case **always starts at `checklist`**. Stage moves are **forward-only; skipping stages is allowed**; leaving `checklist` always runs the verification gate. |
| V4 | The appointment is the existing `visa_cases.appointment_date` (date only; agencies can clear it). New `visa_application_date` and `interview_date` are **dates**; `interview_date >= visa_application_date`, same day allowed. |
| V5 | The visa case is **independent of the application stage.** A case can be started when the application is at `offer`, `visa_documentation` or `status_tracking`. Visa actions never change the application stage. Writes are refused on withdrawn or enrolled applications and archived students; an existing case stays readable. |
| V6 | Checklist items are **picked from the AGN-009 agency document types, excluding "Other"**. An item is satisfied when the **latest** document of that type **attached to this application** is `verified`. No new document types. The checklist is editable only while the case is at `checklist`. |
| V7 | **Re-application after a final decision is out of scope:** one visa case per application. |
| V8 | The new fields are **agency-only**. Student, counselor, admin and school visa responses are unchanged. No notifications. |
| V9 | **Approach A:** `POST`/`PATCH …/crm/applications/{id}/visa` in the AGN-008 router, rules in a new `services/agent_visa.py`, a `visa` block in the application detail. The `workflows.py` visa routes are untouched. |

## 2. Out of scope

- Re-application / a second case per application (V7).
- Any change to `POST /workflows/overseas/visa`, `PATCH /workflows/overseas/visa/{id}`, `GET …/visa-checklist`, `GET …/visa-status`,
  `GET /overseas/visa/interview-prep`, `_checklist_verification`, `VISA_CASE_STAGES`, or the school, portal and report readers.
- Coupling visa progress to the application stage (V5), the commission trigger, enrollment.
- New document types; listing documents per application; notifications; dashboard KPIs (ang-018).
- A unique index on `visa_cases.application_id` (it would change the counselor route's failure mode).
- Fixing `seed.py`'s `status="not_started"` (pre-existing; the agency rules tolerate it, §4.1).

## 3. Data (migration `0061_agent_visa_details`)

Four nullable columns on `visa_cases`; no existing row is read or written:

| Column | Type | Meaning |
|---|---|---|
| `visa_application_date` | `Date` | when the visa application was lodged |
| `interview_date` | `Date` | visa interview |
| `decision` | `String(20)` + CHECK `decision IN ('approved','refused','withdrawn')` (NULL allowed) | the authority's outcome, recorded by the agency |
| `decided_at` | `DateTime(timezone=True)` | when the decision was recorded |

- The model carries the columns and the named CHECK (`ck_visa_cases_decision`), so 0001's `create_all` builds them; every add in
  0061 is guarded (0060's idiom), including the constraint.
- `downgrade()` refuses while any of the four columns is non-null, then drops the constraint and columns.
- Revision id ≤ 32 characters; `down_revision = "0060_agent_app_enrollment"`.
- `test_agn_013_migration.py` pins the head to 0060; it is relaxed to the single-head form (as `d871cdd` did for AGN-016).

## 4. API

Both routes live in `app/api/agent_applications.py` (prefix `/workflows/overseas/agent/crm/applications`) and return
`{"application": detail}`. Entry is the enrollment route's: `_gate` → `_locked` (organisation lock, then the application row,
scoped — out of scope `404`) → `_refuse_closed` (archived `409`, withdrawn `409`) → enrolled `409` (`VISA_ENROLLED`). The visa case
is loaded **after** the application lock, so every agency visa write for one application is serialised. One commit per request.

### 4.1 `POST …/{id}/visa` — start a case (`201`)

Body (`AgentVisaStart`, `extra="forbid"`):
- `expected_status: str` (required; the application stage the screen shows)
- `checklist: list[VisaDocumentType]` (unique; may be empty — today's rule passes an empty checklist)
- `visa_application_date`, `appointment_date`, `interview_date`: optional dates (2000–2100, `_application_date`)

Order of checks after entry:
1. `expected_status != application.status` → `409 STALE`.
2. Application stage not in `offer | visa_documentation | status_tracking` → `422 VISA_OFFER_NEEDED`.
3. A case already exists → `409 VISA_EXISTS`.
4. Date order (§4.3) → `422`.
5. Create the case at `checklist`; audit `overseas.application.visa_start` (`{"checklist_items": n}`).

### 4.2 `PATCH …/{id}/visa` — update a case (`200`)

Body (`AgentVisaUpdate`, `extra="forbid"`):
- `expected_stage: str` (required; the visa stage the screen shows)
- optional `to_stage: VisaStage`, `checklist: list[VisaDocumentType]` (unique), the three dates (explicit `null` clears),
  `decision: Literal["approved","refused","withdrawn"]`

Order of checks after entry:
1. No case → `404 VISA_NOT_FOUND`.
2. `case.decision` is set → `409 VISA_DECIDED` (V2).
3. `expected_stage != case.status` → `409 VISA_STALE`.
4. `checklist` sent and the case is not at `checklist` (or a stage outside `VISA_CASE_STAGES`) → `422`.
5. `decision` sent and the case was not **already** at `decision` before this request → `422 VISA_DECISION_STAGE`.
   (`decision` together with `to_stage` in one request is therefore refused.)
6. `to_stage`: must be after the current stage (`422` otherwise). A stage outside `VISA_CASE_STAGES` (legacy `not_started`) counts
   as before `checklist`.
7. Gate (VISA-001-AC02): when the current stage is at or before `checklist` and `to_stage` is after it, every item of the
   **resulting** checklist must be `verified` (§4.4) → else `422 "Cannot advance past the checklist stage -- not yet verified: X, Y."`
   (the existing wording).
8. Date order on the resulting values (§4.3) → `422`.
9. Apply. Nothing changed → no write, no audit. Otherwise one audit row:
   `visa_decision` (`{"decision": …}`) > `visa_advance` (`{"from_stage", "to_stage"}`) > `visa_update` (`{"fields": [...]}`);
   a request that both advances and edits writes `visa_advance` with `fields`. Recording a decision sets `decided_at = now()`.

### 4.3 Date order (V4)

After merging the request with stored values: if `visa_application_date` and `interview_date` are both set,
`interview_date < visa_application_date` → `422` with `loc` on `interview_date` ("The interview date cannot be before the visa
application date"). Same day is accepted. No other date rule (an appointment may fall anywhere).

### 4.4 Checklist verification (V6)

New helper in `services/agent_visa.py`: for each checklist item, the `StudentDocument` rows with `application_id == app.id` and
`document_type == item`, newest by `(created_at, id)`; its `verification_status`, or `not_uploaded`. Documents not attached to the
application do not count. `workflows._checklist_verification` is not changed (its unordered pick stays the counselor route's behavior).

### 4.5 Detail (`services/agent_applications.detail`)

Adds `"visa": null` or:

```json
{"id": "…", "stage": "checklist", "checklist": [{"item": "Passport", "verification_status": "verified"}],
 "visa_application_date": null, "appointment_date": null, "interview_date": null,
 "decision": null, "decided_at": null, "disclaimer": "<VISA_DECISION_DISCLAIMER>"}
```

Only on the single-application detail (and therefore every write's response); the list items are unchanged. A case opened by an
overseas admin through the old route is shown as is (free-text items not matching an agency type show `not_uploaded`).

### 4.6 Activity

`overseas.application.visa_start|visa_update|visa_advance|visa_decision` are added to the AGN-021 allowlist
(`services/staff_activity.py`); the subject resolver already handles `overseas_application`. Audit metadata carries field names,
stages and the decision only — never dates' values or document names beyond the item count.

## 5. Frontend

**`lib/agentApplications.ts`:** `Visa` type; `visa?: Visa | null` on `AgentApplicationDetail`; `VISA_STAGES`, `visaStageLabel`,
`nextVisaStages(stage)` (forward-only, legacy stage = before `checklist`), `canStartVisa(status)`, `VISA_DOCUMENT_TYPES`
(`DOCUMENT_TYPES` minus "Other"), `VISA_DECISIONS`.

**`components/AgentApplicationVisa.tsx`** (the `AgentApplicationEnrollment` pattern), mounted in `AgentApplicationDetail` next to
Enrollment inside its own `Fragment key={visa?.stage ?? "none"}` so a stage change resets its forms.

| State | Shown |
|---|---|
| No case, application before `offer` | nothing |
| No case, eligible, writable | "No visa case yet" + **Start visa case** → form: checklist checkboxes, three optional dates |
| Case | stage badge; `<dl>` of the three dates; checklist with each item's status and the hint "Upload and verify it under Documents"; **Edit details** (dates; checklist while at `checklist`); **Move to** select of forward stages with a confirm step |
| Case at `decision`, undecided | **Record decision** radio group + confirm ("A recorded decision cannot be changed") |
| Decided | read-only: decision, recorded date, disclaimer |
| Application read-only / enrolled | read-only view of any case; no actions |

Loading and gone states are the detail's (the visa block arrives with it). Errors as Enrollment: `inFlight` guard; `422` maps field
errors (`visa_application_date`, `appointment_date`, `interview_date`, `checklist`, `to_stage`, `decision`) to `aria-invalid` /
`aria-describedby` and focuses the first, other `422`s (gate, decision stage) are a form-level `role=alert`; `409`/`404` → `onFailed`
(reload); `401` → `SESSION_EXPIRED` + sign-in link; `5xx` → server error text. Success focuses the detail notice; cancel restores
stored values and focuses the opener; Escape leaves a confirm step.

**Competing actions:** `AgentApplicationDetail`'s `enrolling` becomes `openForm: "enrollment" | "visa" | null`; the status form is
hidden while either is open, Enrollment while Visa is open and vice versa. `AgentApplicationEnrollment`'s props are unchanged.
Works at 320 px without horizontal scroll. No new dependencies.

## 6. Security

- Authentication: unchanged (`get_current_user`); `401` anonymous.
- Authorization: `_gate` (agent role, overseas division, approved org) → `403` for other roles, including super admin as on the other
  AGN-008 routes; resource scope through `load_scoped` (`application_scope`): Master = the organisation, Staff = assigned students;
  out of scope `404` (no existence leak).
- Refused requests write nothing (checks precede every write; one commit).
- `extra="forbid"` bodies; enum-typed stage, decision and checklist values; dates range-checked.
- Visa documents keep AGN-009's rules (upload, download, verify); this feature only reads their verification status.
- Wording records the authority's decision; the disclaimer is shown with every decision (VISA-003 compliance).

## 7. Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | A decision is accepted only when the case is already at `decision`; otherwise `422`, nothing written. |
| AC2 | `interview_date` before `visa_application_date` → `422` on `interview_date`; same day accepted; either alone accepted. |
| AC3 | Moving past `checklist` with any checklist item whose latest attached document is not `verified` → `422` naming the items; once all are verified the move succeeds. |
| AC4 | A new case starts at `checklist` regardless of input; stage moves are forward-only; skips allowed; backward/same → `422`. |
| AC5 | A recorded decision is final: every later PATCH → `409`. |
| AC6 | Start requires the application at `offer`, `visa_documentation` or `status_tracking` (`422`) and no existing case (`409`). |
| AC7 | Withdrawn or enrolled application, or archived student → `409`; stale `expected_status` / `expected_stage` → `409`. |
| AC8 | Master: whole organisation; Staff: assigned students only; other org / unassigned → `404`; non-agent → `403`; anonymous → `401`. |
| AC9 | Concurrent starts create exactly one case; concurrent advances from the same stage → one `200`, one `409`. |
| AC10 | Existing visa routes and responses, the application list, status and enrollment routes behave exactly as before. |
| AC11 | The UI shows each §5 state, maps errors to fields, keeps focus correct, hides competing forms, and fits 320 px. |

## 8. Tests (written before the code)

- **Backend:** `test_agn_012_schemas.py`, `test_agn_012_migration.py` (+ relax `test_agn_013_migration.py`), `test_agn_012_visa.py`
  (AC1–AC7, legacy case, no-op PATCH, audit hygiene), `test_agn_012_security.py` (AC8, refusals write nothing),
  `test_agn_012_concurrency.py` (AC9), `test_agn_012_unchanged.py` (AC10: counselor/admin POST/PATCH and student
  checklist/status keys on a case with the new columns set; list response keys), rows in `test_agn_003_matrix.py`,
  `test_agn_021_activity.py` for the new actions. Builders: `agn008_helpers`, `agn009_helpers`.
- **Frontend (vitest):** `AgentApplicationVisa.test.tsx` (AC11), helper tests in `tests/lib/agentApplications.test.ts`, `detail()`
  fixtures in `AgentApplicationDetail.test.tsx` and `AgentApplicationEnrollment.test.tsx` gain `visa: null`.
- **E2E (Playwright):** `agn-012-visa.spec.ts`: start from an offer, gate blocks, verify the document, advance, interview-before-
  application error, move to decision, record approved, read-only; Staff on an assigned student; 320 px.

## 9. Regression risks

| Risk | Guard |
|---|---|
| `visa_cases` readers (portal student/counselor/admin, RPT-002 aging, school dashboard/timeline/analytics/global education) | Columns are nullable and additive; `test_visa_001/002/003`, `test_sch_010`, `test_rpt_002`, `test_cns_001`, `test_enh_016_*`, `test_enh_017_*`, `test_sch_reports`, `test_agn_008_null_owner` |
| Tier gating on `/overseas/visa` | Routes untouched; `test_enh_022_tier_enforcement`, `test_enh_023_tier_change` |
| Migration chain / head pin | 0061 single head; relaxed 0060 pin; collision with AGN-010's 0060 resolved at merge |
| `AgentApplicationDetail` competing-form logic | AGN-008/013 component tests unchanged and passing; new hiding tests |
| `AgentApplicationDetail` type change | fixtures updated in the same task |
| Agency status/enrollment routes | `test_agn_008_*`, `test_agn_013_*` unchanged |
