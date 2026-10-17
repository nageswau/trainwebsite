# EduSphere Overseas BDM CRM — Documentation Analysis (Phase 1)

> Master planning session S1, 2026-10-17. Code baseline `main` @ `6fee294d`. Branch `docs/bdm-crm-user-guide` (worktree
> `.claude/worktrees/bdm-docs`). Read-only source discovery; **nothing here is browser-verified yet**. Where this file and the
> browser disagree, the browser wins and this file is annotated.
>
> Field-level evidence (file:line, literal UI strings, error messages) is in the four appendices:
> - `discovery/01-bdm-frontline.md` — Agent BDM and School BDM portal (`/bdm/*`)
> - `discovery/02-bdm-manager.md` — BDM Manager portal (`/bdm/manager/*`)
> - `discovery/03-access-admin-touchpoints.md` — account access, admin provisioning and lifecycle, travel approvals, touchpoints
> - `discovery/04-test-data-tooling-decisions.md` — seed data, e2e flows, bdm-001..025 decisions, glossary, capture tooling

**Owner answers (2026-10-17):**

| # | Question | Answer |
|---|---|---|
| D1 | Approach | Full verified set, same pipeline as the Telecaller and School CRM docs. |
| D2 | Scope | Agent BDM + School BDM (`bdm`, Overseas) + `bdm_manager` over Overseas BDMs + Super Admin / Overseas Admin BDM screens (`/overseas/admin/bdms`, `/admin/bdms`, `/admin/bdm-travel-approvals`) + telecaller meeting-request touchpoint. **College BDMs (IT) are out of scope.** |
| D3 | Stack | Claude may start, seed, reset and snapshot only the `bdmdocs` compose project (web 3040, api 8040, Mailpit 127.0.0.1:8028). |
| D4 | Personas | Overseas-only **Docs** personas created through the admin screens + a `demo-accounts.md` page mapping them to Sanjay / Rahul / Kavya. |
| D5 | Time-bound states | Spread capture over real days: overdue follow-ups, missed daily report (AL-7) and the MoU 5-day alert are captured in later sessions run on later days; PARTIAL until then. |
| D6 | Onboarding links | Link the Docs Agent organisation to the seeded **EduSphere Partner Agency** and the Docs School organisation to the seeded **Sunrise Public School**, so the performance/activity panels show real figures. |

---

## 1. Application Overview

### 1.1 What the BDM CRM is
The BDM CRM (backlog bdm-001..025, all merged; bdm-021 is College-only) is the field-sales desk for partner institutions. An
**Agent BDM** recruits education agencies; a **School BDM** recruits schools. Each BDM works organisations through a
module-specific pipeline, books and reports on meetings, plans travel (approved by their manager), records follow-ups and
activities, submits a daily report, manages MoUs, and requests onboarding once a deal is signed — at which point an Overseas
Admin links the organisation to a real agency (Agent CRM) or partner school (School CRM). Telecallers can send **meeting
requests** to BDMs (tel-019).

Roles in scope:
- **Agent BDM / School BDM** (`bdm`, `bdm_type` agent / school, division overseas). Sign in at `/overseas/login`; land on `/bdm/my-day`.
- **BDM Manager** (`bdm_manager`, division global). Signs in at `/admin/login`; lands on `/bdm/manager/dashboard`. Team = direct reports only.
- **Overseas Admin** (create/edit/deactivate Agent and School BDMs; onboarding links; admin lead list) and **Super Admin** (all of that + BDM Managers + fallback travel approvals).

### 1.2 Agent BDM vs School BDM (appendix 01 §0.1)
Same sidebar and same travel flow. They differ in pipeline stages, onboarding trigger (Agent: stage **Agreement Signed**;
School: MoU **Signed/Active**), organisation panel (Agent performance vs School activity), appointment types, meeting-report
outcomes (Agents have no Reschedule outcome), My Day tiles, daily-report tiles and target KPIs. Every feature file that differs
by type carries a **What each BDM type sees** table.

### 1.3 Authentication (appendix 03 §1)
- Signed-out `/bdm/*` → `/bdm/sign-in?next=` chooser (**College BDM** → `/it/login`; **Agent / School BDM** → `/overseas/login`); `/bdm/manager/*` → `/admin/login?next=`.
- Wrong portal: 403 naming the right portal. Welcome link 72 h, single use; BDM → `/overseas/reset-password`, manager → `/admin/reset-password`.
- Every BDM page calls `GET /bdm/me`; a non-BDM gets "BDM role required".

### 1.4 Cross-cutting rules to explain in every manual
- **Module scope:** a BDM reads every organisation in their module but edits only those assigned to them; only a manager restores an archived organisation; a manager cannot archive.
- **Travel approval:** only the BDM's current manager decides; Super Admin decides only while that manager is inactive; rejection needs a reason. Travel is the **only** approval type — there is no MoU approval.
- **Time rules:** booking needs a future time; Complete / No-show only after start; meeting reports and activities editable only the same day; a submitted daily report locks that day's activities.
- **Not built — never document:** expense receipt upload, appointment mode field, external calendar sync, agent commission on BDM screens ("Not shown to BDMs (awaiting a decision)"), unlinking an onboarded partner, Agent/School revenue, any CSV export (appendix 04 §3).

---

## 2. Module Inventory

| Code | Module | Features |
|---|---|---|
| AUTH | Account access | 7 |
| NAV | Navigation | 2 |
| DAY | My Day | 5 |
| NOTIF | Notifications | 3 |
| CAL | Calendar | 1 |
| MEET | Meeting requests | 4 |
| UNI | Organisations | 1 |
| ORG | Organisations | 5 |
| CONT | Organisations | 1 |
| PROF | Organisations | 3 |
| PIPE | Pipeline | 4 |
| LEAD | Organisations | 1 |
| REF | Reference | 2 |
| MOU | MoUs | 4 |
| ONB | Onboarding | 2 |
| ORGP | Onboarding | 2 |
| APPT | Appointments | 8 |
| FUP | Follow-ups | 4 |
| ACT | Activities | 4 |
| TRAV | Travel | 12 |
| RPT | Daily report | 4 |
| MDASH | Manager: dashboard | 2 |
| MNOTIF | Manager: dashboard | 1 |
| MTEAM | Manager: team | 2 |
| MORG | Manager: organisations | 4 |
| MPIPE | Manager: pipeline | 1 |
| MAPPT | Manager: appointments | 2 |
| MCAL | Manager: appointments | 1 |
| MFUP | Manager: activity | 1 |
| MACT | Manager: activity | 1 |
| MRPT | Manager: daily reports | 2 |
| MMOU | Manager: organisations | 1 |
| MMEET | Manager: meeting requests | 1 |
| APPR | Manager: travel | 1 |
| MTRIP | Manager: travel | 2 |
| PERF | Manager: performance | 3 |
| TGT | Manager: targets | 2 |
| ADM | Admin | 11 |
| **Total** | | **117** |

## 3. Feature Inventory

ID format `DOC-BDM-<MOD>-NNN`, grouped by manual folder. Roles: BDM = Agent and School BDM, MGR = BDM Manager, OA = Overseas
Admin, SA = Super Admin.

### `user-manual/account-access/` (7)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-AUTH-001 | Choose your BDM portal and sign in as an Agent/School BDM | `/bdm/sign-in → /overseas/login` | BDM |
| DOC-BDM-AUTH-002 | Sign in as a BDM Manager (lands on Dashboard) | `/admin/login → /bdm/manager/dashboard` | MGR |
| DOC-BDM-AUTH-003 | Set your first password from the welcome email | `/overseas/reset-password, /admin/reset-password` | BDM, MGR |
| DOC-BDM-AUTH-004 | Forgot / reset your password | `/overseas/forgot-password, /admin/forgot-password` | BDM, MGR |
| DOC-BDM-AUTH-005 | Change your password and sign out | `/account/password, sidebar` | BDM, MGR |
| DOC-BDM-AUTH-006 | Your BDM profile and the account profile page | `/bdm/profile, /account/profile` | BDM, MGR |
| DOC-BDM-AUTH-007 | "Access unavailable" messages (no BDM profile, wrong role, wrong portal) | `any /bdm/*` | BDM, MGR |

### `user-manual/navigation/` (1)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-NAV-001 | BDM portal tour: sidebar, role pill (Agent BDM / School BDM), unread badge | `/bdm/*` | BDM |

### `manager-manual/navigation/` (1)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-NAV-002 | Manager portal tour: the 17-item sidebar | `/bdm/manager/*` | MGR |

### `user-manual/my-day/` (5)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-DAY-001 | My Day: today's appointments, upcoming travel, follow-ups | `/bdm/my-day` | BDM |
| DOC-BDM-DAY-002 | My Day: Agent overview tiles | `/bdm/my-day` | Agent BDM |
| DOC-BDM-DAY-003 | My Day: School overview tiles | `/bdm/my-day` | School BDM |
| DOC-BDM-DAY-004 | My Day: monthly targets card | `/bdm/my-day` | BDM |
| DOC-BDM-DAY-005 | My Day: meeting requests card | `/bdm/my-day` | BDM |

### `user-manual/notifications/` (3)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-NOTIF-001 | Read and open notifications | `/bdm/notifications` | BDM |
| DOC-BDM-NOTIF-002 | Reminders (appointment, travel, follow-up, MoU follow-up/renewal) and email action links | `/bdm/notifications` | BDM |
| DOC-BDM-NOTIF-003 | Decision notices (trip approved / not approved, onboarding outcome, handover) | `/bdm/notifications` | BDM |

### `user-manual/calendar/` (1)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-CAL-001 | Calendar: week/day view and navigation | `/bdm/calendar` | BDM |

### `user-manual/meeting-requests/` (4)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MEET-001 | Meeting request inbox and filters (requests from telecallers) | `/bdm/meeting-requests` | BDM |
| DOC-BDM-MEET-002 | View a meeting request | `/bdm/meeting-requests/[id]` | BDM |
| DOC-BDM-MEET-003 | Accept a request and book the appointment | `/bdm/meeting-requests/[id]` | BDM |
| DOC-BDM-MEET-004 | Decline a request with a reason | `/bdm/meeting-requests/[id]` | BDM |

### `user-manual/organisations/` (11)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-UNI-001 | View a linked University Master record | `/bdm/universities/[id]` | BDM |
| DOC-BDM-ORG-001 | Browse and filter your module's organisations | `/bdm/organizations` | BDM |
| DOC-BDM-ORG-002 | Add an organisation (duplicate warning) | `/bdm/organizations/new` | BDM |
| DOC-BDM-ORG-003 | Open an organisation (read-only when not assigned to you) | `/bdm/organizations/[id]` | BDM |
| DOC-BDM-ORG-004 | Edit organisation details | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-ORG-005 | Archive an organisation (your manager restores it) | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-CONT-001 | Manage contacts (add, edit, primary, delete; 1–20) | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-PROF-001 | Agent organisation details (type profile) | `/bdm/organizations/new, [id]` | BDM |
| DOC-BDM-PROF-002 | School organisation details (board, type, grades) | `/bdm/organizations/new, [id]` | BDM |
| DOC-BDM-PROF-003 | Change an organisation's type (clear-first rule) | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-LEAD-001 | Add and view student leads on an organisation | `/bdm/organizations/[id]` | BDM |

### `user-manual/pipeline/` (4)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-PIPE-001 | Move an organisation through pipeline stages (moving back needs a reason) | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-PIPE-002 | Mark an organisation Lost and revive it | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-PIPE-003 | Read the stage history | `/bdm/organizations/[id]` | BDM |
| DOC-BDM-PIPE-004 | Pipeline board (Mine / All in module, stage tiles, Lost) | `/bdm/pipeline` | BDM |

### `user-manual/reference/` (2)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-REF-001 | Reference lists: organisation types, contact roles, pipeline stages per module | `reference` | all |
| DOC-BDM-REF-002 | Management BDM figures (pointer only) | `/management/bdm` | partner, SA |

### `user-manual/mous/` (4)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MOU-001 | Start and edit an organisation's MoU (status, dates, signing) | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-MOU-002 | Upload and download the MoU document | `/bdm/organizations/[id]` | BDM |
| DOC-BDM-MOU-003 | MoU history, expiry and renewal | `/bdm/organizations/[id]` | BDM (assigned) |
| DOC-BDM-MOU-004 | MoU list by status | `/bdm/mous` | BDM |

### `user-manual/onboarding/` (4)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-ONB-001 | Request Agent onboarding (at Agreement Signed) | `/bdm/organizations/[id]` | Agent BDM |
| DOC-BDM-ONB-002 | Request School onboarding (MoU Signed / Active) | `/bdm/organizations/[id]` | School BDM |
| DOC-BDM-ORGP-001 | Agent performance panel | `/bdm/organizations/[id]` | Agent BDM |
| DOC-BDM-ORGP-002 | School activity panel | `/bdm/organizations/[id]` | School BDM |

### `user-manual/appointments/` (8)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-APPT-001 | View and filter your appointments | `/bdm/appointments` | BDM |
| DOC-BDM-APPT-002 | Book an appointment (overlap warning) | `/bdm/appointments/new` | BDM |
| DOC-BDM-APPT-003 | Link an appointment to a trip | `/bdm/appointments/new, [id]` | BDM |
| DOC-BDM-APPT-004 | Appointment detail, edit details and history | `/bdm/appointments/[id]` | BDM |
| DOC-BDM-APPT-005 | Confirm, reschedule or cancel an appointment | `/bdm/appointments/[id]` | BDM |
| DOC-BDM-APPT-006 | Complete with a meeting report, or mark no-show | `/bdm/appointments/[id]` | BDM |
| DOC-BDM-APPT-007 | Edit the meeting report the same day; book the next meeting | `/bdm/appointments/[id]` | BDM |
| DOC-BDM-APPT-008 | Act on an appointment reminder | `/bdm/appointments/[id]?action=` | BDM |

### `user-manual/follow-ups/` (4)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-FUP-001 | Follow-ups: tabs, counts and filters (incl. Overdue) | `/bdm/follow-ups` | BDM |
| DOC-BDM-FUP-002 | Add a follow-up or task | `/bdm/follow-ups` | BDM |
| DOC-BDM-FUP-003 | Mark done, edit or cancel a task | `/bdm/follow-ups` | BDM |
| DOC-BDM-FUP-004 | Follow-ups created from meeting reports | `/bdm/follow-ups, /bdm/appointments/[id]` | BDM |

### `user-manual/activities/` (4)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-ACT-001 | Your activities for a day, with counts | `/bdm/activities` | BDM |
| DOC-BDM-ACT-002 | Log an activity (including backdating) | `/bdm/activities` | BDM |
| DOC-BDM-ACT-003 | Edit or delete today's activity | `/bdm/activities` | BDM |
| DOC-BDM-ACT-004 | Organisation activity timeline | `/bdm/organizations/[id]` | BDM |

### `user-manual/travel/` (12)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-TRAV-001 | View and filter your trips | `/bdm/travel` | BDM |
| DOC-BDM-TRAV-002 | Plan a new trip (draft) | `/bdm/travel/new` | BDM |
| DOC-BDM-TRAV-003 | Open a trip (details, appointments, productivity) | `/bdm/travel/[id]` | BDM |
| DOC-BDM-TRAV-004 | Edit a draft or rejected trip | `/bdm/travel/[id]` | BDM |
| DOC-BDM-TRAV-005 | Submit a trip for approval, or withdraw it | `/bdm/travel/[id]` | BDM |
| DOC-BDM-TRAV-006 | Handle a rejected trip (reason, fix, resubmit) | `/bdm/travel/[id]` | BDM |
| DOC-BDM-TRAV-007 | Start, complete or cancel a trip | `/bdm/travel/[id]` | BDM |
| DOC-BDM-TRAV-008 | Record trip expenses | `/bdm/travel/[id]#trip-costs` | BDM |
| DOC-BDM-TRAV-009 | Trip remarks | `/bdm/travel/[id]#trip-remarks` | BDM |
| DOC-BDM-TRAV-010 | Trip itinerary: appointments linked to a trip | `/bdm/travel/[id]#trip-appointments` | BDM |
| DOC-BDM-TRAV-011 | Travel report of a completed trip | `/bdm/travel/[id]/report` | BDM |
| DOC-BDM-TRAV-012 | Travel notifications and the day-before reminder | `/bdm/notifications` | BDM |

### `user-manual/daily-report/` (4)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-RPT-001 | View a day's live report | `/bdm/daily-report` | BDM |
| DOC-BDM-RPT-002 | Submit the daily report with a note (locks the day) | `/bdm/daily-report` | BDM |
| DOC-BDM-RPT-003 | Read a submitted report and your manager's comment | `/bdm/daily-report?date=` | BDM |
| DOC-BDM-RPT-004 | What each count means (Agent vs School tiles) | `/bdm/daily-report` | BDM |

### `manager-manual/dashboard/` (3)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MDASH-001 | Read the BDM overview tiles | `/bdm/manager/dashboard` | MGR |
| DOC-BDM-MDASH-002 | Act on dashboard alerts (AL-1 … AL-7) | `/bdm/manager/dashboard` | MGR |
| DOC-BDM-MNOTIF-001 | Manager notifications | `/bdm/manager/notifications` | MGR |

### `manager-manual/team/` (2)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MTEAM-001 | View the BDMs who report to you | `/bdm/manager/team` | MGR |
| DOC-BDM-MTEAM-002 | Read the Master view (type → BDM → linked organisations) | `/bdm/manager/hierarchy` | MGR |

### `manager-manual/organisations/` (5)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MORG-001 | Find the team's organisations | `/bdm/manager/organizations` | MGR |
| DOC-BDM-MORG-002 | Read an organisation's profile and panels | `/bdm/manager/organizations/[id]` | MGR |
| DOC-BDM-MORG-003 | Reassign an organisation to another BDM on your team | `/bdm/manager/organizations/[id]` | MGR |
| DOC-BDM-MORG-004 | Restore an archived organisation | `/bdm/manager/organizations?archived=1` | MGR |
| DOC-BDM-MMOU-001 | Review the team's MoUs by status | `/bdm/manager/mous` | MGR |

### `manager-manual/pipeline/` (1)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MPIPE-001 | Team pipeline by type and stage | `/bdm/manager/pipeline` | MGR |

### `manager-manual/appointments/` (3)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MAPPT-001 | Filter the team's appointments | `/bdm/manager/appointments` | MGR |
| DOC-BDM-MAPPT-002 | Read an appointment and its meeting report | `/bdm/manager/appointments/[id]` | MGR |
| DOC-BDM-MCAL-001 | View a BDM's calendar | `/bdm/manager/calendar` | MGR |

### `manager-manual/activity/` (2)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MFUP-001 | Review the team's follow-ups and tasks | `/bdm/manager/follow-ups` | MGR |
| DOC-BDM-MACT-001 | Review the team's activities for a day | `/bdm/manager/activities` | MGR |

### `manager-manual/daily-reports/` (2)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MRPT-001 | Check daily-report submission (7-day grid) | `/bdm/manager/daily-reports` | MGR |
| DOC-BDM-MRPT-002 | Read a daily report and comment | `/bdm/manager/daily-reports/[bdmId]` | MGR |

### `manager-manual/meeting-requests/` (1)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-MMEET-001 | Review meeting requests (team and open pool) | `/bdm/manager/meeting-requests` | MGR |

### `manager-manual/travel/` (3)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-APPR-001 | Work the travel approval queue | `/bdm/manager/approvals` | MGR |
| DOC-BDM-MTRIP-001 | Approve or reject a trip | `/bdm/manager/trips/[id]` | MGR |
| DOC-BDM-MTRIP-002 | Read a completed trip's travel report | `/bdm/manager/trips/[id]/report` | MGR |

### `manager-manual/performance/` (3)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-PERF-001 | Performance by BDM type for a period | `/bdm/manager/performance` | MGR |
| DOC-BDM-PERF-002 | Drill into one BDM type | `/bdm/manager/performance/[type]` | MGR |
| DOC-BDM-PERF-003 | Drill into one BDM (organisations and trips) | `/bdm/manager/performance/bdms/[id]` | MGR |

### `manager-manual/targets/` (2)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-TGT-001 | Team targets for a month; copy last month | `/bdm/manager/targets` | MGR |
| DOC-BDM-TGT-002 | Set one BDM's monthly targets | `/bdm/manager/targets/[bdmId]` | MGR |

### `admin-manual/` (11)
| ID | Feature | Route | Roles |
|---|---|---|---|
| DOC-BDM-ADM-001 | Create an Agent or School BDM | `/overseas/admin/bdms, /admin/bdms` | OA, SA |
| DOC-BDM-ADM-002 | Find and edit a BDM | `/overseas/admin/bdms, /admin/bdms` | OA, SA |
| DOC-BDM-ADM-003 | Deactivate a BDM with handover | `/overseas/admin/bdms, /admin/bdms` | OA, SA |
| DOC-BDM-ADM-004 | Hand over an inactive BDM's work; reactivate | `/overseas/admin/bdms, /admin/bdms` | OA, SA |
| DOC-BDM-ADM-005 | Re-send a BDM's set-password link | `/overseas/admin/users` | OA, SA |
| DOC-BDM-ADM-006 | Create a BDM Manager | `/admin/users` | SA |
| DOC-BDM-ADM-007 | Deactivate a BDM Manager and move the team | `/admin/bdms` | SA |
| DOC-BDM-ADM-008 | Link an agency from an Agent onboarding request | `/overseas/admin/agents` | OA |
| DOC-BDM-ADM-009 | Create or link a school from a School onboarding request | `/overseas/admin/schools` | OA |
| DOC-BDM-ADM-010 | Fallback travel approvals when the manager is inactive | `/admin/bdm-travel-approvals` | SA |
| DOC-BDM-ADM-011 | BDM leads in the admin lead list | `/overseas/admin/leads` | OA |

## 4. User Role Inventory

| Role | Label | Division | Sign-in | Landing | Created by |
|---|---|---|---|---|---|
| `bdm` (`bdm_type` agent) | Agent BDM | overseas | `/overseas/login` | `/bdm/my-day` | Overseas Admin or Super Admin |
| `bdm` (`bdm_type` school) | School BDM | overseas | `/overseas/login` | `/bdm/my-day` | Overseas Admin or Super Admin |
| `bdm_manager` | BDM Manager | global | `/admin/login` | `/bdm/manager/dashboard` | Super Admin only |
| `overseas_admin` | Overseas Admin | overseas | `/overseas/login` | — | — |
| `super_admin` | Super Admin | global | `/admin/login` | — | — |

## 5. Role Permission Matrix (summary; detail in appendices 01 §B.0, 02 §0.3, 03 §2–3)

| Capability | BDM | Manager | Overseas Admin | Super Admin |
|---|---|---|---|---|
| Read organisations in own module | ✔ | ✔ team | ✘ | ✘ (via management only) |
| Create / edit / archive organisation, contacts, pipeline, MoU | ✔ assigned | ✘ | ✘ | ✘ |
| Restore archived organisation / reassign | ✘ | ✔ team | ✘ | ✘ |
| Appointments, follow-ups, activities, daily report | ✔ own | read + comment on report | ✘ | ✘ |
| Plan / submit trips | ✔ own | ✘ | ✘ | ✘ |
| Approve / reject trips | ✘ | ✔ direct reports | ✘ | ✔ only if manager inactive |
| Accept / decline telecaller meeting requests | ✔ | read | ✘ | ✘ |
| Set monthly targets | ✘ | ✔ current..+12 months | ✘ | ✔ incl. past months |
| Request onboarding | ✔ assigned | ✘ | ✘ | ✘ |
| Link agency / school from onboarding | ✘ | ✘ | ✔ | ✔ |
| Create / edit / deactivate Agent & School BDMs | ✘ | ✘ | ✔ | ✔ |
| Create / deactivate BDM Manager | ✘ | ✘ | ✘ | ✔ |

## 6. Major User Workflows
1. **Set-up:** SA creates BDM Manager → OA creates Agent/School BDMs (module fixed, Employee ID, reporting manager) → welcome email → set password.
2. **Prospecting:** add organisation + contacts + type profile → move through pipeline → appointments (book, confirm, complete with meeting report) → follow-ups → activities.
3. **Travel:** plan trip → link appointments → submit → manager approves/rejects → start → expenses/remarks → complete → travel report.
4. **Close & onboard:** MoU (document, signing) → onboarding request → OA links agency / school → performance or activity panel.
5. **Daily rhythm:** My Day → calendar → notifications/reminders → daily report submit → manager comment.
6. **Telecaller hand-off:** telecaller files meeting request → BDM accepts (books appointment) or declines with reason.
7. **Manager oversight:** dashboard tiles/alerts → team → Master view → pipeline → performance drill-downs → targets.
8. **Lifecycle:** deactivate BDM with handover → reactivate; deactivate manager → team moves to replacement; fallback travel approvals.

## 7. Required Test Data (created by capture specs; all `Docs ` prefixed, `@example.test`)
- **Personas (S2):** Docs BDM Manager; Docs Agent BDM A, Docs Agent BDM B, Docs School BDM, Docs Spare BDM (for deactivation); a Docs telecaller (Overseas) to file meeting requests.
- **Organisations (S4):** ~8 Docs organisations across Agent and School stages, contacts, profiles, one archived, one Lost, one duplicate attempt, student leads.
- **MoUs (S5):** each status, a small generated PDF document; one Agent org at Agreement Signed and one School org MoU Signed → onboarding → linked to EduSphere Partner Agency / Sunrise Public School (D6).
- **Appointments (S6):** batch booked ~3 minutes ahead, then confirmed / rescheduled / cancelled / completed with reports / no-show; follow-ups and activities.
- **Travel (S7):** trips in draft, submitted, rejected, approved, in progress, completed, cancelled; expenses; travel report.
- **Meeting requests (S8):** named and pooled requests from the Docs telecaller; accept and decline.
- **Later days (S9, S10):** overdue follow-ups, a missed daily report, the MoU 5-day alert (D5).

## 8. Unknown Workflows Requiring Browser Verification
- Pipeline "Reason" blank-message wording (01 B-Q5); manager reassign picker and inactive BDMs (02 Q10).
- Forgot-password delivery on the docs stack (03 Q1) — AUTH-004 expected PARTIAL as in the other docs sets.
- Super Admin reactivating a BDM Manager from Users (03 Q2); manager notice email (02 Q17).
- "Management tasks" sidebar item (02 Q18) — link out, not documented here.

## 9. Product Findings and Open Questions (owner)
Recorded as found; manuals document behaviour **as built**. None blocks documentation.

| # | Finding | Source |
|---|---|---|
| P1 | Welcome email calls the role "Bdm" / "Bdm Manager". | 03 P1 |
| P2 | BDMs and managers can rename themselves on `/account/profile`, while `/bdm/profile` says to contact the administrator. | 03 P2 |
| P3 | `/overseas/login` text does not mention BDMs. | 03 P3 |
| P4 | No notification to a BDM when a telecaller files a meeting request. | 03 P4, 01 |
| P5 | No Re-send link on the BDMs page; admins use Users. | 03 P5 |
| P6 | Sign out lands on `/`, not the BDM chooser. | 03 P6 |
| P7 | BDM deactivation does not bump the session version (relies on the active check). | 03 P7 |
| P8 | Organisation type is independent of module: an Agent BDM can create a School/College/University organisation. | 01 B-Q1 |
| P9 | Any BDM can open any University Master record by id. | 01 B-Q2 |
| P10 | Agent daily report has 3 always-"Not tracked" tiles; several Agent target KPIs and the "Agents awaiting onboarding" tile show "Not tracked" though bdm-019 is merged. | 01, 02 Q5, 04 Q5 |
| P11 | Agent/School target KPI lists include College KPIs ("College Meetings", "New Colleges"). | 02 Q4 |
| P12 | Performance and Master view always show College columns for an Overseas-only team; Pipeline hides absent types; appointment Type filter lists all 37 types. | 02 Q1, Q3 |
| P13 | Meeting requests page shows the whole open pool of every type. | 02 Q2 |
| P14 | Reassigning an organisation does not move the old BDM's appointments, follow-ups or leads. | 02 Q9 |
| P15 | Trip expenses: no receipt upload, expense date not checked against trip dates, editable after completion/cancellation. | 01 (c.4) |
| P16 | A submitted daily report cannot be corrected and locks the day's activities; no notification to the BDM on manager comment or targets. | 01 (c.4), 02 Q13 |
| P17 | Activity "When" uses browser-local time, not IST. | 01 (c.3) |
| P18 | Dashboard team summary counts only the first 50 rows; AL-7 checks yesterday only. | 02 Q11, Q16 |
| P19 | Team-trips API exists with no page; no export anywhere. | 02 Q14, Q15 |
| P20 | Super Admin sees "BDM Manager" pill on Team/Approvals but is denied Notifications. | 02 Q12 |
