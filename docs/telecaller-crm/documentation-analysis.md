# EduSphere Overseas Telecaller CRM — Documentation Analysis (Phase 1)

> Master planning session S1, 2026-10-17. Code baseline `main` @ `6fee294d`. Branch `docs/telecaller-crm-user-guide`
> (worktree `.claude/worktrees/tel-docs`). Read-only source discovery; **nothing here is browser-verified yet**. Where this
> file and the browser disagree, the browser wins and this file is annotated.
>
> Field-level evidence (file:line, literal UI strings, error messages) lives in the four appendices:
> - `discovery/01-telecaller-frontline.md` — the Overseas telecaller portal (`/telecaller/*`)
> - `discovery/02-telecaller-manager.md` — the Telecaller Manager portal (`/telecaller/manager/*`)
> - `discovery/03-access-admin-counselor.md` — account access, admin provisioning and lifecycle, counselor side, intake
> - `discovery/04-test-data-tooling-decisions.md` — seed data, capture tooling, tel-001..026 decisions, glossary

**Owner scope answers (2026-10-17):**

| # | Question | Answer |
|---|---|---|
| D1 | Approach | Full verified set, same pipeline as the School CRM docs (`docs/school-crm/`). |
| D2 | Scope | Overseas `telecaller` + `telecaller_manager` (running an Overseas team) + Super Admin / Overseas Admin telecaller provisioning, deactivation and team move + the Overseas counselor side of handover/conversion. **IT-team telecallers are out of scope.** |
| D3 | Stack | Claude may start, seed, reset and snapshot only the `teldocs` compose project (web 3030, api 8030, Mailpit 127.0.0.1:8027). |
| D4 | Personas | **Both:** screenshots use `Docs` Overseas personas created through the real admin screens; an appendix maps them to the seeded demo accounts. |
| D5 | Conversion | Drive the real UI: capture specs create and enrol the Overseas application through the existing application screens (setup only, not screenshotted). |
| D6 | Time-based alerts | Set the Docs Overseas thresholds to 1 h, wait on the real beat job (~75 min), capture, then restore 24 h / 4 h. |

---

## 1. Application Overview

### 1.1 What the Telecaller CRM is
The Telecaller CRM (EVID-019, backlog `docs/delivery/TELECALLER_CRM_BACKLOG.md`, tel-001..026, all merged) is the
calling desk for enquiries. Leads arrive from the website, CSV imports, or manual entry. They are routed to a
telecaller by product rule, city rule or round robin. The telecaller calls, qualifies, follows up, sends WhatsApp/email,
books counselling appointments, and hands qualified leads to a **counselor**. The lead counts as **Converted** when the
counselor links a student whose Overseas application reaches `enrolled`.

Two roles:
- **Telecaller** (`telecaller`, division = team = `overseas`). Signs in at `/overseas/login`; works only their own leads.
- **Telecaller Manager** (`telecaller_manager`, division `global`). Signs in at `/admin/login`; sees their direct
  reports' leads plus unassigned leads in those reports' teams; runs routing, imports, catalogue, content library,
  targets, alerts, performance and reports.

Supporting roles in scope: **Super Admin**, **Overseas Admin** (create/deactivate telecallers), **Counselor** (Overseas,
receives handovers).

### 1.2 Technology (from code)
Next.js 15 web (`apps/web`), FastAPI (`apps/api`, routers under `/api/v1`), PostgreSQL, Celery worker + beat. The
worker sends tel-014 emails; beat raises tel-020 time-based alerts every 900 s. WhatsApp is click-to-chat (`wa.me`) and
calls are a `tel:` link plus a manual call log — there is no telephony or WhatsApp API.

### 1.3 Authentication (appendix 03 §1)
- Signed-out `/telecaller/*` → `/telecaller/sign-in` chooser (**IT team** / **Overseas team**); `/telecaller/manager/*` → `/admin/login`.
- Wrong portal: 403 "Use the correct EduSphere portal for this account: sign in at /overseas/login" (or `/admin/login`). Inactive: 401 "Invalid credentials".
- Landing: telecaller → `/telecaller/dashboard`; manager → `/telecaller/manager/team` (no manager home page).
- Welcome link 72 h → `/overseas/reset-password` (telecaller) or `/admin/reset-password` (manager).
- Telecallers can change only their mobile (`PATCH /telecaller/profile`; `PATCH /auth/me` refuses name changes with 403).

### 1.4 Cross-cutting rules worth explaining in every manual
- **Own-leads scope.** A telecaller opening a lead that is not theirs gets 404 "Lead not found".
- **Handover lock.** After handover the telecaller's lead view is read-only; the counselor owns it.
- **Daily caps.** 300 calls/day, 300 WhatsApp/day, 100 emails/day, 20 open follow-ups per lead.
- **Same-day windows.** Calls can be edited/deleted, and WhatsApp records deleted, only on the day they were logged.
- **Settings are not team-scoped** (appendix 02 §0.4): any manager can edit global products, campaigns, scripts,
  templates, brochures, and both teams' target defaults and alert thresholds. The manual documents this as built and
  tells Overseas managers to pick **Overseas** where forms default to IT (Rules, Targets).
- **Not built — never document:** telephony, ad-platform APIs, duplicate merge, automatic No Response, WhatsApp API and
  consent capture, email reply tracking, withdrawing a meeting request, quiet hours, working-day calendar, downstream
  Application/Visa CRMs (appendix 04 §4).

---

## 2. Module Inventory

| Module | Code | Manual folder | Role(s) | Features |
|---|---|---|---|---|
| Account access | AUTH | `user-manual/account-access/` | telecaller, manager | 8 |
| Navigation & notifications | NAV | `user-manual/navigation/` | telecaller, manager | 3 |
| Telecaller dashboard | DASH | `user-manual/dashboard/` | telecaller | 4 |
| Leads | LEAD | `user-manual/leads/` | telecaller | 7 |
| Qualification | QUAL | `user-manual/leads/` | telecaller | 1 |
| Calls | CALL | `user-manual/calls/` | telecaller | 2 |
| Follow-ups | FUP | `user-manual/follow-ups/` | telecaller | 2 |
| Counselling appointments | APPT | `user-manual/appointments/` | telecaller | 2 |
| WhatsApp & email | MSG | `user-manual/messages/` | telecaller | 2 |
| Content library | CONT | `user-manual/content/` (001) · `manager-manual/content/` (002–004) | telecaller, manager | 4 |
| BDM meeting requests | MEET | `user-manual/meeting-requests/` | telecaller | 2 |
| Handover & conversion | HAND | `user-manual/handover/` | telecaller | 2 |
| Lead timeline | TIME | `user-manual/leads/` | telecaller | 1 |
| Team | TEAM | `manager-manual/team/` | manager | 2 |
| Manager leads & assignment | MLEAD | `manager-manual/leads/` | manager | 7 |
| Distribution rules | DIST | `manager-manual/distribution/` | manager | 3 |
| Lead import | IMP | `manager-manual/imports/` | manager | 3 |
| Products & campaigns | CAT | `manager-manual/catalogue/` | manager | 2 |
| Targets | TGT | `manager-manual/targets/` | manager | 2 |
| Team follow-ups | MFUP | `manager-manual/follow-ups/` | manager | 1 |
| Alert settings | ALRT | `manager-manual/alerts/` | manager | 1 |
| Performance | PERF | `manager-manual/performance/` | manager | 1 |
| Reports | RPT | `manager-manual/reports/` | manager | 3 |
| Admin: telecaller accounts & lifecycle | ADM | `admin-manual/` | super_admin, overseas_admin | 9 |
| Counselor side | CNS | `admin-manual/counselor/` | counselor (+ overseas_admin) | 6 |
| Lead intake | INTAKE | `user-manual/intake/` | public / reference | 2 |
| **Total** | | | | **82** |

## 3. Feature Inventory

ID format `DOC-TEL-<MOD>-NNN`. "Src" = appendix row it was merged from.

### AUTH — Account access (8)
| ID | Feature | Route | Roles | Src |
|---|---|---|---|---|
| AUTH-001 | Choose your portal (Telecaller sign-in chooser) | `/telecaller/sign-in` | telecaller, manager | 03 |
| AUTH-002 | Sign in as an Overseas telecaller (where you land) | `/overseas/login` | telecaller | 01 ACC-001, 03 |
| AUTH-003 | Sign in as a Telecaller Manager (lands on Team) | `/admin/login` | manager | 02 MGRHOME-001, 03 |
| AUTH-004 | Set your first password from the welcome email | `/overseas/reset-password`, `/admin/reset-password` | both | 03 |
| AUTH-005 | Forgot / reset your password | `/overseas/forgot-password`, `/admin/forgot-password` | both | 03 |
| AUTH-006 | Change your password | `/account/password` | both | 03 |
| AUTH-007 | Your profile: view details, update your mobile (name locked) | `/telecaller/profile`, `/account/profile` | telecaller | 01 ACC-003/004, 03 |
| AUTH-008 | Sign out, ended sessions and "access unavailable" messages | sidebar | both | 03 |

### NAV — Navigation & notifications (3)
| ID | Feature | Route | Roles |
|---|---|---|---|
| NAV-001 | Telecaller portal tour: sidebar, role label, unread badge | `/telecaller/*` | telecaller |
| NAV-002 | Manager portal tour: the 16-item sidebar | `/telecaller/manager/*` | manager |
| NAV-003 | Notifications and the nine alert types | `/telecaller/notifications` | telecaller |

### DASH — Telecaller dashboard (4)
| ID | Feature | Route |
|---|---|---|
| DASH-001 | Today's tiles (10 tiles with hints) | `/telecaller/dashboard` |
| DASH-002 | Today's follow-ups and appointments cards | `/telecaller/dashboard` |
| DASH-003 | My targets (6 KPIs) | `/telecaller/dashboard` |
| DASH-004 | Daily activity for a chosen day | `/telecaller/dashboard?date=` |

### LEAD / QUAL / TIME — Leads (9)
| ID | Feature | Route |
|---|---|---|
| LEAD-001 | My Leads: search, filters, paging | `/telecaller/leads` |
| LEAD-002 | Create a lead | `/telecaller/leads/new` |
| LEAD-003 | Duplicate warning and "Add enquiry to this lead" | `/telecaller/leads/new` |
| LEAD-004 | Open a lead: header, Call button, panels, read-only state | `/telecaller/leads/[id]` |
| LEAD-005 | Set priority | `/telecaller/leads/[id]` |
| LEAD-006 | Edit lead details (contact, product) | `/telecaller/leads/[id]` |
| LEAD-007 | Change stage / close a lead (reasons, no reopen) | `/telecaller/leads/[id]` |
| QUAL-001 | Qualification form (Basic + Overseas requirement) | `/telecaller/leads/[id]` |
| TIME-001 | Read the lead activity timeline | `/telecaller/leads/[id]` |

### CALL / FUP / APPT / MSG / CONT-001 — Working a lead (9)
| ID | Feature | Route |
|---|---|---|
| CALL-001 | Log a call (13 outcomes, stage effects, next follow-up) | `/telecaller/leads/[id]` |
| CALL-002 | Edit or delete today's call | `/telecaller/leads/[id]` |
| FUP-001 | Add, reschedule, complete or cancel a follow-up on a lead | `/telecaller/leads/[id]` |
| FUP-002 | Today's and overdue follow-ups page | `/telecaller/follow-ups` |
| APPT-001 | Book a counselling appointment | `/telecaller/leads/[id]` |
| APPT-002 | Reschedule or cancel an appointment | `/telecaller/leads/[id]` |
| MSG-001 | Send and record a WhatsApp message; delete today's record | `/telecaller/leads/[id]` |
| MSG-002 | Send an email and track delivery | `/telecaller/leads/[id]` |
| CONT-001 | Use the call script, templates and brochure links on a lead | `/telecaller/leads/[id]` |

### MEET / HAND — Hand-offs (4)
| ID | Feature | Route |
|---|---|---|
| MEET-001 | Request a BDM meeting | `/telecaller/meeting-requests/new` |
| MEET-002 | Track my BDM meeting requests | `/telecaller/meeting-requests` |
| HAND-001 | Hand a lead over to a counselor | `/telecaller/leads/[id]` |
| HAND-002 | Follow a handed-over lead: read-only view, returns, student link, milestones, conversion | `/telecaller/leads/[id]` |

### Manager modules (28, including CONT-002..004)
| ID | Feature | Route |
|---|---|---|
| TEAM-001 | View the telecallers who report to you | `/telecaller/manager/team` |
| TEAM-002 | A telecaller's daily activity and targets | `/telecaller/manager/team/[id]/activity` |
| MLEAD-001 | Browse, search and filter team leads | `/telecaller/manager/leads` |
| MLEAD-002 | Enter a new lead (distributed or queued; duplicate panel) | `/telecaller/manager/leads/new` |
| MLEAD-003 | Open a team lead: stage, priority, details, qualification | `/telecaller/manager/leads/[id]` |
| MLEAD-004 | Reopen a closed lead | `/telecaller/manager/leads/[id]` |
| MLEAD-005 | Assign or change the counselor on a lead | `/telecaller/manager/leads/[id]` |
| MLEAD-006 | Assign unassigned leads in bulk | `/telecaller/manager/assignment` |
| MLEAD-007 | Reassign leads between telecallers | `/telecaller/manager/assignment?view=assigned` |
| DIST-001 | How routing works (product → city → round robin → queue) | `/telecaller/manager/distribution` |
| DIST-002 | Create a product or city rule | `/telecaller/manager/distribution` |
| DIST-003 | Change or delete a rule | `/telecaller/manager/distribution` |
| IMP-001 | Download and fill in the CSV template | `/telecaller/manager/imports` |
| IMP-002 | Import leads for a campaign; read the per-row report | `/telecaller/manager/imports` |
| IMP-003 | Review past imports | `/telecaller/manager/imports` |
| CAT-001 | Manage products | `/telecaller/manager/products` |
| CAT-002 | Manage campaigns | `/telecaller/manager/campaigns` |
| CONT-002 | Write call scripts | `/telecaller/manager/scripts` |
| CONT-003 | Create and preview WhatsApp/email templates | `/telecaller/manager/templates` |
| CONT-004 | Upload brochures and copy 7-day links | `/telecaller/manager/brochures` |
| TGT-001 | Set team default targets (daily/monthly) | `/telecaller/manager/targets?for=overseas` |
| TGT-002 | Override targets for one telecaller | `/telecaller/manager/targets?for=<id>` |
| MFUP-001 | Monitor team follow-ups | `/telecaller/manager/follow-ups` |
| ALRT-001 | Set team alert thresholds (and what triggers each alert) | `/telecaller/manager/alerts` |
| PERF-001 | Compare telecallers over a date range; export CSV | `/telecaller/manager/performance` |
| RPT-001 | Source / Course / Campaign funnel reports | `/telecaller/manager/reports` |
| RPT-002 | Telecaller activity report | `?report=telecaller` |
| RPT-003 | Counselor handover report | `?report=handover` |


### ADM — Admin: telecaller accounts & lifecycle (9)
| ID | Feature | Route | Roles |
|---|---|---|---|
| ADM-001 | Create a Telecaller Manager | `/admin/users` | super_admin |
| ADM-002 | Create an Overseas telecaller | `/overseas/admin/telecallers`, `/admin/telecallers` | overseas_admin, super_admin |
| ADM-003 | Find and edit a telecaller (Employee ID, manager, mobile) | same | overseas_admin, super_admin |
| ADM-004 | Re-send a set-password link | `/admin/users`, `/overseas/admin/users` | overseas_admin, super_admin |
| ADM-005 | Deactivate a telecaller and hand over open leads | Telecallers page | overseas_admin, super_admin |
| ADM-006 | Reassign the open work of an inactive telecaller | Telecallers page | overseas_admin, super_admin |
| ADM-007 | Move a telecaller to the other team | Telecallers page | super_admin |
| ADM-008 | Reactivate a telecaller | Telecallers page / Users | overseas_admin, super_admin |
| ADM-009 | Deactivate a Telecaller Manager (with replacement) | `/admin/telecallers` | super_admin |

### CNS — Counselor side (6)
| ID | Feature | Route | Roles |
|---|---|---|---|
| CNS-001 | See leads handed to you | `/overseas/counselor/leads` | counselor |
| CNS-002 | Open a handed-over lead (details, milestones, activity) | `/overseas/counselor/leads/[id]` | counselor |
| CNS-003 | Link / unlink the student account | same | counselor |
| CNS-004 | Return a lead to the telecaller | same | counselor |
| CNS-005 | Conversion when the student enrols (and admin unlink) | counselor detail, `/overseas/admin/leads` | counselor, overseas_admin |
| CNS-006 | BDM side of meeting requests (touchpoint note only) | `/bdm/meeting-requests` | bdm (reference) |

### INTAKE — Lead intake (2)
| ID | Feature | Route |
|---|---|---|
| INTAKE-001 | A website enquiry becomes (or joins) a lead | `/overseas/contact` |
| INTAKE-002 | Lead sources reference (13 sources) | reference |

---

## 4. User Role Inventory

| Role | Label | Division | Sign-in | Landing | Created by | Manual |
|---|---|---|---|---|---|---|
| `telecaller` (Overseas team) | Overseas Telecaller | overseas | `/overseas/login` | `/telecaller/dashboard` | Overseas Admin or Super Admin | user-manual, role guide |
| `telecaller_manager` | Telecaller Manager | global | `/admin/login` | `/telecaller/manager/team` | Super Admin only | manager-manual, role guide |
| `super_admin` | Super Admin | global | `/admin/login` | — | — | admin-manual |
| `overseas_admin` | Overseas Admin | overseas | `/overseas/login` | — | — | admin-manual |
| `counselor` | Counselor | overseas | `/overseas/login` | — | — | admin-manual/counselor |
| `bdm` (Agent/School) | BDM | overseas | `/overseas/login` | — | — | reference only (CNS-006) |

## 5. Role Permission Matrix (summary; detail in appendices 02 §0.3, 03 §2–4)

| Capability | Telecaller | Manager | Overseas Admin | Super Admin | Counselor |
|---|---|---|---|---|---|
| Work own leads (calls, messages, follow-ups, appointments) | ✔ own | ✘ (view only) | ✘ | ✘ | ✘ |
| Change stage / priority / details / qualification | ✔ own, open | ✔ team | ✘ | ✘ | ✘ |
| Reopen a closed lead | ✘ | ✔ (to Follow-up, reason) | ✘ | ✘ | ✘ |
| Hand over to counselor | ✔ own | ✔ team | ✘ | ✘ | — |
| Link student / return lead | ✘ | ✘ | ✘ | ✘ | ✔ handed-to-me |
| Assign / reassign leads, rules, imports | ✘ | ✔ | ✘ | ✘ | ✘ |
| Catalogue, content library, targets, alert thresholds | read (on lead) | ✔ (global, both teams) | ✘ | by URL only | ✘ |
| Create telecaller | ✘ | ✘ | ✔ Overseas | ✔ both | ✘ |
| Create / deactivate manager | ✘ | ✘ | ✘ | ✔ | ✘ |
| Deactivate / reactivate telecaller | ✘ | ✘ | ✔ | ✔ | ✘ |
| Move team | ✘ | ✘ | ✘ (needs both teams) | ✔ | ✘ |
| Unlink a converted lead | ✘ | ✘ | ✔ | ✔ | ✘ |

## 6. Frontend Route Inventory (in scope)

- **Account:** `/telecaller/sign-in`, `/overseas/login`, `/admin/login`, `/overseas|admin/forgot-password`, `/overseas|admin/reset-password`, `/account/password`, `/account/profile`.
- **Telecaller (12):** `/telecaller`, `/dashboard`, `/leads`, `/leads/new`, `/leads/[id]`, `/follow-ups`, `/meeting-requests`, `/meeting-requests/new`, `/notifications`, `/profile`.
- **Manager (19):** `/telecaller/manager` + `team`, `team/[id]/activity`, `leads`, `leads/new`, `leads/[id]`, `assignment`, `distribution`, `imports`, `products`, `campaigns`, `scripts`, `templates`, `brochures`, `targets`, `follow-ups`, `alerts`, `performance`, `reports`.
- **Admin:** `/admin/users`, `/admin/telecallers`, `/overseas/admin/telecallers`, `/overseas/admin/users`, `/overseas/admin/leads`.
- **Counselor:** `/overseas/counselor/leads`, `/overseas/counselor/leads/[id]`.
- **Public:** `/overseas/contact`.

## 7. Backend API Mapping
Per-feature endpoint lists are in appendix 01 §(a), 02 §A, 03 §(a). The full tel route list used by e2e tests is in
appendix 04 §3. Routers: `api/api/telecaller*.py`, `lead_appointments.py`, `lead_handover.py`, `admin.py`,
`counselor*.py`; services `api/services/lead_*.py`, `telecaller_*.py`.

## 8. Major User Workflows
1. **Account set-up:** Super Admin creates manager → Overseas Admin creates telecaller with manager + Employee ID → welcome email → set password → sign in.
2. **Lead arrival:** website enquiry / CSV import / manual entry → duplicate check → routing (product rule → city rule → round robin → unassigned queue) → "New lead assigned" alert.
3. **Working a lead:** open → call (`tel:`) → log outcome → qualification → WhatsApp/email → follow-up → stage changes.
4. **Counselling:** book appointment with counselor → reschedule/cancel.
5. **Handover & conversion:** hand over → counselor links student → (application enrolled) → Converted; or counselor returns the lead.
6. **Manager oversight:** team page → activity → follow-ups monitor → alerts → performance → reports → targets.
7. **Lifecycle:** deactivate telecaller → open work handed to a teammate or team queue → reactivate / move team.

## 9. Required Screenshots
Estimated ~170 PNGs: ~2 per feature, plus one per differing role on shared screens (lead detail as telecaller vs manager
vs counselor; handed-over read-only state; closed lead). Path `docs/telecaller-crm/screenshots/<module>/NN-<feature>-<step>.png`.

## 10. Required Test Data (created by capture specs, all `Docs ` prefixed, `@example.test`)
- **Personas (S2, via admin UI):** Docs Overseas Manager; Docs Telecaller A/B/C (Overseas, Employee IDs DOCS-TEL-A..C, reporting to Docs Overseas Manager); Docs Counselor (Overseas); Docs Student (Overseas student account, for linking/conversion).
- **Catalogue & content (S4):** Docs product(s) + campaign, a Docs call script with steps, Docs WhatsApp + email templates, one brochure PDF (generated, no real content).
- **Routing:** a product rule → Telecaller A, a city rule → Telecaller B.
- **Leads (S5):** ~20 Docs leads across all 11 open stages and 5 closed outcomes, priorities, sources; a CSV import with created / attached / rejected rows; a duplicate.
- **Activity (S6–S7):** calls with several outcomes, follow-ups today/overdue/future, WhatsApp + emails (delivered/failed via Mailpit), appointments, a BDM meeting request (Agent/School BDM), a handed-over lead, a returned lead, a converted lead (application enrolled via real UI, D5).
- **Alerts (S8):** 1-hour thresholds, untouched new/hot leads, ~75 min wait (D6).
- **Lifecycle (S10, last):** deactivate Telecaller C with open work; reactivate; Super Admin team move.
- Seeded demo accounts (Lakshmi, Imran, counselor@) are documented only in the demo-account appendix (D4).

## 11. Unknown Workflows Requiring Browser Verification
- What the **Call** button does on the manager lead page (appendix 02 Q5).
- "Management tasks" sidebar item for telecaller and manager (01, 02 Q10).
- Exact text of three alerts ("New lead assigned", "Lead not contacted", "Lead returned for follow-up").
- Counselor handover API path from the manager page (02 MLEAD-005).
- Forgot-password delivery on the docs stack (webhook only, raw token — 03 Q1). Expect AUTH-005 to be PARTIAL, as in the School CRM docs.
- Email delivery status values as seen through Mailpit.

## 12. Product Findings and Open Questions (owner)
Recorded as found; the manuals document behaviour **as built**. None blocks documentation.

| # | Finding | Source |
|---|---|---|
| P1 | An Overseas telecaller can create a lead on an IT product; the lead becomes `division=it` but stays assigned to them (product picker not team-filtered). | 01 Q1, `lead_intake.py:95-130` |
| P2 | Priority, details and qualification stay editable on a **closed** lead; only handover blocks writes. | 01 Q2 |
| P3 | Settings are not team-scoped: any manager can edit IT and Overseas products, content, target defaults, alert thresholds. | 02 Q1, 03 Q8 |
| P4 | Rules and Targets forms default to IT; Performance offers IT to an Overseas-only manager while Reports hides the picker. | 02 Q2–Q3 |
| P5 | Round robin spans the whole team, including other managers' reports. | 02 Q4 |
| P6 | Reports accept a future "To" date; Performance refuses it. | 02 Q6 |
| P7 | Managers receive no alerts (no Notifications item). | 02 Q7 |
| P8 | Forgot-password email is webhook-only (raw token, no link, no SMTP). | 03 Q1, `PRODUCT_DECISION_REGISTER.md:2135` |
| P9 | Counselor gets no notification on handover. | 03 Q2 |
| P10 | Telecallers page has no "Re-send link"; admin must use Users. | 03 Q3 |
| P11 | Overseas Admin cannot move teams (needs both teams). | 03 Q4 |
| P12 | No reactivate control for managers on the managers card. | 03 Q5 |
| P13 | Manager on `/account/password` gets no "Forgot your current password?" link; session-expired message lacks an admin sign-in link. | 03 Q6 |
| P14 | Manager can edit own name on `/account/profile` (telecaller cannot). | 03 Q7 |
| P15 | "Telecaller profile not set up" card's "Go to your dashboard" loops. | 03 Q9 |
| P16 | Sidebar sign-out lands on `/`, not the sign-in chooser. | 03 Q10 |
| P17 | Import history shows only the manager's own imports. | 02 Q9 |
