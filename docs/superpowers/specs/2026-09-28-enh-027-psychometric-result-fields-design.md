# ENH-027 — Psychometric Record: Structured Result Fields — Design

**Status:** Design approved in-session, 2026-09-28, section by section (data/API/backend, frontend,
acceptance criteria and tests). Superpowers architectural path: brainstorming → this design doc →
`writing-plans` next. Revised the same day after API / frontend / security engineering reviews (§11).
Rebased on `main` after ENH-021/026 (2026-09-28), then after ENH-024 (same day, which took `DEC-SCOPE-033`/`0044`): migration `0045`, `DEC-SCOPE-034`, ENH-026 field names,
comma list input, `.record-details` display (§9 Q8/Q9). Written spec awaiting user review.

**Source requirement:** `School CRM.md §6` "Psychometric Test Module", "Individual Student" subsection
(`docs/sources/School CRM.md:254-300`, byte-identical to `functionalities/edusphere_markdown/School CRM.md`;
`EVID-014`, `DERIVED_BLUEPRINT`) — a 12-field record to "Store".
**Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md:2514-2584` (`ENH-027`).
**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → `DEC-SCOPE-034` (added by the
implementation plan's first task; records the in-session answers in §9 as `EXPLICIT_APPROVAL`, user,
2026-09-27/28 — same precedent as `DEC-SCOPE-029` for ENH-025). If another branch claims `DEC-SCOPE-034`
or migration `0045` first, renumber on merge (precedent: `DEC-SCOPE-024`/`025`, `0041`'s re-chain note).
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
| 8 | Career recommendations | — | `recommended_careers` (JSON list[str]) |
| 9 | Recommended streams | — | `recommended_stream` (JSON list[str]) |
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
recommended_careers  JSON    list[str]
recommended_stream     JSON    list[str]
counsellor_remarks      Text
parent_discussion_on    Date
parent_discussion_notes Text
follow_up_on            Date
```

**Migration `0045_psychometric_result_fields`** (down_revision `0044_skill_india_certification`):
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
  `field_validator(mode="before")` that accepts only `None`, a blank string (→ `None`, same as the text
  fields' blank → `None`; an emptied `<input type="date">` submits `""`), or a string of exactly `YYYY-MM-DD`
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
- The 422 body follows the existing `HTTPException(422, <message>)` convention via ENH-025's
  `validation_message` (`"<field> <reason>"`, never echoing the value, e.g.
  `"strengths must have at most 20 items"`). Parsing and applying reuse ENH-025's generic
  `_master_fields_or_422(model, data)` and `_apply_master_fields(obj, fields)` (`schools.py:610-630`);
  no parallel helpers are written.

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
- **No mass assignment.** Only `report_url` and the 10 result keys are ever written. `school_student_id`,
  `psychometric_team_user_id`, `status`, `assessment_type`, `id`, `created_at` in a PATCH body stay ignored,
  as today — a record can never be moved to another student or re-attributed to another member (abuse
  test in §8).
- JSON list columns are always **reassigned** (a new list object), never mutated in place, so SQLAlchemy
  marks them dirty and the UPDATE touches only changed columns (the basis of §4.3).

**HTTP semantics.** POST stays `201` + the created record; PATCH stays `200` + the updated record; the
error mapping stays the house one — `403` role/portfolio/tier, `404` unknown record, `422` validation, all
with a string `detail`. PATCH is naturally idempotent (it sets values), so a client retry is safe; POST
create stays non-idempotent (pre-existing, unchanged — no `Idempotency-Key` is introduced, none is
contracted for this route).

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

Response size: validation caps bound one record's result payload at roughly 14 KB worst case
(5 × 20 × 80 chars + 4000 + 2000). The two list endpoints are unpaginated today; paginating them would be
a contract change outside ENH-027 and is not done (noted as a follow-up if portfolios grow large).

The output contract (field names, `null` = not recorded, ISO dates, lists never empty — `null` instead)
is recorded in `API_CONTRACT.md` and mirrored by one exported TypeScript type (§5.5).

Visibility (§9 Q1, Q10): every role that can read the record today sees the result fields — including, through the portfolio and the 360° tab, the portfolio-scoped Academic Team and Career Counsellor (Q10). Scope loaders
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

### 5.1 `components/PsychometricResultDetails.tsx` (new, shared, presentational)

Server-safe, no hooks. Props: one assessment object typed `PsychometricResult` (§5.5). Mirrors the
ENH-018 precedent (`ActivityFeedbackDetails` inside `<details>`, `SchoolActivityFeedbackPanel.tsx:204`).
- One `<dl className="record-details">` — ENH-026's `CareerRecordDetails` list (label/value rows, one
  column ≤640 px, `overflow-wrap: anywhere`), so both records read alike in the 360° view and on the parent
  page: Test date, the 5 list fields (items joined with ", ", like ENH-026), Counsellor remarks, Parent
  discussion (date — notes), Follow-up (dates via `formatCalendarDate`). A field whose value is `null` is
  omitted. Everything is plain text, React-escaped.
- Counsellor remarks and parent-discussion notes keep their line breaks (`white-space: pre-wrap`).
- Also exports `PsychometricResultsList({ assessments })` — the per-assessment `<details>` / "no results
  recorded yet" block of §5.2 — so both consumers render one component instead of repeating the loop.
  `hasResults` comes from `lib/psychometric.ts` (§5.5).
- No new colours, radii or shadows: existing tokens/classes only; one small CSS block in `globals.css`
  (`.psy-results`, `.psy-result`, `.psy-result-text`) for the disclosure and the pre-wrap text.

### 5.2 360° Psychometric tab (`Student360Panels.tsx:109-110`)

Existing table (Assessment / Status / Date, caption "Psychometric assessments") kept verbatim. Below it,
one line per assessment:
- `hasResults` → `<details className="psy-result"><summary>{assessment_type} — results</summary>
  <PsychometricResultDetails …/></details>` (collapsed by default, so a long history stays scannable;
  `<summary>` is natively keyboard-operable and announced as expandable — no ARIA re-implementation).
- otherwise → `<p className="muted">{assessment_type}: no results recorded yet.</p>` — no empty
  disclosure to open. This is the legacy/empty state (AC06).
Restricted/empty/loading states of the tab itself are unchanged (`_tab`, `EMPTY_TEXT`, `loading.tsx`).

### 5.3 Psychometric Team dashboard

**Split for focus.** `SchoolPsychometricRecordsPanel.tsx` is 150 lines; the editor goes in a new client
component `components/PsychometricResultsForm.tsx` so neither file passes ~200 lines. The panel keeps
the table, the attach card, the assign card and the "which card is open" state.

**Panel changes (`SchoolPsychometricRecordsPanel.tsx`)**
- Actions cell wraps its buttons in the existing `.actions` flex-wrap container (two buttons wrap on a
  phone instead of widening the table; the table already sits in `.table-wrap`).
- New button **"Record results"** / **"Edit results"** (when `hasResults`) for every status, beside the
  existing "Attach report" (assigned only) / "Report attached". Its `aria-label` names the student and
  assessment ("Record results for Aarav — Aptitude Test"), because several rows show the same visible text.
- One card open at a time: opening the results card closes the attach card and vice-versa (the existing
  `uploadingId` state becomes `open: {kind: "attach" | "results", id} | null`; attach behaviour, ids and
  messages unchanged).

**Editor (`PsychometricResultsForm.tsx`)** — props: the record, the student name, `onDone(saved: boolean)`.
Patterns reused from `ActivityFeedbackForm.tsx` (ENH-018), not reinvented:
- **Heading + focus:** `<h3 tabIndex={-1}>Results — {student} · {assessment}</h3>`, focused on open
  (keyboard and screen-reader users land in the card). On Cancel or success, focus returns to the button
  that opened it (the panel keeps a ref per row).
- **Layout (visual hierarchy):** three groups, each a `<fieldset>` with a `<legend>`:
  1. *Assessment* — Test date.
  2. *Findings* — Strengths, Interest areas, Personality indicators, Career recommendations,
     Recommended streams — single-line inputs, **comma-separated** like the ENH-025/026 forms (reusing
     `splitList`/`listText`); hint "Separate items with commas — up to 20 items of 80 characters each"
     (§9 Q9).
  3. *Counselling & follow-up* — Counsellor remarks, Parent discussion date + notes, Follow-up date.
  Dates sit in the existing `.form-grid` (two columns, one column ≤640 px); textareas span full width
  (`.field.full`). Every control has a real `<label htmlFor>`; hints are linked with `aria-describedby`.
- **Client-side checks (usability, not security — the server stays the authority):** textareas carry
  `maxLength` (4000 / 2000); list fields are checked on submit for >20 items or an item >80 characters —
  a failing field gets `aria-invalid="true"` and an inline message linked by `aria-describedby`, and focus
  moves to the first invalid field. Character counters for the two long text fields ("n / 4000"), as in
  `ActivityFeedbackForm`.
- **Payload:** prefilled from the record; on submit only **changed** fields are sent (lists compared after
  split-lines → trim → drop blanks; dates/text compared after trim). An emptied field is sent as `null`.
  No changed field → no request, polite status "No changes to save."
- **Saving:** submit and Cancel disabled, submit label "Saving…", `aria-busy` on the form.
- **Failure** (422/403/network via `sendJson`): `FormMessage` alert inside the card (announced, scrolled
  into view on a phone — its existing behaviour); card stays open; everything typed is kept.
- **Unsaved changes:** `beforeunload` warning while dirty (ActivityFeedbackForm precedent) — remarks can
  be long.
- **Success:** `onDone(true)` → panel closes the card, shows "Results saved." under the assign form (where
  the attach success already goes), `router.refresh()`.
- **Perceived performance:** no optimistic update — the server normalises lists (dedupe, trim, blank
  drop), so an optimistic render could show values that were not stored. The card is client-only; the page
  stays server-rendered; the refresh re-fetches one list.
- Assign form and attach flow unchanged (`#psych-student`, `#psych-type`, `#report-url` keep their ids);
  new controls get new `psy-result-*` ids.

### 5.4 Parent child overview (`SchoolChildOverview.tsx:154-163`)

Existing table unchanged. Below it, the same per-assessment `<details>` / "no results recorded yet" line
as §5.2. `Assessment` type gains the optional fields.

### 5.5 Types

`PsychometricResult` (the 10 optional fields, `string | null` for dates/text, `string[] | null` for
lists), `hasResults`, the field labels/limits and the pure form helpers (`toDraft`, `changedFields`,
`listError`) live in `lib/psychometric.ts` (precedent: ENH-025's `lib/schoolStudents.ts`) so the server
component and the client form share them without importing each other. The type is intersected into: `Record_` in the panel and
in `app/school/psychometric-team/dashboard/page.tsx`, `lib/portfolio.ts` `psychometric_report`, and
`SchoolChildOverview`'s `Assessment`.

### 5.6 States, accessibility, responsiveness — summary

| Concern | Handling |
|---|---|
| Loading | Existing route `loading.tsx` (360°); server-rendered dashboard/parent page; form "Saving…" + `aria-busy` |
| Empty | Existing tab/table empty text; per-assessment "no results recorded yet" line (no empty disclosure) |
| Error | Existing page-level read errors; form `FormMessage` alert + field-level `aria-invalid` |
| Keyboard | Native `<button>`, `<details>/<summary>`, form controls; focus to card heading on open, back to trigger on close, to first invalid field on a client check |
| Screen reader | Labelled controls, fieldset legends, row-specific button labels, alert vs status live regions (existing `FormMessage`) |
| Mobile (320 px) | `.form-grid` → one column; `.record-details` one column; `.actions` wraps; `overflow-wrap: anywhere` on free text; table stays in `.table-wrap` |
| Design language | Existing classes and tokens only; no new dependency |

## 6. Security and authorization (security-and-hardening review)

**Trust boundaries:** the two write routes (JSON body from a `psychometric_team` session) and the four
read paths (data written by staff, rendered to Coordinator/Principal/Teacher/Parent). **Assets:**
psychometric findings and counsellor remarks about minors — *sensitive* personal data.

| Check | Finding / design | Change in ENH-027 |
|---|---|---|
| Authentication | `get_current_user` on every route; httpOnly `SameSite=Lax` JWT cookies (`auth.py:88`) | None |
| Authorization | Role gate + `_student_in_portfolio` before any write; readers via `_readable_students` / `_load_student_for_reader` | None — new fields ride inside rows those loaders already admit |
| IDOR | PATCH resolves the record, then re-checks the *record's* student against the caller's portfolio; reads are keyed on the loaded student, never a raw id | None; abuse tests: out-of-portfolio record id, reader PATCH |
| Role escalation / mass assignment | Only `report_url` + 10 allow-listed keys are written; ownership/status/student keys in a body are ignored | Abuse test: PATCH with `school_student_id`/`psychometric_team_user_id`/`status` changes nothing |
| Input validation | Pydantic model at the route boundary; house rules for lists/text (caps, control + bidi rejection); `YYYY-MM-DD`-only dates | New model (§4.1) |
| XSS | React escaping; no `dangerouslySetInnerHTML`; list items and remarks rendered as text | Abuse test: `<script>`/`<img onerror>` payload stored and rendered as literal text (web unit test) |
| CSRF | `SameSite=Lax` cookies + CORS limited to `settings.frontend_url` with JSON bodies (`main.py:52`) | None (existing model covers the two routes) |
| SQL injection | SQLAlchemy ORM, bound parameters only | None |
| Token / session handling | Unchanged; client uses same-origin `sendJson` | None |
| Secret exposure | No secrets, config or env involved | None |
| Sensitive logs | Routes log no payloads; audit metadata holds **field names only**, never values | Test: audit metadata has no result values |
| Rate limiting | None on staff write routes (`SECURITY_CONTROLS.md`: open item, auth endpoints). Authenticated, role- and portfolio-scoped, ~14 KB max per record | Not added — "ask first" category and outside ENH-027; noted as existing open item |
| Audit | Create/update already audited in the same transaction; update now lists the changed field names | Additive metadata |
| Privacy / retention | New fields live **on the existing row**, so they follow that row's existing access, retention and any export/deletion path automatically (no new store, no copy) — one reason for Approach A | None |
| Report link | `report_url` stays unvalidated at write (RAID I-33, pre-existing) and rendered only via `safeHref` | None |

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
  ENH-022/023 tier rules behave as before — after the partnership expires both create and update are 403
  and a result-field PATCH changes nothing (`test_enh_022_tier_enforcement.py:148` is the existing
  precedent for `report_url`); readers cannot PATCH.
- **ENH-027-AC05:** Coordinator, Principal, Teacher and Parent see the result fields via
  `/psychometric-records`, the child overview, the portfolio and the 360° Psychometric tab, within their
  existing scope. Which endpoints return `report_url` is unchanged.
- **ENH-027-AC06:** A legacy record (all new fields null) serializes with nulls and renders
  "{assessment}: no results recorded yet." (no empty disclosure) — never an error.
- **ENH-027-AC07:** UI — a Psychometric Team member records and edits results from the dashboard (only
  changed fields sent; no-change submits nothing; failure keeps input; saving state disables actions;
  focus moves to the card heading on open and back to the trigger on close; client checks mark the
  invalid field); the 360° tab and the parent child page show the structured data; the editor and the
  details are usable at 320 px width and by keyboard alone.
- **ENH-027-AC10 (security):** A PATCH body carrying `school_student_id`, `psychometric_team_user_id` or
  `status` changes none of them; HTML/script text in any result field is stored as text and rendered as
  literal text; audit metadata never contains result values.
- **ENH-027-AC08:** No regression — report counts, entitlement usage count, timeline events, portfolio
  completion %, and the existing SCH-005/007/008/011, ENH-012/013/022/023 suites pass unchanged.
- **ENH-027-AC09:** Migration `0044` upgrade → downgrade → upgrade on a database with existing
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
- AC10: mass-assignment PATCH (student/owner/status keys) → nothing but allowed keys changes; audit
  metadata holds field names only; blank date string → `null`; `<script>` text round-trips unchanged as
  data (the API stores text; escaping is the renderer's job).

**Migration (AC09):** round-trip script against the Docker Postgres (user starts the stack) with seeded
psychometric rows; compare row values before/after.

**Web unit (Vitest):**
- `tests/components/PsychometricResultDetails.test.tsx` (new): full data; partial data (null facts
  omitted); `hasResults` true/false; `<script>`/`<img onerror>` text rendered literally (AC10).
- `tests/components/PsychometricResultsForm.test.tsx` (new): prefill; only changed fields in payload;
  emptied field → `null`; no-change → no request + status; client check (>20 items / an item >80 chars) →
  `aria-invalid` + message + focus on the field, no request; 422 → alert, card open, input kept; busy
  state disables submit/Cancel; heading focused on open; `beforeunload` registered only while dirty.
- `SchoolPsychometricRecordsPanel.test.tsx` (extend): "Record/Edit results" label by `hasResults`;
  row-specific accessible name; one card at a time with attach; focus returns to the trigger on Cancel;
  existing attach/assign tests unchanged.
- `Student360Panels.test.tsx`, `SchoolChildOverview` test (extend): `<details>` when results exist;
  "no results recorded yet" line otherwise; existing table unchanged.

**Playwright (AC07):** new `tests/e2e/enh-027-psychometric-results.spec.ts` (API-only setup like
`enh-013-student-360.spec.ts`, so the long SCH-004/005/006 flow stays untouched) — record results (keyboard-only for the editor: Tab to the button, Enter, fill, submit); verify on
the psychometric team's 360° tab and on the parent's child page; one run at a 320 px viewport checks the
editor has no horizontal page scroll.

**Regression (AC08):** per task, the psychometric-related API tests + web unit tests. Full backend and
E2E suites once at the end (user's every-3-4-features cadence; this is one feature).

## 9. Decisions confirmed in-session (→ `DEC-SCOPE-034`; `031`/`032` went to ENH-026/021)

| # | Question | Answer |
|---|---|---|
| Q1 | Which readers see the new fields? | All existing readers (Coordinator/Principal/Teacher/Parent), same scope as today |
| Q2 | Who writes Counsellor remarks / Parent discussion? | Psychometric Team only (SCH-005-AC04 unchanged) |
| Q3 | Career recommendations shape, given ENH-026 is unbuilt? | `list[str]`. ENH-026 then landed first with the same shape (`DEC-SCOPE-031`), so ENH-027 follows it (Q8) |
| Q4 | Parent discussion / Follow-up shape? | Parent discussion = date + notes; Follow-up = date |
| Q5 | Test date storage? | New nullable `test_date`; `created_at` stays "assigned on" |
| Q6 | Required fields / completion rule? | All optional; completion still flips only on `report_url` |
| Q7 | §6 "Counselling Completed" count? | Not in ENH-027 → ENH-026 |
| Q8 | (2026-09-28, after ENH-021/026 merged) Field names? | Match ENH-026: `recommended_careers`, `recommended_stream` (UI labels stay "Career recommendations" / "Recommended streams") |
| Q9 | (same) How are list fields typed? | Comma-separated, like ENH-025/026 (`splitList`/`listText`) |
| Q10 | (2026-09-28, final review) What do the portfolio-scoped service roles see? | Academic Team and Career Counsellor see all ten fields in the portfolio and the 360° tab (owner approval; pinned by `test_portfolio_service_roles_see_result_fields_in_the_portfolio_and_360`) |

## 10. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| `portfolio_payload` feeds `/portfolio`, 360° tabs and completion % for every reader | Additive keys only; completion formula untouched; AC05/AC08 tests |
| Stricter parsing breaks existing clients | Routes keep `payload: dict`; only the 10 new keys are validated; unknown keys still ignored |
| Exact-shape assertions in existing tests | Additive keys; existing tests asserting whole dicts (`test_sch_reports`, `test_sch_008`, `test_sch_011`) cover structures this design does not touch |
| e2e selectors | Existing ids kept; new controls get new ids |
| Migration/decision-ID collision with parallel branches | Renumber on merge per precedent (header note) |
| Audit metadata shape change on PATCH (`{}` → `{"fields": [...]}`) | Additive; no reader of that metadata depends on `{}` — verified by grep in the plan's first task |
| Panel refactor (`uploadingId` → one open-card state) touches the attach flow | Attach ids/messages/behaviour kept; existing panel tests and the SCH-004/005/006 e2e run unchanged first (red→green only on new cases) |

## 11. Engineering reviews applied (2026-09-28)

Reviewed against `api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening`,
checked against the actual code. Changes this review made to the design:

- **API:** blank date string → `null`; explicit mass-assignment allow-list + abuse test; JSON columns
  reassigned (dirty tracking); HTTP status/idempotency semantics stated; response-size bound stated;
  output contract documented in `API_CONTRACT.md` with one TS type. Not adopted, with reason: a
  `response_model` on the existing routes (Hyrum's-law risk to serialization of existing keys for no
  requirement gain), pagination of the two list endpoints (contract change outside ENH-027), a structured
  `{code, message, details}` error body (the house convention is a string `detail`; changing it for two
  routes would make them inconsistent with the rest).
- **Frontend:** editor split into `PsychometricResultsForm.tsx` (panel stays <200 lines); fieldset
  grouping for hierarchy; focus management, `beforeunload`, character counters and field-level
  `aria-invalid` reused from `ActivityFeedbackForm`; row-specific button names; empty results shown as a
  plain line, not an empty disclosure; `overflow-wrap` for 320 px; no optimistic update (server
  normalises lists).
- **Security:** §6 threat table. No new controls needed beyond validation and abuse tests; rate limiting
  and `report_url` validation remain pre-existing open items, deliberately not touched here.
