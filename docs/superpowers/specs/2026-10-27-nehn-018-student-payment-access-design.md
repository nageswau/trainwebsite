# nehn-018 — Student feature access by enrolment and payment status (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-018` (§6 L148-151, §24; `UNVERIFIED` backlog).
Dependency nehn-003 (private file serving) is `Done`. OD-06 (which feature unlocks at which payment state) is still open with the
client, so this build ships **builder's defaults** (the owner pre-authorised recommended answers, as for DEC-SCOPE-298), all
`NEEDS_CONFIRMATION`, inside a policy the IT admin can change without a release (AC4).

## Intent

Before paying, an IT student sees course and enrolment information, fees and payment. The other learning features unlock when the
student's payment state reaches the minimum the policy sets for that feature. The API enforces it; the UI shows a locked section
with a "Complete payment to unlock" call to action instead of hiding the page.

## Payment state (one per student, derived live — never stored)

Computed by `services/student_access.student_state(db, student_id)` from the student's own rows on every request, so a Razorpay
webhook that marks a payment paid unlocks the next request (AC2) — no re-login, no cache across requests.

| State | Rule (first match wins) |
|---|---|
| `registered` | no enrolment other than `rejected` / `withdrawn` / `dropped` |
| `fully_paid` | nothing owed: no IT payment `pending` / `overdue` with amount > 0 |
| `partially_paid` | something owed, and at least one IT payment `paid` / `succeeded` (EMI instalment 1 counts) |
| `enrolled_pending_payment` | something owed, nothing paid |

Order: `registered` < `enrolled_pending_payment` < `partially_paid` < `fully_paid`. Same money basis as certificate eligibility's
`pending_fee` (IT division, pending/overdue). Consequences (builder's calls, `NEEDS_CONFIRMATION`):

- A free course, or a student never billed, is `fully_paid`. A fee discounted to 0 is `fully_paid` (edge case "100% discount").
- An overdue instalment does not re-lock a student who has paid something. A refund does not re-lock (a refunded row is neither
  owed nor paid).
- State is per student, not per enrolment (payments do not reliably reference an enrolment; certificate eligibility uses the same
  student-wide rule). A student with two enrolments owes across both.
- overseas_student is not gated (OD-06 open part).

## Policy

Table `student_access_rules(feature PK, min_state, updated_by_id, timestamps)`, the `certificate_rules` keyed-row idiom. One row per
feature; a missing row falls back to the default. Read on every check, so an admin's change applies to the next request (AC4).

| Feature key | Gates | Default minimum |
|---|---|---|
| `attendance` | Attendance section, `GET /workflows/it/student/attendance`, `POST .../attendance-corrections` | `partially_paid` |
| `assignments` | Assignments + Projects sections, `POST /it/assignments/{id}/submissions`, student `GET /it/submissions/{id}/files/{fid}` | `partially_paid` |
| `assessments` | Examinations section, `POST /it/assessments/{id}/attempts`, `POST /it/assessment-attempts/{id}/submit` | `partially_paid` |
| `resources` | Downloads section, student `GET /it/materials/{id}/file` | `partially_paid` |
| `live_classes` | student `GET /communications/it/live-sessions` (the Course page's live-classes panel) | `partially_paid` |
| `questions` | Questions section, `GET`/`POST /it/student/questions` | `partially_paid` |
| `feedback` | Feedback section, `POST /it/student/feedback` | `partially_paid` |
| `certificates` | Certificates section, student `GET /it/certificates/{id}/download` | `partially_paid` |

Default rationale: "the first instalment starts the course" — the most common rule, and it keeps every seeded/demo student (paid
one instalment) working. Issuing a certificate still requires no fee owed (unchanged nehn-031 eligibility).

Never gated: dashboard (its "upcoming work" rows are hidden while assignments are locked), profile, course, fees, placement,
interview schedule, job applications, support, agreements, batch selection, notifications.

## API

- `GET /workflows/it/student/access` (it_student): `{state, features: [{key, label, unlocked, required_state}]}`.
- `GET /workflows/it/student-access/rules` and `PUT` (full replacement: every feature, each a known state; 422 otherwise) —
  permission `student_access.configure` (new catalogue entry, granted to it_admin by migration; super_admin implicit). The PUT is
  audited (`student_access_rules.update`, before/after).
- A gated route refused for payment: **403** with the codebase's structured detail
  `{"message": "Complete your payment to unlock <Label>.", "code": "payment_required", "feature", "required_state", "current_state"}`.
  403 rather than 402 (402 is reserved; every client here already treats 403 as "not allowed").
- Ordering: the role/ownership checks run first; the payment check runs only for it_student, so other roles are unchanged and a
  wrong-batch learner still gets the existing 404 (no existence leak).
- Portal section (`GET /portal/it/student/<section>`) of a locked feature: 200 with an empty table and
  `locked: {feature, label, required_state, current_state}` (additive key) — the page renders the locked card.
- `GET /workflows/it/student/learning` (not used by the web app): locked features' lists come back empty; adds an `access` key.

## Web

- `PortalPage` (it/student only) reads `/workflows/it/student/access` once per request; a locked section renders
  `LockedFeatureCard` (heading, why, current status, "Complete payment to unlock" → `/it/student/fees`) instead of the section and its
  action panels. The Course page hides `LiveClassesPanel` behind the same card when live classes are locked.
- Sidebar: a locked item keeps its link and gets a "Locked" badge (not hidden).
- `it/admin/payments`: `AdminStudentAccessPanel` — one select per feature, save, the success/error message idiom of
  `AdminCertificatePanel`.

## Non-goals

Per-enrolment gating, re-locking on overdue/refund, overseas gating, hiding the fees page, any change to payment/webhook code.

## Risks

- e2e/backend tests that enrol a fresh student into a paid program and then use learning features: the enrolment bills a pending
  fee, so they are now locked. Fixtures record a paid payment (the backlog's stated mitigation), product behaviour is not bent.
- Permission catalogue tests that enumerate keys.

## Plan (TDD, focused tests)

1. Migration 0206 + model `StudentAccessRule` + catalogue/grant; migration round-trip test.
2. `services/student_access.py`: state derivation + policy read + `require`; unit tests per state and edge case.
3. Access + rules endpoints; tests (roles, 422s, audit, immediate effect).
4. Route guards (table above) + portal locked payload + learning payload; tests: unpaid → 403 `payment_required`, paid → 200,
   webhook-paid → unlocked, other roles unchanged.
5. Web: types, `LockedFeatureCard`, PortalPage/nav wiring, admin panel; vitest.
6. Fix affected existing tests' fixtures; e2e spec for locked → pay → unlocked; docs (decision, API, RBAC, data model, RTM, tracker).
