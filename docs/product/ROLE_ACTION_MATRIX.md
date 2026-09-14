# Role / Action Matrix

Consolidated from `docs/product/PRD.md` (confirmed functional requirements) and the extended
reference implementation's own `ROLE_ACCESS_MATRIX.md` / `SCREEN_ROUTE_MAP.md` / `ARCHITECTURE.md`
(`docs/evidence/REFERENCE_IMPLEMENTATION_FINDINGS.md`). **17 roles total** (updated 2026-09-14,
twice — first a single School Representative propagated from `DEC-SCOPE-009`, then superseded the
same session by `DEC-SCOPE-011`'s four-role School structure): 1 public, 5 IT-division,
5 Overseas-division, 1 global, plus 5 net-new (Employer, and — School — Principal, Coordinator,
Teacher, Parent). Every division-scoped user belongs to exactly one division (`it` / `overseas` /
`global`) per the codebase's own architecture — Student is the one identity that spans both
divisions under this project's confirmed `DEC-ROLE-001`, narrowed by `DEC-ROLE-004` to
self-authenticating applicants only.

Status tags: **[base]** = already exists in the reference implementation, extended as noted;
**[new]** = net-new build work this project adds on top of the base codebase.

---

## Visitor (public, unauthenticated)
- Browse public content: home, about, courses/programs, career paths, real projects, success
  stories, business services, blog, FAQ, search, news, gallery (`PRD-PUB-001, 003–010`)
- Browse Overseas public content: countries, universities, courses, admission process, visa
  services, scholarships, events (`PRD-OVS-001, 006, 007`, `PRD-VISA-001–003`)
- Submit an enquiry / request a callback → routed to Admin, synced to Zoho CRM (`PRD-PUB-002`)
- Register interest in a webinar/event or Overseas event (`PRD-PUB-009`, `PRD-OVS-007`)
- Browse public job openings and apply with a resume; track an application by tracking code + email
  without an account **[base]**
- Sign up / log in (division-specific: IT login or Overseas login)

## IT Division

### Student (`it_student`)
- Enrol in a course: select trainer/time-slot (20/slot cap, locked once booked, ~3-month duration)
  (`PRD-STU-001`, `DEC-WF-002`)
- Dashboard: progress, attendance, pending fees, applied jobs, upcoming assignments (`PRD-STU-002`)
- Join live classes (Zoho default, Google Meet retained) (`PRD-STU-003`)
- Submit assignments, view scores/feedback (`PRD-STU-004`)
- Raise/track a support ticket (`PRD-STU-005`)
- View attendance record (`PRD-STU-006`), progress/completion (`PRD-STU-007`)
- Download certificates (`PRD-STU-008`)
- Submit course/trainer feedback (`PRD-STU-009`)
- Review/accept digital agreement (`PRD-STU-010`)
- Payments: dashboard, EMI schedule, invoices, receipts — Razorpay only
  (`PRD-STU-011`, `PRD-PAY-001–003`)
- Manage own profile/documents (`PRD-STU-012`)
- **[base]** Examinations, projects, interview schedule, placement status, job applications,
  downloads (`SCREEN_ROUTE_MAP.md` — carried forward as PROPOSED detail under `PRD-STU-002`/`004`)

### Trainer (`trainer`) — "Teacher" is the same role, per `DEC-ROLE-002`
- View "My Batches" — own assigned batches only (`PRD-TRN-001`)
- Open batch detail: roster + schedule (`PRD-TRN-002`)
- View/join upcoming sessions from a dashboard (`PRD-TRN-003`)
- Access recording list for their batches (`PRD-TRN-004`)
- Upload course resources/notes (`PRD-TRN-005`)
- Create/edit assignments (`PRD-TRN-006`)
- Create/edit assessments — distinct type, draft/scheduled states (`PRD-TRN-007`)
- Review submissions, grade/feedback (`PRD-TRN-008`)
- Mark attendance (`PRD-TRN-009`)
- Respond to student Q&A (`PRD-TRN-010`)

### Placement Team (`placement_team`) **[base]**
- Manage candidate pool (placement-ready students)
- Review company hiring requirements
- Coordinate interviews
- Manage job offers
- View placement reports

### HR Team (`hr_team`) **[base]**
- Manage hiring/job requirements
- Review candidate shortlists
- Coordinate interviews
- (Distinct from the new self-service Employer role below — this is EduSphere-internal staff
  handling corporate hiring, not the hiring company's own account)

### IT Admin (`it_admin`)
- User/course/batch administration (`PRD-ADM-001`)
- View/route enquiries synced via the CRM webhook, configured for Zoho (`PRD-ADM-002`)
- Create batches, assign trainers, set capacity (`PRD-ADM-003`)
- Directory + detail management: Students, Trainers, Employers (`PRD-ADM-006`)
- Enrolment review and approval (`PRD-ADM-007`)
- **[PROPOSED, unconfirmed]** Resources/recordings oversight (`PRD-ADM-008`), certificate
  administration (`PRD-ADM-009`), agreement/consent oversight (`PRD-ADM-010`), notification
  template management (`PRD-ADM-011`), roles/permission administration (`PRD-ADM-013`)
- **[PROPOSED, unconfirmed — may belong to Super Admin instead]** System settings, audit logs, data
  import/export, backups, system health (`PRD-ADM-012`)

## Overseas Division

### Student (`overseas_student`) — same identity as IT Student, per `DEC-ROLE-001`
- Submit Overseas interest/application (country/university/course) (`PRD-OVS-002`)
- Track application through the confirmed stage sequence: Enquiry → Eligibility Evaluation →
  University/Course Selection → Offer → Visa Documentation → Status Tracking → Enrolment
  (`PRD-OVS-004`, `DEC-WF-001`)
- Upload documents against a checklist (varies by country/university/course) (`PRD-OVS-005`)
- Complete visa checklist, view interview prep, track visa approval status (`PRD-VISA-001–003`)
- Apply for scholarships (`PRD-OVS-006`)
- Register for Overseas events/webinars (`PRD-OVS-007`)
- **[base]** View offer letters, appointments, payments, counselor-chat (direct messaging with
  their assigned counselor), university communication (`SCREEN_ROUTE_MAP.md`)
- **`DEC-ROLE-004` (2026-09-14) narrows who ever holds this identity:** `DEC-ROLE-001`'s "same
  identity, extended" unification assumed every Overseas applicant is a self-authenticating
  account. This identity/login is now confirmed to apply only to an EduSphere-direct or
  self-registered applicant — an Agent-referred applicant and a School-affiliated student are never
  issued it at all. Their equivalent actions above are performed by the Agent (see the Agent section
  below) or, for a School-affiliated student, the `Counselor` role below, per `DEC-ROLE-005` —
  service-delivery data including any Overseas-application journey a school student pursues is the
  Counselor's job, not the School Coordinator's (the School Coordinator owns roster/operational data
  only, see the School section below).

### Counselor (`counselor`) **[base]** — internal case-management staff, distinct from Agent
- Manage assigned students and leads
- Review/verify student documents
- Manage applications and visa cases (checklist, status)
- Manage appointments
- View reports
- Maintain checklist/evidence status per country/university (per the live site's own visa-services
  and country-guide copy)
- **Confirmed as the actor for School-affiliated service-delivery data — `DEC-ROLE-005`, resolved
  2026-09-14.** An earlier pass here inferred this from `DEC-SCOPE-009`'s generic wording alone,
  which was an unwarranted jump — corrected, then asked directly and confirmed by the user: this
  role is extended to also cover school-affiliated case management (career guidance, psychometric,
  counselling — whenever those modules are built), rather than building the four specialized roles
  `EVID-014` §13 proposed. **Division of labor with the School Coordinator role** (see the School
  section below): Coordinator owns roster/operational data (create/manage students, attendance,
  scheduling); Counselor owns service-delivery data. Neither Career Guidance, Psychometric, nor
  Counselling exist as a buildable module yet — `DEC-ROLE-005` only settles *who* would manage that
  data once/if built, not whether it's in scope (`PRD_OPEN_ITEMS.md` item 71).

### University Representative (`university_rep`) **[base]** — external partner-university portal
- Review applications sent to their institution
- Track/update offer letters
- Post admission updates
- Communicate with applicant students
- View reports

### Agent (`agent`)
- Self-register — held **pending Overseas Admin approval** before active (`PRD-AGT-001`,
  `DEC-SCOPE-004`)
- View roster of referred students and each one's application status, scoped to their own referrals
  only (`PRD-AGT-002`)
- View commission accrued per referral — **[extended]** now auto-created on the finalized+joined
  trigger rather than admin-manual timing; amount stays admin-discretionary per application, not a
  fixed rate (`PRD-AGT-003`, `DEC-SCOPE-005`)
- Claim commission payout — **[extended]** now requires a genuine, separate Overseas Admin approval
  step before paid, closing a gap the base codebase left open (`PRD-AGT-004`)
- **[not yet built, `DEC-ROLE-004`, 2026-09-14]** Create a referred student's record and perform
  the Overseas application actions on their behalf — submit an application, track status, upload
  documents — because an Agent-referred student is never issued a login. This is new grant scope
  beyond `AGT-002`'s current read-only roster view; parallels `OVS-002`/`004`/`005`'s "Self
  (Student)" actions but attributed to the acting Agent. See `RBAC_MATRIX.md` §2.8 and
  `PRD_OPEN_ITEMS.md` item 68.

### Overseas Admin (`overseas_admin`)
- Approve or reject pending Agent registrations (`PRD-ADM-004`, `DEC-SCOPE-004`)
- Approve commission payouts, separately from accrual (`PRD-ADM-005`, `DEC-SCOPE-005`)
- **[base]** Manage users, students, counselors, universities, applications, leads, payments;
  view reports (`ROLE_ACCESS_MATRIX.md`)

## School **[new — net-new build, no equivalent role exists in the base codebase; propagated from `DEC-SCOPE-009` 2026-09-14, role structure superseded by `DEC-SCOPE-011` 2026-09-14]**

`DEC-SCOPE-009` originally confirmed a single, undifferentiated, read-only login per school.
`DEC-SCOPE-011` (resolved 2026-09-14, same session, asked directly) superseded that login-cardinality
clause: the user adopted the full four-role structure `EVID-014` §33 describes, each scoped
server-side to their own institution only ("they can access the respective school data only").
`DEC-SCOPE-009` itself is kept, not deleted, per this project's traceability convention — only its
single-login clause is superseded.

### Principal (`school_principal`)
- **Read-only.** Complete school dashboard, student statistics, career progress, global education
  status, reports — for their own institution only (`DEC-SCOPE-011`)
- **Not granted:** create/edit/delete any student record

### School Coordinator (`school_coordinator`) — **write access; distinctly named to avoid colliding
with the existing `coordinator` role** (`DEC-ROLE-003`'s certificate-issuance Coordinator — an
unrelated, EduSphere-internal role)
- Create/manage student records for their own institution, one at a time (`DEC-SCOPE-011`)
- **Bulk upload student rosters** — template-download-first workflow: download a fixed template,
  fill offline, upload, server-side validation, row-level accept/reject report (`DEC-SCOPE-010`
  part 1, `CONFIRMED_CURRENT` 2026-09-14)
- Schedule activities, track attendance, monitor services, generate reports for their own
  institution (`DEC-SCOPE-011`)
- **Not granted:** academic results upload/management — no results module is confirmed at all
  (`DEC-SCOPE-010` part 2, still `PENDING`); career guidance/psychometric/counselling content
  creation, which stays with the Counselor (see below)

### Teacher (`school_teacher`) — **distinctly named; not `DEC-ROLE-002`'s Trainer/Teacher**, which
remains EduSphere's own IT-training instructor role, an unrelated actor
- View their **assigned** students only (not the whole school), attendance, career activities,
  student progress (`DEC-SCOPE-011`)
- **Read-only** — no grant to create/edit any student record

### Parent (`school_parent`)
- View their own child's/children's profile and progress only — never another student's, even
  within the same institution (`DEC-SCOPE-011`)
- **Read-only**

*Note on who manages the underlying data (`DEC-ROLE-005`, resolved 2026-09-14): School Coordinator
(above) owns roster/operational data — creating/maintaining student records, scheduling, attendance.
The existing `Counselor` role (Overseas Division above, extended) owns service-delivery data — the
substantive content of career guidance/psychometric/counselling work, if and when those modules are
built. **Neither Career Guidance, Psychometric, nor Counselling exist as a buildable module yet** —
`DEC-ROLE-005` only settles who would manage that data once/if it's built, not whether it's in scope.
How the School partner record itself and each of these four accounts are provisioned (self-service
vs. Admin-created) remains **OPEN**, not yet specified by any decision or evidence.*

## Employer **[new — net-new build, no equivalent role exists in the base codebase]**
- Register a company account (`PRD-EMP-001`; approval-before-activation workflow still open)
- Post job openings (`PRD-EMP-002`)
- Search/browse candidate profiles, within GDPR-approved visibility limits (`PRD-EMP-003`)
- Schedule interviews with shortlisted candidates (`PRD-EMP-004`)
- Maintain a shortlist (`PRD-EMP-005`)
- View scheduled/past interviews (`PRD-EMP-006`)
- **[PROPOSED, unconfirmed]** Track placement status per candidate (`PRD-EMP-007`)

*Note: the base codebase handles corporate hiring entirely through Placement Team/HR Team (above)
plus a public apply/track flow — the Employer role above is being built alongside that existing
model, not replacing it. How the two coexist (does Placement Team mediate Employer-posted jobs, or
does Employer post directly?) is not yet specified — worth confirming before Feature Catalogue
work on this role.*

## Global

### Super Admin (`super_admin`) **[base]**
- Central dashboard spanning both divisions
- Manage users, students, staff, programs, batches, universities, recruiters
- CMS: content pages, blogs, events
- Manage leads, applications, payments
- View reports; manage notifications
- Manage roles, system settings, security logs, backups

---

## Open questions this matrix surfaces

1. Employer/Placement Team/HR Team interaction model — not yet specified (see note above).
2. Whether Super Admin or IT Admin owns the operational-tooling cluster (`PRD-ADM-012`) — currently
   ambiguous between the two.
3. Whether "same Student identity" (`DEC-ROLE-001`) means one account can hold both `it_student` and
   `overseas_student` simultaneously, or whether the base codebase's division-pinned-per-user model
   needs adjustment to support that — not yet reconciled at the implementation level.

These are Architecture/Contracts-phase questions (`prompts/08`, `prompts/09`), not blocking this
matrix — flagged here so they aren't lost.
