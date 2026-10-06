# bdm-018 — School onboarding handover + `schools` link (design)

- **Feature ID:** bdm-018 · **Decision:** `DEC-SCOPE-079` · **Migration:** `0080_bdm_onboarding` (after `0079_bdm_mous`)
- **Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-018 (`DERIVED_BLUEPRINT`); `DEC-SCOPE-055` D5, D8, Q-16 (D25); `DEC-SCOPE-071` S3; `DEC-SCOPE-078` M2.
- **Dependencies:** bdm-004 (COMPLETE), bdm-005 (merged to `main`, PR #77; its record says "VERIFIED — not yet COMPLETE": only Browser Use and the owner's full suites are open).

## 1. Owner answers (2026-10-06, in-session, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| H1 | How a School records its BDM | **Derived from the link.** No `schools.bdm_user_id` column. The School's BDM is the assigned BDM of the organization whose `school_id` points at it. A reassignment follows automatically. `SchoolOut` gains a read-only `linked_bdm`. |
| H2 | Live School stages 9–14 | **Per-step evidence** (§4). Each live step is `done` only on its own evidence; the first live step that isn't done is `current`. |
| H3 | Linking an existing School | **Through the request.** The BDM requests onboarding as usual. The admin resolves the request with *Create school* or *Link existing school* (by School ID). Admins never browse BDM organizations. |
| H4 | Legacy `schools.edusphere_bdm` (Q-16) | **Read-only in the UI.** The create panel drops the input. The edit panel shows it read-only as "Edusphere BDM (legacy note)". The API still accepts the field (backward compatible; ENH-029 bulk CSV unchanged). |

Defaults taken without a question (recorded in `DEC-SCOPE-079`):

- **H5** Who requests: the assigned BDM or `super_admin` (bdm-004 S1 / bdm-005 M3, i.e. `can_edit`). Managers read.
- **H6** Request preconditions: the organization is a School-module one (`bdm_type = 'school'`), not archived (409), not Lost (409 `organization_lost`), not already linked (409 `already_linked`), with no pending request (409 `request_pending`), and its current MoU reads Signed or Active (bdm-005 effective status, so an Expired one is refused; 422).
- **H7** Notices: in-app only (`channels=[]`, the bdm-010 travel precedent). The active `overseas_admin` users get "School onboarding requested". The organization's assigned BDM gets "School onboarded" or "School onboarding not approved", with the reason.
- **H8** After a rejection the BDM may request again (a new row). One pending request per organization, enforced by a partial unique index.
- **H9** No unlink in bdm-018. A wrong link is a follow-up (logged).
- **H10** What a BDM or manager sees of the School: its name and School ID plus the live step states. No counts and no School-portal data; per-school activity numbers belong to bdm-020.
- **H11** The pipeline view (counts by stored stage) is unchanged: an onboarded organization still counts under "Signed". Live stages are never stored (bdm-004).

## 2. Scope

**In:** the request table and link column; the BDM request route; the admin queue with reject / link / create; `POST /overseas-admin/schools` resolving a request in the same transaction; `SchoolOut.linked_bdm`; the live stages; the BDM onboarding card; the admin queue inside `AdminSchoolCreatePanel`; the linked BDM and the read-only legacy note in `AdminSchoolEditPanel`.

**Out:** Agent onboarding (bdm-019; the table's `kind` CHECK allows `'school'` only, and bdm-019 widens it); per-school counts (bdm-020); unlinking; deactivating the School's BDM (bdm-025).

## 3. Data — migration `0080_bdm_onboarding` (additive)

`bdm_onboarding_requests`

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| organization_id | uuid FK `bdm_organizations` RESTRICT | |
| kind | varchar(20) | CHECK `kind IN ('school')` |
| status | varchar(20) | CHECK `pending / completed / rejected` |
| note | varchar(1000) null | the BDM's note to the admin |
| requested_by_user_id | uuid FK users RESTRICT | |
| resolved_by_user_id | uuid FK users RESTRICT null | |
| resolved_at | timestamptz null | |
| resolution | varchar(20) null | CHECK `created / linked` |
| school_id | uuid FK schools RESTRICT null | |
| reject_reason | varchar(500) null | |
| created_at, updated_at | | TimestampMixin |

CHECKs: `(status = 'pending') = (resolved_at IS NULL)`; `status <> 'completed' OR (school_id IS NOT NULL AND resolution IS NOT NULL)`; `status <> 'rejected' OR reject_reason IS NOT NULL`. Indexes: `uq_bdm_onboarding_requests_pending (organization_id) WHERE status = 'pending'` (unique) and `ix_bdm_onboarding_requests_status (status, created_at)`.

`bdm_organizations.school_id` is a nullable uuid FK `schools.id` (RESTRICT) with unique constraint `uq_bdm_organizations_school`. No existing row is touched. The downgrade refuses while any request or link exists (the bdm-002/005 pattern).

## 4. Live School stages (H2)

`bdm_pipeline.live_status(db, org)` returns `None` when the organization has neither a pending request nor a link (steps stay "Awaiting handover", unchanged). Otherwise it returns `{step_key: bool}`:

| step | evidence (students = `school_students.school_id = linked school`) |
|---|---|
| school_onboarding | a link exists (pending request alone → not done, so it is `current`) |
| users_created | ≥1 `school_teacher` user of the school AND ≥1 parent link to its students AND ≥1 student |
| career_guidance | ≥1 `school_career_records` with `record_type='guidance_session'` AND `status='completed'` |
| psychometric | ≥1 `school_psychometric_records` with `status='completed'` |
| profile_building | ≥1 `portfolio_entries`, or a `portfolio_profiles` row with a personal statement |
| university_planning | ≥1 `overseas_applications` row bridged from one of its students (`school_student_id`) |

`pipeline_out(org, live)` works as follows when `live` is given. Manual steps up to and including the stored stage are `done`, and later manual steps are `upcoming`. Live steps are `done` from the evidence, the first live step that isn't done is `current`, and the rest are `upcoming`. `stage` and `stage_label` remain the stored manual stage. The queries are EXISTS checks on indexed FKs, at most six, and run on the detail view only.

## 5. API

All writes are one transaction with the audit row and in-app notice in it; logs carry ids and keys only. Lock order is always organization, then request, then school.

1. `POST /bdm/organizations/{id}/onboarding-request` `{note?: str ≤1000}` → 201 `{organization}`. Order: `load_scoped(lock)` 404 → `require(can_edit)` 403/409 → not school 422 → Lost 409 → linked 409 `already_linked` → pending 409 `request_pending` → MoU 422 "The MoU must be Signed or Active to request onboarding" → insert (IntegrityError on the pending index → 409 `request_pending`) → audit `bdm_organization.onboarding_requested` → notices to the overseas admins → commit.
2. `GET /overseas-admin/bdm-onboarding-requests?status=pending|completed|rejected&limit&offset` (`overseas_admin`, `super_admin`; else 403) → `{items,total,limit,offset}`, oldest first for pending and newest first otherwise. Each item has `id, status, note, created_at, resolved_at, resolution, reject_reason, requested_by{id,full_name}, assigned_bdm{id,full_name,active}`, an `organization` prefill (`id, code, name, city, state, address, phone, email, website, board, grade_from, grade_to`), `primary_contact{name,email,phone}|null`, `mou{reference, signed_on}|null` and `school{id,name,school_code}|null`.
3. `POST /overseas-admin/bdm-onboarding-requests/{id}/reject` `{reason: 1–500}` → 200 item. 404 unknown; 409 `request_resolved` when it isn't pending.
4. `POST /overseas-admin/bdm-onboarding-requests/{id}/link` `{school_code}` → 200 item. 404 unknown request; 409 `request_resolved`; 409 `already_linked` (the organization was linked meanwhile); 422 no School with that ID; 409 `school_linked` (the School is linked to another organization).
5. `POST /overseas-admin/schools` gains optional `bdm_onboarding_request_id`. The request is locked first, so 404 / 409 `request_resolved` / 409 `already_linked` arrive before anything is created. School + Coordinator + link + request completion commit together; any failure rolls all of it back. Without the field, behavior is byte-for-byte unchanged.
6. `SchoolOut.linked_bdm: {full_name, active, organization_code} | null` comes from one batched query in `_school_outs_batch`. It is returned only on overseas-admin routes, and School users never receive `SchoolOut`.
7. `BdmOrganizationOut.onboarding`: null unless `bdm_type = 'school'`; otherwise `{request: {id,status,created_at,resolved_at,reject_reason}|null (latest), school: {name, school_code}|null, can_request: bool}`.

Unchanged: `PATCH /overseas-admin/schools/{id}` (no `bdm_user_id`, H1), the stage-move route (live keys are still 422), the pipeline view, and every `/school/*` route. A test pins that a BDM calling `/school/*` gets 403.

## 6. Frontend

- `components/BdmOrganizationOnboarding.tsx` sits on both organization detail pages for school organizations, below the MoU card. It has four states: **Linked** (School name + ID), **Pending** ("Requested on …; waiting for Overseas Admin"), **Rejected** (the reason plus "Request again") and **None** (a "Request onboarding" button with an optional note when `can_request`, otherwise the hint "Available once the MoU is Signed or Active"). The manager view is read-only. A success re-renders from the returned organization; the MoU card's status changes re-read the organization so `can_request` stays fresh.
- `components/AdminSchoolOnboardingRequests.tsx`, rendered at the top of `AdminSchoolCreatePanel`, lists pending requests (loading, empty, error, and paging past 20 with "Show more"). Each request has three actions. **Use for new school** prefills the create form (name, city, state, address, phone, email, website, board, grades, MoU reference, partnership date = signed date, coordinator = primary contact) and sends `bdm_onboarding_request_id`. **Link existing school** takes a School ID. **Reject** asks for a reason.
- `AdminSchoolCreatePanel` drops the Edusphere BDM input (H4). `AdminSchoolEditPanel` shows "Linked BDM: name (ORG code)" or "Not linked", and the legacy note read-only; `edusphere_bdm` leaves its `FIELDS` list, so it is never sent.

## 7. Security

- Admin routes: `overseas_admin` / `super_admin` only, so a BDM or manager gets 403. BDM routes: `caller_scope` plus `can_edit`. Out of scope is 404 (no IDOR).
- The link widens nothing. A BDM gets no `/school/*` access (pinned by a test), and School roles never receive BDM data (`SchoolOut` is admin-only; nothing in the School portal reads the link).
- Inputs: lengths are capped by Pydantic and `school_code` is a plain equality lookup. React escapes all text.
- Audit: `bdm_organization.onboarding_requested`, `bdm_onboarding_request.rejected`, `.linked` and `.created` (ids, plus `school_id` when there is one).

## 8. Tests

Backend (`tests/test_bdm_018_*.py`): migration round trip and CHECKs; request rules and their order; queue scope and shape; reject / link / create, including atomic rollback and the races (two creates on one request, linking a School linked elsewhere); live-stage derivation per step; the `SchoolOut.linked_bdm` regression; BDM 403 on `/school/*` and on the admin routes. The SCH-003, ENH-009, ENH-023 and ENH-029 suites are rerun.

Web (vitest): the onboarding card's states and the request flow; the admin queue (loading, empty, error, prefill, reject, link); edit-panel linked BDM and legacy note; the create panel without the BDM input. Playwright: request → admin creates the School from the request → the organization shows Linked and "School Onboarding" done.

## 9. Risks

- `create_school` is shared with ENH-029 bulk. The new parameter lives only in the route, so `_provision_school` is untouched.
- `SchoolOut` consumers gain one field (additive). The edit panel type is updated.
- `organization_out` adds queries only for school organizations. Lists use `row_out`, which is unchanged.
