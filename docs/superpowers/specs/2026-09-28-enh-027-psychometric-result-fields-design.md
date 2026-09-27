# ENH-027 — Psychometric Record: Structured Result Fields — Design

**Status:** Design approved in-session, 2026-09-28, section by section (data/API/backend, frontend,
acceptance criteria and tests). Superpowers architectural path: brainstorming → this design doc →
`writing-plans` next. Written spec awaiting user review.

**Source requirement:** `School CRM.md §6` "Psychometric Test Module", "Individual Student" subsection
(`docs/sources/School CRM.md:254-300`, byte-identical to `functionalities/edusphere_markdown/School CRM.md`;
`EVID-014`, `DERIVED_BLUEPRINT`) — a 12-field record to "Store".
**Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md:2514-2584` (`ENH-027`).
**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → `DEC-SCOPE-031` (added by the
implementation plan's first task; records the in-session answers in §9 as `EXPLICIT_APPROVAL`, user,
2026-09-27/28 — same precedent as `DEC-SCOPE-029` for ENH-025). If another branch claims `DEC-SCOPE-031`
or migration `0042` first, renumber on merge (precedent: `DEC-SCOPE-024`/`025`, `0041`'s re-chain note).
**Branch:** `feature/enh-027-psychometric-full-record` (from `main` @ `03d4408`).

## 1. Scope

Field-by-field audit of `SchoolPsychometricRecord` (`apps/api/app/models.py:1269-1278`) against §6's
12 fields. **Correction to the backlog:** it counts 4 existing fields; the honest count is 3 plus a
proxy — `created_at` is the *assignment* day, not the test date.

| # | §6 field | Today | Delivered as |
|---|---|---|---|
| 1 | Test date | ≈ `created_at` (proxy) | `test_date` (Date, new) |
| 2 | Assessment type | `assessment_type` | unchanged |
| 3 | Test status | `status` | unchanged (`assigned`/`completed`) |
| 4 | Report | `report_url` | unchanged |
| 5 | Strengths | — | `strengths` (JSON list[str]) |
| 6 | Interest areas | — | `interest_areas` (JSON list[str]) |
| 7 | Personality indicators | — | `personality_indicators` (JSON list[str]) |
| 8 | Career recommendations | — | `career_recommendations` (JSON list[str]) |
| 9 | Recommended streams | — | `recommended_streams` (JSON list[str]) |
| 10 | Counsellor remarks | — | `counsellor_remarks` (Text, ≤4000) |
| 11 | Parent discussion | — | `parent_discussion_on` (Date) + `parent_discussion_notes` (Text, ≤2000) |
| 12 | Follow-up | — | `follow_up_on` (Date) |

**10 new columns** cover the 9 missing fields.

**Out of scope (decided):**
- §6's school-level "Counselling Completed" count → `ENH-026` (§9 Q7).
- Calendar integration of `follow_up_on` → `ENH-019` (not built).
- Bulk entry → `ENH-028` (will reuse this shape).
- Parent access to the report *file* → Client Question #20 stays open; this design does not change which
  endpoints expose `report_url` (§6).
- Timeline events, reports/KPIs, `PortfolioPanel`, portfolio completion %.

## 2. Approach

Chosen: **A — 10 nullable columns** on `school_psychometric_records`, JSON arrays for list-shaped fields.
Mirrors ENH-025 (`subjects`, `career_interests` are JSON lists on `school_students`); additive; no join;
per-field validation.

Rejected:
- **B — one JSON `result` blob:** not queryable, validation opaque, weakest for ENH-028 bulk import.
- **C — 1:1 child table `school_psychometric_results`:** extra join in six read paths and two rows to keep
  consistent; result history is not a requirement (YAGNI).

**Career recommendations shape** (`ENH-026` coordination, §9 Q3): `list[str]`, same as ENH-025's
`career_interests`, same `_clean_list` rule. `ENH-026` must reuse this shape rather than invent another.
A `{career, rationale}` object list was considered and rejected — nothing in the source asks for a rationale.

## 3. Data model and migration

`SchoolPsychometricRecord` gains (all nullable, no defaults written to existing rows):

```
test_date               Date
strengths               JSON    list[str]
interest_areas          JSON    list[str]
personality_indicators  JSON    list[str]
career_recommendations  JSON    list[str]
recommended_streams     JSON    list[str]
counsellor_remarks      Text
parent_discussion_on    Date
parent_discussion_notes Text
follow_up_on            Date
```

**Migration `0042_psychometric_result_fields`** (down_revision `0041_student_master_fields`):
- Adds the 10 columns, each guarded by an "already exists" check (fresh DBs get them from
  `0001_initial`'s `create_all()`, same reason `0030`/`0041` guard).
- No backfill, no data rewrite, no constraint on existing rows. Existing rows keep every value.
- `downgrade()` drops exactly these 10 columns.
- Empty lists are stored as `NULL` (`_clean_list` returns `None` for empty), so "not recorded" has one
  representation.

## 4. Backend / API

### 4.1 Validation model

New `PsychometricResultFields(BaseModel)` in `apps/api/app/schemas.py`, next to `StudentMasterFields`:

- `model_config = {"extra": "ignore"}` — it is fed only the 10 result keys (§4.2); the route's other keys
  keep their existing handling.
- The 5 list fields → `field_validator(mode="before")` → existing `_clean_list` (≤20 items, ≤80 chars
  each, blank/duplicate items dropped, control/bidi characters rejected, non-list rejected).
- `counsellor_remarks` (`max_length=4000`), `parent_discussion_notes` (`max_length=2000`) → existing
  `_clean_multiline_text` (line breaks allowed; control/bidi rejected; blank → `None`).
- `test_date`, `parent_discussion_on`, `follow_up_on` → `datetime.date | None`, via a
  `field_validator(mode="before")` that accepts only `None` or a string of exactly `YYYY-MM-DD`
  (`date.fromisoformat` on a 10-character string). A datetime string, a number (pydantic's lax mode would
  read it as a Unix timestamp) or an impossible date (`2026-02-30`) is a 422. Pydantic `strict` mode is not
  used: it rejects ISO strings when validating a Python dict, which is what the routes pass.
- No cross-field rules (no "test date not in future", no "follow-up after test"): none is sourced, and a
  late-recorded follow-up is legitimate.
- Every field optional. `model_fields_set` gives PATCH semantics (§4.3).

### 4.2 Route changes (`apps/api/app/api/schools.py`)

Signatures stay `payload: dict`. Existing checks, their order and their error messages are untouched.
A new step is inserted **after** role → student/portfolio → entitlement → existing field checks, and
**before any `db.add`/mutation**:

```python
result = _parse_result_fields(payload)   # picks only RESULT_FIELD_KEYS present in payload,
                                         # validates via PsychometricResultFields, ValidationError -> 422
```

Consequences:
- 403 (role/portfolio) and the entitlement block keep precedence over any 422 on a new field — an
  outsider learns nothing about validation of a record they cannot touch.
- A 422 happens before any write → no partial state; record and audit row still commit in the single
  existing `db.commit()` (one transaction per request, unchanged).
- Unknown keys are still ignored, exactly as today (no `extra="forbid"` on the routes → no new 422s for
  existing clients).
- The 422 body follows the existing `HTTPException(422, <message>)` convention: the first error, named by
  field (e.g. `"strengths: must have at most 20 items"`).

**`create_psychometric_record` (POST `/school/psychometric-team/records`):** sets any provided result
fields on the new record. Status rule unchanged (`completed` iff `report_url` given). Notifications
unchanged. Audit `metadata_json` = `{"assessment_type": ..., "fields": [sorted result keys set]}` —
names only, never values (student data stays out of the audit log).

**`update_psychometric_record` (PATCH `/school/psychometric-team/records/{id}`):**
- For each key in `model_fields_set`: set the column (value, or `None` to clear). Absent keys untouched.
- `report_url` handling, the assigned→completed flip and the parent notification are unchanged.
- Changing only result fields never changes `status` and never notifies parents.
- Entitlement check with `grandfathered_since=record.created_at` unchanged.
- Audit `metadata_json` = `{"fields": [sorted keys changed, incl. "report_url" if sent]}` (was `{}`).

### 4.3 Concurrency

Last-write-wins **per field**: PATCH writes only the keys sent, and the UI sends only fields the user
changed (§5.3), so two members editing different fields of one record do not overwrite each other.
Same-field simultaneous edits: the later commit wins. No ETag/`If-Match` — none is contracted
(constitution: no uncontracted ETag assumptions). Pre-existing and out of scope: two simultaneous report
attaches can each observe `status != "completed"` and notify twice — noted, not changed.

### 4.4 Reads (additive only)

One helper `_psychometric_result_out(r) -> dict` returns the 10 fields (dates as ISO dates, lists as
lists or `null`). It is spread into the existing dicts:

| Endpoint / builder | Readers | Change |
|---|---|---|
| POST/PATCH responses, `GET /psychometric-team/records` | psychometric_team | + 10 fields |
| `GET /school/psychometric-records` (`schools.py:2010`) | coordinator/principal/teacher/parent | + 10 fields; **still no `report_url`** |
| `_overview_payload` `psychometric.assessments` (`schools.py:1208`) | overview readers (parent child page) | + 10 fields |
| `portfolio_payload` `psychometric_report` (`portfolio.py:128`) | portfolio + 360° readers | + 10 fields → reaches the 360° Psychometric tab with **no change to `student_360.py`** |

Visibility (§9 Q1): every role that can read the record today sees the result fields. Scope loaders
(`_student_in_portfolio`, `_readable_students`, `_load_student_for_reader`) are unchanged.

**Explicitly unchanged:** `rbac.py`, `admin.py`, `services/portal.py`, `student_360.py`,
`TAB_360_KEYS`, reports/KPI builders (`schools.py:384-491, 816-843`), entitlement usage count
(`schools.py:1043`), timeline (`schools.py:1266-1270`), portfolio completion formula, notifications.

### 4.5 Seed

`seed.py:741`: Aarav's completed "Aptitude Test" gets demo values for the new fields (test date,
2-3 items per list, remarks, a parent discussion, a follow-up) so the demo and the dev 360° view show
structured data. The two `assigned` demo records stay legacy-shaped (null result fields) — deliberately
exercising the empty state.

## 5. Frontend

### 5.1 `components/PsychometricResultDetails.tsx` (new, shared)

Presentational, server-safe. Props: one assessment object with the optional result fields.
- Facts list: Test date, Parent discussion (date + notes), Follow-up (dates via `formatCalendarDate`),
  Counsellor remarks (`white-space: pre-wrap`).
- The 5 list fields as labelled bullet lists; a list that is `null`/empty is omitted.
- No result field set (legacy / not yet recorded) → one muted line: "No results recorded yet."
- Two consumers (§5.2, §5.4) justify the extraction.

### 5.2 360° Psychometric tab (`Student360Panels.tsx:109-110`)

Existing table (Assessment / Status / Date, caption "Psychometric assessments") kept verbatim. Below it,
per assessment, a `<details>` with `<summary>{assessment_type} — results</summary>` rendering
`PsychometricResultDetails`. Restricted/empty/loading states unchanged (`_tab`, `EMPTY_TEXT`,
`loading.tsx`).

### 5.3 Psychometric Team dashboard (`SchoolPsychometricRecordsPanel.tsx`)

- Actions column gains **"Record results"** (label **"Edit results"** when any result field is set)
  beside the existing "Attach report" (assigned only) / "Report attached". The results button shows for
  every status — results may be recorded before or after the report (§9 Q6).
- Opens a results action card, same interaction model as the attach card: one card open at a time
  (opening one closes the other), message rendered beside the form that produced it, Cancel clears it.
- Fields (each with a real `<label>`):
  - Test date — `<input type="date">`
  - Strengths / Interest areas / Personality indicators / Career recommendations / Recommended
    streams — `<textarea>`, one item per line (hint text says so)
  - Counsellor remarks — `<textarea>`
  - Parent discussion date — `<input type="date">`; Parent discussion notes — `<textarea>`
  - Follow-up date — `<input type="date">`
- Prefilled from the record. On submit, builds the payload from **changed fields only** (compared with the
  prefill; list fields compared after splitting lines + trimming + dropping blanks). An emptied field is
  sent as `null`.
- No changed field → no request; card shows "No changes to save."
- Saving: submit and Cancel disabled, submit label "Saving…".
- Failure (422/403/network, via `sendJson`): server message shown in the card; card stays open; typed
  input preserved.
- Success: card closes, "Results saved." shown under the assign form (same place the attach success
  message goes today), `router.refresh()`.
- Assign form and attach flow unchanged (`#psych-student`, `#psych-type`, `#report-url` keep their ids).

### 5.4 Parent child overview (`SchoolChildOverview.tsx:154-163`)

Existing table unchanged. Below it, the same per-assessment `<details>` + `PsychometricResultDetails`.
`Assessment` type gains the optional fields.

### 5.5 Types

Optional result fields added to: `Record_` in the panel and in
`app/school/psychometric-team/dashboard/page.tsx`, `lib/portfolio.ts` `psychometric_report`,
`SchoolChildOverview` `Assessment`. One shared `PsychometricResult` type exported from the new
component file.

### 5.6 States, accessibility, responsiveness

- Loading: existing route `loading.tsx` (360°) and server rendering (dashboard, parent page).
- Empty: existing tab/table empty text; per-assessment "No results recorded yet."
- Error: existing page-level error handling for reads; form errors per §5.3.
- `<details>/<summary>` is keyboard-operable natively; no ARIA re-implementation.
- Existing `.form`/`.field`/`.action-card` classes; the card stacks at phone width. No new dependency.

## 6. Security and authorization

- No new endpoint, no new role, no RBAC change. Only `psychometric_team` writes (SCH-005-AC04 holds).
- Portfolio/readable-scope loaders run before any query; new fields travel only inside rows those
  loaders already admit.
- Input hardening reuses the house rules (`_clean_list`, `_clean_multiline_text`): control/bidi
  characters rejected, lengths capped, list sizes capped. React escapes all rendered text; no
  `dangerouslySetInnerHTML`.
- Audit log records field names, not values.
- `report_url` exposure per endpoint unchanged (Client Question #20 open; the pre-existing difference
  between `/psychometric-records` and `portfolio_payload` is noted, not changed).

## 7. Acceptance criteria

- **ENH-027-AC01:** A Psychometric Team member creates a record with all 12 source fields in one POST; all
  are returned in the response and in `GET /psychometric-team/records`.
- **ENH-027-AC02:** PATCH updates only the keys sent; an explicit `null` clears a field. A PATCH carrying
  only result fields changes neither `status` nor notifications; `report_url` keeps its existing
  assigned→completed + parent-notification behavior.
- **ENH-027-AC03:** Invalid input — wrong type, non-ISO date, >20 list items, list item >80 chars,
  remarks >4000 / notes >2000 chars, control or bidi-override characters, non-list for a list field — is
  a 422 and leaves the record and the audit log unchanged.
- **ENH-027-AC04:** Authorization unchanged: a non-`psychometric_team` role gets 403 on create/update; a
  student outside the member's portfolio gets 403 even with a valid (or invalid) result payload; the
  ENH-022/023 tier rules behave as before (blocked create after expiry; update grandfathered by
  `created_at`); readers cannot PATCH.
- **ENH-027-AC05:** Coordinator, Principal, Teacher and Parent see the result fields via
  `/psychometric-records`, the child overview, the portfolio and the 360° Psychometric tab, within their
  existing scope. Which endpoints return `report_url` is unchanged.
- **ENH-027-AC06:** A legacy record (all new fields null) serializes with nulls and renders "No results
  recorded yet." — never an error.
- **ENH-027-AC07:** UI — a Psychometric Team member records and edits results from the dashboard (only
  changed fields sent; no-change submits nothing; failure keeps input; saving state disables actions); the
  360° tab and the parent child page show the structured data.
- **ENH-027-AC08:** No regression — report counts, entitlement usage count, timeline events, portfolio
  completion %, and the existing SCH-005/007/008/011, ENH-012/013/022/023 suites pass unchanged.
- **ENH-027-AC09:** Migration `0042` upgrade → downgrade → upgrade on a database with existing
  psychometric rows preserves those rows' existing values.

## 8. Testing (written before implementation)

**API — new `apps/api/tests/test_enh_027_psychometric_results.py`**, reusing the
`test_sch_005_psychometric_assessment.py` fixtures/helpers (`_create_school_with_coordinator`,
`_add_psychometric_team_member`, `_login`):
- AC01: create with all fields → round-trip in response + team list.
- AC02: PATCH present / absent / `null`; result-only PATCH → status unchanged, zero new notifications;
  report attach after results → completed + one notification.
- AC03: one parametrized test over the invalid cases; assert 422, row unchanged, no new audit row.
- AC04: other roles 403; out-of-portfolio 403 with valid and invalid payloads; reader PATCH 403;
  expired-tier create blocked / grandfathered update allowed with result fields.
- AC05: each reader role sees result fields on `/psychometric-records`, overview, portfolio, 360°;
  `/psychometric-records` still has no `report_url` key.
- AC06: legacy row → nulls in every read path.
- Audit metadata holds field names only.

**Migration (AC09):** round-trip script against the Docker Postgres (user starts the stack) with seeded
psychometric rows; compare row values before/after.

**Web unit (Vitest):**
- `tests/components/PsychometricResultDetails.test.tsx` (new): full data; partial data; legacy → "No
  results recorded yet."
- `SchoolPsychometricRecordsPanel.test.tsx` (extend): editor prefill; only changed fields in payload;
  emptied field → `null`; no-change → no request + message; 422 → card open, input kept; busy state;
  one-card-at-a-time with attach.
- `Student360Panels.test.tsx`, `SchoolChildOverview` test (extend): details render; legacy empty line;
  existing table unchanged.

**Playwright (AC07):** extend `tests/e2e/sch-004-005-006-service-delivery.spec.ts` — after attaching the
report, record results; verify on the psychometric team's 360° tab and on the parent's child page.

**Regression (AC08):** per task, the psychometric-related API tests + web unit tests. Full backend and
E2E suites once at the end (user's every-3-4-features cadence; this is one feature).

## 9. Decisions confirmed in-session (→ `DEC-SCOPE-031`)

| # | Question | Answer |
|---|---|---|
| Q1 | Which readers see the new fields? | All existing readers (Coordinator/Principal/Teacher/Parent), same scope as today |
| Q2 | Who writes Counsellor remarks / Parent discussion? | Psychometric Team only (SCH-005-AC04 unchanged) |
| Q3 | Career recommendations shape, given ENH-026 is unbuilt? | Defined here (`list[str]`); ENH-026 reuses it |
| Q4 | Parent discussion / Follow-up shape? | Parent discussion = date + notes; Follow-up = date |
| Q5 | Test date storage? | New nullable `test_date`; `created_at` stays "assigned on" |
| Q6 | Required fields / completion rule? | All optional; completion still flips only on `report_url` |
| Q7 | §6 "Counselling Completed" count? | Not in ENH-027 → ENH-026 |

## 10. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| `portfolio_payload` feeds `/portfolio`, 360° tabs and completion % for every reader | Additive keys only; completion formula untouched; AC05/AC08 tests |
| Stricter parsing breaks existing clients | Routes keep `payload: dict`; only the 10 new keys are validated; unknown keys still ignored |
| Exact-shape assertions in existing tests | Additive keys; existing tests asserting whole dicts (`test_sch_reports`, `test_sch_008`, `test_sch_011`) cover structures this design does not touch |
| e2e selectors | Existing ids kept; new controls get new ids |
| Migration/decision-ID collision with parallel branches | Renumber on merge per precedent (header note) |
| Audit metadata shape change on PATCH (`{}` → `{"fields": [...]}`) | Additive; no reader of that metadata depends on `{}` — verified by grep in the plan's first task |
