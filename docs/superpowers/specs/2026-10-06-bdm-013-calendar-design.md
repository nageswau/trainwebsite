# bdm-013 — BDM calendar (daily / weekly) (design)

- **Backlog item:** `docs/delivery/BDM_CRM_BACKLOG.md` § bdm-013. **Source:** `EVID-016` §5 "BDM Calendar" (lines 172–196) and §4 Common "Calendar" (1254–1265).
- **Decision:** `DEC-SCOPE-079` (K1–K10 below).
- **Dependencies (merged to `main`):** bdm-006 appointments (PR #58), bdm-008 follow-ups and tasks (PR #71), bdm-010 travel.
- **Migration:** none. **New tables:** none.

## 1. Goal

Each BDM has a read-only calendar of their appointments (meetings, with seminars and workshops flagged), trips, follow-ups and
tasks. It has a day view and a week view. The week view reproduces the §5 example, one line per day:

| Source §5 | Meaning |
|---|---|
| Monday: Hyderabad – Agent Meetings | trip destination + the day's dominant appointment type |
| Tuesday / Wednesday: Vijayawada – College Meetings | the same, on each day the trip covers |
| Thursday: Return Travel | the trip's return date |
| Friday: Follow-ups | a day with only follow-ups / tasks |

Managers read the calendar of any BDM on their team (super_admin: any BDM). Nothing can be edited from the calendar; each item links to its own page.

## 2. Scope

**In:** `GET /api/v1/bdm/calendar`; `/bdm/calendar` (BDM); `/bdm/manager/calendar` (manager / super_admin); a "Calendar" nav entry in both sidebars.
**Out:** drag-and-drop editing; external calendar sync (Q-11); the travel ↔ appointment link (bdm-011); reminders (bdm-012); My Day (bdm-014).

## 3. Decisions (`DEC-SCOPE-079`)

These are **agent-recommended defaults**. On 2026-10-06 the owner told this session to "proceed with recommended answers" and to ask only on
real blockers. They are recorded as such, not as `EXPLICIT_APPROVAL`, and the owner can override any of them.

| # | Question | Default chosen | Why |
|---|---|---|---|
| K1 | Query parameter names | `date_from`, `date_to` (inclusive IST dates), `bdm_user_id` | The backlog writes `from/to/bdm_id` as a sketch. The sibling lists (`/bdm/appointments`, `/bdm/tasks`, `/bdm/manager/trips`) already use these names |
| K2 | Range cap | Both dates required; `date_to - date_from + 1 > 31` → 422; `date_from > date_to` → 422 | The backlog says "capped, e.g. 31 days"; 31 covers a month view later |
| K3 | Whose calendar | BDM: their own; sending `bdm_user_id` → 422 (the sibling rule). Manager: `bdm_user_id` required (422), and it must report to them, else **404** "BDM not found". super_admin: any BDM with a profile, else 404. Other roles → 403 | AC "manager requesting a non-team BDM → 404" |
| K4 | Which rows | Appointments: every status **except cancelled**. Trips overlapping the range, **except cancelled or rejected**. Tasks and follow-ups due in the range, **except cancelled** | A cancelled or rejected item is not on anyone's plan. Completed / done items stay, so the past reads truthfully |
| K5 | "Seminars" | Appointment types `seminar_workshop`, `seminar`, `workshop`, `student_seminar` are flagged `seminar: true` and badged "Seminar" | §5 lists seminars beside meetings; they are appointment types in bdm-006 |
| K6 | Day headline | §4 below | Reproduces §5 |
| K7 | Week | Monday–Sunday containing `date`; default view `week`, default date today (IST); an invalid `view`/`date` falls back to the default | §5's week starts on Monday |
| K8 | Links | Appointment → its detail page; trip → its detail page; follow-up / task → its organization's page (which lists open items) or, with no organization, the Follow-ups list | Tasks have no detail page (bdm-008) |
| K9 | Response bound | At most 500 rows per source; `truncated: true` if any source hit it | 31 days × the 200/day task cap could be large; never hit in real use |
| K10 | Nav | BDM: "Calendar" after My Day. Manager: "Calendar" after Follow-ups | Next to the related pages |

## 4. Day headline (K6), computed in the web app (`lib/bdmCalendar.ts`)

For a day `d`: `A` = the day's appointments, `T` = the trips listed, `dominant` = the most frequent appointment type in `A` (on a tie, the
type of the earliest appointment). Its label is pluralized (`College Meeting` → `College Meetings`).

1. A trip **away** on `d` (`travel_date ≤ d < return_date`, or a same-day trip on `d`): `"{to_place} – {dominant}"`. With no
   appointments: `"Travel to {to_place}"` on its travel date, else `"{to_place}"`.
2. Else a trip **returning** on `d` (`return_date = d > travel_date`): `"Return travel"`, plus `" – {dominant}"` when there are appointments.
3. Else appointments: `"{dominant}"`.
4. Else follow-ups or tasks: `"Follow-ups"` (`"Tasks"` when every item is a task).
5. Else: `"Nothing planned"`.

If two trips are away on the same day, the earliest travel date wins, then the code. Seminar types count like any other type.

## 5. API — `GET /api/v1/bdm/calendar` (`app/api/bdm_calendar.py`)

Query: `date_from`, `date_to` (required dates), `bdm_user_id` (UUID, optional). Response `BdmCalendarOut`:

```json
{
  "bdm": {"id": "…", "full_name": "…", "active": true},
  "date_from": "2026-10-05", "date_to": "2026-10-11", "today": "2026-10-06", "truncated": false,
  "appointments": [{"id": "…", "code": "APT-000012", "day": "2026-10-06", "starts_at": "…", "duration_minutes": 60,
                    "appointment_type": "college_meeting", "status": "scheduled", "seminar": false,
                    "organization": {"id": "…", "name": "…"}}],
  "trips": [{"id": "…", "code": "TRV-000004", "travel_date": "…", "return_date": "…", "from_place": "…", "to_place": "…",
             "mode": "train", "approval_status": "approved", "travel_status": "planned"}],
  "tasks": [{"id": "…", "kind": "follow_up", "title": "…", "due_on": "…", "status": "open", "overdue": false,
             "organization": {"id": "…", "name": "…"} | null}]
}
```

- Three indexed range queries (`ix_bdm_appointments_bdm_starts`, `ix_bdm_trips_bdm_travel_date`, `ix_bdm_tasks_assignee_status_due`),
  each joined to `bdm_organizations` where it has one, so four tables and no N+1. Ordered: appointments by `starts_at, id`; trips by
  `travel_date, code`; tasks by `due_on, created_at, id`.
- The appointment `day` is the IST date of `starts_at` (named `day`, not `date`, so the field does not shadow the type in the schema), and the range is `[date_from 00:00 IST, date_to + 1 00:00 IST)`, using bdm-006's `ist_bounds`.
- A trip is in the range when `travel_date ≤ date_to AND return_date ≥ date_from`, so a trip across the week boundary appears in both weeks.
- Read only: no transaction beyond the read, no audit, no log line (reads of the sibling lists don't log either).
- Errors: 401 signed out; 403 wrong role or a BDM without a profile; 404 BDM not in scope; 422 for a missing date, a bad date or UUID, a reversed range, a range over 31 days, or `bdm_user_id` sent by a BDM / missing for a manager.

## 6. Security review (security-and-hardening)

- **IDOR:** `bdm_user_id` is resolved through scope in SQL (the manager's team or a BDM profile); out of scope looks the same as a
  missing BDM (404). A BDM cannot name another user (422). Each query filters by the resolved user id only.
- **Role escalation:** read-only, so there is no write path. The role is checked first (403).
- **Input:** FastAPI types the dates and UUID; the range cap bounds work. The response cap (K9) bounds size.
- **XSS:** React escapes all text. Links are built from UUIDs the API returns, never from free text.
- **CSRF:** GET only. **SQL injection:** SQLAlchemy expressions only. **Logging:** nothing is logged. **Secrets:** none.
- **Data exposure:** task titles and organization names are already visible to the same callers through `/bdm/tasks` and
  `/bdm/appointments`. Notes, contact details, purpose, costs and remarks are not returned.

## 7. Frontend (frontend-ui-engineering)

- **Pages** (server components, like the sibling pages): `/bdm/calendar?view=day|week&date=YYYY-MM-DD` and
  `/bdm/manager/calendar?view=&date=&bdm=<uuid>`, each with a `loading.tsx`. The API is the gate. The page uses `accessUnavailable` /
  `accessDenied` as its siblings do.
- **Toolbar:** Day / Week links (`aria-current`); Previous / Today / Next links; the range title ("5–11 Oct 2026"). Plain links work
  without JS, keep browser history and are keyboard-reachable (AC5).
- **Manager:** a BDM picker (`SearchableSelect` + `teamMemberSearch`, as on the follow-ups page) in a small client component that pushes
  `?bdm=`. With no BDM chosen the page asks for one; a 404 from the API shows "This BDM is not on your team".
- **Layout:** the week is an ordered list of days. Each day is a `<section>` with an `h4` heading (under the `h3` range title) `Monday 5 Oct — Vijayawada – College
  Meetings`, then a `<ul>` of items: trips (all day), appointments by time, then follow-ups and tasks. Today's day is marked
  "Today" (text, not just colour). The day view shows one such section. On a phone it is a single column that wraps text, so there is
  no horizontal scroll (AC4). It is not a canvas or a grid of fixed-width cells.
- **Items:** a text label for the kind ("Appointment", "Seminar", "Trip", "Follow-up", "Task"), the time in IST, organization or
  route, and a status pill for appointments / trips / tasks that are not simply scheduled or open (STATUS_LABEL from bdm-006,
  "Draft" / "Submitted" for trips, "Done" / "Overdue" for tasks).
- **States:** loading (`loading.tsx`, `role=status`); empty week or day ("Nothing planned this week."); API failure → an inline
  `role=alert` message with a "Try again" link to the same URL; `truncated` → the note "Some items are not shown."

## 8. Acceptance criteria (testable)

1. **AC1** Every item type appears on the right day or days. Appointment on its IST date (incl. 23:30 IST); a trip on every day from travel to return; a task on its due date; cancelled/rejected excluded. *(API + web unit tests)*
2. **AC2** The week view reproduces the §5 layout: Monday "Hyderabad – Agent Meetings", Tue/Wed "Vijayawada – College Meetings", Thu "Return travel", Fri "Follow-ups". *(web unit test on the headline function, page test, e2e)*
3. **AC3** A range over 31 days → 422. *(API test)*
4. **AC4** The phone layout has no horizontal scroll (320 / 375 px). *(Playwright + browser)*
5. **AC5** Keyboard navigable: every control and item link is reachable by Tab in reading order, with a visible focus ring. *(browser)*
6. **AC6** Manager reads a team BDM's calendar; a non-team BDM → 404; a BDM sending `bdm_user_id` → 422; another role → 403. *(API test)*
7. **AC7** Each item links to its page (K8). *(web unit test + browser)*
8. **Edge:** a multi-day trip across a week boundary appears in both weeks; an empty week shows the empty state.

## 9. Regression risks

Low. The change is additive: a new router, two new pages, and two nav entries. Tests that count nav items or snapshot the sidebars
may need the new entry. No existing query, schema or migration changes.

## 10. Testing (lite)

Backend: `tests/test_bdm_013_calendar.py` (scope, range, inclusion, IST boundary, week-boundary trip). Web: `tests/lib/bdmCalendar.test.ts`
(days, headline, plural, placement) and `tests/components/BdmCalendar.test.tsx` (render, links, empty, error). E2E:
`tests/e2e/bdm-013-calendar.spec.ts` (seed through the API, week + day, phone width). The owner runs the full suites.
