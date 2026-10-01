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
| D7 | **One open record per student per school per support type** (amended by D12), enforced by a partial unique index; `completed`/`closed` records do not block a new one. |
| D8 | **Entitlement usage:** `loan_assistance` = distinct students with any loan / financial-assistance / funding-guidance record *created at that school* (`record.school_id`, D12); `scholarship_assistance` = the same for scholarship records. Closed records count (the service was delivered). |
| D9 | **Downstream = usage only.** The ENH-016 scorecard "Scholarship" row, `UNTRACKED_OUTCOMES["scholarships"]` and the ENH-017 "Scholarships" item stay *not tracked*: they describe §18 university Scholarship Management, which ENH-020 does not implement. ENH-016 utilization percentages change automatically through `service_usage` (intended). |
| D10 | **Final records are read-only** (any PATCH to a `completed`/`closed` record → 422). |
| D11 | Counsellor UI on a **new page `/school/career-counselor/funding`** with a "Funding" nav item; read-only card on the parent child page and the coordinator/principal student detail pages. |
| D12 | **Records stay with the school that created them** (security review, user-chosen 2026-10-01). Each record stores `school_id` (the student's school at creation, read under the student row lock). Coordinator/principal/counsellor see only records whose `school_id` is the student's *current* school and in their own scope; after a transfer the new school starts clean and the previous school's records become read-only history visible to linked parents only. A record is editable only while `record.school_id == student.school_id`. Deliberately stricter than career records (which follow the student). |
| D13 | **Scope denials are audited** (security review): a 403 for role/scope on E1, E2 or E4 writes `school.funding_record_denied` (actor, role, reason code, target id — no contents) before raising, as ENH-030 does (`school_attendance.py` `DENIED_ACTION`). Tier denials keep the helper's own `school.tier_access_denied` row. |

**Out of scope:** lender/bank integration, money movement, document files, §18 Scholarship Management, school-student
login, ENH-013 360 tab, ENH-015 report rows, bulk entry, admin (Overseas) views of these records.

## 3. Data model

### 3.1 Table `school_funding_records` (migration `0051_school_funding_records`, revises `0050_notification_channels`)

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID PK | no | `uuid4` |
| `school_student_id` | UUID FK `school_students.id` | no | indexed |
| `school_id` | UUID FK `schools.id` | no | the student's school at creation (D12); never changes |
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
- `uq_funding_record_open_student_type`: unique index on (`school_student_id`, `school_id`, `support_type`) `WHERE status NOT IN ('completed', 'closed')` (D7/D12: an open case left at a previous school never blocks the new school).
- `ix_school_funding_records_school_type`: (`school_id`, `support_type`) for the usage count (§5) and school-scoped lists.

Data classification: `provider_name`, `amount_text`, `notes`, `closure_reason` and the mere existence of a record are
**sensitive personal data** (a family's financial need). Retention follows `SchoolStudent` (no school-student deletion path
exists today — a pre-existing gap, not widened here; recorded in RAID, not solved by ENH-020).

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

- `FundingRecordCreate`: `school_student_id: UUID` (Pydantic-parsed, so a malformed id is a 422, never the 500 that
  `UUID(str(...))` gives), `support_type: FundingSupportType`, `provider_name` (≤200), `amount_text` (≤120), `notes`
  (≤4000). `status`, `school_id`, owner and date fields are **not** fields: every record starts at `required`.
- `FundingRecordUpdate`: `status: FundingStatus | None`, `closure_reason` (≤500), `provider_name`, `amount_text`,
  `notes`, `expected_status: FundingStatus | None` (precondition). `support_type`, `school_id`, ids and owners are not fields.

Text rules: `provider_name`, `amount_text`, `closure_reason` are single-line (`_clean_text`: trimmed, blank → `None`,
length-capped, control characters/NUL refused); `notes` is multi-line, trimmed, NUL refused, ≤4000 (a cap the
unbounded career `notes` lacks; new endpoint, so no compatibility cost). Validation errors use the house string-422 via
`_master_fields_or_422` (`{"detail": "<field> …"}`).

## 4. API (`apps/api/app/api/school_funding.py`, `APIRouter(prefix="/school", tags=["school-funding"])`)

Registered in `main.py` after `school_attendance.router`. No existing route, request or response shape changes, except
`/school/entitlements` `used` for the two keys (null → integer).

| # | Method + path | Roles | Scope |
|---|---|---|---|
| E1 | `POST /school/funding-records` (201) | `career_counselor` | student in portfolio, checked under the student row lock |
| E2 | `PATCH /school/funding-records/{record_id}` (200) | `career_counselor` | portfolio, re-checked under the student row lock; `record.school_id == student.school_id` (D12) |
| E3 | `GET /school/career-counselor/funding-records` (200) | `career_counselor` | records whose `school_id` is in the portfolio **and** equals the student's current school; open records first, then `updated_at DESC` |
| E4 | `GET /school/students/{student_id}/funding-records` (200) | `career_counselor` (portfolio), `school_coordinator`/`school_principal` (own school), `school_parent` (linked) | `school_teacher` → explicit 403 *before* `_load_student_for_reader` (which would otherwise admit an assigned teacher); any other role → 403. Staff see only records with `school_id == student.school_id`; a parent sees all of the child's records (D12) |

Reads are **not** tier-gated (as career records), so history survives a downgrade. Roles are an allowlist per endpoint
(deny by default).

**Contract conventions** (house rules, `API_CONTRACT.md` §0, over generic advice): snake_case fields; errors are FastAPI's
`{"detail": "<plain sentence>"}` as every route returns; every endpoint returns the **same record shape** from one
serializer (lists are bare JSON arrays, as `GET /school/career-records`). **Not paginated** (§0.1 exception, stated
reason): E4 is one student's handful of cases; E3 is bounded by the counsellor's portfolio, exactly like
`GET /school/career-counselor/records` — revisit together with that endpoint if portfolio sizes grow. **No
`Idempotency-Key`** (§0.2): nothing financial moves, and create is naturally retry-safe — a retried POST after a lost
response hits the open-record index and returns 409, never a duplicate; PATCH is retry-safe by `expected_status` and
the no-op rule.

Response record: `id, school_student_id, support_type, status, status_changed_on, provider_name, amount_text, notes,
closure_reason, created_at, updated_at, counselor_name, updated_by_name` (names via `_user_names`, one query). No
`school_id` and no student master data are exposed (not needed by any screen).

### 4.1 E1 create — order (one transaction, then notify)

1. role ≠ `career_counselor` → 403 (denial audited, D13).
2. Validate body (`FundingRecordCreate`) → 422.
3. `SELECT … FOR UPDATE` the student (`populate_existing`) → 404; school not in portfolio → 403 `OUTSIDE_PORTFOLIO`
   (audited, D13). Locking here (career create does not) closes the transfer race: `school_id` is copied from a row a
   transfer approval cannot change until this transaction ends.
4. `require_school_entitlement(db, user, student.school_id, FUNDING_SERVICE_KEYS[support_type])` → 403 (audited by the helper; nothing else pending).
5. Insert with `school_id=student.school_id`, `status="required"`, `status_changed_on=_today_ist()`; `flush`.
   `IntegrityError` whose constraint is `uq_funding_record_open_student_type` → `rollback`, **409** "{student} already has
   an open {type} case. Open it from the list to update it." Any other `IntegrityError` re-raises (a real bug, not a 409).
6. `AuditLog` `school.funding_record_create` (`entity_type="school_funding_record"`), metadata `{support_type, fields: [names set]}` — never contents.
7. `commit`; read the response.
8. Notify parents (`_notify_student_parents`) in a `try`; on failure `rollback` and log `funding_record_notify_failed`; the record stands.

### 4.2 E2 update — order (as ENH-026 `update_career_record`)

1. role check → 403 (audited, D13).
2. `SELECT … FOR UPDATE` the record (`populate_existing`) → 404.
3. `SELECT … FOR UPDATE` its student; not in portfolio → 403 (`OUTSIDE_PORTFOLIO`, audited); `record.school_id !=
   student.school_id` (the student has transferred) → 403 "This case belongs to the student's previous school and can
   no longer be changed." (audited). Lock order record → student, the same as ENH-026, so the two never deadlock.
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

- Duplicate create race → the partial unique index decides; the loser gets 409 (§4.1 step 5). (Two creates for one
  student also serialize on the student row lock; the index remains the guarantee.)
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
| 403 | wrong role; outside portfolio; other school; unlinked parent; teacher; tier denial; editing a previous school's case |
| 404 | record or student not found (ids are UUIDv4, so 404-vs-403 reveals nothing guessable; matches §0.3 and ENH-026) |
| 409 | stale `expected_status`; open record of that type already exists |
| 422 | body validation; disallowed transition; missing closure reason; closure reason on a non-closed record; PATCH of a final record |

## 5. Entitlement usage (`schools.py:service_usage`)

Two `_per_school` lines, distinct students per **creating** school (`school_funding_records.school_id`, D12 — the
school whose tier delivered the service; no join to the student's current school):

- `loan_assistance`: `select(school_id, count(distinct school_student_id)) … where school_id IN (...) and support_type IN ('education_loan','financial_assistance','funding_guidance') group by school_id`.
- `scholarship_assistance`: same, `support_type = 'scholarship'`.

Served by `ix_school_funding_records_school_type`; two grouped queries regardless of school count (the `service_usage`
contract).

Effects: `/school/entitlements` shows numbers; ENH-016 `utilization()` moves these two services from *not tracked* to
delivered/pending for Gold/Platinum schools. Nothing else in ENH-016/017 changes (D9). Seed comment `seed.py:764-770`
updated; demo records added for the demo Platinum school so the screens show real numbers.

## 6. Frontend (`apps/web`)

| Unit | Purpose | States |
|---|---|---|
| `lib/fundingRecords.ts` | `FundingRecord` type, `SUPPORT_TYPE_LABEL`, `STATUS_LABEL`, `nextStatuses(status)` mirroring `FUNDING_STATUS_NEXT`, `isFinal`, `stageText(status)` ("Stage 3 of 6 · Documents"; Closed/Completed spelled out) | — |
| `components/FundingRecordForm.tsx` | create (student via the existing `SearchableSelect`, type, provider, amount, notes) / edit (status select offering only "keep current" + `nextStatuses`, closure reason shown and **required** only when Closed is chosen, provider, amount, notes). Raw `fetch` (as `CareerRecordForm`) so 409 offers **Reload** (`router.refresh()`); edit always sends `expected_status` | busy: Save disabled, `aria-busy`, label "Saving…", `inFlight` ref against double submit; success "Case saved." in `FormMessage`; 5xx "Something went wrong on our side. Please try again; your entry is kept."; network `NOT_COMPLETED`; 4xx `detailMessage` (tier 403 and duplicate-open 409 texts are written for people) |
| `components/SchoolFundingRecordsPanel.tsx` | **Open cases** table (Student, Type, Stage, Since, Provider, Edit) first — the actionable work; **Finished cases** (Completed/Closed) below in a native `<details>` with its count in the summary, read-only. Inline edit (focus to the edit heading via `refocus`, Escape closes, focus returns to the row's Edit button) + "Add a case" card | empty: "No funding support cases yet. Add one below when a student needs a loan, scholarship or funding guidance."; no portfolio: the existing "No students in your portfolio yet. Contact your Overseas Admin." |
| `app/school/career-counselor/funding/page.tsx` + `loading.tsx` | server page: `auth/me`, E3, `portfolio-students` in one `Promise.all` | loading: `skeleton-line` rows inside `PortalShell` (copy of the dashboard `loading.tsx`, so the shell never flashes); failure → `accessUnavailable(e)` |
| `components/FundingRecordsCard.tsx` | read-only card, one `<dl className="record-details">` per case (Type, Stage + since, Provider, Amount, Notes, Closure reason, Updated by). Rendered from data the host page fetches **in its existing `Promise.all`** (no extra waterfall) | error (`null` from `.catch`): "Funding support cases couldn't be loaded. Reload the page to try again." — the rest of the page still renders; empty: "No funding support cases for this student." |
| `lib/navigation.ts` | `SCHOOL_NAV["career-counselor"]` gains `"funding"` (label "Funding") | — |
| pages | card added to `school/parent/children/[id]/page.tsx`, `school/coordinator/students/[id]/page.tsx`, `school/principal/students/[id]/page.tsx` | — |
| `globals.css` | add `.table.funding-records` to the existing phone card-row rule (`.table.psy-records`, QA27-05) and its 44px touch-target rule — selectors only, no new visual language | — |

**Design language.** Reuse only: `PortalShell`, `card`/`card-stack`/`action-card`, `table-wrap`/`table`, `status`
pills, `record-details`, `btn secondary small`, `FormMessage`, `SearchableSelect`, `refocus`, `detailMessage`,
`accessUnavailable`, `skeleton-line`. No new component library, icon set, colour or dependency. Components stay under
~200 lines (form, panel and card are separate files).

**Hierarchy.** Page heading "Funding support" (h2 inside the shell, as sibling pages) → "Open cases" (h3) → "Finished
cases" (`<summary>`) → "Add a case" (h3). Stage is shown as text ("Stage 3 of 6 · Documents"), never colour alone; the
pill class only reinforces it (open stages `status pending`, Approved/Completed `status`, Closed plain `status` with
the word "Closed").

**Responsive.** At ≤640px the open-cases table becomes stacked cards using each cell's `data-label` (the psychometric
pattern: no sideways scroll, the Edit button stays with its student); `record-details` collapses to one column (existing
rule); buttons are 44px tall on phones; the form uses the existing `form-grid` (one column on phones).

**Forms and keyboard.** Every control has a visible `<label>`; required fields say so in text; `maxLength` mirrors the
server caps (200/120/500/4000); helper text is tied with `aria-describedby`; choosing Closed reveals the reason field and
moves focus to it; Escape cancels an edit; Enter submits; nothing is hover-only. The status select never offers a move
the server would refuse; the server still decides.

**Accessibility.** Table headers with `scope`, unique accessible names on Edit buttons (type + opened date + student,
the QA-15 pattern), `FormMessage` as a polite live region, `aria-busy` on loading regions, focus management as
ENH-026. axe check in the Playwright spec.

**Perceived performance.** Server-rendered lists (no client fetch spinner on first paint); the read-only card joins the
host page's parallel fetch; after a save `router.refresh()` re-reads the server list. No optimistic update: stage
changes are guarded server-side (409/422), so showing a stage before the server accepts it would mislead.

**XSS.** All text renders through React's escaping; `notes` uses `white-space: pre-wrap`; no `dangerouslySetInnerHTML`.

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC01 | A counsellor creates a record for a portfolio student in a tier that includes the type's service → 201, `status=required`, `status_changed_on=today (IST)`, audit row without contents, linked parents notified. |
| AC02 | Create for a non-portfolio student → 403; unknown student → 404; non-counsellor role → 403. |
| AC03 | Gold school: `scholarship` create → 201; `education_loan` / `financial_assistance` / `funding_guidance` → 403 (`school.tier_access_denied` audited). Platinum: all four → 201. No/expired tier → 403. |
| AC04 | A second open record with the same student + school + type → 409; after the first is `completed` or `closed`, a new one → 201. Two simultaneous creates → exactly one 201 and one 409. A malformed `school_student_id` → 422, never 500. |
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
| AC17 | Transfer (D12): after an approved transfer, the new school's coordinator/principal/counsellor see none of the previous school's cases (E3, E4); a PATCH to a previous-school case → 403; the new school can open a case of the same type → 201; the linked parent still sees every case; usage stays with the creating school. |
| AC18 | Denials (D13): each role/scope 403 on E1, E2, E4 writes one `school.funding_record_denied` audit row (actor, role, reason, target id) and no record row; tier denials write `school.tier_access_denied`. |
| AC19 | No record contents (provider, amount, notes, closure reason) appear in any audit row, application log line or notification. |
| AC20 | UI at 320px and 768px: no horizontal page scroll; open cases render as stacked cards; buttons ≥44px tall; axe reports no violations on the funding page and on a page with the read-only card. |

## 8. Testing (written before the code they cover)

- **Schema unit** `test_enh_020_schemas.py`: transition table (every pair), final statuses, `extra="forbid"`, text trimming/limits, NUL refusal.
- **Migration** `test_enh_020_migration.py`: table, three check constraints, partial unique index present; existing-table guard; downgrade (pattern `test_enh_026_migration.py`).
- **API** `test_enh_020_funding_records.py`: AC01–AC10, AC12 (including the notify-failure path and audit metadata), concurrent create (AC04), AC19 (log capture).
- **Authorization** `test_enh_020_rbac.py`: AC02, AC11 role × scope matrix (every role × own/other school × linked/unlinked), AC17 transfer, AC18 denial audit; abuse cases first: teacher reading an assigned student, parent reading a sibling's unlinked classmate, counsellor PATCHing another portfolio's record id, owner/`school_id` injection in bodies.
- **Usage** `test_enh_020_usage.py`: AC13, AC14.
- **Existing tests intentionally updated** (behaviour change approved in D8, not to make a draft pass):
  `test_sch_011_entitlements.py:138-139` (drop `loan_assistance`, `scholarship_assistance` from the untracked loop; assert counts),
  `test_enh_016_contracts.py:70-73,94` (usage map), any ENH-016 utilization expectations that counted those keys as not tracked.
- **Frontend unit (vitest)**: `tests/lib/fundingRecords.test.ts` (`nextStatuses`, labels), `tests/components/FundingRecordForm.test.tsx` (closure field toggle, busy state, 409 Reload, 5xx text).
- **Frontend unit** also covers `SchoolFundingRecordsPanel` (open/finished split, empty and no-portfolio states, no Edit on final) and `FundingRecordsCard` (error and empty text).
- **Playwright** `tests/e2e/enh-020-funding-support.spec.ts`: AC16, AC20 (320px/768px viewports, axe), parent read-only, teacher denied.
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
| Shared phone-table CSS rule edited | Selector added only; `psy-records` e2e/visual behaviour re-checked in the regression gate (`enh-027-psychometric-results`). |
| Student row lock on create contends with transfer approval | Same lock ENH-026 PATCH and transfers already take; held only for one short transaction, released before notification. |

## 10. Documentation updates

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-043`, D1–D13), `ENHANCEMENT_BACKLOG.md` (row 132, §21 audit row 943,
§ENH-020 entry, §3 decision table), `DATA_MODEL.md` §6.24, `API_CONTRACT.md` §12A (E1–E4), `RBAC_MATRIX.md` §2.12,
`SCREEN_CATALOG.md` + `screen_catalog.json` (SCR-SCH-040 counsellor funding page, SCR-SCH-041 read-only card),
`ROLE_NAVIGATION.md`, `docs/quality/RTM.md`.

## 11. Review passes (2026-10-01, before planning)

Three passes over this design, at the user's request. House conventions win where a skill's generic advice conflicts.

### 11.1 API and interface design

| Check | Result |
|---|---|
| Contract first | E1–E4 shapes fixed in §4; one serializer; request models `extra="forbid"`. |
| Error semantics | `{"detail": str}` everywhere (house reality, `API_CONTRACT.md` ENH-006 row); 401/403/404/409/422 mapping in §4.5; no 400s; 5xx never carries internals. |
| Validation at the boundary | Pydantic models only; malformed UUID → 422 (avoids the 500 that `UUID(str(x))` gives). Internal code trusts parsed values. |
| HTTP semantics | POST 201 + full record; PATCH 200 partial, presence-aware; GET 200 arrays; no verbs in paths; no DELETE (cases are closed, not erased — audit trail). |
| Pagination | Explicit §0.1 exception with reason (§4). |
| Idempotency | No key (§0.2); natural retry safety documented (§4). |
| Backward compatibility | Purely additive routes, table and migration; the only observable change to an existing response is `used` null → integer for two keys (D8), with the tests that pinned the old value updated on purpose. |
| Transactions | One transaction per write; tier gate before any `db.add`; notify after commit; only the named unique violation maps to 409. |
| Database usage | Two grouped usage queries; composite and partial indexes; no N+1 (names in one `_user_names` query). |

### 11.2 Security and hardening (STRIDE over the four endpoints)

Trust boundary: the browser → `/api/v1/school/*` (JSON bodies, path ids). Asset: a family's financial-need information.

| Area | Finding / control |
|---|---|
| Authentication | `get_current_user` (HttpOnly `edusphere_access` cookie, active-user check) on every endpoint; no new auth flow. |
| Authorization | Per-endpoint role allowlists; explicit teacher deny; portfolio / own-school / linked-parent scoping; D12 creating-school scoping. |
| IDOR | Record ids resolve to their student and school, then scope is checked (E2); readers never fetch by record id; E4 checks the student via the shared loader. |
| Role escalation | Owner, `school_id`, `status` (create), `support_type` (update) not writable; author comes from the session; parents have no write route. |
| Input validation | Literal enums, length caps, control/bidi-override characters refused in single-line fields, NUL refused in notes (§3.3). |
| XSS | React escaping only; notifications carry only fixed labels and the student name (§4.4, §6). |
| CSRF | Unchanged and sufficient: `SameSite=Lax` HttpOnly cookie (`auth.py:90`), CORS limited to `settings.frontend_url` (`main.py:60`), JSON bodies need a preflight a foreign origin fails. No new control. |
| SQL injection | SQLAlchemy ORM with bound parameters only; no `text()` with input. |
| Tokens / sessions | No change. |
| Secret exposure | None introduced. |
| Sensitive logs | Logs and audit rows carry ids, role, status and field **names** only (AC19); no request bodies in exception logs. |
| Rate limiting | None added (consistent with career records): writes are authenticated staff-only actions, open cases are capped by the unique index, bodies are size-capped. Accepted; revisit if abuse appears. |
| Audit | Create/update audited; scope denials audited (D13); tier denials audited by the existing helper. Reads are not audited (as every School read). |
| Privacy | Fields classified sensitive (§3.1); minimal fields (D4); content-free notifications (§4.4); retention gap pre-existing (RAID). |

### 11.3 Frontend UI engineering

Reuse-first (§6 "Design language"); hierarchy (open cases first, finished collapsed); responsive (stacked cards at
≤640px, 44px targets); accessibility (labels, live region, focus management, unique button names, axe); loading
(`PortalShell` skeleton), empty (names the next action), error (soft-fail card, kept form input, 409 Reload); keyboard
(Escape, Enter, focus to closure reason); perceived performance (server render, parallel fetch, no misleading optimistic
stage). Pinned by AC16 and AC20.

### 11.4 Deliberately not changed

Existing career-record behaviour (its missing `notes` cap and follow-the-student visibility), global rate limiting,
CSP/headers, the CSRF model, other modules' "not tracked" outputs, and the school-student retention gap — each is
outside ENH-020.
