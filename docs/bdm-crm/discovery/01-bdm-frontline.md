# BDM CRM user-guide discovery: Overseas BDM portal (Agent / School BDM)

> **Evidence appendix** for `docs/bdm-crm/documentation-analysis.md`: raw read-only source discovery (master planning session S1, 2026-10-17, code `main` @ `6fee294d`). Field-level detail for the module sessions. Not browser-verified. Where this file and the browser disagree, the browser wins and this file gets an annotation; it is not silently trusted.

Source: repo `edusphere` at main 6fee294d (worktree `.claude/worktrees/bdm-docs`). Read-only discovery; nothing was run against a live stack.
Path prefixes: `web/` = `apps/web/`, `api/` = `apps/api/app/`. Every browser call goes to `/api/v1/...`.
Scope: role `bdm` with `bdm_type` `agent` or `school` (division `overseas`). Covers everything under `web/app/bdm/*` except `/bdm/manager/*` and `/bdm/sign-in`; the sign-in chooser appears only as context. College BDMs (division `it`) are out of scope, but this file notes where they differ. Decision IDs come from `docs/decisions/PRODUCT_DECISION_REGISTER.md` and backlog items from `docs/delivery/BDM_CRM_BACKLOG.md`. They are labels only; code is the authority.

Legend: **VERIFICATION REQUIRED** = code alone cannot settle it (needs a running stack, a screenshot or an owner answer). `NEEDS_CONFIRMATION` = an open owner/product decision.

Layout: Part 0 (identity and the master difference table) · Part A (shell, My Day, notifications, calendar, meeting requests, university view) · Part B (organisations, contacts, type profiles, pipeline, onboarding, panels, leads, MoUs) · Part C (appointments, follow-ups, activities) · Part D (travel, daily report) · (a) feature rows · (b) test data · (c) open questions.

---

## PART 0 — Who the Overseas BDM is

| Topic | Rule (code) | Evidence | Decision |
|---|---|---|---|
| Role / types | Role `bdm`; `bdm_profiles.bdm_type` ∈ `agent` / `school` / `college`. Type is fixed after creation: "BDM type cannot be changed" (422) | `api/services/bdm.py:19,126-127` | DEC-SCOPE-055 (bdm-001) B7 |
| Division | `BDM_DIVISION = {"college": "it", "agent": "overseas", "school": "overseas"}`. Agent and School BDMs belong to **Overseas** | `api/services/bdm.py:20` | DEC-SCOPE-055 D3 |
| Who provisions | `super_admin` → all types; `overseas_admin` → agent and school; `it_admin` → college only. Otherwise 403 "Your role cannot manage <type> BDMs" | `api/services/bdm.py:21-25,34-41` | DEC-SCOPE-055 D10 |
| Sign-in | Agent/School BDM signs in at **`/overseas/login`**. The `/bdm/sign-in` chooser has buttons **College BDM** (`/it/login`) and **Agent / School BDM** (`/overseas/login`); managers sign in at Administration | `web/app/bdm/sign-in/page.tsx:16-20` | B9 |
| Wrong portal | Correct password but a different division → 403 "Use the correct EduSphere portal for this account: sign in at <path>" | `api/api/auth.py:110-112` | bdm-001 QA-07 |
| Landing | `ROLE_DASHBOARD_PATH.bdm = "/bdm/my-day"`; `/bdm` redirects to `/bdm/my-day` | `web/lib/navigation.ts:46`; `web/app/bdm/page.tsx:4-5` | bdm-001 QA-09 |
| Gate on every page | `GET /api/v1/bdm/me` (`api/api/bdm.py:62-69`) → `bdm_context`: another role → 403 "BDM role required"; no profile → 403 "BDM profile not set up — contact your administrator" | `api/services/bdm.py:138-145` | — |
| RBAC bundle | `bdm` → `{"bdm:self"}`. Type, own and team scope are enforced in the services, not by the bundle | `api/core/rbac.py:50-51` | DEC-SCOPE-055 |
| Role pill | "<Type> BDM", i.e. **"Agent BDM"** or **"School BDM"** (`BDM_TYPE_LABEL`). Exception: `/bdm/universities/[id]` shows just "BDM" | every page's `roleLabel`; `web/lib/bdm.ts:16` | — |
| Module read scope vs write scope | A BDM reads **every organisation in their own module** (agent BDMs see the Agent module, school BDMs the School module) but changes only the organisations **assigned to them**. Details in Part B.0 | `api/services/bdm_organizations.py` (see B.0) | DEC-SCOPE-060 D11 (Q-02) |
| Pipelines | Three catalogues in `api/bdm_stages.py:20-69`. Only **manual** stages are stored or set by the BDM (`MANUAL_STAGES`, `:70`); **live** stages come from the onboarded partner record and **volume** stages are counted | `api/bdm_stages.py`; model CHECK `api/models.py:2986` | DEC-SCOPE-071 (bdm-004) |
| Agent manual stages | Agent Prospect · Contacted · Meeting Scheduled · Meeting Completed · Interested · Proposal / Agreement · Agreement Signed. Live: Agent Onboarding · Master Login Created · Staff Logins Created · Active Agent. Volume: Students · Applications · Enrollments | `api/bdm_stages.py:21-36` | DEC-SCOPE-071 |
| School manual stages | School Prospect · Contacted · Meeting · Presentation · Proposal · Negotiation · MoU · Signed. Live: School Onboarding · Teachers / Parents / Students Created · Career Guidance · Psychometric · Student Profile Building · University Planning | `api/bdm_stages.py:37-52` | DEC-SCOPE-071 |
| College (contrast) | College Prospect … MoU Signed · College Activated (manual), then 6 volume stages; the BDM is in the IT division | `api/bdm_stages.py:53-68` | — |
| Agent status | 8-value derived status (Prospect, Contacted, Meeting, Interested, Agreement, Onboarding, Active, Inactive). It is never stored; nothing maps to Inactive except through the linked Agent Organization | `api/bdm_stages.py:72-87` | DEC-SCOPE-071 S4 (D13) |
| MoU Signed → stage | A signed MoU moves the pipeline forward only, to agent `agreement_signed` / school `signed` / college `mou_signed` | `api/bdm_stages.py:90` | DEC-SCOPE-078 M5 |
| Sidebar | **One `BDM_NAV` for every type**: My Day · Calendar · Organizations · Pipeline · MoUs · Appointments · Follow-ups · Requests · Activities · Daily report · Travel · Notifications · Profile · Management tasks | `web/lib/navigation.ts:72-81` | DEC-SCOPE-055 and later items |
| Time zone | Every page labels times "India time (IST)" | page headers | — |

### 0.1 Master Agent-BDM vs School-BDM difference table (summary; detail is in each part)

| Area | Agent BDM | School BDM | College BDM (out of scope) | Part |
|---|---|---|---|---|
| Portal / division | `/overseas/login`, overseas | `/overseas/login`, overseas | `/it/login`, it | 0 |
| Sidebar | same `BDM_NAV` | same | same | A1.2 |
| My Day overview tiles | Agent tiles (some "not tracked") | School tiles | College tiles | A2.3 |
| Monthly target KPIs | Agent KPI set; several "(not tracked)" | School KPI set | College set | A2.4 |
| Organisations visible | Agent-module orgs | School-module orgs | College-module orgs | B.0, B.7 |
| Pipeline | 7 manual + 4 live + 3 volume | 8 manual + 6 live | 8 manual + 6 volume | 0, B.3.3 |
| Agent status badge | yes | no | no | B.7 |
| Onboarding handover | at stage Agreement Signed → linked to an Agent Organization (AGN) | when the MoU is Signed/Active → School created or linked | none | B.3.5 |
| Organisation panel | Agent performance | School activity | Business | B.3.6 |
| Appointment types | common 8 + 8 agent types | common 8 + 10 school types | common 8 + college types | C.0 |
| Meeting-report outcomes | Agent list (no Reschedule → no "Book the next meeting") | Common list (with Reschedule) | Common list | C.0 |
| Meeting requests | agent requests from overseas telecallers | school requests | — | A5 |
| Travel | identical | identical | identical | D.7 |
| Daily report tiles | 11 agent tiles, 3 always "Not tracked" | 11 school tiles | college tiles incl. "Travel completed" | D.6.1 |
| Profile section on orgs | follows **org type**, not BDM type (an agent BDM can create a School/College/University-type org) | same | same | B.2.2, B-Q1 |

---

## PART A1 — Shell, navigation, account (NAV)

### A1.1 Gate, sign-in, role pill

| Topic | Rule (code) | Evidence | Decision |
|---|---|---|---|
| Role / module | Role `bdm`, `bdm_profiles.bdm_type` ∈ `agent`/`school`/`college`. Division follows the type: college → `it`, agent/school → `overseas` | `api/services/bdm.py:20` (`BDM_DIVISION`) | DEC-SCOPE-055 (bdm-001) D3 |
| Sign-in | Agent/School BDMs sign in at **`/overseas/login`**, College BDMs at `/it/login`. `/bdm/sign-in` is only a chooser: heading **"BDM sign-in"**, text "Choose the portal for your module. BDM Managers sign in at Administration.", buttons **College BDM** / **Agent / School BDM** | `web/app/bdm/sign-in/page.tsx:16-20` | B9 |
| Wrong portal | Correct password, wrong division → 403 **"Use the correct EduSphere portal for this account: sign in at <path>"** | `api/api/auth.py:110-112` | bdm-001 QA-07 |
| Landing | `ROLE_DASHBOARD_PATH.bdm = "/bdm/my-day"`; `/bdm` redirects to `/bdm/my-day` | `web/lib/navigation.ts:46`; `web/app/bdm/page.tsx:4-5` | bdm-001 QA-09 |
| Gate on every page | `GET /api/v1/bdm/me` (`api/api/bdm.py:62-69`) → `bdm_context`: another role → 403 **"BDM role required"**; no profile → 403 **"BDM profile not set up — contact your administrator"** | `api/services/bdm.py:138-145` | — |
| Manager on My Day | A `bdm_manager` refused by `/bdm/me` on `/bdm/my-day` is redirected to the manager dashboard | `web/app/bdm/my-day/page.tsx:20-24,38-39` | K10 |
| Role pill | `"<Type> BDM"` → **"Agent BDM"** / **"School BDM"** (College: "College BDM"). Exception: `/bdm/universities/[id]` shows plain **"BDM"** | `web/lib/bdm.ts:16`; every page `roleLabel`; `web/app/bdm/universities/[id]/page.tsx:23` | — |
| Times | Pages say "Times are India time (IST)." | many pages | — |

### A1.2 Sidebar (BDM_NAV, `web/lib/navigation.ts:72-81`)

**My Day · Calendar · Organizations · Pipeline · MoUs · Appointments · Follow-ups · Requests · Activities · Daily report · Travel · Notifications · Profile · Management tasks**

| Item | Agent BDM | School BDM | College BDM (out of scope) |
|---|---|---|---|
| Sidebar entries | identical | identical | identical — **one `BDM_NAV` for every type**; no type-specific menu |
| Page headings using the type | "Agent organizations", "Agent pipeline", "Agent MoUs", "Agent overview" | "School …" | "College …" |
| "Management tasks" | shared `MANAGEMENT_TASKS_NAV` → `/account/management-tasks` (`navigation.ts:11,80`, mgmt-028 MT14). Out of this file's scope — **VERIFICATION REQUIRED** what a BDM sees there | same | same |

- Unread badge on **Notifications**: `bdmNav()` → `GET /api/v1/workflows/notifications/unread-count` (`web/lib/bdmNav.ts:6-15`); a failed count hides the badge, never fails the page.
- Shell (`web/components/PortalShell.tsx:17`): logo, role pill (`<Type> BDM` / name), nav, footer **Change password** (`/account/password`), **My profile** (`/account/profile`), **Sign out**; top bar **"EduSphere Portal"** + name + unread icon; mobile menu repeats Change password, My profile and nav ("Notifications (N unread)").
- Access failure card (`web/components/AccessUnavailable.tsx:21-38`): heading **"Access unavailable"** + server message; button **"Go to your dashboard"** (signed-in) or return-to-login (401); **Sign out**. For "BDM profile not set up — contact your administrator" the dashboard button is suppressed (the user is already on it) — `:16-19,23,34`.

### A1.3 Profile — `/bdm/profile` (`web/app/bdm/profile/page.tsx:10-31`)

- Eyebrow "Profile", heading **"My profile"**, text **"Your details as recorded by your administrator. Contact them to change anything."**
- Read-only `<dl>` (`web/components/BdmProfileCard.tsx:7-18`): **Name, Employee ID, Module** (Agent/School/College), **Designation, Department, Territory, Mobile, Email** ("—" when empty), **Reporting manager** (suffix " (inactive)"), **Status** (Active/Inactive). No form, no write API on this page.
- API: `GET /api/v1/bdm/me` (`api/api/bdm.py:62`).

### A1.4 Generic account pages (shell footer)

| Page | BDM behaviour | Evidence |
|---|---|---|
| `/account/profile` | `nameLocked` is only for `telecaller`/`partnership_manager` → for a BDM **Name and Phone are both editable** | `web/app/account/profile/page.tsx:70` |
| `PATCH /api/v1/auth/me` | `bdm` is **not** in `PHONE_ONLY_ROLES` → a BDM can change `full_name` and `phone` (only server-owned profile keys `school_id`, `university_id`, `assigned_grade`, `assigned_section` are refused with 403 "<key> cannot be changed here"). Audit `profile.update` | `api/api/auth.py:35,333-366` |
| `/account/password` | shared page, heading **"Change your password"** (`web/app/account/password/page.tsx:59`); no BDM-specific copy found | — |

**Product finding NAV-1:** `/bdm/profile` says "Contact them to change anything", yet `/account/profile` lets the BDM rename themselves and change mobile — **VERIFICATION REQUIRED** (owner: should `bdm` join `PHONE_ONLY_ROLES` like telecallers?).

---

## PART A2 — My Day — `/bdm/my-day` (DAY)

Page `web/app/bdm/my-day/page.tsx:28-70`; component `web/components/BdmMyDay.tsx`; types `web/lib/bdmMyDay.ts`. API `GET /api/v1/bdm/my-day` (`api/api/bdm_my_day.py:125-181`) — own records only, IST "today", read-only. DEC-SCOPE-097 (bdm-014).

### A2.1 Header

Eyebrow **"My Day"**, heading **"Welcome, <full name>"**, line "Employee ID <id> · <territory> · **View profile**" (territory only when set), "Times are India time (IST)." If the day can't be read: **"Unable to load your day."** + **Try again** (`page.tsx:58-64`).

### A2.2 Sections (common to every type)

| Section | Content | Empty state (text + button) | Server rule |
|---|---|---|---|
| **"Today's appointments: N"** | rows "<h:mm AM> — <organization>" → `/bdm/appointments/<id>`; a status pill unless `scheduled`; if >50: "Showing the first X of N appointments. **Open the calendar**" | "No appointments today." + **Book an appointment** → `/bdm/appointments/new` | own, today IST, status ≠ cancelled, limit 50 (`bdm_my_day.py:21,54-55,139-143`) |
| **"Upcoming travel"** | next 5 trips: "<18 Sep> — <from> → <to>", sub-line "No appointments scheduled" / "N appointment(s) scheduled"; link **All travel (N)** | "No upcoming travel." + **Plan a trip** → `/bdm/travel/new` | own, `travel_date > today`, not cancelled, not rejected (`:22,58-59,147-151`) |
| **"Follow-ups"** + "Due today or overdue." | grouped lines: "N <Org type> follow-up(s)", "N MoU follow-ups", "N follow-ups without an organization"; link **View follow-ups** | "No follow-ups due." + **View follow-ups** | open `follow_up` tasks assigned to me with `due_on <= today` (`:62-63,153-159`); text `web/lib/bdmMyDay.ts:39-44` |
| **"<Type> overview"** + "Today, from your own records." | KPI tiles; untracked tile shows badge **"Not tracked yet"** + note | — | tiles per type, `TILES` (`:31-48`) |
| **"Monthly targets — <Month YYYY>"** (`web/components/BdmTargetsCard.tsx`) | one line per KPI that has a target: "<label> — achieved / target (pct%)", or "target N (not tracked)" | "No targets set for this month yet."; read failure "Unable to load your targets right now." | `GET /api/v1/bdm/targets` (`api/api/bdm_targets.py:32-36`), `editable=False`; targets are set by the manager (DEC-SCOPE-103, bdm-016) |
| **"Meeting requests"** (`web/components/MeetingRequestsCard.tsx`) | "N pending request(s) — accept or decline from the request." + next 5: "<MRQ-code> · <type> · <organization> · <IST time>[ · for you]"; link **Open requests** | "No pending meeting requests."; failure "Unable to load your meeting requests right now." | `GET /api/v1/bdm/meeting-requests?status=pending&limit=5` |

### A2.3 Overview tiles — Agent vs School (`api/api/bdm_my_day.py:31-48,92-122`)

| # | Agent BDM tile | Counts | School BDM tile | Counts |
|---|---|---|---|---|
| 1 | **Today's appointments** (T-A1) | = today's appointments | **School appointments** (T-S1) | today's appts at `school` orgs |
| 2 | **Today's agent meetings** (T-A2) | today's appts of type `agent_meeting`/`agent_visit` | **Principal meetings** (T-S2) | type `principal_meeting` |
| 3 | **Agents to follow up** (T-A3) | distinct agent orgs with an open follow-up due ≤ today | **Management meetings** (T-S3) | type `management_meeting` |
| 4 | **New agent leads** (T-A4) | agent orgs assigned to me created today | **Follow-ups** (T-S4) | open follow-ups due ≤ today (any org) |
| 5 | **Pending agreements** (T-A5) | my live agent orgs whose current MoU is `proposal_sent`/`under_negotiation`/`draft_shared` | **School visits** (T-S5) | my activities with channel `visit` today |
| 6 | **Agents awaiting onboarding** (T-A6) | **Not tracked yet** — "Agent onboarding requests are not recorded in EduSphere yet." | **Proposals** (T-S6) | my live school orgs with current MoU `proposal_sent` |
| 7 | **Agent-related tasks** (T-A7) | open `task` kind due ≤ today at agent orgs | **MoUs pending** (T-S7) | current MoU in `discussion_started`/`proposal_sent`/`under_negotiation`/`draft_shared` |
| 8 | **Travel for today/tomorrow** (T-A8) | live trips overlapping today–tomorrow | **School activities** (T-S8) | today's appts of seminar/workshop/orientation/presentation types |

College (out of scope): T-K1..K8, with T-K7 "MoU follow-ups" not tracked.

**Product finding DAY-1:** T-A6 says agent onboarding requests are "not recorded", but `services/bdm_onboarding.py` (bdm-019) now has onboarding requests for agent organisations — tile text may be stale. **VERIFICATION REQUIRED.**

### A2.4 Target KPIs per type (`api/services/bdm_metrics.py:404-447`)

Card lists only KPIs with a target set. Type list = own list + common list (`_COMMON`), de-duplicated.

| Agent BDM KPIs | School BDM KPIs |
|---|---|
| New Agent Leads; Agent Meetings; New Agents (not tracked); Agreements Signed; Active Agents (not tracked); Agent Students (not tracked); Applications (not tracked); Enrollments (not tracked); + common College Meetings, New Colleges, Appointments, MoUs, Student Leads | Schools Contacted; School Meetings; Presentations; Proposals; MoUs; Active Schools; Students Onboarded; Career Guidance; Psychometric Tests; + common College Meetings, Agent Meetings, New Colleges, New Agents (not tracked), Appointments, Student Leads |

Not-tracked notes: "Not tracked yet: agent onboarding links arrive with the agent onboarding handover." / "Not tracked yet: Agent CRM records are not linked to BDM organizations." (`bdm_metrics.py:400-401`). There is **no BDM targets page** — only the My Day card.

---

## PART A3 — Notifications — `/bdm/notifications` (NOTIF)

Page `web/app/bdm/notifications/page.tsx:11-37`: eyebrow "Notifications", heading **"Your notifications"**; `SchoolNotificationList readBeforeOpen` — each item: **title** (+ **new** badge if unread), body, IST date/time, button **Open** (marks read before navigating) (`web/components/SchoolNotificationList.tsx:35-62`). Empty: **"No notifications yet. Your reminders (appointments, travel, MoUs, follow-ups) and trip decisions appear here."** API `GET /api/v1/workflows/notifications` (shared).

### A3.1 What a BDM receives

| Kind | Title | When (IST) | Body (literal pattern) | Link / action links | Channel | Evidence |
|---|---|---|---|---|---|---|
| Appointment, day before | **"Appointment reminder"** | 09:00 the day before (can still fire later that day); statuses scheduled/confirmed/rescheduled | "Tomorrow at <hh:mm AM>. Organization: <org>. Contact: <name>. Purpose: … Location: …" + "Please confirm your appointment." unless confirmed | `/bdm/appointments/<id>`; email links **Confirmed** (not if already confirmed), **Reschedule**, **Cancel** → `?action=confirm|reschedule|cancel` | in-app + email | `api/services/bdm_reminders.py:113-122` |
| Appointment, 1 h before | **"Appointment in 1 hour"** | exactly 1 h before start (until start) | "Your appointment with <org> is at <time>. Location: …" | **View appointment** | in-app + email | `:125-130,133-141` |
| Trip, day before | **"Travel reminder"** | 09:00 the day before; trip `approved` + `planned` | "Tomorrow (<dd Mon YYYY>): travel to <place>. BDM: <name>. Purpose: … Appointments: N." | **View Appointments** / **View Expenses** / **Add Remarks** (anchors `#trip-appointments`, `#trip-costs`, `#trip-remarks`) | in-app + email | `:145-165` |
| Follow-up / task due | **"Follow-up due today"** / **"Task due today"** | 09:00 on due day; open tasks | "<title>. Organization: <org>. Due <date>." | `/bdm/follow-ups?kind=<kind>`, **View follow-ups** / **View tasks** | in-app + email | `:169-189` |
| MoU follow-up | **"MoU follow-up"** | every 5 days while current MoU is `proposal_sent`/`draft_shared` | "<org>: the proposal was sent / the draft was shared N days ago. Follow up with the contact person." | `/bdm/organizations/<id>#org-mou`, **View MoU** | in-app + email | `:193-224` |
| MoU renewal | **"MoU renewal due"** | 30 days before an `active` MoU's valid-until | "<org>: the MoU is valid until <date>. Plan the renewal with the contact person." | same | in-app + email | `:210-230` |
| Trip decision | **"Trip approved"** / **"Trip not approved"** | on manager decision | "<place line>" | `/bdm/travel/<id>` | in-app only | `api/api/bdm_travel.py:130-135` |
| Onboarding outcome | **"School onboarded"** / **"Agent onboarded"** / **"<Type> onboarding not approved"** | on admin decision (bdm-019) | "<ORG-code> · <name> is now onboarded (School ID …)" / "… is now linked to the agent organization <name> (<prefix>)" / "…: <reason>" | `/bdm/organizations/<id>` | in-app only | `api/services/bdm_onboarding.py:188-195`; `api/api/bdm_onboarding.py:65-68` |
| Handover | **"Work handed over to you"** | admin deactivates/hands over another BDM's work | "N organizations, N appointments and N follow-ups/tasks from <name> are now yours." | `/bdm/organizations` | in-app + email | `api/services/bdm_lifecycle.py:112-119` |

Rules: reminder engine runs every 5 min; owner must be active at fire time; dedupe key per kind/record/time (a rescheduled time = a new reminder); bodies carry no phone/email (`bdm_reminders.py:1-8`). DEC-SCOPE-102 (bdm-012).

**Product finding NOTIF-1:** no notification is created when a telecaller files a meeting request (no `_notify_user` in `api/api/bdm_meeting_requests.py` / `services/bdm_meeting_requests.py`); the BDM learns of it only via My Day card / Requests page. **VERIFICATION REQUIRED** (intended per MR spec?).

---

## PART A4 — Calendar — `/bdm/calendar` (CAL)

Page `web/app/bdm/calendar/page.tsx:15-41`; component `web/components/BdmCalendar.tsx`; helpers `web/lib/bdmCalendar.ts`. API `GET /api/v1/bdm/calendar?date_from&date_to` (`api/api/bdm_calendar.py:52-100`). DEC-SCOPE-079 (bdm-013).

- Eyebrow "Calendar", heading **"Your calendar"**, text "Appointments, travel, follow-ups and tasks. Read-only; open an item to change it. Times are India time (IST)."
- URL `?view=day|week&date=YYYY-MM-DD`; default **week** (Monday–Sunday), invalid date → today (`bdmCalendar.ts:31-40`).
- Toolbar: range title (e.g. "15–21 Sep 2026"), buttons **Day** / **Week**, **Previous day|week**, **Today**, **Next day|week**.
- Each day: "<Weekday d Mon>" + **Today** badge + " — " + headline: "<to_place> – <Type plural>", "Travel to <place>", "Return travel", "<Type plural>", "Tasks", "Follow-ups" or **"Nothing planned"** (`bdmCalendar.ts:89-99`).
- Item rows:

| Badge | Row text | Pills | Link |
|---|---|---|---|
| **Trip** | "Trip <code>" + "<from> → <to> · Departs / Away / Return travel / Day trip" | Draft / Submitted (by approval) or In progress / Completed (when approved) | `/bdm/travel/<id>` |
| **Appointment** / **Seminar** (types seminar_workshop, seminar, workshop, student_seminar) | "<HH:MM> · <duration>" + "<Type label> — <organization>" | status unless scheduled | `/bdm/appointments/<id>` |
| **Task** / **Follow-up** | "<title> — <organization>" | **Done**, **Overdue** | org page, else `/bdm/follow-ups` |

- Messages: "Some items are not shown." (truncated >500 per source), **"Nothing planned this week|day."**, failure **"Unable to load the calendar."** + **Try again**.
- Server rules: own calendar only; a BDM passing `bdm_user_id` → 422 "bdm_user_id is only for managers"; range ≤31 days ("The calendar shows at most 31 days"); `date_from > date_to` → 422; excludes cancelled appointments, cancelled/rejected trips, cancelled tasks (`bdm_calendar.py:27-44,60-84`).
- Agent vs School: identical page; appointment type labels differ only by the types each module books.

---

## PART A5 — Meeting requests — `/bdm/meeting-requests`, `/bdm/meeting-requests/[id]` (MEET)

DEC-SCOPE-098 (tel-019, MR1-MR12). API §12S. Requests are filed by telecallers (`POST /api/v1/telecaller/meeting-requests`).

### A5.1 Scope and states

| Topic | Rule | Evidence |
|---|---|---|
| Request types → BDM type | `agent` → Agent BDM; `school` → School BDM; `college` and `corporate` → College BDM | `api/models.py:3319-3320` |
| Type labels | "Agent meeting", "School meeting", "College meeting", "Corporate meeting" | `api/services/bdm_meeting_requests.py:33` |
| What a BDM sees | requests of **their own bdm_type** that are either **named for them** or in the **pool** (unassigned, always pending), plus ones they decided | `services/bdm_meeting_requests.py:83-93` |
| Out of scope | 404 **"Meeting request not found"** (another type, someone else's, taken from the pool) | `:32,102-110` |
| Statuses | `pending` → **Pending**, `accepted` → **Accepted**, `declined` → **Declined**; decision is final | `api/models.py:3321`; `web/lib/meetingRequests.ts:16` |
| Who decides | role `bdm` only, request pending and named for me or pooled (`permissions.can_accept/can_decline`) | `services/bdm_meeting_requests.py:127-130` |
| Already decided | 409 **"This request is already <status>"** | `:113-115` |
| Order | pending first (named-for-me before pool, soonest proposed first), then decided (latest first) | `:118-124` |

### A5.2 List — `/bdm/meeting-requests` (`web/app/bdm/meeting-requests/page.tsx:11-36`)

- Eyebrow **"Requests"**, heading **"Meeting requests"**, text "Telecallers ask for agent|school meetings here. Open a request to accept it into an appointment or decline it."
- Filter links (`web/components/MeetingRequestList.tsx:95-105`): **All · Pending · Accepted · Declined**; default **Pending** (`?status=all` for All).
- Columns: **Request** (MRQ-NNNNNN link), **Proposed (IST)** (+ mode), **Organization** (+ person), **Type**, **Status** (+ appointment code link · time; "Reason: …"), **Requested by**.
- Empty: "No pending|accepted|declined requests." / "No meeting requests yet."; paging 25 per page, "x–y of N", **Previous** / **Next**.
- API `GET /api/v1/bdm/meeting-requests?status=&limit=25&offset=` (`api/api/bdm_meeting_requests.py:68-74`).

### A5.3 Detail — `/bdm/meeting-requests/[id]` (`web/app/bdm/meeting-requests/[id]/page.tsx:17-78`)

- Heading "<code> <status pill>", link **Back to requests**.
- Details: **Type, Organization, Person, Phone** (tel: link), **Email, Proposed time (IST), Mode, Meeting link or location, Purpose, Remarks, Requested by** ("<name> · <time>"), **For** (named BDM or "Any Agent|School BDM").
- After decision: "Accepted by <name>: <APPT code> · <time>" or "Declined by <name>: <reason>".
- API `GET /api/v1/bdm/meeting-requests/{id}` (`api/api/bdm_meeting_requests.py:77-79`).

**Accept and book** (`web/components/MeetingRequestDecide.tsx:221-231`): heading **"Accept and book"**, text "Choose one of your organizations and a contact; the appointment is booked when you accept." (+ " The proposed time has passed — choose a new time." when past). Embedded bdm-006 appointment form (`BdmAppointmentForm`), prefilled: time (blank if past), type = `agent_meeting` / `school_meeting` / `college_meeting` / `corporate_meeting`, location, purpose, remarks; button **"Accept and book"** (busy "Saving…") (`web/components/BdmAppointmentForm.tsx:24,123,197`). The telecaller's free-text organization is **not** linked: the BDM must pick one of their own organizations and a contact.
- API `POST /api/v1/bdm/meeting-requests/{id}/accept` body = `BdmAppointmentCreate` (`api/api/bdm_meeting_requests.py:90-104`): row lock → pending check → `book_appointment` (every bdm-006 rule incl. overlap confirm); a refusal there leaves the request pending. Sets status accepted, `bdm_user_id` = me, links the appointment. Audit `bdm_meeting_request.accept`.

**Decline** (`MeetingRequestDecide.tsx:232-248`): heading **"Decline"**, field **"Reason for declining"** (textarea, required, max 500), hint "The telecaller sees your reason. A declined request can't be reopened.", button **"Decline request"** (busy "Declining…"). Client error **"Enter the reason for declining."**; 5xx "We couldn't decline the request. Please try again."; server 422 "Reason is required" (`api/schemas.py:4486-4490,6573-6575`).
- API `POST /api/v1/bdm/meeting-requests/{id}/decline` `{reason}` (`api/api/bdm_meeting_requests.py:107-115`). Audit `bdm_meeting_request.decline`.

Agent vs School: an Agent BDM sees only `agent` requests; a School BDM only `school` requests. The accept prefill type is `agent_meeting` vs `school_meeting` (both in `COMMON_TYPES`, `web/lib/bdmAppointments.ts:22`).

---

## PART A6 — University view — `/bdm/universities/[id]` (UNI)

Page `web/app/bdm/universities/[id]/page.tsx:13-28`; component `web/components/UniversityView.tsx`; loader `web/lib/universityViewServer.ts` (non-UUID → "University not found" without calling the API). API `GET /api/v1/universities/{id}/view` (`api/api/university_view.py:22-25`). DEC-SCOPE-161 (upc-030, UV6, U13).

| Topic | Rule | Evidence |
|---|---|---|
| Entry point | Only link: organisation detail field **"University Master"** on an organisation of `org_type = university` ("<code> · <name>, <country>" or "Not linked") | `web/components/BdmOrganizationDetail.tsx:131-138` |
| Who | role `bdm` (any bdm_type, BDM gate applies) and `bdm_manager` → slice `bdm`; others → 403 "University view access required" | `api/services/university_view.py:30,54-62` |
| Agent/School reach | org_type is **not restricted per BDM type** (`BDM_ORG_TYPES` incl. `university`, `api/models.py:2935`); any Agent/School BDM can create a University organisation and link it (`api/api/bdm_organizations.py:104-110`) and open this page | — |
| Scope | No per-BDM scope: `visible_university` only filters counselor/rep slices, so a BDM can open **any** University Master id | `api/services/university_view.py:65-72` |
| Sections (bdm slice) | header eyebrow **"University · <code>"**, name, "<city>, <country> · <stage badge>"; **Profile** (Institution type, Public / private, Country, City, Website, Course levels, Popular programmes, Campuses, Fee structure, Rankings, Overview, Eligibility); **Partnership** (Stage [+ " (lost)"], Partnership manager "<name> · <email>" or "Not assigned yet"). No contacts, courses, documents, applications, commission | `web/components/UniversityView.tsx:42-79`; `university_view.py:36` |
| Role pill | plain **"BDM"** (not "Agent BDM") | `page.tsx:23` |

**Product findings UNI-1/2:** (1) any BDM can read any University Master profile by id, not only the one their organisation links to — **VERIFICATION REQUIRED** whether intended (U13). (2) Whether Agent/School BDMs are meant to have University-type organisations at all is not settled by code — **VERIFICATION REQUIRED**.

---


---

## PART B — Organisations, contacts, type profiles, pipeline, onboarding, org panels, MoUs

Scope of this part: `/bdm/organizations` (list, new, [id] and every section it renders), `/bdm/pipeline`, `/bdm/mous`. Activity timeline and follow-up items on the organisation page are only noted here (covered with Activities / Follow-ups). Path prefixes `web/` = `apps/web/`, `api/` = `apps/api/app/`. **VERIFICATION REQUIRED** = not settled from code alone.

### B.0 Scope rules that apply to every organisation route

| Rule | Code | Evidence | Decision |
|---|---|---|---|
| Gate | Every BDM route calls `bdm_context`: role ≠ `bdm` → 403 **"BDM role required"**; no profile → 403 **"BDM profile not set up — contact your administrator"** | `api/services/bdm.py:138-145` | DEC-SCOPE-055 |
| Module | `BDM_DIVISION = {"college": "it", "agent": "overseas", "school": "overseas"}`; an organisation's `bdm_type` = the creating BDM's `bdm_type` (server-owned, never sent) | `api/services/bdm.py:20`; `api/api/bdm_organizations.py:115-118` | DEC-SCOPE-055 D3, DEC-SCOPE-060 C3 |
| Read scope (BDM) | **Every organisation of the BDM's module** (`BdmOrganization.bdm_type == profile.bdm_type`), not just assigned ones. Agent BDM sees all Agent-module orgs; School BDM sees all School-module orgs; neither sees the other module, nor College | `api/services/bdm_organizations.py:80-91` | DEC-SCOPE-060 Q-02 |
| Out of scope | Any id outside scope = same **404 "Organization not found"** as a missing id (never 403) | `api/services/bdm_organizations.py:39,94-106` | C14 |
| Write scope | `can_edit` / `can_archive` = the **assigned** BDM (or super_admin), and only while not archived. `can_restore` / `can_reassign` = `bdm_manager` / super_admin only — **never shown to a BDM** | `api/services/bdm_organizations.py:109-118` | C5, C15 |
| Refusal wording (403) | "Only the assigned BDM can edit this organization" · "Only the assigned BDM can archive this organization" · "Only the BDM's manager can restore this organization" · "Only the BDM's manager can reassign this organization" | `api/services/bdm_organizations.py:45-50` | — |
| State refusal (409) | "Restore this organization first" (edit/reassign while archived) · "Already archived" · "Already active" | `api/services/bdm_organizations.py:51-56` | C15 |
| Org type vs module | `org_type` is free choice from 7 values (College, University, Agent, School, Corporate, Training Institute, Other) **independent of the module** — an Agent BDM may create an org of type "School" in the Agent module. Module-specific features (pipeline, onboarding, panels) follow `bdm_type` (module); type profile fields follow `org_type` | `web/lib/bdmOrganizations.ts:19-23,93-95`; `api/schemas.py:3833`; `web/components/BdmOrganizationDetail.tsx:219-224` | DEC-SCOPE-065 — **VERIFICATION REQUIRED** (product intent of cross-type orgs) |

### B.1 Organisations list — `/bdm/organizations`

Page `web/app/bdm/organizations/page.tsx:12-35`; panel `web/components/BdmOrganizationsPanel.tsx`.

| Element | Literal UI | Evidence |
|---|---|---|
| Eyebrow / heading | "Organizations" / **"Agent organizations"** or **"School organizations"** (`BDM_TYPE_LABEL` + " organizations") | `page.tsx:25-26` |
| Intro | "Every organization in your module. You can edit the ones assigned to you." | `page.tsx:27` |
| Card title + button | "Organizations" · **Add organization** (BDM only) | `BdmOrganizationsPanel.tsx:134-139` |
| Filters (form `role=search`, "Filter organizations") | **Name or code** (search, max 200) · **City** (search, max 120) · **Type** select ("All types" + 7 types; changes apply immediately) · type-dependent: **Board** select (School type: "All boards", CBSE, ICSE, State board, IB, Other) / **University / affiliation** (College or University type, max 200) / **Territory** (Agent type, max 120) · checkbox **Assigned to me** (BDM only) · checkbox **Show archived** · **Search** · **Clear filters** (only when any filter is on) | `:141-203`; `web/lib/bdmOrganizations.ts:114-115` |
| Columns | **Code · Name** (link; "Archived" badge) **· Type · City · Primary contact · Assigned BDM** (" (inactive)") **· Last meeting · Next meeting** (IST date-time or "—") | `:252-288` |
| Loading / errors | "Loading organizations…" · "Updating organizations…" · "Unable to load organizations." + **Retry** | `:205-248`; page Suspense `page.tsx:30` |
| Empty states | Filtered: "No organizations match these filters." · Unfiltered BDM: "No organizations yet." + **Add organization** · past end: "This page is past the end of the list." + **Go to the first page** | `:218-241` |
| Pager | 50/page (`PAGE_SIZE`); "Showing X–Y of N" · **Previous** · **Next** | `:293-305`; `web/lib/bdm.ts:189` |
| URL state | `?q&org_type&city&board&affiliation&territory&assigned=me&archived=1&offset` (refresh/back keep the view) | `:30-58` |

API: `GET /api/v1/bdm/organizations` (`api/api/bdm_organizations.py:55-94`) — filters ANDed with scope; archived excluded unless `include_archived=true`; `assigned=me` only for role `bdm` (else 422 "assigned must be me or a BDM id"); ordered by name. Last meeting = latest **completed** appointment at the org by **any** BDM; Next = earliest open future appointment (`api/services/bdm_organizations.py:225-242`).

### B.2 Add organisation — `/bdm/organizations/new`

Page `web/app/bdm/organizations/new/page.tsx:9-30` — eyebrow "Organizations", heading **"Add organization"**, text "It will belong to the Agent|School module and be assigned to you." Form `web/components/BdmOrganizationForm.tsx` + fields components. After save → `/bdm/organizations/<id>?created=1` with notice **"Organization ORG-NNNNNN created."** (`BdmOrganizationCreate.tsx:12`; `BdmOrganizationDetail.tsx:53`).

#### B.2.1 Organisation fields (`web/components/BdmOrganizationFields.tsx:33-131`; server `api/schemas.py:3926-4029`)

| Label (UI) | Type | Required | Limit | Server rule / message |
|---|---|---|---|---|
| Type (required) | select, "Choose a type" + 7 types; hint "The details section below changes with the type." | Y | — | client "Choose a type" |
| Organization name (required) | text | Y | 200 | "Organization name is required" |
| City (required) | text | Y | 120 | "City is required" |
| State | text | N | 120 | — |
| Address | textarea (line breaks kept) | N | 500 | — |
| Phone | tel | N | 30 | "Phone may contain only digits, spaces and + - ( )" |
| Email | email | N | 255 | "Enter a valid email address" (stored lower-case) |
| Website | url; hint "For example stjoseph.edu or https://stjoseph.edu" | N | 255 | bare domain → `https://` prefix; "Website must start with http:// or https://" / "Enter a website such as stjoseph.edu" |
| Number of students | number 0–1,000,000 | N | — | "Number of students must be a whole number from 0 to 1,000,000" |
| Courses interested | textarea | N | 1000 | — |
| Existing partner | checkbox | N | — | default false |
| any text | — | — | — | "<Label> contains invalid characters" (control chars) |

#### B.2.2 Type profile ("<Group> details" fieldset) — `web/components/BdmOrganizationProfileFields.tsx:333-415`

| Org type → group | Fields (UI label, control) | Limits / values |
|---|---|---|
| Agent → **Agent details** | Country (text) · Territory (text) · Source (select: Referral, Website, Event, Cold call, Walk-in, Other) · Number of staff (text, numeric keyboard) | 120 / 120 / — / 0–100,000 "Number of staff must be a whole number from 0 to 100,000"; note **"Commission: Available after onboarding"** |
| School → **School details** | Board (CBSE, ICSE, State board, IB, Other) · School type (Private, Government, Aided, International, Other) · Lowest grade · Highest grade (Nursery, LKG, UKG, 1–12) | "Lowest grade can't be above the highest grade"; "Grade must be Nursery, LKG, UKG or 1 to 12" |
| College / University → **College details** | University / affiliation (text) · College type (Engineering, Arts & Science, Management, Medical, Polytechnic, Other) · Courses (textarea) | 200 / — / 1000 |
| Corporate, Training Institute, Other | no profile section | — |

Server: a key not belonging to the org type → 422 "<Field> is not a field for <Type> organizations" (`api/services/bdm_organizations.py:253-264`). Type change on edit into another group while the old group has data → 409 "Clear the <Type> details before changing the type" (`:267-276`); UI words it "Clear the <Group> details before changing the type: <fields>." or "Save the cleared <Group> details first: change the type back to <Group> and save, then change the type." (`web/lib/bdmOrganizations.ts:150-155`). College↔University share a group.

#### B.2.3 Contacts on create — `web/components/BdmContactFields.tsx`

| Element | Literal | Rule |
|---|---|---|
| Fieldset | "Contacts"; each block "Contact N" + " (primary)" | starts with 1 contact, primary |
| Fields | **Contact name (required)** (200) · Designation (120) · Role (select "Not set" + Principal, Dean, HOD, Placement Officer, Counselor, Management, Owner, Other — type's people first: Agent → Owner; School → Principal, Management, Counselor) · Phone (30) · Email (255) | `:150-203`; `web/lib/bdmOrganizations.ts:136-142` |
| Controls | radio **Primary contact** · **Remove contact N** (when >1) · **Add contact** (disabled at 20, note "An organization can have at most 20 contacts.") | `:247-263` |
| Server | "Add at least one contact" · "An organization can have at most 20 contacts" · "Only one contact can be primary" · "Contact name is required" | `api/schemas.py:3907-3912,3981-3988` |

#### B.2.4 Save / duplicate

- Buttons **Save organization** (busy "Saving…") · **Cancel**; leave prompt "You have unsaved changes to this organization. Leave without saving?" (`BdmOrganizationForm.tsx:47,291-298`).
- Duplicate = same module + normalised name + city (archived included) → 409 with heading **"A similar organization already exists in your module"**, list "ORG-… — name, city · assigned to X · Archived", "N more similar organization(s).", buttons **Save anyway** / **Go back** (`BdmOrganizationForm.tsx:243-285`; `api/services/bdm_organizations.py:130-152`). For org type University also "Already in the University Master" + **Link to <code> and save** / **Save without linking** (upc-004).
- Generic failure "Unable to save this organization." Code = `ORG-` + 6-digit sequence (`api/services/bdm_organizations.py:71-77`).
- API `POST /api/v1/bdm/organizations` (`api/api/bdm_organizations.py:97-149`): BDM only; creator = assignee.

### B.3 Organisation detail — `/bdm/organizations/[id]`

Page `web/app/bdm/organizations/[id]/page.tsx:21-61`; component `web/components/BdmOrganizationDetail.tsx`. Not found / out of module: **"Organization not found"** + "Back to organizations" (`page.tsx:54-57`). Section order: header → status line → Pipeline → MoU → Onboarding → School activity (School module) / Agent performance (Agent module) → Details (or Edit details) → Contacts → Stage history → Activities → Follow-ups & tasks → Leads → (Business: College only) → (Assignment: managers only).

#### B.3.1 Header, details, archive

| Element | Literal | Visible when | Evidence |
|---|---|---|---|
| Eyebrow / title | "ORG-000123 · <Type>" / name + "Archived" badge; "Back to organizations" | always | `:149-162` |
| Buttons | **Add appointment** (→ `/bdm/appointments/new?organization=<id>`) · **Edit** · **Archive** | `can_edit` / `can_archive` (assigned, not archived) | `:163-178` |
| Restore | **Restore** | `can_restore` → never for a BDM | `:179-183` |
| Archive confirm | "Archive <name>? It will be hidden from the list and read-only until a manager restores it." **Yes, archive** / **Keep it** (busy "Archiving…") | — | `:194-198` |
| Notices | "Organization archived." · "Organization restored." · "Changes saved." · "No changes to save." · error "Unable to update this organization." | — | `:98-101,232` |
| Details rows | Type · City · State · Address · Contact person · Designation · Phone · Email · Website (link if http/s, "(opens in a new tab)") · Existing partner (Yes/No) · [University Master — org type University only: link or "Not linked"] · Courses interested · Number of students · Last meeting · Next meeting · Assigned BDM · Created by "<name> on <date>" | — | `:109-145` |
| Type details | heading "<Group> details"; empty "No <group> details yet. Use Edit to add them."; Agent: "Commission: Available after onboarding" or, once linked, "Commission: Not shown to BDMs (awaiting a decision)"; linked agency staff shown "N live (M entered)"; School grades as one "Grades" row | — | `web/components/BdmOrganizationProfileDetails.tsx:457-505` |
| Edit | section "Edit details", same form (no contacts), **Save changes** / **Cancel** | `can_edit` | `:225-237` |

API: `GET/PATCH /api/v1/bdm/organizations/{id}` (`api/api/bdm_organizations.py:152-194`; PATCH sends only changed fields; name/city change re-runs duplicate check). `POST …/archive` (`:211-214`) — archive **cancels every open follow-up/task** on the org (`:203`); `POST …/restore` (`:217-220`) manager only.

#### B.3.2 Contacts — `web/components/BdmOrganizationContacts.tsx`

| Element | Literal | Evidence |
|---|---|---|
| Heading / item | "Contacts"; name + "Primary" badge; details "Designation: … · Role: … · Phone: … · Email: …" or "No other details" | `:16-25,114-127` |
| Actions (`can_edit`) | **Edit** · **Make primary** (non-primary) · **Delete** (disabled when last) · **Add contact** (disabled at 20) · editor **Save contact** / **Cancel** | `:128-177` |
| Messages | "An organization needs at least one contact." · confirm "Delete <name>? This removes their details." **Yes, delete** / **Keep** · notices "Contact added." "Contact updated." "Primary contact changed." "Contact deleted." · error "Unable to update the contacts." | `:119-170` |
| API | `POST /organizations/{id}/contacts` (`api/api/bdm_organizations.py:245-260`; 409 "An organization can have at most 20 contacts") · `PATCH …/contacts/{cid}` (`:263-282`; 422 "Choose another primary contact instead") · `DELETE …/contacts/{cid}` (`:285-307`; 409 **"An organization needs at least one contact"**; deleting primary promotes oldest; hard delete) · 404 "Contact not found" | — |

#### B.3.3 Pipeline section — `web/components/BdmOrganizationPipeline.tsx`; rules `api/services/bdm_pipeline.py`; catalogue `api/bdm_stages.py:20-90`

| Element | Literal | Evidence |
|---|---|---|
| Heading | "Pipeline"; Agent module only: "Agent status: <badge>" | `:290-295` |
| Lost banner | "Marked lost on <date>: <reason>" | `:296-300` |
| Stepper | each stage label + state **Done / Current / Upcoming / Awaiting handover / Not tracked**; volume steps show a count once linked | `:301-310`; `web/lib/bdmPipeline.ts:261-263` |
| Move form (`can_edit`, not Lost) | **Move to** select ("Choose a stage", manual stages only, current shows " (current)" disabled) · **Note (optional)** or, moving back, **Reason (required when moving back)** (max 500) · **Move** | `:312-337` |
| Lost / Revive | **Mark lost** / **Revive** → **Reason** (required, max 500) · **Yes, mark lost** / **Yes, revive** · **Cancel** | `:338-359` |
| Notices | "Moved to <stage>." · "Marked lost." · "Revived." | `:270,274` |
| Server errors | "Choose a stage of this organization's pipeline" · "This stage is set by the onboarding handover" (live) · "This step is counted from live records, not set by hand" (volume) · "The organization is already at this stage" · "Add a note to move an organization back" · 409 "This organization moved to <stage> meanwhile" (+ UI ". Check the stage and try again.") · 409 "This organization is marked lost. Revive it first." · 409 "This organization is not marked lost." · reason blank → "Reason is required" (**VERIFICATION REQUIRED**: label comes from `BDM_TRIP_FIELD_LABELS`) | `api/services/bdm_pipeline.py:35-41,156-177`; `api/schemas.py:3625-3634,4229-4251` |
| API | `POST /organizations/{id}/stage` `{from_stage,to_stage,note?}` (`api/api/bdm_pipeline.py:33-45`) · `POST …/lost` `{reason}` (`:67-69`) · `POST …/revive` `{reason}` (`:72-74`) — all assigned BDM only, archived → 409 | — |

Lost is a flag over the stage (stage kept); revive returns to the same stage (`api/api/bdm_pipeline.py:48-64`). Stored stage is always manual; live/volume steps derive from onboarding (`api/services/bdm_pipeline.py:77-149`).

**Pipeline stages per module (`api/bdm_stages.py:20-69`)**

| # | Agent module | kind | School module | kind | (College — out of scope) |
|---|---|---|---|---|---|
| 1 | Agent Prospect | manual | School Prospect | manual | College Prospect |
| 2 | Contacted | manual | Contacted | manual | Contacted |
| 3 | Meeting Scheduled | manual | Meeting | manual | Meeting |
| 4 | Meeting Completed | manual | Presentation | manual | Presentation |
| 5 | Interested | manual | Proposal | manual | Proposal |
| 6 | Proposal / Agreement | manual | Negotiation | manual | MoU Negotiation |
| 7 | Agreement Signed | manual | MoU | manual | MoU Signed |
| 8 | Agent Onboarding | live | Signed | manual | College Activated (manual) |
| 9 | Master Login Created | live | School Onboarding | live | Course Promotion (volume) |
| 10 | Staff Logins Created | live | Teachers / Parents / Students Created | live | Student Leads (volume) |
| 11 | Active Agent | live | Career Guidance | live | Training (volume) |
| 12 | Students | volume | Psychometric | live | Internship (volume) |
| 13 | Applications | volume | Student Profile Building | live | Recruitment (volume) |
| 14 | Enrollments | volume | University Planning | live | Placement (volume) |

Agent status (Agent module only, derived): Prospect, Contacted, Meeting, Interested, Agreement, Onboarding, Active, Inactive (`api/bdm_stages.py:74-87`; `api/services/bdm_pipeline.py:111-120`). MoU Signed auto-advances forward to Agent "Agreement Signed" / School "Signed" (`api/bdm_stages.py:90`).

#### B.3.4 Stage history — `web/components/BdmStageHistory.tsx`

"Stage history"; rows "<from> → <to>" / "Marked lost at <stage>" / "Revived at <stage>", "By <name>", "Note: …" or "Reason: …"; empty "No stage changes yet."; error "Unable to load the stage history." + **Try again**; **Show more** (20/page). API `GET /organizations/{id}/stage-history` (`api/api/bdm_pipeline.py:77-81`).

#### B.3.5 Onboarding handover — `web/components/BdmOrganizationOnboarding.tsx`; `api/api/bdm_onboarding.py:35-48`; `api/services/bdm_onboarding.py`

| | Agent module ("Agent onboarding") | School module ("School onboarding") |
|---|---|---|
| Qualifies when | stored stage = **Agreement Signed** | current MoU effective status **Signed or Active** (Expired does not qualify) |
| Not-yet text (assigned BDM) | "Available once the agreement is signed." | "Available once the MoU is Signed or Active." |
| Ready text | "Ready to hand over: Overseas Admin will link the agent organization once the agency is registered." | "Ready to hand over: Overseas Admin will create the School, or link one that already exists." |
| Pending | "Requested on <dt>. Waiting for Overseas Admin to link the agent organization." | "Requested on <dt>. Waiting for Overseas Admin to create or link the School." |
| Rejected | "Not approved on <dt>. Reason: <reason>" + **Request again** | same |
| Linked | "Linked to <agency> (code <prefix>). Status: Pending approval/Active/Suspended/Rejected." + "Master login: Created/Not yet · Staff logins: N" | "Onboarded as <school> (School ID <code>)." |
| Success notice | "Onboarding requested. Overseas Admin will link the agent organization." | "Onboarding requested. Overseas Admin will create or link the School." |
| Server refusals | 422 "The agreement must be signed to request onboarding" | 422 "The MoU must be Signed or Active to request onboarding" |

Common: button **Request onboarding**, form "Note for Overseas Admin (optional)" (max 1000), **Send request** / **Cancel**; non-assigned viewer "Not requested yet."; 409 "This organization already has an onboarding request waiting" · "This organization is already linked to a School|an agent organization" · Lost 409; 5xx "The request could not be confirmed. Reload the page to check before trying again." Notifies all active `overseas_admin` users (`api/api/bdm_onboarding.py:43-45`); BDM gets "School onboarded" / "Agent onboarded" / "<Type> onboarding not approved" notices (`api/services/bdm_onboarding.py:188-197`). Section absent for College. Decisions DEC-SCOPE-085 (bdm-018), DEC-SCOPE-107 (bdm-019).

#### B.3.6 Module panels

| Panel | Module | Literal UI | API |
|---|---|---|---|
| **School activity** (`web/components/BdmOrganizationSchoolActivity.tsx`) | School only | unlinked "Not onboarded yet. Counts appear once Overseas Admin links the School."; linked "<School> (School ID x) · N students", table **Metric / Completed / Pending**: Career Guidance, Psychometric Test, Foreign Language, English Testing, University Guidance, Student Profile Completion ("Not tracked"); error "Unable to load the school activity." | `GET /organizations/{id}/school-activity` (`api/api/bdm_school_activity.py:29-42`; non-School 404 "School activity is only for School organizations"); rows `api/api/school_analytics.py:298-304`. DEC-SCOPE-089 |
| **Agent performance** (`web/components/BdmOrganizationAgentPerformance.tsx`) | Agent only | unlinked "Not onboarded yet. Figures appear once Overseas Admin links the agent organization."; linked "<agency> (<prefix>) · live figures from the agency's own records."; steps Students, Applications, Offers, Visa, Enrolled, Revenue ("Not tracked yet") each with its definition; **Show/Hide applications by stage** ("Withdrawn applications are not counted in Applications."); flags "Suspended — this agency's members can't sign in, so these figures are not changing." / "Not approved — this agency was rejected by Overseas Admin." | `GET /organizations/{id}/agent-performance` (`api/api/bdm_metrics.py:35-42`; non-Agent 404 "Agent performance is only for Agent organizations"); `api/services/bdm_metrics.py:113-161`. DEC-SCOPE-110 |
| Business | College only (not rendered for Agent/School) | — | `GET …/business` (`api/api/bdm_metrics.py:27-32`) DEC-SCOPE-086 |

#### B.3.7 Leads section — `web/components/BdmOrganizationLeads.tsx`, `BdmLeadForm.tsx`; `api/api/bdm_leads.py`

| Element | Literal | Evidence |
|---|---|---|
| Heading / button | "Leads (N)" · **Add lead** (assigned, not archived) | `:51-54` |
| Columns | **Student** (name + email · phone) · **Interest · Status** (New, Contacted, Qualified, Converted, Lost; badge "Converted to a student") **· Added by · Added** | `:11,70-95` |
| States | "No leads yet." · "Leads couldn't be loaded." + **Try again** · **Load more** (20/page) · notice "Lead added." | `:61-103` |
| Form | **Student name (required)** (160) · **Email (required)** (255) · Phone (40) · **Interest (required)** (180) · Note (5000; hint "Everyone who can see this organization can read this lead.") · **Save lead** / **Cancel**; client "Enter the student's name." / "Enter the student's email." / "Enter what the student is interested in." / "Check the highlighted fields." | `BdmLeadForm.tsx:121-223` |
| Duplicate | 409 "This student is already a lead of this organization: <name> (added <dt>)…" **Save anyway** / **Go back** | `api/services/bdm_leads.py:48-57` |
| Server | 403 "Only the organization's assigned BDM can add leads" · 422 "This organization is archived" · 409 "You've added 200 leads today" (IST day cap) | `api/services/bdm_leads.py:22-45` |
| Effect | Creates an `enquiries` row, division **overseas** for Agent/School BDMs, `source="bdm"`, then `lead_distribution.on_intake` (telecaller distribution) and CRM sync | `api/api/bdm_leads.py:45-59` |

DEC-SCOPE-072 (bdm-017).

#### B.3.8 Other sections (noted only)

- **Activities** timeline (`BdmActivityTimeline`, can log = assigned and not archived) — see Activities part.
- **Follow-ups & tasks** (`web/components/BdmOrganizationTasks.tsx:44-70`): "Follow-ups & tasks", **Add task** (assigned, not archived), empty "No open follow-ups or tasks.", "Showing N of M. See all follow-ups", error "Follow-ups couldn't be loaded." DEC-SCOPE-075 — see Follow-ups part.
- **Assignment / Reassign** (`web/components/BdmOrganizationReassign.tsx`): rendered only when `can_reassign` → **never for a BDM** (manager feature; 422 "Choose an active BDM of this type from your team").

### B.4 MoU card on the organisation — `web/components/BdmOrganizationMou.tsx`, `BdmMouForm.tsx`, `BdmMouDocument.tsx`, `BdmMouHistory.tsx`, `BdmMouPrevious.tsx`

| Element | Literal | Evidence |
|---|---|---|
| Heading / read-only notes | "MoU"; "This organization is archived, so its MoU is read-only." / "This organization is marked lost, so its MoU is read-only." | `BdmOrganizationMou.tsx:156-158`; `BdmOrganizationDetail.tsx:35-38` |
| None yet | "No MoU yet." + **Start MoU** (`can_start`) | `:104-110` |
| Current | "Status: <badge>", ladder Prospect → Discussion Started → Proposal Sent → Under Negotiation → Draft Shared → Signed → Active (Done/Current/Upcoming); outcome "Expired on <d> (valid until <d>)." or "Rejected."; **Edit MoU** · **Start renewal** (only when Expired/Rejected) → "Start a new MoU for this organization? The current one is kept in its history." **Yes, start renewal** | `:111-146` |
| Rows | Reference · Proposal sent · Signed on · Valid from · Valid until (renewal date) · Notes · Status changed | `:113-121` |
| Form | **Status** (all except Expired; disabled when Expired with hint "Expired. Start a renewal to change the status, or correct the valid-until date.") · Proposal sent date · Signed date (required for Signed/Active) · Valid from · Valid until (required for Active) · Reference (100) · Notes (2000) · **Start MoU** / **Save MoU** / **Cancel**; signing confirm "This also moves the pipeline to <stage>." **Yes, save** / **Not yet** | `BdmMouForm.tsx:173-288` |
| Notices | "MoU started." · "MoU saved." · "Renewal started." · "Document saved." · "… The pipeline moved to <stage>." | `BdmOrganizationMou.tsx:68,84,103,148` |
| Document | "Document: <name> · uploaded <dt>" **Download document (PDF/image)** / "No document on file."; **Upload document** / **Replace document** "(PDF, JPEG or PNG, up to 20 MB)"; errors "Upload a PDF, JPEG or PNG file" · "The file must be at most 20 MB" · "Something went wrong on our side. Please try again."; "Uploading…" | `BdmMouDocument.tsx:9-60` |
| History | `<details>` "MoU history": "Started at X" · "X → Y" · "Document uploaded" · "Replaced by a renewal" · "Updated: <fields>" · "Expired (automatic)" "The validity window ended on <d>." | `BdmMouHistory.tsx:11-83` |
| Previous | `<details>` "Previous MoUs": "<ref or MoU of date> · status · valid until …" + Download; "No previous MoUs." | `BdmMouPrevious.tsx:88-117` |
| Server rules | "Add the signed date" · "Add the validity window" · "Valid-until can't be before valid-from" · "The MoU is already at this status" · 409 "This organization already has an MoU in progress" · 409 "This MoU has expired. Start a renewal." · 409 "This MoU was changed meanwhile" (+". Check it and try again.") · 409 "This MoU moved to <status> meanwhile" · 429 "Too many uploads. Try again later." (20/user/hour) · Proposal Sent without date defaults to today · Expired is derived (Signed/Active past valid-until), never stored | `api/services/bdm_mous.py:27-106`; `api/api/bdm_mous.py:32-138` |
| Writers | assigned BDM (or super_admin), org not archived and not Lost | `api/services/bdm_mous.py:172-180` |
| API | `GET/POST/PATCH /organizations/{id}/mou` · `PUT …/mou/document` (multipart) · `GET /mous/{mou_id}/history` · `GET /mous/{mou_id}/document` (file named `mou-<ORG code>.<ext>`, audited) | `api/api/bdm_mous.py:26-174` |

DEC-SCOPE-078 (bdm-005).

### B.5 MoU list — `/bdm/mous`

Page `web/app/bdm/mous/page.tsx:14-47`; panel `web/components/BdmMousPanel.tsx`.

| Element | Literal |
|---|---|
| Eyebrow / heading | "MoUs" / **"Agent MoUs"** or **"School MoUs"** |
| Intro | "Each organization's current MoU. A Signed or Active MoU past its valid-until date reads Expired." |
| Filter (links, one scrolling row) | **All · Prospect · Discussion Started · Proposal Sent · Under Negotiation · Draft Shared · Signed · Active · Expired · Rejected** |
| Card heading | "<Status> MoUs" / "All MoUs" |
| Columns | **Organization** (link) **· Code · Status · Signed on · Valid until · Reference · Document** (Yes/—) **· Assigned BDM** |
| Empty | "No MoUs yet." · "No MoUs at <Status>." · "This page is past the end of the list." |
| Invalid filter | "That filter isn't valid." + "Show all MoUs" |
| Pager | 50/page "Showing X–Y of N" Previous / Next |

API `GET /api/v1/bdm/mous?status&organization&current&limit&offset` (`api/api/bdm_mous.py:141-154`) — scope = module (same as organisations); status filter on the **derived** status; ordered by status change, newest first; current MoUs only by default.

### B.6 Pipeline board — `/bdm/pipeline`

Page `web/app/bdm/pipeline/page.tsx:16-73`; board `web/components/BdmPipelineBoard.tsx`; API `GET /api/v1/bdm/pipeline` (`api/api/bdm_pipeline.py:84-101`; `api/services/bdm_pipeline.py:229-273`).

| Element | Literal / rule |
|---|---|
| Eyebrow / heading | "Pipeline" / **"Agent pipeline"** / **"School pipeline"**; "Organizations per stage. Lost organizations are counted apart; archived ones are left out." |
| Scope toggle | **Mine** (default, `assigned=me`) · **All in module** (`?scope=all`) |
| Tiles | one per stage of the module + **Lost**; manual stages show a count link; live stages show "Awaiting handover", volume "Not tracked" (no link) |
| List heading | chosen stage label or "All open organizations"; **Show all stages** when filtered |
| Columns | **Code · Name · Type · City · Stage** (+ "Lost" badge) **· Assigned BDM** |
| Empty | "No organizations at this stage." + **Add organization**; "This page is past the end of the list." |
| Invalid | "That filter isn't valid." + "Show my pipeline" (unknown stage → 422 "Choose a stage of this pipeline"; another module → 422 "You can only view your own module's pipeline") |
| Counting | archived excluded; Lost orgs only in Lost tile/`stage=lost`; counts follow Mine/All |

### B.7 Agent BDM vs School BDM (this part) — College noted

| Topic | Agent BDM | School BDM | College BDM (out of scope) |
|---|---|---|---|
| Orgs visible | all Agent-module orgs | all School-module orgs | all College-module orgs |
| Headings | "Agent organizations / pipeline / MoUs" | "School organizations / pipeline / MoUs" | "College …" |
| Pipeline | 7 manual + 4 live (agency link) + 3 volume (counts) | 8 manual + 6 live (School records) | 8 manual + 6 volume |
| Agent status badge | yes (8 derived values) | no | no |
| MoU Signed advances to | Agreement Signed | Signed | MoU Signed |
| Onboarding trigger | stage Agreement Signed | MoU Signed/Active | no onboarding section |
| Onboarding outcome | linked to an Agent Organization (AGN) by code | School created or linked (School ID) | — |
| Panel | Agent performance | School activity | Business (leads funnel, revenue rules) |
| Lead division | overseas | overseas | it |
| Contact role suggestions | follow `org_type`, not module (Agent type → Owner first; School type → Principal, Management, Counselor) | same | same |
| Profile section | follows `org_type` (any module) | same | same |


---

## PART C — Appointments, Follow-ups and tasks, Activity log

Path prefixes: `web/` = `apps/web/`, `api/` = `apps/api/app/`. Browser calls go to `/api/v1/...`. Router prefixes: `/bdm/appointments` (`api/api/bdm_appointments.py:38`), `/bdm/tasks` (`api/api/bdm_tasks.py:22`), `/bdm` (activities, `api/api/bdm_activities.py:24`). List paging: `limit` default 50 (1-100), `offset` ≥0, search `q` ≤200 chars (`api/api/bdm.py:24-26`); UI page size 50 (`web/lib/bdm.ts:29`).
Decision labels: bdm-006 = DEC-SCOPE-068 (appointments), bdm-007 = DEC-SCOPE-070 (meeting report), bdm-008 = DEC-SCOPE-075 (follow-ups), bdm-009 = DEC-SCOPE-069 (activities), bdm-011 = DEC-SCOPE-092 (trip link), bdm-012 = DEC-SCOPE-102 (reminders), bdm-015 (daily report lock). Code is the authority.

### C.0 Agent vs School (vs College) differences in this part

| Topic | Agent BDM | School BDM | College BDM (out of scope, for contrast) | Evidence |
|---|---|---|---|---|
| Appointment types offered (common 8 + module list, duplicates once) | Common: College Meeting, Agent Meeting, School Meeting, MoU Discussion, Student / Institution Meeting, Seminar / Workshop, Corporate Meeting, Other **+** New Agent Presentation, Product Training, Agreement Discussion, Performance Review, Agent Onboarding, Agent Visit, Commission Discussion, Business Review | Common 8 **+** Principal Meeting, Management Meeting, Career Guidance Presentation, Psychometric Presentation, Student Profile Building Presentation, Parent Orientation, Teacher Orientation, Seminar, Workshop, Renewal Meeting (MoU Discussion already in common) | Common 8 + Principal Meeting, HOD Meeting, Placement Cell Meeting, Course Promotion, IT Training Presentation, Student Seminar, Workshop, Internship Discussion, Placement Discussion, Corporate Connect, Faculty Meeting | `web/lib/bdmAppointments.ts:22-41`; `api/models.py:3220-3239`; `api/services/bdm_appointments.py:67-69` |
| Type refused server-side | 422 "This appointment type is not available for Agent BDMs" | "…for School BDMs" | "…for College BDMs" | `api/api/bdm_appointments.py:56-58` |
| Meeting-report Outcome list | **Agent list**: Interested, Agreement Required, Product Training Required, Follow-up, Documents Required, Onboarding Required, Active Business Expected, Not Interested | **Common list**: Interested, MoU Discussion Required, Student Leads Expected, Course Promotion Interested, Follow-up Required, Commercial Discussion, Not Interested, Reschedule, Other | Common list (same as School) | `web/lib/bdmAppointments.ts:43-52`; `api/services/bdm_appointments.py:72-74` (A8) |
| "Book the next meeting" button after report | Never (no `reschedule` outcome in Agent list) | Shown when outcome = Reschedule and org not archived | Same as School | `web/components/BdmMeetingReportSection.tsx:89-91` |
| Outcome refused | 422 "This outcome is not available for Agent BDMs" | "…School BDMs" | — | `api/api/bdm_appointments.py:279-282` |
| Follow-ups org-type chips | Chips count by the linked organization's org type (College, University, Agent, School, Corporate, Training Institute, Other, "No organization"); an Agent BDM's orgs are normally type Agent — **VERIFICATION REQUIRED** which org types an agent/school BDM can actually hold (see organisations part) | same | same | `api/services/bdm_tasks.py:123-129`; `web/lib/bdmOrganizations.ts:21-23` |
| Activities | No type difference (channels identical) | same | same | `web/lib/bdmActivities.ts:8` |
| Meeting requests (tel-019) prefill types | Request type lands in the same Type select — types are the module list above | same | — | `web/components/BdmAppointmentForm.tsx:24,62-65` |

---

### C.1 Appointments list — `/bdm/appointments`

Page `web/app/bdm/appointments/page.tsx:13-38`; panel `web/components/BdmAppointmentsPanel.tsx` (`isBdm`, types = `appointmentTypes(bdm_type)`).

| Element | Literal UI | Evidence |
|---|---|---|
| Eyebrow / heading / sub | "Appointments" / **"Your appointments"** / "Times are India time (IST)." | page.tsx:27-29 |
| Suspense fallback | "Loading appointments…" | page.tsx:32 |
| Card heading + button | **"Appointments"** · button **"Book appointment"** → `/bdm/appointments/new` | Panel:135-139,144-145 |
| Filters (form "Filter appointments") | **Code or organization** (search, maxLength 200, applied on **Search**); **From (IST)** (date, default = today IST); **To (IST)** (date, min = From); **Status**: "All statuses", Scheduled, Confirmed, Rescheduled, Completed, Cancelled, No show, **Outcome pending**; **Type**: "All types" + module types. Date/status/type apply on change. **Clear filters** shown when anything differs from default | Panel:347-405 |
| Outcome pending rule | Choosing it clears From (pending meetings are past); leaving it restores From = today (QA7-04). Sent as `outcome_pending=true` | Panel:224,238-240,324-328,273 |
| Deep-link badges | "Showing one organization" (from `?organization=`), "Showing one BDM", button **Show all** | Panel:407-415 |
| Columns | **Code** (link) · **Date & time** ("<date time> · <duration>", e.g. "1 h 30 min") · **Organization** (+ badge **Archived**) · **Contact** · **Type** · **Status** (pill + badge **Outcome pending**). BDM column only for managers | Panel:461-506; `web/lib/bdmAppointments.ts:122-126` |
| States | Load error "Unable to load appointments." + **Retry**; loading "Loading appointments…"; filtered empty "No appointments match these filters." + Clear filters; unfiltered empty **"No appointments yet."** + Book appointment; past end "This page is past the end of the list." + **Go to the first page**; refreshing "Updating appointments…" | Panel:416-458 |
| Pager (>50) | "Showing X–Y of N", **Previous**, **Next** | Panel:512-523 |
| Order | Ascending by start time | `api/api/bdm_appointments.py:113-115` |

API `GET /api/v1/bdm/appointments` (`api/api/bdm_appointments.py:70-121`): params `date_from`, `date_to` (IST inclusive), `status` (multi), `appointment_type`, `organization_id`, `bdm_user_id`, `outcome_pending`, `q` (code or org name). Rules: BDM sees **only own** appointments (`bdm_user_id = me`, `api/services/bdm_appointments.py:105-116`); `bdm_user_id` from a BDM → 422 "bdm_user_id is only for managers"; from > to → 422 "date_from must be on or before date_to"; other roles 403 "BDM role required".

### C.2 Book appointment — `/bdm/appointments/new`

Page `web/app/bdm/appointments/new/page.tsx:13-49`: eyebrow "Appointments", heading **"Book appointment"**, sub "Times are India time (IST). You can book for organizations assigned to you." `?organization=<id>` preselects only if assigned to me and not archived (page.tsx:24-31); otherwise silently not preselected.

Form `web/components/BdmAppointmentForm.tsx` + `web/components/BdmAppointmentFields.tsx` + `web/components/BdmAppointmentTripField.tsx`:

| Fieldset / field | Type | Required / limits | Notes | Evidence |
|---|---|---|---|---|
| **Organization (required)** | searchable select | required; picker = my assigned, non-archived orgs (`assigned=me`, 20 per search, label = name, detail "CODE · City") | Hint: "Only organizations assigned to you can be booked." + link **Open organizations** | Form:162-184; `web/lib/bdmAppointments.ts:132-141` |
| Who → **Contact person (required)** | select of org contacts ("Name — Designation") | required on create; defaults to primary contact; "Loading contacts…" / "Choose a contact" | Load failure: "Unable to load this organization's contacts." | Fields:198-212; Form:30,90-98 |
| When → **Date and time (IST) (required)** | datetime-local | required; `min` = now IST; create only (edit has no time — that is Reschedule) | API: must be in the future (seconds dropped) | Fields:213-220 |
| When → **Duration** | select | default 60; options 15, 30, 45 min, 1 h, 1 h 30 min, 2 h, 3 h, 4 h, 6 h, 8 h, 12 h; API accepts any 15-720 | | Fields:221-230; `web/lib/bdmAppointments.ts:53` |
| Details → **Type (required)** | select | "Choose a type" + module list (C.0) | | Fields:232-244 |
| Details → **Location** | text | max 255 | | Fields:245-248 |
| Details → **Purpose** | textarea | max 1000 | | Fields:249-252 |
| Details → **Remarks** | textarea | max 2000 | | Fields:253-256 |
| Estimates → **Expected leads** | number | whole 0-1,000,000; error "Expected leads must be a whole number from 0 to 1,000,000." | | Fields:258-264; Form:35,42 |
| Estimates → **Expected revenue (INR)** | number | 0-9,999,999,999.99, ≤2 decimals; error "Expected revenue must be from 0 to 9,999,999,999.99, with up to 2 decimals." | | Fields:265-269; Form:36,44 |
| Travel → **Trip** | select | "No trip" + my open trips covering the chosen IST date; label "TRP-… · From → To (dd – dd)"; hints "Choose the date first." / "None of your open trips covers this date." / "Your trips couldn't be loaded — you can link this appointment to a trip later." Changing the date off the trip clears it | Trips read via `GET /api/v1/bdm/trips?linkable=true&limit=100` | `web/components/BdmAppointmentTripField.tsx` (whole file); `web/lib/bdmTripChoices.ts:7-13`; Form:86 |
| Submit | **"Book appointment"** (busy "Saving…"); disabled until org + contact chosen | On success → `/bdm/appointments/<id>?created=1` → notice "Appointment APT-000123 booked." | Form:195-198,125; Detail:59 |
| Overlap warning | Heading = API message **"You already have an appointment at this time"**, list "APT-… · <when> · <org>" (≤10, "and N more."), buttons **Save anyway** / **Cancel** (Esc dismisses) | Save anyway resends the exact checked body with `confirm_overlap: true` | `web/components/BdmOverlapAlert.tsx`; `api/services/bdm_appointments.py:215-249` |
| Generic failure | 5xx: "We couldn't save the appointment. Please try again — your entry is kept."; else server message | | Form:150-151 |

API `POST /api/v1/bdm/appointments` (`api/api/bdm_appointments.py:124-173`, schema `api/schemas.py:4503-4518`, `extra=forbid`). Refusal order (each one rule):

| # | Rule | Status / message |
|---|---|---|
| 1 | BDM profile gate | 403 "BDM role required" / "BDM profile not set up — contact your administrator" (`api/services/bdm.py:138-144`) |
| 2 | Org outside my type scope | 404 (org not found) |
| 3 | Org not assigned to me | 403 "Only the assigned BDM can book appointments for this organization" |
| 4 | Org archived (A4) | 422 "This organization is archived — restore it before booking" |
| 5 | Contact not of this org | 422 "Choose a contact of this organization" |
| 6 | Type not in my module | 422 "This appointment type is not available for <Type> BDMs" |
| 7 | Time not in future | 422 "Choose a time in the future" |
| 8 | Trip (bdm-011) | 404 "Trip not found" (not mine); 409 "This trip <state> and can't take appointments" (not planned/in progress); 422 "This appointment is on dd Mon yyyy, outside TRP-… (… – …)" (`api/services/bdm_travel.py:399-412`) |
| 9 | Overlap with my open appointments (A6) | 409 `{code:"possible_overlap", message:"You already have an appointment at this time", matches, total}` unless `confirm_overlap` (override audited `bdm_appointment.overlap_override`) |
| — | Created | status **Scheduled**, code **APT-NNNNNN** (sequence), contact details snapshotted; audit `bdm_appointment.create`. Not idempotent |

### C.3 Appointment detail — `/bdm/appointments/[id]`

Page `web/app/bdm/appointments/[id]/page.tsx:15-50`; not mine / unknown / malformed → card **"Appointment not found"** + "Back to appointments" (never says which). Component `web/components/BdmAppointmentDetail.tsx`.

| Block | Literal UI | Evidence |
|---|---|---|
| Title | Eyebrow "APT-… · <Type>"; heading "<Organization> <status pill>" + badges **Archived**, **Outcome pending**; link "Back to appointments"; button **Edit** (when `can_edit`) | Detail:95-118 |
| Notes | "Outcome pending — file the meeting report, or mark it as a no-show." (owner, started, open) | Detail:122-126 |
| Details card | **Date & time, Organization** (link), **Contact person, Designation, Mobile, Email, Type, Location, Purpose, Remarks, Expected leads, Expected revenue** (₹ en-IN, 2 dp), **BDM** ("(inactive)"), **Trip** (link "TRP-… · From → To" + " · Trip cancelled" / " · Trip not approved yet") | Detail:30-41,76-91 |
| Edit details | Same fields minus date/time (+ Trip); buttons **Save changes** / **Cancel**; notices "Changes saved." / "No changes to save."; removed contact note "The booked contact (<name>) was removed from the organization. Choose another contact to change it, or leave it as recorded." | Detail:132-150; Form:158-189 |
| History card | **"History"**: each event "<date time>", "Booked" or "<From> → <To>", "By <name>" + " · moved from <old> to <new>", "Reason: …" | `web/components/BdmAppointmentHistory.tsx:6-29` |

Status values (`web/lib/bdmAppointments.ts:12-20`): **Scheduled, Confirmed, Rescheduled, Completed, Cancelled, No show**. Open = Scheduled/Confirmed/Rescheduled (`api/models.py:3219`).

Transitions (`api/services/bdm_appointments.py:45-52`) and buttons (`web/components/BdmAppointmentActions.tsx`):

| Button (when shown) | From → To | Form / body | Server checks & messages | Success notice |
|---|---|---|---|---|
| **Confirm** (`can_confirm`: owner, status Scheduled or Rescheduled) | → Confirmed | none | 409 "Appointment is already <status>" | "Appointment confirmed." |
| **Reschedule** (open) | → Rescheduled (also from Rescheduled) | **New date and time (IST) (required)** (min now), **Duration**, **Reason** (optional, max 500); **Save new time** / **Cancel** | 422 "Choose a time in the future"; 422 "Choose a different time" (same time); overlap 409 → Save anyway; leaving trip dates unlinks the trip | "Appointment rescheduled." or "Appointment rescheduled. It is now outside TRP-…'s dates, so it was removed from that trip." |
| **Complete** (open **and** start time passed) | → Completed | Meeting report form (below) | 422 "You can only complete an appointment after its start time"; 409 = "This appointment changed elsewhere — copy your notes, then reload." + **Reload** | "Appointment completed." |
| **Mark no-show** (open and started) | → No show | **Reason (required)** max 500, counter "n/500", empty → "Enter a reason."; **Mark no-show** / **Keep it** | 422 "You can only mark a no-show after the start time"; reason required ("Reason is required") | "Marked as a no-show." |
| **Cancel appointment** (open) | → Cancelled | **Reason (required)**; **Yes, cancel it** / **Keep it** | as above | "Appointment cancelled." |
| Any 409 not overlap | — | refetch | — | "This appointment changed — it is now <Status>." |

All writes: scope 404 "Appointment not found" → owner 403 "Only the appointment's BDM can change it" → state 409 (`api/api/bdm_appointments.py:222-227`). Edit (`PATCH /{id}`) only while open; type re-checked per module; longer duration re-checks overlap (`api/api/bdm_appointments.py:182-219`).

Reminder buttons `?action=confirm|reschedule|cancel` (bdm-012): opens the matching action, never performs it (`web/lib/bdmAppointments.ts:106-110`; Actions:182-199). Notices: "Check the details, then select Confirm."; "This appointment is already confirmed."; "This appointment is <Status>, so it can no longer be <confirmed|rescheduled|cancelled>." (Detail:43-50). Source: day-before reminder links **Confirmed** (if not yet confirmed), **Reschedule**, **Cancel** (`api/services/bdm_reminders.py:119-128`). **VERIFICATION REQUIRED**: whether these links render as buttons in the in-app notification, the email, or both.

Meeting report (bdm-007) — `web/components/BdmMeetingReportForm.tsx`, `web/components/BdmMeetingReportSection.tsx`:

| Field | Type | Required / limit | Evidence |
|---|---|---|---|
| **Outcome (required)** | select ("Choose an outcome" + type list, C.0) | required | Form:48-55 |
| **Discussion (required)** | textarea | ≤4000; hint "What was discussed. Up to 4,000 characters." | Form:56-61 |
| **Requirements** / **Opportunity** | textarea | ≤2000 each | Form:62-68; `web/lib/bdmAppointments.ts:88` |
| **Next action** | textarea | ≤1000 | same |
| **Responsible person** | text | ≤200 | Form:69-73 |
| **Next follow-up (IST date)** | date | min today; hint "A date creates one follow-up for you."; API 422 "Next follow-up can't be in the past" | Form:74-79; `api/api/bdm_appointments.py:285-287` |
| Buttons | **Save report and complete** (complete) / **Save changes** (edit) / **Cancel** (or **Close** when locked); disabled until outcome + discussion | Form:80-87 |
| Leave guard | "Discard this meeting report?" | Form:27 |

Report card **"Meeting report"**: rows Outcome, Discussion, Requirements, Opportunity, Next action, Responsible person, Next follow-up, **Filed** ("<author>, <date time>"); legacy note "Recorded before meeting reports — outcome only."; **Edit report** + hint "You can change this report until midnight IST today."; afterwards "This report can no longer be changed."; save notice "Meeting report saved."; field errors "Check the highlighted fields." (Section:54-94). API `POST /{id}/complete` (`api/api/bdm_appointments.py:290-303`), `PATCH /{id}/report` (`:306-337`): 409 "This appointment has no meeting report" / "Meeting reports can only be changed on the day they were filed" (IST day; legacy never) (`api/services/bdm_appointments.py:61-62,165-167`).

Follow-up sync (`api/services/bdm_appointments.py:180-205`): a follow-up date creates task "Follow up on APT-…" (kind follow_up, source appointment_outcome) for the BDM; editing the date moves/reopens it; clearing cancels it with reason "Follow-up date removed from the meeting report"; if the follow-up is already done → 409 "This follow-up is already done".

---

### C.4 Follow-ups and tasks — `/bdm/follow-ups`

Page `web/app/bdm/follow-ups/page.tsx:12-36`: eyebrow "Follow-ups", heading **"Your follow-ups and tasks"**, sub "Dates are India time (IST).", fallback "Loading follow-ups…". Panel `web/components/BdmTasksPanel.tsx` (`isBdm`).

| Element | Literal UI | Evidence |
|---|---|---|
| Card heading + button | **"Follow-ups and tasks"** · **"Add follow-up or task"** | Panel:88,96-97 |
| Tabs (URL `?bucket=`, default Today) | **Today (n)**, **Overdue (n)**, **Upcoming (n)**, **Done (n)**, **Cancelled (n)** | Panel:109-119; `web/lib/bdmTasks.ts:7-9` |
| Org-type chips (toggle) | "<Org type> <count>" e.g. "Agent 3", "School 2", "No organization 1" (only non-zero) | Panel:120-129; `web/lib/bdmTasks.ts:56` |
| Filter | **Kind**: All / Follow-ups / Tasks; **Clear filters** | Panel:130-143 |
| Empty texts | Today "Nothing due today."; Overdue "No overdue follow-ups."; Upcoming "Nothing upcoming."; Done "Nothing done yet."; Cancelled "Nothing cancelled."; filtered "No items match these filters." | `web/lib/bdmTasks.ts:10-12`; Panel:163-167 |
| Errors | "Unable to load follow-ups." + **Retry**; session "Your session has ended — sign in again to continue." + return-to-login; refused write "<msg>. This item changed elsewhere — the list has been reloaded." | Panel:86,151-160; `web/lib/bdmTasks.ts:73` |
| Item (`BdmTaskItem`) | Title, badge **Follow-up**/**Task**, badge **"Overdue · N days"**; meta "Due <date>", org link + " · <Org type>" (+ **Archived**) or "No organization", link **"From APT-…"** or "Added by hand", notes, "Done <date time>", "Cancelled <date time> — <reason>" | `web/components/BdmTaskItem.tsx:49-75` |
| Item buttons | **Done** ("Marked done."), **Edit** (manual only), **Cancel task** (manual only; Reason required; **Cancel it** / **Keep it**; "Cancelled.") | TaskItem:76-87 |
| After Done | Notice + links **Log activity** (org activity section) and **Book appointment** (`/bdm/appointments/new?organization=`) when the org is not archived | Panel:85,100-105 |
| Pager (>50) | "Showing X–Y of N" Previous / Next | Panel:181-187 |
| Ordering | open: due date asc; Done: completed desc; Cancelled: cancelled desc | `api/services/bdm_tasks.py:78-83` |

Add / edit form `web/components/BdmTaskForm.tsx`:

| Field | Type | Rules | Evidence |
|---|---|---|---|
| **Kind** (create only) | radio Follow-up / Task | default Follow-up | :61-70 |
| **Title (required)** | text | ≤200; "Title is required" | :71-75 |
| **Due date (IST, required)** | date | min today (edit of an already-past item has no min); "Choose a due date"; API 422 "Due date can't be in the past" | :76-80 |
| **Organization (optional)** | searchable select (my assigned orgs) — or fixed "Organization: <name>" when opened from an org page | API 403 "Only the assigned BDM can add tasks for this organization"; 422 "This organization is archived — restore it before adding tasks" | :81-88 |
| **Notes** | textarea | ≤2000, counter "n/2000" | :89-95 |
| Buttons | **Add** / **Save changes**, **Cancel**; success "Added." / "Changes saved."; failure "We couldn't save this. Please try again."; guard "Discard this task?" | :103-106 |

API (`api/api/bdm_tasks.py`): `GET /api/v1/bdm/tasks` (:25-47; `bucket` today/overdue/upcoming/open/done/cancelled, `kind`, `org_type` incl. `none`, `organization_id`; counts per tab and per org type), `POST` (:50-73), `PATCH /{id}` (:76-94), `POST /{id}/complete` (:97-107), `POST /{id}/cancel` (:110-121). Rules (`api/services/bdm_tasks.py`): own items only (:36-47); writes 404 "Task not found" → 403 "Only the assigned BDM can change this task"; 409 "This task is already done" / "This task was cancelled"; edit/cancel of an appointment follow-up → 409 "Change this follow-up from its meeting report" (Done is allowed); daily cap 200 manual items → 409 "You've added 200 tasks today"; overdue = open and due before today IST; archiving an organization cancels its open items with reason "Organization archived" (:187-195).

---

### C.5 Activity log — `/bdm/activities`

Page `web/app/bdm/activities/page.tsx:15-57`; component `web/components/BdmActivityDay.tsx`.

| Element | Literal UI | Evidence |
|---|---|---|
| Header | eyebrow "Activities", heading **"My activities"**, sub "Calls, WhatsApp messages, emails, visits and meetings you logged. You can change an entry on the day it happened." | page.tsx:36-38 |
| Day picker | **Day** (date, max today) + **Show** (plain GET `?date=`). Bad date → "That isn't a valid date — showing today."; future → "Dates after today can't be shown — showing today." | page.tsx:39-46; `web/lib/bdmActivities.ts:52-57` |
| Button | **Log activity** | Day:53-55 |
| Count tiles ("Day counts") | **Calls made** (outgoing calls), **Organizations contacted** (distinct), **Call, WhatsApp, Email, Visit, Meeting, Other** | `web/components/BdmActivityCounts.tsx:6-10`; `api/services/bdm_activities.py:166-180` |
| List item | time; badge "<Channel> · Outgoing/Incoming"; org link; "<contact> · Logged by <name>" ("(removed)" if contact deleted); note; **Edit** / **Delete** only when `can_change` | `web/components/BdmActivityItem.tsx:57-85` |
| Delete confirm | "Delete this <channel>? It is removed from today's counts." **Yes, delete** / **Keep it** | Item:86-91 |
| Notices | "Activity logged." / "Activity logged for <date>. Change the day to see it." (backdated) / "Activity saved." / "Activity deleted."; refresh failure "The list couldn't be refreshed. Reload the page to see the latest entries and counts." | Day:38-39,63,76-77 |
| Empty / more | "No activities on this day." · **Load more** (50 per page) | Day:15,70-83 |

Log / edit form `web/components/BdmActivityForm.tsx`:

| Field | Type | Rules | Evidence |
|---|---|---|---|
| **Organization (required)** | searchable select of my assigned orgs (activities page only; fixed on org page) | "Choose an organization." | :123-129 |
| **Channel (required)** | select Call / WhatsApp / Email / Visit / Meeting / Other | default Call | :130-136 |
| **Direction (required)** | radio **Outgoing** / **Incoming** — only for Call, WhatsApp, Email | "Choose outgoing or incoming." (API: "Choose outgoing or incoming for a call, WhatsApp or email"; "Direction applies only to calls, WhatsApp and email") | :137-149; `api/schemas.py:4711-4723` |
| **When (required)** | datetime-local, max now, default now | hint "Your local time. Up to 7 days back."; "Enter when it happened." | :150-157 |
| **Contact** | select "No contact" + org contacts | API 422 "Choose a contact of this organization" | :158-165 |
| **Note** | textarea ≤500, counter "n / 500" | hint "Everyone who can see this organization can read this note." | :166-173 |
| Buttons | **Save activity** / **Save changes**, **Cancel**; "Check the highlighted fields."; 5xx "The server couldn't save this activity. Your entry is kept — try again."; guard "Discard this activity?" | :174-177,116 |

API (`api/api/bdm_activities.py`): `GET /api/v1/bdm/activities?date=` (:36-43; own only, `channel`, `organization_id`; future day 422 "That date hasn't happened yet"), `POST /api/v1/bdm/activities` (:46-69), `PATCH /activities/{id}` (:87-112), `DELETE /activities/{id}` (:115-123, hard delete), `GET /organizations/{org_id}/activities` (:126-132, every BDM's activity on an org I can read — org timeline). Rules (`api/services/bdm_activities.py:33-46`):

| Rule | Message |
|---|---|
| Only the org's assigned BDM logs (create) | 403 "Only the organization's assigned BDM can log activity" |
| Archived org | 422 "This organization is archived" |
| Future (>5 min tolerance; within tolerance clamped to now) | 422 "When can't be in the future" |
| Backdate > 7 IST days | 422 "Activities can be logged up to 7 days back" |
| Daily cap 200 per IST day | 409 "You've logged 200 activities for this day" |
| Edit/delete only by the logger | 403 "Only the BDM who logged this activity can change it" |
| Edit/delete only same IST day | 409 "Only today's activities can be changed" |
| Moving an activity to another day | 422 "An activity can only be moved within today" |
| Daily report submitted for that day (bdm-015) | 409 "This day's report has been submitted, so its activities can't be changed" (also blocks backdated logging onto a submitted day) (`api/services/bdm_daily_reports.py:25,51-55`) |

Org timeline (`web/components/BdmActivityTimeline.tsx`, on org detail): heading **"Activity"**, **Log activity** only on `/bdm/organizations/*` when I can edit the org (`BdmOrganizationDetail.tsx:249`); empty "No activity logged yet."; error "Activity couldn't be loaded." + **Try again**; **Load more** (20 per page).

---


---

## PART D — Travel (`/bdm/travel/*`) and Daily report (`/bdm/daily-report`)

Decisions (labels only): travel = bdm-010 **DEC-SCOPE-063** (T1–T16); trip ↔ appointment links, itinerary, productivity, travel report = bdm-011 **DEC-SCOPE-092** (L1–L4, D17); travel reminder = bdm-012; daily report = bdm-015 **DEC-SCOPE-099** (R1–R8). Code is the authority.

### D.0 Shared rules (travel)

| Topic | Rule (code) | Evidence |
|---|---|---|
| Gate | Every own-trip route calls `bdm_context`: non-`bdm` → 403 "BDM role required"; no profile → 403 "BDM profile not set up — contact your administrator" | `api/services/bdm.py:138-145` |
| Scope | Own trips only (`BdmTrip.bdm_user_id == user.id` in the WHERE); another BDM's trip = **404 "Trip not found"** | `api/services/bdm_travel.py:152-159` |
| Agent vs School | **No difference.** No travel rule reads `bdm_type`; agent, school (and college) BDMs get the same screens/rules | `api/services/bdm_travel.py` (no `bdm_type` reference) |
| "Today" | India calendar date (Asia/Kolkata) | `api/services/bdm_travel.py:33,66-67`; `web/lib/bdmTravel.ts:96` |
| Trip code | `TRV-` + 6-digit sequence (e.g. TRV-000012) | `api/services/bdm_travel.py:131-132` |
| Two statuses | **Approval**: `draft` "Draft", `submitted` "Submitted", `approved` "Approved", `rejected` "Rejected". **Travel**: `planned` "Planned", `in_progress` "In progress", `completed` "Completed", `cancelled` "Cancelled". Shown as badges "Approval: X" + "Travel: Y" | `web/lib/bdmTravel.ts:6-7,35-36`; `web/components/TripStatusBadges.tsx:7-8` |
| Modes | `flight` Flight, `train` Train (form default), `bus` Bus, `car` Car, `cab` Cab, `local` "Local travel" | `web/lib/bdmTravel.ts:34`; `web/components/TripForm.tsx:27` |
| Expense categories | `travel` Travel (default), `stay` Stay, `food` Food, `local` Local, `other` Other | `web/lib/bdmTravel.ts:37`; `web/components/TripExpenseRowForm.tsx:14` |
| Currency | INR only (server-owned) | `api/services/bdm_travel.py:137` |
| Receipts / attachments | **None.** No upload field, no receipt model, no "receipt" string anywhere in travel code. Expenses are category + amount + date + note only | grep of `api/services/bdm_travel.py`, `web/components/Trip*.tsx` (no hits) |
| Notifications (in-app only, `channels=[]`) | Submit → reporting manager (or every active super_admin if the manager is inactive) gets **"Travel approval needed"** "TRV-…: From → To, 18 Sep 2026"; decision → BDM gets **"Trip approved"** / **"Trip not approved"** linking `/bdm/travel/{id}` | `api/api/bdm_travel.py:28-29,71-74,134-135`; `api/services/bdm_travel.py:226-232` |
| Reminder | Day before an **approved + planned** trip (active BDM): "Travel reminder" — "Tomorrow (<day>): travel to <To>. BDM: <name>. Purpose: … Appointments: N." with links **View Appointments** (`#trip-appointments`), **View Expenses** (`#trip-costs`), **Add Remarks** (`#trip-remarks`) | `api/services/bdm_reminders.py:154-170`; deep-link scroll `web/components/TripWorkspace.tsx:51-56` |
| Audit | `bdm.trip_<action>` per change (create/update/submit/withdraw/start/complete/cancel/approve/reject/expense_add/expense_update/expense_delete) | `api/services/bdm_travel.py:124-128` |

### D.0.1 Transition table (the single source of both enforcement and the `can_*` flags)

`RULES` `api/services/bdm_travel.py:50-59`; flags `:62-63,108-109`; owner buttons render only when the flag is true (`web/components/TripActions.tsx:25`).

| Action (button) | Allowed when | Result | Success text (UI) |
|---|---|---|---|
| Edit (Edit trip card / PATCH non-remark fields) | approval ∈ {draft, rejected} AND travel = planned | fields changed | "Trip saved." |
| **Submit for approval** | same as edit | approval → submitted, `submitted_at` set, previous rejection reason/decider cleared | "Submitted for approval." |
| **Withdraw** | approval = submitted AND travel = planned | approval → draft | "Withdrawn to draft." |
| (manager) decide | approval = submitted AND travel = planned | approved / rejected (reason required) | — |
| **Start trip** | approval = approved AND travel = planned AND today ≥ travel date | travel → in_progress | "Trip started." |
| **Mark completed** | approval = approved AND travel ∈ {planned, in_progress} AND today ≥ travel date (Start is optional) | travel → completed, `completed_at` | "Trip completed." |
| **Cancel trip** (inline confirm) | travel ∈ {planned, in_progress} (any approval state) | travel → cancelled, `cancelled_at` | "Trip cancelled." |
| Add/edit/delete expense | approval = approved (any travel state incl. completed/cancelled) | line written | "Expense added." / "Expense updated." / "Expense deleted." |
| Remarks | **every state** (incl. completed, cancelled) | remarks saved/cleared | "Remarks saved." |

Owner actions by state (derived from the table):

| Approval / Travel | Buttons shown to owner |
|---|---|
| Draft / Planned | Edit trip card, Submit for approval, Cancel trip |
| Submitted / Planned | Withdraw, Cancel trip |
| Rejected / Planned | warning "**Not approved.** <reason> Edit the trip and submit it again." + Edit trip card, Submit for approval, Cancel trip |
| Approved / Planned, before travel date | Cancel trip, Add expense |
| Approved / Planned, on/after travel date | Start trip, Mark completed, Cancel trip, Add expense |
| Approved / In progress | Mark completed, Cancel trip, Add expense |
| Approved / Completed | Add expense, "View travel report", remarks |
| Any / Cancelled | remarks; Add expense only if it had been approved |

409 refusal wording (`api/services/bdm_travel.py:87-105,178-181`):
- generic: "This trip <phrase> and can't be <verb>" — phrases "is still a draft", "is waiting for approval", "is already approved", "was not approved", "is in progress", "is completed", "is cancelled"; verbs edited/submitted/withdrawn/decided/started/completed/cancelled.
- date: "This trip starts on 18 Sep 2026; it can be started from that day" (or "completed").
- expense: "Expenses can be added once the trip is approved"; limit "A trip can have at most 100 expense lines".
- edit while submitted: 409 "Withdraw the trip to edit it"; while approved: 422 "An approved trip's details can't be changed".
- A refused write shows the reason at the top of the page and re-reads the trip (`web/components/TripWorkspace.tsx:39-50,76`).

---

### D.1 My trips — `/bdm/travel` (`web/app/bdm/travel/page.tsx:17-68`)

- Eyebrow "Travel", heading **"My trips"**, text "Plan a trip, send it to <reporting manager name> for approval, then add expenses once it is approved." Button **New trip** (`:36-41`).
- Filter form (plain GET): **Approval status** select — All / Draft / Submitted / Approved / Rejected; buttons **Filter**, **Clear filter** (only when filtered) (`:43-53`). Unknown value is ignored, not sent (`:21`). No travel-status filter in the UI although the API accepts `travel_status` (`api/api/bdm_travel.py:33`) — **VERIFICATION REQUIRED** whether a URL `?travel_status=` is honoured (page does not forward it: it isn't).
- Table (`web/components/TripTable.tsx:20-41`): columns **Trip** (code, link) · **Status** (two badges) · **Dates** ("18 Sep 2026 – 20 Sep 2026", single date if same day) · **Route** ("From → To") · **Estimated** · **Actual** (sum of expenses) · **Mode**. Sorted newest travel date first, then code desc (`api/api/bdm_travel.py:25`).
- Pager when total > 50: "Showing 1–50 of N", **Previous** / **Next** (`TripTable.tsx:44-49`; PAGE_SIZE 50 `web/lib/bdm.ts:29`; API limit 1–100 `api/api/bdm.py:24`).
- Empty states (`page.tsx:54-61`): "No trips yet — create your first trip." · "No trips match this filter. Clear filter" · "This page is past the end of your trips. Go to the first page".
- API: `GET /api/v1/bdm/trips?limit&offset&approval_status` → `my_trips` `api/api/bdm_travel.py:32-40`.

### D.2 New trip — `/bdm/travel/new` (`web/app/bdm/travel/new/page.tsx:13-38`; form `web/components/TripForm.tsx`)

- Eyebrow "Travel", heading **"New trip"**, text "Saved as a draft. You can edit it until you submit it for approval." Button **Back to my trips**.

| Field (label) | Type | Required | Limits / rules (client + API) | Evidence |
|---|---|---|---|---|
| Travel date | date | yes | min = today − 30 days; API "Travel date can be at most 30 days in the past"; malformed → "Enter a valid travel date" | `TripForm.tsx:97-99,43,46`; `api/services/bdm_travel.py:74-80`; `api/schemas.py:3660-3675` |
| Return date | date | yes | ≥ travel date ("Return date must be on or after the travel date"); ≤ travel + 30 ("A trip can last at most 31 days") | `TripForm.tsx:101-104,47-48` |
| From | text | yes | max 120, trimmed, no control characters ("From contains invalid characters") | `TripForm.tsx:106-112`; `api/schemas.py:3678` |
| To | text | yes | max 120, same | same |
| Mode of travel | select | yes (default Train) | 6 modes above | `TripForm.tsx:113-119` |
| Estimated cost (₹) | text, decimal | yes | `^\d+(\.\d{1,2})?$` "Enter an amount in rupees with up to 2 decimals"; API adds ", for example 2500.50", ≥ 0 ("The estimated cost can't be negative"), ≤ ₹1,00,00,000 ("The amount can be at most ₹1,00,00,000"); 0 allowed | `TripForm.tsx:120-124,49`; `api/schemas.py:3621-3653` |
| Purpose | textarea (3 rows) | yes | max 1000, multi-line | `TripForm.tsx:126-130`; `api/schemas.py:3679` |
| Accommodation required | checkbox | no (default off) | — | `TripForm.tsx:131-136` |
| Remarks | textarea | no | max 2000; **create only** (later edited in the Remarks section) | `TripForm.tsx:137-143`; `api/schemas.py:3681` |

- Required message pattern "<Label> is required"; summary "Check the highlighted fields." (`TripForm.tsx:42,75`). Button **Save draft** / busy "Saving…"; success "Trip saved as a draft." then redirect to `/bdm/travel/{id}` (`:81,145`). Fieldset disabled until hydrated (`:62,94`).
- API: `POST /api/v1/bdm/trips` → `create_trip` `api/api/bdm_travel.py:43-49`; body `BdmTripCreate` `extra=forbid` (`api/schemas.py:3687-3700`); created as `draft`/`planned` (`api/services/bdm_travel.py:135-142`). No notification on create.

### D.3 Trip page — `/bdm/travel/[id]` (`web/app/bdm/travel/[id]/page.tsx:13-30`; `web/components/TripWorkspace.tsx`)

- Malformed id (not UUID) → access card "Trip not found" without calling the API (`page.tsx:16`; `web/components/TravelUnavailable.tsx:22`).
- Header: eyebrow "Travel · TRV-…", heading "From → To", status badges; buttons **View travel report** (only when travel = completed) and **Back to my trips** (`TripWorkspace.tsx:65-75`).
- Sections in order:

| Section | Content / labels | Evidence |
|---|---|---|
| (actions) | Buttons per D.0.1; Cancel confirm: "**Cancel TRV-…?** A cancelled trip can't be restarted. Expenses already added stay on it." **Confirm cancel** / **Keep trip** (Escape backs out) | `web/components/TripActions.tsx:11-16,46-61` |
| **Trip details** | dl: Travel ID, BDM, Travel date, Return date, From, To, Mode of travel, Accommodation required (Yes/No), Purpose, Approval status, Travel status; + "Approved by"/"Rejected by" "<name>, <date>", "Completed", "Cancelled" when set | `web/components/TripDetails.tsx:7-22` |
| **Edit trip** (only `can_edit`) | Same TripForm without Remarks; button **Save changes**; sends only changed fields; nothing changed → "Nothing to change." | `TripWorkspace.tsx:93-98`; `TripForm.tsx:85-89,145` |
| **Appointments** (`#trip-appointments`) | Table Time · Organization (link to appointment) · Meeting · Status; time shows day when trip spans several days. Empty: "No appointments are linked to this trip yet. Link one from an appointment's Edit form, or Book an appointment." Notes: "Trip not approved yet — these appointments depend on the manager's approval." / "This trip is cancelled. Its appointments stay listed for the record; reschedule or cancel them on each appointment." | `web/components/TripItinerary.tsx:10-45` |
| **Productivity** | KPI tiles: Meetings planned, Meetings completed, Estimated cost, Actual cost, Cost per completed meeting ("No completed meetings yet"), Expected leads / Expected revenue ("No estimates entered"), Actual leads, Actual revenue (badge "Not tracked yet" — always, D17) | `web/components/TripProductivity.tsx:11-21`; `api/services/bdm_travel.py:453-471` |
| **Costs and expenses** (`#trip-costs`) | Estimated, Actual, Difference ("On the estimate" / "₹X over/under the estimate", only once an expense exists); table Date · Category · Amount · Note · Actions (Edit/Delete); empty "No expenses yet."; hint "Expenses can be added once the trip is approved." (owner, not approved, still planned); button **Add expense**; delete confirm "**Delete the <Category> expense of ₹X?**" **Delete expense** / **Keep** | `web/components/TripExpenses.tsx:15-100` |
| **Remarks** (`#trip-remarks`) | textarea, counter "N / 2000", **Save remarks**; blank clears; editable in every state | `web/components/TripRemarks.tsx:10-33` |

- Expense line form (`web/components/TripExpenseRowForm.tsx`): **Category** (select), **Amount (₹)** (> 0, 2 decimals: "Enter an amount in rupees with up to 2 decimals" / "The amount must be more than ₹0"), **Date** (default = travel date; "Date is required" / "Enter a valid expense date"), **Note (optional)** (max 500). Buttons **Save expense** / **Cancel**. No check that the expense date lies within the trip dates (client or API) — see findings.
- Productivity rules: cancelled appointments listed but not counted; cost per completed meeting = actual cost / completed; Actual leads = BDM's own leads of organisations met (completed), created travel date … return date + 7 days IST (`api/services/bdm_travel.py:433-450,460-471`).
- Date edit vs linked appointments: an open linked appointment outside new dates → 422 "N linked appointment(s) fall outside the new dates — unlink or reschedule it/them first"; closed ones are silently unlinked and recorded in audit (`api/services/bdm_travel.py:419-430`).
- APIs: `GET /api/v1/bdm/trips/{id}` (`api/api/bdm_travel.py:52-55`); `PATCH /api/v1/bdm/trips/{id}` (`:58-64`, rules `api/services/bdm_travel.py:171-191`); `POST /api/v1/bdm/trips/{id}/{submit|withdraw|start|complete|cancel}` (`api/api/bdm_travel.py:67-87`); `POST /trips/{id}/expenses` (`:159-161`), `PATCH /trips/{id}/expenses/{eid}` (`:164-167`), `DELETE …/expenses/{eid}` (`:170-172`); expense not on this trip → 404 "Expense not found" (`api/services/bdm_travel.py:338-342`).
- Manager side (not in scope, note only): `TripDecision` Approve / Reject ("Reason for rejecting", required, ≤1000; "Reason is required"), only when `can_decide`; deciders = reporting manager, or any super_admin only while that manager is inactive; a BDM can't decide own trip (`web/components/TripDecision.tsx`; `api/services/bdm_travel.py:112-116,300-321`).

### D.4 Travel report — `/bdm/travel/[id]/report` (`web/app/bdm/travel/[id]/report/page.tsx:12-39`; `web/components/TripReport.tsx`)

- Title: eyebrow "Travel report · TRV-… · <BDM name>", heading "From → To", button **Back to the trip** (`TripReport.tsx:30-40`).
- Sections: **Trip details**, **Appointments**, **Productivity** (same components as D.3), **Expenses by category** (Category · Amount, then **Total** = actual cost; empty "No expenses were recorded."), **Remarks** (or "No remarks were added.") (`TripReport.tsx:42-69`). Read-only.
- Not completed → API 409 **"The travel report is available once the trip is completed"**, shown as a status card under the title (`api/api/bdm_travel.py:113-122`; `page.tsx:28-35`).
- API: `GET /api/v1/bdm/trips/{id}/report`.

### D.5 Travel error page (`web/components/TravelUnavailable.tsx:8-19`)

401/403/404 → the shared "Access unavailable" card. Any other failure → heading **"Travel is not available right now"**, text "We could not load this page. Your trips are safe; please try again.", button **Retry** (same URL).

---

### D.6 Daily report — `/bdm/daily-report` (`web/app/bdm/daily-report/page.tsx:17-49`; `web/components/BdmDailyReport.tsx` mode `bdm`)

- Eyebrow "Daily report", heading **"Daily report — <18 Sep 2026>"**, text "The day's counts come from what you recorded: activities, appointments, trips, MoUs, leads and follow-ups." Day picker form: **Day** (date, max today) + **Show** (`page.tsx:31-42`).
- `?date=` rules: missing → today; invalid → today + "That isn't a valid date — showing today."; future → today + "Dates after today can't be shown — showing today." (`web/lib/bdmActivities.ts:52-57`). API also refuses a future day: 422 "That date hasn't happened yet" (`api/services/bdm_daily_reports.py:30-32`; `api/services/bdm_activities.py:46`).
- Status line (`BdmDailyReport.tsx:76-84`):
  - not submitted, in window: "A live preview of the day's counts. Add a note and submit at the end of the day."
  - not submitted, older than window: "Reports can be submitted up to 7 days back. These counts are a live preview."
  - submitted: "Submitted <date time>. These counts were saved when the report was submitted."
- Counts grid: one tile per count = label, value (or **"Not tracked"** when the metric has no source), definition text under it (`BdmDailyReport.tsx:85-93`).
- Submit section (only when `can_submit`): **End-of-day note (optional)** textarea, hint "Your reporting manager reads this note. On a day off, say so here.", counter "N / 2000"; button **Submit report** → inline confirm "Submitting saves these counts and locks this day's activities. You can't undo it." **Yes, submit** (busy "Submitting…") / cancel (`:111-131`). Success "Report submitted. This day's activities are now locked." (`:42`).
- After submit: card **End-of-day note** (or "No note.") and, if the manager commented, **Manager's comment** + "<name>, <date time>" (`:97-109`). The BDM cannot edit the note or re-submit.

| Rule | Code | Evidence |
|---|---|---|
| Report row exists only after submit; before that = live preview (`status: "draft"`) | `report_out` | `api/services/bdm_daily_reports.py:1-6,58-75` |
| Submission window | today − 7 … today (IST), same as activity backdate window (V4) | `api/services/bdm_daily_reports.py:22-23,35-36`; `api/services/bdm_activities.py:33` |
| Too old | 422 "Reports can be submitted up to 7 days back" | `api/api/bdm_daily_reports.py:43-44` |
| Once per day | 409 "This day's report has already been submitted" (lock + unique constraint backstop) | `api/api/bdm_daily_reports.py:45-54` |
| Snapshot | counts frozen into the row at submit (with `bdm_type` at that time) | `api/api/bdm_daily_reports.py:48`; `api/services/bdm_daily_reports.py:67,71` |
| Day lock | after submit, any activity write for that BDM+day → 409 "This day's report has been submitted, so its activities can't be changed" | `api/services/bdm_daily_reports.py:25,51-55`; used by `api/services/bdm_activities.py:88` |
| Note | optional, trimmed, ≤ 2000, multi-line, no control chars ("Note contains invalid characters"); unknown body keys → 422 | `api/schemas.py:6316-6325` |
| Edit after submit | none for the BDM; manager may add/replace one comment (≤1000) | `api/api/bdm_daily_reports.py:115-128` |
| No deadline reminder / missed-report alert to the BDM | none found in bdm daily report code; manager grid shows "Missing" | `api/api/bdm_daily_reports.py:94-99` — **VERIFICATION REQUIRED** whether any reminder exists elsewhere |
| Audit | `bdm_daily_report.submitted` (date only, never the note) | `api/services/bdm_daily_reports.py:78-80` |

- APIs: `GET /api/v1/bdm/daily-reports/{YYYY-MM-DD}` → `my_report` `api/api/bdm_daily_reports.py:30-35`; `POST /api/v1/bdm/daily-reports/{date}/submit` body `{note}` → `submit_report` `:38-58`. Counts: `daily_counts` `api/services/bdm_metrics.py:316-324`.

### D.6.1 Counts per BDM type (R1, `DAILY_REPORTS` `api/services/bdm_metrics.py:294-313`; definitions `DAILY_METRICS` `:267-291`)

All counts are the BDM's own records on the IST day.

| # | Agent BDM label | Source (key → definition) | School BDM label | Source |
|---|---|---|---|---|
| 1 | Calls made | calls_made — "Outgoing calls you logged that day." | Schools contacted | schools_contacted — "Schools with an activity you logged or a meeting you completed that day." |
| 2 | Agents contacted | agents_contacted — "Agents with an activity you logged or a meeting you completed that day." | Calls | calls_made (outbound calls) |
| 3 | Meetings | meetings_completed — "Your appointments completed that day." | Meetings | meetings_completed |
| 4 | New prospects | new_prospects — "Agent organizations you created that day." | School visits | school_visits — "Visits you logged that day." |
| 5 | New agents | **Not tracked** — "Not tracked yet: agent onboarding links arrive with the agent onboarding handover." | Presentations | presentations — career guidance, psychometric and profile building presentations completed |
| 6 | Agreements | mous_signed — "MoUs you moved to Signed that day." | Proposals | proposals_sent — "MoUs you moved to Proposal Sent that day." |
| 7 | Agent training | agent_training — "Your product training sessions completed that day." | MoUs | mous_signed |
| 8 | Follow-ups | follow_ups_completed — "Follow-ups you marked done that day." | Follow-ups | follow_ups_completed |
| 9 | Student leads generated | student_leads — "Student leads you entered that day." | Students generated | students_generated — "Students added that day in the schools linked to your organizations." |
| 10 | Applications generated | **Not tracked** — "Not tracked yet: Agent CRM applications are not linked to BDM organizations." | Career guidance sessions | career_guidance_sessions |
| 11 | Enrollments generated | **Not tracked** — "Not tracked yet: Agent CRM enrollments are not linked to BDM organizations." | Psychometric sessions | psychometric_sessions |

College (out of scope) has its own 11 rows incl. "Colleges contacted", "Appointments fixed", "Travel completed", "Proposals sent", "MoUs discussed" — note: **"Travel completed" appears only for College BDMs**; Agent/School daily reports do not count trips even though the page sub-heading mentions "trips" (`api/services/bdm_metrics.py:295-300`; `web/app/bdm/daily-report/page.tsx:34`).

### D.7 Agent vs School differences (this part)

| Area | Agent BDM | School BDM |
|---|---|---|
| Travel list/form/rules/report | identical | identical |
| Appointment types in itinerary "Meeting" column | agent appointment types (labels from `TYPE_LABEL`, see appointments part) | school appointment types |
| Daily report tiles | 11 agent tiles; 3 always "Not tracked" (New agents, Applications generated, Enrollments generated) | 11 school tiles; all tracked |
| Daily-report count that needs Schools data | — | Students generated needs organisations linked to a School (`school_id`) |

---


---

## (a) Proposed feature rows

Modules: NAV, DAY, NOTIF, CAL, MEET, UNI (Part A); ORG, CONT, PROF, PIPE, ONB, ORGP, LEAD, MOU (Part B); APPT, FUP, ACT (Part C); TRAV, RPT (Part D). Role "bdm" means agent and school BDMs unless the row says otherwise.

### (a.1) Shell, My Day, notifications, calendar, meeting requests, universities

| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| DOC-BDM-NAV-001 | Sign in to the Overseas portal as an Agent/School BDM (chooser + wrong-portal message) | `/bdm/sign-in`, `/overseas/login` | bdm (agent/school) | `POST /api/v1/auth/login` |
| DOC-BDM-NAV-002 | Portal shell, sidebar and unread badge | all `/bdm/*` | bdm | `GET /api/v1/bdm/me`, `GET /api/v1/workflows/notifications/unread-count` |
| DOC-BDM-NAV-003 | View my BDM profile | `/bdm/profile` | bdm | `GET /api/v1/bdm/me` |
| DOC-BDM-NAV-004 | Account profile and password (footer links) | `/account/profile`, `/account/password` | bdm | `PATCH /api/v1/auth/me`, change-password route |
| DOC-BDM-NAV-005 | "Access unavailable" (profile not set up / wrong role) | any `/bdm/*` | bdm | `GET /api/v1/bdm/me` |
| DOC-BDM-DAY-001 | My Day: today's appointments, upcoming travel, follow-ups | `/bdm/my-day` | bdm | `GET /api/v1/bdm/my-day` |
| DOC-BDM-DAY-002 | My Day: Agent overview tiles | `/bdm/my-day` | bdm (agent) | `GET /api/v1/bdm/my-day` |
| DOC-BDM-DAY-003 | My Day: School overview tiles | `/bdm/my-day` | bdm (school) | `GET /api/v1/bdm/my-day` |
| DOC-BDM-DAY-004 | My Day: monthly targets card | `/bdm/my-day` | bdm | `GET /api/v1/bdm/targets` |
| DOC-BDM-DAY-005 | My Day: meeting requests card | `/bdm/my-day` | bdm | `GET /api/v1/bdm/meeting-requests?status=pending&limit=5` |
| DOC-BDM-NOTIF-001 | Read and open notifications | `/bdm/notifications` | bdm | `GET /api/v1/workflows/notifications`, mark-read |
| DOC-BDM-NOTIF-002 | Reminder catalogue (appointment, travel, follow-up/task, MoU follow-up/renewal) + email action links | `/bdm/notifications` | bdm | beat `run_bdm_reminders` |
| DOC-BDM-NOTIF-003 | Decision notices (trip approved/not approved, onboarding outcome, handover) | `/bdm/notifications` | bdm | — |
| DOC-BDM-CAL-001 | Calendar week/day view and navigation | `/bdm/calendar` | bdm | `GET /api/v1/bdm/calendar` |
| DOC-BDM-MEET-001 | Meeting request inbox and filters | `/bdm/meeting-requests` | bdm | `GET /api/v1/bdm/meeting-requests` |
| DOC-BDM-MEET-002 | View a meeting request | `/bdm/meeting-requests/[id]` | bdm | `GET /api/v1/bdm/meeting-requests/{id}` |
| DOC-BDM-MEET-003 | Accept a request and book the appointment | `/bdm/meeting-requests/[id]` | bdm | `POST …/{id}/accept` |
| DOC-BDM-MEET-004 | Decline a request with a reason | `/bdm/meeting-requests/[id]` | bdm | `POST …/{id}/decline` |
| DOC-BDM-UNI-001 | View the linked University Master record | `/bdm/universities/[id]` | bdm | `GET /api/v1/universities/{id}/view` |

### (a.2) Organisations, contacts, profiles, pipeline, onboarding, panels, leads, MoUs

| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| DOC-BDM-ORG-001 | Browse and filter module organisations | /bdm/organizations | bdm (agent/school) | GET /bdm/organizations |
| DOC-BDM-ORG-002 | Add an organisation (incl. duplicate warning) | /bdm/organizations/new | bdm | POST /bdm/organizations |
| DOC-BDM-ORG-003 | View organisation details (read-only for non-assigned) | /bdm/organizations/[id] | bdm | GET /bdm/organizations/{id} |
| DOC-BDM-ORG-004 | Edit organisation details | /bdm/organizations/[id] | bdm (assigned) | PATCH /bdm/organizations/{id} |
| DOC-BDM-ORG-005 | Archive an organisation (manager restores) | /bdm/organizations/[id] | bdm (assigned) | POST …/archive |
| DOC-BDM-CONT-001 | Manage contacts (add, edit, primary, delete, min 1 / max 20) | /bdm/organizations/[id] | bdm (assigned) | POST/PATCH/DELETE …/contacts |
| DOC-BDM-PROF-001 | Agent organisation details (type profile) | /bdm/organizations/new, [id] | bdm | POST/PATCH /bdm/organizations (profile) |
| DOC-BDM-PROF-002 | School organisation details (board, type, grades) | /bdm/organizations/new, [id] | bdm | same |
| DOC-BDM-PROF-003 | Changing an organisation's type (clear-first rule) | /bdm/organizations/[id] | bdm (assigned) | PATCH (409 profile_not_empty) |
| DOC-BDM-PIPE-001 | Move an organisation through pipeline stages (back needs reason) | /bdm/organizations/[id] | bdm (assigned) | POST …/stage |
| DOC-BDM-PIPE-002 | Mark lost and revive | /bdm/organizations/[id] | bdm (assigned) | POST …/lost, …/revive |
| DOC-BDM-PIPE-003 | Read stage history | /bdm/organizations/[id] | bdm | GET …/stage-history |
| DOC-BDM-PIPE-004 | Pipeline board (Mine / All in module, stage tiles, Lost) | /bdm/pipeline | bdm | GET /bdm/pipeline |
| DOC-BDM-ONB-001 | Request agent onboarding (Agreement Signed → AGN link) | /bdm/organizations/[id] | agent bdm (assigned) | POST …/onboarding-request |
| DOC-BDM-ONB-002 | Request school onboarding (MoU Signed/Active → School) | /bdm/organizations/[id] | school bdm (assigned) | POST …/onboarding-request |
| DOC-BDM-ORGP-001 | Agent performance panel | /bdm/organizations/[id] | agent bdm | GET …/agent-performance |
| DOC-BDM-ORGP-002 | School activity panel | /bdm/organizations/[id] | school bdm | GET …/school-activity |
| DOC-BDM-LEAD-001 | Add and view student leads on an organisation | /bdm/organizations/[id] | bdm (assigned adds; module reads) | GET/POST …/leads |
| DOC-BDM-MOU-001 | Start and edit an organisation's MoU (status, dates, signing confirm) | /bdm/organizations/[id] | bdm (assigned) | GET/POST/PATCH …/mou |
| DOC-BDM-MOU-002 | Upload / download the MoU document | /bdm/organizations/[id] | bdm (assigned uploads; module downloads) | PUT …/mou/document, GET /mous/{id}/document |
| DOC-BDM-MOU-003 | MoU history, expiry and renewal | /bdm/organizations/[id] | bdm (assigned) | GET /mous/{id}/history, POST …/mou, GET /mous?current=false |
| DOC-BDM-MOU-004 | MoU list by status | /bdm/mous | bdm | GET /bdm/mous |

### (a.3) Appointments, follow-ups, activities

| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| DOC-BDM-APPT-001 | View and filter my appointments | /bdm/appointments | bdm (agent, school) | GET /api/v1/bdm/appointments |
| DOC-BDM-APPT-002 | Book an appointment (incl. overlap warning) | /bdm/appointments/new | bdm | GET /api/v1/bdm/organizations?assigned=me, GET /api/v1/bdm/organizations/{id}, POST /api/v1/bdm/appointments |
| DOC-BDM-APPT-003 | Link an appointment to a trip | /bdm/appointments/new, /bdm/appointments/[id] | bdm | GET /api/v1/bdm/trips?linkable=true, POST / PATCH /api/v1/bdm/appointments |
| DOC-BDM-APPT-004 | Appointment detail, edit details and history | /bdm/appointments/[id] | bdm | GET, PATCH /api/v1/bdm/appointments/{id} |
| DOC-BDM-APPT-005 | Confirm, reschedule, cancel an appointment | /bdm/appointments/[id] | bdm | POST …/{id}/confirm, …/reschedule, …/cancel |
| DOC-BDM-APPT-006 | Complete with a meeting report / mark no-show | /bdm/appointments/[id] | bdm | POST …/{id}/complete, POST …/{id}/no-show |
| DOC-BDM-APPT-007 | Edit the meeting report on the same day; book next meeting | /bdm/appointments/[id] | bdm | PATCH …/{id}/report |
| DOC-BDM-APPT-008 | Act on an appointment reminder (?action=) | /bdm/appointments/[id]?action= | bdm | GET /api/v1/bdm/appointments/{id}; workflow notifications |
| DOC-BDM-FUP-001 | Follow-up tabs, counts and filters | /bdm/follow-ups | bdm | GET /api/v1/bdm/tasks |
| DOC-BDM-FUP-002 | Add a follow-up or task | /bdm/follow-ups | bdm | POST /api/v1/bdm/tasks |
| DOC-BDM-FUP-003 | Mark done, edit, cancel a task | /bdm/follow-ups | bdm | POST /api/v1/bdm/tasks/{id}/complete, PATCH /api/v1/bdm/tasks/{id}, POST …/{id}/cancel |
| DOC-BDM-FUP-004 | Follow-ups created from meeting reports | /bdm/follow-ups, /bdm/appointments/[id] | bdm | POST …/appointments/{id}/complete, PATCH …/report, GET /api/v1/bdm/tasks |
| DOC-BDM-ACT-001 | My activities for a day with counts | /bdm/activities | bdm | GET /api/v1/bdm/activities?date= |
| DOC-BDM-ACT-002 | Log an activity (incl. backdating) | /bdm/activities | bdm | POST /api/v1/bdm/activities |
| DOC-BDM-ACT-003 | Edit or delete today's activity | /bdm/activities | bdm | PATCH, DELETE /api/v1/bdm/activities/{id} |
| DOC-BDM-ACT-004 | Organization activity timeline | /bdm/organizations/[id] | bdm | GET /api/v1/bdm/organizations/{id}/activities, POST /api/v1/bdm/activities |

### (a.4) Travel, daily report

| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| DOC-BDM-TRAV-001 | View and filter my trips | /bdm/travel | bdm (agent/school) | GET /api/v1/bdm/trips |
| DOC-BDM-TRAV-002 | Plan a new trip (draft) | /bdm/travel/new | bdm | POST /api/v1/bdm/trips |
| DOC-BDM-TRAV-003 | Read a trip (details, appointments, productivity) | /bdm/travel/[id] | bdm | GET /api/v1/bdm/trips/{id} |
| DOC-BDM-TRAV-004 | Edit a draft or rejected trip | /bdm/travel/[id] | bdm | PATCH /api/v1/bdm/trips/{id} |
| DOC-BDM-TRAV-005 | Submit for approval / withdraw | /bdm/travel/[id] | bdm | POST …/trips/{id}/submit, …/withdraw |
| DOC-BDM-TRAV-006 | Handle a rejected trip (read reason, fix, resubmit) | /bdm/travel/[id] | bdm | PATCH, POST …/submit |
| DOC-BDM-TRAV-007 | Start, complete or cancel a trip | /bdm/travel/[id] | bdm | POST …/start, …/complete, …/cancel |
| DOC-BDM-TRAV-008 | Record trip expenses (add/edit/delete) | /bdm/travel/[id]#trip-costs | bdm | POST/PATCH/DELETE …/trips/{id}/expenses[/{eid}] |
| DOC-BDM-TRAV-009 | Trip remarks | /bdm/travel/[id]#trip-remarks | bdm | PATCH …/trips/{id} {remarks} |
| DOC-BDM-TRAV-010 | Link appointments to a trip (itinerary) — cross-ref APPT form | /bdm/travel/[id]#trip-appointments, /bdm/appointments/[id] | bdm | GET /api/v1/bdm/trips?linkable=true; appointment PATCH (APPT part) |
| DOC-BDM-TRAV-011 | Travel report of a completed trip | /bdm/travel/[id]/report | bdm | GET …/trips/{id}/report |
| DOC-BDM-TRAV-012 | Travel notifications and day-before reminder | /bdm/notifications → trip | bdm | GET /api/v1/workflows/notifications |
| DOC-BDM-RPT-001 | View a day's live report (pick a day) | /bdm/daily-report | bdm | GET /api/v1/bdm/daily-reports/{date} |
| DOC-BDM-RPT-002 | Submit the daily report with note (locks the day) | /bdm/daily-report | bdm | POST /api/v1/bdm/daily-reports/{date}/submit |
| DOC-BDM-RPT-003 | Read a submitted report and manager's comment | /bdm/daily-report?date= | bdm | GET /api/v1/bdm/daily-reports/{date} |
| DOC-BDM-RPT-004 | What each count means (Agent vs School tiles) | /bdm/daily-report | bdm | (same GET; definitions in payload) |

---

## (b) Test data needed before screenshots

### (b.1) Part A

| Feature | Data |
|---|---|
| NAV-001..005 | One active Agent BDM and one School BDM (overseas division) with profiles incl. designation/department/territory and an active reporting manager; one `bdm` user without a profile (for Access unavailable); one College BDM to show the wrong-portal message |
| DAY-001 | For each BDM: ≥2 appointments today (one confirmed), 1 cancelled today (excluded), ≥2 approved future trips (one with linked appointments), open follow-ups due today/overdue at agent/school orgs, one MoU-sourced follow-up, one without organisation |
| DAY-002 | Agent BDM: agent_meeting/agent_visit today, agent org created today, agent org with current MoU proposal_sent, open `task` at agent org, trip today/tomorrow |
| DAY-003 | School BDM: principal_meeting, management_meeting, seminar/workshop appts today, visit activity today, school orgs with MoU proposal_sent / discussion_started |
| DAY-004 | Manager-set targets for current month for both BDMs (incl. one not-tracked KPI); a BDM with no targets for the empty state |
| DAY-005 / MEET-001..004 | Telecaller (overseas) files: agent request named for the Agent BDM, agent pool request, school pool request, one past-proposed-time request; one accepted, one declined (with reason); the BDM must own ≥1 active organisation with a contact for accept |
| NOTIF-001..003 | Seeded notifications (or run reminder task at 09:00 IST) for each kind; trip approved + rejected; onboarding outcome; handover |
| CAL-001 | A week with a multi-day trip (departs/away/returns), a day trip, seminar appointment, task done, overdue follow-up |
| UNI-001 | University Master record with stage + primary partnership manager; a University-type organisation (assigned to the BDM) linked to it |

### (b.2) Part B

| Feature | Data |
|---|---|
| ORG-001 | 1 Agent BDM + 1 School BDM (same manager) and a 2nd BDM per module; ≥3 orgs each per module, mixed org types and cities, ≥1 assigned to the other BDM, ≥1 archived; >50 orgs for the pager (optional); ≥1 org with completed + future appointment (Last/Next meeting) |
| ORG-002 | an existing org with same name+city in the module (duplicate warning) |
| ORG-003/004/005 | one assigned org (editable) and one assigned to a colleague (read-only); one org to archive (with an open follow-up to show cancellation) |
| CONT-001 | org with 2+ contacts (one primary) and org with exactly 1 contact |
| PROF-001/002/003 | Agent-type org with country/territory/source/staff; School-type org with board/school type/grades; one org with filled profile for the type-change refusal |
| PIPE-001..004 | orgs spread across several manual stages per module; one Lost org with reason; history with a forward move, a backward move with note, a lost and a revive |
| ONB-001 | Agent-module org at Agreement Signed (ready); one pending; one rejected (Overseas Admin rejects); one linked to an AGN agency (Active, with Master and staff logins, students/applications) |
| ONB-002 | School-module org with MoU Signed (ready); pending; rejected; one linked to a School (School ID) |
| ORGP-001 | linked agency with students, applications in several stages, offers, visa, enrolled; optional suspended agency |
| ORGP-002 | linked School with students and some guidance/psychometric/language/IELTS/shortlist records |
| LEAD-001 | org with 2+ leads (one converted); an existing lead email for the duplicate warning |
| MOU-001..004 | MoUs in several statuses across orgs; one Signed with valid-until in the past (Expired); one Rejected; one renewed (previous MoU); one PDF document uploaded |

### (b.3) Part C

| Feature | Data |
|---|---|
| APPT-001 | One agent BDM and one school BDM, each with ≥3 assigned orgs (one archived) and ≥55 appointments across all 6 statuses (to show pager), incl. one open appointment in the past (Outcome pending) |
| APPT-002 | Assigned non-archived org with ≥2 contacts (one primary); an existing open appointment at a chosen slot to trigger the overlap warning; an unassigned org in module (to show it is absent from the picker) |
| APPT-003 | An approved/planned trip covering a future date and one cancelled/completed trip; appointment on a date inside the trip |
| APPT-004 | Appointment with all optional fields, expected revenue, a trip, and ≥3 history events (booked, rescheduled with reason); one whose contact was deleted |
| APPT-005 | Scheduled future appointment (confirm/reschedule/cancel); trip-linked appointment to reschedule outside trip dates |
| APPT-006 | Open appointment whose start time has passed (needs DB time or a backdated seed — booking requires future time) |
| APPT-007 | Completed appointment with report filed today (editable) and one filed yesterday (locked); school appointment with outcome Reschedule; a legacy report row |
| APPT-008 | An in-app "Appointment reminder" notification for a Scheduled appointment due tomorrow (reminder job run) |
| FUP-001 | Open items due yesterday/today/next week, done and cancelled items, items with and without an organization, both kinds; ≥51 in one tab for pager |
| FUP-002/003 | Assigned org for the picker; one manual open task; one appointment follow-up (to show missing Edit/Cancel) |
| FUP-004 | Appointment completed with a next follow-up date |
| ACT-001..003 | Activities today on all 6 channels (incl. outgoing and incoming calls) across ≥2 orgs; one activity 3 days ago; a contact deleted after logging; a day whose daily report is submitted (locked) |
| ACT-004 | Org with activities from two BDMs (e.g., after a reassignment), >20 rows for Load more |

### (b.4) Part D

| Feature | Data |
|---|---|
| TRAV-001 | One agent BDM + one school BDM, each with an active reporting manager; ≥ 1 trip in each approval state (draft, submitted, approved, rejected) and travel state (in_progress, completed, cancelled); > 50 trips on one BDM only if pager screenshot wanted; one BDM with zero trips for the empty state |
| TRAV-002 | Clean BDM; known "today" for the 30-days-past / 31-day-span validation shots |
| TRAV-003/010 | Approved trip spanning 2–3 days with 2–3 linked appointments (one completed with expected leads/revenue, one cancelled) to fill Productivity; a draft trip with a linked appointment for the "not approved yet" note |
| TRAV-004/006 | Draft trip; rejected trip with a manager reason (manager must reject it — needs manager login) |
| TRAV-005 | Draft trip → submit (manager receives "Travel approval needed") |
| TRAV-007 | Approved trip with travel date = today or past (for Start/Complete); approved trip with future date (shows only Cancel) |
| TRAV-008 | Approved trip with 3+ expense lines across categories; one not-yet-approved trip for the hint |
| TRAV-009 | Any trip; a completed trip to show remarks still editable |
| TRAV-011 | Completed trip with expenses + remarks; a non-completed trip for the 409 card |
| TRAV-012 | Approved planned trip with travel date = tomorrow + reminder job run (**VERIFICATION REQUIRED**: how the reminder sweep is triggered on the docs stack); approve/reject notices |
| RPT-001..004 | For the chosen day, each BDM needs: outbound call + visit activities, completed appointments of relevant types (product_training for agent; career_guidance/psychometric/profile_building presentations for school), MoU moved to proposal_sent and signed, a follow-up task marked done, a BDM-attributed lead (agent), an agent org created that day (agent), a School-linked organisation with a student added that day (school). One unsubmitted day within 7 days, one submitted day (with note), one with a manager comment (manager login), one day > 7 days back |

---

## (c) Open questions / product findings

### (c.1) Part A

| # | Finding | Evidence |
|---|---|---|
| NAV-1 | BDM can edit own name/phone at `/account/profile` though `/bdm/profile` says to contact the administrator | `api/api/auth.py:35`; `web/app/bdm/profile/page.tsx:25` |
| NAV-2 | Sidebar is identical for Agent, School and College BDMs; "Management tasks" visibility for BDM — **VERIFICATION REQUIRED** | `web/lib/navigation.ts:72-81` |
| DAY-1 | T-A6 "Agents awaiting onboarding" marked not tracked while bdm-019 onboarding requests exist | `api/api/bdm_my_day.py:35` |
| DAY-2 | Agent targets "New Agents"/"Active Agents"/"Applications"/"Enrollments" are not tracked — users see "(not tracked)" | `api/services/bdm_metrics.py:400-416` |
| NOTIF-1 | No notification when a telecaller files a meeting request for a BDM | `api/api/bdm_meeting_requests.py:39-54` |
| MEET-1 | Accept requires the BDM to choose one of their own organisations; if the requested organisation does not exist yet, the BDM must create it first — workflow to document — **VERIFICATION REQUIRED** in browser | `web/components/MeetingRequestDecide.tsx:225` |
| UNI-1 | Any BDM can view any University Master by id (no link check) | `api/services/university_view.py:65-72` |
| UNI-2 | Agent/School BDMs can create `university`-type organisations — intended? | `api/models.py:2935` |
| UNI-3 | Role pill on university page reads "BDM" instead of "<Type> BDM" (cosmetic) | `web/app/bdm/universities/[id]/page.tsx:23` |

### (c.2) Part B

| # | Finding | Evidence | Status |
|---|---|---|---|
| B-Q1 | `org_type` is independent of module: an Agent BDM can create a "School"/"College"/"University" type org in the Agent module; the profile section follows org type while pipeline/onboarding follow module. Is that intended, and should the manual recommend matching types? | `api/schemas.py:3833,4015`; `api/api/bdm_organizations.py:115-118` | **VERIFICATION REQUIRED** |
| B-Q2 | Overseas BDMs can create University-type orgs and link to the Global University Master; `/bdm/universities/[id]` opens from there. Confirm whether Agent/School BDMs are expected to use this. | `web/components/BdmOrganizationDetail.tsx:131-138` | **VERIFICATION REQUIRED** |
| B-Q3 | A BDM cannot restore their own archived org (manager only) — the manual must say "ask your manager". | `api/services/bdm_organizations.py:109-113` | settled from code |
| B-Q4 | Agent commission is never shown to BDMs ("Commission: Not shown to BDMs (awaiting a decision)") — decision still open per code comment. | `web/lib/bdmOrganizations.ts:108-111` | NEEDS_CONFIRMATION (owner) |
| B-Q5 | Pipeline "Reason" blank message wording depends on `BDM_TRIP_FIELD_LABELS["reason"]` — verify in the browser. | `api/schemas.py:3625-3634` | **VERIFICATION REQUIRED** |
| B-Q6 | Leads added by Agent/School BDMs enter the overseas telecaller distribution (`on_intake`) — the manual should state what happens next; BDM sees only status/converted. | `api/api/bdm_leads.py:45-52` | **VERIFICATION REQUIRED** (downstream visibility) |
| B-Q7 | School onboarding uses the MoU status while Agent onboarding uses the pipeline stage; for an Agent org, signing an MoU auto-advances to Agreement Signed, so both paths converge — confirm wording for users. | `api/services/bdm_onboarding.py:56-61`; `api/bdm_stages.py:90` | settled from code; wording to confirm |
| B-Q8 | Last/Next meeting columns use appointments of any BDM at the org (when, not who). | `api/services/bdm_organizations.py:225-242` | settled from code |

### (c.3) Part C

| # | Finding | Evidence | Status |
|---|---|---|---|
| C-1 | Task source `mou` exists in the enum and UI type, but no code creates a MoU-sourced task — MoU reminders seem to be notifications only | `api/models.py:3367`; only creators `api/api/bdm_tasks.py:64`, `api/services/bdm_appointments.py:187` | VERIFICATION REQUIRED |
| C-2 | Activity "When" uses the browser's local time ("Your local time") while every other BDM date/time is IST; a BDM whose device is not on IST sees different day boundaries | `web/components/BdmActivityForm.tsx:155`; `web/lib/agentTasks.ts:51-60` | Product finding |
| C-3 | Agent outcome list has no "Reschedule" outcome, so agent BDMs never get the "Book the next meeting" shortcut | `web/lib/bdmAppointments.ts:44`; Section:89 | Product finding / confirm intended (A8) |
| C-4 | Completing / no-show requires the start time to have passed, but booking requires a future time — a meeting held without prior booking cannot be recorded as an appointment (only as an activity) | `api/services/bdm_appointments.py:145-152` | Confirm intended |
| C-5 | Edit details and Done on a follow-up give no way to change an appointment follow-up's date except via the meeting report, which locks at IST midnight of the filing day — after that, the date can never move (only Done) | `api/services/bdm_tasks.py:26,71-75`; `api/services/bdm_appointments.py:165-167` | Product finding |
| C-6 | Reminder action links (Confirmed / Reschedule / Cancel) — channel(s) where they render not settled from code | `api/services/bdm_reminders.py:119-128` | VERIFICATION REQUIRED |
| C-7 | Which organization types an agent/school BDM holds (affects follow-up org-type chips and pickers) | `api/services/bdm_tasks.py:123-129` | VERIFICATION REQUIRED (organisations part) |
| C-8 | Activity daily cap (200) and task daily cap (200) messages are reachable only with seeded abuse data; not screenshot-worthy | `api/services/bdm_activities.py:35`; `api/services/bdm_tasks.py:31` | Doc note only |

### (c.4) Part D

| # | Finding | Evidence |
|---|---|---|
| D-F1 | **No receipt/bill upload for trip expenses** — task brief mentions "receipts upload limits", none exist. Confirm this is intended for the manual (or a gap) | `api/services/bdm_travel.py`, `web/components/TripExpense*.tsx` |
| D-F2 | Expense date is not checked against the trip's travel–return dates (any valid date accepted) | `web/components/TripExpenseRowForm.tsx:27-28`; `api/schemas.py:3724-3729` |
| D-F3 | Expenses can still be added/edited/deleted after a trip is **completed or cancelled** (rule only needs approval = approved) — confirm intended (D15) | `api/services/bdm_travel.py:58` |
| D-F4 | "Mark completed" is offered without "Start trip" first (planned → completed directly) — confirm wording for the manual | `api/services/bdm_travel.py:56` |
| D-F5 | Cancelling a draft/submitted trip is allowed; a submitted trip that is cancelled leaves the manager notice in place — **VERIFICATION REQUIRED** what the manager's approval queue shows (filter excludes non-planned, so it disappears) | `api/services/bdm_travel.py:57,324-330` |
| D-F6 | Travel list has no Travel-status filter in the UI though the API supports one | `web/app/bdm/travel/page.tsx:43-53`; `api/api/bdm_travel.py:33` |
| D-F7 | Actual revenue tile is permanently "Not tracked yet" (D17) | `api/services/bdm_travel.py:470` |
| D-F8 | Agent daily report has 3 permanently "Not tracked" tiles (New agents, Applications generated, Enrollments generated) — manual must explain; confirm whether still true after AGN/agent-onboarding work | `api/services/bdm_metrics.py:282-285` |
| D-F9 | Daily-report sub-heading says counts come from "trips", but no Agent/School tile counts trips (only College "Travel completed") | `web/app/bdm/daily-report/page.tsx:34`; `api/services/bdm_metrics.py:294-313` |
| D-F10 | Agent "Agreements" and School "MoUs" both count MoUs moved to Signed by the BDM on **any** organisation (not filtered to own type in the daily list) — **VERIFICATION REQUIRED** whether `_owned` limits it sufficiently | `api/services/bdm_metrics.py:223-232,278` |
| D-F11 | No submission deadline time or reminder for the BDM; a missed day is simply "Missing" on the manager grid, and can be submitted up to 7 days late | `api/services/bdm_daily_reports.py:22-36`; `api/api/bdm_daily_reports.py:94-99` |
| D-F12 | A submitted report can't be corrected by the BDM (note or counts); activities of that day are locked — confirm escalation path (who can unlock?) — none found in code | `api/services/bdm_daily_reports.py:51-55` |
