# ENH-020 — Financial Support / Loan Assistance Tracking: Design

**Status:** Draft for review, 2026-10-01. Branch `feature/enh-020-funding-tracker` (from `main` @ `18886bf`).
**Feature ID:** ENH-020. **Decision:** proposed `DEC-SCOPE-043` (provisional number; §2), recorded in the register only once
this spec is approved.
**Source:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-020 (`DERIVED_BLUEPRINT`), from `School CRM.md` §21
(`ORIGINAL_REQUIREMENT`, `EVID-014`). The working copy `functionalities/edusphere_markdown/School CRM.md` matches the
`SOURCE_MANIFEST.csv` SHA-256 (`60977c8b…`) after CRLF→LF normalisation; `docs/sources/` is empty in this worktree.
**Existing authority:** `DEC-SCOPE-017` (CONFIRMED_CURRENT 2026-09-15) lists `loan_assistance` (Platinum) and
`scholarship_assistance` (Gold) as included tier services reported `used: null` because no module exists.

## 1. Problem and audit result (2026-10-01, Graphify-led, verified against the files)

§21 asks to "track students requiring education loan, financial assistance, scholarship, funding guidance" with status
**Required → Counselling → Documents → Application → Approved → Completed**. The backlog made the design conditional on
an audit: is this already in the Overseas domain?

**Verdict: no. ENH-020 is a new tracker (backlog option (b)), not a school-side view.**

| Fact | Evidence |
|---|---|
| No loan, financial-assistance or funding-guidance model, route, status or UI exists anywhere in `apps/` | grep over `apps/` (excluding `node_modules`); the only code hit is the tier label `("loan_assistance", "Loan assistance")` `schools.py:1005` |
| `apps/api/app/finance/` is a reserved, empty package | `finance/__init__.py:1` (docstring only) |
| `ScholarshipApplication` is overseas-only: `student_id` → `users.id`, `status` String(40) default `"submitted"`, no school-student link, no endpoint ever updates the status | `models.py:512-517`; `workflows.py:2266-2281` (only writer, `overseas_student`); `services/portal.py:624-640` (self-scoped read) |
| ENH-016/ENH-017 render scholarships as *not tracked* for exactly that reason | `school_analytics.py:397,487-489`; `school_global_education.py:39` |
| `EMISchedule`/`Payment` are fee instalments (`DEC-PAY-001/002`), not loans | `models.py:532-598` |
| No `DEC-*` decision covers loans, financial assistance or funding | `PRODUCT_DECISION_REGISTER.md`, `PRD_OPEN_ITEMS.md` |
| School students have no login; there is no `school_student` role | `models.py:427-434` (DEC-ROLE-004); `SCHOOL_ROLES` `schools.py:329`; `web/lib/navigation.ts:37-45` |
| `require_tier()` (named in the backlog) does not exist; the gate is `require_school_entitlement`, which commits its own denial audit row and so must run before any pending write | `schools.py:1119-1122` |
| The School domain has no service/repository layer: routes hold query, scope, tier, audit and notification logic; newer modules get their own router file so `schools.py` (2,671 lines) stops growing | `school_attendance.py:1-5`; `school_feedback.py`; `main.py:61-62` |
| Closest pattern: SCH-004/ENH-026 career records (portfolio scope, transition table, `expected_status` 409, locked PATCH, notify-after-commit) | `schools.py:2081-2210`; `schemas.py:910-990` |
| A partial unique index already has precedent | `uq_school_transfer_pending_student` `models.py:1216` |
| `service_usage` is read by `/school/entitlements` **and** ENH-016 utilization / cross-school rollup | `schools.py:1147,1231`; `school_analytics.py:525,579` |

## 2. Decisions (user, in-session, 2026-10-01 — `EXPLICIT_APPROVAL` per answer; proposed `DEC-SCOPE-043`)

| ID | Decision |
|---|---|
| D1 | **Writer = `career_counselor`**, students in their own school portfolio only (`_student_in_portfolio`, as SCH-004). |
| D2 | **Per-type tier gate.** `support_type = scholarship` → `scholarship_assistance` (Gold+); `education_loan`, `financial_assistance`, `funding_guidance` → `loan_assistance` (Platinum). `support_type` is fixed after creation. |
| D3 | **Stages = the six source stages, forward one step at a time, plus a terminal `closed`** (not approved / withdrawn) reachable from any open stage with a required reason. `completed` and `closed` are final. `closed` is an addition beyond the source wording. |
| D4 | **Lean fields:** notes, closure reason, optional provider/institution name (free text), optional amount (free text, like `Scholarship.amount`), date the current stage was entered. No document uploads, no currency arithmetic, no lender integration. |
| D5 | **Readers:** the owning portfolio's `career_counselor`; `school_coordinator`/`school_principal` (own school); linked `school_parent` (own child, read-only). **`school_teacher` is excluded** (financial-need data; tighter than career records). Parents get the existing in-app/channel notification on create and on stage change. |
| D6 | **Architecture = Approach A:** new `school_funding_records` table and `school_funding.py` router reusing `schools.py` helpers. Rejected: B (a new `SchoolCareerRecord.record_type` — different statuses, tier keys and readers would fork ENH-026's rules); C (generic case engine — abstraction ahead of need). |
| D7 | **One open record per student per support type**, enforced by a partial unique index; `completed`/`closed` records do not block a new one. |
| D8 | **Entitlement usage:** `loan_assistance` = distinct students with any loan / financial-assistance / funding-guidance record; `scholarship_assistance` = distinct students with any scholarship record. Closed records count (the service was delivered). |
| D9 | **Downstream = usage only.** The ENH-016 scorecard "Scholarship" row, `UNTRACKED_OUTCOMES["scholarships"]` and the ENH-017 "Scholarships" item stay *not tracked*: they describe §18 university Scholarship Management, which ENH-020 does not implement. ENH-016 utilization percentages change automatically through `service_usage` (intended). |
| D10 | **Final records are read-only** (any PATCH to a `completed`/`closed` record → 422). |
| D11 | Counsellor UI on a **new page `/school/career-counselor/funding`** with a "Funding" nav item; read-only card on the parent child page and the coordinator/principal student detail pages. |

**Out of scope:** lender/bank integration, money movement, document files, §18 Scholarship Management, school-student
login, ENH-013 360 tab, ENH-015 report rows, bulk entry, admin (Overseas) views of these records.

## 3. Data model

### 3.1 Table `school_funding_records` (migration `0051_school_funding_records`, revises `0050_notification_channels`)

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID PK | no | `uuid4` |
| `school_student_id` | UUID FK `school_students.id` | no | indexed |
| `support_type` | String(30) | no | `education_loan` \| `financial_assistance` \| `scholarship` \| `funding_guidance` |
| `status` | String(20) | no | `required` \| `counselling` \| `documents` \| `application` \| `approved` \| `completed` \| `closed` |
| `status_changed_on` | Date | no | India-calendar day (`_today_ist()`) the current status was entered |
| `provider_name` | String(200) | yes | bank / scholarship body |
| `amount_text` | String(120) | yes | free text |
| `notes` | Text | no | `""` when empty |
| `closure_reason` | String(500) | yes | |
| `career_counselor_user_id` | UUID FK `users.id` | no | creator |
| `updated_by_user_id` | UUID FK `users.id` | yes | last editor |
| `created_at`, `updated_at` | timestamptz | no | `TimestampMixin` / `server_default now()` |

Constraints (named, in model and migration):
- `ck_funding_record_support_type`: `support_type IN (...)` (the four values).
- `ck_funding_record_status`: `status IN (...)` (the seven values).
- `ck_funding_record_closure`: `(status = 'closed') = (closure_reason IS NOT NULL)`.
- `uq_funding_record_open_student_type`: unique index on (`school_student_id`, `support_type`) `WHERE status NOT IN ('completed', 'closed')`.

Migration: create-table only; skips if the table already exists (the `0048` guard); no existing table or row is read or
written; `downgrade()` drops the table (and its indexes). Data preservation: purely additive.

### 3.2 Constants (`schemas.py`, beside ENH-026)

```python
FundingSupportType = Literal["education_loan", "financial_assistance", "scholarship", "funding_guidance"]
FundingStatus = Literal["required", "counselling", "documents", "application", "approved", "completed", "closed"]
FUNDING_STATUS_NEXT: dict[str, frozenset[str]] = {
    "required": frozenset({"counselling", "closed"}), "counselling": frozenset({"documents", "closed"}),
    "documents": frozenset({"application", "closed"}), "application": frozenset({"approved", "closed"}),
    "approved": frozenset({"completed", "closed"}), "completed": frozenset(), "closed": frozenset(),
}
# allowed(current, requested) = requested == current or requested in FUNDING_STATUS_NEXT[current]
FUNDING_FINAL_STATUSES = frozenset({"completed", "closed"})
FUNDING_SERVICE_KEYS = {"scholarship": "scholarship_assistance", "education_loan": "loan_assistance",
                        "financial_assistance": "loan_assistance", "funding_guidance": "loan_assistance"}
```

Labels: Education loan / Financial assistance / Scholarship / Funding guidance; Required / Counselling / Documents /
Application / Approved / Completed / Closed. `FUNDING_SERVICE_KEYS` lives in `school_funding.py` (it names
`TIER_SERVICES` keys, like `TEST_PREP_SERVICE_KEYS`); the rest in `schemas.py`.

### 3.3 Request models (`extra="forbid"`)

- `FundingRecordCreate`: `school_student_id: UUID`, `support_type: FundingSupportType`, `provider_name`, `amount_text`
  (stripped, `None` when blank, max length, NUL refused), `notes` (as `_career_notes`). `status` is **not** a field:
  every record starts at `required`.
- `FundingRecordUpdate`: `status: FundingStatus | None`, `closure_reason`, `provider_name`, `amount_text`, `notes`,
  `expected_status: FundingStatus | None` (precondition). `support_type`, ids and owners are not fields.

Validation errors use the house string-422 via `_master_fields_or_422`.

## 4. API (`apps/api/app/api/school_funding.py`, `APIRouter(prefix="/school", tags=["school-funding"])`)

Registered in `main.py` after `school_attendance.router`. No existing route, request or response shape changes, except
`/school/entitlements` `used` for the two keys (null → integer).

| # | Method + path | Roles | Scope |
|---|---|---|---|
| E1 | `POST /school/funding-records` (201) | `career_counselor` | `_student_in_portfolio` |
| E2 | `PATCH /school/funding-records/{record_id}` | `career_counselor` | portfolio, re-checked under the student row lock |
| E3 | `GET /school/career-counselor/funding-records` | `career_counselor` | portfolio students, `created_at DESC` |
| E4 | `GET /school/students/{student_id}/funding-records` | `career_counselor` (portfolio), `school_coordinator`/`school_principal` (own school), `school_parent` (linked) | `school_teacher` → explicit 403 *before* `_load_student_for_reader` (which would otherwise admit an assigned teacher); any other role → 403 |

Reads are **not** tier-gated (as career records), so history survives a downgrade.

Response record: `id, school_student_id, support_type, status, status_changed_on, provider_name, amount_text, notes,
closure_reason, created_at, updated_at, counselor_name, updated_by_name` (names via `_user_names`, one query).

### 4.1 E1 create — order (one transaction, then notify)

1. role ≠ `career_counselor` → 403.
2. Validate body (`FundingRecordCreate`) → 422.
3. `_student_in_portfolio` → 404 / 403.
4. `require_school_entitlement(db, user, student.school_id, FUNDING_SERVICE_KEYS[support_type])` → 403 (audited by the helper; nothing else pending).
5. Insert with `status="required"`, `status_changed_on=_today_ist()`; `flush`. `IntegrityError` on
   `uq_funding_record_open_student_type` → `rollback`, **409** "{student} already has an open {type} record."
6. `AuditLog` `school.funding_record_create` (`entity_type="school_funding_record"`), metadata `{support_type, fields: [names set]}` — never contents.
7. `commit`; read the response.
8. Notify parents (`_notify_student_parents`) in a `try`; on failure `rollback` and log `funding_record_notify_failed`; the record stands.

### 4.2 E2 update — order (as ENH-026 `update_career_record`)

1. role check → 403.
2. `SELECT … FOR UPDATE` the record (`populate_existing`) → 404.
3. `SELECT … FOR UPDATE` its student; not in portfolio → 403 (`OUTSIDE_PORTFOLIO`).
4. `require_school_entitlement(…, FUNDING_SERVICE_KEYS[record.support_type], grandfathered_since=record.created_at)`.
5. Validate body (`FundingRecordUpdate`) → 422.
6. `expected_status` sent and ≠ `record.status` → **409** "This record was changed by someone else (now {label}). Reload to see the latest."
7. Record final (D10) → 422 "This record is {label} and can no longer be changed."
8. `status` sent and ≠ current: not in `FUNDING_STATUS_NEXT[current]` → 422 "Cannot change status from {a} to {b}."
   Entering `closed` without a non-blank `closure_reason` → 422 "Give a reason for closing this record."
   `closure_reason` sent while the resulting status ≠ `closed` → 422. On a status change set `status_changed_on=_today_ist()`.
9. No tracked field changed → return the record, write nothing (repeat-safe).
10. `updated_by_user_id`; `AuditLog` `school.funding_record_update` with `changed_fields` (names only) and `status {old,new}`.
11. `commit`; build the response.
12. Status changed → notify parents (try / rollback / log, as 4.1 step 8).

### 4.3 Concurrency and transactions

- Duplicate create race → the partial unique index decides; the loser gets 409 (§4.1 step 5).
- Concurrent PATCHes → serialized by the record row lock; the second sees the new status and gets 409 if it sent `expected_status`, else the transition rule applies to the *current* status.
- Transfer race → the student row lock (the lock transfer approval takes) plus the portfolio re-check under it.
- No row lock is held across notification delivery (notify after commit).
- A tier denial commits only its own audit row: it runs before any `db.add`.

### 4.4 Parent notification text

Title "Funding support update for {student}"; body "{Type label} is now at {Status label}." (create: "… is now being
tracked (Required)."). `action_url=/school/parent/children/{id}`. **Never** includes amount, provider, notes or closure
reason (notifications may leave the app via ENH-014 channels).

### 4.5 Error matrix

| Code | When |
|---|---|
| 401 | not authenticated (`get_current_user`) |
| 403 | wrong role; outside portfolio; other school; unlinked parent; teacher; tier denial |
| 404 | record or student not found |
| 409 | stale `expected_status`; open record of that type already exists |
| 422 | body validation; disallowed transition; missing closure reason; closure reason on a non-closed record; PATCH of a final record |

## 5. Entitlement usage (`schools.py:service_usage`)

Two `_per_school` lines, distinct students per school:

- `loan_assistance`: `count(distinct school_funding_records.school_student_id)` where `support_type IN ('education_loan','financial_assistance','funding_guidance')`.
- `scholarship_assistance`: same, `support_type = 'scholarship'`.

Effects: `/school/entitlements` shows numbers; ENH-016 `utilization()` moves these two services from *not tracked* to
delivered/pending for Gold/Platinum schools. Nothing else in ENH-016/017 changes (D9). Seed comment `seed.py:764-770`
updated; demo records added for the demo Platinum school so the screens show real numbers.

## 6. Frontend (`apps/web`)

| Unit | Purpose | States |
|---|---|---|
| `lib/fundingRecords.ts` | `FundingRecord` type, `SUPPORT_TYPE_LABEL`, `STATUS_LABEL`, `nextStatuses(status)` mirroring `FUNDING_STATUS_NEXT`, `isFinal` | — |
| `components/FundingRecordForm.tsx` | create (student, type, provider, amount, notes) / edit (status select offering only `nextStatuses`, closure reason shown only for `closed`, provider, amount, notes). Raw `fetch` (as `CareerRecordForm`) so 409 offers **Reload** (`router.refresh()`) | busy: Save disabled + `inFlight` ref; success message; 5xx "Something went wrong on our side…, your entry is kept"; network `NOT_COMPLETED`; 4xx `detailMessage` (incl. tier 403 text) |
| `components/SchoolFundingRecordsPanel.tsx` | counsellor table (Student, Type, Status, Since, Provider, Notes, Edit) + inline edit (focus via `refocus`, Escape closes) + Add card. Final records show no Edit button | empty: "No funding support tracked yet."; no portfolio: "No students in your portfolio yet. Contact your Overseas Admin." |
| `app/school/career-counselor/funding/page.tsx` + `loading.tsx` | server page: `auth/me`, E3, `portfolio-students` | failure → `accessUnavailable(e)` |
| `components/FundingRecordsCard.tsx` | read-only list for one student (Type, Status + since, Provider, Amount, Notes, Closure reason) | loads E4 itself with `.catch(() => null)`: error → "Funding support records couldn't be loaded." without breaking the page; empty → "No funding support tracked for this student." |
| `lib/navigation.ts` | `SCHOOL_NAV["career-counselor"]` gains `"funding"` | — |
| pages | card added to `school/parent/children/[id]/page.tsx`, `school/coordinator/students/[id]/page.tsx`, `school/principal/students/[id]/page.tsx` | — |

Accessibility: table headers, unique accessible names on Edit buttons (type + date + student), labelled controls,
`FormMessage` live region, focus return on close — the ENH-026 patterns.

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC01 | A counsellor creates a record for a portfolio student in a tier that includes the type's service → 201, `status=required`, `status_changed_on=today (IST)`, audit row without contents, linked parents notified. |
| AC02 | Create for a non-portfolio student → 403; unknown student → 404; non-counsellor role → 403. |
| AC03 | Gold school: `scholarship` create → 201; `education_loan` / `financial_assistance` / `funding_guidance` → 403 (`school.tier_access_denied` audited). Platinum: all four → 201. No/expired tier → 403. |
| AC04 | A second open record with the same student + type → 409; after the first is `completed` or `closed`, a new one → 201. Two simultaneous creates → exactly one 201 and one 409. |
| AC05 | PATCH advances exactly one forward step or to `closed`; skipping, going backward or any other status → 422; current status repeated → 200, no write. |
| AC06 | `closed` requires a non-blank `closure_reason` (422 otherwise); `closure_reason` with any other resulting status → 422. |
| AC07 | PATCH of a `completed`/`closed` record → 422, nothing written. |
| AC08 | Stale `expected_status` → 409 and nothing written. |
| AC09 | A record created before a downgrade can still be advanced after it (grandfathering); a new record of a now-excluded type → 403. |
| AC10 | `support_type`, `status` (on create), ids or owner fields in a body → 422 (`extra="forbid"`). |
| AC11 | E4: coordinator/principal see own-school students only (other school → 403); parent sees linked child only (unlinked → 403); teacher → 403 even for an assigned student; counsellor portfolio only. |
| AC12 | Parents are notified on create and on each status change, never on a notes/provider/amount-only edit; notification text contains no amount, provider, notes or closure reason. A notification failure leaves the record saved and returns success. |
| AC13 | `/school/entitlements` reports `used` for `loan_assistance` and `scholarship_assistance` as distinct-student counts (0 when none); every other key's value is unchanged. |
| AC14 | ENH-016 scorecard "Scholarship" row, `UNTRACKED_OUTCOMES["scholarships"]` and ENH-017 `not_tracked` list are unchanged. |
| AC15 | Migration upgrades from `0050`, creates the table/constraints/partial index, touches no existing table, and downgrades cleanly. |
| AC16 | UI: counsellor can create, advance and close a record by keyboard; the status select offers only allowed next stages; a 409 shows a Reload action; loading, empty and error states render as in §6; parent and coordinator/principal see the read-only card; final records show no Edit. |

## 8. Testing (written before the code they cover)

- **Schema unit** `test_enh_020_schemas.py`: transition table (every pair), final statuses, `extra="forbid"`, text trimming/limits, NUL refusal.
- **Migration** `test_enh_020_migration.py`: table, three check constraints, partial unique index present; existing-table guard; downgrade (pattern `test_enh_026_migration.py`).
- **API** `test_enh_020_funding_records.py`: AC01–AC10, AC12 (including the notify-failure path and audit metadata), concurrent create (AC04).
- **Authorization** `test_enh_020_rbac.py`: AC02, AC11 role × scope matrix.
- **Usage** `test_enh_020_usage.py`: AC13, AC14.
- **Existing tests intentionally updated** (behaviour change approved in D8, not to make a draft pass):
  `test_sch_011_entitlements.py:138-139` (drop `loan_assistance`, `scholarship_assistance` from the untracked loop; assert counts),
  `test_enh_016_contracts.py:70-73,94` (usage map), any ENH-016 utilization expectations that counted those keys as not tracked.
- **Frontend unit (vitest)**: `tests/lib/fundingRecords.test.ts` (`nextStatuses`, labels), `tests/components/FundingRecordForm.test.tsx` (closure field toggle, busy state, 409 Reload, 5xx text).
- **Playwright** `tests/e2e/enh-020-funding-support.spec.ts`: AC16 + parent read-only + teacher denied.
- **Regression gate:** full API suite and the e2e specs `sch-011-entitlements`, `enh-016-analytics`, `enh-017-global-education`, `enh-022-tier-enforcement`, `enh-023-tier-change`, `enh-026-counselling-record`, `sch-007-parent-portal`, `sch-004-005-006-service-delivery`.

## 9. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| Entitlement / ENH-016 utilization numbers shift | Intended (D8/D9); assertions updated explicitly; AC13/AC14 pin the boundary. |
| Tier gate called after a pending write commits half a request | Gate at step 4 before any `db.add`; test asserts no record row after a 403. |
| Downgrade strands in-flight records | `grandfathered_since=record.created_at` (AC09). |
| Financial-need data leaks (teacher, other school, unlinked parent, notification channels) | Explicit teacher 403, loader scoping, contents-free audit and notifications (AC11, AC12). |
| Duplicate scholarship tracking with `ScholarshipApplication` | D9: §18 stays untouched and *not tracked*; the decision records that ENH-020 scholarship records are guidance cases, not university applications. |
| `schools.py` circular import | Import helpers from `schools.py` at module top (as `school_attendance.py`); `service_usage` imports `SchoolFundingRecord` from `models.py` only. |
| Migration number collision with parallel branches | Renumber on merge, as ENH-030 did (`0048`). |

## 10. Documentation updates

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-043`, D1–D11), `ENHANCEMENT_BACKLOG.md` (row 132, §21 audit row 943,
§ENH-020 entry, §3 decision table), `DATA_MODEL.md` §6.24, `API_CONTRACT.md` §12A (E1–E4), `RBAC_MATRIX.md` §2.12,
`SCREEN_CATALOG.md` + `screen_catalog.json` (SCR-SCH-040 counsellor funding page, SCR-SCH-041 read-only card),
`ROLE_NAVIGATION.md`, `docs/quality/RTM.md`.
