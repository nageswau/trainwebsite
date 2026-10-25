# ccrm-032 — Counselor action dashboard (design)

Decision `DEC-SCOPE-277`, API §12GD, RBAC §2.191, **no migration**. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-032`
(Counselor CRM Specification §12, UNVERIFIED). Dependencies merged on main @ d44fe723: ccrm-001, 003, 012, 014, 019, 023, 026, 029.
The owner pre-authorised recommended defaults for this session; every D-row below is the builder's call, `NEEDS_CONFIRMATION`.

## 1. Requirement (backlog)

Sections: new / not-contacted leads; today's appointments, calls, follow-ups; overdue tasks and leads without a next action; students
with pending documents, applications not ready; submitted awaiting decision; offers with conditions/deadlines approaching; visa
appointments, pending decisions, enrolment tasks; quick search (ccrm-012) and filters. Every figure computed live. FE: replace the
generic `PortalPage` dashboard for the counselor. BE: one aggregate endpoint. Also closes ccrm-003's deferred acceptance ("a follow-up
the counselor creates shows in their dashboard").

## 2. Existing behaviour (main @ d44fe723)

`/overseas/counselor/dashboard` renders `PortalPage` → `PortalSection` with the ccrm-012 quick search as its lead, three tiles
(Applications, Awaiting documents — ccrm-001, Offers) and the application table from `services/portal.py`. Nothing lists leads, tasks,
follow-ups, appointments, offers or visa work there.

## 3. Decisions (defaults, `NEEDS_CONFIRMATION`)

| # | Question | Default |
|---|---|---|
| D1 | Who | The **overseas counselor** only (`role=counselor`, `division=overseas`); anyone else 403. Own records only — the request names nobody. Read-only, not audited (ccrm-036 P9 precedent). |
| D2 | Scope | Leads: `lead_handover.counselor_scope` (owner = me). Applications: `counselor_id = me` (the dashboard table's scope), archived students excluded (ccrm-040), `withdrawn` excluded, and outcomes that are terminal or `on_hold` excluded (the ccrm-030 `_not_paused` rule). Students: csc-001 `visible_student_ids`, not archived. Tasks: `counselor_user_id = me`. Appointments: `staff_id = me` (lead and student). Calls: `caller_user_id = me`. |
| D3 | "Today" | The India calendar day of the DB clock (`db_now` / `today_ist`), as every counselor surface. |
| D4 | "Approaching" window | **14 days** ahead (a fixed constant), past-due items included and flagged overdue. |
| D5 | Section definitions | See §4. |
| D6 | Size | Each section returns its full `count` and at most **10** items (soonest first) plus `more`; the section links to the full list. |
| D7 | Filters | The quick search stays; each section links to the existing filtered list (leads by stage, tasks, applications) — no new dashboard-level filter. |
| D8 | Old tiles + table | Kept below the sections (ccrm-001's tiles and the application table are unchanged; the payload remains the page gate). |
| D9 | Failure | The panel reads its own endpoint inside `Suspense`; a failure shows "Dashboard sections are unavailable right now" + Try again, and the rest of the page still works (AGN-018 precedent). 401 → access-unavailable card. |
| D10 | Not-contacted | Lead stages `new`, `assigned`, `first_call_pending` (no contact made yet); these are not repeated under "no next action". |

## 4. Sections (`GET /counselor/dashboard`)

Response `{today, window_days, sections: {key: {count, more, items[]}}}`; every item has `id`, `label`, `detail`, `date`
(nullable), `overdue` (bool), `href`.

| Key | Rows |
|---|---|
| `new_leads` | My leads in D10 stages, newest first. → `/overseas/counselor/leads/{id}` |
| `appointments_today` | My appointments (lead or student) today in `scheduled/confirmed/rescheduled`, by time. Lead → lead page; student → 360. |
| `calls_today` | My lead calls logged today, latest first. → lead page. |
| `follow_ups` | Open follow-ups on my leads due today or earlier (overdue flagged), soonest first. → lead page. |
| `overdue_tasks` | My open tasks due before today, oldest first. → `/overseas/counselor/tasks`. |
| `no_next_action` | My open leads past first contact (not D10 stages, not closed, not `application_enrollment`/`converted`) with no next action. → lead page. |
| `pending_documents` | Visible students with an open document request or a document awaiting verification. → 360. |
| `not_ready` | Applications at `university_selection`, not submitted, `documents_completed_on` empty (ccrm-019 not complete). |
| `awaiting_decision` | Applications at `university_selection` with `submitted_on` set; `decision_due_on` shown, overdue flagged. |
| `offers_due` | On my applications: active+considering offers with a deadline, open offer conditions with a due date, required pending deposits with a due date — each due within D4. |
| `visa` | Undecided visa cases: appointment within D4 ("Visa appointment"), or status `submitted`/`additional_info_requested`/`decision_pending` ("Decision pending"). |
| `enrolment` | Visa approved and enrolment not confirmed ("Confirm enrolment"); enrolled with arrival not confirmed ("Confirm arrival"); overdue once the course start date has passed. |

Application hrefs: the student's 360 when the application has a direct student, else the applications list narrowed by university and
intake (the ccrm-012 QA-01 precedent).

## 5. Frontend

`components/CounselorDashboardPanel.tsx` (server component, `serverApi`), sections in the BdmMyDay grid (`panel` cards, one heading per
section with its count, a list, an empty line, a "View all" link). Overdue items carry a `badge` "Overdue". `PortalPage` counselor
dashboard branch: lead = quick search + `<Suspense fallback={skeleton}>` panel. Types in `lib/types.ts`.

## 6. Risks / regression

Read-only; no writes, no migration. Regression: ccrm-001 tiles, ccrm-012 search on the same page, `PortalPage` other roles. Query count
~2 per section (count + items), all indexed on owner/counselor columns.
