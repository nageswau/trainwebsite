# upc-011 — Travel & visit calendar + partnership events (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". The item answers CL1–CL14 (§1), including **Q-14** (conferences, fairs and webinars without a
university — a new `partnership_events` record? what counts as an overlap?), are **recommended defaults accepted under that
instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals). They are registered that way in `DEC-SCOPE-150`.

**Branch:** `feature/upc-011`, cut from `origin/main` @ `080c07b3` (after #196).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-011, Q-14, Appendix A L352–L365 and L1090.
**Dependencies:** upc-009 (`0130_university_meetings`, `DEC-SCOPE-145`, merged #190) and upc-010 (`0115_university_visits`,
`DEC-SCOPE-130`) are merged on main. This was verified in code: `UniversityMeeting` (+ participants), `UniversityVisit` (+ participants,
events), `services/university_visits.lead_filter`, `STAFF_ROLES`.
**Source:** `EVID-020` §9 (L352–L365): "Management should see a calendar containing: University meetings, University visits,
Conferences, Education fairs, Partner meetings, MoU signing, Webinars, University presentations. This prevents overlapping travel and
meetings."
**Numbering:** migration `0135_partnership_events`, `DEC-SCOPE-150`, API §12BR, RBAC §2.76 (re-check `main` at Phase 9).
**Gate:** `APPROVAL_GATES.md` GATE-09.

**Templates:** bdm-013 (`api/bdm_calendar.py`: ≤ 31-day read-only union, `truncated`, `components/BdmCalendar.tsx` list-of-days
layout with plain-link navigation) and upc-009/upc-010 (partnership roles, `lead_filter`, employee pickers, page shells). None is
changed except that the meeting and visit detail responses gain an additive `overlaps` list (CL11).

## 0. Discovery (Phase 1 evidence)

| Class | Files |
|---|---|
| MUST CHANGE | `models.py` (+`PartnershipEvent`, `PartnershipEventParticipant`, seq), `alembic/versions/0135_partnership_events.py`, new `partnership_event_kinds.py`, `services/partnership_calendar.py`, `services/partnership_events.py`, `api/partnership_calendar.py`, `api/partnership_events.py`, `main.py` (routers), `schemas.py`; web `lib/navigation.ts` (Calendar live + head nav), new `lib/partnershipCalendar.ts`, `components/PartnershipCalendar.tsx`, `components/PartnershipEventForm.tsx`, `components/OverlapNotice.tsx`, pages `/partnership/calendar`, `/partnership/events/new`, `/partnership/events/[id]`, `/[id]/edit`; docs (DEC, API, RBAC, backlog) |
| MAY CHANGE | `services/university_meetings.detail_out`, `services/university_visits.detail_out` (+`overlaps`), their `*Out` schemas, meeting and visit detail pages (show `OverlapNotice`), web tests that count menu entries |
| SHOULD NOT CHANGE | BDM calendar, meeting/visit rules and commands, stage engine, partnership tasks, commission stripping |
| HIGH REGRESSION RISK | shared `models.py` / `schemas.py`; the meeting/visit detail payloads (additive only); `PartnershipMenuCard` "coming soon" counts |

Auth: inline role checks (`User.role`, `partnership_context` for managers) per the 2026-09-28 convention; no `require_*` deps.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| CL1 | The 8 §9 kinds | **University meetings** = upc-009 meetings; **University visits** = upc-010 visits; the other six — **Conference, Education fair, Partner meeting, MoU signing, Webinar, University presentation** (source order and wording) — are `partnership_events.kind` |
| CL2 | Q-14a: an event record | **Yes, new `partnership_events`.** Code `PEV-000001` (`partnership_event_code_seq`). Fields: kind, title (1–200), university (optional; any **active** university, else 422 — the event is EduSphere's own, not a write on the university), starts_on, ends_on (≥ starts_on, span ≤ 31 days), location (≤ 200), notes (≤ 2000), owner, other employees, status |
| CL3 | Dates | Events are **all-day, date ranges** (multi-day allowed; the backlog edge case). A new or changed start or end date is today or later (IST); no time of day (the source gives none) |
| CL4 | Owner | `owner_user_id`. A manager owns their own events; a head picks themselves or an active direct report (upc-010 `lead_filter`). Default: the caller |
| CL5 | Other employees | Active `partnership_manager` / `partnership_head` users other than the owner, ≤ 10 (upc-009 MG7, upc-010 picker reused). A stored participant stays when later deactivated |
| CL6 | Statuses | `scheduled` → `cancelled` (reason 1–1000). No "completed": a past event is simply past. Cancelled events leave the calendar |
| CL7 | Who | Read: partnership managers (with a profile), heads, super_admin; every other role 403. Create: managers and heads. Edit / cancel: the owner or the creator (403 otherwise), scheduled only (409). super_admin reads only |
| CL8 | Calendar range | `GET /partnership/calendar?date_from&date_to&user_id`: inclusive IST dates, ≤ 31 days (else 422, the backlog negative scenario), from ≤ to (else 422). ≤ 500 rows per source; `truncated` when more |
| CL9 | Whose calendar | No `user_id`: a manager → themselves; a head → themselves + their direct reports (team); super_admin → everyone. `user_id`: a manager may name only themselves; a head themselves or a direct report; super_admin any partnership staff user — otherwise 404 "Employee not found". An item is shown when one of its people is in that set. `GET /partnership/calendar/employees` lists the choosable people |
| CL10 | Q-14b: what is an overlap | **The same employee on two items whose time intervals intersect.** People: meeting = responsible + EduSphere participants; visit = lead + other employees; event = owner + other employees. Intervals (IST): a visit occupies its whole day (confirmed date, else proposed date); an event its whole days `starts_on … ends_on`; a meeting `[starts_at, starts_at + 60 min)` (meetings have no duration, MG3 — 60 minutes is the assumed slot). So a meeting during a visit or fair day is an overlap, two meetings 30 minutes apart are, back-to-back hourly meetings are not. Excluded: cancelled meetings, cancelled events, visits closed before they happened (closed without ever reaching Visit Completed). Warnings only — nothing is blocked |
| CL11 | AC2 "warning on create and on the calendar" | Each calendar item carries `overlaps [{employee, item {source, id, code, title}}]` (for people in the calendar's set). The **event, meeting and visit detail** responses carry the same `overlaps` for all their people, so the page the user lands on after creating (or editing) any of them shows the warning. Additive field; no existing field changes |
| CL12 | Window edge | Overlaps on the calendar are computed among the items in the window; an item's own detail computes over the item's own days, so a multi-day event across months is complete on its detail page |
| CL13 | Views | Web `/partnership/calendar?view=week|month&date=&employee=`: week (Mon–Sun, every day listed) and month (calendar month, days with items only); Previous / Today / Next are plain links; an employee `<select>` (GET form) for heads and super_admin. List of days, not a grid (phone reflow, bdm-013 AC4) |
| CL14 | Audit and logs | `partnership_event.{create,update,cancel}` audit rows in the same transaction (ids, code, kind, counts, field names; never title, notes or reason values). Structured log after commit, ids only. The calendar read writes nothing |

Not in scope: blocking overlaps, notifications, iCal export, drag-and-drop, an event list page (the calendar is the list), recurring
events, overlap checks on the meeting / visit forms before saving (follow-up candidate).

## 2. Data model — migration `0135_partnership_events`

- `partnership_event_code_seq`.
- `partnership_events`: id; code String(20) unique; kind String(30) CHECK in the six; title String(200); university_id FK
  `universities` RESTRICT null; starts_on Date; ends_on Date; location String(200) null; notes Text null; owner_user_id FK users
  RESTRICT; created_by_user_id FK users RESTRICT; status String(12) default `scheduled` CHECK in (scheduled, cancelled); cancelled_at
  timestamptz null; cancel_reason Text null; created_at / updated_at.
  CHECKs: `ends_on >= starts_on`; `(status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)`.
  Indexes: `(starts_on, ends_on)`, `owner_user_id`, `university_id`.
- `partnership_event_participants`: event_id FK CASCADE + user_id FK RESTRICT, composite PK.
- Downgrade drops both tables and the sequence. No existing table changes; no data touched.

## 3. API (§12BR)

| Method/Path | Notes |
|---|---|
| `GET /partnership/calendar` | CL8/CL9/CL10 → `{date_from, date_to, today, employee (person or null), truncated, items: [{source (meeting|visit|event), kind (university_meeting|university_visit|<event kind>), id, code, title, starts_on, ends_on, starts_at (meetings) , status, university {id, name}|null, people [person], overlaps [...]}]}` ordered by start |
| `GET /partnership/calendar/employees` | `{items: [person]}` — the people CL9 lets the caller choose |
| `POST /partnership/events` | `{kind, title, university_id?, starts_on, ends_on, location?, notes?, owner_user_id?, participant_user_ids? (≤ 10)}` → `201 {event}`. Unknown keys 422 |
| `GET /partnership/events/{id}` | `{event}` = fields + `university`, `owner`, `created_by`, `participants`, `overlaps`, `permissions {can_edit, can_cancel}` |
| `PATCH /partnership/events/{id}` | Any create field; scheduled only; sent null kind/title/dates/owner 422 |
| `POST /partnership/events/{id}/cancel` | `{reason}` |

Meeting (§12BM) and visit (§12AX) detail items gain `overlaps` (CL11).

## 4. Implementation plan (TDD, one commit per task)

1. **Constants + model + migration** — `partnership_event_kinds.py`; models; `0135`; `test_upc_011_migration.py` (upgrade/downgrade, CHECK parity).
2. **Event writes** — `services/partnership_events.py`, `api/partnership_events.py`, schemas; tests: create stores every field (P1),
   university optional, inactive/unknown university 422, past date 422, ends before starts 422, span > 31 422, owner rule, employees rule,
   other role 403, edit by non-owner 403, cancel then edit 409, audit has no free text.
3. **Calendar union + overlaps** — `services/partnership_calendar.py`, `api/partnership_calendar.py`; tests: all 8 kinds appear (AC1),
   range > 31 422, from > to 422, employee scoping (manager self only / head team / super_admin all / out of scope 404), overlap
   meeting-in-visit-day + event (AC2 positive "education fair week plus two visits"), no overlap for 2 h apart meetings, cancelled
   excluded, multi-day across months (edge), employees list.
4. **Detail overlaps** — event, meeting and visit detail `overlaps` (AC2 on create).
5. **Web lib + calendar page** — `lib/partnershipCalendar.ts` (+ vitest), `PartnershipCalendar.tsx` (+ vitest), page, nav live.
6. **Event pages** — form, detail (with `OverlapNotice`), edit, cancel; meeting/visit detail pages show `OverlapNotice`.
7. **Playwright** `upc-011-partnership-calendar.spec.ts`; docs (DEC-SCOPE-150, §12BR, §2.76, backlog status).

## 5. Acceptance criteria → tests

| AC | Test |
|---|---|
| AC1 all 8 kinds appear | `test_calendar_shows_all_eight_kinds` + e2e |
| AC2 overlap warning on create and on the calendar | `test_event_create_returns_overlap_with_visit`, `test_meeting_detail_shows_overlap`, `test_calendar_flags_overlaps` + e2e |
| N range > 31 days → 422 | `test_range_over_31_days_is_422` |
| E multi-day across months | `test_multi_day_event_across_months` |
| P education fair week + two visits | `test_education_fair_week_with_two_visits` |

## 6. Risks

- Shared schemas: the meeting/visit `*Out` gain a defaulted list — existing clients ignore it.
- The 60-minute meeting slot is an assumption (CL10, `NEEDS_CONFIRMATION`).
- Query cost: three range queries + three participant queries per calendar read, bounded by 500 rows each; detail overlaps reuse the
  same code over the item's own days.

## 7. Browser QA (Phase 5/6)

First pass (no code changes), Playwright against the isolated stack (`http://localhost:13111`), 1280 / 820 / 390 px, as super_admin,
head, two managers and a counselor. Passed: the empty week, bad `view` / `date` fall back to this week, a manager naming a colleague (or a
malformed id) gets "This person is not in your team", the meeting and visit pages show the overlap notice after a meeting is scheduled on a
visit day (AC2), required fields, the 200-character title cap, a past date placed on its field, the event page warns on create, refresh
and back keep the page, a malformed event id is "not found", no horizontal overflow at any width, no broken images, a participant sees the
meeting, a colleague's PATCH is a 403 (no IDOR), the head's team calendar and employee choice, super_admin's "Everyone's calendar" without
"Add an event", a counselor gets the access card (API 403), signed out → overseas sign-in. Console errors were only the deliberate 422
(plus Next prefetches cancelled by signing out).

| ID | Severity | Role / page | Finding | Fix |
|---|---|---|---|---|
| QA-01 | Medium | manager / `/partnership/events/new` | A click between the save's response and the navigation sent a second POST: two identical events (PEV-000056/57) | The form stays locked (busy) after a successful save until the event page replaces it; vitest "never sends twice" + browser (1 POST) |
| QA-02 | Low | all / calendar | The overlap marker was one long red pill repeating the person's name per overlap ("QA Manager … is also at …; QA Manager … is also at …"), a blob on a phone | One amber line per person, "Overlap — Asha Rao: VIS-000003, UMT-000002", each code an underlined link with its title on hover; vitest + e2e + screenshots |
| QA-03 | Low | manager, head / calendar (desktop) | "Add an event" wrapped onto three lines beside the long description | `white-space: nowrap` on the button; verified by screenshot |
