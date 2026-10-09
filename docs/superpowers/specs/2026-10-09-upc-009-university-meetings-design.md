# upc-009 — University meetings (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". The item answers MG1–MG16 (§1), including **Q-12** (does "Next meeting date" create a draft meeting or a
follow-up?), are **recommended defaults accepted under that instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals). They
are registered that way in `DEC-SCOPE-145`.

**Branch:** `feature/upc-009`, cut from `origin/main` @ `788b1636` (after #186, upc-020).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-009, Q-12, Appendix A L244–L312.
**Dependencies:** upc-006 (`0108`, `DEC-SCOPE-123`) and upc-020 (`0126`, `DEC-SCOPE-141`) are merged on main. This was verified in code:
`UniversityContact`, `services/partnership_tasks.py` (`_auto_create`, source `meeting` reserved by TK4), and the upc-007 stage engine.
**Source:** `EVID-020` §7 (L244–L312): "The Partnership Manager should be able to schedule every interaction", 19 meeting fields and 12
meeting types.
**Numbering:** migration `0130_university_meetings`, `DEC-SCOPE-145`, API §12BM, RBAC §2.71. Drafted as `0127` / `DEC-SCOPE-142` / §12BJ /
§2.68; renumbered on merging `main` @ `7ba4cb36` (upc-014 took them first), then from `0128` / `DEC-SCOPE-143` / §12BK / §2.69 on merging
`main` @ `52646217` (upc-008 took them first), and from `0129` / `DEC-SCOPE-144` / §12BL / §2.70 on merging `main` @ `362cf3ca` (upc-016
took them first; this migration now follows `0129_university_commission_terms`).
**Gate:** `APPROVAL_GATES.md` GATE-09.
**Templates:** rec-028 (`recruiter_meetings`: type, one `starts_at`, mode, location, typed link, participants table, events with old/new
times, outcome → follow-up) and upc-010 (`university_visits`: partnership roles, edit scope, lead rule, option pickers, page layout). Neither
is changed.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| MG1 | Meeting types | The 12 §7 values in source order and wording: `introduction`, `partnership_discussion`, `commercial_discussion`, `mou_discussion`, `product_presentation`, `student_recruitment_discussion`, `application_process_discussion`, `marketing_discussion`, `university_visit`, `campus_visit`, `webinar`, `training_session`. "University visit" / "Campus visit" are meeting types only; the planned trip with approval stays upc-010 |
| MG2 | Meeting ID | `UMT-000001` from `university_meeting_code_seq` (the VIS/TRV idiom). Server-owned |
| MG3 | Date and time | One `starts_at` instant (§7 "Date" + "Time"). The web enters it in IST (`istInputToIso`). At scheduling and on reschedule it is in the future and within 366 days, else 422 on `starts_at` (rec-028 MT3). No duration (the source has none) |
| MG4 | Online/Offline, location, link | `mode` is `online` or `offline` (§7 wording). Location ≤ 200 is optional. The link is optional, ≤ 500, `http(s)` only, typed in (R14; no provider integration). **Edge case:** an online meeting without a link is **allowed with a warning** — the output carries `warnings: ["link_missing"]` while it is scheduled, and the form and detail show it |
| MG5 | Contact Person + Designation | `contact_id` (optional) must be a contact **of this university** (any other → 422, the backlog negative scenario). Its name and designation are **copied** onto the meeting (`contact_name`, `contact_designation`) when it is set, so the record keeps them after the contact changes or is deleted (the FK is `SET NULL`) |
| MG6 | University participants | Contacts of this university, at most 20 (22 → 422). The contact person is always stored as a participant. A deleted contact leaves the list (FK CASCADE: contact PII deletion wins, upc-010 VS12) |
| MG7 | Participants from EduSphere | Active `partnership_manager` / `partnership_head` users other than the responsible employee, at most 10 (upc-010 VS11, its `employee-options` picker is reused). A stored participant stays when later deactivated |
| MG8 | Responsible employee | `responsible_user_id`. A manager is responsible for the meetings they schedule; a head picks themselves or an active direct report (upc-010 VS6 `lead_filter`, its `lead-options` picker is reused). Default: the caller |
| MG9 | Statuses | `scheduled` → `completed` (the outcome is recorded once the start has passed) or `cancelled` (reason 1–1000 required). Both final. Reschedule = `PATCH starts_at` on a scheduled meeting. Every schedule, edit, reschedule (old + new time), completion and cancellation appends a `university_meeting_events` row |
| MG10 | Notes, discussion points, decisions | Agenda ≤ 2000 and notes ≤ 2000 are set when scheduling or editing. On **complete**: notes (may be updated), discussion points ≤ 4000, decisions ≤ 2000, next action, next meeting date. At least one of notes / discussion points / decisions is required to complete (an outcome with no record is a 422) |
| MG11 | Next action (AC2) | On complete, `next_action` (≤ 200, the task-title limit) needs `next_action_due_on` (today or later, IST) and **creates a upc-020 follow-up** in the same transaction: kind `follow_up`, title = the next action, source `meeting`, rule `meeting:<id>`, priority `high` (a committed next step, the §20 XYZ example), assigned to the responsible employee when active, else upc-020's TK6 fallback. A due date without a next action is a 422 |
| MG12 | Q-12: Next meeting date | **A follow-up, not a draft meeting.** A meeting needs a time, contact and type the user has not chosen yet, and a draft would sit in the upcoming list as if agreed. The date is stored on the meeting and creates the follow-up "Schedule the next meeting", due on that date (today or later), rule `meeting:<id>:next`, priority `medium`, same assignee as MG11 |
| MG13 | Stage (AC3) | Scheduling moves the university to **Meeting Scheduled** when its stage is earlier; completing moves it to **Meeting Completed** when earlier (the backlog's "can move the stage"). Never backwards, never when the university is lost or inactive. The move goes through the upc-007 engine (history row kind `move`, note "Automatic: meeting UMT-… scheduled/completed", audit `stage_changed` with `source: meeting`) and fires upc-020's stage rule (Meeting Completed → "Send partnership proposal"). Rescheduling and cancelling never move the stage |
| MG14 | Who reads | `partnership_manager` (with a profile), `partnership_head` and `super_admin` read **every** meeting (upc-010 VS7, upc-020 TK8). Every other role, including `overseas_admin`, gets a 403 |
| MG15 | Who schedules / acts | Schedule: managers and heads, on an active university in their edit scope (upc-006 `can_edit_contacts`, as visits VS6). Edit, complete and cancel: the **responsible employee or the person who scheduled it** (upc-010 VS8); others 403. super_admin reads only. A completed or cancelled meeting is a 409 |
| MG16 | Lists | `/partnership/meetings` has four views with counts (rec-028 MT10): **Upcoming** (scheduled, start in the future, soonest first), **Awaiting outcome** (scheduled, start passed, oldest first), **Completed** and **Cancelled** (newest first), plus "Only my meetings" (responsible, scheduler or EduSphere participant) and a university filter. The university page lists its latest 5 meetings: scheduled by start, then the rest newest first |

Not in scope: the calendar and overlap warning (upc-011), the timeline (upc-013), notifications (the source names none; the follow-up
appears in the assignee's task list), a meeting-provider integration (R14), and auto-closing "Schedule the next meeting" when the next
meeting is booked (follow-up candidate).

## 2. Data model — migration `0130_university_meetings`

- `university_meeting_code_seq`.
- `university_meetings`:
  - id; code String(20) unique; university_id FK RESTRICT; contact_id FK `university_contacts` SET NULL null; contact_name String(200)
    null; contact_designation String(120) null;
  - meeting_type String(40); starts_at timestamptz; mode String(10); location String(200) null; meeting_url String(500) null;
  - agenda / notes / discussion_points / decisions Text null; next_action String(200) null; next_action_due_on Date null;
    next_meeting_date Date null;
  - responsible_user_id FK users RESTRICT; created_by_user_id FK users RESTRICT; status String(12) default `scheduled`;
  - completed_at timestamptz null, completed_by_user_id FK null; cancelled_at null, cancel_reason Text null; created_at / updated_at.
  - CHECKs: type, mode, status in their lists; `(status = 'completed') = (completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL)`;
    `(status = 'cancelled') = (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)`; `(next_action IS NULL) = (next_action_due_on IS
    NULL)`; outcome fields (`discussion_points`, `decisions`, `next_action`, `next_meeting_date`) only on completed.
  - Indexes: `(university_id, starts_at)`, `(status, starts_at)`, `(responsible_user_id)`.
- `university_meeting_participants`: id; meeting_id FK CASCADE; contact_id FK `university_contacts` CASCADE null; user_id FK users RESTRICT
  null; CHECK exactly one of contact/user; unique `(meeting_id, contact_id)` and `(meeting_id, user_id)`.
- `university_meeting_events`: id; meeting_id FK CASCADE; event String(12) CHECK (`scheduled, edited, rescheduled, completed,
  cancelled`); old_starts_at / new_starts_at null; reason Text null; actor_user_id FK RESTRICT; position BigInteger Identity (orders rows
  in one transaction, rec-028); created_at. Index (meeting_id, position).
- Downgrade refuses while any meeting exists. No backfill (inventing past meetings would invent facts).

## 3. Backend

`app/partnership_meeting_types.py` (constants), `services/university_meetings.py` (scope, rules, output; never commits),
`api/university_meetings.py` (prefix `/partnership/meetings`, owns the transaction). The stage move reuses upc-014's forward-only
`partnership_pipeline.advance_to` (the meeting service skips lost / inactive universities first). `services/partnership_tasks.py` gains
`on_meeting_completed(db, actor, meeting, uni)`.

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/meetings` | readers (MG14) | `view` (`upcoming / awaiting_outcome / completed / cancelled`; omitted = all, scheduled first), `university_id`, `mine`, `limit`, `offset` → `{items,total,limit,offset,counts}`; counts use every filter but the view |
| `POST /partnership/meetings` | schedulers (MG15) | 201 `{meeting}`; AC3 stage move in the same transaction |
| `GET /partnership/meetings/{id}` | readers | `{meeting}` with participants, history, follow-ups, `warnings`, `permissions` |
| `PATCH /partnership/meetings/{id}` | actor | Scheduled only; only fields sent (`extra="forbid"`); a changed `starts_at` is a reschedule (+ optional `reschedule_reason` ≤ 500) |
| `POST /partnership/meetings/{id}/complete` | actor | `{notes?, discussion_points?, decisions?, next_action?, next_action_due_on?, next_meeting_date?}`; started only (422) |
| `POST /partnership/meetings/{id}/cancel` | actor | `{reason}` |

Pickers reuse `GET /partnership/visits/university-options | lead-options | employee-options` (same roles and scope); contacts come from
upc-006 `GET /partnership/universities/{id}/contacts`.

- **Every write**, one transaction: role check → lock (create: the university `FOR UPDATE`; complete: the university, then the meeting;
  edit/cancel: the meeting only) → actor (403, logged ids only) → state (409) → validation (422) → change + event row + `AuditLog`
  (`university_meeting.<action>`: ids, code, type, mode, counts, field names; never agenda, notes, discussion, decisions, next action or
  reason) → stage advance / tasks → one commit → structured log.
- Unknown meeting → 404.

## 4. Frontend

- `lib/meetings.ts`: types, `MEETING_TYPES` (12 labels), `MODES`, `VIEWS` + empty texts, `EVENT_LABELS`, URLs/paths, `MEETING_READERS` /
  `SCHEDULER_ROLES`, list query helpers, `meetingWhen` (IST).
- `components/MeetingForm.tsx` (client): university (SearchableSelect via visits' `universityOptions`, or fixed), responsible (heads),
  type, date-time (IST, `datetime-local`), online/offline, location, link (+ the MG4 warning), contact person (select of the university's
  contacts) with its designation shown, university participants (checkboxes), EduSphere participants (chips + picker), agenda, notes. 422
  field errors, a double-submit guard. On edit only the changed fields are sent; a changed time asks for an optional reschedule reason.
- `components/MeetingActions.tsx` (client): Record outcome (inline form: notes, discussion points, decisions, next action + due date,
  next meeting date) when `can_complete`; Cancel (reason) when `can_cancel`; Escape backs out; `router.refresh()` on success.
- `components/MeetingTable.tsx`: code link, university, type, when (IST), mode, responsible, status; cards below 640 px.
- Pages (server, PortalShell via `shellFor`): `/partnership/meetings` (view tabs with counts as links, "Only my meetings", paging),
  `/partnership/meetings/new?university=<id>`, `/partnership/meetings/[id]` (facts, participants, outcome, follow-ups, history, actions),
  `/partnership/meetings/[id]/edit`.
- University page: a **Meetings** section (latest 5, "Schedule a meeting" for a scheduler with `can_edit_contacts`, "All N meetings").
  No always-present `role="status"` element (upc-012 lesson).
- Nav: `PARTNERSHIP_MENU` "Meetings" goes live; `PARTNERSHIP_HEAD_NAV` gains "Meetings"; `SUPER_ADMIN_NAV` gains "Partnership Meetings".

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | All §7 fields are stored and returned (code, university, contact + designation, type, date/time, location, mode, link, both participant lists, agenda, notes, discussion points, decisions, next action, next meeting date, responsible employee) | `test_upc_009_meetings.py`; e2e |
| AC2 | The next action creates a upc-020 follow-up (title, due date, assignee, source `meeting`) | `test_upc_009_meetings.py`; e2e |
| AC3 | Scheduling moves the stage to Meeting Scheduled when it is earlier (and not when later, lost or inactive); completing moves it to Meeting Completed when earlier | `test_upc_009_meetings.py`; e2e |
| P1 | An MoU discussion meeting with 2 university participants | `test_upc_009_meetings.py`; e2e |
| N1 | A contact of another university → 422 | `test_upc_009_meetings.py` |
| E1 | An online meeting without a link is saved with a `link_missing` warning | `test_upc_009_meetings.py`; vitest |
| Q12 | The next meeting date creates "Schedule the next meeting" due on that date | `test_upc_009_meetings.py` |
| R1 | Other roles 403; non-actor writes 403; closed meeting 409; past start 422; outcome before start 422; out-of-scope university 403; unknown meeting 404 | `test_upc_009_meetings.py` |
| M1 | Migration: CHECKs and indexes equal the model; downgrade guard | `test_upc_009_migration.py` |

## 6. Tasks (TDD, in order)

1. Constants + models + migration + parity test (`test_upc_009_migration.py`).
2. Schemas, service, routes: create/read/access/list tests, then edit/reschedule, then complete/cancel, stage and task tests, then the code
   (`test_upc_009_meetings.py`).
3. Frontend: lib, `MeetingForm`, `MeetingActions`, `MeetingTable`, pages, university section, nav, with vitest.
4. Playwright `upc-009-university-meetings.spec.ts`.
5. Docs: DEC-SCOPE-145, API §12BM, RBAC §2.71, DATA_MODEL, SCREEN_CATALOG, backlog status.

## 7. Regression set (lite)

`test_upc_007_*` (the engine gains `advance`), `test_upc_020_*` (tasks gain a hook), `test_upc_010_*` (option pickers reused),
`test_upc_006_*`, `navigation.partnership.test.ts`, `UniversityDetailPage.test.tsx`, the upc-007/010/020 e2e specs.

## 8. Engineering review notes (Phase 3)

- **API (api-and-interface-design):**
  - Responses use the partnership envelope (`{meeting}`), as `{visit}` / `{task}` do. Each meeting carries `permissions` (`can_edit,
    can_complete, can_cancel`) computed from the same actor + state rules the routes enforce; `can_complete` is also false before the
    start (the UI never offers a 422).
  - 404 only for a missing meeting (every reader reads every meeting: no scope-hiding 404). 403 for a role or actor refusal, 409 for a
    completed or cancelled meeting, 422 for validation (service rules raise on their body field so the form can place them).
    `extra="forbid"` on every body; `status`, `code`, `university_id` are never writable.
  - Not idempotent: a retried create schedules a second meeting (rec-028's accepted behaviour; the form's double-submit guard limits
    it). A retried complete/cancel meets a closed meeting → 409, which the UI shows as "changed elsewhere".
  - Additive only: no existing route or response changes shape. The visits option pickers are reused unchanged.
- **Transactions and locks:** lock order is always university → meeting → task insert. Create locks the university (it also moves its
  stage); complete locks the university, then the meeting; edit/cancel lock only the meeting and never a university afterwards; the stage
  route locks only the university; task routes lock only tasks. The orders cannot cross. Two concurrent completes: the second waits on
  the university lock, then sees `completed` → 409. The stage advance and the follow-ups run in the meeting's transaction (fail closed:
  a task error rolls the outcome back; a skipped task is logged, never an error, upc-020 TK6).
- **Security (security-and-hardening):**
  - Reads are role-gated (MG14); writes re-check the actor after `FOR UPDATE` (no TOCTOU).
  - IDOR: a contact id from another university is a 422 (N1), participant users must be active partnership staff, the responsible
    employee follows `lead_filter`; the pickers only return what the caller may submit.
  - The link must be `http(s)` (a `javascript:` URL is a 422) and renders with `rel="noopener noreferrer"`; React escapes every free
    text (no `dangerouslySetInnerHTML`).
  - Logs and audit metadata hold ids, codes, keys, counts and field names only — never agenda, notes, discussion points, decisions,
    next action or reasons (contact names and university talks are business-sensitive).
  - CSRF follows the app's cookie + same-origin `sendJson` path; nothing new. No secrets, no new dependencies.
- **Frontend (frontend-ui-engineering):**
  - Reuses `SearchableSelect`, `FormMessage`, `fieldErrors`, `istInputToIso` / `isoToIstInput`, the `.action-card` / `.badge` /
    `.form-error` / `.telecaller-list` styles and the visit pages' layout.
  - View tabs are links with `aria-current="page"`; a single `role="status"` only for the empty list text (rendered only when empty);
    errors `role="alert"`; the link warning is static text (`role="note"`). Every control has a visible label and `aria-invalid` +
    described-by errors; Escape closes the inline outcome/cancel forms.
  - Loading ("Saving…"), empty (per view), past-the-end, error and access-refused states, as the visit pages.
  - Single column on mobile (`auto-fit` grids, table → cards below 640 px, long text `overflow-wrap: anywhere`).

## 9. Browser QA (Phase 5/6)

First pass (no code changes), Playwright against the isolated stack (`http://localhost:13209`), 1280 / 820 / 390 px. Passed: required
fields, a past start and a `javascript:` link placed on their fields, a 500 → "The meeting could not be saved. Try again.", double-click
schedules one meeting, the online-without-link warning, refresh and back keep the view, the form's Cancel discards, Escape closes the
cancel form, a non-actor manager reads without actions and cannot schedule on another owner's university, overseas_admin gets the access
card and no Meetings section, signed out → overseas sign-in, head nav, no horizontal overflow on list / detail / form / university page at
820 and 390 px, no broken images. Console errors were only the deliberate 422 / 500 responses (plus cancelled Next prefetches).

| ID | Severity | Role / page | Finding | Fix |
|---|---|---|---|---|
| QA-01 | Medium | manager / meeting edit → detail | After saving an edit, the detail page showed the pre-edit meeting until a reload (the database held the new values; Next's router cache served the page visited moments before) | `MeetingForm` calls `router.refresh()` after `router.push` (the `UniversityForm` idiom); vitest + e2e reschedule |
| QA-02 | Medium | manager / meeting detail | "Outcome recorded." / "Meeting cancelled." could vanish: the actions card was rendered only while an action remained, so the re-read unmounted it (intermittent e2e failure) | The status card is always rendered (with the cancel reason, who recorded the outcome, or who may change it); vitest page test + e2e ×2 |
| QA-03 | Low | all / form + detail | The "no link yet" warning was unstyled (`.notice` has no CSS) | `form-warning` (the existing amber style); vitest |
| QA-04 | Low | manager / form | With an error under the link, the Location input stretched to the row height | The form's grids align items to the start; verified by screenshot |
