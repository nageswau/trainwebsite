# rec-020 — Interview management (design)

- **Feature:** `rec-020` (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-020). **Dependency:** rec-017 (PR #178), merged.
- **Evidence:** `EVID-018` §14 (lines 594–652). It lists 12 fields (Interview ID, Company, Requirement, Candidate, Round, Date, Time,
  Interview Mode, Meeting Link, Interviewer, Location, Status), 5 rounds and 8 statuses. Line 47 adds the "+ Schedule Interview" quick
  action (rec-032 owns the dashboard). §5's pipeline stage "Interview" (rec-005) is reached by scheduling.
- **Module scope:** `DEC-SCOPE-116`. R14: interview links are typed in. R8: candidate phone and email are never shared with a company.
- **Decision:** `DEC-SCOPE-139`. IV1–IV12 are **recommended defaults**, taken on the owner's standing instruction for build sessions
  ("proceed with the recommended answers; ask only if blocking"). They stay `UNVERIFIED` until the owner confirms them. IV9 answers the
  backlog's Q-20.
- **Numbering (draft):** migration `0124_interview_management` on `0122_candidate_skills`, API §12BG and RBAC §2.65. rec-010 is in
  progress in parallel and has planned `0123` / DEC-SCOPE-138 / §12BF / §2.64, so this item reserves the next set. Whichever merges second
  re-chains `down_revision` only.

## 1. Decisions (UNVERIFIED defaults)

| # | Point | Answer |
|---|---|---|
| IV1 | Rounds | The 5 §14 values in source order: `hr_round`, `technical_round`, `manager_round`, `final_round`, `client_round`. Required on the recruiter routes. Nullable in the table: legacy rows and the legacy/employer routes have no round |
| IV2 | Statuses | The 8 §14 values: `scheduled`, `confirmed`, `completed`, `rescheduled`, `no_show`, `selected`, `rejected`, `on_hold`. **Open** = scheduled, confirmed, rescheduled |
| IV3 | Moves (`POST …/status`) | confirmed ← scheduled/rescheduled. completed, no_show ← open, **only once the scheduled time has passed** (AC2, `422`). on_hold ← open or completed (the backlog edge case "the company cancels" → On Hold). selected, rejected ← completed or on_hold, once started. selected and rejected are final. `scheduled` and `rescheduled` are never chosen here. Anything else → `409`. An optional note ≤ 500 goes on the event |
| IV4 | Reschedule (`POST …/reschedule`) | Allowed from open, on_hold and no_show. The new time must be in the future and within 366 days (`422` on `scheduled_at`) and must differ from the current one. The status becomes `rescheduled`. An event keeps the old → new time and an optional reason ≤ 500 (AC1) |
| IV5 | Schedule (`POST /recruiter/interviews`) | Body: application, round, `scheduled_at`, mode, `meeting_url?`, `interviewer?`, `location?`, `contact_id?`, `notify` (default true). The time must be in the future and within 366 days (`422`, the backlog negative scenario). The application must be open (sourced … interview → else `409`) and its requirement not closed or cancelled (`409`). Several rounds on one application and several on one day are allowed |
| IV6 | Clash | Per candidate, across every requirement: another **open** interview of the same candidate at the same minute → `409` (the existing EMP-004 rule, kept, no duration invented: §14 has none). It applies to every creator and to a reschedule. The candidate row is locked first, so two schedules for one candidate serialise |
| IV7 | Fields | `interview_code` `INT-000001` from `interview_code_seq` (server-owned; existing rows backfilled in creation order). Mode is one of `APPOINTMENT_MODES` (Online, Phone, In person) on the recruiter routes; the column stays free text for legacy rows. `meeting_url` is optional, ≤ 500, `http(s)` (R14, typed). `interviewer` ≤ 160 and `location` ≤ 200 are optional free text. `contact_id` is optional: an active contact of the requirement's company (`422`) |
| IV8 | Side effects | Scheduling moves the application to Interview via rec-017 `follow` (only when allowed) and fires rec-005 `interview_scheduled` on the company (forward only). **Rejected** moves the application to Rejected via `follow`. **Selected** moves it to Selected only on a Final or Client round; on HR, Technical and Manager rounds Selected means "passed this round" and the application stays at Interview (the backlog positive scenario "HR round → Technical round"). Nothing else moves the application |
| IV9 | Notifications (Q-20) | On schedule and on reschedule, when `notify` is true: a student candidate (with a login) gets the in-app notification plus ENH-014 deliveries. An external candidate with an email gets a queued email through rec-026's `recruiter_messages` pipeline (SMTP, retries, visible in the candidate's messages). The chosen company contact with an email gets one too, naming the candidate by name and code only (R8). SMTP not configured or no email → the interview is still saved, and the response says which notices were skipped. The rec-026 daily cap does not apply (these are system notices, not the recruiter's messages) |
| IV10 | Who | Writes: rec-017's writers (`placement_team` within the requirement's scope, `super_admin`). `placement_manager` and the assigned BDM read (`403` on writes). Reads use rec-007's requirement scope; out of scope = `404`. `hr_team` and `it_admin` keep the legacy `/workflows/it/interviews` routes. Employers keep `/employer/interviews` (own jobs) |
| IV11 | Legacy routes | `POST /workflows/it/interviews` and `POST /employer/interviews` delegate to `services/interviews.create_legacy` (code, `scheduled` event, the IV6 clash `409`). They stay without the IV5 future-time and open-application rules, so their contracts are unchanged. `PATCH /workflows/it/interviews/{id}`: a changed `scheduled_at` is recorded as a reschedule (event, status rescheduled), and a result of selected/rejected/on_hold also sets the status when the move is allowed. `result` is kept as is. Responses only gain fields |
| IV12 | Lists | `/recruiter/interviews` has four views with counts. **Upcoming** = open with the time in the future, soonest first (the UI groups them by day: the calendar). **Awaiting update** = open with the time passed, or completed, oldest first. **On hold**, newest first. **Closed** = selected, rejected, no_show, newest first. An application's interviews are listed on the requirement's candidate row, newest first |

## 2. Data (`0124`)

- **`interviews`** gains:
  - `interview_code` (String 20, unique, NOT NULL after the backfill), `round` (String 20, nullable, CHECK the 5),
    `status` (String 16, NOT NULL, default `scheduled`, CHECK the 8), `interviewer` (String 160), `location` (String 200)
  - `contact_id` (FK `company_contacts`, RESTRICT, nullable) and `created_by_user_id` (FK `users`, nullable: legacy rows)
  - Index `(status, scheduled_at)`.
  - Backfill: the code in `created_at` order. Status from the legacy `result`: selected / rejected / on_hold are kept; any other non-empty
    result (for example `cancelled`) → on_hold; empty → scheduled.
- **`interview_events`**: an append-only log. `id`, `interview_id` (FK RESTRICT), `event` (CHECK scheduled / rescheduled / status),
  `from_status`, `to_status`, `old_scheduled_at`, `new_scheduled_at`, `note` (≤ 500), `actor_user_id` (FK, nullable),
  `position` (identity) and `created_at`. Index `(interview_id, position)`. No events are backfilled; history starts with this release.
- **`interview_code_seq`**, set past the backfilled codes.
- `downgrade()` refuses while any event exists: entered data is never dropped silently. The steps are guarded (0001 builds a fresh
  database from the current models).

## 3. API (§12BG)

| Method/Path | Notes |
|---|---|
| `GET /recruiter/interviews?view=upcoming\|awaiting_update\|on_hold\|closed&limit&offset` | IV12. `{items, total, limit, offset, counts}`, scoped by requirement |
| `GET /recruiter/interviews/{id}` | One item |
| `GET /recruiter/applications/{id}/interviews` | The application's interviews, plus `can_schedule` |
| `POST /recruiter/interviews` | IV5. `201` and `{interview, notifications}` |
| `PATCH /recruiter/interviews/{id}` | Round, mode, link, interviewer, location and contact on a non-final interview (selected and rejected are final → `409`). Equal values are not changes. The time changes only through reschedule |
| `POST /recruiter/interviews/{id}/reschedule` | IV4. Body: `{scheduled_at, reason?, notify}`. Returns `{interview, notifications}` |
| `POST /recruiter/interviews/{id}/status` | IV3. Body: `{status, note?}` |

Each write follows the same sequence:
1. Resolve the interview's application through the requirement scope (`404`), lock the application, then check the writer (`403`).
2. Lock the candidate when the time is set, run the clash check, then lock the interview and check its state (`409`).
3. Validate, make the change, append an event, and apply the side effects (IV8).
4. Write the audit row `recruiter_interview.{create,update,reschedule,status}` (ids, keys, field names; never a note or reason).
5. Commit once, then publish the queued emails, then log.

**Item:**
- `id`, `code`, `round`, `round_label`, `scheduled_at`, `mode`, `meeting_url`, `interviewer`, `location`, `status`, `status_label`, `result`
- `application {id, status, status_label}`, `candidate {id, code, name}`, `requirement {id, code, title}`, `company {id, name}`,
  `contact {id, name}|null`
- `history [{event, from_status, to_status, old_scheduled_at, new_scheduled_at, note, actor, created_at}]`
- `allowed_statuses [{key, label}]` (only the moves allowed now, and only for a writer), `can_edit`, `can_reschedule`

## 4. Web

- **Requirement page, candidate row:** an **Interviews** toggle next to History. It lists the application's interviews, with
  "+ Schedule interview" when allowed. Each interview shows its round, time (IST), mode, link, interviewer, location, contact and status.
  Its actions are Change status, Reschedule and Edit, each offered only when the API allows it. Each interview shows its history.
  Any change re-reads the candidates list, so the application's status follows.
- **`/recruiter/interviews`:** tabs for the four views with counts. The tab lives in the URL. Upcoming is grouped by day. Each card links
  to its requirement. The page is in the recruiter and manager navs.
- Every list has loading, empty, error and retry states. 422s are placed on their fields. When the session ends, the session-ended link
  is shown (the rec-028 idioms).

## 5. Tests

- **Backend:** `test_rec_020_interviews.py` covers:
  - rounds, statuses and moves (IV3), with No Show and Completed only after the time (AC2)
  - reschedule history (AC1), the past time `422`, and the clash `409`
  - the open-application and ended-requirement `409`s
  - roles and scope, the side effects (IV8), notifications (IV9), the lists and counts, and audit

  `test_rec_020_migration.py` covers the CHECKs equalling the model, the backfill, the head and the downgrade refusal. The EMP-004 and
  EMP-005 tests and the legacy workflow interview routes keep passing (AC3).
- **vitest:** the lib helpers, the application interviews section and the interviews panel.
- **e2e:** `rec-020-interviews.spec.ts`. Schedule an HR round → reschedule it → history shows old → new → it appears under Upcoming.
