# Telecaller CRM user-guide discovery: Frontline (Overseas) Telecaller portal

> **Evidence appendix** for `docs/telecaller-crm/documentation-analysis.md` — raw read-only source discovery (master planning session S1, 2026-10-17, code `main` @ `6fee294d`). Field-level detail for module sessions. Not browser-verified; where this file and the browser disagree, the browser wins and this file is annotated, not silently trusted.

Source: repo `edusphere` at main 6fee294d (branch docs/telecaller-crm-user-guide, worktree `.claude/worktrees/tel-docs`). Read-only discovery; nothing executed against a running stack.
Path prefixes: `web/` = `apps/web/`, `api/` = `apps/api/app/`. Every browser call goes to `/api/v1/...`.
Scope: role `telecaller`, team `overseas`, everything under `web/app/telecaller/*` except `/telecaller/manager/*` and `/telecaller/sign-in`. Decision IDs are from `docs/decisions/PRODUCT_DECISION_REGISTER.md`; code is the authority.

Legend: **VERIFICATION REQUIRED** = cannot be confirmed from code alone (needs a running stack / screenshot / owner answer).

---

## PART 0 — Who the frontline telecaller is (IT vs Overseas)

| Topic | Rule (code) | Evidence | Decision |
|---|---|---|---|
| Role / team | Role `telecaller`; `telecaller_profiles.team` ∈ `it`/`overseas`; the user's `division` must equal the team | `api/api/admin.py:553` ("Division must match the telecaller's team"); team move sets `profile.team = user.division = team` `api/services/telecaller_lifecycle.py:122` | DEC-SCOPE-073 (tel-001), DEC-SCOPE-104 (tel-025) |
| Sign-in | Overseas telecaller signs in at **`/overseas/login`** (IT at `/it/login`). `/telecaller/sign-in` is only a chooser: "Telecaller sign-in", buttons **IT team** / **Overseas team** (`web/app/telecaller/sign-in/page.tsx:18-22`) | — | TL1 |
| Landing | `ROLE_DASHBOARD_PATH.telecaller = "/telecaller/dashboard"`; `/telecaller` redirects there | `web/lib/navigation.ts:49`; `web/app/telecaller/page.tsx:4-6` | tel-001 |
| Gate on every page | `GET /api/v1/telecaller/me` → `telecaller_context`: other role → 403 "Telecaller role required"; no profile → 403 "Telecaller profile not set up — contact your administrator" | `api/services/telecaller.py:133-139` | — |
| Role pill | `"<Team> Telecaller"` → **"Overseas Telecaller"** | `web/lib/telecaller.ts:17-18` | — |
| Lead scope | A telecaller sees/acts only on leads where `enquiries.telecaller_user_id = me`; anything else reads as **404 "Lead not found"** (never 403) | `api/services/lead_pipeline.py:41-52` | DEC-SCOPE-081 (T23) |
| Handed over = read only | Once `owner_id` (counselor) is set, the telecaller gets read-only; writes → 403 "This lead is with the counselor; you can view it but not change it" | `api/services/telecaller_leads.py:22,27-35` | DEC-SCOPE-084 (D1), DEC-SCOPE-101 |
| Counselor role | Handover/booking targets are users with `role = "counselor"` and `division = lead.division` (IT counselor role added by tel-017) | `api/services/lead_appointments.py:71-72,85-90` | DEC-SCOPE-076, DEC-SCOPE-095 |
| Appointment types | IT: `career_counselling`, `it_course_counselling`; **Overseas: `career_counselling`, `overseas_counselling`, `university_counselling`** | `api/models.py:1969-1972` | DEC-SCOPE-095 (AP4) |
| Conversion | System moves Application/Enrollment → Converted when the linked student has an **active IT enrolment OR an overseas application with status `enrolled`** (on detail read + 15-min sweep) | `api/services/lead_handover.py:128-171` | DEC-SCOPE-101 (HO3) |
| Milestones panel | Overseas: "Overseas application" + "Visa case" rows; IT: "IT enrolment" | `api/services/lead_handover.py:174-191`; `web/lib/leadHandover.ts:87` | T4 |
| Qualification section | Chosen by the **product group** (`it`/`overseas`/`other`), not the lead division; Overseas group → "Overseas requirement" | `api/services/lead_qualification.py:20-25`; `web/lib/telecallerLeads.ts:244-265` | DEC-SCOPE-093 |
| Team thresholds | "Lead not contacted" hours (default 24) and "Hot lead pending" hours (default 4) are per team (manager Alert settings) and feed the dashboard Overdue tile and alerts | `api/models.py:2853-2854`; `api/services/telecaller_metrics.py:227-230` | DEC-SCOPE-111 |
| Targets | Effective targets are resolved per team + user | `api/services/telecaller_metrics.py:241,271-277` | DEC-SCOPE-080 |

---

## PART 1 — Shell, navigation, account

### 1.1 Sidebar (TELECALLER_NAV, `web/lib/navigation.ts:103-110`)

**Dashboard · My Leads · Follow-ups · BDM requests · Notifications · Profile · Management tasks** (the last is the shared `MANAGEMENT_TASKS_NAV` → `/account/management-tasks`, `navigation.ts:11`; out of this file's scope — **VERIFICATION REQUIRED** whether a telecaller can see any task there).
- Unread badge on **Notifications**: `telecallerNav()` → `GET /api/v1/workflows/notifications/unread-count` (`web/lib/telecallerNav.ts:5`, `web/lib/bdmNav.ts:6-13`); a failed count just hides the badge.
- Shell (`web/components/PortalShell.tsx:17`): logo, role pill "Overseas Telecaller / <name>", nav, footer **Change password** (`/account/password`), **My profile** (`/account/profile`), **Sign out**; top bar "EduSphere Portal" + name + unread icon; mobile menu repeats Change password, My profile and nav items ("Notifications (N unread)").
- Access failure card: heading **"Access unavailable"** + server message + "Go to your dashboard" / return-to-login (`web/components/AccessUnavailable.tsx:27-32`).

### 1.2 Profile — `/telecaller/profile` (`web/app/telecaller/profile/page.tsx:11-33`)

- Eyebrow "Profile", heading **"My profile"**, text "You can update your mobile number. Contact your administrator to change anything else."
- Read-only card (`web/components/TelecallerProfileCard.tsx`): **Name, Employee ID, Team, Mobile, Email, Reporting manager** (suffix " (inactive)" if the manager is inactive), **Status** (Active/Inactive).
- Form (`web/components/TelecallerPhoneForm.tsx`): field **Mobile** (`type=tel`, maxLength 40), button **Save mobile** (busy "Saving…"); success "Mobile saved."; error = server text.
- API: `PATCH /api/v1/telecaller/profile` (`api/api/telecaller.py:80-91`) body `{phone}` only — any other key 422 (`TelecallerSelfUpdate`, `extra=forbid`, `api/schemas.py:4970-4975`); phone rule = trimmed, ≤40, digits/spaces/+-(), no control chars; `null`/"" clears. Audit `telecaller.profile_update` (field names only). DEC-SCOPE-073 TL3.

### 1.3 Generic account pages (shell footer)

- `/account/profile`: `ProfileForm nameLocked` for telecaller → name read-only with hint **"Your administrator manages your name."**, **Phone** editable (`web/app/account/profile/page.tsx:70`; `web/components/ProfileForm.tsx:32-34,127-132`).
- `PATCH /api/v1/auth/me` (`api/api/auth.py:335`, rule at `:348-356`): for `telecaller` a changed `full_name` or `profile` → 403 **"Telecallers can change only their phone number — contact your administrator"**; phone re-validated with the TL3 rule. DEC-SCOPE-073 TL8.
- `/account/password` = shared change-password page (documented elsewhere; **VERIFICATION REQUIRED** for telecaller-specific copy — none found).

### 1.4 Notifications — `/telecaller/notifications` (`web/app/telecaller/notifications/page.tsx:11-37`)

- Eyebrow "Notifications", heading **"Your notifications"**; list `SchoolNotificationList` with `readBeforeOpen` (opening an unread item marks it read before navigating, so the badge is correct). Each item: title + **new** badge when unread, body, link (`web/components/SchoolNotificationList.tsx:35-61`).
- Empty: **"No notifications yet. New leads, follow-ups, appointments, returned leads and waiting leads appear here."**
- API: `GET /api/v1/workflows/notifications` (shared workflow route).
- Alert kinds (`api/services/telecaller_alerts.py:50-60`), each = one in-app notice + one email to the lead's telecaller, no quiet hours (DEC-SCOPE-111 AL2/AL3):

| Title | Trigger | Body (code) |
|---|---|---|
| New lead assigned | event (assignment; never to self) | **VERIFICATION REQUIRED** exact body |
| Follow-up due | beat, 15 min | "Your follow-up with {name (Lead ID)} is due at {time}." (`:181`) |
| Missed follow-up | beat | "Your follow-up with … due at … is still open." (`:186`) |
| Appointment tomorrow / Appointment in 1 hour | beat | "The counselling appointment for … starts at …." (`:198`) |
| Lead not contacted | beat; team hours (default 24) | **VERIFICATION REQUIRED** |
| Hot lead pending | beat; team hours (default 4) | "Hot lead … has had no call for over {hours} hours." (`:248`) |
| Counselor appointment completed | event | "The counselling appointment for … on … was completed." (`:130`) |
| Lead returned for follow-up | event (counselor returns lead) | **VERIFICATION REQUIRED** |

Link label per notice: "Open follow-ups" or "Open lead" (`:79`). Bodies never carry phone/email/free text.

---

## PART 2 — Dashboard — `/telecaller/dashboard`

Page `web/app/telecaller/dashboard/page.tsx:19-57`. Eyebrow "Dashboard", heading **"Welcome, {full name}"**, text "Your figures for today, worked out from your calls, follow-ups and appointments." Each card fails independently ("… unavailable right now"). DEC-SCOPE-105 (tel-021), DEC-SCOPE-080 (targets), DEC-SCOPE-094 (follow-ups card).

| Card | Content / labels | API | File |
|---|---|---|---|
| Tiles "Today at a glance" | **New Leads** (Leads received today) · **Calls Today** (Done / to do → "done / to_do") · **Follow-ups Due** (Scheduled for today) · **Hot Leads** (High-potential leads) · **Appointments** (Counselling / BDM today) · **Connected** (Successfully contacted) · **Not Connected** (No answer / busy / switched off) · **Converted** (Leads converted today) · **Overdue** (Missed calls / follow-ups) · **Daily Target** (Calls vs target → "65 / 80", "not set") | `GET /telecaller/dashboard` `api/api/telecaller_dashboard.py:32-42`; tiles `api/services/telecaller_metrics.py:233-255` | `web/lib/telecallerMetrics.ts:22-33`, `TelecallerDashboardTiles.tsx` |
| Today's follow-ups | "**N** due today · **N** overdue"; first 5: name link · next action or reason · time · priority · **Overdue** badge; empty "Nothing due today."; link **View all follow-ups** | `GET /telecaller/follow-ups?view=day&limit=5` | `TelecallerFollowUpsCard.tsx` |
| Today's appointments | "time · Counselling / BDM meeting · title (lead link) · code"; empty "No appointments today." (own counselling bookings + accepted BDM meetings) | same dashboard payload | `TelecallerAppointmentsCard.tsx`, `telecallerMetrics.ts:52` |
| My targets | Table **KPI / Today / {Month YYYY}**; KPIs **Calls, Connected calls, Qualified leads, Follow-ups, Counselling appointments, Conversions**; cell "achieved / target" or "Not set"; note "Achieved / target. Targets are set by your manager; the month counts from the 1st to today." | `GET /telecaller/targets/effective` `api/api/telecaller_targets.py:97` + dashboard `targets` | `TelecallerTargetsCard.tsx`, `web/lib/telecallerTargets.ts:23-35` |
| Daily activity | GET form **Day** (date, max today) + **Show**; table "Activity on {d MMM yyyy} / Count" with 13 rows: Total leads assigned, Total calls, Connected calls, Not connected, Follow-ups completed, Follow-ups pending, New appointments, Counselor appointments, BDM appointments, WhatsApp messages, Qualified leads, Hot leads, Converted leads; second table **KPI / Achieved / target** | `GET /telecaller/activity?date=` `api/api/telecaller_dashboard.py:45-75`: future day → 422 "Daily activity can't be shown for a future date"; `user_id` ≠ self → 403 "You can only view your own activity" | `TelecallerActivityPanel.tsx`, `telecallerMetrics.ts:36-50,78-83` |
| Profile card | same as 1.2 | `/telecaller/me` | `TelecallerProfileCard.tsx` |

Tile rules: Calls Today to-do = first-call-pending leads + follow-ups due today; Overdue = open follow-ups past due + First Call Pending leads older than the team's not-contacted hours (`telecaller_metrics.py:244,251-253`).

---

## PART 3 — Leads

### 3.1 My Leads — `/telecaller/leads` (`web/components/TelecallerLeadPages.tsx:44-66`, table `web/components/TelecallerLeadTable.tsx`)

- Eyebrow "Leads", heading **"My leads"**, text "The leads assigned to you. Open a lead to call, update it or set its priority.", button **New lead**.
- Search: label **Search leads**, hint "Lead ID, name, phone, WhatsApp or email", maxLength 200, buttons **Search**, **Clear search**.
- Filters (all in the URL): **Stage** (All stages + 16 stages), **Priority** (All priorities / Hot / Warm / Cold), **Product** (All products; grouped IT Courses / Overseas Education / Other), **Campaign** (All campaigns), **Due follow-up** (Any / Due today / Overdue).
- Columns: **Name** (link) · **Lead ID** · **Mobile** · **Interest** (product name else subject) · **Stage** (+ "With counselor" when handed over) · **Priority** · **Lead date**. Page size 50; "Showing a–b of N", **Previous** / **Next**.
- Empty: "No leads match these filters." / "No leads are assigned to you yet."; error "Unable to load leads." + **Retry**; loading "Loading leads…".
- API: `GET /api/v1/telecaller/leads?status&priority&product_id&campaign_id&follow_up&q&limit&offset` (`api/api/telecaller.py:100-122`), newest first, every filter ANDed with own scope; bad priority/UUID → 422 (UI drops them). Product/campaign pickers: `GET /telecaller/products`, `/telecaller/campaigns` — telecallers see **active rows only, all groups/teams** (`api/services/telecaller_catalogue.py:23-30`). DEC-SCOPE-084, DEC-SCOPE-094 (F9).

Stage catalogue (`api/lead_stages.py:4-22`): open — New Lead, Assigned, First Call Pending, Contacted, Qualified, Interested, Follow-up, Counselling Scheduled, Counselling Completed, Application/Enrollment, Converted; closed — Not Interested, Not Eligible, Wrong Number, No Response, Lost.

### 3.2 New lead — `/telecaller/leads/new` (`TelecallerLeadPages.tsx:93-114`, form `web/components/NewLeadForm.tsx`)

- "← Back to leads"; heading **"New lead"**; text "The lead is assigned to you. We check the mobile number and email against every lead first, so a person is never entered twice."

| Field (label) | Type / limit | Required | Server rule |
|---|---|---|---|
| Student name * | text ≤160 | yes | `BdmLeadName` |
| Mobile number * | tel ≤40 | yes | must normalise → else "Enter a valid mobile number" (`api/schemas.py:6008-6011`) |
| Email | email ≤255 | no | |
| WhatsApp number | tel ≤40 | no | |
| City / State | ≤120 | no | |
| Qualification | ≤120 | no | |
| Passing year | number 1950–2100 | no | |
| College/University | ≤200 | no | |
| Product interest * | select (active products, grouped) | yes | must be active |
| Division * | IT / Overseas — shown only for an `other` product without a team | cond. | "Choose the division (IT or Overseas) for this product"; mismatch "{product} belongs to the {team} team" (`api/services/lead_intake.py:95-102`) |
| Campaign | select, this product's active campaigns ("Choose a product first" / "No campaign"); choosing one sets the source | no | "Choose an active campaign" / "This campaign is for another product" / "This campaign belongs to another lead source" (`lead_intake.py:88-115`) |
| Lead source * | Instagram, Facebook, Google, Website, WhatsApp, Walk-in, College, School, Agent, Referral, Exhibition/Event, BDM, Other (`web/lib/telecallerCatalogue.ts:22-25`) | yes | |
| Priority | Hot / Warm / Cold, default **Warm** | — | |
| Enquiry subject | ≤180, placeholder = product name | no (defaults to product) | |
| Notes | textarea ≤5000 | no | |

- Client validation: "Enter the {student name, mobile number, product interest and lead source}." Buttons **Create lead** (busy "Creating…"), **Cancel**. Picker failure: "Unable to load the products and campaigns. Reload the page to try again."
- Duplicate panel (on blur of mobile/email: `GET /telecaller/leads/duplicate-check?phone&email`, `api/api/telecaller.py:125-135`; across every lead incl. closed and the other team): heading **"⚠️ Lead already exists."**, "A lead with this mobile number or email is already in the CRM. Add this enquiry to it instead of creating another lead."; per match "LEAD-ID · name (same phone and email)", **Existing telecaller / Counselor / Last contact / Current status**, "Previous enquiries" list, buttons **Add enquiry to this lead** (→ "Enquiry added"; `POST /telecaller/leads/{id}/enquiries`, `api/api/telecaller.py:151-157`, any lead, append-only) and **Open lead** (only if in my scope). Create with a known person → 409 `duplicate_lead` + "This person is already a lead. Add the enquiry to the existing lead instead."
- Create: `POST /api/v1/telecaller/leads` (`api/api/telecaller.py:138-148`; `lead_intake.create_lead` `:105-139`): a telecaller's lead is **assigned to the creator** (`assigned` event → stage Assigned), audit `lead.create`, CRM sync after commit; success navigates to the new lead. DEC-SCOPE-088 (I1, I2, I5, R2).
- **IT-vs-Overseas gap:** nothing stops an Overseas telecaller choosing an IT-group product; the lead gets `division=it` but stays assigned to the Overseas telecaller. **VERIFICATION REQUIRED** (open question Q1).

### 3.3 Lead detail — `/telecaller/leads/[id]` (`TelecallerLeadPages.tsx:117-142`, panel `web/components/LeadDetailPanel.tsx`)

- Not found / out of scope / malformed id: card **"Lead not found"** — "This lead does not exist, or it is not in your leads."
- Header: eyebrow Lead ID, H2 name, "Stage: **X** · Priority: **Y**"; when handed over: "This lead is with the counselor, {name}. You can view it but not change it." (`:203-208`).
- `telecallerWrites` = not handed over AND not closed (`:165`) — gates Log call, WhatsApp, Email, Add follow-up.

Action row (`:211-237`):

| Control | Shown when | Behaviour |
|---|---|---|
| **Call** (`tel:` link) | lead has a usable phone (≥6 digits) — even closed/handed over | opens dialer and the Log call form |
| **WhatsApp** | telecallerWrites + `whatsapp_to` | opens WhatsApp composer |
| **Email** | telecallerWrites + email | opens email composer |
| **Change stage** | not handed over AND `personTargets` non-empty | see 3.4 |
| **Assign to counselor** | not handed over, not closed, stage before Application/Enrollment | see 3.11 |

Sections in page order: Priority → Calls → Messages → Follow-ups → Call script → Lead details → Qualification → Counselling appointments → Student and milestones (if linked) → Enquiry (subject + message) → Activity.

- **Priority** (`:241-260`): radios **Hot** "Ready to join / immediate requirement." / **Warm** "Interested but needs follow-up." / **Cold** "Long-term / low interest."; **Save priority** → "Priority updated."; `PATCH /telecaller/leads/{id}` `{priority}`.
- **Lead details** (`:276-297`): view = Lead ID, Mobile number, WhatsApp number, Email, City, State, Qualification, Passing year, College/University, Lead source, Campaign, Product interest, Assigned telecaller, Assigned counselor ("Not assigned"), Lead date. **Edit details** → Student name (≤160, req.), Email (≤255, req. only if it had one), Mobile number, WhatsApp number (≤40), City, State (≤120), **Product interest** (No product + active products); **Save details** → "Details saved." / **Cancel**. `PATCH /telecaller/leads/{id}` (`api/api/telecaller.py:167-176`; `TelecallerLeadUpdate` `api/schemas.py:5996-6005`): row locked in scope (reassigned meanwhile → 404), handed over → 403; only changed values written; priority change = own audit row `lead.priority_change`.
- Note: Priority, Lead details and Qualification stay editable on a **closed** lead (only handover blocks them, `require_writable`). **VERIFICATION REQUIRED** that this is intended (Q2).
- **Enquiry**: subject (bold) + message text.

### 3.4 Stage control (`web/components/AdminLeadStage.tsx:18-88`; rules `web/lib/leadStages.ts:304-312`, server `api/services/lead_pipeline.py:81-106`)

- Button **Change stage** → select "Choose a stage" + **Reason (optional)/(required)** textarea ≤500 + **Save** / **Cancel**; client errors "Choose a stage." / "Add a reason for this stage."; success "Stage updated."
- Telecaller targets: **Qualified, Interested, Follow-up** (only while before Application/Enrollment) + any closed outcome (reason required). Nothing on Converted. On a closed lead the telecaller gets **no control** (reopen is manager-only: 403 "Only a manager can reopen a closed lead").
- Server messages: "Choose a stage of the lead pipeline", "The lead is already at this stage", "This stage is set by the system", "The lead is with the counselor; its stage moves with the application", "Add a reason for closing the lead". Closing cancels open follow-ups (reason "Lead closed") and open counselling appointments. Endpoint `POST /telecaller/leads/{id}/stage` (`api/api/telecaller.py:212-223`); history `GET …/stage-history` (`:226`). DEC-SCOPE-081.
- System moves (`api/lead_stages.py:37-48`): assigned; call_unconnected → First Call Pending; call_connected → Contacted; appointment_booked → Counselling Scheduled; appointment_completed → Counselling Completed; no-show/cancel → Follow-up; student_linked → Application/Enrollment; returned → Follow-up; converted.

### 3.5 Calls (`web/components/LeadCalls.tsx`, `web/components/CallLogForm.tsx`; API `api/api/telecaller_calls.py`, `api/services/lead_calls.py`) — DEC-SCOPE-096

- Section **Calls**, button **Log call** (telecallerWrites); empty "No calls logged yet."; "Showing the latest 50 of N calls."
- Item: outcome label + badge **Connected** / **Not connected**; "date time · duration · Incoming/Outgoing · caller"; remarks; **Edit** / **Delete** when `can_change` (caller, call's IST day, not handed over). Delete confirm: "Delete this call? The lead's stage and any follow-up it added stay." **Yes, delete** / **Keep it**.
- Form fields: **Outcome (required)** (optgroups Connected / Not connected; hidden on edit — CL4), **Call date and time (IST)** (datetime-local, min = 7 days back, max = now), **Duration** Minutes (0–240) / Seconds (0–59), **Call type** Outgoing/Incoming, **Remarks** ≤2000 with counter. Optional checkbox **Add a next follow-up**; required follow-up block for Follow-up Required / Call Back Requested: **Follow-up due (IST, required)**, **Follow-up reason**, **Next action** (≤200, placeholder "e.g. Call today at 4:00 PM"), checkbox **Also move the lead to Follow-up**. Closing outcome note: "This outcome closes the lead as {X}. Its open follow-ups are cancelled." Buttons **Save call** / **Save changes** / **Cancel**.
- Client errors (`CallLogForm.tsx:61-70`): "Choose the call date and time", "Enter whole minutes and seconds (0–59), up to 4 hours", "Choose an outcome", "Add remarks naming the other lead", "Choose a due date and time", "Choose a reason".
- Outcomes (`web/lib/telecallerCalls.ts:6-20`): Connected – Interested; Connected – Need Information; Connected – Follow-up Required*; Connected – Appointment Fixed; Not Interested → closes; Wrong Number → closes (not connected); Busy; No Answer; Switched Off; Call Back Requested*; Already Joined Elsewhere → Lost; Duplicate Lead (remarks required, no stage effect); Not Eligible → closes. (*needs follow-up). "Interested" also moves the lead to Interested if earlier.
- Server (`lead_calls.py:37-50,128-149`): closed lead 409 "This lead is closed. A manager can reopen it before a call is logged"; "The call time can't be in the future"; "Calls can be logged up to 7 days back"; 300 calls/day cap "You've logged 300 calls for this day"; "Add the next follow-up for this outcome"; "This outcome closes the lead, so it takes no follow-up"; edit only today's "Only today's calls can be changed", "A call can only be moved within today", other caller 403 "Only the telecaller who logged this call can change it".
- Endpoints: `GET/POST /telecaller/leads/{id}/calls` (`telecaller_calls.py:33,42`), `PATCH/DELETE /telecaller/calls/{id}` (`:58,71`), `GET /telecaller/calls/day-counts` (`:26`).

### 3.6 Messages — WhatsApp + email (`web/components/LeadMessages.tsx`, `WhatsAppComposer.tsx`, `EmailComposer.tsx`; API `api/api/telecaller_messages.py`, `api/services/lead_messages.py`) — DEC-SCOPE-100, DEC-SCOPE-106

- Section **Messages**; buttons **Send WhatsApp** / **Send email** (disabled with "No WhatsApp or mobile number on this lead." / "No email address on this lead."); empty "No messages sent yet."
- Item title: "WhatsApp sent – 13 Sept 2026 – 10:35 AM" or "Email sending / Email delayed / Email sent / Email failed – …"; "template name or Custom message · sender"; "Subject: …"; body. Failed: "This email was not delivered. Check the lead's email address and send it again."; retrying: "The mail server didn't accept it yet. It will be retried automatically." List polls every 5 s while queued/sending.
- WhatsApp composer: **Template** (Custom message + active WhatsApp templates), **Message** ≤1000 "n/1000 characters"; **Open WhatsApp** (wa.me link, new tab) → confirm "Did you send it in WhatsApp?" **Yes, record as sent** / **Not sent**; notice "WhatsApp send recorded." Delete (sender, same IST day, WhatsApp only): "Delete this record? It does not unsend the WhatsApp message." → "Message deleted."
- Email composer: **Template**, **Subject** ≤200 (CR/LF → space), **Message** ≤5000; **Send email** → "Email queued for sending." (worker sends; never deletable — "A sent email can't be deleted").
- Template render `GET /telecaller/leads/{id}/render?template_id=` fills {name}, {product}, {brochure_link} (fresh 7-day signed link if brochure active), {appointment_time}; warnings "This template was made for another product. Check the text before sending." and "Check the text: {x} has no value for this recipient." (`lead_messages.py:62-79`).
- Server refusals (`lead_messages.py:29-46`): "Only the lead's telecaller can send a message", closed 409 "This lead is closed. A manager can reopen it before a message is sent", "This lead has no WhatsApp or mobile number", "This lead has no email address", "Choose an active WhatsApp template" / "Choose an active email template", caps 300 WhatsApp/day and 100 emails/day ("You've sent 100 emails today"), 503 "Email is not set up. Ask an administrator to configure SMTP.", delete "Only today's messages can be deleted".
- Endpoints: `GET /telecaller/leads/{id}/messages` (`:41`), `POST …/messages` (`:47`), `DELETE /telecaller/messages/{id}` (`:65`), render (`:34`).

### 3.7 Follow-ups on the lead (`web/components/LeadFollowUps.tsx`, `FollowUpForm.tsx`, `FollowUpItem.tsx`) — DEC-SCOPE-094

- Section **Follow-ups**, button **Add follow-up**; empty "No follow-ups yet."
- Form: **Due date and time (IST, required)** (min now), **Reason (required)**, **Next action** ≤200, **Notes** ≤2000, checkbox **Also move the lead to Follow-up**; **Add follow-up** / **Save changes** / **Cancel**; notices "Follow-up added.", "Follow-up rescheduled.", "Marked done.", "Follow-up cancelled."
- Reasons (`web/lib/telecallerFollowUps.ts:7-18`): Need to discuss with parents; Need course details; Need fee details; Waiting for salary; Waiting for documents; Comparing courses; Interested next month; Interested next intake; Waiting for university information; Requested counselor call.
- Item: reason title, badges **Overdue / Done / Cancelled**, "Due …", "Next action: …", notes, "Done … by …", "Cancelled … — reason"; actions **Done**, **Reschedule**, **Cancel follow-up** (reason required ≤500, **Cancel it**).
- Server (`api/services/lead_follow_ups.py:29-37`): telecaller only (403 "Only the lead's telecaller can change its follow-ups"), closed 409, "Choose a due time in the future", "Choose a due time within the next 12 months", 20 open per lead "This lead already has 20 open follow-ups", "This follow-up is already done" / "was cancelled". Handover/close cancel open follow-ups.
- Endpoints `api/api/telecaller_follow_ups.py`: `GET/POST /telecaller/leads/{id}/follow-ups` (`:43,51`), `PATCH /telecaller/follow-ups/{id}` (`:65`), `POST …/complete` (`:86`), `POST …/cancel` (`:99`).

### 3.8 Call script (content library usage) (`LeadDetailPanel.tsx:109-146`) — DEC-SCOPE-083

- Section **Call script**: the product's single active script → name + numbered steps (title + notes). States: "Set the lead's product interest to see its call script.", "Loading the call script…", "Unable to load the call script.", "No active call script for {product} yet."
- API `GET /telecaller/scripts?product_id&active=true&limit=1` (`api/api/telecaller_content.py:69-86`); readers = telecaller, telecaller_manager, super_admin (`api/services/telecaller_content.py:29,48-50`); telecallers get active rows only. Templates and brochures reach the telecaller only via the composers (3.6). No standalone library page for a telecaller.

### 3.9 Qualification (`web/components/LeadQualificationForm.tsx`; API `api/api/telecaller.py:188-209`, `api/services/lead_qualification.py`) — DEC-SCOPE-093

- Section **Qualification**, button **Edit qualification** (not handed over); view rows show "Not recorded"; "Last updated by {name} · {date}"; success "Qualification saved."; no product → "Set the lead's product interest in Lead details to see its IT or overseas questions."
- Fieldset **Basic qualification**: Qualification (≤120), Current college/company (≤200), Passing year (1950–2100), Work experience (years) (0–50), City, State (≤120).
- Fieldset **Overseas requirement** ("Destination: {product} (change it in Lead details)"): UG / Master's (UG/Masters), Preferred course (≤200), Intake (≤40), Academic percentage (0–100, step 0.01), IELTS/PTE status (≤120), Budget (≤120), Passport status (No passport / Applied / Has a valid passport).
- (IT counterpart "IT training requirement", "Course interested in": Current skill level, Career objective, Preferred batch, Budget range, Preferred mode Online/Offline.)
- Buttons **Save qualification** / **Cancel**, per-field **Clear**; errors "Check the highlighted fields." / range messages ("Enter a percentage from 0 to 100." etc.). `PUT` replaces applicable fields; non-applicable → 422 "These fields don't apply to this lead's product: …"; stage never moves; shared fields update Lead details.

### 3.10 Counselling appointments (`web/components/LeadAppointmentsSection.tsx`, `BookCounsellingForm.tsx`, `LeadAppointmentCard.tsx`; API `api/api/lead_appointments.py`) — DEC-SCOPE-095

- Section **Counselling appointments**, button **Book counselling**; notes "This lead has an open appointment. Reschedule or cancel it to book another." / "This lead is closed. A manager can reopen it before a booking."; empty "No counselling appointments yet."
- Booking form (`GET /telecaller/leads/{id}/appointment-options`, `:44`): **Appointment type** (Overseas: Career counselling / Overseas counselling / University counselling), **Counselor** (active counselors of the lead's division), **Date and time (IST)**, **Mode** Online/Phone/In person (default Online), **Meeting link** ≤500, **Location** ≤200, **Purpose** ≤500, **Remarks** ≤1000; **Book appointment** / **Cancel**; "There is no active counselor in this lead's division yet."; success "Appointment {code} booked with {counselor}."; clash "The counselor is busy at this time." Every booking = 60 min.
- Server (`api/api/lead_appointments.py:30-32,57-86`): only telecaller ("Only the lead's telecaller can book an appointment"), handed over 403, closed 409 "This lead is closed; reopen it before booking", wrong type 422, "Choose a time in the future" / "within the next year", "Choose an active counselor of the lead's division", 409 "This lead already has an open counselling appointment", 409 counselor busy. Stage → Counselling Scheduled.
- Card: "{type} {code}" + status badge (Scheduled/Confirmed/Rescheduled/Completed/Cancelled/No show); **When, Counselor, Mode, Meeting link, Location, Purpose, Remarks, Booked by**; history "from → to". Telecaller actions: **Reschedule** ("New date and time (IST)", "Reason (optional)", **Save new time**) and **Cancel appointment** ("Reason for cancelling" required); confirm/complete/no-show are counselor-only (`api/services/lead_appointments.py:50-53,176-188`). Endpoints `POST /lead-appointments/{id}/cancel|reschedule` (`lead_appointments.py:140,145`). Cancel/no-show → Follow-up.

### 3.11 Handover / student link / conversion (`web/components/LeadHandoverForm.tsx`, `LeadMilestones.tsx`; API `api/api/lead_handover.py:28-36`, `api/services/lead_handover.py`) — DEC-SCOPE-101

- Button **Assign to counselor** → **Counselor** select ("Choose a counselor"), note "The counselor takes over the lead. You keep read access and its open follow-ups are cancelled.", **Hand over** / **Cancel**; "No other active counselor in this division."; success "Handed over to {name}."
- Server: closed 409 "This lead is closed; reopen it before handing it over"; past 409 "This lead is already past the counselor handover"; same 409 "This lead is already with this counselor"; counselor not active/of division 422. Follow-ups cancelled ("Handed over to counselor"); stage unchanged. After this the telecaller page is read-only.
- Counselor (not the telecaller) links the student and may return the lead (→ alert "Lead returned for follow-up", stage Follow-up). Section **Student and milestones** (+ **Converted** badge): "No student account is linked yet." / "Linked student: name (email)" / "No enrolment or application yet." / rows "Overseas application · University — Status · reference · time", "Visa case · …".

### 3.12 Timeline (`web/components/LeadTimeline.tsx`, `web/lib/leadTimeline.ts`; API `GET /telecaller/leads/{id}/timeline`, `api/api/telecaller.py:179-185`) — DEC-SCOPE-114

- Section **Activity**, list "Lead activity", 50 per page, **Show older entries**; "No activity yet."; "Unable to load the activity." + **Retry**. Re-reads after every action on the page.
- Badges/titles (`leadTimeline.ts:66-110`): Lead "Lead created" (Source…, "Assigned to …"); Enquiry "New enquiry: …"; Stage "Stage: A → B" / "Returned to the telecaller" / "Converted"; Priority "Priority: A → B"; Telecaller "Assigned to / Reassigned from … to …" (Manual / Round robin / Product rule / Location rule); Counselor "Handed over to …"; Student "Student linked/unlinked: …"; Call "Outgoing call: {outcome}" (Duration m:ss); WhatsApp/Email; Follow-up "scheduled/done/cancelled: {reason}" (Due); Appointment "Counselling appointment booked/…" (For); Milestone. Actor "Website form" / "System" when none. Free text cut at 200 chars.

---

## PART 4 — Follow-ups page — `/telecaller/follow-ups`

`TelecallerLeadPages.tsx:69-90`, list `web/components/TodayFollowUps.tsx`. Eyebrow "Follow-ups", heading **"Today's follow-ups"**, text "Your open follow-ups for the day, earliest first. Times are India time (IST)."
- Tabs **Today (n)** (or the chosen date) / **Overdue (n)**; **Day** date picker + **Back to today**.
- Card per follow-up: lead name link + badges; **Interest, Action** ("next action or reason · time"), **Priority, Reason, Lead** ("ID · stage"), **Last call** ("outcome · time" or "No calls yet"); notes; **Done / Reschedule / Cancel follow-up** when `can_change`.
- Empty "No follow-ups due on this day." / "No overdue follow-ups."; error "Unable to load follow-ups." + **Retry**; paging 50.
- API `GET /telecaller/follow-ups?view=day|overdue&day=&limit&offset` (`api/api/telecaller_follow_ups.py:27-40`), own leads only, returns `day` + `counts`.

---

## PART 5 — BDM meeting requests — `/telecaller/meeting-requests` (+ `/new`) — DEC-SCOPE-098

- List page (`web/app/telecaller/meeting-requests/page.tsx:13-41`): eyebrow "BDM requests", heading **"BDM meeting requests"**, "Ask a BDM to meet a college, agent, school or company. You'll see here when it is accepted or declined.", button **New request**; after filing "Request {code} sent. It stays Pending until a BDM accepts or declines it."
- Filters **All / Pending / Accepted / Declined**; columns **Request** (MRQ-000001) · **Proposed (IST)** (+ mode) · **Organization** (+ person) · **Type** · **Status** (+ appointment code · time, or "Reason: …") · **BDM** (name or "Any {College/Agent/School} BDM"); 25 per page **Previous/Next**; empty "No meeting requests yet." / "No pending requests." (`web/components/MeetingRequestList.tsx`).
- New page (`web/app/telecaller/meeting-requests/new/page.tsx`): heading **"Request a BDM meeting"**, "Pick a BDM, or leave it for any BDM of the meeting's module. Corporate meetings go to college BDMs." **Back to requests**.
- Form (`web/components/MeetingRequestForm.tsx`): **Meeting type** (College meeting / Agent meeting / School meeting / Corporate meeting), **BDM** ("Any {type} BDM" or a named active BDM; "There is no active {type} BDM yet; the request waits for one."), **Organization** ≤200*, **Person to meet** ≤200*, **Phone** ≤30*, **Email (optional)** ≤255, **Proposed date and time (IST)***, **Mode** (Online/Phone/In person, default In person), **Meeting link or location (optional)** ≤255, **Purpose** ≤1000*, **Remarks (optional)** ≤2000; **Send request**. Errors "Choose the meeting type.", "Enter the organization.", "Enter the person to meet.", "Enter a phone number.", "Choose the date and time.", "Enter the purpose."
- API (`api/api/bdm_meeting_requests.py:33-65`): `GET /telecaller/meeting-requests/options`, `POST /telecaller/meeting-requests`, `GET /telecaller/meeting-requests?status` (own only). Server: "Choose a time in the future" / "within the next year", "Choose an active {type} BDM, or leave it for any of them". Not tied to a lead; same for IT and Overseas telecallers (corporate → college BDMs). The BDM accepts (creates a BDM appointment) or declines with a reason.

---

## (a) Proposed feature list

| Feature ID | Title | Route | Role | Key APIs |
|---|---|---|---|---|
| **ACC — account, profile, notifications** |||||
| DOC-TEL-ACC-001 | Sign in as an Overseas telecaller (chooser + `/overseas/login`) | /telecaller/sign-in → /overseas/login | telecaller | POST /auth/login |
| DOC-TEL-ACC-002 | Portal shell, sidebar and unread badge | all /telecaller/* | telecaller | GET /telecaller/me, GET /workflows/notifications/unread-count |
| DOC-TEL-ACC-003 | View my profile and update my mobile | /telecaller/profile | telecaller | GET /telecaller/me, PATCH /telecaller/profile |
| DOC-TEL-ACC-004 | Account page limits (name locked, phone only) + change password | /account/profile, /account/password | telecaller | PATCH /auth/me |
| DOC-TEL-ACC-005 | Notifications and the nine alerts | /telecaller/notifications | telecaller | GET /workflows/notifications |
| **DASH — dashboard** |||||
| DOC-TEL-DASH-001 | Today's tiles | /telecaller/dashboard | telecaller | GET /telecaller/dashboard |
| DOC-TEL-DASH-002 | Today's follow-ups and appointments cards | /telecaller/dashboard | telecaller | GET /telecaller/follow-ups?view=day&limit=5, /telecaller/dashboard |
| DOC-TEL-DASH-003 | My targets | /telecaller/dashboard | telecaller | GET /telecaller/targets/effective |
| DOC-TEL-DASH-004 | Daily activity for a chosen day | /telecaller/dashboard?date= | telecaller | GET /telecaller/activity |
| **LEAD — leads list, create, detail** |||||
| DOC-TEL-LEAD-001 | My Leads: search, filters, paging | /telecaller/leads | telecaller | GET /telecaller/leads, /products, /campaigns |
| DOC-TEL-LEAD-002 | Create a lead | /telecaller/leads/new | telecaller | POST /telecaller/leads |
| DOC-TEL-LEAD-003 | Duplicate warning and "Add enquiry to this lead" | /telecaller/leads/new | telecaller | GET /leads/duplicate-check, POST /leads/{id}/enquiries |
| DOC-TEL-LEAD-004 | Lead detail overview, header, Call button, read-only state | /telecaller/leads/[id] | telecaller | GET /telecaller/leads/{id} |
| DOC-TEL-LEAD-005 | Set priority | /telecaller/leads/[id] | telecaller | PATCH /telecaller/leads/{id} |
| DOC-TEL-LEAD-006 | Edit lead details (contact + product) | /telecaller/leads/[id] | telecaller | PATCH /telecaller/leads/{id} |
| DOC-TEL-LEAD-007 | Change stage / close a lead | /telecaller/leads/[id] | telecaller | POST /leads/{id}/stage |
| **QUAL** |||||
| DOC-TEL-QUAL-001 | Qualification form (Basic + Overseas requirement) | /telecaller/leads/[id] | telecaller | GET/PUT /leads/{id}/qualification |
| **CALL** |||||
| DOC-TEL-CALL-001 | Log a call (outcomes, stage effects, next follow-up) | /telecaller/leads/[id] | telecaller | POST /leads/{id}/calls |
| DOC-TEL-CALL-002 | Edit or delete today's call | /telecaller/leads/[id] | telecaller | PATCH/DELETE /telecaller/calls/{id} |
| **FUP** |||||
| DOC-TEL-FUP-001 | Add / reschedule / complete / cancel a follow-up on a lead | /telecaller/leads/[id] | telecaller | POST /leads/{id}/follow-ups, PATCH /follow-ups/{id}, POST …/complete, …/cancel |
| DOC-TEL-FUP-002 | Today's and overdue follow-ups page | /telecaller/follow-ups | telecaller | GET /telecaller/follow-ups |
| **APPT** |||||
| DOC-TEL-APPT-001 | Book a counselling appointment | /telecaller/leads/[id] | telecaller | GET /leads/{id}/appointment-options, POST /leads/{id}/appointments |
| DOC-TEL-APPT-002 | Reschedule or cancel an appointment | /telecaller/leads/[id] | telecaller | POST /lead-appointments/{id}/reschedule, …/cancel |
| **MSG** |||||
| DOC-TEL-MSG-001 | Send and record a WhatsApp message (template or custom); delete same-day record | /telecaller/leads/[id] | telecaller | GET /leads/{id}/render, POST /leads/{id}/messages, DELETE /telecaller/messages/{id} |
| DOC-TEL-MSG-002 | Send an email and track delivery | /telecaller/leads/[id] | telecaller | POST /leads/{id}/messages (channel=email), GET /leads/{id}/messages |
| **CONT** |||||
| DOC-TEL-CONT-001 | Use the call script and templates/brochure links | /telecaller/leads/[id] | telecaller | GET /telecaller/scripts, /telecaller/templates, /leads/{id}/render |
| **MEET** |||||
| DOC-TEL-MEET-001 | Request a BDM meeting | /telecaller/meeting-requests/new | telecaller | GET /telecaller/meeting-requests/options, POST /telecaller/meeting-requests |
| DOC-TEL-MEET-002 | Track my BDM meeting requests | /telecaller/meeting-requests | telecaller | GET /telecaller/meeting-requests |
| **HAND** |||||
| DOC-TEL-HAND-001 | Hand a lead over to a counselor | /telecaller/leads/[id] | telecaller | POST /leads/{id}/handover |
| DOC-TEL-HAND-002 | Follow a handed-over lead: read-only view, return, student link, milestones, conversion | /telecaller/leads/[id] | telecaller (counselor acts) | GET /telecaller/leads/{id} (milestones) |
| **TIME** |||||
| DOC-TEL-TIME-001 | Read the lead activity timeline | /telecaller/leads/[id] | telecaller | GET /leads/{id}/timeline |

## (b) Test data needed before screenshots

| Feature(s) | Seed required |
|---|---|
| All | Active `telecaller_manager`; Overseas telecaller (team=overseas, division=overseas, Employee ID, phone) reporting to that manager; an IT telecaller for contrast |
| ACC-005 | Unread + read notifications for the telecaller (one per alert kind, ideally via the real triggers: assignment, follow-up due/missed, appointment tomorrow/1 h, not-contacted, hot pending, completed, returned); SMTP/Mailpit for the email copies |
| DASH-* | Today: new assigned leads, calls connected and not connected, follow-ups due today and overdue, a hot lead, a counselling booking today, an accepted BDM meeting today, a converted lead; manager-set daily + monthly targets for the overseas team; past-day activity for the Day picker |
| LEAD-001 | ≥51 own leads across stages, priorities, products (Overseas Education products), campaigns, with today/overdue follow-ups; one handed-over lead ("With counselor") |
| LEAD-002/003 | Active overseas products + campaigns (with source); an "Other" product without a team (Division field); an existing lead with the same mobile (own and another telecaller's / other team, with previous enquiries) |
| LEAD-004..007 | One open lead with phone + WhatsApp + email; one with mobile only; one closed lead; one handed-over lead; one at Application/Enrollment |
| QUAL-001 | Lead with an overseas product; one with no product (empty state); prior save by another user ("Last updated by") |
| CALL-* | Lead in Assigned stage (to show First Call Pending / Contacted moves); a call logged today (Edit/Delete visible) and one from an earlier day (no actions) |
| FUP-* | Open, done, cancelled and overdue follow-ups on one lead; follow-ups due on another day |
| APPT-* | ≥2 active overseas `counselor` users; one lead with an open booking; a completed and a cancelled appointment for history; a counselor clash slot |
| MSG-* | Active WhatsApp and email templates (one with {brochure_link} + active brochure, one for another product, one with a placeholder that renders empty); SMTP configured; email in each status (queued/sent/retrying/failed) |
| CONT-001 | Active call script with steps for the lead's product; a product without a script |
| MEET-* | Active BDMs of types college/agent/school; requests in Pending, Accepted (with appointment), Declined (with reason) |
| HAND-* | Active overseas counselor; a lead handed over; a linked student with an overseas application (incl. `enrolled` → Converted) and a visa case; a returned lead |
| TIME-001 | A lead with >50 timeline events of every kind (website-created, round-robin assignment, calls, messages, follow-ups, appointment, handover, student link, milestone) |

## (c) Open questions

1. **Q1 (cross-team product):** An Overseas telecaller can pick any active product, including an IT one; the lead becomes `division=it` but stays theirs (`lead_intake.py:95-130`, `telecaller_catalogue.py:23-30`). Intended? Should the guide tell Overseas telecallers to pick only "Overseas Education" products? NEEDS_CONFIRMATION.
2. **Q2 (closed lead edits):** Priority, Lead details and Qualification remain editable on a closed lead (only handover blocks writes). Intended (T13/D2)? NEEDS_CONFIRMATION.
3. **Q3:** Exact bodies of "New lead assigned", "Lead not contacted" and "Lead returned for follow-up" alerts, and the email copy wording — read from `telecaller_alerts.py` in the ACC module session or capture from Mailpit.
4. **Q4:** "Management tasks" sits in the telecaller sidebar (mgmt-028). Does a telecaller ever receive tasks? Include in this guide or the Management guide?
5. **Q5:** The **Call** button shows on closed and handed-over leads (dialer only, no log form). Document as "call without logging" or treat as a gap?
6. **Q6:** The Follow-ups Day picker accepts future days and any past day — confirm wording for the guide (planning ahead).
7. **Q7:** Telecaller UI never shows the stage history endpoint (`GET …/stage-history`) separately — the timeline covers it. Confirm no separate screen is expected.
8. **Q8:** Overseas vs IT counselor availability: if no active overseas counselor exists, both booking and handover are blocked ("There is no active counselor in this lead's division yet."). Confirm the demo/prod data plan has overseas counselors.
9. **Q9:** Login copy on `/overseas/login` does not mention telecallers (as with schools) — confirm whether that is acceptable for the guide's sign-in step (browser check required).
