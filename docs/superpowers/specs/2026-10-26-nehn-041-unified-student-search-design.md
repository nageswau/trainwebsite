# nehn-041 — Unified admin/operations student search (design + plan)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-041` (PDF §23 L588-597, action 22; the PDF and backlog are
`UNVERIFIED`). **Decision:** `DEC-SCOPE-291` (builder's defaults; owner pre-authorised recommended answers, `NEEDS_CONFIRMATION`).
**Dependency:** nehn-040 (`DEC-SCOPE-280`, PR #346) — merged; every student kind now has a searchable Student ID.

## Intent

An admin hears a Student ID, a phone number in any format, a name or a course, and opens that student in one click — whichever kind of
student it is (IT, overseas, an agency's student with no login, a school's student). Nobody ever finds a student they could not already
see on their own lists.

## Builder's calls (`NEEDS_CONFIRMATION`)

| # | Call |
|---|---|
| S1 | **Who / what** (the existing scope functions, nothing new): Super Admin — all four kinds. IT Admin — IT students. Overseas Admin — overseas students + agency students with no login. Overseas counselor — overseas students they may see (`counselor_students.visible_student_ids`, csc-001). Agent — their agency's students (`agent_students.student_scope`: a staff member only the ones assigned to them; a linked student appears as an overseas student, a no-login one as an agency student). Everyone else **403**: an IT counselor (no student caseload, tel-017), the telecaller manager (no student scope — leads are out, S2), school roles (they keep the coordinator list search; per-teacher/parent scopes are not reproduced here). |
| S2 | **Leads are not included.** The open question stays open; ccrm-012 already gives the overseas counselor a leads+students box. |
| S3 | **One card per record.** The same person as an IT and an overseas student holds two accounts, so two cards. A linked agency row is shown once (its account). |
| S4 | **Matching:** `q` trimmed, 3-100 characters (422 otherwise — so a 1-character query is 422), the ccrm-012 rule. Literal, case-insensitive substring of name, email and Student ID; a phone-shaped `q` (digits, spaces, `+ - ( ) .`, ≥ 3 digits) also matches the phone's digits whatever its separators, last 10 digits when longer (ccrm-012/tel-018 rule). **Course:** an IT student also matches by the title of a program they are enrolled in; an overseas student by the course title of any of their applications. **Agency:** an agency student also matches by the agency's name or prefix (the agency code; no Agent ID — `DEC-DATA-003`). A school student also matches by the school's name. Diacritics are not folded (`unaccent` is not installed) — known limit. |
| S5 | **Filters:** `type` (`it_student`, `overseas_student`, `agency_student`, `school_student` — the backlog's "role"), `division` (`it` → IT students; `overseas` → overseas + agency; `school` → school), `program` (an IT program id → IT students enrolled in it). A filter outside the caller's kinds simply returns no group; a bad value is 422. |
| S6 | **Result:** `{q, groups: {<kind>: {items (≤ 20), more}}}` with only the caller's kinds (after filters). Item `{id, code, label, detail, href}`; `detail` joins email, phone and context (programs / school / agency); `href` is the page that already exists for that caller, or `null` when there is none (a school student for the Super Admin). |
| S7 | **Deep links:** IT student → `/admin/users?q=<ID>` (Super Admin) or `/it/admin/students?q=<ID>` (IT Admin; the users panel now takes its search from `?q=`). Overseas student → `/admin/users?q=<ID>` (Super Admin; the student 360 is Overseas Admin/counselor only), `/overseas/admin/students/<id>`, `/overseas/counselor/students/<id>`, `/overseas/agent/students`. Agency student → `/overseas/admin/agent-network/<orgId>` (admins), `/overseas/agent/students` (agent). |
| S8 | **Abuse controls:** 30 searches a minute per user (429 + `Retry-After`), counted from audit rows `student.search`, one per search, holding result counts only — never the search text (the ccrm-012/lookups precedent). |
| S9 | **Performance / migration:** no migration. Scoped callers read bounded sets; admins scan `users` / `agent_students` / `school_students` with `ILIKE`, measured on the stack against the 300 ms target. `pg_trgm` is not added (not in the project; managed PG support is `NEEDS_CONFIRMATION`) unless the measurement fails. |
| S10 | **UI:** a "Student search" page for the three admin portals (`/admin/student-search`, `/it/admin/student-search`, `/overseas/admin/student-search`, server-rendered from the address — `?q=&type=&program=`), a nav entry, and a header search box in the portal top bar on every page whose nav has that entry. Counselor and agent keep their own search UIs (ccrm-012, AGN-004); they get the API only. |

## Changes

- **API:** `GET /api/v1/search/students` (new; §12GP). `services/student_search.py` (scopes per kind, reusing `counselor_search.term`,
  `_digits_pattern`, `_matches` and its rate-limit counter, now taking the audit action).
- **Web:** `lib/studentSearch.ts` (types, URL builder, filter parsing), `components/StudentSearchPage.tsx` (server), three page files,
  `navigation.ts` (entries), `PortalShell` header box, `AdminUserManagementPanel` initial `?q=`.
- **Docs:** register `DEC-SCOPE-291`, API §12GP, RBAC §2.202, RTM, backlog status, feedback tracker.

## Plan (TDD, one slice at a time)

1. Service + route, scope per role (RED: tests for 403 roles, 422 short query, scoped results for counselor/agent, admin kinds).
2. Matching: phone any format, Student ID, course (IT program, overseas application course), agency name/prefix, school name.
3. Filters `type` / `division` / `program`, 422 on bad values; group cap 20 + `more`; audit row + 429.
4. Web lib + page component (vitest), nav + header box, users panel `?q=` (vitest).
5. Stack: e2e `nehn-041-student-search.spec.ts`, browser QA, timing at volume.
6. Docs.

## Acceptance criteria

| AC | Criterion |
|---|---|
| AC1 | A phone in any format (`+91 98765-43210`, `098765 43210`, `9876543210`) finds the student. |
| AC2 | A course name returns that course's enrolled IT students (and overseas students who applied to it). |
| AC3 | A counselor finds only students they may see; an agent only their own agency's (staff: assigned only); an IT Admin only IT students. |
| AC4 | Response under 300 ms at the expected volume (measured on the stack). |
| AC5 | A 1-character (or 2-character) query is 422; a non-admin/ops role is 403. |
| AC6 | Each result opens the student in one click where a page exists for the caller. |
| AC7 | Every search is audited without the search text; the 31st in a minute is 429. |

## Evidence (2026-10-26, isolated stack)

- **AC4:** 20,709 users (20,000 synthetic `it_student`/`overseas_student`), 5,161 agency rows, 5,045 school students. Super Admin (every
  kind, full scans): name 0.10-0.22 s, phone 0.13-0.16 s, Student ID 0.07-0.08 s, course 0.08-0.09 s, no match 0.08-0.10 s, broad
  `Perf` 0.07 s; counselor 0.02-0.03 s — HTTP round trip included, all under 300 ms, so no index/`pg_trgm` migration (S9).
- **Browser QA:** QA-041-01 (card names did not look like links) and QA-041-02 (the `/admin/users?q=` link opened with the searched
  panel below the page's generic table) fixed; no console errors, failed calls or horizontal scroll at 375/768/1024/1280 px.

## Regression risks

`PortalShell` (every portal page; the top bar must still fit 320 px), `navigation.ts` nav tests, `AdminUserManagementPanel` (the
initial `?q=` must not change its behaviour without one), `counselor_search` (its rate-limit helper gains a parameter).
