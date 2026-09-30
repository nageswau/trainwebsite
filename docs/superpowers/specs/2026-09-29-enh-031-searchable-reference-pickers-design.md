# ENH-031 — Searchable reference pickers: design

**Status:** design approved section by section in-session, 2026-09-29; this written spec awaits the owner's review.
**Decision:** `DEC-SCOPE-037` (provisional number; renumbered by whichever branch merges later, as for earlier entries).
**Branch:** built on `feature/agn-001-multi-tenant-agent-crm` (owner's choice, 2026-09-29), so AGN-001 and ENH-031 reach
`main` together. Agent scoping uses AGN-001's organisation scope (`services/agent_orgs.org_member_ids`).

## 1. Requirement and evidence

- **Requirement (`EXPLICIT_APPROVAL`, the owner, in-session 2026-09-29):** "all the student references and application
  references should be the drop down with valid values. drop down values should be able to search".
- **Current state (read-only investigation, 2026-09-29):** several forms make a user type a raw internal ID; others offer a
  plain `<select>` with no search. The web app has no combobox/searchable-select component and no lookup endpoints.

## 2. Decisions (owner's answers, in-session 2026-09-29)

| # | Question | Answer |
|---|---|---|
| D1 | Which fields? | Both groups: every free-text student/application reference becomes a searchable dropdown of valid values, **and** every existing student/application `<select>` becomes searchable. Other reference fields (commission, visa case, appointment, batch, enrollment, job, document, payment, user, …) are **out of scope**. |
| D2 | Agent "Link student" | Server search only: nothing until 3+ characters; at most 10 matches; email partly masked; students already linked to the caller's agency are left out. No browsable directory. **Revised 2026-09-30 (owner, after the final review showed substring search could probe emails and harvest names):** an email matches only when typed in full (case-insensitive); names match from the start of a word only; at most 30 link searches per agent per minute (`429` + `Retry-After`), counted from `lookup.agent_link_search` audit rows that carry no search text — the one exception to AC10's "no audit row". |
| D3 | Approach | Own accessible `SearchableSelect` component (no new dependency) with a load-once mode and a server-search mode, plus role-scoped read-only lookup endpoints. Rejected: native `<datalist>` (weak label→id mapping, accessibility and mobile behaviour); a library such as react-select/Downshift (new dependency). |
| D4 | Admin School→Overseas bridge "Student ID" | Pick the school first (searchable), then search only that school's students by name or code. No cross-school name browsing. |
| D5 | Branch | Continue on the AGN-001 branch. |

## 3. Field inventory

### 3.1 Free text today → searchable dropdown

| # | Form (file) | Roles | Field (`name`, unchanged) | Source |
|---|---|---|---|---|
| F1 | Upload document (`WorkflowPanel` `DocumentUpload`, rendered for overseas_student and agent only) | agent | `student_id` | `overseas-students` lookup |
| F2 | Upload document | overseas_student, agent | `application_id` (optional) | `overseas-applications` lookup, filtered to the chosen student (a student sees only their own applications) |
| F3 | Schedule appointment (`appointmentSpec(true)`) | counselor, overseas_admin | `student_id` | `overseas-students` lookup |
| F4 | Link student (`agentSpecs` "students") | agent | `student_id` | `overseas-students?purpose=link` (D2) |
| F5 | Update application (`overseasOperationsSpecs`) | university_rep, overseas_admin | `application_id` | `overseas-applications` lookup |
| F6 | Create visa case | overseas_admin | `application_id` | `overseas-applications` lookup |
| F7 | Post admission update | university_rep | `application_id` | `overseas-applications` lookup |
| F8 | Update overseas application (`adminSpecs` "applications"; an Overseas Admin gets F5 in that section) | super_admin | `application_id` | `overseas-applications` lookup |
| F9 | Schedule interview (`placementSpecs`) | placement_team, hr_team, it_admin | `application_id` | `it-job-applications` lookup |
| F10 | Create offer (`placementSpecs`) | placement_team, hr_team, it_admin | `application_id` | `it-job-applications` lookup |
| F11 | School→Overseas bridge (`AdminSchoolApplicationsPanel`) | overseas_admin, super_admin, counselor | student code → school student | D4: `schools` lookup, then `school-students?school_id=` lookup |

### 3.2 Plain `<select>` today → searchable (load-once; data source unchanged)

`SchoolAcademicResultsPanel` (`result-student`), `SchoolPsychometricRecordsPanel` (`psych-student`),
`SchoolTestPrepLanguagePanel` (`testprep-student`, `language-student`), `CareerRecordForm` (`*-student`),
`CareerPreferencesCard` (`prefs-student`), `CounselorChatPanel` (`counselor-chat-student`),
`AgentApplicationCreatePanel` (`agent-app-student`), `EmployerInterviewsPanel` (`shortlist-candidate`).

Every one keeps its current, already-scoped option list and its field `name`/value; only the control changes.

## 4. Component: `SearchableSelect`

- **Markup:** WAI-ARIA 1.2 combobox: a labelled `<input role="combobox" aria-expanded aria-controls aria-activedescendant
  aria-autocomplete="list">` and a `role="listbox"` of `role="option"` items. A hidden `<input type="hidden" name={name}>`
  carries the chosen id, so existing `FormData` submissions and every write endpoint are unchanged.
- **Keyboard:** typing filters; ↓/↑ move the active option; Enter picks it; Esc closes the list;
  Tab leaves the field without picking.
- **Valid values only:** the hidden value is set only by picking an option. Editing the text after a pick clears the pick.
  On submit, a required field with no pick, or text that matches no pick, shows a field error — "Choose a student from the
  list." / "Choose an application from the list." — sets `aria-invalid`, focuses the field, and blocks the submit.
- **Load-once mode** (`options` prop): case-insensitive substring match over `label` and `detail`; at most 50 rendered, then
  "Keep typing to narrow the list."
- **Server mode** (`search(q, signal)` prop): 250 ms debounce; each new query aborts the previous request (`AbortController`)
  and a late reply for an older query is ignored; optional `minChars` (F4: 3) with the hint "Type at least 3 characters.".
  A `truncated: true` reply shows "Keep typing to narrow the list.".
- **States:** "Loading…", "No matching students." / "No matching applications.", load failure with a Retry button. Status
  text is announced through a polite live region.
- **Option text:** overseas student `Full name — email` (F4: masked, e.g. `r***@example.local`); school student
  `Full name — grade · student code`; overseas application `Student — university · course · status`; IT job application
  `Candidate — job title · company · status`; school `Name — school code`.
- **Layout:** full width of its `.field`; the list is positioned under the input, scrolls internally (max ~12 rows), and never
  causes horizontal page scroll at 320 px.

## 5. Lookup endpoints

All read-only, prefix `/api/v1/lookups`. Common query: `q` (optional, max 100 chars, trimmed, matched literally and
case-insensitively with escaped `ILIKE`), `limit` (default 20, 1–50). Response: `{"items": [{"id", "label", "detail"}],
"truncated": bool}` (`truncated` = more matches exist beyond `limit`). Order: label ascending. Each endpoint applies **the
same scope rule as the write endpoint it feeds**, so it never offers a value that write would refuse.

| Endpoint | Roles | Scope | Match on |
|---|---|---|---|
| `GET /overseas-students` | overseas_admin, super_admin | all `overseas_student` users | name, email |
| | counselor | students of the counselor's own applications (rule of `create_appointment` / `add_document`) | name, email |
| | agent | students linked to the caller's agency (`AgentStudent.agent_id IN org_member_ids`) | name, email |
| `GET /overseas-students?purpose=link` | agent only | any `overseas_student` **not** already linked to the caller's agency; `q` required, ≥ 3 chars (else 422); `limit` capped at 10; `detail` = masked email | name, email |
| `GET /overseas-applications` | overseas_student, counselor, university_rep, agent, overseas_admin, super_admin | `_assigned_application` rule (overseas_student own; counselor own; university_rep own university; agent own agency; admin all); optional `student_id=` narrows to that student | student name, university, course, application reference |
| `GET /it-job-applications` | placement_team, hr_team, it_admin, super_admin | all job applications (the rule of `schedule_interview` / create offer) | candidate name, job title, company |
| `GET /schools` | overseas_admin, super_admin, counselor | all partner schools (bridge roles) | name, school code |
| `GET /school-students?school_id=` | overseas_admin, super_admin, counselor | students of that one school only; `school_id` required (D4) | name, student code |

- **Errors:** wrong role → 403 "This role cannot use this lookup"; bad `limit`, over-long `q`, missing `school_id`, or a
  short `q` for `purpose=link` → 422; an unknown `school_id` → 404. Pending/suspended/deactivated agents are denied by the
  existing agent gate (`rbac.agent_denial_reason`).
- **Masking (F4):** keep the first character of the local part, replace the rest with `***`, keep the domain.
- **Logging:** one structured line per lookup (`lookup`, role, result count, truncated); never the search text, never an
  `AuditLog` row (reads — the ENH-016 D15 precedent).
- **Performance:** unindexed `ILIKE` on names bounded by `limit`; acceptable at current volumes and recorded as a known
  limit. No new table, column, index or migration.

## 6. Unchanged

Every write endpoint's request and response, every existing role/scope rule, every existing option list in §3.2, the
School roster screens, and all other reference fields (D1).

## 7. Acceptance criteria

- **AC01** Each §3.1 field is a searchable dropdown; typing filters; only a picked value is submitted; a required field
  without a pick shows the field error and does not submit.
- **AC02** Each §3.2 dropdown is searchable with the same options and submitted value as before.
- **AC03** Each lookup returns only values the matching write accepts, for every allowed role; every other role → 403
  (a test per endpoint per role).
- **AC04** Agent link: under 3 characters the dropdown sends no request and the endpoint itself returns 422; ≤ 10 results; masked email; students already linked to the agency are
  absent; students linked to another agency still appear.
- **AC05** Bridge: a student can be searched only after a school is picked, and only within that school.
- **AC06** Keyboard-only use works (type, ↓/↑, Enter, Esc, Tab); screen-reader attributes are present; status changes are
  announced.
- **AC07** Server mode ignores stale replies (a slow reply for an older query never replaces a newer one).
- **AC08** Loading, empty, "type more", "keep typing", and failure-with-Retry states render.
- **AC09** No horizontal scroll at 320 px; usable at 375/768/1280.
- **AC10** Lookups log counts only (no search text) and write no audit rows.

## 8. Testing

- **Web (Vitest):** `SearchableSelect` behaviour (AC01, AC06–AC08), each converted form still submitting the same payload.
- **API (pytest):** per endpoint × role scope and cross-scope tests (AC03–AC05), `q` escaping, limits, masking, 422/403/404,
  log content (AC10).
- **E2E (Playwright):** existing specs that type raw IDs into these fields are updated to pick from the dropdown — the
  behaviour changed by decision (D1), recorded in the RTM, not edited to make a test pass; one new ENH-031 spec covering a
  load-once field, a server-search field, the agent link and the bridge.
- **Browser QA:** isolated browser at 375/768/1280, keyboard-only pass.

## 9. Traceability

Requirement (owner, 2026-09-29) → `DEC-SCOPE-037` D1–D5 → this spec AC01–AC10 → `API_CONTRACT.md` (lookups) →
`SCREEN_CATALOG.md` (changed forms) → tests (§8) → code → `RTM.md` ENH-031 row; `ENHANCEMENT_BACKLOG.md` ENH-031 entry.
