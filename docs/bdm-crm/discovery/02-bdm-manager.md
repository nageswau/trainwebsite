# Discovery: BDM Manager portal (role `bdm_manager`)

> **Evidence appendix** for `docs/bdm-crm/documentation-analysis.md`. This is raw, read-only source discovery (S1, 2026-10-17, code `main` @ `6fee294d`, worktree `.claude/worktrees/bdm-docs`). It gives field-level detail for the module sessions. It is **not browser-verified**: where this file and the browser disagree, the browser wins and this file gets an annotation (it is not trusted silently).

Nothing was run. Every statement comes from source. Path prefixes: `web/` = `apps/web/`, `api/` = `apps/api/app/`. All API paths are mounted under `/api/v1`. Legend: **VERIFICATION REQUIRED** = not settled from code; confirm in the browser or with the owner. Decision IDs (DEC-SCOPE-055, -060, -071, -079, -098, -103, -108, -113 …) are cited only as labels taken from code comments. Code is the authority.

The manual's focus is a manager over **Overseas** BDMs (types `agent` and `school`). Rows marked **[OVS]** call out type- or division-specific behaviour. College BDMs (`college`, division `it`) are out of scope, but where a manager page still shows College rows or columns, this file says so.

---

## 0. Cross-cutting facts (read first)

### 0.1 Account, sign-in and landing
| Fact | Evidence |
|---|---|
| Role `bdm_manager`, division `global`. Only super_admin creates managers (`CREATOR_TYPES` lets admins create BDMs only). | `api/services/bdm.py:21-25` |
| BDM type → division is fixed: `college → it`, `agent → overseas`, `school → overseas` (D3). A manager has no type or division of their own. | `api/services/bdm.py:20` |
| Demo account: `bdm.manager@edusphere.local`, "Sanjay BDM Manager". Direct reports: "Rahul Agent BDM" (agent, BDM-DEMO-001, Hyderabad), "Kavya School BDM" (school, BDM-DEMO-002, Bengaluru), "Vivek College BDM" (college, BDM-DEMO-003, Chennai). The demo manager is therefore **mixed-type, not Overseas-only** [OVS]. | `api/seed.py:863-871` |
| Sign-in is at `/admin/login`. After login, `ROLE_DASHBOARD_PATH.bdm_manager = "/bdm/manager/dashboard"`. | `web/lib/navigation.ts:47` |
| Middleware sends a signed-out visitor of `/bdm/manager/*` to `/admin/login?next=…`. Other `/bdm/*` pages go to `/bdm/sign-in?next=…`. | `web/middleware.ts:11-18` |
| The `/bdm/sign-in` chooser (heading "BDM sign-in") says: "Choose the portal for your module. BDM Managers sign in at **Administration**." It also has the buttons "College BDM" (`/it/login`) and "Agent / School BDM" (`/overseas/login`). | `web/app/bdm/sign-in/page.tsx:16-20` |
| `/bdm/manager` redirects to `/bdm/manager/dashboard` (it is also a sign-in `next` target). | `web/app/bdm/manager/page.tsx:1-6` |

### 0.2 Shell and sidebar (`BDM_MANAGER_NAV`, `web/lib/navigation.ts:82-96`)
The sidebar shows these items in this order: **Dashboard, Performance, Master view, Team, Organizations, Pipeline, MoUs, Appointments, Requests, Follow-ups, Calendar, Activities, Daily reports, Targets, Approvals, Notifications, Management tasks**. Notifications goes to `/bdm/manager/notifications` (`navigation.ts:71`); Management tasks goes to `/account/management-tasks` (mgmt-028, `navigation.ts:11`).
- Notifications carries an **unread badge** from `GET /api/v1/workflows/notifications/unread-count` (`web/lib/bdmNav.ts:6-16`). The top bar repeats the count (`TopbarUnread`). If the count can't be read, the page still renders, just without the badge.
- Footer: "Change password", "My profile", "Sign out". Top bar: "EduSphere Portal" plus the user's name. Below the desktop breakpoint the mobile menu (`PortalMobileNav`) replaces the sidebar and lists "Notifications (N unread)" (`web/components/PortalShell.tsx:17`).
- Role pill: "BDM Manager". A super_admin sees "Super Admin" on most pages, and "Super Administrator" with the **admin** sidebar on Dashboard, Performance, Master view, Trips and Trip report (`web/lib/bdmPerformancePage.ts:12-15`, `dashboard/page.tsx:53`, `trips/[id]/page.tsx:27`).
- **The Team and Approvals pages always show "BDM Manager"**, even for a super_admin (`team/page.tsx:26`, `approvals/page.tsx:29`). Minor.
- An item is marked active only on an exact path match (`aria-current` when `pathname===href`, `PortalShell.tsx:17`). Detail pages (`/organizations/[id]`, `/appointments/[id]`, `/daily-reports/[bdmId]`, `/targets/[bdmId]`, `/performance/[type]`, `/performance/bdms/[id]`, `/trips/[id]`) therefore highlight nothing.

### 0.3 Authorization model (as built)
| Rule | Evidence |
|---|---|
| Manager gate is `require_manager`: the role must be `bdm_manager` or `super_admin`, otherwise **403 "BDM manager role required"**. | `api/services/bdm.py:148-150` |
| Shared read scopes (organizations, appointments, tasks, MoUs, meeting requests) use their own `caller_scope`/`caller_filters`, which answer **403 "BDM role required"** to any other role. | `api/services/bdm_organizations.py:80-91`, `bdm_appointments.py:105-116`, `bdm_tasks.py:36-47`, `bdm_meeting_requests.py:88-99` |
| Frontend guard: most pages call `/auth/me` and show `accessDenied(user, "This page is for BDM managers.")` for other roles. Team, Approvals, Dashboard, Performance and Master view have no frontend role check: the API refuses and the page shows the access card. Notifications denies even super_admin with "BDM manager role required". | each `page.tsx`; `notifications/page.tsx:18` |
| **Team scope (D4)**: a manager's BDMs are exactly their **direct reports** (`BdmProfile.reporting_manager_user_id == manager`). super_admin sees all. There is **no multi-level hierarchy**: a manager never sees another manager's BDMs. | `api/services/bdm.py:153-155` |
| Team scope **includes inactive BDMs**. The Team list, organizations, appointments and trips of inactive reports stay visible. The Daily reports and Targets grids list **active** BDMs only. | `api/api/bdm.py:72-88`; `bdm_daily_reports.py:82`; `bdm_targets.py:45` |
| Organization scope for a manager = organizations whose **assigned BDM** reports to them (any org type). | `api/services/bdm_organizations.py:86-88` |
| Out-of-scope record = **404** with a plain "not found" (Organization / Appointment / Trip / BDM not found). The page never says which. | each `load_scoped` |
| **The manager is read-only almost everywhere.** The only manager writes are: reassign an organization, restore an archived organization, approve or reject a trip, comment on a submitted daily report, set targets and copy last month's targets. | sections below |
| A manager **cannot archive** an organization (only the assigned BDM or super_admin). | `api/services/bdm_organizations.py:109-113` |

### 0.4 Type specifics in manager pages [OVS]
| Surface | Type behaviour | Evidence |
|---|---|---|
| Pipeline | Offers only the BDM types that exist in the team (one count per type). An Overseas-only team sees Agent and School only. | `pipeline/page.tsx:13,26-27` |
| Performance (§5 table) | **Always three columns** (Agent BDM, School BDM, College BDM), because `TYPES` is fixed. An Overseas-only team sees a College column of zeros. | `api/api/bdm_performance.py:64-90`; `web/components/BdmPerformanceTable.tsx:64-76` |
| Master view | **Always three sections**. An empty one reads "No College BDMs in this team." | `api/services/bdm_performance.py:213-250`; `BdmHierarchy.tsx:42` |
| Appointments Type filter | Lists **all** appointment types (`ALL_TYPES`, 37 values incl. College ones such as "HOD Meeting" and "Placement Cell Meeting"). | `appointments/page.tsx:32`; `web/lib/bdmAppointments.ts:28-40` |
| Organizations Type filter | All 7 org types: College, University, Agent, School, Corporate, Training Institute, Other. The profile filter that appears depends on the Type: School → "Board", Agent → "Territory", College → "University / affiliation". | `BdmOrganizationsPanel.tsx:17,150-185`; `web/lib/bdmOrganizations.ts:19-22` |
| Meeting requests | Manager sees their team's requests **plus the whole open pool of every type** (College and Corporate included). | `api/services/bdm_meeting_requests.py:94-96` |
| Org detail panels | "School activity" for school orgs, "Agent performance" for agent orgs, "Business" for college orgs only. | `organizations/[id]/page.tsx:52`; `BdmOrganizationDetail.tsx:223-224,259` |
| Targets / Daily report KPIs | A per-type catalogue (§7, §8 below). | `api/services/bdm_metrics.py:294-314,438-447` |

### 0.5 Shared list idioms
- Page size 50 (`web/lib/bdm.ts:29`). The pager reads "Showing a–b of N" with **Previous** and **Next**. A hand-edited `?offset=` past the end shows "This page is past the end of …" with **Go to the first page**.
- Client panels (Organizations, Appointments, Follow-ups) keep their filters in the URL and show "Loading …", then "Updating …" while a change lands, and "Unable to load …" with **Retry**.
- Server pages use plain GET forms with a **Show** button (Activities, Daily reports, Targets, Pipeline, Performance).
- IST everywhere: "Times are India time (IST)." An invalid date in the URL shows "That isn't a valid date — showing today." and a future date shows "Dates after today can't be shown — showing today." (`web/lib/bdmActivities.ts:52-56`).
- **No CSV, export or download** exists on any manager page or BDM manager API (no `csv`/`xlsx` match). The only file served is the MoU document (§11).

---

## 1. Dashboard: `/bdm/manager/dashboard` (landing page)
- Frontend: `web/app/bdm/manager/dashboard/page.tsx:28-91`, with the body in `web/components/BdmManagerDashboard.tsx:14-63` and the wording in `web/lib/bdmManagerDashboard.ts`.
- APIs: `GET /bdm/manager/team?limit=50` (`api/api/bdm.py:72`); `GET /bdm/manager/dashboard[?manager_user_id=]` (`api/api/bdm_manager_dashboard.py:158`). super_admin also reads `GET /admin/bdm-managers?limit=100` (`api/api/bdm.py:109`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 | "Dashboard" / "Your team" (super_admin: "All BDM teams" or "<name>'s team") |
| Team summary | "No BDMs report to you yet." or "N BDMs report to you: A active, I inactive" plus " on the first page" when the team has more than 50 BDMs (counts come from the first 50 rows only, `page.tsx:17-23`) |
| Button | **View team** (only when the team is not empty) |
| super_admin filter | "Team" select with "All teams" and "<name> (<email>)" options, then **Show** |
| Section 1 | "BDM overview" — "Today and this month, India time (IST)." — 8 KPI tiles (label, value in en-IN format, definition) |
| Section 2 | "Alerts". Empty: "No alerts right now." Each alert: a tone word, then "<label>: <count>", a list of up to 10 items, "Showing X of N." when there are more, and **View all** |
| Error | "Unable to load the dashboard." + **Try again** (super_admin with a manager chosen also gets **Show all teams**) |

**Tiles** (`api/api/bdm_manager_dashboard.py:44-53`, built at `:83-104`):
| Key | Label | Definition (shown under the value) |
|---|---|---|
| T-M01 | Total BDMs | Active BDMs. |
| T-M02 | Today's Appointments | Appointments starting today, except cancelled ones. |
| T-M03 | Upcoming Appointments | Scheduled, confirmed or rescheduled appointments after today. |
| T-M04 | BDMs Travelling | BDMs on an approved trip that covers today. |
| T-M05 | Trips This Month | Trips starting this month, except cancelled or rejected ones. |
| T-M06 | Meetings Completed | Appointments this month that are completed. |
| T-M07 | MoUs in Progress | Current MoUs from Discussion Started to Draft Shared. |
| T-M08 | MoUs Signed | MoUs moved to Signed this month. |

**Alerts** (`:55-63`, rules at `:120-155`). The tone word comes from `TONE`: danger → "Urgent", warning → "Attention", success → "Done" (`bdmManagerDashboard.ts:128-132`). An alert with count 0 is not listed.
| Key | Label | Tone | Rule | Item time text | Item link / View all |
|---|---|---|---|---|---|
| AL-1 | Appointment not confirmed | Attention | Status Scheduled/Rescheduled, starting within the next 24 h | "Starts 8 Oct, 10:00" | appointment / Appointments |
| AL-2 | Travel approval pending | Attention | Trip Submitted + Planned | "Travels 8 Oct" | trip / Approvals (super_admin: `/admin/bdm-travel-approvals`) |
| AL-3 | Follow-up overdue | Urgent | Open follow-up (kind `follow_up`, not task) due before today | "Due …" | organization, or Follow-ups / Follow-ups |
| AL-4 | MoU pending | Attention | Current MoU at Proposal Sent or Draft Shared for 5 days or more (D19) | "Waiting since …" | organization / MoUs |
| AL-5 | Appointment completed | Done | Completed today (IST) | "Completed 14:30" | appointment / Appointments |
| AL-6 | Outcome missing | Urgent | Open appointment whose start time has passed (`pending_filter`) | "Started …" | appointment / Appointments |
| AL-7 | Daily report not submitted | Attention | Active BDM, profile existed before today, no report for **yesterday** | "Report for …" (no BDM name) | daily report of yesterday / Daily reports |

Rules: super_admin may pass `manager_user_id`; any other caller gets 422 "Only a super admin can choose a manager", and an unknown manager is 404 "Manager not found" (`:66-76`). Read-only: no writes, no audit.

---

## 2. Team: `/bdm/manager/team`
- Frontend: `web/app/bdm/manager/team/page.tsx:13-47`, table in `web/components/BdmTeamTable.tsx:10-43`. Server-rendered; paging by link (`?offset=`), 50 per page.
- API: `GET /bdm/manager/team?limit&offset[&bdm_type][&q]` (`api/api/bdm.py:72-88`). `q` matches name, email or Employee ID; it is ANDed with team scope. Ordered by name, then id.

| UI element | Literal text |
|---|---|
| Eyebrow / H2 | "Team" / "BDMs who report to you" |
| Columns | Name · Employee ID · **Module** (shows "Agent" / "School" / "College") · Territory · Mobile · Status ("Active" / "Inactive" badge) |
| Empty | "No BDMs report to you yet." |
| Past end | "This page is past the end of your team." + **Go to the first page** |

- Read-only. There is no row link, no search box and no type filter on this page (the API's `q` and `bdm_type` are used only by pickers).
- Team membership is changed only by an admin: the BDM's `reporting_manager_user_id` (bdm-001), BDM deactivate/handover (`POST /admin/bdms/{id}/deactivate`, `/handover`, `api/api/bdm_lifecycle.py:35,60`), and manager deactivation, which moves the whole team to another active manager (`POST /admin/bdm-managers/{id}/deactivate`, `:79`). The receiving manager gets the notification "N BDMs now report to you" with "Their pending travel approvals are now yours to decide." (`api/services/bdm_lifecycle.py:163-165`).

## 3. Master view ("hierarchy"): `/bdm/manager/hierarchy`
- Frontend: `web/app/bdm/manager/hierarchy/page.tsx:15-44`, body in `web/components/BdmHierarchy.tsx`.
- API: `GET /bdm/manager/hierarchy[?manager_user_id=]` (`api/api/bdm_performance.py:123-131`) → `hierarchy()` (`api/services/bdm_performance.py:213-250`).
- This is **not an org chart**. It is type → BDMs → linked organizations → value chain, with live, all-time figures.

| UI element | Literal text |
|---|---|
| Eyebrow / H2 | "Master view" / "Your team" (super_admin: "All BDM teams" / "<name>'s team") |
| Sub | "Live figures, all time. Open a BDM to see their linked organizations." |
| Link | "Performance by period" |
| Per type card | "Agent BDM" / "School BDM" / "College BDM" — "N active BDMs · N linked organizations · N not onboarded yet" — the chain as "Students → Applications → …" with totals |
| Per BDM | the name (" (inactive)" when inactive) — "N linked organizations · N not onboarded yet"; empty: "No linked organizations yet."; table: Organization + chain columns + **Total** row |
| Empty type | "No Agent BDMs in this team." (same pattern per type) |
| Untracked | "Not tracked" badge |

Value chains (`CHAINS`, `api/services/bdm_performance.py:147-168`) [OVS]:
| Type | Steps (label: definition) |
|---|---|
| Agent | Students: Active students of the linked agency. · Applications: The agency's applications, except withdrawn ones. · Enrollment: Applications at the Enrolled stage. · Revenue: **Not tracked** (deposits pass through to universities and commission is not BDM revenue). |
| School | Students: Students of the linked school. · Profile Building: **Not tracked** (the School module has no profile completion figure). · Career/University: Students with a career guidance session completed. · Future Student: Students with an overseas application. |
| College | Students · Training · Internship (not tracked) · Placement · Revenue (out of scope) |

Rules: only non-archived organizations whose `bdm_type` matches the BDM's own type count. An Agent/School organization appears only once it is **linked** (`agent_org_id` / `school_id` set by onboarding); the others are counted as "not onboarded yet" (`:206-209`).

---

## 4. Organizations: `/bdm/manager/organizations` and `/[id]`
### 4.1 List
- Frontend: `organizations/page.tsx:11-35`, panel `web/components/BdmOrganizationsPanel.tsx:70-310` (`isBdm=false`).
- API: `GET /bdm/organizations?q&org_type&city&board&affiliation&territory&include_archived&limit&offset` (`api/api/bdm_organizations.py:55-94`). The manager's scope is the team's assigned organizations. Archived ones are hidden unless `include_archived=true`.

| UI element | Literal text |
|---|---|
| Eyebrow / H2 | "Organizations" / "Your team's organizations" |
| Card heading | "Organizations" (no "Add organization" for a manager) |
| Filters | "Name or code" · "City" · "Type" ("All types" + 7 types) · conditional "Board" ("All boards", CBSE, ICSE, "State board", IB, Other) / "Territory" / "University / affiliation" · checkbox "Show archived" · **Search** · **Clear filters** |
| Columns | Code · Name (link; "Archived" badge) · Type · City · Primary contact · Assigned BDM (" (inactive)") · Last meeting · Next meeting |
| Empty | "Your team has no organizations yet." / filtered: "No organizations match these filters." |
| States | "Loading organizations…", "Updating organizations…", "Unable to load organizations." + **Retry** |

### 4.2 Detail (read + reassign + restore)
- Frontend: `organizations/[id]/page.tsx:21-64`, `web/components/BdmOrganizationDetail.tsx:42-273` (basePath `/bdm/manager/organizations`).
- APIs read together: `GET /bdm/organizations/{id}` (`api/api/bdm_organizations.py:152`), `/organizations/{id}/activities` (`bdm_activities.py:126`), `/organizations/{id}/leads` (`bdm_leads.py:27`), `/organizations/{id}/stage-history` (`bdm_pipeline.py:77`), `/organizations/{id}/mou` (`bdm_mous.py:26`), `/bdm/tasks?organization_id=` (`bdm_tasks.py:25`), `/organizations/{id}/school-activity` (`bdm_school_activity.py:29`), `/organizations/{id}/agent-performance` (`bdm_metrics.py:35`), and `/organizations/{id}/business` (`bdm_metrics.py:27`, College only).
- Not found / out of team: "Organization not found" + "Back to organizations".

Sections, in order, as a manager sees them:
| Section | Manager view |
|---|---|
| Header | Eyebrow "<code> · <Type>", H2 name (+ "Archived"), "Back to organizations". Buttons: **Restore** ("Restoring…") only when archived. No Edit, no Archive, no "Add appointment". |
| Pipeline | Steps with their state text, plus "Agent status: <badge>" for Agent orgs and "Marked lost on <date>: <reason>" when lost. **No Move / Mark lost / Revive** (those need `can_edit`, `BdmOrganizationPipeline.tsx:22,127,153`). |
| MoU | Read-only card. Archived: "This organization is archived, so its MoU is read-only." Lost: "This organization is marked lost, so its MoU is read-only." (`BdmOrganizationDetail.tsx:35-38`). Writes need `can_edit` (`api/services/bdm_mous.py:172-173`). |
| Agent onboarding / School onboarding | Status sentence only; for a manager with no request yet: "Not requested yet." (`BdmOrganizationOnboarding.tsx:47-54`). |
| School activity (school orgs) / Agent performance (agent orgs) | Read-only panels. Revenue is visible to the manager (`api/services/bdm_metrics.py:70-72`). |
| Details | Type, City, State, Address, Contact person, Designation, Phone, Email, Website, Existing partner, (University Master for university orgs), Courses interested, Number of students, Last meeting, Next meeting, Assigned BDM, Created by + the type profile details |
| Contacts | Read-only (`can_edit` false). |
| Stage history, Activity, Follow-ups & tasks, Leads (N) | Read-only (`canLog` / `canAdd` only on the BDM path). |
| **Assignment** | "Assigned to <name>." · "Reassign to" picker (noun BDM) · **Reassign** · confirm "Reassign <code> to <name>?" with **Yes, reassign** ("Reassigning…") · success "Reassigned to <name>." · failure "Unable to reassign this organization." or the API message |

Server rules:
| Rule | Evidence |
|---|---|
| `can_reassign` / `can_restore`: role `bdm_manager` or super_admin, on an organization in scope. Reassign requires not archived; restore requires archived. | `api/services/bdm_organizations.py:109-118` |
| Refusals: 403 "Only the BDM's manager can reassign this organization" / "…can restore…"; 409 "Restore this organization first" / "Already active". | `:44-56` |
| Reassign target must be an **active `bdm` of the organization's type who reports to this manager** (any team for super_admin). Otherwise 422 "Choose an active BDM of this type from your team". Same BDM → 409 "Already assigned to this BDM". | `:204-222` |
| The picker searches `GET /bdm/manager/team?bdm_type=<org type>&q=` (limit 20) and leaves out the current assignee. **VERIFICATION REQUIRED**: whether the picker also hides inactive BDMs (the comment says active, but `/manager/team` returns inactive rows too). | `web/lib/bdmOrganizations.ts:71-80` |
| Reassign writes `BdmAssignmentHistory(reason="organization_reassigned")` and an audit row. It changes **only** `assigned_bdm_user_id`. Open appointments, tasks and leads keep their owner (**VERIFICATION REQUIRED**, product finding Q9). | `api/api/bdm_organizations.py:223-242` |
| Restore: "Organization restored." Archive is not available to the manager (403 "Only the assigned BDM can archive this organization"). | `BdmOrganizationDetail.tsx:91-101` |

## 5. Pipeline: `/bdm/manager/pipeline`
- Frontend: `pipeline/page.tsx:16-111`, board `web/components/BdmPipelineBoard.tsx:16-100`.
- APIs: `GET /bdm/manager/team?bdm_type=<t>&limit=1` per type (counts), then `limit=100` for the BDM filter; `GET /bdm/pipeline?bdm_type&assigned&stage&limit&offset` (`api/api/bdm_pipeline.py:84-98`, `api/services/bdm_pipeline.py:244-280`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "Pipeline" / "Team pipeline" / "Your BDMs' organizations per stage. Lost organizations are counted apart; archived ones are left out." |
| Filters | "Type" (only the types present in the team) · "BDM" ("Everyone" + up to 100 BDMs of that type) · **Show** |
| Bad BDM note | "That BDM isn't an Agent BDM in your team — showing everyone." ("a School") |
| Tiles | one per stage with a count link; live steps read "Awaiting handover", volume steps "Not tracked"; plus "Lost" |
| List | heading = the stage label or "All open organizations"; "Show all stages"; columns Code · Name · Type · City · Stage (+ "Lost") · Assigned BDM |
| Empty | "No BDMs report to you yet." / "No organizations at this stage." / invalid: "That filter isn't valid." + "Show the team pipeline" |

Stages (`api/bdm_stages.py:20-52`) [OVS]:
| Agent | School |
|---|---|
| Manual: Agent Prospect, Contacted, Meeting Scheduled, Meeting Completed, Interested, Proposal / Agreement, Agreement Signed | Manual: School Prospect, Contacted, Meeting, Presentation, Proposal, Negotiation, MoU, Signed |
| Live (onboarding handover): Agent Onboarding, Master Login Created, Staff Logins Created, Active Agent | Live: School Onboarding, Teachers / Parents / Students Created, Career Guidance, Psychometric, Student Profile Building, University Planning |
| Volume (not counted on tiles): Students, Applications, Enrollments | — |
Agent status (derived): Prospect, Contacted, Meeting, Interested, Agreement, Onboarding, Active, Inactive (`bdm_stages.py:74`). A manager names the type; omitting it is 422 "Choose a BDM type" (`bdm_pipeline.py:244`). Read-only.

## 6. Appointments: `/bdm/manager/appointments` and `/[id]`
- Frontend: `appointments/page.tsx:12-37`, panel `web/components/BdmAppointmentsPanel.tsx` (`isBdm=false`, `types=ALL_TYPES`); detail `appointments/[id]/page.tsx:12-44` + `BdmAppointmentDetail.tsx`.
- APIs: `GET /bdm/appointments?date_from&date_to&status&appointment_type&organization_id&bdm_user_id&outcome_pending&q&limit&offset` (`api/api/bdm_appointments.py:70-122`); `GET /bdm/appointments/{id}` (`:176`). Scope = team (`api/services/bdm_appointments.py:111-113`). Start date after end date → 422 "date_from must be on or before date_to".

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "Appointments" / "Your team's appointments" / "Read-only. Times are India time (IST)." |
| Filters | "Code or organization" · "From (IST)" (defaults to today) · "To (IST)" · "Status" ("All statuses", Scheduled, Confirmed, Rescheduled, Completed, Cancelled, No show, **Outcome pending**) · "Type" ("All types" + all 37) · "BDM" picker · **Search** · **Clear filters** |
| Chips | "Showing one organization" / "Showing one BDM" + **Show all** |
| Columns | Code · Date & time · Organization ("Archived") · Contact · Type · Status (+ "Outcome pending") · BDM |
| Empty | "Your team has no appointments in this period." / "No appointments match these filters." |
| Detail | Eyebrow "<code> · <type>", H2 org + status pill (+ "Archived", "Outcome pending"), "Back to appointments"; note "Outcome pending — the BDM hasn't filed the meeting report yet."; **Details** (Date & time, Organization, Contact person, Designation, Mobile, Email, Type, Location, Purpose, Remarks, Expected leads, Expected revenue, BDM, Trip); **Meeting report** (Outcome, Discussion, Requirements, Opportunity, Next action, Responsible person, Next follow-up, Filed); **History** ("Booked", "<from> → <to>") |
| Not found | "Appointment not found" + "Back to appointments" |

- Read-only: `permissions` are all false for a manager (`api/services/bdm_appointments.py:256-258`). There is no Edit or action button.
- Outcome lists [OVS]: Agent outcomes = Interested, Agreement Required, Product Training Required, Follow-up, Documents Required, Onboarding Required, Active Business Expected, Not Interested. School (common) outcomes = Interested, MoU Discussion Required, Student Leads Expected, Course Promotion Interested, Follow-up Required, Commercial Discussion, Not Interested, Reschedule, Other (`web/lib/bdmAppointments.ts:43-52`).

## 7. Calendar: `/bdm/manager/calendar`
- Frontend: `calendar/page.tsx:25-62`, `BdmCalendarPicker.tsx`, `BdmCalendar.tsx`.
- API: `GET /bdm/calendar?date_from&date_to&bdm_user_id` (`api/api/bdm_calendar.py:52-110`). A manager **must** name a BDM (422 "Choose a BDM"); a BDM not in the team → 404 "BDM not found"; at most 31 days ("The calendar shows at most 31 days"); at most 500 rows per source (`truncated`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "Calendar" / "Team calendar" or "<name>'s calendar" / "Read-only. Times are India time (IST)." |
| Picker | "BDM" searchable select (team) |
| No BDM | "Choose a BDM to see their calendar." |
| Not on team | "This BDM is not on your team." |
| Nav | range title · **Day** / **Week** (default Week) · "Previous week"/"Previous day" · **Today** · "Next week" |
| Items | badges "Today", "Trip" (Departs / Away / Return travel / Day trip; Draft/Submitted/In progress/Completed), "Seminar"/"Appointment", "Task"/"Follow-up", "Done", "Overdue" |
| Empty / errors | "Nothing planned this week." · "Some items are not shown." · "Unable to load the calendar." + **Try again** |
Contents: non-cancelled appointments, non-cancelled and non-rejected trips (so Draft and Submitted trips show), and non-cancelled tasks. The seminar types are seminar_workshop, seminar, workshop and student_seminar.

## 8. Follow-ups: `/bdm/manager/follow-ups`
- Frontend: `follow-ups/page.tsx:11-36`, `BdmTasksPanel.tsx` (`isBdm=false`), `BdmTaskItem.tsx`.
- API: `GET /bdm/tasks?bucket&kind&org_type&organization_id&bdm_user_id&limit&offset` (`api/api/bdm_tasks.py:25-47`); team scope (`api/services/bdm_tasks.py:42-44`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "Follow-ups" / "Your team's follow-ups and tasks" / "Read-only. Dates are India time (IST)." |
| Card | "Follow-ups and tasks" |
| Tabs | Today · Overdue · Upcoming · Done · Cancelled (each "(n)") |
| Chips | one per org type with a count, e.g. "Agent 3", "School 1", "No organization 2" |
| Filters | "Kind" (All / Follow-ups / Tasks) · "BDM" picker · **Clear filters**; "Showing one BDM: <name>" + **Show all** |
| Empty | "Nothing due today." / "No overdue follow-ups." / "Nothing upcoming." / "Nothing done yet." / "Nothing cancelled."; filtered: "No items match these filters." |
| Row | assignee shown (`showAssignee`), "Archived", "Added by hand"; **no Done / Edit / Cancel task** buttons (only the assigned BDM writes, `bdm_tasks.py:71-75`) |

## 9. Activities: `/bdm/manager/activities`
- Frontend: `activities/page.tsx:14-80`, `BdmActivityDay.tsx` (`canLog=false`), `BdmActivityCounts.tsx`.
- APIs: `GET /bdm/manager/team?limit=100`; `GET /bdm/manager/activities?date&bdm_user_id&channel&limit=50&offset` (`api/api/bdm_activities.py:135-145`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "Activities" / "Team activities" / "What your BDMs logged on the chosen day, with that day's counts." |
| Filters | "Day" (max today) · "BDM" ("Everyone" + team) · **Show** |
| Notes | "That BDM isn't in your team — showing everyone." + the date notes (§0.5) |
| Counts | per channel (Call, WhatsApp, Email, Visit, Meeting, Other) + "Calls made" + "Organizations contacted" |
| List | entries; **Load more** ("Loading…") |
| Empty | "No activities on this day." / "No activities from <name> on this day." |
Read-only (Q-17: managers do not log). Direction labels: Outgoing / Incoming.

## 10. Daily reports: `/bdm/manager/daily-reports` and `/[bdmId]`
- Frontend: `daily-reports/page.tsx:16-94`; detail `daily-reports/[bdmId]/page.tsx:17-47` + `BdmDailyReport.tsx` (`mode="manager"`).
- APIs: `GET /bdm/manager/daily-reports?date&limit&offset` (`api/api/bdm_daily_reports.py:68-102`); `GET /bdm/manager/daily-reports/{bdm_user_id}/{date}` (`:105`); `PUT …/{bdm_user_id}/{date}/comment` (`:115-130`).

| UI element | Literal text |
|---|---|
| Grid eyebrow / H2 / sub | "Daily reports" / "Team daily reports" / "Who submitted the end-of-day report in the seven days up to the chosen date. Open a report to read it or comment." |
| Filter | "Up to" (date, max today) · **Show** |
| Grid | rows = active team BDMs ("<name>" + "Agent BDM"); columns = 7 days, **newest first**; cells "✓ Submitted" (tooltip "Submitted <time>"), "Missing", "—" (before the BDM's profile existed) |
| Empty | "No active BDMs report to you yet." |
| Pager | "BDMs a–b of N" |
| Detail H2 | "<name> — <date>", sub "<Type> BDM", button **Back to team reports** |
| Detail body | "Submitted <time>. These counts were saved when the report was submitted." or "Not submitted yet. These counts are a live preview."; KPI tiles (value or "Not tracked"); "End-of-day note" ("No note."); "Manager's comment" (text, "<name>, <time>") |
| Comment form (submitted only) | "Your comment" · **Save comment** ("Saving…") · "Write a comment first." · "Comment saved." |

Rules: one comment per submitted report; a later save **replaces** it (R7, D22). The comment is 1–1000 characters (`api/schemas.py:6318`). Not submitted → 409 "This report hasn't been submitted yet". A BDM outside the team → 404 "BDM not found". The code sends **no notification** to the BDM on a comment (no `_notify_user` in `bdm_daily_reports.py`). A BDM submits up to 7 days back (`BACKDATE_DAYS`).

Daily KPI rows per type (`DAILY_REPORTS`, `api/services/bdm_metrics.py:294-314`) [OVS]:
| Agent | School |
|---|---|
| Calls made · Agents contacted · Meetings · New prospects · New agents (**Not tracked**) · Agreements · Agent training · Follow-ups · Student leads generated · Applications generated (**Not tracked**) · Enrollments generated (**Not tracked**) | Schools contacted · Calls · Meetings · School visits · Presentations · Proposals · MoUs · Follow-ups · Students generated · Career guidance sessions · Psychometric sessions |

## 11. MoUs: `/bdm/manager/mous`
- Frontend: `mous/page.tsx:14-48`, `BdmMousPanel.tsx`.
- API: `GET /bdm/mous?status&bdm_type&organization&current&limit&offset` (`api/api/bdm_mous.py:141-154`), scoped like organizations. Also `GET /bdm/mous/{id}/history` (`:157`) and `GET /bdm/mous/{id}/document` (`:163`, audited download, file name `mou-<org code>.<ext>`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "MoUs" / "Team MoUs" / "Your BDMs' current MoUs. A Signed or Active MoU past its valid-until date reads Expired." |
| Status filter | All · Prospect · Discussion Started · Proposal Sent · Under Negotiation · Draft Shared · Signed · Active · Expired · Rejected |
| Table | "<status> MoUs" — Organization (link) · Code · Status · Signed on · Valid until · Reference · Document ("Yes"/"—") · Assigned BDM |
| Empty | "No MoUs yet." / "No MoUs at <status>." / invalid: "That filter isn't valid." + "Show all MoUs" |
- **There is no MoU approval step.** MoUs are read-only for a manager: writes need `can_edit` (the assigned BDM). Expired is derived from `valid_until`, never chosen. For Agent orgs the daily KPI calls a signed MoU an "Agreement".

## 12. Meeting requests: `/bdm/manager/meeting-requests`
- Frontend: `meeting-requests/page.tsx:10-40`, `MeetingRequestList.tsx` (`viewer="manager"`).
- API: `GET /bdm/meeting-requests?status&limit=25&offset` (`api/api/bdm_meeting_requests.py:68-74`). Scope = requests named for the team's BDMs **plus every unassigned (pool) request of any type** (`api/services/bdm_meeting_requests.py:94-96`). Accept and decline are BDM-only (`bdm_context`, `:84-88`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "Requests" / "Meeting requests" / "Read-only: requests for your team's BDMs and the open requests any BDM of the module can take. Times are India time (IST)." |
| Filter | All · Pending · Accepted · Declined |
| Columns | Request (code, not a link) · Proposed (IST) (+ mode) · Organization (+ person) · Type · Status (+ appointment code and time, "Reason: …") · Requested by (+ "For <BDM>" or "Any Agent BDM") |
| Empty | "No meeting requests yet." / "No pending requests." |
Request types: college, agent, school, corporate (corporate → College BDM) (`api/models.py:3319-3320`). The list is ordered pending first, soonest proposed first, then by latest decision.

## 13. Approvals (travel): `/bdm/manager/approvals`
- Frontend: `approvals/page.tsx:16-48`, `TripTable.tsx`.
- API: `GET /bdm/manager/approvals?limit&offset` (`api/api/bdm_travel.py:101-104`) → `approvals_filter` (`api/services/bdm_travel.py:324-330`): Submitted + Planned trips of BDMs whose **current** reporting manager is the caller. Oldest submitted first.

| UI element | Literal text |
|---|---|
| Eyebrow / H2 / sub | "Approvals" / "Travel waiting for your approval" / "Every trip needs your approval before it starts. A rejection needs a reason, which the BDM sees." |
| Columns | Trip · Status · BDM · Dates · Route · Estimated · Actual · Mode |
| Empty | "Nothing waiting for approval." / past end: "This page is past the end of the queue." + "Go to the first page" |
| Error | "Travel is not available right now" — "We could not load this page. Your trips are safe; please try again." + **Retry** |
- **Travel is the only approval type in the manager portal.** There is no MoU, expense, onboarding or target approval. (Onboarding requests go to Overseas Admin, `api/api/bdm_onboarding.py:45`.)

## 14. Trip: `/bdm/manager/trips/[id]` and `/report`
- Frontend: `trips/[id]/page.tsx:15-35` + `TripWorkspace.tsx` (`view="manager"`), `TripDecision.tsx`, `TripDetails.tsx`, `TripItinerary.tsx`, `TripProductivity.tsx`, `TripExpenses.tsx`; report `trips/[id]/report/page.tsx:12-39` + `TripReport.tsx`.
- APIs: `GET /bdm/manager/trips/{id}` (`api/api/bdm_travel.py:107`), `POST …/approve` (`:140`), `POST …/reject` body `{reason}` (`:145`), `GET …/report` (`:125`). There is also a team trip list, `GET /bdm/manager/trips?bdm_user_id&approval_status&travel_status` (`:90`), **with no manager page using it** (**VERIFICATION REQUIRED**).

| UI element | Literal text |
|---|---|
| Header | Eyebrow "Travel · <code> · <BDM>", H2 "<from> → <to>", status badges; **View travel report** (completed only); **Back to approvals** |
| Decision (when `can_decide`) | **Approve** ("Saving…") → "Trip approved; the BDM has been told." · **Reject** → "Reason for rejecting" textarea, "Reason is required", **Confirm reject** / **Cancel** (Esc) → "Trip not approved; the BDM has been told why." |
| After rejection | "Reason given: <text>" |
| Sections | "Trip details" (Travel ID, Travel date, Return date, From, To, Mode of travel, Accommodation required, Purpose, Approval status, Travel status, Approved by / Rejected by, Completed, Cancelled) · "Appointments" · "Productivity" (Meetings planned, Meetings completed, Estimated cost, Actual cost, Cost per completed meeting, Expected leads, Expected revenue, Actual leads, Actual revenue) · "Costs and expenses" (read-only) · "Remarks" (only if present) |
| Report | Eyebrow "Travel report · <code> · <BDM>"; **Back to the trip**; Trip details, Appointments, Productivity, "Expenses by category" (Category, Amount, **Total**; "No expenses were recorded."), Remarks ("No remarks were added."). Before completion: "The travel report is available once the trip is completed" (409) |

State machine (`api/services/bdm_travel.py:37-60,194-210,300-321`):
| Field | Values (labels) |
|---|---|
| approval_status | draft (Draft) → submitted (Submitted) → approved (Approved) / rejected (Rejected); withdraw returns submitted → draft; a rejected trip is editable and can be resubmitted |
| travel_status | planned (Planned) → in_progress (In progress) → completed (Completed); cancelled (Cancelled) from planned or in progress |
| Decide allowed | approval Submitted **and** travel Planned only |
| Who decides | the BDM's **current** reporting manager; a super_admin only while that manager is inactive (`decider_may`, `:112-116`); never one's own trip (403 "You can't decide your own trip") |
| Refusals | another manager → 404 "Trip not found"; super_admin while the manager is active → 403 "The reporting manager is active and decides this trip" (page note: "This BDM's reporting manager is active and decides this trip. A Super Administrator can decide only while that manager is inactive.") |
| Reject reason | required, multi-line, ≤1000 characters (`api/schemas.py:3680,3719-3721`) |
| Notifications | on submit: the manager gets "Travel approval needed", "<code>: <from> → <to>, <dd Mon yyyy>", which links to `/bdm/manager/approvals` (all active super_admins when the manager is inactive); on decision: the BDM gets "Trip approved" / "Trip not approved", in-app only (`channels=[]`) (`api/api/bdm_travel.py:68-75,128-136`) |
| Limits | travel date ≤30 days in the past; a trip lasts ≤31 days; ≤100 expense lines; expenses only once approved (owner only) |

## 15. Notifications: `/bdm/manager/notifications`
- Frontend: `notifications/page.tsx:10-41`, `SchoolNotificationList.tsx` (`readBeforeOpen`).
- APIs: `GET /workflows/notifications` (newest 100, `api/api/workflows.py:2810`), `PATCH /workflows/notifications/{id}/read` (`:2823`), unread count (`:2816`).

| UI element | Literal text |
|---|---|
| Eyebrow / H2 | "Notifications" / "Your notifications" |
| Row | title (+ "new" badge), body, time, **Open** (marks it read, then follows the link) |
| Empty | "No notifications yet. You will be told here when one of your BDMs submits a trip for approval." |
Known manager notices: "Travel approval needed" (→ Approvals) and "N BDM(s) now report(s) to you" (→ Team, `api/services/bdm_lifecycle.py:163-165`; uses default channels, so **VERIFICATION REQUIRED** whether an email is also sent). The page is for `bdm_manager` only; a super_admin is told "BDM manager role required".

## 16. Performance: `/bdm/manager/performance`, `/[type]`, `/bdms/[id]`
- Frontend: `performance/page.tsx:17-50` + `BdmPerformanceTable.tsx`; `performance/[type]/page.tsx:20-64` + `BdmPerformanceFigures.tsx`; `performance/bdms/[id]/page.tsx:23-92`; filters in `BdmPerformanceControls.tsx`.
- APIs: `GET /bdm/manager/performance?from&to[&type][&manager_user_id]` (`api/api/bdm_performance.py:59-89`); `GET /bdm/manager/performance/bdms/{id}?from&to` (`:92-120`).

| UI element | Literal text |
|---|---|
| Overview eyebrow / H2 / sub | "Performance" / "Your team" / "<from> – <to>, India time (IST)."; link "Master view" |
| Filters | "From", "To" (required dates) · (super_admin "Team") · **Show** · **This month** |
| Table | "Performance by BDM type"; columns KPI · Agent BDM · School BDM · College BDM; each tracked value links to the type page; untracked = "Not tracked"; "No active BDMs in this team yet." when P-01 is all 0 |
| Footnote | "How each figure is counted" with each row's definition (per type when they differ) |
| Type page | breadcrumb "Performance › Agent BDM"; H2 "Agent BDMs"; card "BDMs" — columns BDM · Meetings · Travel Trips · New Organizations · MoUs · Leads · Students · Revenue; **Total** row; "Inactive" note; empty "No Agent BDMs in this team." |
| BDM page | breadcrumb "Performance › Agent BDM › <name>"; H2 name (+ "Inactive"); sub "<Type> · <period>, India time (IST)."; card "Organizations" ("These figures count the period only. Each organization's page lists all its appointments, outcomes and leads, and its student and revenue panels show all-time figures."; empty "No organization has a figure in this period."); card "Travel trips: N" (rows "<code> · <from> → <to> · <date> · <approval>, <travel>"; empty "No trips in this period.") |
| Errors | "Unable to load the performance figures." / "Choose valid dates for the period." / API 422/404 text + **Try again** / **Show this month** |

KPI rows (`ROWS`, `api/api/bdm_performance.py:31-50`):
| Key | Label | Definition |
|---|---|---|
| P-01 | BDMs | Active BDMs of this type in the team (today). |
| P-02 | Meetings | Appointments completed in the period by these BDMs. |
| P-03 | Travel Trips | Trips travelling in the period, except cancelled or rejected ones. |
| P-04 | New Organizations | Organizations these BDMs created in the period. |
| P-05 | MoUs | MoUs these BDMs moved to Signed in the period. |
| P-06 | Leads | Student leads these BDMs entered in the period. |
| P-07 | Students | Agent: Active students added in the period in the agencies linked to these BDMs' organizations. School: Students added in the period in the schools linked to these BDMs' organizations. |
| P-08 | Revenue | Agent and School: **Not tracked** ("no revenue is recorded for this BDM type (deposits and commissions are not BDM revenue)"). College only: paid INR fees. |

Period rules: inclusive IST dates; the default is the current IST month; start after end → 422 "The period must start on or before its end"; at most 366 days → 422 "The period can be at most 366 days" (`api/services/bdm_performance.py:40-57`). Inactive BDMs are listed (their records still count, P4). A BDM outside the team → 404 "BDM not found".

## 17. Targets: `/bdm/manager/targets` and `/[bdmId]`
- Frontend: `targets/page.tsx:12-82` + `BdmTargetsCopy.tsx`; `targets/[bdmId]/page.tsx:15-44` + `BdmTargetsEditor.tsx` → `TargetsEditor.tsx`.
- APIs: `GET /bdm/manager/targets?month&limit&offset` (`api/api/bdm_targets.py:39-52`); `GET /bdm/manager/targets/{bdm_user_id}?month` (`:55-65`); `PUT /bdm/manager/targets` `{month, items:[{bdm_user_id,kpi_key,target|null}]}` (`:68-78`); `POST /bdm/manager/targets/copy` `{month}` (`:81-91`).

| UI element | Literal text |
|---|---|
| Team H2 / sub | "Team targets — <Month YYYY>" / "Set each BDM's monthly target per KPI. Achieved is counted from what the BDM recorded that month." |
| Filter | "Month" (12 months back to 12 ahead) · **Show**; bad value: "That isn't a valid month — showing this month." |
| Read-only notes | "Past months are read-only." / "Targets can be set up to 12 months ahead." |
| Copy | **Copy last month's targets** → "Copy your team's targets from <prev> into <month>? Targets already set for <month> are kept." **Yes, copy** → "Copied N targets." / "Nothing to copy: every target from <prev> is already set or there were none." |
| Team table | BDM ("<Type> BDM") · Targets set ("x of y") · **Set targets** / **View** |
| Empty | "No active BDMs report to you yet." |
| BDM H2 / sub | "<name> — <Month YYYY>" / "<Type> BDM · All team targets"; "These targets can't be changed." when not editable |
| Editor | columns KPI (+ definition) · Target (number, placeholder "Not set") · Achieved ("Not tracked" / "Month not started") · Achievement (%); **Save targets** ("Saving…"); "Leave a target blank to clear it."; "Saved N targets." / "No target changed."; "<KPI> target must be a whole number from 0 to <max>." |

Rules (`api/services/bdm_targets.py:23-27,48-70,73-161`): a whole number from 0 to 100000, or null (which clears the target). Editable for the current month and up to 12 months ahead; a past month only by super_admin (422 "Past months' targets can only be changed by a super admin"); more than 12 months ahead → "Targets can be set up to 12 months ahead"; an inactive BDM → 422 "This BDM is inactive, so their targets can't be changed"; a KPI outside the type → 422 "<KPI> is not a target KPI for Agent BDMs". Saves are all-or-nothing and audited. When two managers save at once, the last write wins. Achievement % = round(achieved × 100 ÷ target), with no value when the target is 0 or unset.

Monthly KPI catalogue (`TARGET_KPIS` = own + common, de-duplicated; `api/services/bdm_metrics.py:438-447`) [OVS]:
| Agent (13) | School (15) |
|---|---|
| New Agent Leads · Agent Meetings · New Agents (**Not tracked**) · Agreements Signed · Active Agents (**Not tracked**) · Agent Students (**Not tracked**) · Applications (**Not tracked**) · Enrollments (**Not tracked**) · College Meetings · New Colleges · Appointments · MoUs · Student Leads | Schools Contacted · School Meetings · Presentations · Proposals · MoUs · Active Schools · Students Onboarded · Career Guidance · Psychometric Tests · College Meetings · Agent Meetings · New Colleges · New Agents (**Not tracked**) · Appointments · Student Leads |

---

## (a) Proposed feature rows
| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| DOC-BDM-MDASH-001 | Sign in and land on the dashboard | `/admin/login` → `/bdm/manager/dashboard` | bdm_manager | `POST /auth/login`, `GET /auth/me` |
| DOC-BDM-MDASH-002 | Read the BDM overview tiles | `/bdm/manager/dashboard` | bdm_manager | `GET /bdm/manager/dashboard`, `GET /bdm/manager/team` |
| DOC-BDM-MDASH-003 | Act on dashboard alerts (AL-1…AL-7) | `/bdm/manager/dashboard` | bdm_manager | `GET /bdm/manager/dashboard` |
| DOC-BDM-MDASH-004 | Sidebar, unread badge, sign out | all manager pages | bdm_manager | `GET /workflows/notifications/unread-count` |
| DOC-BDM-MTEAM-001 | View the BDMs who report to you | `/bdm/manager/team` | bdm_manager | `GET /bdm/manager/team` |
| DOC-BDM-MTEAM-002 | Read the Master view (type → BDM → linked orgs) | `/bdm/manager/hierarchy` | bdm_manager | `GET /bdm/manager/hierarchy` |
| DOC-BDM-MORG-001 | Find the team's organizations | `/bdm/manager/organizations` | bdm_manager | `GET /bdm/organizations` |
| DOC-BDM-MORG-002 | Read an organization's profile and panels | `/bdm/manager/organizations/[id]` | bdm_manager | `GET /bdm/organizations/{id}` + activities/leads/stage-history/mou/tasks/school-activity/agent-performance |
| DOC-BDM-MORG-003 | Reassign an organization to another team BDM | `/bdm/manager/organizations/[id]` | bdm_manager | `POST /bdm/organizations/{id}/assign`, `GET /bdm/manager/team?bdm_type&q` |
| DOC-BDM-MORG-004 | Restore an archived organization | `/bdm/manager/organizations?archived=1` → `[id]` | bdm_manager | `POST /bdm/organizations/{id}/restore` |
| DOC-BDM-MPIPE-001 | Read the team pipeline by type and stage | `/bdm/manager/pipeline` | bdm_manager | `GET /bdm/pipeline`, `GET /bdm/manager/team?bdm_type` |
| DOC-BDM-MAPPT-001 | Filter the team's appointments | `/bdm/manager/appointments` | bdm_manager | `GET /bdm/appointments` |
| DOC-BDM-MAPPT-002 | Read an appointment and its meeting report | `/bdm/manager/appointments/[id]` | bdm_manager | `GET /bdm/appointments/{id}` |
| DOC-BDM-MCAL-001 | View a BDM's calendar (day/week) | `/bdm/manager/calendar` | bdm_manager | `GET /bdm/calendar?bdm_user_id` |
| DOC-BDM-MFUP-001 | Review the team's follow-ups and tasks | `/bdm/manager/follow-ups` | bdm_manager | `GET /bdm/tasks` |
| DOC-BDM-MACT-001 | Review the team's activities for a day | `/bdm/manager/activities` | bdm_manager | `GET /bdm/manager/activities` |
| DOC-BDM-MRPT-001 | Check daily report submission (7-day grid) | `/bdm/manager/daily-reports` | bdm_manager | `GET /bdm/manager/daily-reports` |
| DOC-BDM-MRPT-002 | Read a daily report and comment | `/bdm/manager/daily-reports/[bdmId]` | bdm_manager | `GET …/{bdm}/{date}`, `PUT …/{bdm}/{date}/comment` |
| DOC-BDM-MMOU-001 | Review the team's MoUs by status | `/bdm/manager/mous` | bdm_manager | `GET /bdm/mous` |
| DOC-BDM-MMEET-001 | Review meeting requests (team + pool) | `/bdm/manager/meeting-requests` | bdm_manager | `GET /bdm/meeting-requests` |
| DOC-BDM-APPR-001 | Work the travel approval queue | `/bdm/manager/approvals` | bdm_manager | `GET /bdm/manager/approvals` |
| DOC-BDM-MTRIP-001 | Approve or reject a trip | `/bdm/manager/trips/[id]` | bdm_manager | `GET /bdm/manager/trips/{id}`, `POST …/approve`, `POST …/reject` |
| DOC-BDM-MTRIP-002 | Read a completed trip's travel report | `/bdm/manager/trips/[id]/report` | bdm_manager | `GET /bdm/manager/trips/{id}/report` |
| DOC-BDM-MNOTIF-001 | Read and open notifications | `/bdm/manager/notifications` | bdm_manager | `GET /workflows/notifications`, `PATCH …/{id}/read` |
| DOC-BDM-PERF-001 | Read performance by BDM type for a period | `/bdm/manager/performance` | bdm_manager | `GET /bdm/manager/performance` |
| DOC-BDM-PERF-002 | Drill into one BDM type | `/bdm/manager/performance/[type]` | bdm_manager | `GET /bdm/manager/performance?type=` |
| DOC-BDM-PERF-003 | Drill into one BDM (orgs + trips) | `/bdm/manager/performance/bdms/[id]` | bdm_manager | `GET /bdm/manager/performance/bdms/{id}` |
| DOC-BDM-TGT-001 | Review team targets for a month and copy last month | `/bdm/manager/targets` | bdm_manager | `GET /bdm/manager/targets`, `POST /bdm/manager/targets/copy` |
| DOC-BDM-TGT-002 | Set one BDM's monthly targets | `/bdm/manager/targets/[bdmId]` | bdm_manager | `GET /bdm/manager/targets/{id}`, `PUT /bdm/manager/targets` |

## (b) Test data needed before screenshots
| # | Data | Why |
|---|---|---|
| 1 | An **Overseas-only manager** (only Agent + School reports), or a decision to screenshot the demo "Sanjay BDM Manager", who also manages College BDM "Vivek" | Avoid College rows and columns in the Overseas manual; Performance and Master view still show a College column/section regardless |
| 2 | At least 2 active Agent BDMs + 1 School BDM + 1 inactive BDM in the team | Team status column, reassign picker (needs a second BDM of the same type), the "Inactive" note in performance, active-only grids |
| 3 | Agent and School organizations across several manual stages, 1 Lost, 1 archived, 1 linked through onboarding (agent_org_id / school_id), 1 not linked | Pipeline tiles, Lost bucket, Restore, Master view "linked" vs "not onboarded yet" |
| 4 | Appointments: one starting within 24 h (Scheduled), one past start with no report (Outcome pending), one completed today with a meeting report, one cancelled | AL-1, AL-5, AL-6, detail, Meeting report |
| 5 | Trips: Submitted + Planned (pending), Approved covering today, Rejected with a reason, Completed with expenses and remarks | Approvals queue, Approve/Reject, T-M04, travel report |
| 6 | Follow-ups: one overdue, one due today, one done; one task with no organization | AL-3, tabs, "No organization" chip |
| 7 | MoUs: one at Proposal Sent ≥5 days ago, one Signed this month, one Active past valid_until (reads Expired), one with an uploaded document | AL-4, T-M07/T-M08, Expired derivation |
| 8 | Activities on a chosen day for 2 BDMs (call, visit, WhatsApp) | Team activities counts |
| 9 | Daily reports: submitted for some days, missing yesterday for one active BDM, one with a manager comment; a BDM created mid-week (shows "—") | Grid states, AL-7, comment form |
| 10 | Targets set last month for 1 BDM, none this month | Copy last month's targets, "x of y", Achievement % |
| 11 | Meeting requests: one named for a team BDM (pending), one accepted, one declined with a reason, one pool request (Agent) | Requests list, "For …" / "Any Agent BDM" |
| 12 | Unread notifications "Travel approval needed" | Badge, Notifications page, Open |
| 13 | Agent organization linked to an agency with students/applications | Agent performance panel and Master view chain non-zero |

## (c) Open questions and product findings
| # | Finding | Evidence | Status |
|---|---|---|---|
| Q1 | Performance (§5) and Master view always show **College BDM** columns/sections, even for an Overseas-only team. Pipeline, by contrast, hides absent types. Is this intended? | `bdm_performance.py:64-90`; `services/bdm_performance.py:226-250`; `pipeline/page.tsx:26-27` | VERIFICATION REQUIRED |
| Q2 | The Meeting requests page shows the **whole open pool of every type** (College and Corporate included), not just the manager's team or type. MR3 says this is by design. Confirm for an Overseas manager. | `services/bdm_meeting_requests.py:94-96` | VERIFICATION REQUIRED |
| Q3 | The Appointments Type filter lists all 37 types, College ones included; the Organizations Type filter lists all 7 org types. | `appointments/page.tsx:32`; `bdmOrganizations.ts:19` | Product finding |
| Q4 | Agent target KPIs include "College Meetings" and "New Colleges"; School KPIs include "College Meetings", "Agent Meetings", "New Colleges" and "New Agents" (the common list). Intended? | `bdm_metrics.py:438-447` | VERIFICATION REQUIRED |
| Q5 | Many Agent KPIs are **Not tracked** (New Agents, Active Agents, Agent Students, Applications, Enrollments; the daily rows "New agents", "Applications generated", "Enrollments generated"), yet the Master view's Agent chain **does** count Applications and Enrollment from the linked agency. The figures are inconsistent across pages. | `bdm_metrics.py:282-285,400-418`; `services/bdm_performance.py:148-152` | Product finding |
| Q6 | **No MoU approval** and no approval other than travel exist. The brief mentioned "MoU approvals"; the manual must not promise them. | §11, §13 | Confirmed from code |
| Q7 | A manager can **restore** but not **archive** an organization. | `services/bdm_organizations.py:109-113` | Confirmed; document it |
| Q8 | Team = direct reports only; no multi-level hierarchy. "Master view" is a type/value-chain view, not an org chart. | `services/bdm.py:153-155` | Confirmed |
| Q9 | Reassigning an organization changes only `assigned_bdm_user_id`. The old BDM's open appointments, follow-ups and leads on that organization are not moved; the new BDM may be unable to act on them. | `api/bdm_organizations.py:223-242` | VERIFICATION REQUIRED |
| Q10 | Does the reassign picker exclude **inactive** BDMs? (`/manager/team` returns inactive rows; the server would refuse them with 422.) | `bdmOrganizations.ts:71-80`; `services/bdm_organizations.py:212-221` | VERIFICATION REQUIRED |
| Q11 | The dashboard's team summary counts active/inactive from the **first 50** rows only ("… on the first page"). | `dashboard/page.tsx:17-23` | Minor |
| Q12 | The Team and Approvals pages show the role pill "BDM Manager" to a super_admin; the Notifications page denies a super_admin. | `team/page.tsx:26`; `approvals/page.tsx:29`; `notifications/page.tsx:18` | Minor |
| Q13 | No notification goes to the BDM when the manager comments on a daily report, and none when targets are set. | `api/bdm_daily_reports.py:115-130`; `api/bdm_targets.py` | Product finding |
| Q14 | No export, CSV or print exists for performance, daily reports, targets or the travel report. | §0.5 | Confirmed from code |
| Q15 | `GET /bdm/manager/trips` (team trip history with filters) exists, but no manager page lists all team trips: only the pending queue, dashboard alerts, the calendar and the performance BDM page. | `api/bdm_travel.py:90-98` | VERIFICATION REQUIRED |
| Q16 | AL-7 checks **yesterday** only; the alert does not count today's report. | `api/bdm_manager_dashboard.py:126,151-153` | Document |
| Q17 | The manager notice "N BDMs now report to you" uses default channels, so it may also send an email. | `services/bdm_lifecycle.py:163-165` | VERIFICATION REQUIRED |
| Q18 | The sidebar ends with "Management tasks" (`/account/management-tasks`). That page is shared with other portals, outside the BDM CRM; decide whether the manual covers it or links out. | `navigation.ts:11,95` | Scope question |
