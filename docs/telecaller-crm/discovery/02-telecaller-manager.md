# Discovery: Telecaller Manager portal (role `telecaller_manager`)

> **Evidence appendix** for `docs/telecaller-crm/documentation-analysis.md`. This is raw, read-only source discovery (S1, 2026-10-17, code `main` @ `6fee294d`, worktree `.claude/worktrees/tel-docs`). It gives field-level detail for the module sessions. It is **not browser-verified**: where this file and the browser disagree, the browser wins and this file gets an annotation (it is not trusted silently).

Nothing was run. Every statement comes from source. Path prefixes: `web/` = `apps/web/`, `api/` = `apps/api/app/`. All API paths are mounted under `/api/v1`. Legend: **VERIFICATION REQUIRED** = not settled from code; confirm in the browser or with the owner. Decision IDs come from `docs/decisions/PRODUCT_DECISION_REGISTER.md` and code comments. Code is the authority.

The manual's focus is a manager who runs an **Overseas** team. Rows marked **[OVS]** call out team- or division-specific behaviour.

---

## 0. Cross-cutting facts (read first)

### 0.1 Account, sign-in and landing
| Fact | Evidence |
|---|---|
| Role `telecaller_manager`, division `global`. Only super_admin creates managers. | `api/services/telecaller.py:21` (comment), seed `api/seed.py:872` |
| Demo account: `telecaller.manager@edusphere.local`, "Lakshmi Telecaller Manager". Its two direct reports are "Pooja IT Telecaller" (team `it`, TEL-DEMO-001) and "Imran Overseas Telecaller" (team `overseas`, TEL-DEMO-002). The demo manager is therefore **mixed-team, not Overseas-only** [OVS]. | `api/seed.py:861-879` |
| Sign-in is at `/admin/login`. After login, `ROLE_DASHBOARD_PATH.telecaller_manager = "/telecaller/manager/team"`. | `web/lib/navigation.ts:50` |
| Middleware sends a signed-out visitor of `/telecaller/manager/*` to `/admin/login?next=…`. Other `/telecaller/*` pages go to `/telecaller/sign-in`. | `web/middleware.ts:11-19` |
| The `/telecaller/sign-in` chooser says: "Choose your team's portal. Telecaller Managers sign in at **Administration**." The link goes to `/admin/login`, and `next` is kept only for `/telecaller/manager…` paths. | `web/app/telecaller/sign-in/page.tsx:12-24` |
| `/telecaller/manager` redirects to `/telecaller/manager/team`. There is no manager dashboard or home page. | `web/app/telecaller/manager/page.tsx:3-6` |

### 0.2 Shell and sidebar (`TELECALLER_MANAGER_NAV`, `web/lib/navigation.ts:112-127`)
The sidebar shows these items in this order: **Team, Leads, Follow-ups, Lead assignment, Distribution rules, Lead import, Targets, Performance, Reports, Alert settings, Products, Campaigns, Scripts, Templates, Brochures, Management tasks** (the last one is `/account/management-tasks`, mgmt-028, `navigation.ts:11`).
- Role pill: "Telecaller Manager". A super_admin on the same pages sees "Super Administrator" (`web/components/TelecallerCataloguePage.tsx:20`).
- Footer: "Change password", "My profile", "Sign out". Top bar: "EduSphere Portal" plus the user's name. The mobile menu (`PortalMobileNav`) replaces the sidebar below 980 px (`web/components/PortalShell.tsx:17`).
- An item is marked active only on an exact path match, so sub-pages such as `/leads/[id]`, `/leads/new` and `/team/[id]/activity` highlight nothing.
- **There is no Notifications item and no unread badge.** tel-020 alerts go only to the lead's telecaller (`api/services/telecaller_alerts.py:1-2`).

### 0.3 Authorization model (as built)
| Rule | Evidence |
|---|---|
| Manager gate is `require_manager`: the role must be `telecaller_manager` or `super_admin`, otherwise **403 "Telecaller manager role required"**. | `api/services/telecaller.py:143-145` |
| Frontend guard: every manager page calls `/auth/me` and shows `accessDenied(user, "Telecaller manager role required")` for other roles. A signed-out user gets the "Access unavailable" card with a link to `/admin/login`. | `TelecallerCataloguePage.tsx:12-18`, `TelecallerLeadPages.tsx:32-39`, `team/[id]/activity/page.tsx:26-29` |
| **Team scope (T23)**: a manager's telecallers are exactly their **direct reports** (`TelecallerProfile.reporting_manager_user_id == manager`). super_admin sees everyone. | `api/services/telecaller.py:148-150` |
| **Lead scope (T23)**: the manager sees the leads of their direct reports, plus **unassigned leads whose division is one of the teams their reports belong to**. A lead outside this scope returns 404 "Lead not found". | `api/services/lead_pipeline.py:41-52` |
| Consequence [OVS]: a manager whose reports are all Overseas sees only Overseas unassigned leads. The "team" of a manager is never stored. It is derived from the reports' `team`. | same |
| Read-only (D1): only a **telecaller** becomes read-only once a counselor is assigned (`owner_id`). A manager can still act on a handed-over lead. | `api/services/telecaller_leads.py:27-35` |
| `core/rbac.py:55` maps `telecaller_manager` to `{"telecaller:team"}`, but routes check `user.role` inline. | `api/core/rbac.py:55` |

### 0.4 What is NOT team-scoped (important for an Overseas manager) [OVS]
| Surface | Scope as built | Evidence |
|---|---|---|
| Products, Campaigns | **Global catalogue.** Any manager can create or edit any product or campaign, IT ones included. | `api/api/telecaller_catalogue.py:88-190` (only `require_manager`) |
| Scripts, Templates, Brochures | **Global library.** Any manager can edit all of it. | `api/api/telecaller_content.py:89-288` |
| Targets: team defaults | Any manager can set the **IT or Overseas** team default. Per-telecaller overrides are limited to direct reports. | `api/api/telecaller_targets.py:33-48`, `services/telecaller_targets.py:43-68` |
| Alert settings | Both team cards (IT, Overseas) are shown, and **any manager** can edit either one. | `api/api/telecaller_settings.py:27-50` |
| Distribution rules: list | Every manager **reads every rule of both teams**. Only rules whose telecaller reports to them are editable. | `api/api/telecaller_distribution.py:99-117` |
| Pickers and filters | The Assignment "Team" filter, Rules "Show" and Performance "Team" always offer both teams. The Reports team picker appears only if the manager's reports span more than one team. | see each page |
Whether this global edit right is intended for a team-specific manager is **VERIFICATION REQUIRED** (see open questions).

### 0.5 Shared list idioms
- Most lists keep their filter, search and page in the URL (`?q=&offset=` and so on). Page size is 50 for the team, leads, assignment, import history and target history lists, and 100 for the catalogue and library lists (`web/lib/telecaller.ts:108`, `web/lib/telecallerCatalogue.ts:11`). The pager reads "Showing a–b of N" with **Previous** and **Next** buttons.
- Common states: "Loading …", "Unable to load …" with a **Retry** button, an empty sentence, and a status notice after each change.
- Inline row edit: **Edit**, then **Save** or **Cancel** (Esc also cancels). **Deactivate** opens an inline confirm with **Confirm deactivate** and **Keep active**. **Reactivate** has no confirm.

---

## 1. Team: `/telecaller/manager/team` (landing page)
- Frontend: `web/app/telecaller/manager/team/page.tsx:13-46`, with the table in `web/components/TelecallerTeamTable.tsx:10-46`. It is server-rendered. Paging is by link (`?offset=`), 50 per page.
- API: `GET /telecaller/manager/team?limit&offset&q` at `api/api/telecaller.py:92-97`. It lists direct reports, **inactive ones included**. `q` matches name, email or Employee ID (the UI does not send `q`).

| Element | Literal text |
|---|---|
| Eyebrow / H2 | "Team" / "Telecallers who report to you" |
| Columns | Name, Employee ID, Team ("IT" or "Overseas"), Mobile ("—" if none), Status (badge "Active" or "Inactive"), Activity (link "View", aria "Activity for {name}") |
| Empty | "No telecallers report to you yet." |
| Past the end | "This page is past the end of your team." + **Go to the first page** |
| Pager | "Showing a–b of N", Previous, Next (only when total > 50) |

There is no search box, no filters and no add or edit action. Telecallers are created and moved by admins (tel-001 and tel-025, `/admin/telecallers`); that is outside the manager portal.

### 1.1 Daily activity: `/telecaller/manager/team/[id]/activity?date=YYYY-MM-DD`
- Frontend: `web/app/telecaller/manager/team/[id]/activity/page.tsx:17-61` and `web/components/TelecallerActivityPanel.tsx:10-51`.
- API: `GET /telecaller/activity?date&user_id` at `api/api/telecaller_dashboard.py:45-73`. For a manager, `user_id` is required (422 "Choose a telecaller"). The telecaller must be a direct report, or the API answers **404 "Telecaller not found"** (`services/telecaller_targets.py:58-68`). A future day gives **422 "Daily activity can't be shown for a future date"**.
- UI: eyebrow "Team · Daily activity". H2 = the telecaller's name, or "Daily activity". Button **Back to team**. A malformed or foreign id shows "This telecaller is not one of your reports." Other failures show "Daily activity is unavailable right now." (`web/lib/telecallerMetrics.ts:287`).
- Card "Daily activity": a **Day** date input (max = today in IST, required) and a **Show** button. This is a plain GET form.
- Table 1, "Activity on {d MMM yyyy}" | Count, 13 rows. Definitions come from `api/services/telecaller_metrics.py`. The day is an IST calendar day [start, end). Labels are from `web/lib/telecallerMetrics.ts:244-258`.

| # | Label | Definition (code) |
|---|---|---|
| D1 | Total leads assigned | Open (not closed) leads owned by the telecaller **as of** end of day, or now for today. Reconstructed from `lead.assign` audit rows and the stage history (`_snapshot`, :92-106) |
| D2 | Total calls | `LeadCall` rows by caller with `occurred_at` in the day (:144-146) |
| D3 | Connected calls | Calls minus not-connected |
| D4 | Not connected | Calls whose outcome is in {busy, no_answer, switched_off, wrong_number} (`api/services/lead_calls.py:33`) |
| D5 | Follow-ups completed | Follow-ups `completed_by` the user, completed in the day |
| D6 | Follow-ups pending | Follow-ups due before day end that were open as of that time (:99-105) |
| D7 | New appointments | Counselor appointments + BDM appointments |
| D8 | Counselor appointments | `Appointment` with a lead, `booked_by` the user, created in the day |
| D9 | BDM appointments | `BdmMeetingRequest` by the requester, created in the day |
| D10 | WhatsApp messages | `LeadMessage` channel `whatsapp`, sender = user, sent in the day |
| D11 | Qualified leads | Stage-history rows to `qualified` with actor = user in the day |
| D12 | Hot leads | Open leads owned as of that time whose priority was `hot` (reconstructed) |
| D13 | Converted leads | Leads **still converted** whose **first** conversion falls in the day, credited to the owner at that instant (DB2, :119-133) |

- Table 2, KPI | "Achieved / target", 6 rows. A missing target reads "not set" (`progressText`). The KPIs map to counts as follows (`telecaller_metrics.py:41`): Calls → D2, Connected calls → D3, Qualified leads → D11, Follow-ups → D5, Counselling appointments → D8, Conversions → D13. The targets are the ones in effect **on that day** (T28).
- Decision: DEC-SCOPE-105 (tel-021).

---

## 2. Leads (manager view)

### 2.1 Team leads: `/telecaller/manager/leads`
- Frontend: `web/components/TelecallerLeadPages.tsx:44-66` with the table `web/components/TelecallerLeadTable.tsx:30-166` (`showTelecaller` = true).
- API: `GET /telecaller/leads?status&priority&product_id&campaign_id&follow_up&q&limit&offset` at `api/api/telecaller.py:100-122`, newest first. Every filter is ANDed with the manager scope (§0.3).

| Element | Literal text |
|---|---|
| Eyebrow / H2 / intro | "Leads" / "Team leads" / "Leads of the telecallers who report to you, and your teams' unassigned leads." |
| Button | **New lead** (to `/telecaller/manager/leads/new`) |
| Search | label "Search leads", hint "Lead ID, name, phone, WhatsApp or email", max 200; **Search**, **Clear search** |
| Filters | Stage ("All stages" + 16 stages), Priority ("All priorities", Hot/Warm/Cold), Product ("All products", grouped IT Courses / Overseas Education / Other), Campaign ("All campaigns"), Due follow-up ("Any", "Due today", "Overdue") |
| Columns | Name (link), Lead ID, Mobile, Interest (product name, else subject), Stage (+ "With counselor" when handed over), Priority, **Telecaller** ("Unassigned" if none), Lead date |
| Empty | filtered: "No leads match these filters."; unfiltered: "No leads in your team yet." |
| Error | "Unable to load leads." + Retry |

Stages (`web/lib/leadStages.ts:4-23`). Open: New Lead, Assigned, First Call Pending, Contacted, Qualified, Interested, Follow-up, Counselling Scheduled, Counselling Completed, Application/Enrollment, Converted. Closed: Not Interested, Not Eligible, Wrong Number, No Response, Lost.
Priorities: Hot "Ready to join / immediate requirement.", Warm "Interested but needs follow-up.", Cold "Long-term / low interest." (`web/lib/telecallerLeads.ts:341-345`). DEC-SCOPE-084 (tel-008).

### 2.2 New lead: `/telecaller/manager/leads/new`
- Frontend: `TelecallerLeadPages.tsx:93-114` and `web/components/NewLeadForm.tsx`. This form is shared with the telecaller; full field detail belongs in the telecaller discovery file.
- Manager intro: "The lead goes to your team's telecallers by your distribution rules, or waits in the unassigned queue. We check the mobile number and email against every lead first, so a person is never entered twice."
- Fields (`NewLeadForm.tsx:17-27, 205-260`): Student name * (160), Mobile number * (40), Email (255), WhatsApp number (40), City (120), State (120), Qualification (120), Passing year (1950-2100), College/University (200), Product interest *, Division * (only when the product has no team; options "Choose the team", IT, Overseas), Campaign (filtered to the product: "No campaign" / "Choose a product first"), Lead source *, Priority, Enquiry subject (180, placeholder = product name or "Defaults to the product"), Notes (5000). Buttons: **Create lead** ("Creating…"), **Cancel**.
- API: `POST /telecaller/leads` at `api/api/telecaller.py:138-148` and `api/services/lead_intake.py:100-140`. **A manager's lead is never assigned to the manager.** `assigned = user.role == "telecaller"`; otherwise the lead goes through `lead_distribution.on_intake` (I6). If no rule or telecaller matches, it waits in the team's unassigned queue (`lead_intake.py:127-135`).
- After create: if the lead is in the manager's scope, the page opens it. If distribution gave it to someone outside the manager's reports (`in_scope=false`), the form clears and says "Lead {code} created and assigned to {name}." (`NewLeadForm.tsx:183-188`).
- Duplicate (409 `duplicate_lead`): the panel heading is "⚠️ Lead already exists." with Existing telecaller, Counselor, Last contact, Current status, "Previous enquiries", **Add enquiry to this lead**, and **Open lead** (only when `in_scope`). Notice: "This person is already a lead. Add the enquiry to the existing lead instead." DEC-SCOPE-088 (tel-005).
- Server errors seen here: "Choose the division (IT or Overseas) for this product", "{product} belongs to the {Team} team", "This campaign is for another product", "This campaign belongs to another lead source", "Choose an active campaign" (`lead_intake.py:91-115`).
- [OVS] When an Overseas product is chosen, the team is fixed to Overseas. The Division picker appears only for an Other product with no team (seeded: "Career Guidance", "General Enquiry").

### 2.3 Manager lead detail: `/telecaller/manager/leads/[id]`
- Frontend: `TelecallerLeadPages.tsx:117-142` with `web/components/LeadDetailPanel.tsx:150-324` and `canReopen={true}`, which marks the manager's page.
- Not found (404 or a malformed id): "Lead not found" / "This lead does not exist, or it is not in your leads."
- APIs (all scope-checked by `lead_pipeline.scope`): `GET /telecaller/leads/{id}` (:160), `PATCH /telecaller/leads/{id}` (:167), `GET …/timeline` (:179), `GET/PUT …/qualification` (:188/:199), `POST …/stage` (:212), `GET …/stage-history` (:226), and the call, follow-up and message reads.

What a manager can and cannot do on the detail page:
| Capability | Manager | Evidence |
|---|---|---|
| Header: Lead ID, name, "Stage: … · Priority: …". If a counselor holds the lead: "This lead is with the counselor, {name}." (no read-only suffix for a manager) | yes | `LeadDetailPanel.tsx:197-209` |
| **Call** (a `tel:` link) | yes, opens the dialer, but the call log form stays closed (`canWrite=false`). **VERIFICATION REQUIRED**: what the Call button does on the manager page | `:213`, `:257` |
| **WhatsApp** / **Email** composers | **hidden** (`telecallerWrites` false for a manager) | `:165`, `:215-221` |
| **Change stage** (Qualified / Interested / Follow-up / closed outcomes; "Reason (required)" for closing) | yes | `:223-228`, `web/components/AdminLeadStage.tsx` |
| **Reopen a closed lead**, only to Follow-up, with a reason | **manager only** (a telecaller gets 403 "Only a manager can reopen a closed lead") | `web/lib/leadStages.ts:38-43`, `api/services/lead_pipeline.py:86-96` |
| **Assign to counselor** / **Change counselor** (before Application/Enrollment, not closed). Hint: "The counselor takes over the lead. You keep read access and its open follow-ups are cancelled." | yes | `:168`, `web/components/LeadHandoverForm.tsx:51-76` (tel-018, DEC-SCOPE-101) |
| Priority radio + **Save priority** ("Priority updated.") | yes | `:241-262` |
| **Edit details** ("Details saved.") | yes | `:276-296` |
| Qualification form (IT or Overseas requirement sections by product group) | yes, editable | `:300`, `web/lib/telecallerLeads.ts:378-407` |
| Calls list | read only | `:257` |
| Follow-ups list | read only (`can_change` is true only for the telecaller) | `:263`, `api/services/lead_follow_ups.py:59-60` |
| Book counselling appointment | **hidden** (`canBook = !canReopen`) | `:304` |
| Call script panel, Milestones, Enquiry, Activity timeline | read | `:266-322` |

Stage errors (literal, `lead_pipeline.py:21-30`): "Choose a stage of the lead pipeline", "The lead is already at this stage", "This stage is set by the system", "The lead is with the counselor; its stage moves with the application", "A closed lead can only be reopened to Follow-up", "Add a reason for closing the lead", "Add a reason for reopening the lead". Closing a lead cancels its open follow-ups and its open counselling appointment (reason "Lead closed"). DEC-SCOPE-081 (tel-004).

---

## 3. Follow-ups: `/telecaller/manager/follow-ups` (read only)
- Frontend: `TelecallerLeadPages.tsx:69-90` and `web/components/TodayFollowUps.tsx:17-116` (`showTelecaller`).
- API: `GET /telecaller/follow-ups?view=day|overdue&day&limit&offset` at `api/api/telecaller_follow_ups.py:27-40` and `api/services/lead_follow_ups.py:104-113`. Scope = the manager's lead scope. Both lists are oldest due first. Tab counts come from the same scope.
- UI: eyebrow "Follow-ups". H2 "Team follow-ups". Intro: "Follow-ups on the leads of the telecallers who report to you. Times are India time (IST)." Tabs: "Today (n)" (or the chosen date) and "Overdue (n)". **Day** date input and **Back to today**.
- Empty: "No follow-ups due on this day." / "No overdue follow-ups." Error: "Unable to load follow-ups." + Retry.
- The manager has no write actions. The API refuses writes with 403 "Only the lead's telecaller can change its follow-ups" (`lead_follow_ups.py:30,136-138`). The card layout (`FollowUpItem`, with the telecaller name shown) is **VERIFICATION REQUIRED** in the browser. DEC-SCOPE-094 (tel-011, F2).

---

## 4. Lead assignment: `/telecaller/manager/assignment`
- Frontend: `web/app/telecaller/manager/assignment/page.tsx` and `web/components/TelecallerAssignmentPanel.tsx:21-241`. Header: eyebrow "Leads", H2 "Lead assignment", intro "Assign waiting leads to your telecallers, or move leads between them."
- Tabs (URL `?view=assigned`): **Unassigned** and **Assigned to my team**.

| Element | Literal text |
|---|---|
| Tab hint (Unassigned) | "Leads no rule or available telecaller could take, oldest first. Assign them to someone on their team." |
| Tab hint (Assigned) | "Leads of the telecallers who report to you, newest first. Reassigning keeps the lead's stage." |
| Filters | Team ("Both teams", IT, Overseas). On the Assigned tab, also Telecaller ("All my telecallers", names with " (inactive)") |
| Search | placeholder "Lead ID, name or city", max 200; Search, Clear search |
| Action group | "Assign to" select ("Choose a telecaller", options "{name} ({Team})", active reports only) + button "Assign selected" / "Assign {n} selected" / "Assigning…" ("Reassign…" on the Assigned tab) |
| Columns | checkbox ("Select all leads on this page"), Lead ID, Name, Team, City, Product, Stage, Telecaller (Assigned tab, "Inactive" badge), Received (date+time) |
| Client errors | "Choose a telecaller.", "Choose leads from one team.", "{name} is on the {Team} team; choose leads from that team." |
| Success | "Assigned {n} lead(s) to {name}." / "…; {m} already with them." |
| Empty | "No unassigned leads. New leads with no matching rule or available telecaller appear here." / "No unassigned leads on the {Team} team." / "No leads are assigned to your telecallers yet." / "No leads are assigned to {name}…" / "No leads match “{q}”." |
| Other | "No active telecaller reports to you, so leads can't be assigned from here."; "Unable to load your telecallers." + **Retry loading telecallers** |

APIs (`api/api/telecaller_distribution.py`):
| Method/path | Line | Rule |
|---|---|---|
| GET `/telecaller/leads/unassigned?team&q` | :182-192 | `telecaller_user_id IS NULL` and division in the manager's reports' teams; oldest first; q = Lead ID, name, city |
| GET `/telecaller/leads/assigned?telecaller_user_id&team&q` | :195-210 | leads of direct reports, newest first; a foreign telecaller id gives 404 "Telecaller not found" |
| POST `/telecaller/leads/assign` `{lead_ids[1..100], telecaller_user_id}` | :213-230 | all or nothing; leads must be in scope (404 "Lead not found"); one team only (422 "Choose leads from one team"); the target is checked by `assignee` |
| GET `/telecaller/manager/team?limit=100…` | `api/api/telecaller.py:92` | the picker source (all pages, `web/lib/telecallerDistribution.ts:271-278`) |

`assignee` (`api/services/lead_distribution.py:106-122`) errors: 422 "Choose an active telecaller", **403 "You can only assign leads to your direct reports"**, 422 "This telecaller is inactive", 422 "{name} is on the {Team} team". The schema caps one request at 100 distinct leads (`api/schemas.py:6225-6236`). Each changed lead gets a `lead.assign` audit row (method `manual`), and the new telecaller gets the "New lead assigned" alert. DEC-SCOPE-087 (tel-007, DI4).
[OVS] An Overseas-only manager's Unassigned tab holds only Overseas leads. The Team filter still offers IT, which simply yields an empty list.

---

## 5. Distribution rules: `/telecaller/manager/distribution`
- Frontend: `web/app/telecaller/manager/distribution/page.tsx`, `web/components/TelecallerRulesPanel.tsx:20-186`, `web/components/TelecallerRuleRow.tsx:11-94`. Header: eyebrow "Settings", H2 "Distribution rules", intro "Send new leads for a product or a city straight to one of your telecallers. Every other lead goes round robin among the team's active telecallers."
- **Create rule** form: Team (required, IT/Overseas, **defaults to IT** [OVS]), Rule type (required: Product / City), Product (required, active products of that team, "Choose a product") **or** City (required, max 120, placeholder "e.g. Hyderabad"), Telecaller (required, active direct reports on that team). Button **Create rule** ("Creating…"). Success: "Created Product: {name}." / "Created City: {city}." With no eligible report: "No active telecaller on the {Team} team reports to you." (button disabled).
- **Rules** list. Explainer: "A new lead goes to the telecaller of its product rule, else of its city rule, else to the next active telecaller of its team in turn. If nobody is available it waits in the unassigned queue. A rule whose telecaller is inactive is skipped." Filter "Show" (Both teams / IT team / Overseas team). Columns: Rule ("Product: X", "(inactive)" suffix, or "City: X"), Team, Telecaller (badge "Inactive — skipped"), Actions.
- Row actions (own reports' rules only): **Change telecaller** (select "New telecaller for {rule}", Save/Cancel; notice "{rule} now goes to {name}.") and **Delete**, which confirms with "New leads stop following this rule; leads already assigned keep their telecaller." + **Confirm delete** / **Keep rule** (notice "Deleted {rule}."). Another manager's rule reads "Another manager's report".
- Empty: "No rules yet. Every new lead goes round robin until you add one." / "No rules for the {Team} team."

APIs (`api/api/telecaller_distribution.py`):
| Method/path | Line | Rule / literal errors |
|---|---|---|
| GET `/telecaller/distribution-rules?team&kind&telecaller_user_id` | :99-117 | every rule of both teams; `editable` = the rule's telecaller reports to the caller |
| POST `/telecaller/distribution-rules` | :120-132 | "Choose a product", "A product rule has no city", "Choose an active product", "This product has no team: its leads wait in the unassigned queue", "This product belongs to the {Team} team", "A city rule has no product", "Enter a city"; 409 "This team already has a rule for this product/city"; plus the `assignee` errors (§4) |
| PATCH `/telecaller/distribution-rules/{id}` `{telecaller_user_id}` | :135-146 | only the telecaller changes (D6); 404 "Rule not found"; 403 "You can only change rules for your direct reports" |
| DELETE `/telecaller/distribution-rules/{id}` | :149-156 | same 404/403 |

Engine (`api/services/lead_distribution.py:53-67`): if the lead's division is not IT or Overseas, the lead goes to the queue. If the product has no team, it goes to the queue (T18). Otherwise the order is: **product rule**, then **city rule** (case-insensitive, trimmed), then **round robin** over the team's active telecallers in id order with a per-team cursor (`TelRoundRobinCursor`). If nobody qualifies, the lead stays unassigned. A rule whose telecaller is inactive is skipped. Round robin runs across the **whole team**, not just one manager's reports (`_eligible_ids`, :25-28). Distribution runs on website, BDM, manager-entered and imported leads, inside a savepoint. DEC-SCOPE-087 (tel-007, DI3).

---

## 6. Lead import: `/telecaller/manager/imports`
- Frontend: `web/app/telecaller/manager/imports/page.tsx`, `web/components/TelecallerLeadImports.tsx`, `TelecallerLeadImportPanel.tsx`, `TelecallerImportHistory.tsx`, `web/lib/telecallerImport.ts`. Header: eyebrow "Leads", H2 "Lead import", intro "Upload a CSV of leads for one campaign. Each row is checked for duplicates: a known person gets the enquiry added to their lead, and new leads are distributed to your team."
- Card **Import leads (CSV)** (`TelecallerLeadImportPanel.tsx:127`). Intro: "Add the leads from an ad platform or an event in one go. A person who is already a lead gets this enquiry added to their lead instead of a duplicate; new leads are distributed like any other."
  1. "1. Choose the campaign": select **Campaign** ("Choose a campaign"; options "{name} — {Source} → {Product}"; active campaigns only). Help: "Every lead in the file gets this campaign, its source and its product. Only active campaigns are listed." **Division** appears only for an Other product (options "The product's team", IT, Overseas; help "Needed only when this product has no team.").
  2. "2. Download the template": **Download the template (.csv)** plus a column reference table (`BulkColumnReference`).
  3. "3. Upload the filled-in file": **Filled-in leads file** (`.csv`). Help: "CSV, up to 1 MB and 500 leads. One lead per row; name and phone are required." Button **Import leads** ("Importing…").
- Client prechecks (`:16-22`): "Choose a campaign first.", "Choose a filled-in CSV file first.", "Choose a .csv file.", "The file is larger than 1 MB." Network error: "The connection dropped. Import again — the same file won't be added twice."
- **Import result** table: Row, Result ("Created" / "Added to existing lead" / "Rejected"), Lead ID, Detail (the error). Summary: all rejected → "No leads were imported. Fix the rows below and upload again."; none rejected → "{c} created, {a} added to existing leads, {r} rejected."; mixed → "…. Fix the rejected rows and upload just those."
- **Past imports**: columns When, Campaign, Team, Uploaded by, Rows, Result. Empty "No imports yet." Error "Past imports could not be loaded." + Retry. The list shows the **last 50 of the manager's own imports** (`?limit=50`).

CSV template columns, in order (`api/schemas.py:6081-6096`, `web/lib/telecallerImport.ts:12-25`):
| Column | Req | Format |
|---|---|---|
| name | yes | Text, up to 160 characters |
| phone | yes | A valid mobile; 10 digits get +91 |
| email | no | An email address |
| whatsapp_number | no | Up to 40 characters |
| city / state / qualification | no | Text, up to 120 characters |
| passing_year | no | Year from 1950 to 2100 |
| institution | no | Text, up to 200 characters |
| priority | no | hot, warm or cold (default warm) |
| subject | no | Up to 180 characters (default: the campaign's product) |
| message | no | Notes, up to 5000 characters |

APIs (`api/api/telecaller_import.py`):
| Method/path | Line | Notes |
|---|---|---|
| GET `/telecaller/imports/template` | :134-140 | header-only CSV `lead-import-template.csv` |
| POST `/telecaller/imports` (multipart `file`, `campaign_id`, optional `division`; header `Idempotency-Key`) | :143-180 | 201 with the per-row report |
| GET `/telecaller/imports?limit&offset` | :183-196 | own imports (super_admin: all), newest first |
| GET `/telecaller/imports/{batch_id}` | :199-204 | 404 "Import not found" (no UI calls it; **VERIFICATION REQUIRED**) |

Server rules:
- **File level** (422 before any row; `api/api/school_bulk.py`, shared ENH-028 parser): "Idempotency-Key header is required"; "The file is larger than 1 MB" (413); "The file must be a UTF-8 CSV"; "Duplicate column: …"; "Unknown column: …"; "Missing required column: name|phone"; "The file has no filled-in rows"; "The file has more than 500 filled-in rows".
- **Campaign**: "Choose an active campaign"; "Choose an active product". The team is the product's team, or the chosen division for a no-team Other product.
- **Per row**: validation errors become the row's Detail. A known person (same phone or email, any lead, earlier rows of the same file included) becomes "attached": a `LeadEnquiry` is added to their newest lead and the stage does not move. Anyone else becomes a new lead with the campaign's source, product and campaign, distributed on arrival (`api/services/lead_intake.py:178-197`). A lock or deadlock conflict gives "This row conflicts with a change made at the same time; upload it again".
- Concurrency and idempotency: imports run one at a time (advisory lock); a busy server gives 409 "This upload is still being processed; retry shortly". Repeating the same key with the same file, campaign and division replays the first report. Reusing the key with a different file gives 422 "Idempotency-Key was already used for a different file". The batch stores counts and outcomes only, never the file. Audit action `lead.import`. DEC-SCOPE-091 (tel-006, IM1).
- [OVS] Choosing an Overseas campaign sends every created lead to the Overseas team. History is per uploader, so two Overseas managers do not see each other's imports.

---

## 7. Targets: `/telecaller/manager/targets`
- Frontend: `web/app/telecaller/manager/targets/page.tsx`, `web/components/TelecallerTargetsPanel.tsx:31-281`, `web/lib/telecallerTargets.ts`. Header: eyebrow "Settings", H2 "Targets", intro "Set daily and monthly targets for each team, and override them for your telecallers. A change starts tomorrow or next month at the earliest, so today's and past results keep the targets they had."
- Card **Whose targets**: "Set targets for" with options "IT team default" / "Overseas team default" / "A telecaller (override)". The URL is `?for=it|overseas|user|<uuid>`, and the **default is IT** [OVS]. For an override, the "Telecaller (required)" searchable picker lists active direct reports ("{Team} · {Employee ID}"). "In effect on" date input. Empty: "Choose a telecaller to see and set their targets."
- Table "In effect on {date}" (for a telecaller: "— an override replaces the team default"), with columns KPI | "Today (daily)" or the date | "{Month YYYY} (monthly)". Values show "Not set". A telecaller's values also show "(Override)" or "(Team default)".
- Form **Set new targets**: Period radio (Daily / Monthly). "Starts on" is a date (min = tomorrow, IST) for Daily, or a select of the next 12 months for Monthly. Hint: "Changes never apply to today or this month; past results keep their targets." Six number inputs "{KPI} target" (0-100000, placeholder "Unchanged"), plus a "Use team default" checkbox per KPI for an override. Hint: "Leave a KPI blank to keep its current target." Button **Save targets** ("Saving…"). Success: "Saved {n} target(s) from {date}." Client errors: "Choose a start date.", "{KPI} must be a whole number from 0 to 100000."
- **History** table: Starts, Period, KPI, Target ("Team default" for a removed override), Set by. Empty "No targets set yet." 50 per page.
- KPIs (`telecallerTargets.ts:23-30`): Calls, Connected calls, Qualified leads, Follow-ups, Counselling appointments, Conversions.

APIs (`api/api/telecaller_targets.py`):
| Method/path | Line | Rule |
|---|---|---|
| POST `/telecaller/targets` `{scope, team|user_id, period, effective_from, values}` | :33-48 | idempotent upsert per KPI (200); null removes an override from that date |
| GET `/telecaller/targets?scope&team&user_id&period&kpi` | :51-94 | history, newest start first: every team row plus the manager's reports' rows |
| GET `/telecaller/targets/effective?user_id|team&date` | :97-120 | exactly one of user or team (422 "Choose either a telecaller or a team") |

Errors (`api/services/telecaller_targets.py:32-68`, `api/schemas.py:5729-`): "A monthly target starts on the 1st of a month", "{Daily|Monthly} targets can start on {dd Mon yyyy} or later", "Choose a team", "A team default cannot name a telecaller", "A team default cannot be removed; enter a number", "Choose a telecaller", "A telecaller override cannot name a team", 422 "This telecaller is inactive", 404 "Telecaller not found" (not a report), "Values: enter at least one target", "Values: unknown KPI …". Resolution: a non-null override beats the team default; a null or missing override falls back to the team value in effect (`effective_targets`). DEC-SCOPE-080 (tel-022, G1-G3).
[OVS] An Overseas manager **can also save the IT team default**. The API does not restrict team defaults by manager (§0.4).

---

## 8. Alert settings: `/telecaller/manager/alerts`
- Frontend: `web/app/telecaller/manager/alerts/page.tsx` and `web/components/TelecallerAlertSettingsPanel.tsx:7-99`. Header: eyebrow "Settings", H2 "Alert settings", intro "Choose when telecallers are alerted about leads that are waiting. Each team has its own thresholds, in whole hours. Follow-up, appointment, assignment and return alerts are always on."
- There is one card per team ("IT team", "Overseas team"). Fields: "Lead not contacted after (hours)" (hint "Alert when a lead is still waiting for its first connected call. 1–168.") and "Hot lead pending after (hours)" (hint "Alert when a hot lead has had no call for this long. 1–168."). Footer: "Last changed by {name} on {date time} IST." or "Default thresholds (never changed)." Button **Save** (aria "Save {Team} thresholds"). Success: "Saved. Alerts use the new thresholds from the next check (within 15 minutes)." Load error: "Could not load the alert settings." + **Try again**.
- APIs: `GET /telecaller/settings` (:27-31) and `PUT /telecaller/settings/{team}` (:34-50), a replace with audit `tel.settings.update`. Validation: integers 1-168 (`api/schemas.py:5811`); unknown team gives 404 "Team not found". Defaults: not contacted **24 h**, hot pending **4 h** (`api/models.py:2853`).
- The 9 alert types (`api/services/telecaller_alerts.py:50-60`) go to the **lead's telecaller only**, as an in-app notice plus email. The beat runs every 900 s (`api/worker.py:223`):

| Kind (title) | Trigger |
|---|---|
| New lead assigned | event, on assignment (not to the actor themselves) |
| Follow-up due | open follow-up due within the next 15 min |
| Missed follow-up | still open 1 h after due (24 h lookback) |
| Appointment tomorrow | from 18:00 IST the day before |
| Appointment in 1 hour | 1 h before |
| Lead not contacted | lead in Assigned / First Call Pending longer than the team's hours (default 24) |
| Hot lead pending | hot lead with no call (since the latest call, else creation) longer than the team's hours (default 4) |
| Counselor appointment completed | event |
| Lead returned for follow-up | event |

Also, the Lead Not Contacted hours feed the telecaller dashboard's **Overdue** tile (`telecaller_metrics.py:227-253`). DEC-SCOPE-111 (tel-020, AL1/AL11/AL12). [OVS] Any manager can change the IT card too (§0.4).

---

## 9. Performance: `/telecaller/manager/performance`
- Frontend: `web/app/telecaller/manager/performance/page.tsx`, `web/components/TelecallerPerformancePage.tsx:16-55`, `TelecallerPerformancePanel.tsx:14-102`, `web/lib/telecallerPerformance.ts`. Header: eyebrow "Performance", H2 "Compare telecallers", intro "Leads received, calls, connected calls, qualified leads, appointments and conversions for each telecaller over a date range (up to 366 days)."
- Card "Telecaller performance": GET form with From and To (date, max today), Team ("All teams", IT, Overseas; always shown for a manager [OVS]) and **Show**. Columns are sortable header links (arrow ↑ ↓ ↕; aria "{label}: sort highest first / A to Z…"): Telecaller (name links to `/telecaller/manager/team/{id}/activity?date={date_to}`, plus an "Inactive" badge), Team, Leads, Calls, Connected, Qualified, Appointments, Conversions. Footer row **Total**. Button **Download CSV** ("Preparing CSV…"), filename `telecaller-performance-{from}-to-{to}.csv`. Empty: "No telecallers in your scope yet." Generic error: "Telecaller performance is unavailable right now."
- APIs: `GET /telecaller/manager/performance` (`api/api/telecaller_dashboard.py:105-109`) and `GET /telecaller/manager/performance.csv` (:91-102, audit `telecaller_performance.export`). Parameters `date_from, date_to, team, sort (name|leads|calls|connected|qualified|appointments|conversions, default calls), dir (default desc)`.
- Rules (`api/services/telecaller_performance.py`): the scope is the manager's direct reports with role `telecaller`; `team` only narrows (:31-38). The default range is the 1st of the month to today. Range errors: "The start date must not be after the end date", "The range can't end in the future", "The range can't be longer than 366 days" (:41-51).
- Metric definitions (:18-26): **Leads** = distinct leads that *became* the telecaller's in the range (a `lead.assign` to them, or a lead they created already assigned), kept or since reassigned (P1, `telecaller_metrics.py:213-224`). Calls = D2. Connected = D3. Qualified = D11. Appointments = D7 (counsellor + BDM). Conversions = D13, all summed over the range.
- The CSV includes an extra **Status** column ("Active" or "Inactive") that the screen does not show (`COLUMNS`, :20-24). DEC-SCOPE-112 (tel-023).

---

## 10. Reports: `/telecaller/manager/reports?report=source|product|telecaller|handover|campaign`
- Frontend: `web/app/telecaller/manager/reports/page.tsx`, `web/components/TelecallerReportsPage.tsx:14-52`, `TelecallerReportView.tsx:16-86`, `web/lib/telecallerReports.ts`. Header: eyebrow "Telecaller CRM", H2 "Reports", intro "Lead source, course, telecaller, counselor handover and campaign figures for a date range. Lead reports count leads created in the range; a lead counts in every stage it has reached. The Telecaller report counts the activity logged in the range."
- Report links (tabs): **Lead Source, Course, Telecaller, Counselor Handover, Campaign**. H3 "{Tab} Report". Filter form: From, To, Team (only when more than one team is in scope; "All teams"), Course ("All courses"), Campaign ("All campaigns"), Source ("All sources"). The last three appear only on the lead reports. Buttons **Apply** and **Clear filters**. **Download CSV**, filename `telecaller-{kind}-{from}-to-{to}.csv`.
- Empty: "No leads in this range." / Telecaller: "No telecallers in your scope." / Handover: "No leads with a counselor in this range." Error: "This report is unavailable right now. Please try again."
- APIs: `GET /telecaller/reports/{kind}` (`api/api/telecaller_reports.py:66-77`) and `GET /telecaller/reports/{kind}.csv` (:48-63, audit `telecaller_report.export`). An unknown kind gives 404 "Report not found". The allowed roles are manager, super_admin, it_admin and overseas_admin.

| Report | Columns (`api/services/telecaller_reports.py:33-53`) | Basis |
|---|---|---|
| Lead Source | Source, Leads, Connected, Qualified, Counselling, Enrolled | leads **created** in range in the manager's lead scope; a column counts if the lead ever reached that stage (Connected=contacted, Counselling=counselling_scheduled); Enrolled = **currently** converted |
| Course | Course ("No product"), same funnel | same |
| Telecaller | Telecaller (" (inactive)" suffix), Calls, Connected, Qualified, Appointments, Conversions | activity in range by direct reports (`flow_counts_by_user`) |
| Counselor Handover | Telecaller ("Unassigned"), Counselor, Handed over, Counselling done, Enrolled | created leads with a counselor (`owner_id`) |
| Campaign | Campaign ("No campaign"), same funnel | same |

Rows are sorted by the first count descending, then by name. A **Total** row follows. Defaults: the 1st of the month to today; at most 366 days. Errors: "'From' is not a valid date", "'From' must be on or before 'To'", "Choose a range of at most 366 days", "Choose a team from the list", "Choose a source from the list", "Choose a course from the list", "Choose a campaign from the list" (:72-105). Unlike Performance, **a future To date is not refused**. Picker options are products and campaigns of the manager's reports' teams plus no-team products, inactive ones included (:132-145). DEC-SCOPE-109 (tel-024).
[OVS] For an Overseas-only manager, `options.teams == ["overseas"]`, so the Team picker is hidden and Course and Campaign list only Overseas and no-team items.

---

## 11. Products: `/telecaller/manager/products`
- Frontend: `web/components/TelecallerProductsPanel.tsx:17-166` and `TelecallerProductRow.tsx:11-127`. Header: eyebrow "Settings", H2 "Products", intro "The interests a telecaller can choose for a lead. IT and Overseas products go to their own team; choose the team for each Other product. Deactivate a product to hide it from pickers — leads and campaigns that use it keep it."
- **Create product**: Group (required: IT Courses / Overseas Education / Other), Name (required, 120). For Other: Team ("Unassigned queue" / IT / Overseas). Otherwise the hint reads "IT products route to the IT team." or "Overseas products route to the Overseas team." For IT only: "Linked IT course" ("No linked course" + public programs). Button **Create product**. Success "Created {name}."
- List **Products**: "Show" filter (All groups / 3 groups), columns Name, Group, Team ("IT" / "Overseas" / "Unassigned queue"), Course ("—"), Order, Status, Actions (Edit, Deactivate, Reactivate). The edit form shows "Group … (cannot be changed)", Product name, Product team (Other only), Product course link (IT only), and Order (0-9999, required). Deactivate hint: "It disappears from pickers; leads and campaigns that already use it keep it." Empty: "No products yet." / "No products in this group yet."
- APIs: `GET /telecaller/products` (`api/api/telecaller_catalogue.py:69-85`; managers see inactive rows too; order IT, Overseas, Other, then sort order, then name), `POST` (:88-105), `PATCH /{id}` (:108-126). Errors: "IT products always route to the IT team", "Overseas products always route to the Overseas team", "Only IT products can link to a course", "Choose an active course", 409 "A product named “X” already exists in this group", "Group cannot be changed", 404 "Product not found".
- Seed (migration `0076_tel_catalogue.py`, 18 values per DEC-SCOPE-074). Overseas products: UK, USA, Canada, Australia, New Zealand, Germany, Japan, South Korea, Dubai. Other: Career Guidance (no team), Job Assistance (it), Career Change (it), General Enquiry (no team). DEC-SCOPE-074 (tel-002).

## 12. Campaigns: `/telecaller/manager/campaigns`
- Frontend: `web/components/TelecallerCampaignsPanel.tsx:20-176` and `TelecallerCampaignRow.tsx:12-125`. Intro: "Each campaign names its source and product, for example Instagram → Cyber Security → September 2026. Deactivate a campaign to hide it from pickers — leads that use it keep it."
- **Create campaign**: Campaign name (required, 160, placeholder "e.g. Sep 2026 Cyber Security"), Source (required, 13 options: Instagram, Facebook, Google, Website, WhatsApp, Walk-in, College, School, Agent, Referral, Exhibition/Event, BDM, Other), Product (required, active, grouped), Start date (required), End date. Client and server error: "End date cannot be before the start date". With no products: "No active product — add or reactivate one on the Products page first."
- List: search "Campaign name" (Search / Clear search), columns Name, Source, Product ("Product inactive" badge), Dates ("d MMM yyyy – d MMM yyyy" or "From …"), Status, Actions. Empty: "No campaigns yet. Use the Create campaign form to add the first one." / "No campaigns match “q”."
- APIs: `GET /telecaller/campaigns` (:130-150; active first, newest start), `POST` (:158-170), `PATCH /{id}` (:173-190). Errors: 409 "A campaign named “X” already exists", "Choose an active product", 404 "Campaign not found". DEC-SCOPE-074.

## 13. Content library (scripts, templates, brochures). DEC-SCOPE-083 (tel-012)
All three use `TelecallerContentList` (`web/components/TelecallerContentList.tsx`) with the empty texts "No {noun} yet." / "No {noun} match this filter." and the row lifecycle in `TelecallerLibraryRow.tsx`. Reads allow telecaller, manager and super_admin (`api/services/telecaller_content.py:29,48-50`). Writes are manager-only.

### 13.1 Call scripts: `/telecaller/manager/scripts`
- Intro: "The standard steps a telecaller follows on a call, one active script per product. Deactivate a script to hide it from telecallers."
- **Create script** ("Each product has one active script: the standard steps every telecaller follows on a call."): Product (required), Script name (required, 160), then "Steps (required, in order)". Each step has "Step n title" (120, required) and "Step n talking points" (1000), with buttons **Up**, **Down**, **Remove** and **Add step**. The limit is 20 steps ("A script has at most 20 steps.").
- List: Product filter; columns Name, Product, Steps (ordered list, "title — notes"), Status. Deactivate hint: "Telecallers stop seeing it. Another script can then become this product's standard."
- APIs: `GET/POST /telecaller/scripts`, `PATCH /telecaller/scripts/{id}` (`api/api/telecaller_content.py:69-120`). Errors: 409 "{product} already has an active script. Deactivate it first."; "Add between 1 and 20 steps" (`api/schemas.py:5184-5187`).

### 13.2 Message templates: `/telecaller/manager/templates`
- Intro: "WhatsApp and email messages telecallers start from. They can edit the text before sending. Use placeholders for the lead's details; attach a brochure to use {brochure_link}."
- Fields (`TelecallerTemplateFields.tsx`): Channel (required, WhatsApp/Email; once saved shows "(cannot be changed)"), Kind (required; WhatsApp: Welcome message, Course details, Brochure, Fee details, Counselling appointment, Reminder, Follow-up, Overseas destination information, Document request; Email: Course brochure, Fee proposal, Counselling confirmation, Overseas information, University information, Follow-up, Appointment confirmation), Template name (required, 160), Product ("Any product"), Brochure ("No brochure"), Subject (required, 200, email only), Message (required; WhatsApp 1000 / email 5000; live counter "n / max"). Hint: "Placeholders: {name}, {product}, {brochure_link} (needs a brochure), {appointment_time}." Warning: "Unknown placeholder: …".
- List: "Show" (All channels / WhatsApp / Email); columns Name, Channel, Kind, Product ("Any"), Brochure ("(inactive)"), Status; **Preview** / **Hide preview** shows "Sample values: Priya Sharma, the template's product (or Cyber Security), Mon 14 Sept 2026, 10:30 AM.", the subject and body, and "The brochure link works until …". An inactive brochure warns "{name} is inactive, so {brochure_link} is left empty…". Deactivate hint: "It disappears from the telecallers' pickers; messages already sent keep its name."
- APIs: `GET/POST /telecaller/templates`, `PATCH /{id}`, `GET /{id}/preview` (`api/api/telecaller_content.py:133-211`). Errors: "Unknown placeholder {x}. Use {name}, {product}, {brochure_link} or {appointment_time}", "Choose a WhatsApp/an email template kind", "Only email templates have a subject", "Subject is required", "A WhatsApp/An email message must be at most N characters", "Attach a brochure to use {brochure_link}", "Choose an active brochure", "Channel cannot be changed", 409 "A WhatsApp/email template named “X” already exists".
- [OVS] Overseas-relevant kinds: "Overseas destination information" (WhatsApp) and "Overseas information" / "University information" (email).

### 13.3 Brochures: `/telecaller/manager/brochures`
- Intro: "PDF brochures and fee sheets. A lead opens one from a link that works without signing in for 7 days. Deactivating a brochure stops all of its links at once."
- **Upload brochure**: Brochure name (required, 160), Kind (Brochure / Fee sheet), Product ("Any product"), PDF file (required; hint "PDF only. Leads open it from a link that works for 7 days."). Button **Upload brochure**. Client errors: "Choose a PDF file" / "Upload a PDF file". Success "Uploaded {name}."
- List: "Show" (All kinds / Brochure / Fee sheet); columns Name, Kind, Product, File ("file.pdf (n KB)"), Uploaded, Status. **Copy link** creates a fresh signed 7-day link and shows "Link copied for {name}. It works until …". If the clipboard fails, a read-only field "Link for {name}" appears. Error: "Unable to create a link. Try again." The edit form says "To change the file, upload a new brochure and deactivate this one." Deactivate hint: "Every link already sent stops working at once. Templates that use it stop offering a link."
- APIs: `GET/POST /telecaller/assets`, `PATCH /{id}`, `POST /{id}/link`, public `GET /public/telecaller-assets/{token}` (`api/api/telecaller_content.py:214-298`). Errors: "The file is empty", 413 "The file must be at most {N} MB" (`settings.max_upload_bytes`, default 20 MB, `api/core/config.py:56`; **VERIFICATION REQUIRED** for the prod value), "Upload a PDF file" (byte check), 404 "Brochure not found". Public failures give "This link has expired or is no longer available".

---

## 14. Management dashboards
- `GET /management/telecalling` (mgmt-019, `api/api/management.py:484-490`, `services/management_telecalling.py`) requires the **operational tier (partner, super_admin)**, so a **telecaller_manager gets 403** ("Management access required" / "Operational access required", `api/services/management_access.py:10,22`). It is not part of this manual.
- A manager **does** see the sidebar item **Management tasks** (`/account/management-tasks`, mgmt-028 MT14). `telecaller_manager` is in `STAFF_ROLES` (`management_access.py:17-21`), so a manager can own tasks. Page detail is **VERIFICATION REQUIRED** (out of this discovery's scope; cover it in the shared account or management guide).

---

## A. Proposed feature rows
| ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| **MGR-HOME** | | | | |
| DOC-TEL-MGRHOME-001 | Sign in as manager and land on Team | `/admin/login` → `/telecaller/manager/team` | telecaller_manager | `POST /auth/login`, `GET /auth/me` |
| DOC-TEL-MGRHOME-002 | Manager sidebar tour and account links | all manager pages | telecaller_manager | – |
| **TEAM** | | | | |
| DOC-TEL-TEAM-001 | View telecallers who report to you | `/telecaller/manager/team` | telecaller_manager | `GET /telecaller/manager/team` |
| DOC-TEL-TEAM-002 | View a telecaller's daily activity and targets | `/telecaller/manager/team/[id]/activity` | telecaller_manager | `GET /telecaller/activity?user_id&date` |
| **MLEAD** | | | | |
| DOC-TEL-MLEAD-001 | Browse, search and filter team leads | `/telecaller/manager/leads` | telecaller_manager | `GET /telecaller/leads` |
| DOC-TEL-MLEAD-002 | Enter a new lead (distributed or queued; duplicate panel) | `/telecaller/manager/leads/new` | telecaller_manager | `POST /telecaller/leads`, `GET …/duplicate-check`, `POST …/{id}/enquiries` |
| DOC-TEL-MLEAD-003 | Open a team lead: stage, priority, details, qualification | `/telecaller/manager/leads/[id]` | telecaller_manager | `GET/PATCH /telecaller/leads/{id}`, `POST …/stage`, `PUT …/qualification` |
| DOC-TEL-MLEAD-004 | Reopen a closed lead (manager only) | same | telecaller_manager | `POST /telecaller/leads/{id}/stage` |
| DOC-TEL-MLEAD-005 | Assign / change the counselor on a lead | same | telecaller_manager | handover API (tel-018, **VERIFICATION REQUIRED** path) |
| DOC-TEL-MLEAD-006 | Assign unassigned leads in bulk | `/telecaller/manager/assignment` | telecaller_manager | `GET /telecaller/leads/unassigned`, `POST /telecaller/leads/assign` |
| DOC-TEL-MLEAD-007 | Reassign leads between telecallers | `/telecaller/manager/assignment?view=assigned` | telecaller_manager | `GET /telecaller/leads/assigned`, `POST /telecaller/leads/assign` |
| **DIST** | | | | |
| DOC-TEL-DIST-001 | Understand routing (product → city → round robin → queue) | `/telecaller/manager/distribution` | telecaller_manager | `GET /telecaller/distribution-rules` |
| DOC-TEL-DIST-002 | Create a product or city rule | same | telecaller_manager | `POST /telecaller/distribution-rules` |
| DOC-TEL-DIST-003 | Change a rule's telecaller / delete a rule | same | telecaller_manager | `PATCH/DELETE /telecaller/distribution-rules/{id}` |
| **IMP** | | | | |
| DOC-TEL-IMP-001 | Download the CSV template and fill it in | `/telecaller/manager/imports` | telecaller_manager | `GET /telecaller/imports/template` |
| DOC-TEL-IMP-002 | Import leads for a campaign and read the per-row report | same | telecaller_manager | `POST /telecaller/imports` |
| DOC-TEL-IMP-003 | Review past imports | same | telecaller_manager | `GET /telecaller/imports` |
| **CAT** | | | | |
| DOC-TEL-CAT-001 | Manage products (create, edit, order, deactivate) | `/telecaller/manager/products` | telecaller_manager | `GET/POST/PATCH /telecaller/products` |
| DOC-TEL-CAT-002 | Manage campaigns | `/telecaller/manager/campaigns` | telecaller_manager | `GET/POST/PATCH /telecaller/campaigns` |
| **CONT** | | | | |
| DOC-TEL-CONT-001 | Write call scripts with ordered steps | `/telecaller/manager/scripts` | telecaller_manager | `GET/POST/PATCH /telecaller/scripts` |
| DOC-TEL-CONT-002 | Create WhatsApp / email templates and preview them | `/telecaller/manager/templates` | telecaller_manager | `GET/POST/PATCH /telecaller/templates`, `GET …/preview` |
| DOC-TEL-CONT-003 | Upload brochures and copy 7-day links | `/telecaller/manager/brochures` | telecaller_manager | `GET/POST/PATCH /telecaller/assets`, `POST …/{id}/link` |
| **TGT** | | | | |
| DOC-TEL-TGT-001 | Set team default targets (daily / monthly) | `/telecaller/manager/targets?for=overseas` | telecaller_manager | `POST /telecaller/targets`, `GET …/effective`, `GET /telecaller/targets` |
| DOC-TEL-TGT-002 | Override targets for one telecaller | `/telecaller/manager/targets?for=<id>` | telecaller_manager | same |
| **MFUP** | | | | |
| DOC-TEL-MFUP-001 | Monitor team follow-ups (today / overdue) | `/telecaller/manager/follow-ups` | telecaller_manager | `GET /telecaller/follow-ups` |
| **ALRT** | | | | |
| DOC-TEL-ALRT-001 | Set team alert thresholds; what telecallers get alerted about | `/telecaller/manager/alerts` | telecaller_manager | `GET /telecaller/settings`, `PUT /telecaller/settings/{team}` |
| **PERF** | | | | |
| DOC-TEL-PERF-001 | Compare telecallers over a date range and export CSV | `/telecaller/manager/performance` | telecaller_manager | `GET /telecaller/manager/performance(.csv)` |
| **RPT** | | | | |
| DOC-TEL-RPT-001 | Lead Source / Course / Campaign funnel reports | `/telecaller/manager/reports?report=source…` | telecaller_manager | `GET /telecaller/reports/{kind}(.csv)` |
| DOC-TEL-RPT-002 | Telecaller activity report | `?report=telecaller` | telecaller_manager | same |
| DOC-TEL-RPT-003 | Counselor handover report | `?report=handover` | telecaller_manager | same |

## B. Test data needed before screenshots
| Feature(s) | Data |
|---|---|
| All | A dedicated **Overseas-only manager** (the seed manager also has an IT report) with at least 3 active Overseas telecallers and 1 inactive one; plus a second manager with their own report, so "Another manager's report" and 404 cases can be shown. Set the manager password from env, never in the docs. |
| TEAM-001 | More than 50 reports only if the pager is to be shown; otherwise 4-5 telecallers, at least one with no phone ("—"). |
| TEAM-002, PERF, RPT-002 | For each telecaller, calls with mixed outcomes (connected, busy, no_answer…), completed and pending follow-ups, a counselling appointment, a BDM meeting request, WhatsApp messages, a qualified move and a converted lead, spread over today, earlier this month and last month. Targets set for daily and monthly. |
| MLEAD-001/003/004 | Overseas leads in **every stage**, including closed ones (for Reopen), Hot/Warm/Cold, with products and campaigns, follow-ups due today and overdue; one lead handed over to a counselor; one unassigned Overseas lead. |
| MLEAD-002 | A known person (phone or email) for the duplicate panel; an Overseas product with a campaign. A distribution rule pointing to a report (for the in-scope open) and one setup where the lead goes to the queue. |
| MLEAD-006/007 | At least 3 unassigned Overseas leads (plus 1 IT lead to show "Choose leads from one team." if the manager has mixed teams); several assigned leads across 2 reports. |
| DIST | 1 product rule (e.g. Product: UK), 1 city rule (e.g. City: Hyderabad), 1 rule whose telecaller is inactive ("Inactive — skipped"), 1 rule of another manager. |
| IMP | An active Overseas campaign; a sample CSV (about 6 rows): 3 new, 1 matching an existing lead (attached), 2 invalid (bad phone, passing_year 1900). Also an over-1 MB or wrong-column file for the error message. |
| CAT | Seeded 18 products; 2 campaigns (one with an end date, one with an inactive product). |
| CONT | 1 script with 3+ steps for an Overseas product; 1 WhatsApp "Overseas destination information" template with {name}/{product}; 1 email template with {brochure_link} + brochure; 1 PDF brochure and 1 fee sheet (small PDFs). |
| TGT | Team default history rows plus one override, with past and future effective dates. |
| ALRT | One saved change, so "Last changed by …" shows. |
| MFUP | Open follow-ups due today and overdue across 2 reports. |
| RPT-003 | At least 2 leads handed over to counselors in range, 1 at counselling_completed, 1 converted. |

## C. Open questions
| # | Question | Why |
|---|---|---|
| Q1 | Should an Overseas manager be able to edit **IT** products, campaigns, scripts, templates, brochures, IT team target defaults and IT alert thresholds? The code allows it (§0.4). | Manual wording and possible permission gap; **VERIFICATION REQUIRED** with the owner. |
| Q2 | Distribution rules and Targets default to **IT** (create form team = IT; `?for=` defaults to IT). Is that acceptable for an Overseas manager? | UX; a doc step must tell the manager to switch to Overseas. |
| Q3 | The Performance Team filter offers IT to an Overseas-only manager (the result is empty), while the Reports Team picker is hidden. Is this inconsistency known? | Screenshot and wording. |
| Q4 | Round robin spans all active telecallers of the team, including other managers' reports. Is that intended (T11)? | Explains why imported or new leads can land outside the manager's reports (the "created and assigned to X" notice). |
| Q5 | What does the **Call** button do on the manager lead page? (The dialer opens, the call-log form does not.) | Browser check. |
| Q6 | The Reports API accepts a future "To" date while Performance refuses it. Is that intentional? | Consistency. |
| Q7 | Will the manager ever receive alerts (no Notifications nav item)? Is the manager meant to be copied on "Lead not contacted"? | Scope (DEC-SCOPE-111 AL5 says telecaller only). |
| Q8 | Is the brochure upload limit in prod the 20 MB default (`max_upload_bytes`)? | The doc states a number. |
| Q9 | Import history shows only the manager's own imports. Should managers of the same team see each other's? | R11 as built. |
| Q10 | Should the Management tasks page (mgmt-028) be documented in this manual or in a shared guide? | Scope of the manual. |
