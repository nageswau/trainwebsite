# upc-030 — University 360 view for other roles — design

- **Feature:** upc-030 (`docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-030; decision U14, U13, U2; EVID-020 closing note
  L1102–L1127 and §16 L579)
- **Decision:** `DEC-SCOPE-161`. **No migration.** API §12CC; RBAC §2.87. These numbers are provisional until merge, as with earlier items.
- **Branch:** `feature/upc-030` from `origin/main` @ `89ac6147`.
- **Dependencies (all merged):** upc-003 (University Master), upc-006 (contacts + `shareable`), upc-016 (commission terms, U2 roles),
  upc-017 (course master + `strip_commission`), upc-026 (documents + `shareable`).
- **Evidence:**
  - U14 (`EXPLICIT_APPROVAL`, 2026-10-08): the role slices.
  - U13: BDMs see the master record read-only, with no commission.
  - U2: commission is restricted to `super_admin` and the partnership roles.
- **Status of answers:** the owner told this session to proceed with the recommended answers. UV1–UV12 below are those recommendations.
  They are `NEEDS_CONFIRMATION` at sign-off, not `EXPLICIT_APPROVAL`.

## 1. Understanding

One university record, and each role sees only what is relevant to it (closing note). Counselors must "know exactly what each partner
university offers" (§16): its profile, its partnership status, who to contact for applications, its courses with entry and English
requirements, its shareable documents, and their own students' applications there.

- A BDM sees the profile, the partnership stage and the managing partnership manager (U13).
- A university representative sees their own university's profile and courses.
- **No slice ever carries commission data.**

The slicing is the confidentiality boundary (backlog: security impact **high**). Each slice is therefore built from an explicit
allow-list per role. It is never the master payload with fields removed.

## 2. Recommendations (UV1–UV12)

| # | Question | Recommended answer (used) |
|---|---|---|
| UV1 | Endpoint | `GET /api/v1/universities/{id}/view`: one route with a role-sliced serializer (backlog). A new router `app/api/university_view.py`, outside `/partnership` (these are not partnership roles). |
| UV2 | Who | `counselor` (overseas division), `overseas_admin` (overseas division), `bdm` and `bdm_manager` (any division), `university_rep`. Every other role, including the partnership roles and super_admin (they have the full master), → `403 "University view access required"`. An IT-division counselor → 403. |
| UV3 | Which universities | **Counselor:** published (`catalogue_visible`) **and** active only. Any other id → 404, so an internal target university is indistinguishable from an unknown one (backlog edge case: "counselors see it? design: no"). **overseas_admin:** every university (already a master reader). **BDM:** every university (U13: their org links to any master row, prospects included). **university_rep:** only `profile["university_id"]`; any other id, or no linked university → 404 (`UNI-001-AC02`). |
| UV4 | Profile (every slice) | `id, university_code, name, institution_type, ownership_type, country{name, iso2, region}, state_region, city, website, overview, eligibility, course_levels, popular_programs, rankings[{system, other_name, year, rank}]`. **Never:** `international_office`, `existing_relationship`, priority, potential, relationship strength, catalogue/active flags, managers (except UV6), expected dates, follow-ups, pipeline internals, linked BDM orgs, permissions. |
| UV5 | Partnership status (counselor, overseas_admin, BDM) | `partnership: {stage, stage_label, lost}`. |
| UV6 | Manager (BDM only, U13) | `manager: {full_name, email}` of the primary partnership manager, else null. |
| UV7 | Contacts (counselor, overseas_admin) | `shareable` contacts only (the upc-006 CT5 slice), primary first, then by name: `id, name, designation, department, role{code,label}, email, phone, whatsapp, linkedin, preferred_channel, is_primary`. **Never** notes, relationship strength, last interaction or the `shareable` flag. Capped at 50. |
| UV8 | Courses (counselor, overseas_admin, university_rep) | **Active** courses only, by title then level, capped at 200: `id, title, level, category, duration, tuition_fee, tuition_amount, tuition_currency, application_fee, application_fee_currency, intakes, intake, entry_requirements, english_test, english_score, scholarships[{id,title,amount}], application_process, deadline`. No commission (and no `permissions`). The listed keys are built by `university_courses.course_out` → `strip_commission`, then allow-listed. |
| UV9 | Documents (counselor, overseas_admin) | `university_documents.visibility(user)` (shareable and never `commission_agreement`): `id, kind, title, current_version, updated_at`. Download: `GET /universities/{id}/view/documents/{document_id}/file`, with the same access rules (UV2/UV3). It serves the current version, is audited before any byte leaves (upc-026 DC10) and uses the server-built file name. A hidden document → 404. The existing `/partnership/.../documents` routes are unchanged (counselor still 403 there). |
| UV10 | Applications (counselor, overseas_admin) | Counselor: their own (`counselor_id = me`). overseas_admin: all, for this university. Newest-updated first, capped at 50, School-bridged excluded (`with_owner`): `id, reference, student_name, intake, status, next_action, updated_at`. |
| UV11 | Response shape | `{"slice": "counselor"\|"overseas_admin"\|"bdm"\|"university_rep", "university": {…UV4}, …sections}`. A section the slice does not include is **absent** (not null), so the per-role snapshot tests pin the exact key set. |
| UV12 | Audit / logs | Reads are not audited (as with the other partnership reads). A refused read is logged with ids and role only. A document download is audited (`university_document.download`, role in metadata). |

## 3. Data

No schema change. The view reads `universities`, `countries`, `university_rankings`, `users`, `university_contacts`,
`university_contact_roles`, `overseas_courses`, `scholarships`, `university_documents`, `overseas_applications` and the owners.

## 4. API (`app/api/university_view.py`)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/universities/{id}/view` | UV2 roles, UV3 scope | `UniversityView` (UV11) |
| GET | `/universities/{id}/view/documents/{document_id}/file` | counselor, overseas_admin (UV9) | The file (attachment) |

**Errors:**
- 401 when signed out.
- 403 for a role outside UV2, or the wrong division.
- 404 for an unknown or out-of-scope university, or a hidden or unknown document.

BDMs and university_reps → 403 on the download (their slices have no documents).

**Query count** is constant: university + country + rankings, plus one query per included section.

## 5. Frontend

The backlog asks for one component reused across portals with role props. `components/UniversityView.tsx` is a server component that
is **data-only**. It renders the sections present in the payload, which gives one look for every portal.

| Role | Page | Entry point |
|---|---|---|
| counselor | `/overseas/counselor/universities` (search over the public catalogue list `GET /public/universities?q=`, which is exactly the counselor's UV3 set) and `/overseas/counselor/universities/[id]` | New "Universities" nav item |
| BDM / bdm_manager | `/bdm/universities/[id]` | The BDM organisation's "University Master" row becomes a link |
| university_rep | `/overseas/university/profile` (static segment; reads `profile.university_id` from `/auth/me`) | New "University Profile" nav item |
| overseas_admin | Unchanged: already reads the master detail page, which is a superset of the slice except applications. The API serves the slice. | — |

**States:**
- Signed out → login.
- Refused or 404 → the `AccessUnavailable` card.
- A rep with no linked university → "Your account is not linked to a university yet. Contact EduSphere Overseas Admin."
- An empty section → a short muted sentence ("No shareable contacts yet.").

## 6. Acceptance criteria

| # | Criterion | Proof |
|---|---|---|
| AC1 | Each slice returns exactly its key set (university keys and top-level keys) | pytest snapshot per role |
| AC2 | No `commission` key at any depth, for any slice, even when a course has commission and a commission agreement exists | pytest recursive scan |
| AC3 | Counselor sees only shareable contacts (no notes), shareable non-commission documents, active courses, and only their own applications | pytest |
| AC4 | A counselor reading an unpublished or inactive university → 404 | pytest |
| AC5 | The university_rep of X reading Y → 404; their own → 200 with profile + courses only | pytest |
| AC6 | Roles outside UV2 (student, agent, IT counselor, partnership_manager, super_admin) → 403; signed out → 401 | pytest |
| AC7 | Document download: a counselor downloads a shareable document (audited); hidden or commission → 404; a BDM → 403 | pytest |
| AC8 | Pages render the slice for counselor, BDM and rep; IELTS requirements are visible to a counselor (positive scenario) | vitest + Playwright |

## 7. Regression risks

- UNI-001 rep portal: `[section]` routes keep working. The new `profile` segment is static.
- Navigation exact-list tests (counselor, university nav).
- The upc-026 test pins counselor → 403 on the partnership documents routes; those routes are untouched.
