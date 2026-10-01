# AGN-007 — Agent Student University Shortlist and Agency University Database — Design

**Status:** Design approved in-session, 2026-10-01, section by section (§4 data model, §5 API, §6 frontend, §8
acceptance/tests/risks). The owner added pagination to the shortlist list. The design was then reviewed against the
`api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening` skills, and the owner approved the
amendments (§7), including the 500-universities-per-agency cap and the non-idempotent POST. No code has been written.

**Source requirement:** the user's `AGN-007` statement (2026-10-01): *"add university, course, country, intake, tuition
fee and entry requirements to a student's shortlist. University DB: Master "Full", Staff "View"; "Add University" is
Master only (§6; DEC-SCOPE-035 D4)."* The acceptance criteria it gives:
- a catalogue-backed entry and a free-text entry both save;
- a free-text entry is invisible to other agencies and to `/public`;
- a course must belong to the chosen university (the existing rule).

**Source sections** (`functionalities/edusphere_markdown/Agent CRM Functionalities.md`, `EVID-015`, `DERIVED_BLUEPRINT`, provenance `NEEDS_CONFIRMATION`):
- §5 "STEP 3 — University Shortlisting" ("Staff can add: University, Course, Country, Intake, Tuition fee, Entry requirements");
- §6 rows "University Database | ✅ Full | 👁️ View" and "Add University | ✅ | ❌".

**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → **`DEC-SCOPE-048`**, provisional.
- `DEC-SCOPE-047` is expected to go to the parallel AGN-006 (counseling) branch, so it is skipped. Whichever branch
  reaches `main` second renumbers, following the existing precedent. Recheck the next free number before the first docs
  commit.
- The `C-10` (`CONFLICT_MATRIX.md`) line for EVID-015 §5 Step 3 and the §6 University DB / Add University rows moves
  from parked to decided.

**Citation correction (recorded, not silently fixed):** the requirement cites `DEC-SCOPE-035 D4`.
- `DEC-SCOPE-035` is ENH-027's psychometric decision.
- `DEC-SCOPE-038` D4 is AGN-001's three-Master limit.
- Neither decides universities or shortlists. AGN-004 recorded the same kind of mis-citation (`DEC-SCOPE-042`).

**Supersedes in part:** `DEC-SCOPE-044` P3 (AGN-003), for the two §6 rows "University Database" and "Add University"
only. Every other P3 row is unchanged.

**Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §AGN-007 (to be added; AGN-007-AC01…AC14 = §8).

---

## 1. Owner decisions (in-session, 2026-10-01, `EXPLICIT_APPROVAL`)

| ID | Decision |
|---|---|
| D1 | "Add University" (Master only) creates an **agency-private** university. It never enters the shared `universities` / `overseas_courses` / `countries` tables and never appears on `/public`. |
| D2 | A shortlist belongs to an **`agent_students`** row (AGN-004): students with and without a login. |
| D3 | **Master and Staff** both add, edit and remove shortlist entries for students in their scope. "Staff: View" applies to the University Database, not to the shortlist. |
| D4 | The course rule: a catalogue course needs a catalogue university, and the course must belong to it (otherwise 422). A free-text course is allowed with either kind of university. An agency (free-text) university allows only a free-text course. |
| D5 | Shortlist writes are allowed for **every active** agency student, linked or not. An archived student's shortlist is read-only (409). |
| D6 | **Approach A:** a "free-text university" *is* an agency university. An entry's university is exactly one of a catalogue university or an agency university. Staff pick a university but cannot create one; there is no typed-only university on an entry. |
| D7 | Course, intake, tuition fee and entry requirements are optional on an entry; only the university is required. Country is derived from the university and never stored on the entry. Duplicate entries are allowed. |
| D8 | Caps: 50 entries per student and 500 agency universities per agency, checked under the agency lock (422 beyond). |
| D9 | The shortlist list is paginated (`limit`/`offset`, same envelope as the AGN-004 student list). |
| D10 | POST is not idempotent and is documented as unsafe to retry; the UI disables Save while in flight. There is no idempotency key and no ETag (neither is contracted). Concurrent PATCHes are last-write-wins under the agency lock. |

## 2. Scope

**In scope:**
- Agency universities: list for Master and Staff; create, edit and delete for Masters only.
- Per-student shortlist: list (paged), add, edit and remove.
- A new agent nav section, "Universities".
- The shortlist panel in the AGN-004 student detail view.
- Audit rows, plus the staff-activity whitelist entries for shortlist actions.
- A migration and the documentation set.

**Out of scope:**
- Agency-owned course catalogues.
- Admin course creation.
- Edits to the shared catalogue.
- Converting a shortlist entry into an application.
- Field names on shortlist edits in AGN-021 staff activity.
- The missing course-belongs-to-university check in `create_bridged_application` (`admin.py:1577`): logged separately in `RAID.md`, not changed here.
- A general hard-delete path for agency students.

## 3. Existing architecture reused (from the Graphify/codebase survey)

- `api/agent_students.py`: `_gate` (agents of an active agency; super_admin excluded), `_audit`, `_log`, `_locked_row`.
  These are imported; **the file is not edited** (AGN-006 edits it).
- `services/agent_students.py`: `load_scoped` (out-of-scope rows return 404 from the WHERE clause), `student_scope`, `_contains`
  (escaped `ilike`). Unchanged.
- `services/agent_orgs.py`: `lock_active_org` (the lock order every agency write uses).
- `core/rbac.py`: `is_agent_staff`. Unchanged.
- `schemas.py`: `clean_free_text` (strips NUL and bidi, blank becomes None, length limit), and the `extra="forbid"` pattern.
- `services/staff_activity.py`: `STAFF_ACTIVITY_ACTIONS` gets three new strings. The existing `agent_student` subject resolver names
  the student, so `_subjects` and `_fields` are unchanged.
- The existing course rule `workflows.py:1767-1771` and its message, "Course does not belong to selected university", are reused verbatim.
- Public catalogue reads `GET /public/universities` and `GET /public/universities/{slug}` (courses with `tuition_fee` and `intake`),
  used as-is by the frontend.

## 4. Data model — migration `0055_agent_shortlist` (provisional; `down_revision` = the real head at execution)

The migration only creates tables. No existing table, column or row changes. The downgrade drops only the two new tables, entries first.

### 4.1 `agent_universities`

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| org_id | UUID FK `agent_orgs.id` NOT NULL, indexed | the tenant key; every read filters on it |
| name | String(200) NOT NULL | |
| country | String(120) NOT NULL | free text |
| city | String(120) NULL | |
| entry_requirements | Text NULL | ≤ 2000 characters (schema) |
| created_by_user_id, updated_by_user_id | UUID FK `users.id` | |
| created_at, updated_at | TimestampMixin | |

- Unique index `uq_agent_universities_org_name_country` on `(org_id, lower(name), lower(country))`.

### 4.2 `agent_student_shortlist_entries`

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| agent_student_id | UUID FK `agent_students.id` NOT NULL | the scope is inherited from the student |
| university_id | UUID FK `universities.id` NULL | catalogue university |
| agent_university_id | UUID FK `agent_universities.id` NULL, indexed | agency university |
| course_id | UUID FK `overseas_courses.id` NULL | catalogue course |
| course_title | String(200) NULL | free-text course |
| intake | String(120) NULL | |
| tuition_fee | String(120) NULL | free text, matching `OverseasCourse.tuition_fee` |
| entry_requirements | Text NULL | ≤ 2000 |
| created_by_user_id, updated_by_user_id | UUID FK `users.id` | |
| created_at, updated_at | TimestampMixin | |

Constraints:
- `ck_shortlist_one_university`: `(university_id IS NULL) <> (agent_university_id IS NULL)`
- `ck_shortlist_catalogue_course`: `course_id IS NULL OR university_id IS NOT NULL`
- `ck_shortlist_one_course_form`: `course_id IS NULL OR course_title IS NULL`
- Index `ix_shortlist_student_created` on `(agent_student_id, created_at, id)`, which serves paging.
- All foreign keys are `ON DELETE RESTRICT`, so data is never cascade-deleted.

The rule "the course belongs to *that* university" needs a cross-table lookup, so the service enforces it (§5.4).

## 5. API

There is a new router module, `api/agent_shortlist.py` (registered in `main.py`), and a new service module, `services/agent_shortlist.py`.
- Service write functions never commit.
- The router does gate, lock, scoped load, validate, write, audit and commit once, as AGN-004 does.

Conventions follow the repo, not generic defaults:
- errors are FastAPI `{"detail": ...}`;
- fields are snake_case;
- 422 is used for validation.

### 5.1 Agency universities — `/api/v1/workflows/overseas/agent/crm/universities`

| Method and path | Master | Staff | Success |
|---|---|---|---|
| `GET ?q=&limit=20&offset=0` | ✅ | ✅ | 200 `{items,total,limit,offset}`, ordered `lower(name), id`; `q` searches name, country and city (escaped) |
| `POST` | ✅ | 403 "Only an agency Master can add universities" | 201 `{"university": …}` |
| `PATCH /{id}` | ✅ | 403 "Only an agency Master can edit universities" | 200 `{"university": …}` |
| `DELETE /{id}` | ✅ | 403 "Only an agency Master can delete universities" | 204 |

- `limit` is 1–100 and `offset` ≥ 0; a value out of range returns 422.
- The university is loaded with `id AND org_id = caller's agency`. Another agency's id returns 404.
- The role check runs **after** the scoped load, so a 404 never reveals that the row exists.
- Item shape: `{id, name, country, city, entry_requirements, created_at, updated_at}`.

Errors:
- 409 "This university is already in your agency's list" (same name and country, case-insensitive).
- 409 "This university is on N shortlist entries; remove it from them first" (delete while in use).
- 422 "Your agency has reached the limit of 500 universities".

### 5.2 Shortlist — `/api/v1/workflows/overseas/agent/crm/students/{student_id}/shortlist`

| Method and path | Master | Staff | Success |
|---|---|---|---|
| `GET ?limit=20&offset=0` | any agency student | assigned students only | 200 `{items,total,limit,offset}`, ordered `created_at, id` |
| `POST` | ✅ | ✅ | 201 `{"entry": …}` |
| `PATCH /{entry_id}` | ✅ | ✅ | 200 `{"entry": …}` |
| `DELETE /{entry_id}` | ✅ | ✅ | 204 |

- The student is loaded by `load_scoped`, so out of scope gives 404 "Student not found".
- The entry is loaded with `id AND agent_student_id = student.id`; anything else gives 404 "Shortlist entry not found".
- Writes on an archived student return 409 "Unarchive this student first". Reads still work.
- An offset past the end returns `items: []` with the true `total`.

Entry shape:
```
{id,
 university: {source: "catalogue"|"agency", id, name, slug (catalogue only, else null), country},
 course: {id (catalogue only, else null), title} | null,
 intake, tuition_fee, entry_requirements,
 created_by (full name), created_at, updated_at}
```
- For a catalogue university, `country` is `University.country.name`; for an agency university, it is `agent_universities.country`.

### 5.3 Request schemas (`schemas.py`, `extra="forbid"`, text through `clean_free_text`)

- `AgentUniversityCreate`: `name` (required, ≤200), `country` (required, ≤120), `city` (≤120), `entry_requirements` (≤2000).
- `AgentUniversityUpdate`: the same fields, all optional. Omitted means unchanged. Null clears `city` and `entry_requirements`. `name` and `country` cannot be cleared (422).
- `ShortlistEntryCreate`: `university_id` (UUID), `agent_university_id` (UUID), `course_id` (UUID), `course_title` (≤200), `intake` (≤120), `tuition_fee` (≤120), `entry_requirements` (≤2000).
- `ShortlistEntryUpdate`: the same fields, all optional. Omitted means unchanged; null clears.
- Server-owned fields (`org_id`, `agent_student_id`, `created_by_*`) are never accepted. `extra="forbid"` returns 422, which blocks mass assignment.

### 5.4 Validation order for an entry write (create, or PATCH after merging into the current row)

1. Exactly one of `university_id` / `agent_university_id`. Otherwise 422 "Choose a catalogue university or one of your agency's universities".
2. `university_id` must exist. Otherwise 422 "University not found".
3. `agent_university_id` must exist **and** have `org_id` equal to the caller's agency. Otherwise 422 "University not found": the same answer for another agency's id and a nonexistent id.
4. `course_id` and `course_title` together: 422 "Choose a catalogue course or type a course, not both".
5. `course_id` with an agency university: 422 "Catalogue courses can only be chosen with a catalogue university".
6. `course_id` must exist with `course.university_id == university_id`. Otherwise 422 "Course does not belong to selected university" (the existing message).
7. Create only: the student already has 50 entries. Then 422 "This student's shortlist is full (50 entries)".

On PATCH, the merged row is validated as a whole. A university change that leaves a stale `course_id` fails step 6 unless the course is sent too. A successful PATCH with no actual change returns 200 and writes no audit row (the AGN-004 convention).

### 5.5 Transactions and concurrency

Every write runs in this order:
1. `_gate`
2. `lock_active_org(org_id)`
3. scoped load(s) with `FOR UPDATE` (the student through `_locked_row`, the entry, the agency university)
4. validate
5. write
6. `_audit` (same transaction)
7. a single `commit`

The agency lock serialises:
- the per-student and per-agency caps (two adds at 49 entries end at 50);
- an add racing a delete of the agency university it references;
- duplicate agency-university names;
- archive racing a write.

The database backstops are the unique index and the RESTRICT foreign keys. An `IntegrityError` is mapped to the matching 409 and never surfaces as a 500.

### 5.6 Audit and staff activity

All entries are written in the same transaction and fail closed (SEC-001). They hold ids, field names and counts only, **never free-text values**.

| Action | entity_type / entity_id | metadata |
|---|---|---|
| `agent_student.shortlist_add` | `agent_student` / student id | `{entry_id, university_source, fields}` |
| `agent_student.shortlist_update` | `agent_student` / student id | `{entry_id, fields}` |
| `agent_student.shortlist_remove` | `agent_student` / student id | `{entry_id}` |
| `agent_university.create` / `.update` / `.delete` | `agent_university` / university id | `{fields}` (update) |

- The three `agent_student.shortlist_*` actions are added to `STAFF_ACTIVITY_ACTIONS`.
- The `agent_university.*` actions are Master-only and are not added.
- Structured logs (`_log`) carry the same ids only.

### 5.7 Portal section

`services/portal.py` `_agent` gets `if section == "universities"`, which returns a header-only `_payload("Universities", "Your agency's own universities. Browse the public catalogue for the rest.", (), ())`. This exists because `PortalPage` fetches `/portal/overseas/agent/{section}` for every nav section. No other portal branch changes.

## 6. Frontend

**Plan-time corrections (2026-10-01, while writing the implementation plan).** These follow the existing code more closely; the design intent is unchanged.
1. **Cards, not a table.** `AgentStudentsPanel` deliberately lists cards, as a `ul.grid.two` (its test asserts "cards, not a second table"). The shortlist and the agency university list do the same.
2. **A native `<select>` with `<optgroup>` ("Catalogue" / "Your agency") picks the university, not `SearchableSelect`.** `SearchableSelect`'s `Noun` type has no "university", so using it would mean editing a shared component. A native select is the precedent in `AgentApplicationCreatePanel`.
3. **The Universities page panel is mounted by `PortalPage`** (the Students precedent) rather than `WorkflowPanel`. A header-only payload rendered by `PortalSection` would show a misleading "No records yet". `WorkflowPanel` is untouched.

Where §6.1–§6.2 below say "table", `SearchableSelect` or `WorkflowPanel`, read them with these corrections.

**Reuse first:**
- existing classes: `card`, `btn`, `btn secondary small`, `form-error`;
- the table, paging ("Showing x–y of N", Previous/Next, step back when a page empties), confirm and stale-response (`current()`) patterns from `AgentStudentsPanel`;
- `SearchableSelect`, unchanged. If it has no option groups, agency options are labelled "<name> · Agency".

No shared component is edited, no new dependency is added and no new design tokens are introduced. Every component stays under 200 lines.

### 6.1 Shortlist (inside `AgentStudentDetailPanel`)

- `AgentStudentDetailPanel.tsx` gets one mount line, `<AgentShortlistPanel studentId={detail.id} archived={detail.status === "archived"} />`, below the facts and hidden while editing.
- **`AgentShortlistPanel.tsx`**
  - Heading `h5` "University shortlist".
  - A paged table of `AgentShortlistRow`s with columns University (an "Agency" text badge for agency universities), Country, Course, Intake, Tuition fee and Entry requirements (collapsed in `<details>`).
  - Each row has Edit and Remove buttons; neither is shown when the student is archived.
- **`AgentShortlistForm.tsx`**
  1. University: a `SearchableSelect` over the catalogue (`GET /public/universities`, fetched when the form first opens and cached while the panel is open) and the agency list (`GET …/crm/universities?limit=100`).
  2. Course:
     - catalogue university: a select of that university's courses (`GET /public/universities/{slug}`) plus "Other (type a course)", which reveals a text input;
     - agency university: a text input only;
     - changing the university resets the course.
  3. Intake, Tuition fee, Entry requirements: text inputs. Picking a catalogue course pre-fills them (course intake and tuition; `University.requirements` joined with newlines; an agency university's `entry_requirements`). A pre-fill **never overwrites a value the user typed**.
  4. Country: read-only text taken from the chosen university.
- **States:**
  - loading: an `aria-busy` placeholder; the previous page stays visible, dimmed, while paging;
  - empty: "No universities shortlisted yet." plus Add (if writable);
  - error: `role="alert"` with Retry;
  - saving: "Saving…", with buttons disabled while in flight.
- **Server errors:**
  - 422 shows the server's `detail` inline at the form;
  - 409 closes the form and refreshes the student;
  - 404 for the student shows "This student is no longer available";
  - 404 after the user's own delete counts as success.

### 6.2 University Database (`/overseas/agent/universities`)

- `lib/navigation.ts` adds `"universities"` to the `overseas/agent` list. It is not in `STAFF_HIDDEN`, so both roles see it.
- `WorkflowPanel.tsx` mounts `AgentUniversitiesPanel` for `user.role === "agent" && section === "universities"`, following the `showAgentTeam` pattern.
- **`AgentUniversitiesPanel.tsx`**
  - A search box and a paged list (name, country, city, entry requirements).
  - Masters get Add, Edit and Delete through `AgentUniversityForm.tsx`. The 409 in-use and duplicate messages show inline.
  - Staff see the same list read-only, with no buttons and no "you lack permission" notice.
  - A link, "Browse the university catalogue", goes to `/overseas/universities`.
  - Empty text: "Your agency hasn't added any universities yet." (Masters also get Add).

### 6.3 Shared client code

`lib/agentShortlist.ts` holds:
- the URLs;
- the types `ShortlistEntry`, `AgentUniversity` and `Page<T>`;
- `buildEntryPayload` and `buildUniversityPayload` (trim, blank becomes null, only changed fields on PATCH);
- client checks that mirror §5.3 and §5.4 steps 1, 4 and 5. The server remains the authority.

### 6.4 Accessibility and responsive behaviour

- Every input is labelled and every control is a native element.
- Focus moves to the form heading on open and returns to the Add or Edit button on close. A delete confirm puts focus on Cancel.
- Escape closes the innermost open thing first (form or confirm, then the detail view).
- Status messages are `aria-live`, and nothing relies on colour alone.
- The table follows `AgentStudentsPanel`'s responsive behaviour. Form inputs are full-width in a single column below 640 px.
- Verified at 320, 375, 768 and 1024 px.

## 7. Review amendments (approved 2026-10-01)

**API** (`api-and-interface-design`):
- A1: the repo's error and naming conventions win over the skill's generic defaults.
- A2: envelopes and status codes as in §5.
- A3: merge-then-validate PATCH.
- A4: D10 (no idempotency key, no ETag).
- A5: a repeated DELETE returns 404, and the UI treats it as success.
- A6: boundary validation.
- A7: indexes, RESTRICT foreign keys, escaped search.
- A8: purely additive.

**Frontend** (`frontend-ui-engineering`): F1–F7 as in §6 (reuse, component split, lazy catalogue, hierarchy, focus, mobile, states).

**Security** (`security-and-hardening`):

| Area | Control |
|---|---|
| Authentication | unchanged (`get_current_user`, httpOnly SameSite=Lax cookie, AGN-002 session version) |
| CSRF | JSON-only bodies, CORS limited to `settings.frontend_url`, SameSite=Lax; nothing new |
| IDOR | each client-supplied id is scoped in the WHERE clause: `student_id` (`load_scoped`), `entry_id`+`agent_student_id`, `agent_university_id`+`org_id`, and catalogue ids existence-checked; each has a cross-agency and a cross-staff test |
| Role escalation | Master-only is decided from the server-side membership (`is_agent_staff`); deactivated members and suspended agencies are refused by `_gate` |
| Input, XSS, SQL injection | `clean_free_text`; React text only (no `dangerouslySetInnerHTML`; `white-space: pre-line`); ORM and escaped `ilike` |
| Information disclosure | another agency's university id gets the same 422 as a nonexistent one; messages never contain another agency's data |
| Logs and audit | ids, field names and counts only; same transaction; fail closed |
| Denial of service | caps D8 under the agency lock, plus length limits; no new rate limiter (an ask-first change, not needed) |
| Secrets and privacy | nothing new; shortlist rows follow the AGN-004 record lifecycle |

## 8. Acceptance criteria

| ID | Criterion | Proved by |
|---|---|---|
| AC01 | A catalogue-backed entry (catalogue university, its catalogue course, intake, fee, requirements) saves: 201; GET shows `source:"catalogue"` and the catalogue country. | `test_agn_007_shortlist.py`, e2e |
| AC02 | A free-text entry (agency university, typed course) saves: 201; `source:"agency"`; the country comes from the agency university. | `test_agn_007_shortlist.py`, e2e |
| AC03 | A course from another university returns 422 "Course does not belong to selected university". A catalogue course with an agency university, both or neither university, or both course forms each return 422. Nothing is written in any of these cases. The migration test proves the CHECK constraints at database level. | `test_agn_007_shortlist.py`, `test_agn_007_migration.py` |
| AC04 | Invisible to other agencies: another agency's university id in a body returns 422; its university by id returns 404, and it is absent from the list; another agency's student shortlist returns 404. | `test_agn_007_isolation.py` |
| AC05 | Invisible to `/public`: `/public/universities`, `/public/universities/{slug}`, `/public/countries/{slug}` and `/public/overseas-courses` are unchanged after agency universities and entries are created. | `test_agn_007_isolation.py`, e2e |
| AC06 | University DB: Master and Staff can GET the list. Staff POST, PATCH and DELETE return 403, with no row and no audit row. Masters succeed, and each write is audited. | `test_agn_007_universities.py`, `test_agn_003_matrix.py` |
| AC07 | Shortlist scope: Staff can do all four operations for assigned students; any other student returns 404 (before any role check). Masters can do so for any agency student. | `test_agn_007_shortlist.py` |
| AC08 | An archived student's shortlist is readable, and writes return 409. A linked (login) student is writable. | `test_agn_007_shortlist.py` |
| AC09 | Deleting an agency university that is in use returns 409, and nothing is lost. A duplicate name and country in the same agency returns 409; the same name in another agency is allowed. | `test_agn_007_universities.py` |
| AC10 | Caps: the 51st entry and the 501st university return 422. Two concurrent adds at 49 entries end at exactly 50. | `test_agn_007_concurrency.py` |
| AC11 | Pagination: the envelope; stable order; 422 for out-of-range values; an offset past the end returns empty items with the true total. | `test_agn_007_shortlist.py`, `test_agn_007_universities.py` |
| AC12 | Each write produces exactly one audit row in the same transaction, with no free-text values. Shortlist actions appear in AGN-021 staff activity; agency-university actions do not. | `test_agn_007_audit.py` |
| AC13 | UI: Master and Staff add a catalogue entry and an agency entry from the detail view. Staff see no write controls in the University Database. Loading, empty and error-with-Retry states render. Keyboard-only use works, and the layout works at 375 px. | vitest, `agn-007-shortlist.spec.ts` |
| AC14 | Regression: the AGN-001/003/004/005/021, OVS-001/002 and public catalogue suites pass. The only existing test edited is the AGN-003 matrix rows for University DB and Add University. | lite backend set, vitest, e2e |

## 9. Tests (written before the code they cover)

**Backend** (`apps/api/tests/`; helpers reuse `agn004_helpers.py`):
- `test_agn_007_universities.py`
- `test_agn_007_shortlist.py`
- `test_agn_007_isolation.py`
- `test_agn_007_concurrency.py`
- `test_agn_007_audit.py`
- `test_agn_007_migration.py`
- the edited rows in `test_agn_003_matrix.py`

**Vitest:**
- `AgentShortlistPanel.test.tsx`
- `AgentShortlistForm.test.tsx`
- `AgentUniversitiesPanel.test.tsx`
- `agentShortlist.test.ts`
- `navigation.agent.test.ts` (the new item, visible to both roles)

**Playwright:** `agn-007-shortlist.spec.ts`. The flow:
1. A Master adds an agency university.
2. Staff shortlist a catalogue entry and an agency entry.
3. The public universities page does not show the agency university.
4. The layout is checked at the 375 px viewport.

**Execution:** real runs only. Run the lite backend set (`test_agn_*`, `test_ovs_001*`, `test_ovs_002*`, `test_pub_*`), vitest, and the AGN-007 e2e spec. The owner runs the full backend suite on their own cadence.

## 10. Regression risks

| Risk | Mitigation |
|---|---|
| Merge collision with AGN-006 (DEC number, migration number, `STAFF_ACTIVITY_ACTIONS`, `AgentStudentDetailPanel`) | `agent_students.py` is not edited; the detail panel gets one mount line; recheck `main` and renumber before execution |
| A leak into the public catalogue | the catalogue tables and `public.py` are untouched; AC05 asserts it |
| AGN-004 scope or contract drift | `load_scoped` and `student_scope` are reused unchanged; the detail GET is untouched |
| The AGN-003 matrix test | the row change is deliberate and recorded as superseding `DEC-SCOPE-044` P3 for those two rows |
| The new nav section breaking the agent portal | the portal branch, plus navigation and e2e tests |
| The migration chain | `down_revision` is set to the real head at execution; a migration test does upgrade, downgrade, upgrade |

## 11. Documentation to update (AGN convention)

- `ENHANCEMENT_BACKLOG.md` §AGN-007
- `PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-048`
- `CONFLICT_MATRIX.md` C-10
- `API_CONTRACT.md` §8
- `DATA_MODEL.md` §6.8d
- `RBAC_MATRIX.md` §2.8 (University DB / Add University rows)
- `SECURITY_CONTROLS.md`
- `THREAT_MODEL.md`
- `SCREEN_CATALOG.md` + `screen_catalog.json` (SCR-AGT-008 update + new SCR-AGT-009 Universities, provisional)
- `ROLE_NAVIGATION.md`
- `RAID.md` (the bridge course-check gap)
- `docs/quality/RTM.md`
- a browser QA record
