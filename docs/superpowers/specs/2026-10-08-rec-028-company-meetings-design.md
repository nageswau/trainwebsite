# rec-028 — Company meetings (design)

- **Feature:** `rec-028` (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-028). **Dependencies:** rec-004 (PR #160) and rec-024 (PR #168),
  both merged.
- **Evidence:** `EVID-018` §20 (lines 796–836). It lists 7 meeting types and 11 fields: Meeting ID, Company, Contact, Date, Time, Mode,
  Location/Meeting Link, Purpose, Participants, Outcome and Next Action. Line 47 adds the "+ Schedule Meeting" quick action (rec-032 owns
  the dashboard). Line 234 is the pipeline stage "Meeting Scheduled" (rec-005).
- **Module scope:** `DEC-SCOPE-116`. R10: recruiters do every meeting, and the BDM is read-only. R14: meeting links are typed in.
- **Decision:** `DEC-SCOPE-134`. MT1–MT10 are **recommended defaults**, taken on the owner's standing instruction for build sessions
  ("proceed with the recommended answers; ask only if blocking"). They stay `UNVERIFIED` until the owner confirms them.
- **Numbering (FINAL):** migration `0119_recruiter_meetings` (after rec-025's `0118_recruiter_calls`), API §12BB and RBAC §2.60. Drafted
  as `0117` / 132 / §12AZ / §2.58, then `0118` / 133 / §12BA / §2.59; rec-008 and then rec-025 merged first and took those numbers.

## 1. Decisions (UNVERIFIED defaults)

| # | Point | Answer |
|---|---|---|
| MT1 | Types | The 7 §20 values, in source order: `company_meeting`, `hr_meeting`, `requirement_discussion`, `recruitment_presentation`, `contract_discussion`, `campus_recruitment_discussion`, `placement_drive_discussion` |
| MT2 | Meeting ID | `MTG-000001` from the sequence `recruiter_meeting_code_seq`, unique. Server-owned |
| MT3 | Date and time | One `starts_at` instant. The web enters it in IST and drops seconds (`BdmApptStart`). At scheduling and on reschedule it must be in the future and within 366 days, else `422` on `starts_at`. No duration (the source has none) |
| MT4 | Mode, location and link | Mode is one of `Online`, `Phone`, `In person` (`APPOINTMENT_MODES`, shared with tel-016/tel-019). Location ≤ 200 characters is optional. The meeting link is optional, ≤ 500 characters, and must use `http(s)` (tel-016's `LeadApptLink`). It is typed in (R14). Purpose ≤ 1000 is optional |
| MT5 | Contact and participants | `contact_id` is the primary contact and is optional. Participants are company contacts plus recruiters (internal `placement_team` / `placement_manager` users). A contact set or added must be an **active contact of the same company**. Anything else → `422` (the backlog negative scenario). A recruiter added must be an active placement user. The primary contact is always stored as a participant. At most 20 contacts and 20 recruiters. A stored participant stays when it is later deactivated |
| MT6 | States | `scheduled` → `completed` (the outcome is recorded) or `cancelled` (a reason is required). Both are final. Reschedule = `PATCH starts_at` on a scheduled meeting. Every schedule, reschedule, completion and cancellation appends a `recruiter_meeting_events` row, so reschedules keep the old and new times (the backlog edge case) |
| MT7 | Outcome and next action | `POST …/outcome {outcome, next_action?, next_action_due_at?, next_action_reason?}`. It is only allowed once the start time has passed (`422`). The outcome (≤ 2000) is required. A next action (≤ 500) needs a due time and a §18 reason. It **creates a rec-024 follow-up** in the same transaction (AC2): notes = the next action, contact = the meeting's primary contact when still active. It goes through rec-024's rules: future due time, the 50-open cap → `409`, and the whole outcome rolls back |
| MT8 | Pipeline | Scheduling fires rec-005's `meeting_scheduled` event under the company lock. It moves the company only when it is earlier in the pipeline (AC1), and never when it is Lost or archived. Rescheduling, completing and cancelling never move the stage |
| MT9 | Who | Writes need the company's `can_edit`: the assigned recruiter or `super_admin`. `placement_manager` and the assigned BDM read only (`403`). An archived company's meetings are read-only (`409`). Reads use rec-003 `caller_scope`. Out of scope = `404` |
| MT10 | Lists | `/recruiter/meetings` has four views with counts. **Upcoming** = scheduled with the start in the future, soonest first. **Awaiting outcome** = scheduled with the start passed, oldest first. **Completed** and **Cancelled** are newest first. A company's list shows scheduled meetings by start, then the rest newest first |

## 2. Data (`0119`)

- **`recruiter_meetings`:**
  - `id`, `meeting_code` (unique), `company_id`, and `contact_id` (nullable, FK `company_contacts`)
  - `meeting_type` (CHECK 7), `starts_at`, `mode` (CHECK 3), `location`, `meeting_url`, `purpose`
  - `status` (CHECK scheduled/completed/cancelled), `outcome`, `next_action`, `follow_up_id` (FK `recruiter_follow_ups`)
  - `completed_at`, `completed_by_user_id`, `cancelled_at`, `cancel_reason`, `created_by_user_id`, `created_at`, `updated_at`
  - A state CHECK. Completed ⇔ completed_at/by and outcome set. Cancelled ⇔ cancelled_at and reason set. Next action and follow-up are
    set only on completed.
  - Indexes: `(company_id, starts_at)`, `(status, starts_at)` and `(contact_id)`.
- **`recruiter_meeting_participants`:** `id`, `meeting_id`, and `contact_id` or `user_id` (CHECK: exactly one).
  - Unique `(meeting_id, contact_id)` and `(meeting_id, user_id)`.
  - Rows are replaced as a set on edit.
- **`recruiter_meeting_events`:** an append-only log of each transition. An `event` value is one of scheduled, rescheduled, completed or
  cancelled.
  - It also has `old_starts_at`, `new_starts_at`, `reason`, `actor_user_id`, `position` (identity) and `created_at`.
- Every FK is RESTRICT. The guarded create follows the 0001 fresh-build idiom. `downgrade()` refuses while any meeting exists.

## 3. API (§12BB)

| Method/Path | Notes |
|---|---|
| `GET /recruiter/meetings?view=upcoming\|awaiting_outcome\|completed\|cancelled&limit&offset` | MT10. Returns `{items, total, limit, offset, counts}`. Scoped to the caller's companies |
| `GET /recruiter/meetings/recruiter-options?q&limit` | The participant picker: active `placement_team` / `placement_manager` users, names only. For recruiters, managers and super_admin |
| `GET /recruiter/meetings/{id}` | One item |
| `GET /recruiter/companies/{id}/meetings` | The company's meetings, paged |
| `POST /recruiter/companies/{id}/meetings` | Body: `{meeting_type, starts_at, mode, location?, meeting_url?, purpose?, contact_id?, participant_contact_ids[], participant_user_ids[]}`. Returns `201` and the item. Fires MT8 |
| `PATCH /recruiter/meetings/{id}` | A partial edit of a scheduled meeting. A changed `starts_at` is a reschedule (MT3; an optional `reschedule_reason` ≤ 500 goes on its event). Participant lists replace the set. Null on a required field → `422` |
| `POST /recruiter/meetings/{id}/outcome` | MT7 |
| `POST /recruiter/meetings/{id}/cancel` | Body: `{reason}` |

Each write follows the same sequence:
1. Load the company in scope and lock it, then check `can_edit` (403/409).
2. Lock the meeting and check that it is scheduled (`409` otherwise).
3. Validate, make the change, and append an event.
4. Write the audit row `recruiter_meeting.{create,update,complete,cancel}` (ids, keys and field names only; never purpose, outcome or
   reasons).
5. Commit once, then log.

**Item:**
- `id`, `code`, `company {id, code, name, assigned_recruiter}`, `meeting_type`, `starts_at`, `mode`, `location`, `meeting_url`, `purpose`
- `contact {id, name}|null`, `participants {contacts [{id, name}], recruiters [{id, full_name}]}`
- `status`, `outcome`, `next_action`, `follow_up {id, due_at}|null`
- `created_by`, `created_at`, `completed_at`, `completed_by`, `cancelled_at`, `cancel_reason`
- `history [{event, old_starts_at, new_starts_at, reason, actor, created_at}]`
- `can_change` (scheduled and `can_edit`) and `can_record_outcome` (`can_change` and started)

## 4. Web

- **Company page:** a **Meetings** section after Follow-ups.
  - Schedule a meeting with the type, date and time (IST), mode, location, link and purpose. The primary contact and participant contacts
    come from the company's active contacts (checkboxes). Recruiter participants come from the searchable picker.
  - Each meeting has three actions, offered only when the API allows them: Record outcome (with an optional next action that becomes a
    follow-up), Reschedule/edit and Cancel.
  - Each meeting shows its reschedule history.
  - Any change re-reads the company (its stage and next follow-up) and reloads the stage history and follow-ups.
- **`/recruiter/meetings`:** tabs for the four views with counts. The tab lives in the URL. Each card links to its company. The page is
  in the recruiter and manager navs.
- Every list has loading, empty, error and retry states. 422s are placed on their fields. When the session ends, the session-ended link
  is shown (the rec-024 idioms).

## 5. Tests

- **Backend:** `test_rec_028_meetings.py` covers the types, fields, the contact and participant rules (another company's contact → 422),
  roles and scope, AC1 (stage moves only when earlier), reschedule history, AC2 (outcome + next action → follow-up), the outcome before
  start, cancel and final states, the lists and counts, and audit. `test_rec_028_migration.py` covers the CHECKs equalling the model, the
  head, the round trip and the downgrade refusal.
- **vitest:** the lib helpers, the company Meetings section and the meetings panel.
- **e2e:** `rec-028-meetings.spec.ts`. Schedule a contract discussion with two contacts → the stage reads Meeting Scheduled → it shows
  under Upcoming.
