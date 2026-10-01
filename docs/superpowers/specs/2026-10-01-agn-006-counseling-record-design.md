# AGN-006 — Agent Student Counseling Record: Design

**Status:** approved in conversation, written for owner review (2026-10-01). **Branch:** `feature/agn-006-counseling-record` (from `origin/main` 52d0c08).
**Decision:** `DEC-SCOPE-047` (provisional number; C1–C9 below, recorded with the code). **Backlog:** `ENHANCEMENT_BACKLOG.md` §AGN-006 (added with the code).
**Builds on:** `AGN-001` (`DEC-SCOPE-038`), `AGN-004` (`DEC-SCOPE-042`), `AGN-003` (`DEC-SCOPE-044`), `AGN-021` (`DEC-SCOPE-046`).
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 "Staff Student Journey", STEP 2 "Counseling". The source's
wording is not the approval; the owner's statement and answers are.
**Oriented with:** Graphify query + read-only inventory of the AGN-004 stack on `main` (2026-10-01); brainstorming (superpowers), in-session.
**Parallel work:** `AGN-007` (university shortlist, `feature/agn-007-student-shortlist`, unpushed) also wants the next migration (0054),
the next `DEC-SCOPE` number, `agent_students.py`, `AgentStudentDetailPanel.tsx` and `STAFF_ACTIVITY_ACTIONS`. Whichever merges second
renumbers its migration/decision and re-chains (precedent: 0052, 0053).

## 1. Intent

The owner's `AGN-006` statement (in-session, 2026-10-01): requirement **"record counseling completed, career interest, course preference,
country preference, budget and remarks"**; acceptance criteria: **save and read back the record; a negative budget → 422; out-of-scope → 404.**

**Owner answers (in-session 2026-10-01, `EXPLICIT_APPROVAL`; recorded as `DEC-SCOPE-047`):**
- **C1 — One record per student.** Saving overwrites it; history is the audit log only.
- **C2 — Budget.** An amount plus a currency from a fixed list: INR (default), USD, GBP, EUR, CAD, AUD, NZD; 0 ≤ amount ≤ 99,999,999.99,
  at most 2 decimals; otherwise 422.
- **C3 — Separate preferences.** Counseling course/country preference are new fields; the Step 1 `preferred_course` /
  `preferred_country` are untouched and both are shown.
- **C4 — Who and which students.** The agency Master and the assigned staff member (the AGN-004 G4 scope); students with no login
  only. A student with a login or an archived student → 409; out of scope → 404.
- **C5 — Completed.** A yes/no flag; the server stamps when and by whom on the change to yes, keeps the stamp while it stays yes, and
  clears it on no.
- **C6 — API shape.** `PUT /workflows/overseas/agent/crm/students/{id}/counseling`; read back as a `counseling` object in the student
  detail. The AGN-004 `PATCH /students/{id}` contract is not changed.
- **C7 — Staff activity.** A new audit action `agent_student.counseling`, shown in AGN-021 Staff Activity with field names only, never
  values (budget and remarks are never shown there).
- **C8 — Storage.** A separate one-to-one table (approach A, §3).
- **C9 — Leave prompt.** The counseling form warns before leaving with unsaved changes, like `AgentStudentForm`.

## 2. Out of scope

- Counseling history / multiple sessions (C1), counseling status in the student list, filters or reports on counseling fields.
- Counseling for students with their own login (C4) — their row is always `counseling: null`.
- STEP 3+ of §5 (shortlisting is `AGN-007`), and the School CRM counselling records (`SchoolCareerRecord`, ENH-021/026) — a different
  domain, not reused and not changed.
- Optimistic concurrency (ETag / version): none is contracted; last write wins, as for the AGN-004 edit.

## 3. Approaches considered

| | Approach | Verdict |
|---|---|---|
| **A** | New table `agent_student_counseling`, one row per student (`UNIQUE agent_student_id`) | **Chosen (C8).** Create-table-only migration; `agent_students`, its list query and the AGN-004 PATCH are untouched; "not recorded" = no row. One extra outer join in the detail read. |
| B | ~11 nullable columns on `agent_students` | Rejected: widens the hot table, a counseling save bumps the student's `updated_at` (changes AGN-004's meaning), higher collision risk with AGN-007. |
| C | One JSON column | Rejected: the database cannot enforce budget ≥ 0 or the currency list. |

## 4. Data model — migration `0054_agent_student_counseling`

Create-table only, guarded like 0053 (on a fresh database `0001_initial`'s `create_all()` has already built the table from the model).
No existing table is altered and no existing row is read or written. `downgrade()` drops the table — **counseling data is lost on
downgrade** (same as 0053). Model `AgentStudentCounseling` in `models.py` beside `AgentStudent`.

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | |
| `agent_student_id` | UUID FK → `agent_students.id`, not null | `UNIQUE` (`uq_agent_student_counseling_student`) |
| `counseling_completed` | Boolean, not null | |
| `completed_at` | timestamptz, null | `ck_agent_student_counseling_completed`: `counseling_completed = (completed_at IS NOT NULL)` and `(completed_at IS NULL) = (completed_by_user_id IS NULL)` |
| `completed_by_user_id` | UUID FK → `users.id`, null | |
| `career_interest` | VARCHAR(200), null | |
| `course_preference` | VARCHAR(200), null | |
| `country_preference` | VARCHAR(120), null | |
| `budget_amount` | NUMERIC(10,2), null | `ck_agent_student_counseling_budget`: `budget_amount IS NULL OR budget_amount >= 0` |
| `budget_currency` | VARCHAR(3), null | `ck_agent_student_counseling_currency`: `budget_currency IS NULL OR budget_currency IN (…7 codes…)`; `ck_agent_student_counseling_budget_pair`: `(budget_amount IS NULL) = (budget_currency IS NULL)` |
| `remarks` | TEXT, null | ≤ 2000 enforced in the schema |
| `updated_by_user_id` | UUID FK → `users.id`, not null | |
| `created_at`, `updated_at` | `TimestampMixin` | |

Limits match the Step 1 fields (`_RECORD_LIMITS`: course 200, country 120, notes 2000). **Retention:** the row lives and dies with the
student row (AGN-004 has no hard delete).

## 5. Backend

### 5.1 Schema — `schemas.py`, beside `AgentStudentAssign`

`AgentStudentCounselingSave` (`extra="forbid"` → unknown or server-owned keys are 422):
- `counseling_completed: bool` — required.
- `career_interest`, `course_preference`, `country_preference`, `remarks: str | None = None` — `clean_free_text` with the limits above
  (trim, blank → null, NUL / bidi override → 422).
- `budget_amount: Decimal | None = None` — `ge=0, le=99_999_999.99, max_digits=10, decimal_places=2`; NaN/Infinity rejected (pydantic
  default `allow_inf_nan=False`). A negative amount → 422 (the owner's acceptance criterion).
- `budget_currency: Literal["INR","USD","GBP","EUR","CAD","AUD","NZD"] | None = None` — model validator: amount given and currency
  omitted → `INR`; currency given without an amount → 422 (`currency_without_amount`).
- PUT replaces the whole record: an omitted optional field is stored as null.

### 5.2 Service — `services/agent_students.py`

- `counseling_detail(db, row) -> dict | None` — loads the counseling row for a student (one `select` with `completed_by` /
  `updated_by` names via outer joins). Shape: `{counseling_completed, completed_at, completed_by, career_interest, course_preference,
  country_preference, budget_amount, budget_currency, remarks, updated_at, updated_by}`; `budget_amount` serialised as a 2-decimal
  string (no float rounding); `completed_by` / `updated_by` are names, never ids.
- `record_detail` adds `"counseling": await counseling_detail(db, student)`. **`record_item` (the list shape) is not changed.** Every
  route returning the detail (create, get, patch, archive, unarchive, assign, counseling) gains the additive `counseling` key.
- `save_counseling(db, row, user, data) -> list[str]` (no commit, like `apply_update`): loads the existing counseling row (the student
  row is already locked); creates it if absent; applies C5 (`completed_at = now`, `completed_by = user` when changing to true; kept when
  already true; cleared on false); returns the sorted names of fields whose value changed (`completed_at` / `completed_by` are not
  listed — `counseling_completed` is). Sets `updated_by_user_id` only when something changed.

### 5.3 Route — `api/agent_students.py`

```
PUT /workflows/overseas/agent/crm/students/{student_id}/counseling   body: AgentStudentCounselingSave
```
1. `membership = _gate(user)` — not an agent / org not active → 403 (super_admin not admitted).
2. `row = await _locked_row(db, user, membership, student_id)` — organisation lock, then the scoped student row `FOR UPDATE`;
   out of scope / unknown → **404** before any other check.
3. `row.student_id is not None` → 409 "Counseling is recorded only for students without a login"; `row.status == "archived"` → 409
   "Unarchive this student first" (same wording as PATCH).
4. `changed = await save_counseling(...)`; if changed: `_audit(db, user, "counseling", row.id, {"fields": changed})`.
5. One `commit`; then `_log("agent_student_counseling_saved", membership, user, row.id, fields=changed)` if changed.
6. Return `{"student": await record_detail(db, row)}` (200, also for a no-op).

### 5.4 Transactions and races

- One transaction per request; the audit row is written in it (fail closed, SEC-001); write functions never commit.
- Lock order is the one every agency write uses: organisation row, then the student row. Consequences:
  - Two first saves for the same student serialise; the second updates the row the first inserted (the `UNIQUE` constraint is the
    backstop — an `IntegrityError` there would be a bug, not a user path).
  - A save racing an archive: whichever commits second sees the other's result (save after archive → 409; archive after save → the
    record is kept, read-only).
  - A save racing an unassign of that staff member: the save re-evaluates scope under the lock → 404.
- Two simultaneous edits of the same record: last write wins (no ETag contracted, §2).

### 5.5 Staff activity — `services/staff_activity.py`

- Add `"agent_student.counseling"` to `STAFF_ACTIVITY_ACTIONS`.
- `_fields()` returns field names for `agent_student.counseling` as it does for `agent_student.update` (names only; A3 of AGN-021).
- The subject resolves through the existing `agent_student` entity type — no change there.

### 5.6 Errors

| Case | Status |
|---|---|
| Not an agent, `super_admin`, organisation pending / rejected / suspended | 403 |
| Unknown student, another agency's, staff member's unassigned student | 404 `Student not found` |
| Student has a login / is archived | 409 |
| Validation (§5.1) | 422 (FastAPI list; `loc` ends with the field name) |

## 6. Frontend (`apps/web`)

- **`lib/agentStudents.ts`** — `Counseling` type; `AgentStudentDetail.counseling: Counseling | null`; `CURRENCIES`; `BUDGET_MAX`;
  `counselingUrl(id)`; `counselingValues(c)`; `counselingPayload(values)`; `validateCounseling(values)` (amount ≥ 0, ≤ max, ≤ 2 decimals,
  currency needs an amount, remarks ≤ 2000); `formatBudget(amount, currency)` (`Intl.NumberFormat`, currency style).
- **New `components/AgentStudentCounselingCard.tsx`** (props: `detail`, `editing`, `onEditingChange`, `onSaved`), rendered by
  `AgentStudentDetailPanel` under the student details with an `h5` "Counseling" heading.
  - *Loading:* none of its own — the record arrives with the detail (the panel's loading state covers it).
  - *Empty:* "Counseling not recorded yet."
  - *View:* Counseling completed ("Yes · 1 Oct 2026 · by Priya" / "No"), Career interest, Course preference, Country preference,
    Budget (`formatBudget`), Remarks (`pre-wrap`), Last updated by; empty values show "—".
  - *Actions:* "Record counseling" (no record) / "Edit counseling" (record), only when `!has_login && status === "active"`.
  - *Form:* checkbox, three text inputs, amount (`inputMode="decimal"`) + currency select (default INR), remarks textarea with a
    2000 counter. Client errors on the field (`aria-invalid`, `aria-describedby`), first invalid field focused, no request sent.
  - *Saving:* fieldset disabled, button "Saving…", an in-flight ref blocks a double submit.
  - *Server errors:* 422 mapped to fields like `AgentStudentForm.fieldErrors` (falls back to one message when a `loc` is not a form
    field); 404 / 409 / network → one `role="alert"` message (`detailMessage`, fallback "Unable to save counseling.").
  - *Success:* `onSaved(student)` → panel shows the new record; `role="status"` "Counseling saved."; focus returns to the heading.
  - *Leave prompt (C9):* while dirty, the `beforeunload` + capture-phase in-app link prompt copied from `AgentStudentForm`; Cancel
    with changes asks first.
- **`AgentStudentDetailPanel.tsx`** — owns `editing: "none" | "student" | "counseling"`; only one form open; the other form's button
  hidden while one is open; Escape closes the panel only when nothing is being edited. The Step 1 rows and behaviour are unchanged.
- **`lib/agentStaff.ts`** — label `"agent_student.counseling": "Recorded counseling"`.

## 7. Acceptance criteria → tests (written before the code)

| ID | Criterion | Test |
|---|---|---|
| AGN-006-AC01 | A Master saves all six fields; `GET /students/{id}` returns them exactly (`budget_amount` "2500000.00", currency) | `test_agn_006_counseling.py` |
| AGN-006-AC02 | The assigned staff member can save; staff on another staff member's / an unassigned student, another agency's student, an unknown id → 404 and nothing written | `test_agn_006_counseling.py` |
| AGN-006-AC03 | 422 for: negative budget, > 99,999,999.99, 3 decimals, NaN, unknown currency, currency without amount, unknown key, missing `counseling_completed`, text over its limit, NUL byte; amount without currency stores INR | `test_agn_006_counseling.py` |
| AGN-006-AC04 | Student with a login → 409; archived student → 409; nothing written | `test_agn_006_counseling.py` |
| AGN-006-AC05 | Completed stamp: no→yes sets `completed_at`/`completed_by`; yes→yes keeps them; →no clears them | `test_agn_006_counseling.py` |
| AGN-006-AC06 | One `agent_student.counseling` audit row with `{fields}` names only (no values); a no-op save writes none; Staff Activity lists it with field names and no budget/remarks | `test_agn_006_counseling.py`, `test_agn_006_activity.py` |
| AGN-006-AC07 | Non-agent, `super_admin`, pending / suspended organisation → 403 | `test_agn_006_counseling.py` |
| AGN-006-AC08 | PUT replaces: an omitted optional field becomes null; `counseling` is null before the first save; the list item shape is unchanged; the PATCH contract is unchanged | `test_agn_006_counseling.py` |
| AGN-006-AC09 | Migration upgrade → downgrade → upgrade, single head; the DB rejects a negative budget, a currency without an amount and an unknown currency written directly | `test_agn_006_migration.py` |
| AGN-006-AC10 | Card: empty / view / form states; buttons hidden for a login or archived student; client errors send nothing; 422 → field, 409 → alert; success shows the record and status; only one form open | `AgentStudentCounselingCard.test.tsx`, `tests/lib/agentStudents.test.ts` |
| AGN-006-AC11 | Browser: a Master records counseling, reloads and sees it; a negative budget shows the field error | `tests/e2e/agn-006-counseling.spec.ts` |

Regression set (lite; the owner runs the full backend suite separately): `test_agn_003_*`, `test_agn_004_*`, `test_agn_005_*`, `test_agn_021_*`, and the
`AgentStudents*` / `AgentStaffActivity` component tests.

## 8. Security review

| Concern | Control |
|---|---|
| Broken object-level authorisation | Scope in the `WHERE` clause (`load_scoped`) under the lock; 404 before any role/state check |
| Mass assignment | `extra="forbid"`; `completed_at`, `completed_by`, `updated_by` are server-owned |
| Sensitive data in logs / activity | Logs and audit carry ids and field names only; budget and remarks never leave the record (AGN-021 A3) |
| Injection / hostile text | ORM parameters; `clean_free_text` (NUL, bidi overrides); React escapes on render |
| Numeric abuse | `Decimal` with bounds and 2 places; NaN/Infinity rejected; DB check as a second guard |
| Data privacy | Budget is personal financial data, visible only inside the student's existing scope; `NEEDS_CONFIRMATION` residual from AGN-004 (no erasure path for students without a login) now also covers this record — noted in `PRD_OPEN_ITEMS.md` |

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| `record_detail` change breaks AGN-004/005 shape assertions | Additive key only; run the AGN-004/005 files; AC08 asserts the list shape |
| Scope / 404-before-403 order | Reuse `_locked_row`; AC02 |
| Staff Activity leaks values | `_fields` returns names only; AC06 checks the response for the budget and remarks strings |
| Migration collision with AGN-007 | Recheck `main` before executing and before merging; re-chain if needed |
| Detail panel focus / Escape regressions | Panel-level `editing` state; AC10 checks Escape and single-form |

## 10. Documentation to update with the code

`ENHANCEMENT_BACKLOG.md` (row + §AGN-006), `PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-047`, C1–C9), `API_CONTRACT.md` (new PUT, detail
`counseling` key), `DATA_MODEL.md` (table addendum), `RBAC_MATRIX.md` (row), `RTM.md` (AC01–AC11), `PRD_OPEN_ITEMS.md` (privacy note),
`EVIDENCE_REGISTER`/backlog Appendix note that §5 STEP 2 left `EVID-015`'s parked list.
