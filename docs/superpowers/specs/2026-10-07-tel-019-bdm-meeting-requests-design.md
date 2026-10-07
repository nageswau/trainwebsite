# tel-019 — BDM meeting requests (design)

**Status:** approved in session 2026-10-07. Owner answers MR1–MR4 are `EXPLICIT_APPROVAL`; MR5–MR14 are defaults recorded in
`DEC-SCOPE-097`. **Evidence:** `EVID-019` §9 (L332–L384, BDM meeting types L346–L354); backlog `docs/delivery/TELECALLER_CRM_BACKLOG.md`
tel-019; T10 (the telecaller files a meeting request, the BDM accepts it into `bdm_appointments`), T26 (corporate → college BDMs).
**Dependencies (both merged):** tel-008 (lead workspace / telecaller portal), bdm-006 (`bdm_appointments`).
**Numbers (re-check at merge):** migration `0093_bdm_meeting_requests` chained after main's `0091_lead_appointments` (tel-010, pushed but
unmerged, holds `0092` / `DEC-SCOPE-096` / §12R / RBAC 2.24; whichever merges second re-chains), `DEC-SCOPE-097`, API §12S, RBAC §2.25.

## 1. Owner answers (2026-10-07)

| # | Question | Answer |
|---|---|---|
| MR1 | Q-13 routing | The telecaller **may name an active BDM of the type**. Left blank, the request goes to the **pool**: every active BDM of that type sees it and the first to accept takes it. No manager triage |
| MR2 | Decline | A reason is required (AC3). A decline is **final**; the telecaller files a new request if needed |
| MR3 | Read-only viewers | `bdm_manager`: requests for their team plus open pool requests. `super_admin`: all. No telecaller-manager view in this item |
| MR4 | Withdraw | **No.** Statuses are `pending` / `accepted` / `declined` only |

Defaults:
- **MR5 (T26):** request type → BDM type: `college` → college, `agent` → agent, `school` → school, `corporate` → **college**.
- **MR6:** code `MRQ-000001` from `bdm_meeting_request_code_seq` (gaps after rollback accepted; unique constraint is the backstop).
- **MR7:** fields — organization name (≤ 200, required), person (≤ 200, required), phone (required; 7–30 characters of digits, spaces,
  `+ - ( )`), email (optional; a valid address, blank = none), proposed date/time (required; future, within 366 days), mode (`Online` / `Phone` / `In person`, required),
  meeting link or location (≤ 255, optional), purpose (≤ 1000, required), remarks (≤ 2000, optional), target BDM (optional).
- **MR8:** a named BDM must be an active `bdm` user whose profile type matches the request's BDM type (422 otherwise).
- **MR9:** accept takes the bdm-006 create body (organization assigned to the BDM, its contact, start, duration, type, optional
  fields, trip, `confirm_overlap`) and applies **every bdm-006 rule unchanged** (archived 422, not assigned 403, foreign contact 422, type
  for the BDM's module 422, future 422, overlap warning 409). The UI prefills the start from the proposed time, the type from the request
  type (`college_meeting` / `agent_meeting` / `school_meeting` / `corporate_meeting`), and location / purpose / remarks from the request.
  A request accepted after its proposed time simply needs a new (future) start — the BDM picks it (backlog edge case).
- **MR10:** the organization must already exist; the accept form links to the BDM's Organizations page to create one (bdm-002, which
  requires a contact). No inline organization creation.
- **MR11:** BDM visibility: their type's **pool** (unassigned, pending) plus requests **assigned to them** (named, or taken by them).
  Once someone else takes a pool request it disappears for the rest (404).
- **MR12:** `bdm_manager` and `super_admin` cannot accept or decline (403). A telecaller sees only their own requests.
- **MR13:** no notifications here (tel-020 owns alerts). A request named for a BDM later deactivated stays pending; the telecaller
  files a new one (recorded as a follow-up for tel-025 / bdm deactivation).
- **MR14:** nothing links a request to a lead (the backlog's field list has none).

## 2. Data (migration 0093)

New table `bdm_meeting_requests`:
- `id` UUID PK; `code` String(20) unique.
- `requester_user_id` → `users.id` (RESTRICT).
- `request_type` String(20) CHECK in (`college`,`agent`,`school`,`corporate`); `bdm_type` String(20) CHECK in (`agent`,`school`,`college`)
  — derived on create (MR5), stored so the scope filter is one indexed column.
- `organization_name` (200), `person_name` (200), `contact_phone` (30), `contact_email` (255 NULL).
- `proposed_at` timestamptz; `mode` String(20) CHECK in the modes; `location` (255 NULL); `purpose` (1000); `remarks` (2000 NULL).
- `status` String(20) default `pending`, CHECK in (`pending`,`accepted`,`declined`).
- `bdm_user_id` → `users.id` NULL (named target or the taker); `bdm_appointment_id` → `bdm_appointments.id` NULL, unique (RESTRICT).
- `decline_reason` (500 NULL); `decided_at` timestamptz NULL; `created_at`, `updated_at`.

CHECKs: `(status = 'accepted') = (bdm_appointment_id IS NOT NULL)`; `(status = 'declined') = (decline_reason IS NOT NULL)`;
`status = 'pending' OR (bdm_user_id IS NOT NULL AND decided_at IS NOT NULL)`.
Indexes: `(bdm_type, status)`, `(bdm_user_id)`, `(requester_user_id, created_at)`.

The upgrade is guarded (0001 builds from current models, the 0074/0091 idiom). A new table touches no existing row. Downgrade refuses
(`RuntimeError`) while requests exist.

## 3. API (§12S)

Every write is one transaction; lock order is **request → organization → appointment** (the bdm-006 order after the request). Out of
scope = 404; a role that may not act = 403.

| Route | Who | Behaviour |
|---|---|---|
| `GET /telecaller/meeting-requests/options` | `telecaller` | `{types:[{key,label,bdm_type}], bdms:{college:[{id,full_name}],agent:[…],school:[…]}, modes}` — active BDMs by name |
| `POST /telecaller/meeting-requests` | `telecaller` | Body per MR7 (`bdm_user_id` optional). 422 on validation / bad target. 201 with the request. Audit `bdm_meeting_request.create` |
| `GET /telecaller/meeting-requests?status=&limit=&offset=` | `telecaller` | Their own, newest first |
| `GET /bdm/meeting-requests?status=&limit=&offset=` | `bdm` / `bdm_manager` / `super_admin` | Scope per MR3/MR11; pending first (soonest proposed first), then decided (latest decision first) |
| `GET /bdm/meeting-requests/{id}` | same | One request, with `permissions {can_accept, can_decline}` |
| `POST /bdm/meeting-requests/{id}/accept` | `bdm` | Body = bdm-006 `BdmAppointmentCreate`. Order: 403 role/profile; 404 scope (locked, re-checked); 409 not pending; then bdm-006's rules (MR9). On success the request is `accepted` (taker, appointment, `decided_at`), returns `{appointment, meeting_request}`. Audits `bdm_appointment.create` (bdm-006's) and `bdm_meeting_request.accept` |
| `POST /bdm/meeting-requests/{id}/decline` `{reason}` | `bdm` | 403 / 404 / 409 as above; reason 1–500 chars required (422). `declined` + taker + `decided_at`. Audit `bdm_meeting_request.decline` |

Request output: `{id, code, request_type, type_label, bdm_type, organization_name, person_name, contact_phone, contact_email, proposed_at,
mode, location, purpose, remarks, status, requester:{id,full_name}, bdm:{id,full_name}|null, appointment:{id,code,starts_at,status}|null,
decline_reason, decided_at, created_at, permissions}`. Lists are `{items,total,limit,offset}`.

`api/bdm_appointments.create_appointment` is refactored so its body (everything before the commit) is `book_appointment(db, user, payload)`;
the route keeps its behaviour, and accept calls the same function.

## 4. Frontend

- `lib/meetingRequests.ts`: types, labels, URLs, status labels/classes.
- Telecaller: nav **BDM requests** → `/telecaller/meeting-requests` (own list: status chip, BDM, the accepted appointment's code + time, the
  decline reason; empty state; "New request" button) and `/telecaller/meeting-requests/new` (`MeetingRequestForm`: type, BDM — "Any
  BDM of this type" or a named one, filtered by type —, organization, person, phone, email, date/time (IST), mode, link/location, purpose,
  remarks; inline focused field errors; the entry is kept on any failure; on success back to the list with a confirmation).
- BDM: nav **Requests** → `/bdm/meeting-requests` (status filter, pending default), `/bdm/meeting-requests/[id]` (the request; when
  `can_accept`: `BdmAppointmentForm` in create mode, prefilled per MR9, submitting to the accept URL, then to the new appointment;
  when `can_decline`: a reason form). **My Day** gains a "Meeting requests" card: pending count and the next five, each linked.
- BDM manager: nav **Requests** → `/bdm/manager/meeting-requests` (read-only list).

## 5. Security

Scope always comes from the session (no client-supplied scope). An id outside it is 404. The target BDM is validated server side. Text
fields refuse control characters (`_clean` idiom); the link/location is free text rendered as text, never as a link (no `javascript:`
risk). Audit rows and logs carry ids, types and statuses only — never the person, phone, email or free text. The pool accept race is
serialised by the request row lock and the `pending` check (second accept → 409/404).

## 6. Tests

- **Backend** `test_tel_019_*`: migration (chain, CHECKs, round trip in a throwaway DB, downgrade guard); create (happy path pool and
  named, every 422, non-telecaller 403); options; telecaller list (own only); BDM scope (AC1 corporate → college only; agent BDM sees no
  college request; named request invisible to another BDM; manager team + pool; super_admin all; telecaller 403); accept (AC2 exactly
  one appointment + request accepted; second accept 409; agent BDM accepting a college request 404; past proposed time + future start OK;
  bdm-006 refusals pass through; manager 403); decline (AC3 reason required 422; final; accept after decline 409); bdm-006 create
  regression (`test_bdm_006_appointments.py`).
- **Frontend** vitest: `MeetingRequestForm`, the BDM request detail (accept/decline visibility), My Day card.
- **E2E** Playwright `tel-019-meeting-requests.spec.ts`: telecaller files a school request → school BDM sees it on My Day → accepts
  into an appointment → telecaller sees Accepted; a corporate request is declined with a reason.
