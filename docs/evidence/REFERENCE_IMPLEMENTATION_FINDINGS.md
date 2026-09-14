# Reference Implementation Findings — External Source Code

NO-ASSUMPTION MODE. This documents a **new evidence source outside `docs/sources/`**, per the
user's direction this session to inspect `http://127.0.0.1:3003/` and then, mid-investigation, to
refer directly to its source code at:

`C:\Users\admin\Documents\freelance\edusphere\Edusphere_Full_Implementation_Package\Edusphere_Complete_Source_Code_Seed_Deployment\edusphere-platform`

**This is not in `docs/sources/` and was not part of the original evidence set.** It is a complete,
runnable, already-built full-stack implementation (Next.js + FastAPI + PostgreSQL + Redis/Celery),
with its own README, architecture doc, role/route/API catalogues, and a seeded database. A
`.claude-cache` directory and an `edusphere_claude_handoff_complete/` folder inside it strongly
suggest it was itself produced by a prior (or parallel) AI-assisted engineering effort — making it,
by `CLAUDE.md`'s own definition, a **prior AI-generated artifact**, not automatically authoritative,
no matter how detailed or professional it looks. It is documented here neutrally, with every
conflict against this project's already-**confirmed** Decision Register called out explicitly and
left for the user to resolve — nothing below has been used to silently change any decision, BRD, or
PRD content yet.

## 1. What was inspected, and how

- HTTP-only crawl of the running instance (45+ pages, `robots.txt`, `sitemap.xml`) before the source
  path was given.
- Direct reading of the source tree's own documentation: `README.md`, `docs/ARCHITECTURE.md`,
  `docs/ROLE_ACCESS_MATRIX.md`, `docs/SCREEN_ROUTE_MAP.md`, `docs/API_CATALOGUE.md`.
- Direct reading of `backend/app/models.py` (all 47 SQLAlchemy model classes) and targeted reading
  of `backend/app/api/workflows.py` (commission claim/create logic) and `backend/app/seed.py`
  (demo status-transition data).
- **Not read:** `.env` (contains secrets — deliberately skipped). Not logged into any portal, no
  write actions taken, no destructive commands run. This was read-only inspection of a local
  instance the user pointed me to directly.

## 2. Quantitative confirmation of the user's own observation

The user said "most business rules may exist for [IT] but not overseas." Counting distinct domain
model classes in `models.py`:

- **IT-side domain models (~19):** Program, Batch, Enrollment, Attendance, AttendanceCorrection,
  Assignment, Assessment, AssessmentQuestion, AssessmentAttempt, AssessmentAnswer, Submission,
  LearningResource, Certificate, Company, Job, JobApplication, Interview, PlacementProfile,
  JobOffer.
- **Overseas-side domain models (~9):** Country, University, OverseasCourse, OverseasApplication,
  ApplicationStatusHistory, StudentDocument, VisaCase, Scholarship, ScholarshipApplication (plus
  Appointment, AgentStudent, AgentCommission, InboundUniversityEmail, which are Overseas-adjacent).

Roughly 2:1 in favor of IT-side depth — the user's characterization holds up against the actual
code, not just impression.

## 3. Full role model (three independent sources agree)

`robots.txt` (crawled), `docs/ROLE_ACCESS_MATRIX.md`, and `docs/ARCHITECTURE.md` §4 all
independently state the same 11 roles:

| Division | Roles |
|---|---|
| IT (`it`) | `it_student`, `trainer`, `placement_team`, `hr_team`, `it_admin` |
| Overseas (`overseas`) | `overseas_student`, `counselor`, `university_rep`, `agent`, `overseas_admin` |
| Global (`global`) | `super_admin` |

**Conflict with this project's confirmed role model:** this reference implementation has **no
"Employer" role at all.** Corporate hiring is handled by two internal EduSphere roles
(`placement_team`, `hr_team`) plus a public, unauthenticated job-application/tracking-code flow —
not a self-service Employer account with its own login, job posting, and candidate search as
`DEC-SCOPE-002` confirmed with the user in this session. This is a direct structural conflict, not
a detail gap — flagged in §6, not resolved here.

**New roles not in this project's Decision Register at all:** `placement_team` and `hr_team` (IT
side — distinct internal staff roles, not the same as "Admin"); `counselor` and `university_rep`
(Overseas side — `counselor` is internal case-management staff distinct from `agent`; `university_rep`
is an external **university partner portal** user, reviewing applications sent to their institution);
`super_admin` (a global, cross-division role with its own dashboard, CMS, security logs, and
backups — not modeled anywhere in this project's BRD/PRD, where these capabilities were tentatively
sketched as `PROPOSED` sub-items of a generic Admin, `PRD-ADM-012`/`PRD-ADM-013`).

## 4. Screen/section inventory (from `docs/SCREEN_ROUTE_MAP.md`)

Notable sections not previously named anywhere in this project's evidence:

- **IT Student portal:** `examinations` (distinct from assignments/assessments), `projects`
  (distinct portal section), `interview-schedule`, `placement-status`, `job-applications` — a
  Student-facing view of their own job applications, not just an Employer-facing candidate search.
- **Overseas Student portal:** `offer-letters`, `appointments`, `counselor-chat` (direct messaging
  with an assigned counselor), `university-communication`.
- **Super Admin:** `security-logs`, `backups`, `roles`, `settings` — a dedicated cross-division
  operations cluster, matching what this project's PRD had marked `PROPOSED`/unconfirmed
  (`PRD-ADM-012`) but never confirmed as actually needed.

## 5. Overseas business-rule detail extracted directly from code

More precise than anything in this project's evidence to date, but note: **code-level detail is not
the same as client-confirmed business rule.** None of this has been asked of, or confirmed by, the
user in this session.

### 5.1 Application state model
`OverseasApplication.status` is a free-text string field, default `"profile_evaluation"` — **not**
a fixed enum enforced at the database level. The only observed transition (from `seed.py`'s demo
data) is `profile_evaluation → university_review`. `"university_review"` is a status value that
does **not** appear in the public admission-process page's 10 marketing-facing stage names
(`§7` below) — meaning the real coded state model is more granular than the public-facing stage
list, and the two have not been reconciled even within this reference implementation itself.
`ApplicationStatusHistory` records each transition with `from_status`, `to_status`, `next_action`,
`notes`, and `changed_by_id` — a real audit trail exists in code, addressing this project's
`NFR-AUDIT-001` (currently `PROPOSED`, unconfirmed) for this specific domain, in this specific
implementation.

### 5.2 Visa case model
`VisaCase.status` defaults to `"checklist"`; other fields: `appointment_date`, `checklist` (JSON
list — so the checklist itself is data-driven, not hardcoded), `tracking_reference`. No fixed set
of valid status values was found enforced anywhere in the backend code searched.

### 5.3 Document verification
`StudentDocument.verification_status` defaults to `"pending"`, with `reviewer_notes` and
`verified_by_id` — a real reviewer/approval trail, addressing part of `PRD_OPEN_ITEMS.md` item 6
(document checklist) at a mechanism level, though not the actual checklist content itself (that's
still admin/CMS-managed data, not hardcoded).

### 5.4 Agent commission — differs from what was confirmed with the user
Actual code behavior (`backend/app/api/workflows.py` lines ~1478-1540):

- `POST /workflows/overseas/agent/commissions` — **Overseas Admin manually creates** a commission
  record for a specific `agent_id` + `application_id` pair, **manually entering the `amount` and
  `currency`** (default currency `INR`). Initial status: `"eligible"`. The endpoint validates that
  the named agent is actually assigned to that application, but does **not** check the
  application's status (finalized/joined) before allowing commission creation — that check, if it
  exists, is left to the admin's judgment, not enforced by the system.
- `POST /workflows/overseas/agent/commissions/{id}/claim` — the **agent** claims it (allowed when
  status is `"eligible"` or `"estimated"`), which sets status to `"claimed"`, stamps `claimed_at`,
  and generates a `claim_reference`.
- A `paid_at` field exists on the model but no `.../pay` or `.../approve` endpoint was found in the
  section searched — payout confirmation likely happens elsewhere (e.g. an admin payments screen),
  not shown in the code read so far.

**This conflicts with what the user confirmed for `DEC-SCOPE-005` in this session** — that
commission accrual should be **automatic**, triggered specifically by "application finalized **and**
student joined the college," with payout requiring a **separate Overseas Admin approval** step. The
reference implementation instead has: **no automatic trigger** (admin manually creates the
commission whenever they judge it appropriate, with a manually-chosen amount, not a rate/percentage)
and **no separate payout-approval step distinct from admin's own creation action** (found so far —
payout mechanics may exist elsewhere, not yet located). This is a real discrepancy, not a rounding
error — flagged in §6, not silently reconciled.

## 6. Direct conflicts with this project's confirmed Product Decision Register

*(All conflicts below are now resolved — see §9. Kept here as the historical record of what was
found and why each reconciliation call was needed.)*

| Decision | Confirmed in this project (2026-09-01) | This reference implementation | 
|---|---|---|
| `DEC-ARCH-001` Architecture | Microservices | **Domain-oriented modular monolith**, explicitly chosen "to reduce service-to-service networking, distributed transactions, observability overhead" (its own `ARCHITECTURE.md` §1) |
| `DEC-INFRA-001` Cloud | DigitalOcean | **AWS** — ECS Fargate, RDS, ElastiCache, S3, CloudFront (its own `ARCHITECTURE.md` §2) |
| `DEC-SCOPE-002` Employer Portal | Confirmed current, as a self-service Employer role (register/post jobs/search candidates/schedule interviews) | **No Employer role exists.** Corporate hiring is internal-staff-mediated (`placement_team`, `hr_team`) plus a public apply/track flow |
| `DEC-SCOPE-001` CRM | Zoho CRM specifically | Generic "internal enquiry record + **optional external CRM webhook**" — provider-agnostic, not Zoho-specific |
| `DEC-PAY-001` Payment gateway | Stripe | **Both Razorpay and Stripe** adapters present |
| `DEC-LIVE-001` Live-class provider | Zoho (Meeting) | **Both Google Meet and Zoho Meeting** adapters present |
| `DEC-NOT-001` Notifications | Email + WhatsApp (Twilio) | Email + **SMS** + WhatsApp — SMS is additional, provider unspecified as Twilio |

Two of these (`DEC-ARCH-001`, `DEC-INFRA-001`) are the two highest-impact technical decisions in the
entire register, made by the user directly, in this session, overturning the *original* blueprint's
recommendations. This reference implementation's choices happen to match the *original superseded
blueprint's* AWS/modular-monolith position, not the user's own subsequent decision. That
coincidence is noted, not resolved — it does not make either position more or less correct.

## 7. Where this corroborates, rather than conflicts with, existing work

- The 10-stage admission-process sequence on the public marketing page (Career Counseling → Profile
  Evaluation → University Selection → Application → Admission → Financial Documentation → Visa
  Documentation → Visa Filing → Travel Assistance → Pre-Departure Orientation) matches `DEC-WF-001`'s
  confirmed base sequence closely (same stages, different granularity of naming) — though §5.1
  shows the actual *coded* states are more granular still and not fully reconciled with this public
  list even within this same codebase.
- `docs/ARCHITECTURE.md` §7 states a 10,000+ registered user scalability target — corroborates this
  project's `NFR-SCALE-001` (currently `PROPOSED`, sourced only from the client's own original
  tech-stack document, EVID-010).
- `docs/ARCHITECTURE.md` §8 explicitly states EduSphere UK still needs to define "lawful basis,
  retention periods, deletion/export processes" — i.e. this reference implementation's own authors
  *also* flagged GDPR retention detail as unresolved, matching this project's own
  `PRD_OPEN_ITEMS.md` item 15.
- The visa-services page's own compliance language ("The application should not represent EduSphere
  as the visa decision-maker... current official immigration rules must be verified per destination")
  is a good, concrete candidate business rule this project has not yet explicitly stated anywhere —
  worth adding regardless of the architecture/cloud conflicts.
- Placeholder/deferred-config language is used consistently throughout the live site's copy instead
  of invented data ("Configure your approved WhatsApp Business provider... in production settings,"
  "after the client confirms the final office address," "optionally synchronized to the configured
  CRM webhook") — the seeded database is genuinely empty of fabricated marketing content (0
  programs, 0 scholarships, 0 events, 0 news articles). This is a meaningfully disciplined build,
  whatever its provenance — it does not fabricate facts it doesn't have, which is exactly this
  project's own standard.

## 8. What this document did NOT do at the time it was written *(superseded by §9 — resolutions
did follow, in the same session)*

- At time of writing, it did not itself change the status of any Decision ID, BRD, or PRD content —
  that required the explicit user answers recorded in §9, after which
  `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/product/BRD.md` (now v1.3), and
  `docs/product/PRD.md` were all updated accordingly.
- It does not classify this source as any existing evidence type from `CLAUDE.md`'s list — none fit
  cleanly (closest is `DERIVED_BLUEPRINT`, but this is executable code plus its own architecture
  decision record, a step beyond a planning document). Recorded here as **UNVERIFIED — external
  reference implementation, provenance and approval status unknown.**

## 9. Resolution — RESOLVED 2026-09-01 (same session)

The three-way question originally posed here is answered: the user confirmed **option 3** in
substance — this reference implementation is the actual codebase to extend (not just functional
reference), but not every conflicting choice was adopted wholesale. Specifically, resolved via two
rounds of direct questions:

| Conflict from §6 | Resolution |
|---|---|
| Architecture (microservices vs. modular monolith) | **Revised to modular monolith** — matches the codebase; extending it while rewriting the architecture would be a rebuild, not an extension. |
| Cloud (DigitalOcean vs. AWS) | **Kept DigitalOcean** — the codebase's Docker/Postgres/Redis workload gets retargeted, not its native AWS/ECS Fargate topology. |
| Employer role (missing vs. confirmed) | **Build it** — net-new work on top of the existing Placement Team/HR Team model, not a replacement of it. |
| Commission logic (manual vs. automatic trigger) | **Extended** — kept the admin-discretionary amount (closing the "fixed rate?" question permanently: there isn't one), added the missing automatic trigger and payout-approval gate. |
| Payment/live-class/notification/CRM provider breadth (narrower confirmed set vs. codebase's broader set) | **Keep all providers, extend instead of stripping** — Stripe/Zoho Meeting/Email+WhatsApp/Zoho-CRM stay primary/default; Razorpay, Google Meet, SMS, and the generic CRM-webhook framework are retained rather than removed. |

Full before/after history for each is in `docs/decisions/PRODUCT_DECISION_REGISTER.md`; propagated
to `docs/product/BRD.md` (v1.1, v1.2) and `docs/product/PRD.md`. The pattern across every
resolution: where the codebase has **more** than this project had confirmed, keep and extend; where
it has **less**, build the gap — never silently shrink a confirmed requirement to match what
happens to already exist.
