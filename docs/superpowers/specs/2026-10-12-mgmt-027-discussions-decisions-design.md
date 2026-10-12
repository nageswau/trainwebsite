# mgmt-027 — Management discussions & decisions — design

- **Feature:** `mgmt-027` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-027). Depends on mgmt-001 (PR #243) and mgmt-002 (PR #245),
  both merged on `main@69cfa6a5`.
- **Evidence:** `EVID-017` §27 (11 fields; the Japan example), Management M13/M14 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`), the mgmt-002
  audit helper (`DEC-SCOPE-187`, kind `mgmt.decision` already registered as operational).
- **Decision:** one new DEC-SCOPE (number taken at merge). MD1–MD14 below answer Q-26 and the item's open points with **recommended
  defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.

## 1. Intent

Partners (and the super admin, M13 operational tier) record each management discussion with its 11 §27 fields. When the discussion
ends in a decision with a responsible person, that person is notified and sees **only the decision line** (decision, deadline,
status, shareable attachments) in a shared "Management decisions" page, where they can update its status. Discussion notes, topic,
participants and follow-up stay management-only. mgmt-028 later folds these lines into the staff "Management tasks" list.

## 2. Decisions (MD1–MD14)

| # | Point | Answer |
|---|---|---|
| MD1 | Fields | topic (2–200, required), discussion date (required, IST day, not future, ≥ 2000-01-01), participants, department (optional free text 2–80), discussion points (optional, ≤ 10 000), decision (optional, 2–500), person responsible, deadline, status, attachments, follow-up date |
| MD2 | Participants (Q-26) | **Staff users only** (no free-text names), 0–30, each an active staff user (MD6). Stored as a link table; replaced as a whole on edit |
| MD3 | Department | Free text (no department model exists; mgmt-011's managed list is later) |
| MD4 | Status | `open` → `in_progress` → `completed`, plus `cancelled` (management only). Labels Open / In Progress / Completed / Cancelled. New discussions start `open` unless sent |
| MD5 | Decision rules | One decision per discussion (the §27 shape). A responsible person or deadline needs a decision (`422`). Deadline and follow-up date ≥ the discussion date (`422`) |
| MD6 | Responsible / participants | Any **active staff user** (M14). Staff = every internal role: super_admin, partner, accountant, it_admin, overseas_admin, trainer, placement_team, placement_manager, hr_team, counselor, academic_team, career_counselor, psychometric_team, bdm, bdm_manager, telecaller, telecaller_manager, partnership_manager, partnership_head. Students, parents, agents, university reps, employers and school-side users are refused. An inactive or non-staff user → `422` on the field |
| MD7 | Who writes | Operational tier (partner, super_admin) lists, reads, creates, edits, uploads/removes attachments. The accountant and every other role → `403`. No delete of a discussion (history) |
| MD8 | Assignee slice | `GET /me/management-decisions` lists the caller's decisions (not cancelled), with id, decision, deadline, status and shareable attachments only. `PATCH /me/management-decisions/{id} {status}` sets open / in_progress / completed. Anyone else's decision, or an unknown id → `404` (no existence leak); a cancelled one → `409` |
| MD9 | Notification | In-app + email (`queue_deliveries`, the ENH-014 outbox) to the responsible person when named or re-named, and when management changes the decision, deadline or status of their line ("decision changed after assignment"). The body carries only the decision line. No notification for the assignee's own status change. Link: `/account/management-decisions` |
| MD10 | Attachments (Q-26) | PDF / JPEG / PNG through `read_upload` (type by bytes, size cap, metadata stripped), at most 10 per discussion, each marked **shareable** or not (default not). Stored under `management-discussions/`. Management downloads any; the assignee downloads only shareable ones (`404` otherwise). Removing one deletes its row; the stored object is deleted after commit |
| MD11 | Audit | Kind `mgmt.decision` (operational → field names only, MA3). Verbs: `create`; `decide` when the decision text is set or changed; `complete` when the status becomes completed; `update` otherwise; `download` for an attachment. The assignee's status change is recorded with the assignee as actor |
| MD12 | List | Filters `status`, `responsible` (user id), `pending` (= a decision with a responsible person, open or in progress; ordered by deadline, earliest first, no deadline last); otherwise newest discussion date first. `limit` 1–100 (25), `offset` ≤ 10 000. The list page shows a "Pending decisions" panel (up to 10) above the list |
| MD13 | Concurrency | Every write locks the discussion row (`FOR UPDATE`) and commits once; an assignee status change racing a reassignment re-checks ownership after the lock (`404`) |
| MD14 | Visibility of notes | The assignee API serializer never includes topic, points, participants, department, follow-up or non-shareable attachments (AC3) |

## 3. Data (migration `0152_management_discussions`)

- `management_discussions`: id, topic, discussion_date, department, points, decision, responsible_user_id → users, deadline, status
  (CHECK), follow_up_date, created_by, updated_by, timestamps. CHECKs: status; `responsible_user_id IS NULL OR decision IS NOT NULL`.
  Indexes `(discussion_date)`, `(responsible_user_id, status)`, `(status, deadline)`.
- `management_discussion_participants`: (discussion_id → cascade, user_id → users) primary key.
- `management_discussion_attachments`: id, discussion_id → cascade, storage key, content type, name, shareable, uploaded_by, created_at.
- New tables only; downgrade refuses while any discussion exists.

## 4. Components

- `services/management_access.py`: `STAFF_ROLES` (MD6), shared with mgmt-028/029.
- `services/management_discussions.py` (owner): rules, serializers (management and assignee), notification, store/discard.
- `api/management_discussions.py`: `GET/POST /management/discussions`, `GET /management/discussions/options`,
  `GET/PATCH /management/discussions/{id}`, `POST /management/discussions/{id}/attachments`,
  `GET|DELETE /management/discussions/{id}/attachments/{aid}`; `me_router`: `GET /me/management-decisions`,
  `PATCH /me/management-decisions/{id}`, `GET /me/management-decisions/{id}/attachments/{aid}`.
- Web: `lib/managementDiscussions.ts`; pages `/management/discussions` (pending panel + list + status filter),
  `/management/discussions/new`, `/management/discussions/[id]`, `/management/discussions/[id]/edit`;
  `/account/management-decisions` (assignee, shared route like `/account/password`); components `DiscussionForm`,
  `DiscussionAttachments`, `MyManagementDecisions`. The Command Center's "Discussions & decisions" entry gets its `href`.

## 5. Error handling

`401` signed out; `403` outside the operational tier; `404` unknown discussion/attachment, or another user's decision on `/me`;
`409` a cancelled decision on `/me`, an 11th attachment; `413/415/422` uploads; `422` field rules (field-located). Pages show the
access card on 401/403 and "Discussions are unavailable right now" otherwise.

## 6. Testing

- Backend `tests/test_mgmt_027_discussions.py`: AC1 (Japan example stored, all 11 fields), AC2 (the partnership manager sees
  "Proceed with agreement — 10 Oct — In Progress" and updates it), AC3 (no topic/points/participants on `/me`), inactive responsible
  → 422, non-staff → 422, responsible without decision → 422, accountant/BDM 403 on management routes, another user's decision 404,
  cancelled 409, notifications on assign / change / reassign and none on the assignee's own update, audit verbs, attachments
  (shareable vs not, cap, delete), list filters + pending ordering, migration up/down.
- Web vitest: `managementDiscussions.test.ts`, `DiscussionForm.test.tsx`, `MyManagementDecisions.test.tsx`.
- Playwright `mgmt-027-discussions.spec.ts`: partner records the Japan example; the responsible user opens Management decisions,
  sees only the decision line and marks it completed.
